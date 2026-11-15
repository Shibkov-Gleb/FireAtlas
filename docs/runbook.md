# Runbook стенда Fire Atlas (BE-13)

Обновлено: 15.11.2026.

## Запуск
```bash
cp .env.example .env          # заполнить FA_CURSOR_SECRET, FA_INTERNAL_TOKEN, FA_ALLOWED_ORIGINS, OPENAI_API_KEY
bash scripts/start.sh          # читает .env; переменные, заданные снаружи, важнее
```
`PYTHONPATH` в `start.sh` и `Makefile` включает `packages/retrieval` и `packages/reasoning`.
Windows без make и bash: `PYTHONPATH=apps/api;packages/contracts;packages/retrieval;packages/reasoning`, затем
`python -m fire_atlas_api.cli migrate`, `... import data/releases/<rev>`, `... serve --port 8000`.
`start.sh` выполняет миграции, затем импорт выпуска, затем запускает сервер. Повторный импорт того же пакета ничего не меняет.
Если пакет отклонен, активной остается предыдущая ревизия, а сервер все равно стартует.
Docker: `docker compose up -d --build` (сборка в среде разработки не проверялась).

Публично доступны только фронтенд и `/api` (`deploy/nginx.conf`). Пути `/internal/*` и `/health/*` наружу не проксируются.

## Проверка после запуска
| Проверка | Ожидание |
|---|---|
| `curl :8000/health/live` | 200 |
| `curl :8000/health/ready` | 200, `active_revision` = нужная ревизия |
| `curl :8000/api/v1/config` | `feature_flags` соответствуют реально включенному |
| `curl -H "Authorization: Bearer $FA_INTERNAL_TOKEN" :8000/internal/metrics` | JSON метрик |
| `python3 tools/loadtest.py --sessions 10` | 0 ошибок; p95 в бюджетах NFR-03 |

## Выпуск новой ревизии корпуса
1. AI 1 кладет пакет в `data/releases/<rev>`.
2. `make validate-release REL=data/releases/<rev>`: `accepted: true`, 0 ошибок в профиле p0.
3. `python3 -m fire_atlas_api.cli backup`.
4. `python3 -m fire_atlas_api.cli import data/releases/<rev>`. Импорт атомарный, новая ревизия становится активной.
5. Старые ответы и отчеты сохраняют свою ревизию. Новые гостевые пространства получают новую.

## Бэкап и восстановление
```bash
python3 -m fire_atlas_api.cli backup                      # онлайн, сервер можно не останавливать
# восстановление: остановить сервер
python3 -m fire_atlas_api.cli restore var/backups/fire_atlas-<stamp>.sqlite3
bash scripts/start.sh
```
`restore` проверяет `integrity_check`, наличие активной ревизии и sha256 по manifest копии. Прежние файлы БД
сохраняются с суффиксом `.before-restore`. Файлы источников (`FA_ASSETS_DIR`) входят в пакет выпуска AI 1 и
восстанавливаются из `data/releases`. PDF-отчеты живут 24 часа и в бэкап не входят.

## Подключение модулей AI (D-025)
| Переменная | Значение |
|---|---|
| `FA_RETRIEVER` | `py:retrieve:retrieve` (AI 1, `packages/retrieval`; читает `data/releases/<rev>`) |
| `FA_REASONER` | `py:fa_reasoning.reason:reason` (AI 2, `packages/reasoning`) |
| `FA_APPLICABILITY` | `py:fa_reasoning.applicability:assess_applicability` (только в процессе) |
| `FA_LLM_PROVIDER`, `FA_LLM_MODEL`, `OPENAI_API_KEY` | модель AI 2: `openai` + `gpt-6-luna`; `offline` - ответ из проверенных выводов без модели (запасной режим демонстрации) |
| `FA_FEATURE_ANALYSIS` | `true` только при подключенных настоящих модулях; в production заглушки запрещены |
| `FA_SEARCH_DEADLINE_S` | дедлайн `retrieve` для `POST /search` (10 с) |
| `FA_SEARCH_PER_MINUTE` | лимит поиска на адрес клиента (60); для `make loadtest` - `0` |
| `FA_FORWARDED_ALLOW_IPS` | от кого принимать `X-Forwarded-For`; в compose `*`, т.к. API видит только nginx |
| `FA_RAW_DIR` | исходные файлы NASA (`data/raw` AI 1): `start.sh` раскладывает их в `FA_ASSETS_DIR` по sha256 перед импортом (D-038) |
| `FA_SCENARIO_PRESETS` | свой JSON пресетов (D-033); ошибка в файле -> сервер не стартует |

`POST /search` без `FA_RETRIEVER` работает на заглушке (`retrieval_mode=curated`, предупреждение `RETRIEVAL_STUB`):
порядок не ранжируется, жесткие фильтры работают полностью.

## Типовые инциденты
| Признак | Действие |
|---|---|
| Задачи падают `MODEL_PROVIDER_ERROR` | Каталог и источники продолжают работать. Проверить провайдера AI 2; при длительном отказе `FA_FEATURE_ANALYSIS=false` и перезапуск. |
| `VALIDATION_FAILED` растет | `/internal/metrics` -> `job_outcomes`; в журнале событие `job_failed` с причиной; передать AI 2. |
| Процесс упал во время анализа | После старта задачи с живым дедлайном выполняются заново, просроченные переходят в `expired`. Ручных правок БД не требуется. |
| Поиск отвечает 503 `AI_UNAVAILABLE` | Модуль AI 1 недоступен или вернул невалидный выход: в журнале `search_retrieval_failed` с кодом. Поиск только по фильтрам (пустой текст) продолжает работать. |
| Много 429 на поиске у разных пользователей | Проверить, что адрес клиента не адрес nginx: `FA_FORWARDED_ALLOW_IPS` и `X-Forwarded-For $remote_addr` в `deploy/nginx.conf`. |
| `health/ready` = 503 | Нет активной ревизии или хранилище недоступно. Импортировать пакет или восстановить бэкап. |
