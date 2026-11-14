# Fire Atlas API (BE-13). Сборка: docker build -t fire-atlas-api .
# Внимание: файл не собирался в среде разработки (нет docker-демона); проверить на стенде.
FROM python:3.13-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY apps/api/requirements.txt apps/api/requirements.txt
RUN pip install --no-cache-dir -r apps/api/requirements.txt

COPY packages/contracts packages/contracts
COPY apps/api apps/api
COPY scripts scripts
COPY data/releases data/releases

ENV FA_ENV=production \
    FA_DB_PATH=/var/lib/fire-atlas/fire_atlas.sqlite3 \
    FA_ASSETS_DIR=/var/lib/fire-atlas/assets \
    FA_REPORTS_DIR=/var/lib/fire-atlas/reports \
    FA_BACKUPS_DIR=/var/lib/fire-atlas/backups \
    FA_FONT_DIR=/usr/share/fonts/truetype/dejavu \
    FA_VALIDATE_RESPONSES=false

RUN useradd --system --uid 10001 fireatlas && mkdir -p /var/lib/fire-atlas && chown fireatlas /var/lib/fire-atlas
USER fireatlas
VOLUME ["/var/lib/fire-atlas"]
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live').status==200 else 1)"
CMD ["bash", "scripts/start.sh"]
