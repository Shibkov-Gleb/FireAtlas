# Fire Atlas API. Полный сервис: pnpm start (docker compose).
FROM python:3.13-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY apps/api/requirements.txt apps/api/requirements.txt
RUN pip install --no-cache-dir -r apps/api/requirements.txt

RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-dejavu-extra \
 && rm -rf /var/lib/apt/lists/*

COPY packages/contracts packages/contracts
# Модули AI 1 и AI 2 (D-025); без них анализ в production не стартует
COPY packages/retrieval packages/retrieval
COPY packages/reasoning/fa_reasoning packages/reasoning/fa_reasoning
COPY apps/api apps/api
COPY scripts scripts
COPY tools tools
COPY data/releases data/releases
COPY data/raw data/raw

ENV FA_ENV=production \
    FA_DB_PATH=/var/lib/fire-atlas/fire_atlas.sqlite3 \
    FA_ASSETS_DIR=/var/lib/fire-atlas/assets \
    FA_REPORTS_DIR=/var/lib/fire-atlas/reports \
    FA_BACKUPS_DIR=/var/lib/fire-atlas/backups \
    FA_FONT_DIR=/usr/share/fonts/truetype/dejavu \
    FA_VALIDATE_RESPONSES=false

RUN PYTHONPATH=apps/api:packages/contracts python3 -c "from pathlib import Path; from fire_atlas_api.report_pdf import find_fonts; find_fonts(Path('/usr/share/fonts/truetype/dejavu'))"

RUN useradd --system --uid 10001 fireatlas && mkdir -p /var/lib/fire-atlas && chown fireatlas /var/lib/fire-atlas
USER fireatlas
VOLUME ["/var/lib/fire-atlas"]
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/ready').status==200 else 1)"
CMD ["bash", "scripts/start.sh"]
