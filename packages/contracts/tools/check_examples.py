"""Проверка contracts/examples против openapi.yaml (BE-01, CT-16).

    python3 packages/contracts/tools/check_examples.py

Код возврата 0 - все примеры валидны. Используется в CI и всеми участниками.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fa_contracts as c  # noqa: E402

# Раздел 14: код ошибки -> допустимые HTTP-статусы
ERROR_STATUS = {
    "MALFORMED_JSON": {400}, "SESSION_REQUIRED": {401}, "ACCESS_DENIED": {403}, "NOT_FOUND": {404},
    "WORKSPACE_CONFLICT": {409}, "IDEMPOTENCY_CONFLICT": {409}, "JOB_ALREADY_FINISHED": {409}, "REPORT_NOT_READY": {409},
    "DATA_REVISION_GONE": {410}, "RESOURCE_EXPIRED": {410}, "VALIDATION_ERROR": {422}, "INVALID_CURSOR": {422},
    "RATE_LIMITED": {429}, "MODEL_PROVIDER_ERROR": {502}, "AI_UNAVAILABLE": {503}, "DATA_NOT_READY": {503},
    "JOB_TIMEOUT": {504}, "INTERNAL_ERROR": {500},
}

# Обязательные примеры CT-16 (operation_id, case)
REQUIRED = [
    ("search", "oxygen_021"), ("getRun", "missing_pressure"), ("compareInvestigations", "different_methods"),
    ("assessApplicability", "moon_no_direct"), ("getAnswer", "answered"), ("getAnswer", "insufficient_evidence"),
    ("getJob", "provider_failed"), ("getJob", "cancelled"), ("patchCurrentWorkspace", "conflict"),
    ("getReport", "ready"), ("getReport", "expired"), ("getRun", "flex_30cal03"), ("queryMeasurements", "flex_5_points"),
]


def main() -> int:
    ops = c.operation_index()
    files = sorted(p for p in c.EXAMPLES_DIR.rglob("*.json") if p.name != "index.json")
    failures: list[str] = []
    seen = set()
    states = Counter()
    for p in files:
        ex = c.strict_json_loads(p.read_text(encoding="utf-8"))
        op_id, case = ex["operation_id"], ex["case"]
        seen.add((op_id, case))
        where = f"{op_id}/{case}"
        if op_id not in ops:
            failures.append(f"{where}: unknown operationId")
            continue
        op = ops[op_id]
        status = ex["response"]["status"]
        states[status // 100] += 1
        if status not in op["responses"]:
            failures.append(f"{where}: status {status} не объявлен для {op['method']} {op['path']}")
            continue
        schema = op["responses"][status]
        body = ex["response"]["body"]
        if schema is None:
            if body is not None:
                failures.append(f"{where}: для {status} тело должно отсутствовать")
        else:
            for v in c.errors_for(schema, body):
                failures.append(f"{where}: response {schema} {v['field']}: {v['reason']}")
            if schema == "ErrorResponse":
                code = body["error"]["code"]
                allowed = ERROR_STATUS.get(code)
                if allowed and status not in allowed:
                    failures.append(f"{where}: код {code} не соответствует HTTP {status}")
        req_schema = op["request_schema"]
        if 200 <= status < 300 and req_schema:
            for v in c.errors_for(req_schema, ex["request"]["body"]):
                failures.append(f"{where}: request {req_schema} {v['field']}: {v['reason']}")
    for op_id, case in REQUIRED:
        if (op_id, case) not in seen:
            failures.append(f"отсутствует обязательный пример CT-16: {op_id}/{case}")
    for op_id in ops:
        if not any(o == op_id for o, _ in seen) and op_id not in ("healthLive", "healthReady", "getSourceAsset"):
            failures.append(f"нет ни одного примера для {op_id}")

    # Внутренние схемы проверяются на фикстурных сущностях
    fx = c.strict_json_loads((c.CONTRACTS_DIR / "fixtures_entities.json").read_text(encoding="utf-8"))
    for key, schema in [("sources", "Source"), ("evidence", "Evidence"), ("runs", "TestRun"), ("materials", "Material"),
                        ("claims", "Claim"), ("investigations", "Investigation")]:
        for eid, obj in fx[key].items():
            for v in c.errors_for(schema, obj):
                failures.append(f"fixture {key}/{eid}: {v['field']}: {v['reason']}")

    if failures:
        print(f"FAIL: {len(failures)} нарушений в {len(files)} примерах")
        for f in failures:
            print("  -", f)
        return 1
    print(f"OK: {len(files)} примеров, {len(ops)} операций; 2xx={states[2]} 4xx={states[4]} 5xx={states[5]}; "
          f"контракт {c.contract_version()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
