# packages/reasoning — модуль AI 2

Владелец: ML/AI Engineer 2. ТЗ: раздел 22, задачи A2-01…A2-12.

## Готово

| Задача | Статус | Что есть |
|---|---|---|
| A2-04 Применимость | ready_for_integration | `fa_reasoning.applicability.assess_applicability`, 25 тестов |
| A2-03, A2-05…A2-08 `reason` | planned | — |
| A2-09…A2-11 Оценка | planned | — |

## Подключение к бэкенду (D-025)

```bash
FA_APPLICABILITY=py:fa_reasoning.applicability:assess_applicability
```

В `PYTHONPATH` нужно добавить `packages/reasoning` (в `Makefile` сейчас только `apps/api:packages/contracts`).

Сигнатура совпадает с заглушкой бэкенда:
`assess_applicability(scenario, investigations, runs, evidence, data_revision=None) -> ApplicabilityResult`.

## Проверка

```bash
PYTHONPATH=packages/reasoning:packages/contracts python -m pytest -q packages/reasoning/tests
```

Тесты бэкенда (`apps/api/tests`) с этой функцией вместо заглушки проходят так же, как с заглушкой.

## Правила применимости (ТЗ 22.3)

Функция детерминированная: модель не используется, одинаковый вход дает одинаковый выход.

* Каждое условие проверяется отдельно: задача, гравитация, материал, геометрия, кислород, давление, поток.
* Материал совпадает только по `material_id`. Совпадение состава не заявляется.
* Число совпадает, если разница не больше неопределенности или точности исходной записи
  (`"22.2"` % → ±0.05 %). Других допусков нет: различие показывается с диапазоном и ближайшим значением.
* `direct_evidence` — только если есть опыт, где **все** заданные условия выполнены одновременно,
  у него есть разрешенное доказательство и все критичные условия задачи совпали.
* Критичные условия: предотвращение — материал, кислород, давление, поток; подавление — материал, кислород,
  давление; обнаружение — материал, поток и наличие измерений дыма.
* Частичная гравитация без опытов этого режима → `not_covered`, итог не выше `related_evidence`.
  `simulated_partial` и `partial` не подменяют друг друга.
* Задача сценария не совпадает с направлением исследований → `insufficient_evidence`.
* В `evidence_ids` факторов попадают только ID из переданного `evidence` (разрешенный bundle).

## Поля факторов

Помимо `gravity_regime`, `material_ids`, `geometry`, `oxygen_fraction`, `pressure`, `airflow_speed`
функция возвращает:

| field | Подпись для FE | Когда |
|---|---|---|
| `safety_task` | Задача | всегда |
| `smoke_measurement` | Измерения дыма | задача «обнаружение» |
| `joint_conditions` | Сочетание условий | задано 2 и больше условий |
