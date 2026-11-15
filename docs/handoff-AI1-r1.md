# BE -> AI 1: интеграция первого пакета данных и retrieve

**Дата:** 15.11.2026. Проверено на архиве `FireAtlas_AI1.zip` (ветка `ai1-data` + отчет BASS-II).

## Итог
Данные хорошие: 508 опытов и 634 доказательства проходят все семантические проверки (ссылки, единицы, исходы,
доказательства у известных значений). Recall@5 = 1.00 по `evaluate.py` воспроизводится. После правок ниже
сквозной путь работает на настоящем API: поиск, ответ со ссылками на строки таблиц NASA, сравнение, скачивание
файлов источников. Проверено на рабочей копии, где эти правки имитированы; исходники AI 1 не менялись.

Проверка без БД: `make validate-release REL=data/releases/<rev>` (профиль p0).

## A. Пакет - блокирует импорт
1. **manifest: `entity_type` в единственном числе**: `investigation`, `material`, `run`, `source`, `evidence`, `claim`.
   Сейчас `investigations`, `materials`, ... (`pipeline/build_release.py:134`).
2. **Время UTC с суффиксом `Z`**: `2026-11-15T12:00:00Z`, а не `+00:00`. Затронуты `manifest.created_at`
   (`build_release.py:139`) и `sources.retrieved_at` (берется из `download_log.json`, `scripts/download_sources.py:117`).
   Например: `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`.
3. **`conditions_coverage.field` - путь поля** (D-037): `conditions.oxygen_fraction`, `conditions.pressure`,
   `conditions.airflow_speed`, `sample.initial_diameter`. С короткими именами сравнение показывало «не сообщено»
   при известных данных. Теперь это ошибка `COVERAGE_FIELD_UNKNOWN`.

## B. Пакет - блокирует профиль p0 (production)
4. **PSI-69 FLEX: нет документа report/publication.** В `data/raw/PSI-69` есть `FLEX_Test_Plan.pdf` и `FLEX DoD.docx`:
   зарегистрировать как источники (`kind=report`, `availability=available`, `sha256`) и добавить в `source_ids`.
5. **PSI-101 SAME-R: `src_ntrs_20130000422` не входит в `source_ids` исследования**, хотя на него ссылаются
   4 доказательства. Добавить в `inv_psi101_samer.source_ids`. `SAMER_Final 0602 2014.pdf` тоже можно зарегистрировать.
6. По желанию: `BASS-II Summary Report.pdf` (49 МБ) и `BASS-II Test Matrix by PI Final.xlsx` пока не источники.

## C. Состав атмосферы (твой пункт 1) - D-036, контракт 1.1.0
7. В `RunConditions` добавлены `nitrogen_fraction`, `co2_fraction`, `helium_fraction` (QuantityFraction).
   Перенеси доли из `table_values` («N/CO/He initial ambient composition; mole fraction») в эти поля:
   `status=reported`, `raw_unit="mole fraction"`, `evidence_ids` = строка опыта. Там, где источник состав
   не дает (BASS-II, SAME-R): `not_reported`, значение null.
8. Добавь в `conditions_coverage` FLEX записи `conditions.co2_fraction` и `conditions.helium_fraction`: по ним
   сравнение покажет строки разбавителей.
9. Старый пакет без полей принимается (`LEGACY_CONDITIONS_FILLED`), но тогда фильтры `co2_range`/`helium_range`
   отсекают все опыты FLEX. На твоих данных сумма O2+N2+CO2+He сходится во всех 271 опыте FLEX (допуск 0.02).

## D. Файлы источников - D-038
10. `local_asset_id` оставь `null`, как сейчас; `sha256` у тебя уже заполнен. Бэкенд раскладывает файлы
    `stage-assets <release> data/raw` и назначает ID при импорте. На твоем архиве найдены все 8 файлов из 8.

## E. retrieve - выход не проходит CT-13 (бэкенд не публикует такой результат)
11. `evidence_bundle.items[].source_metadata` - **полная запись Source** из `sources.jsonl`, все 12 полей
    (`retrieve.py:272`). Сейчас 7 полей.
12. `match_reasons`, `differences` (`retrieve.py:195-225`) и `coverage.reasons` (`retrieve.py:292-301`) -
    **объекты Reason** `{code, text, field, evidence_ids}` (D-011), а не строки. `code` - `^[a-z][a-z0-9_]{1,63}$`,
    `text` - готовая русская подпись, `field` - путь поля или null.
13. `warnings` - **объекты** `{code, message, field}` (`retrieve.py:231`), а не строки.
14. **`normalized_facts[].evidence_ids` только из bundle.** Пример: у BASS-II доля кислорода выведена из
    `ev_psi25_faq_o2`, которого нет в `allowed_evidence_ids`. Либо добавь это доказательство в bundle, либо не
    указывай его в факте.
15. `missing_fields` у ranked items - пути полей (`conditions.airflow_speed`), как в п. 3.
16. `normalized_facts[].field` - тоже путь (`conditions.oxygen_fraction`); сейчас короткое имя.

## F. Пресеты сред - D-033
17. В корпусе нет источника условий трека, поэтому оба пресета («Орбитальная станция», «Лунная база») скрыты
    с `PRESET_SOURCE_MISSING`. Нужен Source для страницы трека Flame in Freefall (сейчас в пресетах
    `src_track_flame_in_freefall`; можно другой ID - скажи BE). Тип - `publication`, пока не решен D-019.

## Как проверить у себя
```bash
make validate-release REL=data/releases/<rev>                  # пакет, профиль p0
python3 -c "import sys; sys.path[:0]=['packages/contracts','packages/retrieval']; \
  import fa_contracts as c, retrieve as r, json; \
  out=r.retrieve(json.load(open('req.json'))); print(c.errors_for('InternalRetrievalResult', out))"
```
Запрос `req.json` должен проходить `InternalRetrievalRequest`: в нем есть `deadline_at`, `selected_investigation_ids`
и все поля `filters`. Бэкенд вызывает `retrieve` и для поиска (`selected_investigation_ids=[]`, `top_k=20`),
и для анализа (выбор пользователя, `top_k=12`).
