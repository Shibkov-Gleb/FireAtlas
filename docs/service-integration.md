# Готовый сервис Fire Atlas

Проверка интеграции от 15 ноября 2026 года. Фронтенд, API, AI 1 и AI 2 объединены; нормативная схема — OpenAPI 1.2.0. Исторические протоколы отдельных модулей описывают состояние до этого объединения.

## Ветки

Исходные `backend`, `ai1-data`, `ai2-reasoning` уже входили в `integration`. В неё добавлена история фронтенда. `codex/fire-atlas-frontend` переименована в `fire-atlas-frontend`: сначала опубликована новая ссылка на тот же коммит, затем удалена старая. Итоговая интеграция переносится в `main` обычным merge без переписывания истории. Ветки участников сохранены.

## Состав и режимы

- Веб-интерфейс: восемь экранов, React/TypeScript, cookie-пространство на сервере, optimistic concurrency через `If-Match`.
- API: Starlette/Python 3.13, SQLite, фоновые задачи, идемпотентность, восстановление, серверная генерация PDF по снимку.
- Корпус `psi-20261115-r2`: 3 исследования, 13 материалов, 508 опытов, 634 доказательства, 12 выводов и 17 источников. Пакет проверяется по SHA256, импорт использует профиль P0.
- Поиск: настоящий лексический модуль AI 1. Индекс неизменяемой ревизии кешируется; выдаваемые объекты копируются, чтобы запросы не меняли общий кеш.
- Ответы: модуль AI 2 проверяет ссылки, числа, область вывода и применимость. Лунная миссия сохраняет отсутствие прямых данных частичной гравитации.
- По умолчанию локальный стенд использует `FA_LLM_PROVIDER=offline`: ответ из подтверждённых выводов, с явной пометкой об отсутствии генеративной модели. Это настоящий серверный маршрут, работающий без ключа. Для генерации нужно настроить провайдера в `.env`.
- `pnpm dev` остаётся отдельной демонстрацией на MSW; `pnpm start` собирает production-интерфейс без моков.

## Запуск и эксплуатация

1. Установить Docker Desktop с Linux Engine, Node.js 22.19+ и pnpm 10.28.2.
2. Из корня выполнить `pnpm start`. Команда создаёт локальный `.env` со случайным секретом, собирает два образа, мигрирует SQLite, раскладывает источники, импортирует реальный пакет и ожидает готовность API и веб-сервера.
3. Открыть <http://127.0.0.1:8080>. UI и `/api/v1` обслуживаются с одного origin. Снаружи опубликован только локальный порт 8080; API, `/internal` и `/health` не выставляются наружу.
4. `pnpm status`, `pnpm logs`, `pnpm stop` — состояние, журналы и остановка. Остановка сохраняет Docker volume с пространствами, задачами, источниками и PDF. Повторный запуск идемпотентен.

Ручной эквивалент: `pnpm setup:env`, затем `docker compose up --build -d --wait`. При смене `FA_WEB_PORT` в `.env` добавить соответствующий адрес в `FA_ALLOWED_ORIGINS`. Публичное размещение требует своего домена, HTTPS и secure cookie; шаблон `deploy/nginx.conf` предназначен для такого стенда, автоматический запуск использует локальный `deploy/nginx.local.conf`.

Для OpenAI в `.env` задать `FA_LLM_PROVIDER=openai`, `FA_LLM_MODEL` и `OPENAI_API_KEY`; для Gemini — `FA_LLM_PROVIDER=gemini`, модель и `GEMINI_API_KEY`. После изменения выполнить `pnpm start`. Ключи остаются на сервере; `.env` исключён из Git и Docker build context. У провайдера должен быть доступ к выбранной модели. Ошибка провайдера публикуется как ошибка задачи, без выдуманного ответа.

## Локальная разработка

`pnpm install --frozen-lockfile`, затем `pnpm dev` для UI-демо. Для UI с запущенным Docker API выполнить `pnpm dev:api`, предварительно задать `API_PROXY_TARGET=http://127.0.0.1:8080` в `apps/web/.env.local` и добавить `http://127.0.0.1:5173` в `FA_ALLOWED_ORIGINS` сервера. Контракт генерируется командой `pnpm contracts:generate`.

Без Docker API запускается через Python 3.13: создать `.venv`, установить `apps/api/requirements.txt`, настроить `.env` по примеру и выполнить `bash scripts/start.sh` (Linux/macOS или Git Bash). Для Windows без Bash доступны те же последовательные CLI-команды `migrate`, `stage-assets`, `import`, `serve`; `PYTHONPATH` включает `apps/api`, `packages/contracts`, `packages/retrieval`, `packages/reasoning`, разделитель — `;`.

## Проверки

```sh
pnpm install --frozen-lockfile
pnpm typecheck
pnpm test
pnpm build
pnpm build:check
pnpm test:e2e
pnpm test:live
pnpm test:restart
pnpm format:check
```

На Windows используется Edge; на Linux/macOS предварительно `pnpm exec playwright install chromium`. `test:e2e` запускает отдельное UI-демо, `test:live` использует уже поднятый сервис на 8080. Альтернативный адрес — переменная `E2E_BASE_URL`.

Python-проверки запускаются отдельно, чтобы одноимённые `conftest.py` разных модулей не перекрывали друг друга:

```sh
python packages/contracts/tools/check_examples.py
python -m pytest -q apps/api/tests
python -m pytest -q packages/reasoning/tests
python -m pytest -q packages/retrieval/test_cache.py
python packages/retrieval/evaluate.py
python tools/e2e_demo.py --base http://127.0.0.1:8080 --origin http://127.0.0.1:8080
```

Перед Python-проверками установить зависимости и `PYTHONPATH`, как описано выше. Аналог backend-проверки в Linux: `docker compose exec -T api python3 -m pytest -q -p no:cacheprovider apps/api/tests`.

Проверены: примеры API, типы, production-сборка без MSW, фильтры и пустая выдача, конфликты ревизий, idempotency/retry, отмена и дедлайн, недоступный источник, истёкший отчёт, сохранение контекста ответов, реальный PDF. UI проверяется клавиатурой и axe на 360, 768, 1280, 1920 px; общий горизонтальный скролл отсутствует. Подробные результаты — в `service-acceptance.md`.

## Границы

Ключ модели и публичный хостинг не входят в репозиторий. Генеративный online-режим на этой машине не проверен: ключей нет. Корпус остаётся ограниченным исследованиями NASA PSI; выводы не являются сертификацией пожарной безопасности. Для большого отчёта BASS-II (49 МБ) в Git сохранены SHA256 и метаданные, сам файл не закоммичен. Его отсутствие обрабатывается как недоступное вложение с сохранением ссылки на NASA; остальные исходные файлы включены в образ.
