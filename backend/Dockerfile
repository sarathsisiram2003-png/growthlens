# GrowthLens API. Build context is the backend/ folder.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# Dependencies first so code changes don't reinstall them
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Results, caches and the job database live here; mount a persistent volume at /data in production
ENV DATA_DIR=/data
RUN mkdir -p /data
EXPOSE 8000

# PORT is set by Render/Railway; --proxy-headers so client IPs survive the platform's load balancer
CMD ["sh", "-c", "uvicorn growthlens.api:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
