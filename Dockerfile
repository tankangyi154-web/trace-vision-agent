# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS frontend
WORKDIR /src
COPY web/package.json web/package-lock.json ./web/
RUN npm --prefix web ci --no-audit --no-fund
COPY . ./
RUN npm --prefix web run build

FROM python:3.12-slim-bookworm AS api-base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . ./
COPY --from=frontend /src/web/dist ./web/dist
RUN useradd --create-home --uid 10001 trace && mkdir -p work/state work/uploads && chown -R trace:trace work
USER trace
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=3)"
CMD ["python","-m","uvicorn","app:app","--host","0.0.0.0","--port","8000","--workers","1","--no-access-log"]

# Private CPU analysis. The compose profile binds it to host loopback only.
FROM api-base AS cpu
USER root
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 fonts-noto-cjk && rm -rf /var/lib/apt/lists/*
RUN python -m venv work/vision-env && work/vision-env/bin/pip install --no-cache-dir -r vision/requirements-cpu.txt
RUN python vision/download_model.py && work/vision-env/bin/python vision/prepare_cpu.py
RUN chown -R trace:trace work vision/weights
ENV APP_MODE=local TRACE_LOCAL_STATE_DIR=/app/work/state OMP_NUM_THREADS=4 MKL_NUM_THREADS=4
USER trace
ENTRYPOINT ["python","deploy/start_cpu.py"]

# Default build: prepared examples only, no Torch, no uploads, no paid model key.
FROM api-base AS showcase
ENV APP_MODE=production
