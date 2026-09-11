---
name: synology-nas-guardian
description: >-
  Resource budgeting, multi-stage Docker packaging, and automated container
  watchdogs for deploying the Quant System onto resource-constrained Synology NAS hardware.
  Use when configuring docker-compose, tuning container memory limits, or running /nas-deploy.
---

# 🐳 Synology NAS Deployment & Resource Guardian (`/nas-deploy`)

The Quant System runs inside Docker containers on a Synology NAS with strict memory and CPU constraints:
- **Standing RAM Budget**: `< 350 MB` total standing memory footprint.
- **Zero Idle CPU**: No continuous polling loops; reactive webhooks and scheduled cron triggers.

---

## 1. Multi-Stage Dockerfile Pattern (Zero-Bloat)

FastAPI Gateway `Dockerfile` pattern to guarantee sub-150MB image size and sub-100MB runtime RAM:

```dockerfile
# Build stage: install wheels
FROM python:3.12-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final runtime stage
FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . /app
ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-keep-alive", "30"]
```

---

## 2. Docker Compose Resource Limits Configuration

Prevent any rogue pipeline or memory leak from locking the Synology NAS OS:

```yaml
version: '3.8'

services:
  quant-gateway:
    image: quant-gateway:latest
    container_name: quant-gateway
    restart: unless-stopped
    ports:
      - "8091:8000"
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 350M
        reservations:
          memory: 120M
    environment:
      - APP_ENV=production
      - LOG_LEVEL=INFO

  quant-pwa:
    image: nginx:alpine
    container_name: quant-pwa
    restart: unless-stopped
    ports:
      - "8096:80"
    deploy:
      resources:
        limits:
          cpus: '0.25'
          memory: 50M
```

---

## 3. Deployment Safety Rules
1. **Never kill standing DB connections abruptly**: Always allow 15s graceful shutdown timeout (`stop_grace_period: 15s`).
2. **Log rotation**: Always configure `json-file` log driver with `max-size: "10m"` and `max-file: "3"` to prevent filling NAS storage volumes.
