# ⚡ Shorts Autobrander

> Video corto + Logo → Short viral con subtítulos quemados en ~30 segundos.

## Stack

- **Backend**: Python 3.11 + FastAPI
- **Transcripción**: Whisper `base` (local)
- **IA subtítulos**: Groq API · `llama-3.1-8b-instant`
- **Video**: FFmpeg (logo + subtítulos quemados)
- **Frontend**: HTML + TailwindCSS CDN

-----

## 🚀 Deploy en Railway

### 1. Cloná el repo

```bash
git clone https://github.com/franllorens/JAVA
```

### 2. Nuevo proyecto en Railway

1. [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub Repo**
1. Seleccioná tu repo → Railway detecta el `Dockerfile` automáticamente.

### 3. Variables de entorno

En **Settings → Variables**:

```
GROQ_API_KEY = gsk_tu_key_aqui
```

Obtenés tu key gratis en [console.groq.com](https://console.groq.com).

### 4. Deploy

Railway construye la imagen (≈5 min la primera vez por Whisper + Torch)
y levanta el servicio. Listo.

-----

## 💻 Desarrollo local

```bash
# 1. Dependencias del sistema
brew install ffmpeg   # macOS
# sudo apt install ffmpeg  # Ubuntu

# 2. Entorno Python
python -m venv venv && source venv/bin/activate
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

# 3. Variables
cp .env.example .env
# Editá .env con tu GROQ_API_KEY

# 4. Correr
uvicorn main:app --reload --port 8000
# Abrí http://localhost:8000
```

-----

## 📁 Estructura

```
shorts-autobrander/
├── main.py              # Backend FastAPI
├── index.html           # Frontend (servido por FastAPI)
├── manifest.json        # PWA manifest
├── service-worker.js    # PWA service worker
├── offline.html         # Página offline PWA
├── logo.png             # Logo por defecto (opcional, añadí el tuyo)
├── icons/               # Íconos PWA (añadir manualmente)
├── requirements.txt
├── Dockerfile
├── .env.example
└── README.md
```

-----

## ⚙️ Personalización

|Parámetro           |Dónde                  |Default               |
|--------------------|-----------------------|----------------------|
|Idioma Whisper      |`main.py` → `language=`|`"es"`                |
|Tamaño logo en video|`ffmpeg_cmd` → `scale=`|`150px` ancho         |
|Opacidad logo       |`overlay=...alpha=`    |`0.8`                 |
|Modelo Groq         |`GROQ_MODEL`           |`llama-3.1-8b-instant`|
|Fuente subtítulos   |`subtitles_style`      |`Montserrat`          |
|CRF (calidad video) |`ffmpeg_cmd -crf`      |`23`                  |

-----

## ⚠️ Notas

- **Primera carga**: Whisper descarga el modelo `base` (~75 MB) si no está en caché.  
  Con Docker este paso ocurre en **build time**, no en runtime.
- **Railway free tier**: tiene límite de memoria (512 MB). Whisper `base` + FastAPI caben justo.  
  Si querés más calidad, usá `small` pero aumentá el plan.
- **Logo por defecto**: poné tu `logo.png` junto a `main.py`. Si no existe, FFmpeg genera uno transparente.
- **Íconos PWA**: creá una carpeta `icons/` con los íconos para que funcione la instalación como app.
