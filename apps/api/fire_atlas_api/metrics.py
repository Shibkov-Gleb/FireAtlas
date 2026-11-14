"""BE-12: длительности запросов и этапов задач, коды ошибок. Без текста вопросов и секретов."""
from __future__ import annotations

import threading
from collections import Counter, defaultdict, deque


def _pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(p / 100 * (len(s) - 1)))))
    return round(s[k], 1)


class Metrics:
    def __init__(self, window: int = 2000):
        self._lock = threading.Lock()
        self._durations: dict[str, deque] = defaultdict(lambda: deque(maxlen=window))
        self._statuses: Counter = Counter()
        self._stages: dict[str, deque] = defaultdict(lambda: deque(maxlen=window))
        self._job_outcomes: Counter = Counter()

    def request(self, route: str, method: str, status: int, ms: float) -> None:
        key = f"{method} {route}"
        with self._lock:
            self._durations[key].append(ms)
            self._statuses[(key, status)] += 1

    def stage(self, job_type: str, stage: str, ms: float) -> None:
        with self._lock:
            self._stages[f"{job_type}.{stage}"].append(ms)

    def job_finished(self, job_type: str, state: str, error_code: str | None) -> None:
        with self._lock:
            self._job_outcomes[(job_type, state, error_code or "-")] += 1

    def snapshot(self) -> dict:
        with self._lock:
            routes = {}
            for key, d in self._durations.items():
                vals = list(d)
                routes[key] = {"count": sum(n for (k, _), n in self._statuses.items() if k == key),
                               "p50_ms": _pct(vals, 50), "p95_ms": _pct(vals, 95),
                               "statuses": {str(s): n for (k, s), n in self._statuses.items() if k == key}}
            stages = {k: {"count": len(d), "p50_ms": _pct(list(d), 50), "p95_ms": _pct(list(d), 95)} for k, d in self._stages.items()}
            jobs = [{"type": t, "state": s, "error_code": e, "count": n} for (t, s, e), n in sorted(self._job_outcomes.items())]
        return {"routes": routes, "job_stages": stages, "job_outcomes": jobs}
