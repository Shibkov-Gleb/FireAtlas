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
    "oxygen_fraction": ("fraction", "oxygen fraction", "conditions.oxygen_fraction"),
    "pressure": ("Pa", "pressure", "conditions.pressure"),
    "airflow_speed": ("m_s", "airflow speed", "conditions.airflow_speed"),
}

TASK_LABELS = {"prevention": "prevention", "detection": "detection", "suppression": "suppression"}
GRAVITY_LABELS = {
    "normal": "earth gravity",
    "microgravity": "microgravity",
    "partial": "partial gravity",
    "simulated_partial": "simulated partial gravity",
    "unknown": "regime not specified",
}
GEOMETRY_LABELS = {
    "film": "film", "sheet": "sheet", "slab": "slab", "rod": "rod", "sphere": "sphere",
    "droplet": "droplet", "fabric": "fabric", "other": "other", "unknown": "not specified",
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
        return f"{value / 1000:.4g} kPa"
    if unit == "m_s":
        return f"{value * 100:.4g} cm/s"
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
        factors.append(_factor("safety_task", "unknown", "No investigations selected.", []))
        return factors, gaps, False
    if task in scopes:
        factors.append(_factor("safety_task", "match",
                               f"The research area matches the scenario task: {TASK_LABELS[task]}.", []))
        ok = True
    else:
        have = ", ".join(TASK_LABELS.get(s, s) for s in scopes) or "not specified"
        factors.append(_factor("safety_task", "mismatch",
                               f"Scenario task: {TASK_LABELS[task]}; research areas: {have}. "
                               "Their results do not directly answer the scenario question.", []))
        gaps.append(_gap("safety_task", f"No investigations in the area “{TASK_LABELS[task]}” among the selected studies.",
                         "Select investigations in the required research area."))
        ok = False

    if task == "detection":
        smoke_runs = [r for r in runs
                      if r["terminal_outcome"]["category"] == "smoke_measurement"
                      or any(m["metric_key"] == "particle_diameter" and _is_set(m["quantity"]) for m in r.get("metrics", []))]
        if smoke_runs:
            factors.append(_factor("smoke_measurement", "match",
                                   f"Smoke measurements are available: {len(smoke_runs)} test run(s).",
                                   ev.pick(e for r in smoke_runs for e in r["evidence_ids"])))
        else:
            factors.append(_factor("smoke_measurement", "mismatch",
                                   "The selected test runs contain no smoke measurements. Flame data cannot replace "
                                   "smoke measurements when assessing detection.", []))
            gaps.append(_gap("smoke_measurement", "The selected test runs contain no smoke measurements.",
                             "Add investigations with smoke particle measurements (such as SAME-R)."))
            ok = False
    return factors, gaps, ok


def _check_gravity(scenario, investigations, runs, ev):
    target = scenario["gravity_regime"]
    present = sorted({r["conditions"]["gravity_regime"] for r in runs}
                     or {g for i in investigations for g in i.get("gravity_regimes", [])})
    have = ", ".join(GRAVITY_LABELS.get(g, g) for g in present) or "no data"
    if target == "unknown":
        return (_factor("gravity_regime", "unknown", "The scenario gravity regime is not specified.", []),
                _gap("gravity_regime", "The scenario gravity regime is not specified.", "Specify the mission environment."))
    same = [r for r in runs if r["conditions"]["gravity_regime"] == target]
    if same:
        return (_factor("gravity_regime", "match",
                        f"Test runs are available in the regime “{GRAVITY_LABELS[target]}»: {len(same)}.",
                        ev.pick(e for r in same for e in r["evidence_ids"])), None)
    if target in PARTIAL:
        extra = ""
        if "simulated_partial" in present or "partial" in present:
            extra = " Simulated partial gravity and partial gravity are different regimes and are not interchangeable."
        return (_factor("gravity_regime", "not_covered",
                        f"Target regime: {GRAVITY_LABELS[target]}; selected test runs: {have}. "
                        f"Transferring findings requires justification.{extra}", []),
                _gap("gravity_regime", f"No direct test runs in the regime “{GRAVITY_LABELS[target]}».",
                     "Explore related studies with an explicit caveat; keep the evidence gap in the report."))
    return (_factor("gravity_regime", "mismatch",
                    f"Scenario regime: {GRAVITY_LABELS.get(target, target)}; selected test runs: {have}. "
                    "Transferring findings between regimes requires justification.", []),
            _gap("gravity_regime", f"No test runs in the regime “{GRAVITY_LABELS.get(target, target)}».",
                 "Compare with results in the target regime or keep the gap in the report."))


def _check_material(scenario, runs, ev, critical):
    wanted = set(scenario.get("material_ids") or [])
    if not wanted:
        gap = _gap("material_ids", "No scenario material is selected; direct applicability is not claimed without it.",
                   "Select a material in the scenario.") if critical else None
        return _factor("material_ids", "unknown", "No material selected.", []), gap
    hit = [r for r in runs if r.get("material_id") in wanted]
    if hit:
        names = ", ".join(sorted({r["material_id"] for r in hit}))
        return (_factor("material_ids", "match",
                        f"Test runs with the selected material are available ({names}): {len(hit)}. Совпадение установлено по "
                        "material identifier; matching composition is not claimed.",
                        ev.pick(e for r in hit for e in r["evidence_ids"])), None)
    have = ", ".join(sorted({r["material_id"] for r in runs if r.get("material_id")})[:8]) or "not specified"
    return (_factor("material_ids", "mismatch",
                    f"The selected materials are not present in the test runs. Available materials: {have}.", []),
            _gap("material_ids", "There are no test runs with the selected material.",
                 "Select a related material with an explicit caveat or keep the gap in the report."))


def _check_geometry(scenario, runs, ev):
    target = scenario.get("geometry")
    if target in (None, "unknown"):
        return _factor("geometry", "unknown", "Sample geometry is not specified.", []), None
    hit = [r for r in runs if r["sample"]["geometry"] == target]
    if hit:
        return (_factor("geometry", "match", f"Test runs with geometry “{GEOMETRY_LABELS[target]}»: {len(hit)}.",
                        ev.pick(e for r in hit for e in r["evidence_ids"])), None)
    have = ", ".join(GEOMETRY_LABELS.get(g, g) for g in sorted({r["sample"]["geometry"] for r in runs})) or "no data"
    return (_factor("geometry", "mismatch",
                    f"Test runs with geometry “{GEOMETRY_LABELS[target]}” are unavailable; test run geometries: {have}. "
                    "Sample shape and thickness affect combustion.", []),
            _gap("geometry", f"No test runs with geometry “{GEOMETRY_LABELS[target]}».", None))


def _check_numeric(field, scenario, investigations, runs, ev, critical):
    unit, label, cov_path = NUMERIC_FIELDS[field]
    target = scenario.get(field)
    if not _is_set(target):
        gap = _gap(field, f"Scenario condition not specified: {label}. Direct applicability is not claimed without it.",
                   f"Specify {label} in the scenario.") if critical else None
        return _factor(field, "unknown", f"Scenario condition not specified: {label}.", []), gap

    getter = (lambda r: r["conditions"].get(field))
    checked = [(r, _satisfies(getter(r), target, unit)) for r in runs]
    known = [(r, ok) for r, ok in checked if ok is not None]
    want = _target_text(target, unit)
    if not known:
        cov_ev = [e for i in investigations for c in i.get("conditions_coverage", [])
                  if c["field"] == cov_path for e in c.get("derivation_evidence_ids", [])]
        return (_factor(field, "unknown",
                        f"In the selected test runs, {label} is not reported, so a match with {want} cannot be verified.",
                        ev.pick(cov_ev)),
                _gap(field, f"Not reported in the sources of the selected investigations: {label}.",
                     "Find an investigation measuring this condition or keep the gap in the report."))

    matched = [r for r, ok in known if ok]
    if matched:
        return (_factor(field, "match",
                        f"Test runs are available where {label} = {want} within source precision: {len(matched)} of {len(known)} "
                        "with a known value.",
                        ev.pick(_quantity_evidence(matched, getter))), None)

    values = [getter(r)["value"] for r, _ in known]
    nearest = min((r for r, _ in known), key=lambda r: (abs(getter(r)["value"] - target["value"]), r["id"]))
    return (_factor(field, "mismatch",
                    f"Test runs where {label} = {want}are unavailable. Observed range: {_fmt(min(values), unit)} - "
                    f"{_fmt(max(values), unit)}; nearest value {_fmt(getter(nearest)['value'], unit)}. "
                    "Transferring findings requires justification.",
                    ev.pick(_quantity_evidence([nearest], getter))),
            _gap(field, f"No test runs at the scenario condition: {label} = {want}.",
                 "Account for different conditions; keep the gap in the report."))


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
                                   f"Test runs meeting all specified scenario conditions simultaneously: {len(joint_cited)}.",
                                   ev.pick(e for r in joint_cited for e in r["evidence_ids"])))
        else:
            factors.append(_factor("joint_conditions", "mismatch",
                                   "No test run meets all specified scenario conditions simultaneously. Matching "
                                   "conditions separately does not prove that a test with their combination exists.", []))
            gaps.append(_gap("joint_conditions", "There is no test run with the specified combination of conditions.",
                             "Relax one condition or keep the gap in the report."))

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
