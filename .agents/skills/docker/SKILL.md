---
name: docker
description: >-
  Multi-stage Docker packaging, resource budgeting (<350MB RAM), and container watchdogs
  for deploying the Quant System onto Synology NAS hardware and staging environments.
  Use when writing Dockerfiles, modifying docker-compose.yml, or running /docker and /nas-deploy.
---

# 🐳 Docker Packaging & Container Resource Guardian (`/docker`, `/nas-deploy`)

This skill governs Docker container builds, staging deployments, and runtime resource limits for the Quant System.

## 1. Multi-Stage Dockerfile Pattern (Zero-Bloat)

FastAPI Gateway `Dockerfile` pattern to guarantee sub-150MB image size and sub-100MB runtime RAM:

```dockerfile
# Build stage: compile dependencies & wheels
FROM python:3.12-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final runtime stage: minimal footprint
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

## 2. Docker Compose Resource Limits

Prevent any memory leak or high CPU load from impacting the host OS:

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
    stop_grace_period: 15s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

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
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

---

## 3. Mandatory Container Invariants
1. **Standing Memory Budget**: `< 350MB` RAM total across all containers.
2. **Graceful Shutdown**: Always configure `stop_grace_period: 15s` so database connections drain cleanly.
3. **Log Caps**: All services must enforce `max-size: "10m"` and `max-file: "3"`.
4. **Health Check Probes**: All API services must expose `/api/health` and define Docker `HEALTHCHECK`.
