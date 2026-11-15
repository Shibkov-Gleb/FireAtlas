PY ?= python3
# Модули AI 1 (packages/retrieval) и AI 2 (packages/reasoning) подключаются через FA_RETRIEVER/FA_REASONER (D-025)
export PYTHONPATH := apps/api:packages/contracts:packages/retrieval:packages/reasoning

.PHONY: check examples test mock fixture-release dev validate-release start backup loadtest

## Полная проверка: примеры против контракта + тесты бэкенда
check: examples test

## Перегенерировать и проверить contracts/examples (CT-16)
examples:
	$(PY) -I packages/contracts/tools/build_examples.py
	$(PY) -I packages/contracts/tools/check_examples.py

test:
	cd apps/api && $(PY) -m pytest -q -p no:cacheprovider tests

## Мок-сервер для FE: http://127.0.0.1:4010/api/v1/...
mock:
	$(PY) packages/contracts/mock_server.py --port 4010

## Фикстурный пакет CT-09 (не научный корпус)
fixture-release:
	$(PY) tools/make_fixture_release.py tests/fixtures/data_release_fixture var/assets

## Локальный стенд на фикстурах: http://127.0.0.1:8000
dev: fixture-release
	$(PY) -m fire_atlas_api.cli import tests/fixtures/data_release_fixture --profile dev
	FA_ENV=dev FA_FEATURE_ANALYSIS=true $(PY) -m fire_atlas_api.cli serve --port 8000

## Проверка пакета AI 1 без записи в БД: make validate-release REL=data/releases/<rev>
validate-release:
	$(PY) -m fire_atlas_api.cli validate $(REL) --profile p0

## Запуск стенда: миграции -> импорт FA_RELEASE_DIR -> сервер (BE-13)
start:
	bash scripts/start.sh

backup:
	$(PY) -m fire_atlas_api.cli backup

## Замер 24.3 против запущенного сервера (сервер с FA_SEARCH_PER_MINUTE=0, см. tools/loadtest.py)
loadtest:
	$(PY) tools/loadtest.py --base http://127.0.0.1:8000 --sessions 10 --rounds 12 --analysis
