# packages/reasoning — модуль AI 2

Владелец: ML/AI Engineer 2. ТЗ: раздел 22, задачи A2-01…A2-12.

## Готово

| Задача | Статус | Что есть |
|---|---|---|
| A2-04 Применимость | ready_for_integration | `fa_reasoning.applicability.assess_applicability`, 25 тестов |
| A2-03, A2-05…A2-08 `reason` | planned | — |
| A2-09 Набор оценки | in_progress | `eval/eval_questions.json`, 30 вопросов, черновик для сверки с AI 1 |
| A2-10, A2-11 Состязательные проверки, регрессия | planned | — |

## Набор оценки (ТЗ 24.2)

`eval/eval_questions.json` — 30 вопросов: 10 `direct`, 5 `comparison`, 5 `no_data`, 5 `lunar_mars`, 5 `adversarial`.
Вопросы q01–q12 взяты из `packages/retrieval/eval_questions.json` (AI 1) без изменений.

Поля AI 1 сохранены, по ним считается Recall@5 в `packages/retrieval/evaluate.py`:
`id`, `question`, `relevant` (нужные исследования), `relevant_claims` (нужные выводы), `lunar`
(`true` — прямых совпадений быть не должно; так помечены лунные, марсианские вопросы и вопросы без данных).

Поля AI 2: `group`, `scenario` (краткая форма: пресет и отличающиеся условия), `data_revision`,
`expected_evidence_ids` (до 3 доказательств каждого вывода из `relevant_claims`), `expected_status`,
`expected_applicability_max`, `required_limitations`, `forbidden_claims`, `adversarial_fixture`, `note`.

Прогон поиска AI 1 на этом наборе (ревизия `psi-20261115-r2`): Recall@5 по исследованиям 0.97,
по доказательствам 0.95, ложных прямых совпадений 2 (q23, q25).

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
