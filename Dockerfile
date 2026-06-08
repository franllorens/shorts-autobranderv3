FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg fonts-liberation fonts-dejavu-core curl gcc g++ wget \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

# numpy<2 primero: torch 2.2.2 fue compilado contra numpy 1.x
# Si numpy 2.x se instala antes, torch falla con "Numpy is not available"
RUN pip install --no-cache-dir "numpy<2"

# PyTorch CPU (numpy ya pinneado a 1.x, no se puede actualizar a 2.x)
RUN pip install --no-cache-dir \
    torch==2.2.2 torchvision==0.17.2 torchaudio==2.2.2 \
    --index-url https://download.pytorch.org/whl/cpu

# Whisper + dependencias de la app
RUN pip install --no-cache-dir setuptools wheel && \
    pip install --no-cache-dir --no-build-isolation openai-whisper==20231117 && \
    pip install --no-cache-dir -r requirements.txt

# Pre-descargar modelo Whisper base en build time
RUN python -c "import whisper; whisper.load_model('base'); print('Whisper OK')"

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
