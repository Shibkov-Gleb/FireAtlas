"""Мок-сервер публичного API по contracts/examples (CT-16, FE работает с первого дня).

    python3 packages/contracts/mock_server.py --port 4010

Выбор примера:
  * заголовок  Prefer: example=<case>   (совместимо с Prism)
  * или query  ?__example=<case>
  * иначе - пример с default=true для операции.

Мок проверяет тело запроса по той же схеме, что и бэкенд: неожиданное поле -> 422.
Список примеров: GET /__examples
"""
from __future__ import annotations

import argparse
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fa_contracts as c  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.middleware import Middleware  # noqa: E402
from starlette.middleware.cors import CORSMiddleware  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import JSONResponse, Response  # noqa: E402
from starlette.routing import Route  # noqa: E402


def _load_examples():
    by_op: dict[str, dict[str, dict]] = {}
    for p in sorted(c.EXAMPLES_DIR.rglob("*.json")):
        if p.name == "index.json":
            continue
        ex = c.strict_json_loads(p.read_text(encoding="utf-8"))
        by_op.setdefault(ex["operation_id"], {})[ex["case"]] = ex
    return by_op


EXAMPLES = _load_examples()
OPS = c.operation_index()


def _route_regex(path: str) -> re.Pattern:
    return re.compile("^/api/v1" + re.sub(r"\{[^/]+\}", r"[^/]+", path) + "$")


ROUTES = [(op["method"], _route_regex(op["path"]), op_id) for op_id, op in OPS.items()]


def _error(status: int, code: str, message: str, details=None):
    return JSONResponse(
        {"error": {"code": code, "message": message, "details": details or [], "retryable": False},
         "meta": {"request_id": f"req_mock{uuid.uuid4().hex[:12]}", "contract_version": c.contract_version(),
                  "data_revision": None, "warnings": []}},
        status_code=status,
    )


async def dispatch(request: Request) -> Response:
    path = request.url.path
    op_id = next((o for m, rx, o in ROUTES if m == request.method and rx.match(path)), None)
    if op_id is None:
        return _error(404, "NOT_FOUND", "Метод не найден в контракте.")
    op = OPS[op_id]
    if op["request_schema"]:
        raw = await request.body()
        try:
            body = c.strict_json_loads(raw or b"null")
        except ValueError:
            return _error(400, "MALFORMED_JSON", "Некорректный JSON.")
        violations = c.errors_for(op["request_schema"], body)
        if violations:
            return _error(422, "VALIDATION_ERROR", "Запрос не соответствует контракту.",
                          [{"field": v["field"], "reason": v["reason"], "current_revision": None} for v in violations])
    cases = EXAMPLES.get(op_id, {})
    prefer = request.headers.get("prefer", "")
    m = re.search(r"example=([A-Za-z0-9_-]+)", prefer)
    case = request.query_params.get("__example") or (m.group(1) if m else None)
    ex = cases.get(case) if case else next((e for e in cases.values() if e["default"]), None)
    if ex is None:
        return _error(404, "NOT_FOUND", f"Нет примера '{case}' для {op_id}. Доступно: {sorted(cases)}")
    resp = ex["response"]
    headers = {k: v for k, v in resp["headers"].items() if k.lower() != "set-cookie"}
    headers["X-Mock-Example"] = f"{op_id}/{ex['case']}"
    if resp["body"] is None:
        r = Response(status_code=resp["status"], headers=headers)
    else:
        r = JSONResponse(resp["body"], status_code=resp["status"], headers=headers)
    if "Set-Cookie" in resp["headers"]:
        r.set_cookie("fa_session", "mock-session", httponly=True, samesite="lax", path="/api")
    return r


async def list_examples(request: Request) -> Response:
    return JSONResponse({op: sorted(cases) for op, cases in EXAMPLES.items()})


def build_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/__examples", list_examples),
            Route("/api/v1/{rest:path}", dispatch, methods=["GET", "POST", "PATCH", "DELETE"]),
        ],
        middleware=[Middleware(CORSMiddleware, allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
                               allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
                               expose_headers=["ETag", "Retry-After", "X-Request-Id", "X-Mock-Example"])],
    )


app = build_app()

if __name__ == "__main__":
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4010)
    a = ap.parse_args()
    uvicorn.run(app, host=a.host, port=a.port)
