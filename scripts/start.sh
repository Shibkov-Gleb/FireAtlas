#!/usr/bin/env bash
# Единый запуск API (BE-13): миграции -> импорт выпуска (идемпотентно) -> сервер.
#   FA_RELEASE_DIR=data/releases/<rev>  - пакет AI 1 для импорта при старте (необязательно)
#   FA_RAW_DIR=<каталог исходных файлов NASA> - разложить файлы источников (D-038, необязательно)
#   FA_PORT=8000
set -euo pipefail
cd "$(dirname "$0")/.."
# Локальный запуск: переменные из .env, если они не заданы снаружи (в Docker .env передает compose).
if [[ -f .env ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^[[:space:]]*([A-Z_][A-Z0-9_]*)=(.*)$ ]] || continue
    key="${BASH_REMATCH[1]}"; val="${BASH_REMATCH[2]%%[[:space:]]#*}"; val="${val%"${val##*[![:space:]]}"}"
    [[ -n "${!key:-}" || -z "$val" ]] && continue
    export "$key=$val"
  done < .env
fi
export PYTHONPATH="apps/api:packages/contracts:packages/retrieval:packages/reasoning${PYTHONPATH:+:$PYTHONPATH}"
PY="${PYTHON:-python3}"

"$PY" -m fire_atlas_api.cli migrate
if [[ -n "${FA_RELEASE_DIR:-}" && -n "${FA_RAW_DIR:-}" ]]; then
  # D-038: файлы источников из исходников AI 1 (поиск по sha256) -> FA_ASSETS_DIR
  "$PY" -m fire_atlas_api.cli stage-assets "$FA_RELEASE_DIR" "$FA_RAW_DIR" >/dev/null || echo "stage-assets failed" >&2
fi
if [[ -n "${FA_RELEASE_DIR:-}" ]]; then
  # Повтор того же manifest идемпотентен; при ошибке активной остается предыдущая ревизия.
  "$PY" -m fire_atlas_api.cli import "$FA_RELEASE_DIR" || echo "import rejected; previous active revision kept" >&2
fi
exec "$PY" -m fire_atlas_api.cli serve --host "${FA_HOST:-0.0.0.0}" --port "${FA_PORT:-8000}"
