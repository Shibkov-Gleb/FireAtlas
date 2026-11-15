"""POST /search (BE-05) и GET /scenario-presets (D-007).

Покрывает AT-03 (фильтры и причины), AT-04 (жесткий диапазон без совпадений) в части бэкенда.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

from conftest import FIX_REV, example, scenario

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages" / "contracts"))
import fa_contracts as c  # noqa: E402

from fire_atlas_api.api_search import load_presets  # noqa: E402
from fire_atlas_api.providers import RetrievalUnavailable, StubRetriever  # noqa: E402

S = "/api/v1/search"


def req(case: str) -> dict:
    b = copy.deepcopy(example("search", case)["request"]["body"])
    b["data_revision"] = FIX_REV
    return b


def body(query="горение", **kw) -> dict:
    return {"query": query, "locale": "ru", "data_revision": FIX_REV, **kw}


def ids(r) -> list[str]:
    return [i["investigation"]["id"] for i in r.data["items"]]


def assert_contract(r):
    assert r.status == 200, r.raw
    assert not c.errors_for("SearchResultEnvelope", r.json), c.errors_for("SearchResultEnvelope", r.json)[:3]


# --- фильтры (AT-03, AT-04) ----------------------------------------------------
def test_example_oxygen_021_filters_and_reasons(server):
    r = server.client().post(S, req("oxygen_021"))
    assert_contract(r)
    d = r.data
    assert ids(r) == ["inv_psi25"]  # FLEX (жидкое, подавление) и SAME-R (обнаружение) отсечены фильтрами
    assert d["total"] == 1 and d["next_cursor"] is None
    assert d["applied_filters"] == req("oxygen_021")["filters"]
    item = d["items"][0]
    assert item["related"] is False
    codes = {x["code"] for x in item["match_reasons"]}
    assert {"scope", "fuel_state", "gravity_regime"} <= codes
    # у BASS-II нет сообщенной доли кислорода: проходит только благодаря include_unknown=true
    assert "conditions.oxygen_fraction" in item["missing_fields"]
    assert set(item["evidence_ids"]) <= {"ev_psi25_fixture01", "ev_psi25_fixture02"} and item["evidence_ids"]
    # заглушка AI 1 честно помечена
    assert d["retrieval_mode"] == "curated"
    assert [w["code"] for w in r.json["meta"]["warnings"]] == ["RETRIEVAL_STUB"]
    assert r.json["meta"]["data_revision"] == FIX_REV


def test_at04_hard_range_without_matches_is_empty_200(server):
    r = server.client().post(S, req("hard_range_empty"))
    assert_contract(r)
    assert r.data["items"] == [] and r.data["total"] == 0 and r.data["next_cursor"] is None


def test_unknown_values_excluded_without_include_unknown(server):
    b = req("oxygen_021")
    b["filters"]["include_unknown"] = False
    r = server.client().post(S, b)
    assert_contract(r)
    assert r.data["items"] == []


def test_run_level_range_match_and_mismatch(server):
    cl = server.client()
    r = cl.post(S, body(filters={"oxygen_range": {"min": 0.2, "max": 0.22, "unit": "fraction"}}))
    assert_contract(r)
    assert ids(r) == ["inv_psi69"]  # у остальных кислород не сообщен
    flex = r.data["items"][0]
    assert len(flex["matching_run_ids"]) == 5
    reason = next(x for x in flex["match_reasons"] if x["code"] == "oxygen_range")
    assert reason["field"] == "conditions.oxygen_fraction" and reason["evidence_ids"]

    r = cl.post(S, body(filters={"pressure_range": {"min": 30000, "max": 40000, "unit": "Pa"}}, include_related=True))
    assert_contract(r)
    flex = next(i for i in r.data["items"] if i["investigation"]["id"] == "inv_psi69")
    assert flex["related"] is True and flex["relevance_category"] in ("related", "contextual")
    diff = next(x for x in flex["differences"] if x["field"] == "conditions.pressure")
    assert diff["code"] == "filter_mismatch" and "outside the filter range" in diff["text"]
    assert not any(not i["related"] for i in r.data["items"])  # прямых совпадений нет


def test_runs_must_satisfy_all_ranges_jointly(server):
    """Кислород 0.21 есть, давление 101325 Па есть, но не в одном опыте с давлением 101018-101100."""
    r = server.client().post(S, body(filters={"oxygen_range": {"min": 0.2, "max": 0.22, "unit": "fraction"},
                                              "pressure_range": {"min": 101000, "max": 101100, "unit": "Pa"}}))
    assert_contract(r)
    assert ids(r) == ["inv_psi69"]
    assert r.data["items"][0]["matching_run_ids"] == ["run_psi69_20cal08"]


def test_list_filters_and_material_labels(server):
    cl = server.client()
    r = cl.post(S, body(filters={"material_ids": ["mat_methanol"]}))
    assert_contract(r)
    assert ids(r) == ["inv_psi69"]
    assert any(x["text"] == "Material: Methanol" for x in r.data["items"][0]["match_reasons"])
    r = cl.post(S, body(filters={"investigation_ids": ["inv_psi101"]}))
    assert ids(r) == ["inv_psi101"]
    r = cl.post(S, body(filters={"has_measurements": True}))
    assert ids(r) == ["inv_psi69"]
    r = cl.post(S, body(filters={"has_measurements": False}))
    assert set(ids(r)) == {"inv_psi25", "inv_psi101"}


def test_filters_only_query_is_allowed(server):
    r = server.client().post(S, body(query="", filters={"scopes": ["detection"]}))
    assert_contract(r)
    assert ids(r) == ["inv_psi101"]
    assert r.data["items"][0]["relevance_category"] == "contextual"  # категорию дает AI 1; заглушка не ранжирует


# --- проверка запроса ----------------------------------------------------------
@pytest.mark.parametrize("b, field, reason", [
    (body(query=""), "query", "empty_query_without_filters"),
    (body(filters={"oxygen_range": {"min": 0.3, "max": 0.2, "unit": "fraction"}}), "filters.oxygen_range", "min_greater_than_max"),
    (body(filters={"oxygen_range": {"min": 0.1, "max": 21, "unit": "fraction"}}), None, None),  # 21 - проценты, а не доля
    (body(limit=101), "limit", None),
    (body(locale="fr"), "locale", None),
])
def test_search_validation(server, b, field, reason):
    r = server.client().post(S, b)
    assert r.status == 422, r.raw
    assert r.error["code"] == "VALIDATION_ERROR"
    if field:
        assert r.error["details"][0]["field"] == field
    if reason:
        assert r.error["details"][0]["reason"] == reason


def test_unexpected_field_matches_example(server):
    ex = example("search", "unexpected_field")["response"]["body"]["error"]
    r = server.client().post(S, req("unexpected_field"))
    assert r.status == 422
    assert {k: r.error[k] for k in ("code", "message", "details", "retryable")} == ex


def test_unknown_revision_gone(server):
    r = server.client().post(S, {**body(), "data_revision": "psi-19990101-r1"})
    assert r.status == 410 and r.error["code"] == "DATA_REVISION_GONE"
    assert r.error["details"][0]["current_revision"] == FIX_REV


def test_search_needs_no_session_but_csrf_applies(server):
    cl = server.client()
    assert not cl.cookies
    assert cl.post(S, body()).status == 200
    r = cl.post(S, body(), origin="https://evil.example")
    assert r.status == 403 and r.error["code"] == "ACCESS_DENIED"


# --- курсор и сортировка -------------------------------------------------------------
def test_cursor_pages_cover_all_once_and_are_bound(server):
    cl = server.client()
    seen, cursor, pages = [], None, 0
    while True:
        r = cl.post(S, body(query="горение пламени", limit=1, cursor=cursor))
        assert_contract(r)
        assert r.data["total"] == 3
        seen += ids(r)
        cursor = r.data["next_cursor"]
        pages += 1
        if cursor is None:
            break
    assert pages == 3 and sorted(seen) == ["inv_psi101", "inv_psi25", "inv_psi69"]
    first = cl.post(S, body(query="горение пламени", limit=1)).data["next_cursor"]
    r = cl.post(S, body(query="другой запрос", limit=1, cursor=first))
    assert r.status == 422 and r.error["code"] == "INVALID_CURSOR"
    r = cl.post(S, body(query="горение пламени", limit=1, cursor=first[:-3] + "AAA"))
    assert r.status == 422 and r.error["code"] == "INVALID_CURSOR"


def test_sort_by_acronym(server):
    r = server.client().post(S, body(sort="acronym"))
    assert_contract(r)
    assert [i["investigation"]["acronym"] for i in r.data["items"]] == ["BASS-II", "FLEX", "SAME-R"]


# --- провайдер AI 1 ------------------------------------------------------------------
def _ranking(server, ranked):
    stub = StubRetriever(server.db)

    def retrieve(rq):
        out = stub(rq)
        out["mode"] = "lexical"
        out["warnings"] = []
        out["ranked_items"] = ranked
        return out

    return retrieve


def ri(iid, score, cat="direct", **kw):
    return {"investigation_id": iid, "rank_score": score, "relevance_category": cat, "match_reasons": [],
            "differences": [], "missing_fields": [], "matching_run_ids": [], **kw}


def test_provider_order_and_reasons_are_used(server, providers):
    why = {"code": "query_terms", "text": "Совпадение по теме погасания капли", "field": None,
           "evidence_ids": ["ev_psi69_30cal03"]}
    providers["retriever"] = _ranking(server, [ri("inv_psi69", 0.9, match_reasons=[why], matching_run_ids=["run_psi69_30cal03"]),
                                               ri("inv_psi101", 0.4, "contextual")])
    r = server.client().post(S, body(query="погасание капли"))
    assert_contract(r)
    assert ids(r) == ["inv_psi69", "inv_psi101"]  # BASS-II модуль не вернул: на текстовый запрос он не релевантен
    assert r.data["retrieval_mode"] == "lexical" and r.json["meta"]["warnings"] == []
    flex = r.data["items"][0]
    assert flex["match_reasons"] == [why] and flex["matching_run_ids"] == ["run_psi69_30cal03"]
    assert r.data["items"][1]["relevance_category"] == "contextual"


def test_provider_cannot_bypass_hard_filters(server, providers):
    providers["retriever"] = _ranking(server, [ri("inv_psi69", 0.99), ri("inv_psi25", 0.5)])
    cl = server.client()
    flt = {"fuel_states": ["solid"]}
    r = cl.post(S, body(query="пламя", filters=flt))
    assert ids(r) == ["inv_psi25"]  # FLEX - жидкое горючее; «direct» от модуля не помогает
    r = cl.post(S, body(query="пламя", filters=flt, include_related=True))
    assert_contract(r)
    assert ids(r) == ["inv_psi25", "inv_psi69"]
    flex = r.data["items"][1]
    assert flex["related"] is True and flex["relevance_category"] == "related"


@pytest.mark.parametrize("bad", [
    [ri("inv_psi999", 0.5)],                                                   # нет в ревизии
    [ri("inv_psi69", 0.5), ri("inv_psi69", 0.4)],                              # повтор
    [ri("inv_psi25", 0.5, matching_run_ids=["run_psi69_30cal03"])],            # чужой опыт
    [ri("inv_psi69", 0.5, match_reasons=[{"code": "x_y", "text": "t", "field": None, "evidence_ids": ["ev_nope"]}])],
    [{"investigation_id": "inv_psi69", "rank_score": 2}],                      # схема
])
def test_invalid_provider_output_is_not_published(server, providers, bad):
    providers["retriever"] = _ranking(server, bad)
    cl = server.client()
    r = cl.post(S, body(query="пламя"))
    assert r.status == 503 and r.error["code"] == "AI_UNAVAILABLE" and r.error["retryable"] is True
    # Поиск только по фильтрам работает без модуля: подборка бэкенда с предупреждением
    r = cl.post(S, body(query="", filters={"gravity_regimes": ["microgravity"]}))
    assert_contract(r)
    assert r.data["retrieval_mode"] == "curated" and len(r.data["items"]) == 3
    assert [w["code"] for w in r.json["meta"]["warnings"]] == ["RETRIEVAL_UNAVAILABLE"]


def test_provider_unavailable_and_crash(server, providers):
    def down(rq):
        raise RetrievalUnavailable("index offline")

    def crash(rq):
        raise KeyError("bug in module")

    for fn in (down, crash):
        providers["retriever"] = fn
        r = server.client().post(S, body(query=f"дым {fn.__name__}"))
        assert r.status == 503 and r.error["code"] == "AI_UNAVAILABLE"
        assert "index offline" not in r.raw.decode() and "bug" not in r.raw.decode()  # внутренности не утекают


def test_foreign_revision_from_provider_rejected(server, providers):
    stub = StubRetriever(server.db)

    def other_rev(rq):
        out = stub(rq)
        out["data_revision"] = "psi-20200101-r1"
        return out

    providers["retriever"] = other_rev
    assert server.client().post(S, body(query="чужой индекс")).status == 503


def test_retriever_receives_contract_request(server, providers):
    seen = []
    stub = StubRetriever(server.db)

    def spy(rq):
        seen.append(rq)
        return stub(rq)

    providers["retriever"] = spy
    sc = scenario("moon")
    server.client().post(S, body(query="луна", scenario=sc, include_related=True, filters={"scopes": ["prevention"]}))
    assert len(seen) == 1
    rq = seen[0]
    assert not c.errors_for("InternalRetrievalRequest", rq)
    assert rq["scenario"] == sc and rq["include_related"] is True and rq["filters"]["scopes"] == ["prevention"]
    assert rq["filters"]["include_unknown"] is False and rq["data_revision"] == FIX_REV


# --- режим, лимиты ---------------------------------------------------------------------
def test_semantic_flag_warns_when_not_hybrid(make_server):
    with make_server(feature_semantic_search=True) as srv:
        r = srv.client().post(S, body())
        assert_contract(r)
        assert "SEMANTIC_SEARCH_UNAVAILABLE" in [w["code"] for w in r.json["meta"]["warnings"]]


def test_search_rate_limit(make_server):
    with make_server(search_per_minute=2) as srv:
        cl = srv.client()
        assert cl.post(S, body()).status == 200
        assert cl.post(S, body()).status == 200
        r = cl.post(S, body())
        assert r.status == 429 and r.error["code"] == "RATE_LIMITED" and int(r.headers["Retry-After"]) >= 1
        assert not c.errors_for("ErrorResponse", r.json)
        # Квота на клиента: адрес за доверенным прокси берется из X-Forwarded-For (в тестах прокси - 127.0.0.1)
        other = {"X-Forwarded-For": "10.0.0.2"}
        assert cl.post(S, body(), headers=other).status == 200


# --- пресеты (D-007) -------------------------------------------------------------------------
P = "/api/v1/scenario-presets"


def test_presets_match_example_and_can_be_applied(server, guest):
    r = guest.get(f"{P}?data_revision={FIX_REV}")
    assert r.status == 200 and not c.errors_for("ScenarioPresetListEnvelope", r.json)
    assert r.data == example("listScenarioPresets", "ok")["response"]["body"]["data"]
    assert r.json["meta"]["warnings"] == []
    moon = next(p for p in r.data["items"] if p["preset_id"] == "moon_base")["scenario"]
    rev = guest.get("/api/v1/workspaces/current").data["revision"]
    r = guest.patch("/api/v1/workspaces/current", {"scenario": moon}, headers={"If-Match": f'"{rev}"'})
    assert r.status == 200, r.raw  # источники пресета существуют в ревизии - PATCH проходит проверку ссылок


def test_presets_require_revision(server):
    cl = server.client()
    r = cl.get(P)
    assert r.status == 422 and r.error["details"][0]["field"] == "data_revision"
    r = cl.get(f"{P}?data_revision=psi-19990101-r1")
    assert r.status == 410 and r.error["code"] == "DATA_REVISION_GONE"


def test_preset_without_source_in_revision_is_hidden(make_server, tmp_path):
    presets = example("listScenarioPresets", "ok")["response"]["body"]["data"]["items"]
    presets = copy.deepcopy(presets)
    presets[1]["scenario"]["assumptions"][0]["source_ids"] = ["src_not_in_corpus"]
    path = tmp_path / "presets.json"
    path.write_text(json.dumps(presets, ensure_ascii=False), encoding="utf-8")
    with make_server(scenario_presets_path=path) as srv:
        r = srv.client().get(f"{P}?data_revision={FIX_REV}")
        assert r.status == 200
        assert [p["preset_id"] for p in r.data["items"]] == ["orbital_habitat"]
        w = r.json["meta"]["warnings"]
        assert [x["code"] for x in w] == ["PRESET_SOURCE_MISSING"] and w[0]["field"] == "presets.moon_base"


def test_invalid_presets_file_fails_fast(tmp_path):
    good = example("listScenarioPresets", "ok")["response"]["body"]["data"]["items"]
    cases = {
        "schema": [{**good[0], "extra": 1}],
        "dup": [good[0], good[0]],
        "no_origin": [{**good[0], "scenario": {**good[0]["scenario"], "assumptions": []}}],
    }
    for name, data in cases.items():
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(RuntimeError):
            load_presets(p)
