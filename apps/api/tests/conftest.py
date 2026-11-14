"""Тестовая обвязка: настоящий uvicorn в потоке + HTTP-клиент на urllib (httpx не требуется)."""
from __future__ import annotations

import json
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "tools"))

import uvicorn  # noqa: E402

from fire_atlas_api.app import build_app  # noqa: E402
from fire_atlas_api.db import Database  # noqa: E402
from fire_atlas_api.importer import import_release  # noqa: E402
from fire_atlas_api.settings import Settings  # noqa: E402
import make_fixture_release  # noqa: E402

ORIGIN = "http://localhost:5173"
FIX_REV = make_fixture_release.FIXTURE_REV


class Resp:
    def __init__(self, status, headers, raw):
        self.status, self.headers, self.raw = status, headers, raw

    @property
    def json(self):
        return json.loads(self.raw)

    @property
    def data(self):
        return self.json["data"]

    @property
    def error(self):
        return self.json["error"]


class Client:
    """Мини-клиент с cookie-jar на одну сессию."""

    def __init__(self, base: str):
        self.base = base
        self.cookies: dict[str, str] = {}

    def request(self, method, path, body=None, headers=None, raw_body: bytes | None = None, origin=ORIGIN):
        h = {"Accept": "application/json"}
        if origin and method in ("POST", "PATCH", "DELETE"):
            h["Origin"] = origin
        data = raw_body
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        if self.cookies:
            h["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        h.update(headers or {})
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                resp = Resp(r.status, r.headers, r.read())
                set_cookie = r.headers.get_all("Set-Cookie") or []
        except urllib.error.HTTPError as e:
            resp = Resp(e.code, e.headers, e.read())
            set_cookie = e.headers.get_all("Set-Cookie") or []
        for sc in set_cookie:
            k, v = sc.split(";", 1)[0].split("=", 1)
            self.cookies[k.strip()] = v.strip()
        return resp

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, body=body, **kw)

    def patch(self, path, body=None, **kw):
        return self.request("PATCH", path, body=body, **kw)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LiveServer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.app = build_app(settings)
        self.port = _free_port()
        self.server = uvicorn.Server(uvicorn.Config(self.app, host="127.0.0.1", port=self.port, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        for _ in range(200):
            if self.server.started:
                return self
            time.sleep(0.02)
        raise RuntimeError("server did not start")

    def __exit__(self, *exc):
        self.server.should_exit = True
        self.thread.join(5)

    @property
    def base(self):
        return f"http://127.0.0.1:{self.port}"

    def client(self) -> Client:
        return Client(self.base)

    @property
    def db(self) -> Database:
        return self.app.state.db


def make_settings(tmp: Path, **kw) -> Settings:
    base = dict(env="test", db_path=tmp / "db.sqlite3", assets_dir=tmp / "assets", allowed_origins=(ORIGIN,),
                validate_responses=True, reports_dir=tmp / "reports", feature_analysis=True, sweep_interval_s=0.2,
                search_per_minute=0)
    return replace(Settings(), **{**base, **kw})


@pytest.fixture(scope="session")
def release_dir(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("release")
    make_fixture_release.build(d / "rel", d / "assets")
    return d


@pytest.fixture(scope="session")
def server(tmp_path_factory, release_dir):
    tmp = tmp_path_factory.mktemp("srv")
    s = make_settings(tmp)
    s = replace(s, assets_dir=release_dir / "assets")
    db = Database(s.db_path)
    db.migrate()
    rep = import_release(db, release_dir / "rel", "dev")
    assert rep["accepted"], rep["errors"]
    with LiveServer(s) as srv:
        yield srv


@pytest.fixture
def empty_server(tmp_path):
    with LiveServer(make_settings(tmp_path)) as srv:
        yield srv


@pytest.fixture
def guest(server) -> Client:
    cl = server.client()
    r = cl.post("/api/v1/workspaces", {})
    assert r.status == 201, r.raw
    return cl


def prepared_settings(tmp: Path, release_dir: Path, **kw) -> Settings:
    """Отдельная БД с импортированным фикстурным корпусом."""
    s = replace(make_settings(tmp, **kw), assets_dir=release_dir / "assets")
    db = Database(s.db_path)
    db.migrate()
    assert import_release(db, release_dir / "rel", "dev")["accepted"]
    return s


@pytest.fixture
def make_server(tmp_path, release_dir):
    """Фабрика отдельных серверов: make_server(analysis_deadline_s=2) -> контекстный менеджер."""
    n = [0]

    def factory(**kw):
        n[0] += 1
        return LiveServer(prepared_settings(tmp_path / f"s{n[0]}", release_dir, **kw))

    return factory


@pytest.fixture
def providers(server):
    """Подмена AI-провайдеров общего сервера с восстановлением после теста."""
    saved = dict(server.app.state.providers)
    server.app.state.search_cache = type(server.app.state.search_cache)()
    yield server.app.state.providers
    server.app.state.providers.clear()
    server.app.state.providers.update(saved)
    server.app.state.search_cache = type(server.app.state.search_cache)()


TERMINAL = {"succeeded", "failed", "cancelled", "expired"}


def poll(cl: Client, job_id: str, timeout: float = 10.0, until=TERMINAL) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = cl.get(f"/api/v1/jobs/{job_id}")
        assert r.status == 200, r.raw
        if r.data["state"] in until or (r.data["stage"] in until):
            return r.data
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not reach {until}: {r.data}")


def example(op: str, case: str) -> dict:
    p = ROOT / "packages" / "contracts" / "examples" / op / f"{case}.json"
    return json.loads(p.read_text(encoding="utf-8"))


def scenario(name: str) -> dict:
    sc = example("patchCurrentWorkspace", "set_moon")["request"]["body"]["scenario"]
    if name == "moon":
        return sc
    orb = example("getCurrentWorkspace", "ok")["response"]["body"]["data"]["scenario"]
    return orb


def set_scenario(cl: Client, sc: dict | None) -> int:
    rev = cl.get("/api/v1/workspaces/current").data["revision"]
    r = cl.patch("/api/v1/workspaces/current", {"scenario": sc}, headers={"If-Match": f'"{rev}"'})
    assert r.status == 200, r.raw
    return r.data["revision"]


def start_analysis(cl: Client, question="Как поток воздуха влияет на горение?", selected=("inv_psi69",), key=None, ws_rev=None,
                   rev=FIX_REV):
    import uuid

    if ws_rev is None:
        ws_rev = cl.get("/api/v1/workspaces/current").data["revision"]
    body = {"question": question, "locale": "ru", "workspace_revision": ws_rev, "data_revision": rev,
            "selected_investigation_ids": list(selected), "mode": "evidence_answer"}
    return cl.post("/api/v1/analyses", body, headers={"Idempotency-Key": key or str(uuid.uuid4())}), body
