# ============================================================
# FireSuppressor – Dockerfile
# Build: docker build -t firesuppressor:latest .
# Run:   docker run --rm -p 8000:8000 -p 1883:1883 \
#               -e DEMO_MODE=1 firesuppressor:latest
# ============================================================

FROM python:3.10-slim-bookworm AS base

LABEL maintainer="hackathon-team"
LABEL description="Autonomous Fire Detection & Suppression System"

# System dependencies for OpenCV headless
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1-mesa-glx \
    libgstreamer1.0-0 \
    libgstreamer-plugins-base1.0-0 \
    libsm6 libxext6 libxrender-dev \
    curl wget git \
    mosquitto mosquitto-clients \      
    && rm -rf /var/lib/apt/lists/*

# ── Python deps ───────────────────────────────────────────
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Copy source ───────────────────────────────────────────
COPY . .

# ── Download models at build time ─────────────────────────
RUN python models/download_models.py --build-only

# ── Expose ports ──────────────────────────────────────────
# 8000 = FastAPI backend
# 1883 = MQTT broker (Mosquitto)
EXPOSE 8000 1883

# ── Entry point ───────────────────────────────────────────
ENV DEMO_MODE=1
ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py", "--demo"]
