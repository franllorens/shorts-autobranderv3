"""
╔══════════════════════════════════════════════════════╗
║   SHORTS AUTOBRANDER v3  —  FastAPI Backend          ║
║   Whisper word_timestamps · FFmpeg · ASS subtitles   ║
╚══════════════════════════════════════════════════════╝
"""

import os, uuid, shutil, tempfile, subprocess, base64, json, math
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import whisper

# ── Configuración ─────────────────────────────────────────────────
WORK_DIR = Path(tempfile.gettempdir()) / "sab_v3"
WORK_DIR.mkdir(parents=True, exist_ok=True)

TARGET_W, TARGET_H = 1080, 1920   # vertical 9:16

FONT_B = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FONT_R = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"

# Extensiones aceptadas
VIDEO_EXTS = {".mp4",".mov",".webm",".mkv",".m4v",".3gp"}
AUDIO_EXTS = {".mp3",".wav",".m4a",".aac",".ogg"}
IMAGE_EXTS = {".jpg",".jpeg",".png",".webp"}

# Carga Whisper una sola vez al arrancar (tiny = 39MB, cabe en 512MB RAM)
print("⏳ Cargando Whisper 'tiny'…")
WHISPER = whisper.load_model("tiny")
print("✅ Whisper listo")

app = FastAPI(title="Shorts Autobrander v3")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# ── 5 Presets de subtítulos ────────────────────────────────────────
PRESETS = {
    "bold_drop": {
        "name": "Bold Drop",
        "font": "Liberation Sans",
        "size": 26,
        "primary":  "FFFFFF",
        "active":   "FFFF00",
        "outline":  "000000",
        "shadow":   "000000",
        "bold": 1,
        "border": 3,
        "shadow_depth": 2,
        "back_color": "00000080",
        "margin_v": 80,
    },
    "neon_pop": {
        "name": "Neon Pop",
        "font": "Liberation Sans",
        "size": 24,
        "primary":  "00FFCC",
        "active":   "FF00FF",
        "outline":  "000000",
        "shadow":   "00FFCC",
        "bold": 1,
        "border": 2,
        "shadow_depth": 3,
        "back_color": "00000060",
        "margin_v": 80,
    },
    "minimal": {
        "name": "Minimal Clean",
        "font": "Liberation Sans",
        "size": 22,
        "primary":  "FFFFFF",
        "active":   "E8E8E8",
        "outline":  "000000",
        "shadow":   "000000",
        "bold": 0,
        "border": 1,
        "shadow_depth": 1,
        "back_color": "00000090",
        "margin_v": 60,
    },
    "fire": {
        "name": "Fire",
        "font": "Liberation Sans",
        "size": 28,
        "primary":  "FFFFFF",
        "active":   "FF6600",
        "outline":  "990000",
        "shadow":   "FF3300",
        "bold": 1,
        "border": 3,
        "shadow_depth": 4,
        "back_color": "00000000",
        "margin_v": 80,
    },
    "glass": {
        "name": "Glass",
        "font": "Liberation Sans",
        "size": 22,
        "primary":  "FFFFFFCC",
        "active":   "FFFFFFFF",
        "outline":  "FFFFFF40",
        "shadow":   "00000000",
        "bold": 0,
        "border": 1,
        "shadow_depth": 0,
        "back_color": "FFFFFF20",
        "margin_v": 70,
    },
}

# ══════════════════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════════════════

def run(cmd: list, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)

def normalize_to_mp4(src: Path, dst: Path) -> None:
    ext = src.suffix.lower()
    if ext in IMAGE_EXTS:
        run([
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(src),
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", "5",
            "-vf", f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,"
                   f"pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2:black",
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p", "-shortest",
            str(dst),
        ])
    elif ext in AUDIO_EXTS:
        run([
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=black:s={TARGET_W}x{TARGET_H}:r=30",
            "-i", str(src),
            "-vf", "format=yuv420p",
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(dst),
        ])
    else:
        run([
            "ffmpeg", "-y", "-i", str(src),
            "-vf", f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,"
                   f"pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2:black,"
                   f"format=yuv420p",
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
            str(dst),
        ])

def get_duration(path: Path) -> float:
    r = run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ])
    try:
        return float(r.stdout.strip())
    except:
        return 0.0

def secs_to_ass(s: float) -> str:
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = s % 60
    return f"{h}:{m:02d}:{sec:05.2f}"

def hex_to_ass(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    if len(h) == 6:
        r, g, b = h[0:2], h[2:4], h[4:6]
        return f"&H00{b}{g}{r}"
    elif len(h) == 8:
        r, g, b, a = h[0:2], h[2:4], h[4:6], h[6:8]
        alpha_ass = f"{255 - int(a, 16):02X}"
        return f"&H{alpha_ass}{b}{g}{r}"
    return "&H00FFFFFF"

def build_ass(
    words: list,
    preset_id: str,
    position: str,
    overlays: list,
    video_w: int = TARGET_W,
    video_h: int = TARGET_H,
) -> str:
    p = PRESETS.get(preset_id, PRESETS["bold_drop"])

    if position == "top":
        alignment = 8
        margin_v  = p["margin_v"]
    elif position == "center":
        alignment = 5
        margin_v  = 0
    else:
        alignment = 2
        margin_v  = p["margin_v"]

    primary  = hex_to_ass(p["primary"])
    outline  = hex_to_ass(p["outline"])
    shadow_c = hex_to_ass(p["shadow"])
    back_c   = hex_to_ass(p.get("back_color", "00000080"))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_w}
PlayResY: {video_h}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{p['font']},{p['size']},{primary},&H000000FF,{outline},{back_c},{p['bold']},0,0,0,100,100,0,0,1,{p['border']},{p['shadow_depth']},{alignment},30,30,{margin_v},1
"""

    overlay_styles = []
    for ov in overlays:
        ov_id  = ov.get("id", uuid.uuid4().hex[:8])
        font   = ov.get("fontFamily", "Liberation Sans")
        size   = ov.get("fontSize", 24)
        color  = hex_to_ass(ov.get("color", "FFFFFF"))
        bg     = hex_to_ass(ov.get("bgColor", "00000080"))
        bold_v = 1 if ov.get("bold", False) else 0
        style_name = f"OV_{ov_id}"
        overlay_styles.append(
            f"Style: {style_name},{font},{size},{color},&H000000FF,&H00000000,{bg},{bold_v},0,0,0,100,100,0,0,1,1,0,5,0,0,0,1"
        )
        ov["_style"] = style_name

    if overlay_styles:
        header += "\n".join(overlay_styles) + "\n"

    header += "\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"

    events = []

    if words:
        groups = []
        current_group = []
        group_start   = None

        for w in words:
            if group_start is None:
                group_start = w["start"]
            current_group.append(w)
            duration_ok = (w["end"] - group_start) <= 3.0
            count_ok    = len(current_group) < 6

            if not duration_ok or not count_ok:
                groups.append(current_group)
                current_group = [w]
                group_start   = w["start"]

        if current_group:
            groups.append(current_group)

        for group in groups:
            g_start = group[0]["start"]
            g_end   = group[-1]["end"]

            parts = []
            for wi, w in enumerate(group):
                duration_cs = max(1, int((w["end"] - w["start"]) * 100))
                parts.append(f"{{\\kf{duration_cs}}}{w['word'].strip()}")

            text = " ".join(parts)
            active = hex_to_ass(p["active"])
            text = f"{{\\2c{active}}}" + text

            events.append(
                f"Dialogue: 0,{secs_to_ass(g_start)},{secs_to_ass(g_end)},"
                f"Caption,,0,0,0,,{text}"
            )

    for ov in overlays:
        ov_start = float(ov.get("start", 0))
        ov_end   = float(ov.get("end", 5))
        text     = ov.get("text", "").replace("\n", "\\N")
        style    = ov.get("_style", "Caption")

        x_pct = float(ov.get("x_pct", 50))
        y_pct = float(ov.get("y_pct", 50))
        px = int(x_pct / 100 * video_w)
        py = int(y_pct / 100 * video_h)

        anim = ov.get("animation", "fade")
        if anim == "fade":
            fx = "{\\fad(200,200)}"
        elif anim == "pop":
            fx = "{\\t(0,150,\\fscx110\\fscy110)\\t(150,300,\\fscx100\\fscy100)}"
        elif anim == "slide":
            fx = "{\\move(" + str(px) + "," + str(py + 40) + "," + str(px) + "," + str(py) + ",0,300)}"
        else:
            fx = ""

        events.append(
            f"Dialogue: 1,{secs_to_ass(ov_start)},{secs_to_ass(ov_end)},"
            f"{style},,0,0,0,,{{\\pos({px},{py})}}{fx}{text}"
        )

    return header + "\n".join(events) + "\n"

# ══════════════════════════════════════════════════════════════════
# RUTAS
# ══════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    p = Path(__file__).parent / "index.html"
    if not p.exists():
        raise HTTPException(404, "index.html no encontrado")
    return HTMLResponse(content=p.read_text(encoding="utf-8"))

@app.get("/tmp/{session}/{filename}")
async def serve_tmp(session: str, filename: str):
    p = WORK_DIR / session / filename
    if not p.exists():
        raise HTTPException(404, "Archivo no encontrado")
    return FileResponse(str(p), media_type="video/mp4")

@app.get("/tmp_logo/{session}/{filename}")
async def serve_logo(session: str, filename: str):
    p = WORK_DIR / session / filename
    if not p.exists():
        raise HTTPException(404, "Logo no encontrado")
    return FileResponse(str(p))

@app.get("/health")
async def health():
    return {"status": "ok", "whisper": "loaded"}

# ══════════════════════════════════════════════════════════════════
# POST /transcribe
# ══════════════════════════════════════════════════════════════════

@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    audio: UploadFile = File(None),
    logo: UploadFile = File(None),
    logo_b64: str = Form(None),
):
    session = uuid.uuid4().hex
    sdir = WORK_DIR / session
    sdir.mkdir(parents=True)

    try:
        raw_name = file.filename or "input"
        ext = Path(raw_name).suffix.lower() or ".mp4"
        raw_path = sdir / f"raw{ext}"
        raw_path.write_bytes(await file.read())

        if audio and ext in IMAGE_EXTS:
            aud_ext  = Path(audio.filename or "audio.mp3").suffix.lower()
            aud_path = sdir / f"audio{aud_ext}"
            aud_path.write_bytes(await audio.read())
            combined = sdir / "combined.mp4"
            run([
                "ffmpeg", "-y",
                "-loop", "1", "-i", str(raw_path),
                "-i", str(aud_path),
                "-vf", f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,"
                       f"pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2:black",
                "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
                "-shortest", str(combined),
            ])
            raw_path = combined

        norm_path = sdir / "normalized.mp4"
        normalize_to_mp4(raw_path, norm_path)

        result = WHISPER.transcribe(
            str(norm_path),
            word_timestamps=True,
            fp16=False,
        )

        words = []
        for seg in result.get("segments", []):
            for w in seg.get("words", []):
                word_text = w["word"].strip()
                if word_text:
                    words.append({
                        "word":  word_text,
                        "start": round(w["start"], 3),
                        "end":   round(w["end"],   3),
                    })

        duration = get_duration(norm_path)

        logo_url = None
        logo_filename = None
        if logo and logo.filename:
            logo_data = await logo.read()
            lp = sdir / "logo.png"
            logo_ext = Path(logo.filename).suffix.lower()
            raw_logo = sdir / f"logo_raw{logo_ext}"
            raw_logo.write_bytes(logo_data)
            run(["ffmpeg", "-y", "-i", str(raw_logo), str(lp)])
            logo_filename = f"{session}/logo.png"
            logo_url = f"/tmp_logo/{session}/logo.png"
        elif logo_b64:
            if "," in logo_b64:
                logo_b64 = logo_b64.split(",", 1)[1]
            lp = sdir / "logo.png"
            lp.write_bytes(base64.b64decode(logo_b64))
            logo_filename = f"{session}/logo.png"
            logo_url = f"/tmp_logo/{session}/logo.png"

        return JSONResponse({
            "session":   session,
            "video_url": f"/tmp/{session}/normalized.mp4",
            "words":     words,
            "duration":  duration,
            "width":     TARGET_W,
            "height":    TARGET_H,
            "logo_url":  logo_url,
            "logo_path": logo_filename,
        })

    except Exception as e:
        shutil.rmtree(sdir, ignore_errors=True)
        raise HTTPException(500, f"Error en transcripción: {str(e)}")

# ══════════════════════════════════════════════════════════════════
# POST /export
# ══════════════════════════════════════════════════════════════════

@app.post("/export")
async def export_video(
    session:     str = Form(...),
    words:       str = Form("[]"),
    preset_id:   str = Form("bold_drop"),
    position:    str = Form("bottom"),
    logo_path:   str = Form(None),
    logo_scale:  float = Form(0.15),
    logo_x:      float = Form(0.85),
    logo_y:      float = Form(0.05),
    overlays:    str = Form("[]"),
    show_captions: str = Form("true"),
):
    sdir = WORK_DIR / session
    if not sdir.exists():
        raise HTTPException(404, "Sesión no encontrada")

    norm_path = sdir / "normalized.mp4"
    if not norm_path.exists():
        raise HTTPException(404, "Video de sesión no encontrado")

    try:
        words_list    = json.loads(words)
        overlays_list = json.loads(overlays)
        show_caps     = show_captions.lower() == "true"

        ass_path = sdir / "subs.ass"
        ass_content = build_ass(
            words     = words_list if show_caps else [],
            preset_id = preset_id,
            position  = position,
            overlays  = overlays_list,
        )
        ass_path.write_text(ass_content, encoding="utf-8")

        logo_abs = None
        if logo_path:
            candidate = WORK_DIR / logo_path
            if candidate.exists():
                logo_abs = candidate

        output_path = sdir / "output.mp4"

        if logo_abs:
            logo_w_px = int(TARGET_W * logo_scale)
            logo_px = int(logo_x * TARGET_W)
            logo_py = int(logo_y * TARGET_H)
            logo_px_offset = max(0, logo_px - logo_w_px // 2)

            filter_complex = (
                f"[1:v]scale={logo_w_px}:-1,format=rgba,"
                f"colorchannelmixer=aa=0.85[lg];"
                f"[0:v][lg]overlay=x={logo_px_offset}:y={logo_py},"
                f"ass='{str(ass_path)}'[vout]"
            )
            cmd = [
                "ffmpeg", "-y",
                "-i", str(norm_path),
                "-i", str(logo_abs),
                "-filter_complex", filter_complex,
                "-map", "[vout]",
                "-map", "0:a?",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart",
                str(output_path),
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", str(norm_path),
                "-vf", f"ass='{str(ass_path)}'",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart",
                str(output_path),
            ]

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise HTTPException(500, f"FFmpeg falló: {proc.stderr[-800:]}")

        return FileResponse(
            str(output_path),
            media_type="video/mp4",
            filename="short_v3.mp4",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error en export: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
