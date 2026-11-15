# Интеграция BE + AI 1 + AI 2 + FE (15.11.2026)

Выполнено за Backend Engineer (по просьбе Юли) участником AI 2. Ветки:

* `be-fixes` - изменения бэкенда поверх `backend` (только файлы бэкенда, контрактов и документация BE).
* `integration` - `be-fixes` + `ai2-reasoning` + `ai1-data`: полный репозиторий без фронтенда, на нем проверен сквозной маршрут.

## Что проверено

| Проверка | Результат |
|---|---|
| Пакет AI 1 `psi-20261115-r2`, `validate --profile p0` | accepted, 0 ошибок, 0 предупреждений |
| Чистый стенд: migrate, stage-assets, import, serve | работает; 1 источник без файла (49 МБ отчет BASS-II не в репозитории) - метаданные доступны (AT-26) |
| Тесты бэкенда (Windows) | 134/134 (было 126/133: шрифт PDF и кодировка) |
| Тесты AI 2 | 121/121 |
| `make e2e` - маршрут ТЗ 27 с настоящими модулями и `gpt-6-luna` | 10/10 шагов, 39 с: поиск BASS-II, карточка и источники, FLEX 30CAL03 = приложение А, сравнение для Луны (`related_evidence`), ответ AI 17 с, лунный сценарий `insufficient_evidence`, PDF, пустая выдача |
| PDF на Windows | шрифт Arial, все символы отчета есть в шрифте, кириллица извлекается |
| Замер 24.3 на полном корпусе | `docs/status.md`: каталог p95 0,69 с (бюджет 2 с), поиск 3,6 с (бюджет 3 с; 2,99 с с кэшем у AI 1) |
| Фронтенд `codex/fire-atlas-frontend` на настоящем API (`pnpm dev:api`) | главный экран работает после D-039/D-040; поиск падает - список ниже |

## Как воспроизвести

```bash
cp .env.example .env              # OPENAI_API_KEY, FA_CURSOR_SECRET, FA_ALLOWED_ORIGINS
make validate-release REL=data/releases/psi-20261115-r2
FA_FEATURE_ANALYSIS=true FA_FEATURE_REPORTS=true bash scripts/start.sh
make e2e                          # без расхода токенов: make e2e E2E_ARGS=--skip-ai
```

## Изменения бэкенда (`be-fixes`)

1. PDF ищет шрифт с кириллицей в `FA_FONT_DIR` и системных каталогах (DejaVu, Liberation, Arial); тесты читают вывод подпроцессов как UTF-8.
2. Подключение модулей AI (D-042): Makefile, start.sh (+ чтение `.env`), Dockerfile, `.env.example`, runbook.
3. `.gitattributes` (D-041).
4. `tools/e2e_demo.py`, `make e2e`.
5. Производительность (D-043).
6. Сценарий нового гостя (D-039) и `dictionaries.materials`, контракт 1.2.0 (D-040).

## FE: что нужно исправить для работы с настоящим API

Проверено двумя способами: запуск фронтенда на стенде и `tsc` с типами из `packages/contracts/openapi.yaml` 1.2.0
(вместо копии 1.0.0 во фронтенде): 60 ошибок вне моков и тестов. Главное:

| Где | Что отличается | Последствие | Исправление |
|---|---|---|---|
| `pages/Catalog.tsx:207-214`, `pages/Compare.tsx:162-163` | `match_reasons`, `differences`, `comparability.reasons` - объекты `Reason {code, text, field, evidence_ids}` (D-011) | экран исследований пустой: React не рендерит объект (проверено в браузере) | выводить `reason.text`, ключ - `code + field` |
| `components/Shell.tsx`, `pages/Catalog.tsx`, `pages/Missions.tsx`, `components/RunPanel.tsx` | словари `scope`, `fuel_state`, `gravity_regime` (не `scopes`, `fuel_states`, `gravity_regimes`); `materials` - `{value, label}` (не `id`) | падение `Cannot read properties of undefined (reading 'find')` | переименовать ключи; `m.id` -> `m.value` |
| `pages/Measurements.tsx:254` | `exclusions` - объект счетчиков `{missing_x: n, ...}`, не массив | падение на графике | `Object.entries(exclusions)` |
| `pages/catalogParams.ts:102` | сортировка `relevance` или `acronym` (D-008), не `title` | 422 при сортировке по названию | `title` -> `acronym` |
| `Shell`, `Missions`, `Ask`, `AnswerView`, `Reports`, `Compare` | `workspace.scenario` и `answer.scenario_snapshot` могут быть null (D-016; после D-039 только если пользователь сбросил сценарий) | падение на чтении `scenario.name` | проверки на null |
| `components/AnswerView.tsx:224`, `pages/Compare.tsx:172` | `applicability` = null для ответа без сценария (D-028) | падение `ApplicabilityView` | не рендерить блок при null |
| `pages/Catalog.tsx:295` | `retrieval_mode`: `hybrid`, `lexical`, `curated` (нет `semantic`) | подпись режима не показывается | `semantic` -> `hybrid` |
| `components/ApplicabilityView.tsx` | новые поля факторов AI 2: `safety_task`, `smoke_measurement`, `joint_conditions` | показываются английские имена | подписи «Задача», «Измерения дыма», «Сочетание условий» |
| `api/types.ts`, `api/client.ts`, `lib/scenarios.ts` | имена схем: `ErrorResponse`/`ErrorObject`, `RunPage`, `AppliedFilters`, `GravityRegime` | только типы | `pnpm contracts:generate` из контракта BE и переименование |

Рекомендация: заменить `packages/contracts/openapi.yaml` во фронтенде файлом бэкенда (единственный источник правды, D-001),
перегенерировать `schema.d.ts`, исправить ошибки `tsc` и пройти `pnpm dev:api` против стенда.

## AI 1: кэш загрузки пакета в `retrieve`

`packages/retrieval/retrieve.py` на каждый вызов читает весь пакет с диска (`load`, ~70 мс) и строит индекс (`index`, ~100 мс CPU).
Ревизия неизменяема (CT-01), поэтому `load` и `index` можно кэшировать по пути пакета. Эксперимент с кэшем (вне репозитория):
p95 поиска при 10 сессиях 3,6 -> 2,99 с - укладывается в бюджет NFR-03. Кэш должен отдавать данные только для чтения.

## Не сделано

* Docker-сборка: нет docker-демона на машине.
* Публичный стенд и его адрес: нужен сервер.
* Интерфейсные AT-23 и AT-24 (клавиатура, узкое окно, перезагрузка) на настоящем API - после исправлений FE.
* Решения D-039…D-043 нужно подтвердить владельцу (BE) и потребителям.
