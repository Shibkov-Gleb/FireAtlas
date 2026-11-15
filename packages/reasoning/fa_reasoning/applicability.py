"""A2-04. Детерминированная оценка применимости исследований к сценарию миссии.

ТЗ: раздел 22.3 и задача A2-04. Выход - ApplicabilityResult (CT-10, packages/contracts/openapi.yaml).
Генеративная модель не используется: одинаковый вход всегда дает одинаковый выход.

Подключение к бэкенду (D-025):
    FA_APPLICABILITY=py:fa_reasoning.applicability:assess_applicability
    PYTHONPATH должен включать packages/reasoning.

Главные правила:
* Каждое условие (задача, гравитация, материал, геометрия, кислород, давление, поток) проверяется отдельно.
* Материал совпадает по material_id, а не по названию. Совпадение состава не заявляется.
* Числа совпадают, только если разница не больше заявленной неопределенности или точности исходной записи.
  Порог близости не подбирается: при отсутствии совпадения различие показывается явно.
* direct_evidence - только если есть хотя бы один опыт, где все заданные условия выполнены одновременно,
  и нет неизвестных критичных условий. Попадание в независимые диапазоны не доказывает такой опыт.
* Частичная гравитация без опытов этого режима -> not_covered, итог не выше related_evidence.
  Имитация частичной гравитации (simulated_partial) не подменяет partial, и наоборот.
* Для обнаружения дыма нужны измерения дыма; данные о пламени их не заменяют.
"""
from __future__ import annotations

from typing import Any, Iterable

RULES_VERSION = "ai2-applicability-1.0"

KNOWN = frozenset({"measured", "reported", "derived"})
MAX_EVIDENCE_PER_FACTOR = 5
MAX_TEXT = 1000

# Условия, без которых итог direct_evidence не заявляется (A2-04: "без неизвестных критичных условий").
CRITICAL_FIELDS: dict[str, tuple[str, ...]] = {
    "prevention": ("material_ids", "oxygen_fraction", "pressure", "airflow_speed"),
    "suppression": ("material_ids", "oxygen_fraction", "pressure"),
    "detection": ("material_ids", "airflow_speed"),
}

# Поле сценария -> (каноническая единица, подпись, путь в conditions_coverage)
NUMERIC_FIELDS: dict[str, tuple[str, str, str]] = {
    "oxygen_fraction": ("fraction", "доля кислорода", "conditions.oxygen_fraction"),
    "pressure": ("Pa", "давление", "conditions.pressure"),
    "airflow_speed": ("m_s", "скорость потока", "conditions.airflow_speed"),
}

TASK_LABELS = {"prevention": "предотвращение", "detection": "обнаружение", "suppression": "подавление"}
GRAVITY_LABELS = {
    "normal": "земная гравитация",
    "microgravity": "микрогравитация",
    "partial": "частичная гравитация",
    "simulated_partial": "имитация частичной гравитации",
    "unknown": "режим не указан",
}
GEOMETRY_LABELS = {
    "film": "пленка", "sheet": "лист", "slab": "пластина", "rod": "стержень", "sphere": "сфера",
    "droplet": "капля", "fabric": "ткань", "other": "другая", "unknown": "не указана",
}
PARTIAL = frozenset({"partial", "simulated_partial"})


# -----------------------------------------------------------------------------
# Вспомогательные функции
# -----------------------------------------------------------------------------
def _fmt(value: float, unit: str) -> str:
    """Число для пользователя в привычных единицах."""
    if unit == "fraction":
        return f"{value * 100:.4g} %"
    if unit == "Pa":
        return f"{value / 1000:.4g} кПа"
    if unit == "m_s":
        return f"{value * 100:.4g} см/с"
    return f"{value:.4g}"


def _cut(text: str) -> str:
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 1] + "…"


def _is_set(q: dict | None) -> bool:
    return bool(q) and q.get("status") in KNOWN and q.get("value") is not None


def _precision(q: dict) -> float:
    """Половина единицы последнего знака исходной записи, переведенная в каноническую единицу.

    Например, "22.2" % -> 0.05 % -> 0.0005 (доля). Если исходная запись не число или равна 0, точность 0.
    """
    raw, value = q.get("raw_value"), q.get("value")
    if raw is None or value is None:
        return 0.0
    s = str(raw).strip().replace(",", ".")
    if "e" in s.lower():
        return 0.0
    try:
        raw_num = float(s)
    except ValueError:
        return 0.0
    if raw_num == 0:
        return 0.0
    decimals = len(s.split(".", 1)[1]) if "." in s else 0
    return 0.5 * 10 ** (-decimals) * abs(value / raw_num)


def _tolerance(run_q: dict, target: dict) -> float:
    tol = max(run_q.get("uncertainty") or 0.0, target.get("uncertainty") or 0.0,
              _precision(run_q), _precision(target))
    return tol + abs(target["value"]) * 1e-9  # защита от ошибок округления float


def _satisfies(run_q: dict | None, target: dict, unit: str) -> bool | None:
    """True/False - выполнено ли условие сценария в опыте; None - значение в опыте неизвестно."""
    if not run_q or run_q.get("unit") != unit or not _is_set(run_q):
        return None
    if run_q.get("qualifier") not in (None, "eq"):
        return None  # в источнике граница ("< 5"), а не значение: совпадение не проверяется
    rv, t, tol = run_q["value"], target["value"], _tolerance(run_q, target)
    qual = target.get("qualifier")
    if qual == "lt":
        return rv < t
    if qual == "lte":
        return rv <= t + tol
    if qual == "gt":
        return rv > t
    if qual == "gte":
        return rv >= t - tol
    return abs(rv - t) <= tol


def _target_text(target: dict, unit: str) -> str:
    sign = {"lt": "< ", "lte": "≤ ", "gt": "> ", "gte": "≥ "}.get(target.get("qualifier") or "", "")
    return sign + _fmt(target["value"], unit)


class _Evidence:
    """Отбор ссылок: только разрешенные ID, без повторов, не больше лимита на фактор."""

    def __init__(self, evidence: Iterable[dict]):
        self.allowed = {e["id"] for e in evidence if isinstance(e, dict) and e.get("id")}

    def pick(self, ids: Iterable[str], limit: int = MAX_EVIDENCE_PER_FACTOR) -> list[str]:
        out: list[str] = []
        for i in ids:
            if i in self.allowed and i not in out:
                out.append(i)
                if len(out) >= limit:
                    break
        return out


def _quantity_evidence(runs: Iterable[dict], getter) -> list[str]:
    ids: list[str] = []
    for r in runs:
        q = getter(r)
        ids += (q or {}).get("evidence_ids") or r.get("evidence_ids") or []
    return ids


def _factor(field: str, status: str, explanation: str, evidence_ids: list[str]) -> dict:
    return {"field": field, "status": status, "explanation": _cut(explanation), "evidence_ids": evidence_ids}


def _gap(field: str, description: str, next_step: str | None) -> dict:
    return {"field": field, "description": _cut(description), "suggested_next_step": _cut(next_step) if next_step else None}


# -----------------------------------------------------------------------------
# Проверки отдельных условий
# -----------------------------------------------------------------------------
def _check_task(scenario, investigations, runs, ev):
    task = scenario["safety_task"]
    scopes = sorted({s for i in investigations for s in i.get("scopes", [])})
    factors, gaps = [], []
    if not investigations:
        factors.append(_factor("safety_task", "unknown", "Исследования не выбраны.", []))
        return factors, gaps, False
    if task in scopes:
        factors.append(_factor("safety_task", "match",
                               f"Направление исследований совпадает с задачей сценария: {TASK_LABELS[task]}.", []))
        ok = True
    else:
        have = ", ".join(TASK_LABELS.get(s, s) for s in scopes) or "не указано"
        factors.append(_factor("safety_task", "mismatch",
                               f"Задача сценария - {TASK_LABELS[task]}, а исследования относятся к направлению: {have}. "
                               "Их результаты не отвечают на вопрос сценария напрямую.", []))
        gaps.append(_gap("safety_task", f"Нет исследований по направлению «{TASK_LABELS[task]}» среди выбранных.",
                         "Выбрать исследования с нужным направлением."))
        ok = False

    if task == "detection":
        smoke_runs = [r for r in runs
                      if r["terminal_outcome"]["category"] == "smoke_measurement"
                      or any(m["metric_key"] == "particle_diameter" and _is_set(m["quantity"]) for m in r.get("metrics", []))]
        if smoke_runs:
            factors.append(_factor("smoke_measurement", "match",
                                   f"Есть измерения дыма: {len(smoke_runs)} опыт(ов).",
                                   ev.pick(e for r in smoke_runs for e in r["evidence_ids"])))
        else:
            factors.append(_factor("smoke_measurement", "mismatch",
                                   "В выбранных опытах нет измерений дыма. Данные о пламени не заменяют "
                                   "измерения дыма для оценки обнаружения.", []))
            gaps.append(_gap("smoke_measurement", "Нет измерений дыма в выбранных опытах.",
                             "Добавить исследования с измерениями частиц дыма (например, SAME-R)."))
            ok = False
    return factors, gaps, ok


def _check_gravity(scenario, investigations, runs, ev):
    target = scenario["gravity_regime"]
    present = sorted({r["conditions"]["gravity_regime"] for r in runs}
                     or {g for i in investigations for g in i.get("gravity_regimes", [])})
    have = ", ".join(GRAVITY_LABELS.get(g, g) for g in present) or "нет данных"
    if target == "unknown":
        return (_factor("gravity_regime", "unknown", "Режим гравитации сценария не указан.", []),
                _gap("gravity_regime", "Не указан режим гравитации сценария.", "Указать среду миссии."))
    same = [r for r in runs if r["conditions"]["gravity_regime"] == target]
    if same:
        return (_factor("gravity_regime", "match",
                        f"Есть опыты в режиме «{GRAVITY_LABELS[target]}»: {len(same)}.",
                        ev.pick(e for r in same for e in r["evidence_ids"])), None)
    if target in PARTIAL:
        extra = ""
        if "simulated_partial" in present or "partial" in present:
            extra = " Имитация частичной гравитации и частичная гравитация - разные режимы и не подменяют друг друга."
        return (_factor("gravity_regime", "not_covered",
                        f"Целевой режим - {GRAVITY_LABELS[target]}; в выбранных опытах: {have}. "
                        f"Перенос результатов требует обоснования.{extra}", []),
                _gap("gravity_regime", f"Нет прямых опытов в режиме «{GRAVITY_LABELS[target]}».",
                     "Изучить связанные исследования с явной оговоркой; сохранить пробел в отчете."))
    return (_factor("gravity_regime", "mismatch",
                    f"Режим сценария - {GRAVITY_LABELS.get(target, target)}; в выбранных опытах: {have}. "
                    "Перенос результатов между режимами требует обоснования.", []),
            _gap("gravity_regime", f"Нет опытов в режиме «{GRAVITY_LABELS.get(target, target)}».",
                 "Сравнить с результатами в нужном режиме или сохранить пробел в отчете."))


def _check_material(scenario, runs, ev, critical):
    wanted = set(scenario.get("material_ids") or [])
    if not wanted:
        gap = _gap("material_ids", "Материал сценария не выбран; без него прямое основание не заявляется.",
                   "Выбрать материал в сценарии.") if critical else None
        return _factor("material_ids", "unknown", "Материал не выбран.", []), gap
    hit = [r for r in runs if r.get("material_id") in wanted]
    if hit:
        names = ", ".join(sorted({r["material_id"] for r in hit}))
        return (_factor("material_ids", "match",
                        f"Есть опыты с выбранным материалом ({names}): {len(hit)}. Совпадение установлено по "
                        "идентификатору материала; совпадение состава не заявляется.",
                        ev.pick(e for r in hit for e in r["evidence_ids"])), None)
    have = ", ".join(sorted({r["material_id"] for r in runs if r.get("material_id")})[:8]) or "не указаны"
    return (_factor("material_ids", "mismatch",
                    f"Выбранных материалов нет в опытах. В опытах есть: {have}.", []),
            _gap("material_ids", "Нет опытов с выбранным материалом.",
                 "Выбрать близкий материал с явной оговоркой или сохранить пробел в отчете."))


def _check_geometry(scenario, runs, ev):
    target = scenario.get("geometry")
    if target in (None, "unknown"):
        return _factor("geometry", "unknown", "Геометрия образца не задана.", []), None
    hit = [r for r in runs if r["sample"]["geometry"] == target]
    if hit:
        return (_factor("geometry", "match", f"Есть опыты с геометрией «{GEOMETRY_LABELS[target]}»: {len(hit)}.",
                        ev.pick(e for r in hit for e in r["evidence_ids"])), None)
    have = ", ".join(GEOMETRY_LABELS.get(g, g) for g in sorted({r["sample"]["geometry"] for r in runs})) or "нет данных"
    return (_factor("geometry", "mismatch",
                    f"Опытов с геометрией «{GEOMETRY_LABELS[target]}» нет; в опытах: {have}. "
                    "Форма и толщина образца влияют на горение.", []),
            _gap("geometry", f"Нет опытов с геометрией «{GEOMETRY_LABELS[target]}».", None))


def _check_numeric(field, scenario, investigations, runs, ev, critical):
    unit, label, cov_path = NUMERIC_FIELDS[field]
    target = scenario.get(field)
    if not _is_set(target):
        gap = _gap(field, f"В сценарии не задано условие: {label}. Без него прямое основание не заявляется.",
                   f"Указать {label} в сценарии.") if critical else None
        return _factor(field, "unknown", f"Условие сценария не задано: {label}.", []), gap

    getter = (lambda r: r["conditions"].get(field))
    checked = [(r, _satisfies(getter(r), target, unit)) for r in runs]
    known = [(r, ok) for r, ok in checked if ok is not None]
    want = _target_text(target, unit)
    if not known:
        cov_ev = [e for i in investigations for c in i.get("conditions_coverage", [])
                  if c["field"] == cov_path for e in c.get("derivation_evidence_ids", [])]
        return (_factor(field, "unknown",
                        f"В выбранных опытах {label} не сообщается, поэтому совпадение с {want} проверить нельзя.",
                        ev.pick(cov_ev)),
                _gap(field, f"В источниках выбранных исследований не сообщается: {label}.",
                     "Найти исследование, где это условие измерено, или сохранить пробел в отчете."))

    matched = [r for r, ok in known if ok]
    if matched:
        return (_factor(field, "match",
                        f"Есть опыты, где {label} = {want} в пределах точности источника: {len(matched)} из {len(known)} "
                        "с известным значением.",
                        ev.pick(_quantity_evidence(matched, getter))), None)

    values = [getter(r)["value"] for r, _ in known]
    nearest = min((r for r, _ in known), key=lambda r: (abs(getter(r)["value"] - target["value"]), r["id"]))
    return (_factor(field, "mismatch",
                    f"Опытов, где {label} = {want}, нет. Наблюдаемый диапазон: {_fmt(min(values), unit)} - "
                    f"{_fmt(max(values), unit)}; ближайшее значение {_fmt(getter(nearest)['value'], unit)}. "
                    "Перенос результатов требует обоснования.",
                    ev.pick(_quantity_evidence([nearest], getter))),
            _gap(field, f"Нет опытов при условии сценария: {label} = {want}.",
                 "Учитывать различие условий; сохранить пробел в отчете."))


def _joint_runs(scenario, runs) -> tuple[list[dict], int]:
    """Опыты, где все заданные условия сценария выполнены одновременно, и число заданных условий."""
    checks = [lambda r: r["conditions"]["gravity_regime"] == scenario["gravity_regime"]]
    n = 0
    wanted = set(scenario.get("material_ids") or [])
    if wanted:
        n += 1
        checks.append(lambda r: r.get("material_id") in wanted)
    if scenario.get("geometry") not in (None, "unknown"):
        n += 1
        checks.append(lambda r: r["sample"]["geometry"] == scenario["geometry"])
    for field, (unit, _, _) in NUMERIC_FIELDS.items():
        target = scenario.get(field)
        if _is_set(target):
            n += 1
            checks.append(lambda r, f=field, t=target, u=unit: _satisfies(r["conditions"].get(f), t, u) is True)
    return [r for r in runs if all(c(r) for c in checks)], n


def _revision(investigations, runs, evidence, data_revision) -> str:
    for group in (investigations, runs, evidence):
        for item in group:
            if isinstance(item, dict) and item.get("data_revision"):
                return item["data_revision"]
    return data_revision or "unknown"


# -----------------------------------------------------------------------------
# Публичная функция
# -----------------------------------------------------------------------------
def assess_applicability(scenario: dict, investigations: list[dict], runs: list[dict], evidence: list[dict],
                         data_revision: str | None = None) -> dict:
    """Оценить применимость исследований к сценарию. Возвращает ApplicabilityResult (CT-10).

    evidence - разрешенные доказательства: в факторах используются только их ID.
    data_revision - запасной вариант, если ревизию нельзя взять из входных объектов.
    """
    investigations = sorted(investigations or [], key=lambda i: i["id"])
    runs = sorted(runs or [], key=lambda r: r["id"])  # порядок входа не влияет на результат
    ev = _Evidence(evidence or [])
    critical = CRITICAL_FIELDS.get(scenario["safety_task"], ())

    factors: list[dict] = []
    gaps: list[dict] = []

    def add(pair):
        f, g = pair
        factors.append(f)
        if g:
            gaps.append(g)

    task_factors, task_gaps, task_ok = _check_task(scenario, investigations, runs, ev)
    factors += task_factors
    gaps += task_gaps
    add(_check_gravity(scenario, investigations, runs, ev))
    add(_check_material(scenario, runs, ev, "material_ids" in critical))
    add(_check_geometry(scenario, runs, ev))
    for field in NUMERIC_FIELDS:
        add(_check_numeric(field, scenario, investigations, runs, ev, field in critical))

    joint, n_set = _joint_runs(scenario, runs)
    joint_cited = [r for r in joint if ev.pick(r["evidence_ids"], 1)]
    if n_set >= 2:
        if joint_cited:
            factors.append(_factor("joint_conditions", "match",
                                   f"Есть опыты, где все заданные условия сценария выполнены одновременно: {len(joint_cited)}.",
                                   ev.pick(e for r in joint_cited for e in r["evidence_ids"])))
        else:
            factors.append(_factor("joint_conditions", "mismatch",
                                   "Нет опыта, где все заданные условия сценария выполнены одновременно. Совпадение "
                                   "условий по отдельности не доказывает наличие опыта с таким сочетанием.", []))
            gaps.append(_gap("joint_conditions", "Нет опыта с заданным сочетанием условий.",
                             "Ослабить одно из условий или сохранить пробел в отчете."))

    by_field = {f["field"]: f["status"] for f in factors}
    critical_ok = all(by_field.get(f) == "match" for f in critical)
    gravity_ok = by_field.get("gravity_regime") == "match"

    if not investigations or not runs or not task_ok:
        overall = "insufficient_evidence"
    elif gravity_ok and critical_ok and joint_cited:
        overall = "direct_evidence"
    else:
        overall = "related_evidence"

    return {
        "overall": overall,
        "factors": factors,
        "gaps": gaps,
        "basis": {"reviewed_rules_version": RULES_VERSION,
                  "data_revision": _revision(investigations, runs, evidence or [], data_revision)},
    }
