"""Импорт пакета data_release (CT-09, BE-02, политика 21.3).

Гарантии:
* Любая блокирующая ошибка -> пакет отклонен целиком, активная ревизия не меняется (AT-02).
* Публикация атомарна: release + все сущности + active_release в одной транзакции.
* Повтор того же manifest идемпотентен; та же ревизия с другим содержимым - ошибка.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

import fa_contracts as c

from .db import Database, dumps, iso, utcnow

ENTITY_FILES = {
    "investigation": ("Investigation", "investigations.jsonl"),
    "material": ("Material", "materials.jsonl"),
    "run": ("TestRun", "runs.jsonl"),
    "source": ("Source", "sources.jsonl"),
    "evidence": ("Evidence", "evidence.jsonl"),
    "claim": ("Claim", "claims.jsonl"),
}
METRIC_UNITS = {"burn_duration": "s", "visible_extinction_diameter": "m", "flame_spread_rate": "m_s", "particle_diameter": "m"}
OUTCOME_LABELS = {"disruption": "disruption", "extinction": "extinction"}  # исходная метка -> единственно допустимая категория
KNOWN = {"measured", "reported", "derived"}
P0_PSI = {"PSI-25", "PSI-69", "PSI-101"}
# D-036: состав атмосферы. Пакеты до контракта 1.1.0 этих полей не содержат - дополняются not_reported.
GAS_FIELDS = ("oxygen_fraction", "nitrogen_fraction", "co2_fraction", "helium_fraction")
NEW_CONDITION_FIELDS = ("nitrogen_fraction", "co2_fraction", "helium_fraction")
# D-037: conditions_coverage.field - путь поля TestRun, как в осях измерений и строках сравнения.
COVERAGE_FIELDS = {
    "conditions.oxygen_fraction": "fraction", "conditions.nitrogen_fraction": "fraction",
    "conditions.co2_fraction": "fraction", "conditions.helium_fraction": "fraction",
    "conditions.pressure": "Pa", "conditions.airflow_speed": "m_s", "conditions.ambient_temperature": "K",
    "conditions.gravity_level": "g_fraction", "sample.initial_diameter": "m", "sample.thickness": "m",
}
ASSET_EXTENSIONS = (".pdf", ".csv", ".txt", ".png", ".jpg", ".jpeg", ".xlsx", ".docx")


def asset_id_for(source_id: str) -> str:
    """D-038: ID файла источника назначает бэкенд, детерминированно из ID источника."""
    return "asset_" + source_id.removeprefix("src_")


def _not_reported(unit: str) -> dict:
    return {"value": None, "unit": unit, "status": "not_reported", "qualifier": None, "raw_value": None, "raw_unit": None,
            "uncertainty": None, "evidence_ids": [], "derivation": None}


class Report:
    def __init__(self) -> None:
        self.errors: list[dict] = []
        self.warnings: list[dict] = []

    def _issue(self, code, message, file=None, line=None, entity_id=None):
        return {"code": code, "file": file, "line": line, "entity_id": entity_id, "message": message}

    def error(self, code, message, **kw):
        self.errors.append(self._issue(code, message, **kw))

    def warn(self, code, message, **kw):
        self.warnings.append(self._issue(code, message, **kw))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk_quantities(obj: Any, path: str = "") -> Iterator[tuple[str, dict]]:
    """Находит все Quantity внутри сущности (по набору обязательных ключей)."""
    if isinstance(obj, dict):
        if {"value", "unit", "status", "evidence_ids", "derivation"} <= obj.keys():
            yield path, obj
            return
        for k, v in obj.items():
            yield from _walk_quantities(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_quantities(v, f"{path}[{i}]")


def validate_release(release_dir: Path, profile: str = "dev") -> tuple[Report, dict | None, dict[str, dict[str, dict]], str | None]:
    rep = Report()
    release_dir = Path(release_dir).resolve()
    mpath = release_dir / "manifest.json"
    if not mpath.is_file():
        rep.error("MANIFEST_MISSING", "manifest.json не найден", file="manifest.json")
        return rep, None, {}, None
    try:
        manifest = c.strict_json_loads(mpath.read_bytes())
    except ValueError as e:
        rep.error("MANIFEST_INVALID", f"manifest.json не является корректным JSON: {e}", file="manifest.json")
        return rep, None, {}, None
    for v in c.errors_for("InternalManifest", manifest):
        rep.error("MANIFEST_INVALID", f"{v['field']}: {v['reason']}", file="manifest.json")
    if rep.errors:
        return rep, manifest, {}, None
    manifest_sha = _sha256(mpath)
    rev = manifest["data_revision"]

    types_seen = [f["entity_type"] for f in manifest["files"]]
    for t in ENTITY_FILES:
        if types_seen.count(t) != 1:
            rep.error("MANIFEST_FILES", f"entity_type {t} должен встречаться ровно один раз", file="manifest.json")
    if rep.errors:
        return rep, manifest, {}, manifest_sha

    entities: dict[str, dict[str, dict]] = {t: {} for t in ENTITY_FILES}
    where: dict[tuple[str, str], tuple[str, int]] = {}
    for f in manifest["files"]:
        etype, rel = f["entity_type"], f["path"]
        schema = ENTITY_FILES[etype][0]
        fpath = (release_dir / rel).resolve()
        if not fpath.is_relative_to(release_dir) or fpath.is_symlink():
            rep.error("PATH_UNSAFE", "путь вне каталога пакета", file=rel)
            continue
        if not fpath.is_file():
            rep.error("FILE_MISSING", "файл не найден", file=rel)
            continue
        if _sha256(fpath) != f["sha256"]:
            rep.error("SHA256_MISMATCH", "sha256 файла не совпадает с manifest", file=rel)
            continue
        count = 0
        legacy = 0
        with fpath.open("rb") as fh:
            for lineno, raw in enumerate(fh, start=1):
                if not raw.strip():
                    continue
                count += 1
                try:
                    text = raw.decode("utf-8")
                    obj = c.strict_json_loads(text)
                except (UnicodeDecodeError, ValueError) as e:
                    rep.error("JSON_INVALID", f"некорректная строка JSON: {e}", file=rel, line=lineno)
                    continue
                if etype == "run" and isinstance(obj, dict) and isinstance(obj.get("conditions"), dict):
                    missing_new = [k for k in NEW_CONDITION_FIELDS if k not in obj["conditions"]]
                    if missing_new:
                        legacy += 1
                        for k in missing_new:
                            obj["conditions"][k] = _not_reported("fraction")
                viol = c.errors_for(schema, obj)
                eid = obj.get("id") if isinstance(obj, dict) else None
                for v in viol:
                    rep.error("SCHEMA_INVALID", f"{v['field']}: {v['reason']}", file=rel, line=lineno, entity_id=eid)
                if viol:
                    continue
                if "data_revision" in obj and obj["data_revision"] != rev:
                    rep.error("REVISION_MISMATCH", f"data_revision {obj['data_revision']} != {rev}", file=rel, line=lineno, entity_id=eid)
                    continue
                prev = entities[etype].get(eid)
                if prev is not None:
                    if dumps(prev) == dumps(obj):
                        rep.warn("DUPLICATE_IDENTICAL", "повтор идентичной записи пропущен", file=rel, line=lineno, entity_id=eid)
                    else:
                        rep.error("DUPLICATE_ID", f"дубликат ID с разным содержимым (первая строка {where[(etype, eid)][1]})",
                                  file=rel, line=lineno, entity_id=eid)
                    continue
                entities[etype][eid] = obj
                where[(etype, eid)] = (rel, lineno)
        if legacy:
            rep.warn("LEGACY_CONDITIONS_FILLED", f"{legacy} записей без nitrogen_fraction/co2_fraction/helium_fraction "
                     "(пакет до контракта 1.1.0): поля дополнены как not_reported (D-036)", file=rel)
        if count != f["record_count"]:
            rep.error("RECORD_COUNT_MISMATCH", f"record_count={f['record_count']}, фактически {count}", file=rel)
    if rep.errors:
        return rep, manifest, entities, manifest_sha

    _check_semantics(entities, where, rep)
    _check_counts(entities, rep, profile)
    return rep, manifest, entities, manifest_sha


def _check_semantics(E: dict[str, dict[str, dict]], where, rep: Report) -> None:
    ids = {t: set(E[t]) for t in E}

    def loc(t, eid):
        f, ln = where.get((t, eid), (None, None))
        return {"file": f, "line": ln, "entity_id": eid}

    def need(t, eid, ref_type, refs, field):
        for r in refs:
            if r not in ids[ref_type]:
                rep.error("DANGLING_REFERENCE", f"{field}: {r} не найден среди {ref_type}", **loc(t, eid))

    for t, objs in E.items():
        for eid, obj in objs.items():
            for qpath, qv in _walk_quantities(obj):
                need(t, eid, "evidence", qv["evidence_ids"], qpath + ".evidence_ids")
                if qv["status"] in KNOWN:
                    if not qv["evidence_ids"]:
                        rep.error("QUANTITY_WITHOUT_EVIDENCE", f"{qpath}: известное значение без доказательства", **loc(t, eid))
                    val, unit = qv["value"], qv["unit"]
                    if unit == "fraction" and not (0 <= val <= 1):
                        rep.error("VALUE_OUT_OF_RANGE", f"{qpath}: доля вне 0..1 ({val})", **loc(t, eid))
                    if unit in ("m", "s", "Pa", "m_s", "count") and val < 0:
                        rep.error("VALUE_OUT_OF_RANGE", f"{qpath}: отрицательное значение ({val})", **loc(t, eid))
                    if unit == "K" and val <= 0:
                        rep.error("VALUE_OUT_OF_RANGE", f"{qpath}: температура должна быть > 0 K", **loc(t, eid))

    for eid, ev in E["evidence"].items():
        need("evidence", eid, "source", [ev["source_id"]], "source_id")
        if ev["verified"] is not True:
            rep.error("UNVERIFIED_EVIDENCE", "в опубликованный корпус входят только verified=true", **loc("evidence", eid))
        lc = ev["locator"]
        if ev["kind"] == "video_span" and not (lc["end_s"] > lc["start_s"]):
            rep.error("LOCATOR_INVALID", "end_s должен быть больше start_s", **loc("evidence", eid))

    for sid, src in E["source"].items():
        if src["availability"] == "available" and not src["local_asset_id"] and not src["sha256"]:
            rep.warn("AVAILABLE_WITHOUT_ASSET", "availability=available без local_asset_id и sha256: файл нельзя выдать",
                     **loc("source", sid))

    for rid, run in E["run"].items():
        need("run", rid, "investigation", [run["investigation_id"]], "investigation_id")
        if run["material_id"]:
            need("run", rid, "material", [run["material_id"]], "material_id")
        need("run", rid, "evidence", run["evidence_ids"], "evidence_ids")
        need("run", rid, "evidence", run["terminal_outcome"]["evidence_ids"], "terminal_outcome.evidence_ids")
        for m in run["metrics"]:
            exp = METRIC_UNITS[m["metric_key"]]
            if m["quantity"]["unit"] != exp:
                rep.error("UNIT_MISMATCH", f"metrics.{m['metric_key']}: ожидается {exp}, получено {m['quantity']['unit']}", **loc("run", rid))
        keys = [m["metric_key"] for m in run["metrics"]]
        if len(keys) != len(set(keys)):
            rep.error("DUPLICATE_METRIC", "повтор metric_key в одной записи", **loc("run", rid))
        out = run["terminal_outcome"]
        raw = (out["raw_label"] or "").strip().lower()
        if raw in OUTCOME_LABELS and out["category"] != OUTCOME_LABELS[raw]:
            rep.error("OUTCOME_MAPPING", f"исходная метка {out['raw_label']} сопоставлена с {out['category']}", **loc("run", rid))
        gases = [run["conditions"][k] for k in GAS_FIELDS]
        if all(q["status"] in KNOWN for q in gases):
            total = sum(q["value"] for q in gases)
            if abs(total - 1) > 0.02 + 1e-9:  # граница включена: 0.98 и 1.02 - норма округления источника
                rep.warn("COMPOSITION_SUM", f"сумма долей O2+N2+CO2+He = {total:.3f} (ожидается 1 +- 0.02)", **loc("run", rid))
        g = run["conditions"]["gravity_level"]
        if run["conditions"]["gravity_regime"] == "microgravity" and g["value"] == 0:
            rep.warn("MICROGRAVITY_ZERO", "gravity_level=0 при microgravity: проверить, что ноль сообщен источником", **loc("run", rid))

    for iid, inv in E["investigation"].items():
        need("investigation", iid, "material", inv["material_ids"], "material_ids")
        need("investigation", iid, "source", inv["source_ids"], "source_ids")
        need("investigation", iid, "source", inv["available_assets"], "available_assets")
        need("investigation", iid, "claim", inv["claim_ids"], "claim_ids")
        for cov in inv["conditions_coverage"]:
            need("investigation", iid, "evidence", cov["derivation_evidence_ids"], "conditions_coverage.derivation_evidence_ids")
            field = cov["field"]
            if field not in COVERAGE_FIELDS:
                hint = next((p for p in COVERAGE_FIELDS if p.split(".", 1)[1] == field), None)
                rep.error("COVERAGE_FIELD_UNKNOWN", f"conditions_coverage.field={field!r}: нужен путь поля TestRun"
                          + (f", например {hint!r}" if hint else "") + " (D-037)", **loc("investigation", iid))
            elif cov["unit"] != COVERAGE_FIELDS[field]:
                rep.error("UNIT_MISMATCH", f"conditions_coverage {field}: ожидается {COVERAGE_FIELDS[field]}, получено {cov['unit']}",
                          **loc("investigation", iid))
        for cid in inv["claim_ids"]:
            cl = E["claim"].get(cid)
            if cl and iid not in cl["investigation_ids"]:
                rep.warn("CLAIM_LINK_ASYMMETRIC", f"claim {cid} не ссылается на исследование", **loc("investigation", iid))

    for cid, cl in E["claim"].items():
        need("claim", cid, "investigation", cl["investigation_ids"], "investigation_ids")
        need("claim", cid, "evidence", cl["supporting_evidence_ids"], "supporting_evidence_ids")
        need("claim", cid, "evidence", cl["contradicting_evidence_ids"], "contradicting_evidence_ids")
        need("claim", cid, "run", cl["applicable_run_ids"], "applicable_run_ids")
        if cl["kind"] == "synthesis" and len(cl["supporting_evidence_ids"]) < 2:
            rep.warn("SYNTHESIS_SINGLE_EVIDENCE", "synthesis с одним доказательством: нужен документированный обзорный источник", **loc("claim", cid))
        if cl["kind"] in ("observation", "synthesis") and cl["review_status"] == "reviewed" and not cl["supporting_evidence_ids"]:
            rep.error("CLAIM_WITHOUT_EVIDENCE", "вывод без основания", **loc("claim", cid))


def _check_counts(E: dict[str, dict[str, dict]], rep: Report, profile: str) -> None:
    """Минимумы P0 (4.1). profile=p0 - блокирующие, dev - предупреждения (D-005)."""
    emit = rep.error if profile == "p0" else rep.warn
    psi = {inv["psi_id"]: iid for iid, inv in E["investigation"].items()}
    for p in sorted(P0_PSI - psi.keys()):
        emit("P0_COUNT", f"нет обязательного исследования {p}")
    runs_by_inv: dict[str, int] = {}
    for run in E["run"].values():
        runs_by_inv[run["investigation_id"]] = runs_by_inv.get(run["investigation_id"], 0) + 1
    claims_by_inv: dict[str, int] = {}
    reviewed = [cl for cl in E["claim"].values() if cl["review_status"] == "reviewed" and cl["kind"] in ("observation", "synthesis")]
    for cl in reviewed:
        for iid in cl["investigation_ids"]:
            claims_by_inv[iid] = claims_by_inv.get(iid, 0) + 1
    if len(E["run"]) < 30:
        emit("P0_COUNT", f"проверенных записей {len(E['run'])} < 30")
    if len(reviewed) < 12:
        emit("P0_COUNT", f"проверенных выводов {len(reviewed)} < 12 (гипотезы не учитываются)")
    if len(E["source"]) < 8:
        emit("P0_COUNT", f"первичных источников {len(E['source'])} < 8")
    for p in sorted(P0_PSI & psi.keys()):
        iid = psi[p]
        if runs_by_inv.get(iid, 0) < 10:
            emit("P0_COUNT", f"{p}: записей {runs_by_inv.get(iid, 0)} < 10", entity_id=iid)
        if claims_by_inv.get(iid, 0) < 3:
            emit("P0_COUNT", f"{p}: выводов {claims_by_inv.get(iid, 0)} < 3", entity_id=iid)
        kinds = {E["source"][s]["kind"] for s in E["investigation"][iid]["source_ids"] if s in E["source"]}
        if not kinds & {"report", "publication"}:
            emit("P0_COUNT", f"{p}: нет содержательного документа (report/publication)", entity_id=iid)


def assign_assets(entities: dict[str, dict[str, dict]], assets_dir: Path | None, rep: Report) -> int:
    """D-038: для источника availability=available с sha256 и без local_asset_id бэкенд назначает ID,
    если в каталоге файлов лежит asset_<id>.<ext> с тем же sha256 (см. `cli stage-assets`)."""
    if assets_dir is None:
        return 0
    n = 0
    for sid, src in entities.get("source", {}).items():
        if src["availability"] != "available" or src["local_asset_id"] or not src["sha256"]:
            continue
        aid = asset_id_for(sid)
        files = [p for p in Path(assets_dir).glob(aid + ".*") if p.suffix.lower() in ASSET_EXTENSIONS]
        if len(files) == 1 and _sha256(files[0]) == src["sha256"]:
            src["local_asset_id"] = aid
            n += 1
        else:
            rep.warn("ASSET_NOT_STAGED", f"файл источника не найден в каталоге файлов ({aid}.*, sha256 {src['sha256'][:12]}...)",
                     entity_id=sid)
    return n


def stage_assets(release_dir: Path, raw_dir: Path, assets_dir: Path) -> dict:
    """D-038: копирует файлы источников из raw_dir (поиск по sha256) в assets_dir под именем asset_<id>.<ext>."""
    import shutil

    by_hash: dict[str, Path] = {}
    for p in sorted(Path(raw_dir).rglob("*")):
        if p.is_file() and not p.is_symlink() and p.suffix.lower() in ASSET_EXTENSIONS:
            by_hash.setdefault(_sha256(p), p)
    assets_dir = Path(assets_dir)
    assets_dir.mkdir(parents=True, exist_ok=True)
    staged, missing = [], []
    with (Path(release_dir) / "sources.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            src = json.loads(line)
            if src.get("availability") != "available" or not src.get("sha256") or src.get("local_asset_id"):
                continue
            hit = by_hash.get(src["sha256"])
            if hit is None:
                missing.append(src["id"])
                continue
            target = assets_dir / (asset_id_for(src["id"]) + hit.suffix.lower())
            for old in assets_dir.glob(asset_id_for(src["id"]) + ".*"):
                if old != target:
                    old.unlink()
            if not target.exists() or _sha256(target) != src["sha256"]:
                shutil.copyfile(hit, target)
            staged.append({"source_id": src["id"], "file": target.name, "from": str(hit.relative_to(raw_dir))})
    return {"staged": staged, "missing": missing}


def import_release(db: Database, release_dir: Path, profile: str = "dev", activate: bool = True,
                   assets_dir: Path | None = None) -> dict:
    rep, manifest, entities, manifest_sha = validate_release(release_dir, profile)
    if not rep.errors:
        assign_assets(entities, assets_dir, rep)
    rev = manifest.get("data_revision") if isinstance(manifest, dict) else None
    counts = {t: len(v) for t, v in entities.items()} if entities else {}
    if rep.errors:
        return {"accepted": False, "data_revision": rev, "entity_counts": counts, "errors": rep.errors, "warnings": rep.warnings}

    with db.write() as conn:
        row = conn.execute("SELECT manifest_sha256 FROM releases WHERE data_revision = ?", (rev,)).fetchone()
        if row is not None:
            if row[0] != manifest_sha:
                rep.error("REVISION_IMMUTABLE", f"ревизия {rev} уже опубликована с другим содержимым; исправление - новая ревизия",
                          file="manifest.json")
                return {"accepted": False, "data_revision": rev, "entity_counts": counts, "errors": rep.errors, "warnings": rep.warnings}
            rep.warn("ALREADY_IMPORTED", "этот manifest уже импортирован; изменений нет", file="manifest.json")
            return {"accepted": True, "data_revision": rev, "entity_counts": counts, "errors": [], "warnings": rep.warnings}

        now = iso(utcnow())
        conn.execute(
            "INSERT INTO releases VALUES (?, ?, ?, ?, ?, ?, ?)",
            (rev, manifest_sha, manifest["schema_version"], manifest["producer"], manifest["created_at"], now, json.dumps(counts)),
        )
        rows = []
        for etype, objs in entities.items():
            for eid, obj in objs.items():
                inv = obj.get("investigation_id") if etype == "run" else None
                sort_key = (obj.get("source_test_id") or eid) if etype == "run" else (obj.get("acronym") or eid)
                rows.append((rev, etype, eid, inv, sort_key, dumps(obj)))
        conn.executemany("INSERT INTO entities VALUES (?, ?, ?, ?, ?, ?)", rows)
        if activate:
            conn.execute(
                "INSERT INTO active_release (singleton, data_revision, activated_at) VALUES (1, ?, ?) "
                "ON CONFLICT(singleton) DO UPDATE SET data_revision = excluded.data_revision, activated_at = excluded.activated_at",
                (rev, now),
            )
    return {"accepted": True, "data_revision": rev, "entity_counts": counts, "errors": [], "warnings": rep.warnings}


def write_release(out_dir: Path, data_revision: str, entities: dict[str, list[dict]], producer: str,
                  created_at: str, schema_version: str = "1.0.0", quarantined: int = 0, warning_count: int = 0) -> Path:
    """Сборка пакета CT-09 (используется фикстурами и может использоваться AI 1)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for etype, (_, fname) in ENTITY_FILES.items():
        objs = entities.get(etype, [])
        p = out_dir / fname
        p.write_text("".join(dumps(o) + "\n" for o in objs), encoding="utf-8")
        files.append({"path": fname, "entity_type": etype, "sha256": _sha256(p), "record_count": len(objs)})
    manifest = {
        "schema_version": schema_version, "data_revision": data_revision, "created_at": created_at, "producer": producer,
        "files": files,
        "quality_summary": {"checked_records": sum(f["record_count"] for f in files) + quarantined,
                            "quarantined_records": quarantined, "blocking_errors": 0, "warning_count": warning_count},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out_dir
