"""BE-14: сквозной маршрут демонстрации (ТЗ, раздел 27) против запущенного API с настоящими модулями.

Новый гость -> вопрос о вентиляции -> BASS-II и причина соответствия -> карточка и источник -> график FLEX
и опыт 30CAL03 -> сравнение -> вопрос AI -> лунный сценарий с пробелом данных -> PDF -> пустая выдача.
Каждый ответ проверяется по контракту (packages/contracts/openapi.yaml).

Запуск (сервер уже работает, FA_FEATURE_ANALYSIS=true, модули AI подключены):
    python tools/e2e_demo.py --base http://127.0.0.1:8000 [--origin http://localhost:5173] [--skip-ai]
Код выхода 0 - все шаги прошли. Вызов модели тратит токены (2 анализа).
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "contracts"))
import fa_contracts as c  # noqa: E402

FLEX_CONTROL = {"30CAL03": (1.92, 6.34)}  # приложение А: диаметр, мм; время горения, с


class Api:
    def __init__(self, base: str, origin: str):
        self.base, self.origin = base.rstrip("/"), origin
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method: str, path: str, body=None, headers=None, schema: str | None = None):
        h = {"Accept": "application/json", **(headers or {})}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode()
            h["Content-Type"] = "application/json"
        if method in ("POST", "PATCH", "DELETE"):
            h["Origin"] = self.origin
        req = urllib.request.Request(self.base + path, data=data, headers=h, method=method)
        try:
            with self.opener.open(req, timeout=60) as r:
                status, raw, hdrs = r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            status, raw, hdrs = e.code, e.read(), e.headers
        is_json = (hdrs.get("Content-Type") or "").startswith("application/json")  # без учета регистра
        payload = json.loads(raw) if is_json and raw else raw
        if schema and status < 400:
            viol = c.errors_for(schema, payload)
            if viol:
                raise AssertionError(f"{method} {path}: ответ не по контракту {schema}: {viol[:2]}")
        return status, payload, hdrs


class Run:
    def __init__(self):
        self.steps: list[tuple[str, bool, str, float]] = []

    def step(self, name: str, fn):
        t0 = time.perf_counter()
        try:
            detail = fn() or ""
            ok = True
        except AssertionError as e:
            detail, ok = str(e), False
        except Exception as e:  # noqa: BLE001
            detail, ok = f"{type(e).__name__}: {e}", False
        dt = time.perf_counter() - t0
        self.steps.append((name, ok, detail, dt))
        print(f"{'OK  ' if ok else 'FAIL'} {dt:6.1f} с  {name}" + (f" - {detail}" if detail else ""), flush=True)
        return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--origin", default="http://localhost:5173")
    ap.add_argument("--skip-ai", action="store_true", help="не вызывать анализ (без расхода токенов)")
    args = ap.parse_args()
    api, run, st = Api(args.base + "/api/v1", args.origin), Run(), {}

    def config():
        s, d, _ = api.call("GET", "/config", schema="ConfigEnvelope")
        assert s == 200, s
        st["rev"] = d["meta"]["data_revision"]
        return f"ревизия {st['rev']}, флаги {d['data']['feature_flags']}"

    def guest():
        s, d, _ = api.call("POST", "/workspaces", {}, schema="WorkspaceEnvelope")
        assert s == 201, (s, d)
        st["ws_rev"] = d["data"]["revision"]
        s, d, _ = api.call("GET", "/scenario-presets?data_revision=" + st["rev"], schema="ScenarioPresetListEnvelope")
        assert s == 200, (s, d)
        st["presets"] = {p["preset_id"]: p["scenario"] for p in d["data"]["items"]}
        assert {"orbital_habitat", "moon_base"} <= set(st["presets"]), list(st["presets"])
        return f"пресеты: {', '.join(st['presets'])}"

    def set_scenario(preset):
        s, d, _ = api.call("PATCH", "/workspaces/current", {"scenario": st["presets"][preset]},
                           headers={"If-Match": f'"{st["ws_rev"]}"'}, schema="WorkspaceEnvelope")
        assert s == 200, (s, d)
        st["ws_rev"] = d["data"]["revision"]

    def search():
        set_scenario("orbital_habitat")
        body = {"query": "Как вентиляция влияет на горение твердых материалов?", "locale": "ru", "data_revision": st["rev"],
                "filters": {"scopes": [], "investigation_ids": [], "material_ids": [], "fuel_states": [], "gravity_regimes": [],
                            "oxygen_range": None, "pressure_range": None, "airflow_range": None, "has_measurements": None,
                            "include_unknown": True},
                "scenario": None, "include_related": True, "cursor": None, "limit": 20}
        s, d, _ = api.call("POST", "/search", body, schema="SearchResultEnvelope")
        assert s == 200, (s, d)
        items = d["data"]["items"]
        assert items and items[0]["investigation"]["acronym"] == "BASS-II", [i["investigation"]["acronym"] for i in items]
        top = items[0]
        assert top["match_reasons"], "нет причины соответствия"
        st["bass"] = top["investigation"]
        st["flex_id"] = next(i["investigation"]["id"] for i in items if i["investigation"]["acronym"] == "FLEX")
        return (f"{d['data']['retrieval_mode']}: " + ", ".join(f"{i['investigation']['acronym']}({i['relevance_category']})"
                                                                 for i in items) + f"; причина: {top['match_reasons'][0]['text'][:60]}")

    def card():
        inv = st["bass"]
        s, d, _ = api.call("GET", f"/investigations/{inv['id']}?data_revision={st['rev']}", schema="InvestigationDetailEnvelope")
        assert s == 200, s
        src_ok = src_missing = 0
        for sid in inv["source_ids"]:
            s, src, _ = api.call("GET", f"/sources/{sid}?data_revision={st['rev']}", schema="SourceEnvelope")
            assert s == 200, (sid, s)
            if src["data"]["local_asset_id"]:
                s2, raw, h = api.call("GET", f"/sources/{sid}/asset?data_revision={st['rev']}")
                assert s2 == 200 and raw, (sid, s2)
                src_ok += 1
            else:
                src_missing += 1  # AT-26: метаданные доступны и без файла
        return f"источников {len(inv['source_ids'])}: файл отдан {src_ok}, только метаданные {src_missing}"

    def flex_chart():
        body = {"investigation_id": st["flex_id"], "data_revision": st["rev"], "run_ids": [], "x_metric": "sample.initial_diameter",
                "y_metric": "metrics.burn_duration", "cursor": None, "limit": 1000}
        s, d, _ = api.call("POST", "/measurements/query", body, schema="MeasurementResponseEnvelope")
        assert s == 200, (s, d)
        pts = d["data"]["points"]
        s, runs, _ = api.call("GET", f"/investigations/{st['flex_id']}/runs?data_revision={st['rev']}&limit=200",
                              schema="RunPageEnvelope")
        by_test = {}
        page = runs
        while True:
            by_test.update({r["source_test_id"]: r for r in page["data"]["items"]})
            nxt = page["data"].get("next_cursor")
            if not nxt or "30CAL03" in by_test:
                break
            _, page, _ = api.call("GET", f"/investigations/{st['flex_id']}/runs?data_revision={st['rev']}&limit=200&cursor={nxt}")
        r = by_test.get("30CAL03")
        assert r, "опыт 30CAL03 не найден"
        s, one, _ = api.call("GET", f"/runs/{r['id']}?data_revision={st['rev']}", schema="TestRunEnvelope")
        dia = one["data"]["sample"]["initial_diameter"]["value"] * 1000
        dur = next(m["quantity"]["value"] for m in one["data"]["metrics"] if m["metric_key"] == "burn_duration")
        exp = FLEX_CONTROL["30CAL03"]
        assert abs(dia - exp[0]) < 1e-6 and abs(dur - exp[1]) < 1e-6, (dia, dur)
        point = next((p for p in pts if p["run_id"] == r["id"]), None)
        assert point, "точка 30CAL03 не на графике"
        return f"точек {len(pts)}; 30CAL03: {dia:.2f} мм, {dur} с, исход {one['data']['terminal_outcome']['category']}"

    def compare():
        ids = [st["bass"]["id"], st["flex_id"]]
        s, d, _ = api.call("POST", "/comparisons", {"investigation_ids": ids, "data_revision": st["rev"],
                                                     "scenario": st["presets"]["moon_base"]}, schema="ComparisonResponseEnvelope")
        assert s == 200, (s, d)
        ap = d["data"]["applicability"]
        assert ap["overall"] != "direct_evidence"
        g = next(f for f in ap["factors"] if f["field"] == "gravity_regime")
        assert g["status"] == "not_covered", g
        return (f"сопоставимость {d['data']['comparability']['status']}; применимость к Луне {ap['overall']}, "
                f"правила {ap['basis']['reviewed_rules_version']}")

    def analysis(preset, question, selected):
        set_scenario(preset)
        body = {"question": question, "locale": "ru", "workspace_revision": st["ws_rev"], "data_revision": st["rev"],
                "selected_investigation_ids": selected, "mode": "evidence_answer"}
        key = str(uuid.uuid4())
        s, job, _ = api.call("POST", "/analyses", body, headers={"Idempotency-Key": key}, schema="JobEnvelope")
        assert s == 202, (s, job)
        s2, again, _ = api.call("POST", "/analyses", body, headers={"Idempotency-Key": key})
        assert again["data"]["id"] == job["data"]["id"], "повтор с тем же ключом создал новую задачу (AT-16)"
        jid = job["data"]["id"]
        for _ in range(120):
            _, j, _ = api.call("GET", f"/jobs/{jid}", schema="JobEnvelope")
            if j["data"]["state"] in ("succeeded", "failed", "cancelled", "expired"):
                break
            time.sleep(1)
        assert j["data"]["state"] == "succeeded", j["data"]
        s, a, _ = api.call("GET", f"/answers/{j['data']['result_id']}", schema="AnalysisResultEnvelope")
        return a["data"]

    def ask_ventilation():
        a = analysis("orbital_habitat", "Как вентиляция влияет на горение твердых материалов?", [])
        assert a["status"] == "answered" and a["citations"], a["status"]
        st["answers"] = [a["id"]]
        summary = next(b["text"] for b in a["answer_blocks"] if b["kind"] in ("summary", "observation"))
        return f"{a['status']}, блоков {len(a['answer_blocks'])}, ссылок {len(a['citations'])}: «{summary[:90]}…»"

    def ask_moon():
        a = analysis("moon_base", "Опасность пожара на лунной базе при 30% кислорода", [])
        assert a["status"] == "insufficient_evidence", a["status"]
        assert a["applicability"] and a["applicability"]["overall"] != "direct_evidence"
        assert any("частичной гравитации" in lim for lim in a["limitations"]), a["limitations"]
        assert a["follow_up_questions"]
        st["answers"].append(a["id"])
        return f"{a['status']}, применимость {a['applicability']['overall']}, уточнений {len(a['follow_up_questions'])}"

    def report():
        body = {"workspace_revision": st["ws_rev"], "title": "Вентиляция и горение материалов", "answer_ids": st.get("answers", []),
                "investigation_ids": [st["bass"]["id"], st["flex_id"]], "include_comparison": True, "locale": "ru"}
        s, job, _ = api.call("POST", "/reports", body, headers={"Idempotency-Key": str(uuid.uuid4())}, schema="JobEnvelope")
        assert s == 202, (s, job)
        for _ in range(60):
            _, j, _ = api.call("GET", f"/jobs/{job['data']['id']}")
            if j["data"]["state"] in ("succeeded", "failed", "cancelled", "expired"):
                break
            time.sleep(1)
        assert j["data"]["state"] == "succeeded", j["data"]
        _, rep, _ = api.call("GET", f"/reports/{j['data']['result_id']}", schema="ReportEnvelope")
        s, pdf, h = api.call("GET", rep["data"]["download_path"].removeprefix("/api/v1"))
        assert s == 200 and pdf[:5] == b"%PDF-", s
        out = ROOT / "var" / "e2e_report.pdf"
        out.parent.mkdir(exist_ok=True)
        out.write_bytes(pdf)
        return f"PDF {len(pdf) // 1024} КБ -> {out.relative_to(ROOT)}"

    def empty():
        body = {"query": "", "locale": "ru", "data_revision": st["rev"],
                "filters": {"scopes": [], "investigation_ids": [], "material_ids": [], "fuel_states": [], "gravity_regimes": [],
                            "oxygen_range": {"min": 0.9, "max": 1.0, "unit": "fraction"}, "pressure_range": None,
                            "airflow_range": None, "has_measurements": None, "include_unknown": False},
                "scenario": None, "include_related": False, "cursor": None, "limit": 20}
        s, d, _ = api.call("POST", "/search", body, schema="SearchResultEnvelope")
        assert s == 200 and d["data"]["items"] == [], (s, d)
        return "кислород 90-100 %: 200 и пустая выдача, фильтр не ослаблен (AT-04)"

    run.step("Конфигурация", config)
    run.step("Новый гость и пресеты сред", guest)
    run.step("Поиск: вентиляция и твердые материалы (AT-03)", search)
    run.step("Карточка BASS-II и источники (AT-26)", card)
    run.step("График FLEX и опыт 30CAL03 (AT-07, AT-08)", flex_chart)
    run.step("Сравнение BASS-II и FLEX для Луны (AT-09, AT-12)", compare)
    if not args.skip_ai:
        run.step("Вопрос AI о вентиляции (AT-11, AT-16)", ask_ventilation)
        run.step("Лунный сценарий: пробел данных (AT-12, AT-13)", ask_moon)
    run.step("PDF-отчет", report)
    run.step("Пустая выдача при жестком фильтре", empty)
    failed = [s for s in run.steps if not s[1]]
    print(f"\nИтого: {len(run.steps) - len(failed)} из {len(run.steps)} шагов, {sum(s[3] for s in run.steps):.0f} с")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
