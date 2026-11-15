# Статус задач бэкенда

Обновлено: 15.11.2026 (вечер: интеграция с модулями AI и фронтендом, `docs/handoff-integration.md`).

Состояния (раздел 9): planned, in_progress, ready_for_integration, accepted, blocked.
`ready_for_integration` ≠ `accepted`: задачу принимает потребитель своим запуском (23.3).

| Задача | Состояние | Что есть | Блокер / следующий шаг |
|---|---|---|---|
| BE-01 Контракты и примеры | ready_for_integration | openapi.yaml **1.2.0** (24 операции, 159 схем), 55 examples, `check_examples.py`, мок-сервер. 1.2.0: `dictionaries.materials` (D-040). Валидаторы с подстановкой `$ref` (быстрее в 1,8 раза) | FE: перейти с копии 1.0.0 на этот файл (`docs/handoff-integration.md`, раздел FE) |
| BE-02 Хранилище и импорт | ready_for_integration | Импорт CT-09: хеши, схемы, ссылки, единицы, исходы, дубли, профили dev/p0, атомарная публикация, идемпотентность; состав атмосферы (D-036), пути coverage (D-037). Первый пакет AI 1 проверен 15.11.2026 | Пакет AI 1 не проходит: формат manifest и дат, пути coverage, P0 по документам FLEX и SAME-R (`docs/handoff-AI1-r1.md`) |
| BE-03 Пространства и доступ | ready_for_integration | cookie-сессия, POST/GET/PATCH, ETag/If-Match, 409, дедупликация, проверка ссылок, CSRF | Проверка FE на реальном API |
| BE-04 Чтение каталога | ready_for_integration | config, investigations/{id}, runs (курсор), runs/{id}, evidence, sources, `/scenario-presets` (D-007, D-033) | Подтверждение D-007/D-033; AI 1 - ID источника условий трека |
| BE-05 Поиск | ready_for_integration | `POST /search`: жесткие фильтры бэкенда, ранжирование через `FA_RETRIEVER`, повторная проверка выхода, курсор, сортировка, `include_related`, деградация без AI для поиска по фильтрам, лимит 60/мин (D-032, D-034). В dev - заглушка `curated` с предупреждением | `retrieve` AI 1 проверен 15.11.2026: выход не проходит CT-13 (4 правки формы, `docs/handoff-AI1-r1.md`); с ними поиск, анализ и ссылки работают. Подтверждение D-032 от FE и AI 1 |
| BE-06 Измерения | ready_for_integration | FLEX: оси, исключения по причинам, фильтры, курсор | Подтверждение D-009 |
| BE-07 Сравнение и применимость | ready_for_integration | `POST /comparisons`, `POST /applicability`; подключена `assess_applicability` AI 2 (`ai2-applicability-1.0`), проверено на корпусе `psi-20261115-r2` | Подтверждение FE |
| BE-08 Анализы и задачи | ready_for_integration | Полная цепочка с `retrieve` AI 1 (`lexical-2`) и `reason` AI 2 (`gpt-6-luna`): ответ 13-17 с, лунный сценарий - `insufficient_evidence` с оговоркой (`tools/e2e_demo.py`) | Подтверждение FE |
| BE-09 Отчеты PDF | ready_for_integration | Снимок при POST, PDF с кириллицей, переносом таблиц, ссылками; визуально проверены 3 отчета (`docs/report-samples`) | Проверка FE |
| BE-10 Ошибки и лимиты | ready_for_integration | Envelope, коды, 5 анализов в минуту, 1 активный анализ, 2 активных экспорта, 429 + Retry-After | - |
| BE-11 Доступ к материалам | ready_for_integration | Отдача только зарегистрированного asset со сверкой sha256; путь из запроса не принимается; `stage-assets` и назначение `local_asset_id` при импорте (D-038): 8 из 8 файлов пакета AI 1 найдены по sha256 | - |
| BE-12 Наблюдаемость | ready_for_integration | health, JSON-журнал, `/internal/metrics` за токеном: p50/p95 маршрутов, этапы задач, исходы и коды ошибок | - |
| BE-13 Сборка и стенд | in_progress | `start.sh` читает `.env` и подключает модули AI; Dockerfile копирует `packages/retrieval` и `packages/reasoning`; `.gitattributes` (данные без CRLF, скрипты с LF); PDF со шрифтом с кириллицей на любой ОС; чистый запуск, импорт и маршрут проверены локально на Windows | Docker-сборка не проверена (нет демона); нужен адрес стенда |
| BE-14 Интеграционные проверки | in_progress | 134 теста (Windows: все проходят); `make e2e` - маршрут демонстрации ТЗ 27 против стенда с настоящими модулями: 10/10 шагов; замер 24.3 на полном корпусе (ниже); фронтенд запущен на настоящем API - найдены расхождения | FE: исправления по `docs/handoff-integration.md`; AI 1: кэш загрузки пакета в `retrieve` (поиск p95) |

## Покрытие приемки (часть бэкенда)

| AT | Где проверено |
|---|---|
| AT-01 | `test_import.py::test_at01_clean_import_counts_and_idempotency` |
| AT-03 | часть бэкенда: `test_search.py::test_example_oxygen_021_filters_and_reasons`, `test_run_level_range_match_and_mismatch`, `test_provider_cannot_bypass_hard_filters`; качество ранжирования проверяет AI 1 |
| AT-04 | `test_search.py::test_at04_hard_range_without_matches_is_empty_200` |
| AT-02 | `test_import.py::test_at02_dangling_reference_rejects_whole_release` |
| AT-05 | `test_api.py::test_at05_at06_units_and_missing_values` |
| AT-06 | то же + блокировка доли кислорода вне 0..1 при импорте |
| AT-07 | `test_api.py::test_at07_flex_points_match_appendix_a` (API); на UI проверяет FE |
| AT-10 | 422 на четвертое исследование (`test_patch_validation`) |
| AT-18 | `test_api.py::test_at18_concurrent_patches_exactly_one_wins` |
| AT-19 | `test_api.py::test_at19_sessions_isolated`, `test_jobs.py::test_at19_jobs_and_answers_isolated`, `test_reports.py::test_report_idempotency_and_isolation` |
| AT-26 | `test_api.py::test_evidence_and_sources` |
| AT-09 | `test_reports.py::test_at09_different_methods_partially_compatible` |
| AT-11 | `test_jobs.py::test_at11_success_answer_is_valid_and_bound_to_context` |
| AT-12 | `test_jobs.py::test_at12_moon_scenario_insufficient_and_never_direct`, `test_direct_evidence_for_partial_gravity_rejected` |
| AT-13 | `test_jobs.py::test_at12_...` (insufficient_evidence с пробелом и уточнениями) |
| AT-14 | `test_jobs.py::test_at14_provider_failure_failed_job_with_fallback` |
| AT-15 | часть бэкенда: URL и HTML в ответе модели отклоняются (`test_invalid_reasoning_never_published`); поведение модели проверяет AI 2 |
| AT-16 | `test_jobs.py::test_at16_same_key_same_job`, `test_concurrent_duplicate_posts_create_one_job`, `test_reports.py::test_report_idempotency_and_isolation` |
| AT-17 | `test_jobs.py::test_at17_cancel_then_late_answer_not_published` |
| AT-20 | `test_jobs.py::test_at20_scenario_change_during_analysis_keeps_snapshot` |
| AT-21 | `test_reports.py::test_at21_report_reflects_snapshot_not_later_changes` |
| AT-22 | `test_reports.py::test_at22_expired_report`, `test_api.py` (410 DATA_REVISION_GONE) |
| AT-25 | `test_jobs.py::test_at25_restart_recovers_or_expires_running_jobs` |

## Замер 24.3 (предварительный, 15.11.2026)
`tools/loadtest.py`, 10 сессий, контейнер разработки, фикстурный корпус (28 сущностей), теплый старт, заглушки AI, проверка ответов по контракту включена, `FA_SEARCH_PER_MINUTE=0`:
чтение каталога n=480, p50 49 мс, p95 107 мс; измерения n=120, p95 105 мс; поиск n=120 (каждый раз новый текст, без кэша), p50 156 мс, p95 209 мс; создание задачи n=50, p95 235 мс; ошибок 0.
Это не результат демо-стенда: повторить на стенде с полным корпусом и реальной моделью.

## Замер 24.3 на полном корпусе (15.11.2026, ноутбук Windows, ветка integration)
Корпус `psi-20261115-r2` (508 опытов, 634 доказательства), `retrieve` AI 1 `lexical-2`, `FA_VALIDATE_RESPONSES=false` (как в production), 10 сессий x 12 раундов, теплый старт, без анализа (модель измерена отдельно):

| Операция | n | p95 до | p95 после | Бюджет NFR-03 |
|---|---|---|---|---|
| Чтение каталога | 480 | 1939 мс (3439 с проверкой ответов) | 688 мс | 2 с |
| Поиск | 120 | 4579 мс (5569 с проверкой ответов) | 3627 мс; 2988 мс с кэшем загрузки у AI 1 | 3 с |
| Измерения | 120 | 737 мс | 1089 мс | - |
| Чтение пространства | 120 | 711 мс | 830 мс | - |

«После» - подстановка `$ref` в валидаторах, проверка выхода `retrieve` и разбор корпуса в пуле потоков, кэш корпуса неизменяемой ревизии. Ошибок 0.
Анализ с `gpt-6-luna`: медиана 9,6 с, максимум 19,2 с на 30 вопросах (отчет AI 2 `packages/reasoning/eval/reports`).
Оставшийся резерв поиска - модуль AI 1: `retrieve` на каждый вызов читает пакет с диска и строит индекс (~70 мс + ~100 мс CPU).
