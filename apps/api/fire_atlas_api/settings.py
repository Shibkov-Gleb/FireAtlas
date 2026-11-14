"""Конфигурация из переменных окружения. Секретов в коде нет (NFR-05)."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from . import REPO_ROOT


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    v = os.environ.get(name)
    return default if v is None else int(v)


@dataclass(frozen=True)
class Settings:
    env: str = "dev"  # dev | test | production
    db_path: Path = REPO_ROOT / "var" / "fire_atlas.sqlite3"
    assets_dir: Path = REPO_ROOT / "var" / "assets"
    allowed_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    cookie_name: str = "fa_session"
    cookie_secure: bool = False
    cursor_secret: bytes = field(default_factory=lambda: secrets.token_bytes(32))
    validate_responses: bool = True
    import_profile: str = "dev"  # dev | p0 - пороги количества CT-09 (D-005)
    # Б.6 limits
    search_limit_max: int = 100
    run_limit_max: int = 200
    measurement_limit_max: int = 1000
    question_chars_max: int = 2000
    comparison_max: int = 3
    analysis_deadline_s: int = 45
    report_deadline_s: int = 30
    workspace_days: int = 7
    report_hours: int = 24
    max_body_bytes: int = 256 * 1024
    # feature flags (возвращаются только реально включенные, BE-04)
    feature_analysis: bool = False
    feature_reports: bool = True
    feature_semantic_search: bool = False
    feature_video_preview: bool = False
    # BE-08: подключаемые модули AI. stub | py:package.module:callable | http(s)://host/internal/v1/...
    retriever: str = "stub"
    reasoner: str = "stub"
    applicability: str = "stub"
    internal_token: str | None = None  # серверная аутентификация внутренних вызовов и /internal/metrics
    reasoning_revision: str = "default"  # ожидаемая версия инструкций AI 2 (передается в reason)
    worker_threads: int = 4
    sweep_interval_s: float = 1.0
    # BE-10
    analysis_per_minute: int = 5
    analysis_active_max: int = 1
    reports_active_max: int = 2
    search_per_minute: int = 60  # на клиентский адрес; 0 - без лимита
    # BE-05
    search_deadline_s: float = 10.0
    scenario_presets_path: Path | None = None  # None - встроенный apps/api/fire_atlas_api/scenario_presets.json
    idempotency_hours: int = 24
    # BE-09
    reports_dir: Path = REPO_ROOT / "var" / "reports"
    font_dir: Path = Path("/usr/share/fonts/truetype/dejavu")
    backups_dir: Path = REPO_ROOT / "var" / "backups"

    @property
    def production(self) -> bool:
        return self.env == "production"

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ.get("FA_ENV", "dev")
        secret = os.environ.get("FA_CURSOR_SECRET")
        if env == "production" and not secret:
            raise RuntimeError("FA_CURSOR_SECRET обязателен в production")
        origins = os.environ.get("FA_ALLOWED_ORIGINS")
        retriever = os.environ.get("FA_RETRIEVER", "stub")
        reasoner = os.environ.get("FA_REASONER", "stub")
        applicability = os.environ.get("FA_APPLICABILITY", "stub")
        feature_analysis = _bool("FA_FEATURE_ANALYSIS", False)
        if env == "production" and feature_analysis and "stub" in (retriever, reasoner, applicability):
            # Заглушка в production опубликовала бы не-ответ как ответ AI (FR-14).
            raise RuntimeError("В production анализ нельзя включать с заглушками FA_RETRIEVER/FA_REASONER/FA_APPLICABILITY")
        return cls(
            env=env,
            db_path=Path(os.environ.get("FA_DB_PATH", str(cls.db_path))),
            assets_dir=Path(os.environ.get("FA_ASSETS_DIR", str(cls.assets_dir))),
            allowed_origins=tuple(o.strip() for o in origins.split(",") if o.strip()) if origins else cls.allowed_origins,
            cookie_secure=_bool("FA_COOKIE_SECURE", env == "production"),
            cursor_secret=secret.encode() if secret else secrets.token_bytes(32),
            validate_responses=_bool("FA_VALIDATE_RESPONSES", env != "production"),
            import_profile=os.environ.get("FA_IMPORT_PROFILE", "p0" if env == "production" else "dev"),
            feature_analysis=feature_analysis,
            feature_reports=_bool("FA_FEATURE_REPORTS", True),
            feature_semantic_search=_bool("FA_FEATURE_SEMANTIC_SEARCH", False),
            feature_video_preview=_bool("FA_FEATURE_VIDEO_PREVIEW", False),
            workspace_days=_int("FA_WORKSPACE_DAYS", 7),
            report_hours=_int("FA_REPORT_HOURS", 24),
            retriever=retriever,
            reasoner=reasoner,
            applicability=applicability,
            internal_token=os.environ.get("FA_INTERNAL_TOKEN") or None,
            reasoning_revision=os.environ.get("FA_REASONING_REVISION", "default"),
            worker_threads=_int("FA_WORKER_THREADS", 4),
            analysis_deadline_s=_int("FA_ANALYSIS_DEADLINE_S", 45),
            report_deadline_s=_int("FA_REPORT_DEADLINE_S", 30),
            analysis_per_minute=_int("FA_ANALYSIS_PER_MINUTE", 5),
            search_per_minute=_int("FA_SEARCH_PER_MINUTE", 60),
            search_deadline_s=float(os.environ.get("FA_SEARCH_DEADLINE_S", "10")),
            scenario_presets_path=Path(os.environ["FA_SCENARIO_PRESETS"]) if os.environ.get("FA_SCENARIO_PRESETS") else None,
            reports_dir=Path(os.environ.get("FA_REPORTS_DIR", str(cls.reports_dir))),
            font_dir=Path(os.environ.get("FA_FONT_DIR", str(cls.font_dir))),
            backups_dir=Path(os.environ.get("FA_BACKUPS_DIR", str(cls.backups_dir))),
        )
