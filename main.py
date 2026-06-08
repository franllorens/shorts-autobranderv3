"""
Shorts Autobrander — Backend Principal
FastAPI + Whisper + Groq (Llama 3.1) + FFmpeg
Deploy-ready para Railway
"""

import os
import uuid
import subprocess
import textwrap
import tempfile
import shutil
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

# Usamos el cliente OpenAI apuntando a Groq (API compatible)
from openai import OpenAI

import whisper

# ──────────────────────────────────────────────
# CONFIGURACIÓN
# ──────────────────────────────────────────────

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = "llama-3.1-8b-instant"

# Directorio temporal de trabajo (se crea si no existe)
WORK_DIR = Path(tempfile.gettempdir()) / "autobrander"
WORK_DIR.mkdir(parents=True, exist_ok=True)

# Logo por defecto (debe existir junto a main.py)
DEFAULT_LOGO = Path(__file__).parent / "logo.png"

# Límites de validación
MAX_VIDEO_MB  = 50
MAX_VIDEO_SEC = 60

app = FastAPI(title="Shorts Autobrander", version="1.0.0")

# CORS abierto para que el HTML estático pueda llamar a la API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Archivos estáticos PWA ─────────────────────────────────────────
# Sirve íconos, manifest, splash screens y service worker
_static_dir = Path(__file__).parent / "icons"
if _static_dir.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/icons", StaticFiles(directory=str(_static_dir)), name="icons")

@app.get("/manifest.json")
async def serve_manifest():
    p = Path(__file__).parent / "manifest.json"
    return FileResponse(str(p), media_type="application/manifest+json")

@app.get("/service-worker.js")
async def serve_sw():
    p = Path(__file__).parent / "service-worker.js"
    return FileResponse(str(p), media_type="application/javascript",
                        headers={"Service-Worker-Allowed": "/"})

@app.get("/offline.html", response_class=HTMLResponse)
async def serve_offline():
    p = Path(__file__).parent / "offline.html"
    return HTMLResponse(content=p.read_text(encoding="utf-8"))

# Cargamos Whisper una sola vez al arrancar (evita recargar en cada request)
print("⏳ Cargando modelo Whisper 'base'…")
whisper_model = whisper.load_model("base")
print("✅ Whisper listo.")

# Cliente Groq (API compatible con OpenAI)
groq_client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)


# ──────────────────────────────────────────────
# UTILIDADES
# ──────────────────────────────────────────────

def segundos_a_srt_time(segundos: float) -> str:
    """Convierte segundos flotantes al formato HH:MM:SS,mmm de SRT."""
    h  = int(segundos // 3600)
    m  = int((segundos % 3600) // 60)
    s  = int(segundos % 60)
    ms = int((segundos - int(segundos)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def construir_srt(segments: list, subtitulos_virales: list[str]) -> str:
    """
    Combina los timestamps de Whisper con las líneas virales de Groq.
    Si hay más/menos líneas virales que segmentos, se reciclan o truncan.
    """
    lineas = subtitulos_virales if subtitulos_virales else [seg["text"].strip() for seg in segments]
    bloques = []

    for i, seg in enumerate(segments):
        texto = lineas[i % len(lineas)] if lineas else seg["text"].strip()
        inicio = segundos_a_srt_time(seg["start"])
        fin    = segundos_a_srt_time(seg["end"])
        bloques.append(f"{i+1}\n{inicio} --> {fin}\n{texto}\n")

    return "\n".join(bloques)


def parsear_subtitulos(raw: str) -> list[str]:
    """Limpia la respuesta de Groq: elimina líneas vacías y strips."""
    lineas = [l.strip() for l in raw.strip().splitlines() if l.strip()]
    return lineas


def borrar_archivos(*paths):
    """Limpia archivos temporales de forma segura."""
    for p in paths:
        try:
            if p and Path(p).exists():
                Path(p).unlink()
        except Exception as e:
            print(f"⚠️  No se pudo borrar {p}: {e}")


def get_video_duration(path: str) -> float:
    """Obtiene la duración del video en segundos usando ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


# ──────────────────────────────────────────────
# ENDPOINT: Servir frontend
# ──────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Sirve el index.html desde el mismo directorio que main.py."""
    html_path = Path(__file__).parent / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="index.html no encontrado")
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


# ──────────────────────────────────────────────
# ENDPOINT PRINCIPAL: /procesar
# ──────────────────────────────────────────────

@app.post("/procesar")
async def procesar(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    logo:  UploadFile = File(None),
):
    """
    Recibe video + logo opcional.
    1. Valida tamaño y duración.
    2. Transcribe con Whisper.
    3. Mejora subtítulos con Groq/Llama.
    4. Genera .srt con timestamps reales.
    5. Aplica FFmpeg: logo en esquina + subtítulos quemados.
    6. Devuelve el video final.
    """

    session_id  = uuid.uuid4().hex
    session_dir = WORK_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    video_in   = session_dir / "input.mp4"
    logo_path  = session_dir / "logo.png"
    srt_path   = session_dir / "subs.srt"
    video_out  = session_dir / "output.mp4"

    try:
        # ── 1. Guardar video ──────────────────────────────────────
        contenido_video = await video.read()

        if len(contenido_video) > MAX_VIDEO_MB * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail=f"El video supera los {MAX_VIDEO_MB} MB permitidos."
            )

        video_in.write_bytes(contenido_video)

        duracion = get_video_duration(str(video_in))
        if duracion > MAX_VIDEO_SEC:
            raise HTTPException(
                status_code=400,
                detail=f"El video dura {duracion:.0f}s. Máximo permitido: {MAX_VIDEO_SEC}s."
            )

        # ── 2. Guardar logo ───────────────────────────────────────
        if logo and logo.filename:
            logo_path.write_bytes(await logo.read())
        elif DEFAULT_LOGO.exists():
            shutil.copy(DEFAULT_LOGO, logo_path)
        else:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=none:s=1x1:r=1",
                 "-frames:v", "1", str(logo_path)],
                check=False, capture_output=True
            )

        # ── 3. Transcripción con Whisper ──────────────────────────
        print(f"[{session_id}] 🎙️  Transcribiendo con Whisper…")
        try:
            resultado_whisper = whisper_model.transcribe(
                str(video_in),
                language="es",
                fp16=False,
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error en Whisper: {str(e)}"
            )

        texto_crudo = resultado_whisper.get("text", "").strip()
        segments    = resultado_whisper.get("segments", [])

        if not texto_crudo:
            raise HTTPException(
                status_code=422,
                detail="No se detectó audio/texto en el video."
            )

        print(f"[{session_id}] ✅ Texto transcripto ({len(texto_crudo)} chars)")

        # ── 4. Mejorar subtítulos con Groq / Llama 3.1 ────────────
        print(f"[{session_id}] 🤖 Enviando a Groq…")
        prompt_viral = (
            "Sos editor de TikTok. Agarrá este texto y convertilo en subtítulos virales: "
            "Máximo 7 palabras por línea. Agregá 1-2 emojis. Todo en mayúscula. "
            "Cortá en frases con punch. Devolvé solo los subtítulos, uno por línea. "
            f"TEXTO: {texto_crudo}"
        )

        subtitulos_virales = []
        try:
            respuesta_groq = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt_viral}],
                temperature=0.8,
                max_tokens=512,
            )
            raw_subs        = respuesta_groq.choices[0].message.content
            subtitulos_virales = parsear_subtitulos(raw_subs)
            print(f"[{session_id}] ✅ Subtítulos virales generados ({len(subtitulos_virales)} líneas)")
        except Exception as e:
            print(f"[{session_id}] ⚠️  Groq falló ({e}). Usando transcripción raw.")
            subtitulos_virales = [seg["text"].strip() for seg in segments]

        # ── 5. Generar archivo .srt ───────────────────────────────
        srt_content = construir_srt(segments, subtitulos_virales)
        srt_path.write_text(srt_content, encoding="utf-8")
        print(f"[{session_id}] 📝 SRT guardado")

        # ── 6. Comando FFmpeg ─────────────────────────────────────
        subtitles_style = (
            "FontName=Montserrat,"
            "FontSize=22,"
            "PrimaryColour=&H00FFFFFF&,"
            "OutlineColour=&H00000000&,"
            "BackColour=&H80000000&,"
            "BorderStyle=3,"
            "Outline=2,"
            "Shadow=1,"
            "Alignment=2,"
            "MarginV=30"
        )

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", str(video_in),
            "-i", str(logo_path),
            "-filter_complex",
            (
                "[1:v]scale=150:-1[logo];"
                f"[0:v][logo]overlay=W-w-10:10:format=auto,format=yuv420p[vlogo];"
                f"[vlogo]subtitles='{str(srt_path)}':force_style='{subtitles_style}'[vout]"
            ),
            "-map", "[vout]",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            str(video_out),
        ]

        print(f"[{session_id}] 🎬 Ejecutando FFmpeg…")
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)

        if proc.returncode != 0:
            print(f"[{session_id}] ❌ FFmpeg stderr:\n{proc.stderr}")
            raise HTTPException(
                status_code=500,
                detail=f"FFmpeg falló. Revisa los logs del servidor."
            )

        print(f"[{session_id}] ✅ Video procesado exitosamente")

        background_tasks.add_task(shutil.rmtree, session_dir, True)

        return FileResponse(
            path=str(video_out),
            media_type="video/mp4",
            filename="short_branded.mp4",
            background=background_tasks,
        )

    except HTTPException:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


# ──────────────────────────────────────────────
# HEALTHCHECK para Railway
# ──────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "whisper": "loaded", "groq_key_set": bool(GROQ_API_KEY)}


# ──────────────────────────────────────────────
# ENTRYPOINT local
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
