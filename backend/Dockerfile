FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Bake the ONNX model into the image so the worker doesn't have to download
# it at startup and the API doesn't fall back to mock predictions.
#
# We can't COPY from ../models/ — the docker-compose build context is
# ./backend, so the host's models/ isn't visible here. We also can't rely on
# the source tree having the weights, since models/*.onnx is gitignored and
# Railway/CI builds clone fresh. Instead, fetch from GitHub Releases at
# build time. Override MODEL_RELEASE_TAG to pin a different version:
#   docker build --build-arg MODEL_RELEASE_TAG=v1.4.0 ...
ARG MODEL_RELEASE_TAG=v1.3.0
RUN mkdir -p /models && \
    curl -fsSL "https://github.com/G1ilbert/DermScan/releases/download/${MODEL_RELEASE_TAG}/dermscan.onnx" \
         -o /models/dermscan.onnx && \
    curl -fsSL "https://github.com/G1ilbert/DermScan/releases/download/${MODEL_RELEASE_TAG}/dermscan.onnx.data" \
         -o /models/dermscan.onnx.data && \
    ls -la /models

EXPOSE 8000

# Railway injects $PORT at runtime; fall back to 8000 for local docker-compose.
# Shell form is required for ${PORT:-8000} expansion; `exec` keeps uvicorn as
# PID 1 so SIGTERM from the platform reaches it directly for graceful shutdown.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
