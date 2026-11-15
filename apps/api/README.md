# Fire Atlas

Исследования горения NASA (PSI) - от вопроса пользователя до отчета с источниками.
ТЗ: «Fire Atlas - техническая спецификация», версия 1 от 15.11.2026. Продуктовое видение - 8 экранов.

## Структура (23.1)

| Путь | Владелец | Что внутри |
|---|---|---|
| `packages/contracts` | BE + потребители | `openapi.yaml` (нормативный контракт), `examples/`, `dictionaries.ru.json`, `fa_contracts` (валидаторы), `mock_server.py` |
| `apps/api` | BE | Публичный API, импорт CT-09, хранилище, тесты |
| `apps/web` | FE | Интерфейс |
| `packages/retrieval` | AI 1 | Поиск, bundle, оценка |
| `packages/reasoning` | AI 2 | Ответы, применимость, валидация |
| `data/releases` | AI 1 | Неизменяемые пакеты корпуса |
| `tests/fixtures`, `tests/e2e` | все | Фикстуры и сквозные проверки |
| `docs` | BE координирует | [журнал решений](docs/decisions.md), [статус](docs/status.md), [передача H1](docs/handoff-H1.md), [передача BE-05](docs/handoff-BE05.md), [runbook стенда](docs/runbook.md), [образцы PDF](docs/report-samples) |
| `deploy`, `scripts`, `Dockerfile` | BE | nginx, единый запуск, контейнер |

## Быстрый старт

Нужен Python 3.13 и зависимости из `apps/api/requirements.txt` (версии зафиксированы).

```bash
pip install -r apps/api/requirements.txt
make check          # examples против openapi.yaml + тесты бэкенда
make mock           # мок-сервер для FE на :4010
make dev            # локальный API на :8000 с фикстурным корпусом и заглушками AI
make loadtest       # замер 24.3 против запущенного API
```

В dev анализ работает на заглушках бэкенда: ответы помечены `[ЗАГЛУШКА]`, режим поиска `curated`.
Так FE может пройти весь путь до PDF, не дожидаясь модулей AI. В production заглушки запрещены (D-024).

### Для FE
* Мок: `make mock`, затем `GET http://127.0.0.1:4010/api/v1/config`. Конкретный пример выбирается заголовком `Prefer: example=<case>` или `?__example=<case>`. Список примеров: `GET /__examples`.
* Мок и API проверяют тело запроса одной схемой: неожиданное поле дает 422 уже на моке.
* Типы генерируются из `packages/contracts/openapi.yaml`, например `npx openapi-typescript`.
* Поиск `POST /api/v1/search` работает на настоящем API (D-032): фильтры жесткие, `missing_fields` показывает неизвестные
  значения, `related=true` - только при `include_related`. Пресеты сред: `GET /api/v1/scenario-presets?data_revision=` (D-033).
* Cookie и CSRF: см. D-003. `/api` должен обслуживаться с того же origin (proxy в dev-сервере).

### Подключение модулей AI (D-025)
Бэкенд вызывает `retrieve` и `reason` через `FA_RETRIEVER` / `FA_REASONER`: `py:package.module:function` в том же
процессе или `http(s)://.../internal/v1/...` с `Bearer FA_INTERNAL_TOKEN`. Вход и выход - dict по схемам `Internal*`.
Перед публикацией бэкенд заново проверяет выход (D-027). Подробности в [runbook](docs/runbook.md).

### Для AI 1
* Формат пакета - CT-09; сборщик `fire_atlas_api.importer.write_release` можно использовать.
* `retrieve(request: dict) -> dict` по `InternalRetrievalRequest` -> `InternalRetrievalResult`. Ошибка недоступности - `raise fire_atlas_api.providers.RetrievalUnavailable`.
* Одна функция обслуживает два вызова: анализ (`selected_investigation_ids` = выбор пользователя, `top_k=12`) и поиск
  (`selected_investigation_ids=[]`, `top_k=20`, `filters` = applied_filters). Для поиска важны порядок `ranked_items`
  (бэкенд сортирует по `rank_score`, при равенстве - по порядку модуля), `relevance_category` и `match_reasons`.
  Фильтры бэкенд применяет сам (D-032): исследование, не прошедшее фильтр, не станет прямым совпадением.
* Для текстового запроса в выдачу попадают только исследования из `ranked_items`: нерелевантные не возвращайте.
* Пакет: `conditions_coverage.field` - путь поля (`conditions.oxygen_fraction`), D-037. Доли N2/CO2/He - в
  `conditions.*_fraction` (контракт 1.1.0, D-036). `local_asset_id` оставьте `null`, `sha256` заполните: файлы
  разложит `python3 -m fire_atlas_api.cli stage-assets <release> data/raw` (D-038).
* Что исправить в первом пакете AI 1: [docs/handoff-AI1-r1.md](docs/handoff-AI1-r1.md).
* Проверка без записи в БД: `make validate-release REL=data/releases/<rev>`. Отчет содержит файл, строку и ID для каждой ошибки.
* Схемы внутренних контрактов: `InternalManifest`, `InternalRetrievalRequest/Result`, `InternalEvidenceBundle`.

### Для AI 2
* Схемы: `InternalReasoningRequest/Response`, `AnswerBlock`, `ApplicabilityResult`.
* `reason(request: dict) -> dict`; ошибки - `ProviderError`, `ReasoningTimeout`, `ContractViolation` из `fire_atlas_api.providers`.
* `assess_applicability(scenario, investigations, runs, evidence) -> dict` заменяет консервативную заглушку бэкенда.
* `from fa_contracts import validate; validate("InternalReasoningResponse", obj)` - та же проверка, что выполнит бэкенд.

## Переменные окружения
См. `.env.example`. Ключи провайдеров и секреты в репозиторий не коммитятся.
