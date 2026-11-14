"""Замер 24.3: N одновременных гостевых сессий, p50/p95 и доля ошибок по типам операций.

    python3 tools/loadtest.py --base http://127.0.0.1:8000 --sessions 10 --rounds 12 [--analysis]

Бюджеты NFR-03 (демо-стенд, 10 сессий): чтение каталога p95 <= 2 с, поиск <= 3 с, создание задачи <= 1 с.
Скрипт печатает конфигурацию замера; результат публикуется вместе с описанием стенда, а не как обещание.
Все сессии идут с одного адреса, поэтому сервер для замера запускают с FA_SEARCH_PER_MINUTE=0
(иначе сработает лимит поиска на адрес, и 429 будут посчитаны как ошибки).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import statistics
import time
import urllib.error
import urllib.request
import uuid
from collections import defaultdict


class Session:
    def __init__(self, base: str, origin: str):
        self.base, self.origin, self.cookie = base, origin, None

    def call(self, method, path, body=None, headers=None):
        h = {"Accept": "application/json", **(headers or {})}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        if method != "GET":
            h["Origin"] = self.origin
        if self.cookie:
            h["Cookie"] = self.cookie
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(urllib.request.Request(self.base + path, data=data, method=method, headers=h), timeout=30) as r:
                status, raw, sc = r.status, r.read(), r.headers.get("Set-Cookie")
        except urllib.error.HTTPError as e:
            status, raw, sc = e.code, e.read(), None
        ms = (time.perf_counter() - t0) * 1000
        if sc:
            self.cookie = sc.split(";", 1)[0]
        return status, (json.loads(raw) if raw and raw[:1] == b"{" else None), ms


def pct(v, p):
    s = sorted(v)
    return s[max(0, min(len(s) - 1, round(p / 100 * (len(s) - 1))))] if s else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--origin", default="http://localhost:5173")
    ap.add_argument("--sessions", type=int, default=10)
    ap.add_argument("--rounds", type=int, default=12, help="итераций на сессию; 10 x 12 = 120 операций каждого типа")
    ap.add_argument("--analysis", action="store_true", help="также замерить POST /analyses (не больше 5 на сессию из-за лимита)")
    a = ap.parse_args()

    boot = Session(a.base, a.origin)
    _, cfg, _ = boot.call("GET", "/api/v1/config")
    rev = cfg["data"]["active_data_revision"]
    axes = cfg["data"]["measurement_axes"]
    inv = (axes[0]["investigation_ids"] or [None])[0] if axes else None
    _, runs, _ = boot.call("GET", f"/api/v1/investigations/{inv}/runs?data_revision={rev}&limit=5")
    run_id = runs["data"]["items"][0]["id"]
    ev_id = runs["data"]["items"][0]["evidence_ids"][0]

    samples: dict[str, list[float]] = defaultdict(list)
    errors: dict[str, int] = defaultdict(int)

    def record(kind, status, ms, ok=(200,)):
        samples[kind].append(ms)
        if status not in ok:
            errors[kind] += 1

    def user(n):
        s = Session(a.base, a.origin)
        st, ws, ms = s.call("POST", "/api/v1/workspaces", {})
        record("create_workspace", st, ms, (201,))
        for i in range(a.rounds):
            for kind, path in (("catalog_read", f"/api/v1/investigations/{inv}?data_revision={rev}"),
                               ("catalog_read", f"/api/v1/investigations/{inv}/runs?data_revision={rev}&limit=50"),
                               ("catalog_read", f"/api/v1/runs/{run_id}?data_revision={rev}"),
                               ("catalog_read", f"/api/v1/evidence/{ev_id}?data_revision={rev}")):
                st, _, ms = s.call("GET", path)
                record(kind, st, ms)
            st, _, ms = s.call("POST", "/api/v1/measurements/query", {"investigation_id": inv, "data_revision": rev,
                                                                    "x_metric": axes[0]["x_key"], "y_metric": axes[0]["y_key"]})
            record("measurements", st, ms)
            st, _, ms = s.call("GET", "/api/v1/workspaces/current")
            record("workspace_read", st, ms)
            # уникальный текст - каждый раз настоящий вызов retrieve, без кэша выдачи
            st, _, ms = s.call("POST", "/api/v1/search", {"query": f"горение в потоке воздуха {n}-{i}", "locale": "ru",
                                                         "data_revision": rev, "filters": {"gravity_regimes": ["microgravity"]}})
            record("search", st, ms)
            if a.analysis and i < 5:
                st, wsd, _ = s.call("GET", "/api/v1/workspaces/current")
                body = {"question": "Что измерено в этом исследовании?", "locale": "ru", "workspace_revision": wsd["data"]["revision"],
                        "data_revision": rev, "selected_investigation_ids": [inv], "mode": "evidence_answer"}
                st, job, ms = s.call("POST", "/api/v1/analyses", body, {"Idempotency-Key": str(uuid.uuid4())})
                record("create_job", st, ms, (202, 429))
                if st == 202:
                    jid = job["data"]["id"]
                    for _ in range(600):
                        _, j, _ = s.call("GET", f"/api/v1/jobs/{jid}")
                        if j["data"]["state"] not in ("queued", "running"):
                            break
                        time.sleep(0.2)

    t0 = time.perf_counter()
    with cf.ThreadPoolExecutor(a.sessions) as ex:
        list(ex.map(user, range(a.sessions)))
    wall = time.perf_counter() - t0
    print(json.dumps({"base": a.base, "sessions": a.sessions, "rounds": a.rounds, "data_revision": rev,
                      "contract_version": cfg["data"]["contract_version"], "wall_s": round(wall, 2)}, ensure_ascii=False))
    print(f"{'operation':<18}{'n':>6}{'p50 ms':>10}{'p95 ms':>10}{'max ms':>10}{'errors':>8}")
    for kind, v in sorted(samples.items()):
        print(f"{kind:<18}{len(v):>6}{statistics.median(v):>10.1f}{pct(v, 95):>10.1f}{max(v):>10.1f}{errors[kind]:>8}")
    return 0 if not any(errors.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
