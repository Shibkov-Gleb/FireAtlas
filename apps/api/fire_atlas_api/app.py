"""Сборка ASGI-приложения Fire Atlas API."""
from __future__ import annotations

import json
import logging
import secrets
import time
from urllib.parse import urlsplit

import fa_contracts as c
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.routing import Route

import contextlib
import hmac

from starlette.responses import JSONResponse

from . import api_catalog as cat
from . import api_compare as cmp
from . import api_jobs as jobsapi
from . import api_search as searchapi
from . import api_system as sysapi
from . import api_workspace as wsapi
from . import providers
from .db import Database
from .errors import ApiError
from .http import ContractJSONResponse, meta
from .jobs import JobRunner
from .metrics import Metrics
from .settings import Settings

access_log = logging.getLogger("fire_atlas.access")
log = logging.getLogger("fire_atlas.api")
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def error_response(request: Request, err: ApiError) -> ContractJSONResponse:
    rev = err.data_revision if err.data_revision is not None else getattr(request.state, "data_revision", None)
    body = {"error": err.body(), "meta": meta(request, rev)}
    return ContractJSONResponse(body, status_code=err.status, headers=err.headers)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """request_id, проверка Origin для изменяющих запросов (CSRF, D-003), журнал без тела запроса (NFR-06)."""

    async def dispatch(self, request: Request, call_next):
        request.state.request_id = "req_" + secrets.token_hex(10)
        request.state.data_revision = None
        started = time.perf_counter()
        settings: Settings = request.app.state.settings
        if request.method in UNSAFE and request.url.path.startswith("/api/"):
            denied = self._csrf_denied(request, settings)
            if denied:
                response = error_response(request, ApiError("ACCESS_DENIED", "Запрос с недоверенного источника отклонен.",
                                                            [{"field": "Origin", "reason": denied}]))
                return self._finish(request, response, started)
        response = await call_next(request)
        return self._finish(request, response, started)

    @staticmethod
    def _csrf_denied(request: Request, s: Settings) -> str | None:
        if request.headers.get("sec-fetch-site") == "cross-site":
            return "cross_site"
        origin = request.headers.get("origin")
        if origin is None and request.headers.get("referer"):
            p = urlsplit(request.headers["referer"])
            origin = f"{p.scheme}://{p.netloc}"
        if origin is None:
            # Браузеры всегда шлют Origin для POST/PATCH/DELETE; без него - не браузер.
            return "origin_required" if s.production else None
        if origin not in s.allowed_origins:
            return "origin_not_allowed"
        return None

    @staticmethod
    def _finish(request: Request, response, started: float):
        response.headers["X-Request-Id"] = request.state.request_id
        response.headers.setdefault("Cache-Control", "no-store")
        route = request.scope.get("route")
        route_path = getattr(route, "path", None) or "unmatched"
        ms = round((time.perf_counter() - started) * 1000, 1)
        request.app.state.metrics.request(route_path, request.method, response.status_code, ms)
        access_log.info(json.dumps({
            "request_id": request.state.request_id, "method": request.method,
            "route": route_path, "status": response.status_code, "duration_ms": ms,
            "workspace_id": getattr(request.state, "workspace_id", None),
        }, ensure_ascii=False))
        return response


async def internal_metrics(request: Request):
    """BE-12. Закрыт токеном FA_INTERNAL_TOKEN; без токена в конфигурации - 404. Наружу не проксируется (BE-13)."""
    token = request.app.state.settings.internal_token
    given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not token or not hmac.compare_digest(given, token):
        raise ApiError("NOT_FOUND")
    return JSONResponse(request.app.state.metrics.snapshot())


async def api_error_handler(request: Request, exc: ApiError):
    return error_response(request, exc)


async def http_error_handler(request: Request, exc: HTTPException):
    if exc.status_code == 405:
        err = ApiError("NOT_FOUND", "Метод не поддерживается для этого адреса.")
    else:
        err = ApiError("NOT_FOUND")
    return error_response(request, err)


async def unhandled_error_handler(request: Request, exc: Exception):
    log.exception("unhandled_error request_id=%s", getattr(request.state, "request_id", None))
    return error_response(request, ApiError("INTERNAL_ERROR"))


def build_app(settings: Settings | None = None) -> Starlette:
    settings = settings or Settings.from_env()
    db = Database(settings.db_path)
    db.migrate()
    p = "/api/v1"
    routes = [
        Route("/health/live", sysapi.health_live),
        Route("/health/ready", sysapi.health_ready),
        Route(f"{p}/config", sysapi.get_config),
        Route(f"{p}/workspaces", wsapi.create_workspace, methods=["POST"]),
        Route(f"{p}/workspaces/current", wsapi.get_workspace, methods=["GET"]),
        Route(f"{p}/workspaces/current", wsapi.patch_workspace, methods=["PATCH"]),
        Route(f"{p}/search", searchapi.search, methods=["POST"]),
        Route(f"{p}/scenario-presets", searchapi.list_presets),
        Route(p + "/investigations/{id:str}", cat.get_investigation),
        Route(p + "/investigations/{id:str}/runs", cat.list_runs),
        Route(p + "/runs/{id:str}", cat.get_run),
        Route(p + "/evidence/{id:str}", cat.get_evidence),
        Route(p + "/sources/{id:str}", cat.get_source),
        Route(p + "/sources/{id:str}/asset", cat.get_source_asset),
        Route(f"{p}/measurements/query", cat.query_measurements, methods=["POST"]),
        Route(f"{p}/comparisons", cmp.compare, methods=["POST"]),
        Route(f"{p}/applicability", cmp.applicability, methods=["POST"]),
        Route(f"{p}/analyses", jobsapi.create_analysis, methods=["POST"]),
        Route(p + "/jobs/{id:str}", jobsapi.get_job, methods=["GET"]),
        Route(p + "/jobs/{id:str}", jobsapi.cancel_job, methods=["DELETE"]),
        Route(p + "/answers/{id:str}", jobsapi.get_answer, methods=["GET"]),
        Route(f"{p}/reports", jobsapi.create_report, methods=["POST"]),
        Route(p + "/reports/{id:str}", jobsapi.get_report, methods=["GET"]),
        Route(p + "/reports/{id:str}/download", jobsapi.download_report, methods=["GET"]),
        Route("/internal/metrics", internal_metrics),
    ]
    metrics = Metrics()
    provs = {kind: providers.load(getattr(settings, kind), kind, db, settings.internal_token)
             for kind in ("retriever", "reasoner", "applicability")}
    runner = JobRunner(settings, db, metrics, provs)
    settings.reports_dir.mkdir(parents=True, exist_ok=True)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        runner.start()
        try:
            yield
        finally:
            runner.stop()

    app = Starlette(
        routes=routes,
        middleware=[],
        lifespan=lifespan,
        exception_handlers={ApiError: api_error_handler, HTTPException: http_error_handler, Exception: unhandled_error_handler},
    )
    app.add_middleware(RequestContextMiddleware)
    app.state.settings = settings
    app.state.db = db
    app.state.metrics = metrics
    app.state.providers = provs
    app.state.runner = runner
    app.state.dictionaries = sysapi.load_dictionaries()
    app.state.search_limiter = searchapi.SlidingWindow(settings.search_per_minute)
    app.state.search_cache = searchapi.TTLCache()
    app.state.presets = searchapi.load_presets(settings.scenario_presets_path or searchapi.PRESETS_PATH)
    c.validator("ConfigEnvelope")  # прогрев: падение на старте, если контракт сломан
    return app
