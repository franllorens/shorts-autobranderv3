# ⚡ Shorts Autobrander v3

> Editor completo de shorts: transcripción word-by-word, 5 presets de subtítulos, capas de texto arrastrables, logo con sliders, exportación 1080×1920.

## Stack

- **Backend**: Python 3.11 + FastAPI
- **Transcripción**: Whisper `base` (local) con `word_timestamps`
- **Subtítulos**: ASS con karaoke highlight por palabra
- **Video**: FFmpeg — normaliza cualquier formato a 9:16 vertical
- **Frontend**: HTML + Sora/JetBrains Mono + TailwindCSS CDN

## Novedades vs v1

| Feature | v1 | v3 |
|---|---|---|
| Subtítulos | SRT básico | ASS karaoke (highlight por palabra) |
| Presets | ❌ | 5 (Bold Drop, Neon Pop, Minimal, Fire, Glass) |
| Editor UI | ❌ | ✅ con timeline |
| Capas manuales | ❌ | ✅ arrastrables + animaciones |
| Entrada | Solo MP4 | Video / Imagen / Audio |
| Groq API | ✅ (requerida) | ❌ (100% local) |

## Deploy en Railway

1. [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub Repo**
2. Seleccioná este repo → Railway detecta el `Dockerfile` automáticamente
3. **No hay variables de entorno requeridas** — todo es local
4. Build time ~5 min (Whisper + Torch se descargan en build)

## Desarrollo local

```bash
brew install ffmpeg   # macOS / sudo apt install ffmpeg  # Ubuntu

python -m venv venv && source venv/bin/activate
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

uvicorn main:app --reload --port 8000
# Abrí http://localhost:8000
```

## Estructura

```
.
├── main.py          # Backend FastAPI (transcribe + export)
├── index.html       # Frontend editor completo
├── requirements.txt
├── Dockerfile
├── .env.example     # Sin API keys requeridas
└── README.md
```
