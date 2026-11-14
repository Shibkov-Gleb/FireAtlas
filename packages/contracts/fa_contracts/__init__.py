"""Общий загрузчик контрактов Fire Atlas.

Единственный источник правды - packages/contracts/openapi.yaml. Этот модуль
используется бэкендом (валидация запросов/ответов), мок-сервером, проверкой
examples и внутренними модулями AI 1 / AI 2 (InternalRetrieval*, InternalReasoning*).

    from fa_contracts import validate, errors_for
    validate("Workspace", obj)            # бросает ContractError
    errors_for("SearchRequest", body)     # список нарушений для 422
"""
from __future__ import annotations

import functools
import json
import math
from pathlib import Path
from typing import Any, Iterable

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

CONTRACTS_DIR = Path(__file__).resolve().parent.parent
OPENAPI_PATH = CONTRACTS_DIR / "openapi.yaml"
EXAMPLES_DIR = CONTRACTS_DIR / "examples"
BASE_URI = "urn:fire-atlas:openapi"

__all__ = [
    "ContractError",
    "Violation",
    "openapi",
    "contract_version",
    "schema_names",
    "validator",
    "validate",
    "errors_for",
    "strict_json_loads",
    "operation_index",
]


class ContractError(ValueError):
    def __init__(self, schema: str, violations: list["Violation"]):
        self.schema = schema
        self.violations = violations
        first = violations[0] if violations else None
        super().__init__(f"{schema}: {first}" if first else schema)


class Violation(dict):
    """{field, reason} - совместимо с ErrorDetail (current_revision добавляет вызывающий)."""

    def __str__(self) -> str:  # pragma: no cover - только для логов
        return f"{self['field']}: {self['reason']}"


@functools.lru_cache(maxsize=1)
def openapi() -> dict[str, Any]:
    with OPENAPI_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def contract_version() -> str:
    return openapi()["info"]["version"]


def schema_names() -> list[str]:
    return sorted(openapi()["components"]["schemas"].keys())


@functools.lru_cache(maxsize=1)
def _registry() -> Registry:
    resource = Resource.from_contents(openapi(), default_specification=DRAFT202012)
    return Registry().with_resource(BASE_URI, resource)


@functools.lru_cache(maxsize=None)
def validator(schema_name: str) -> Draft202012Validator:
    if schema_name not in openapi()["components"]["schemas"]:
        raise KeyError(f"unknown schema {schema_name}")
    ref = {"$ref": f"{BASE_URI}#/components/schemas/{schema_name}"}
    return Draft202012Validator(ref, registry=_registry(), format_checker=FormatChecker())


def _path(err) -> str:
    parts = []
    for p in err.absolute_path:
        parts.append(f"[{p}]" if isinstance(p, int) else (("." if parts else "") + str(p)))
    return "".join(parts) or "$"


def _flatten(errors: Iterable) -> list:
    """Раскрывает anyOf/oneOf/allOf до самых конкретных ошибок."""
    out = []
    for e in errors:
        if e.context:
            # Берем ветку с наиболее глубокими ошибками - она обычно ближе к намерению клиента.
            out.extend(_flatten(sorted(e.context, key=lambda c: -len(c.absolute_path))[:3]))
        else:
            out.append(e)
    return out


def errors_for(schema_name: str, instance: Any, limit: int = 20) -> list[Violation]:
    v = validator(schema_name)
    raw = sorted(v.iter_errors(instance), key=lambda e: (list(map(str, e.absolute_path)), e.message))
    seen, result = set(), []
    for e in _flatten(raw):
        base = _path(e)
        if e.validator == "additionalProperties" and isinstance(e.instance, dict):
            allowed = set((e.schema.get("properties") or {}).keys())
            extras = [k for k in e.instance if k not in allowed] or ["?"]
            items = [Violation(field=(k if base == "$" else f"{base}.{k}"), reason="unexpected_field") for k in extras]
        elif e.validator == "required" and isinstance(e.instance, dict):
            missing = [k for k in e.validator_value if k not in e.instance]
            items = [Violation(field=(k if base == "$" else f"{base}.{k}"), reason="required") for k in missing]
        else:
            items = [Violation(field=base, reason=_reason(e))]
        for item in items:
            key = (item["field"], item["reason"])
            if key not in seen:
                seen.add(key)
                result.append(item)
        if len(result) >= limit:
            break
    return result[:limit]


def _reason(err) -> str:
    v = err.validator
    if v == "additionalProperties":
        return "unexpected_field"
    if v == "required":
        return "required"
    if v in ("enum", "const"):
        return "not_allowed_value"
    if v == "type":
        return "wrong_type"
    if v in ("maxLength", "minLength"):
        return "length_out_of_range"
    if v in ("maxItems", "minItems"):
        return "items_count_out_of_range"
    if v in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
        return "out_of_range"
    if v == "pattern":
        return "invalid_format"
    if v == "format":
        return "invalid_format"
    if v == "uniqueItems":
        return "duplicate_items"
    if v == "minProperties":
        return "empty_object"
    return v or "invalid"


def validate(schema_name: str, instance: Any) -> None:
    errs = errors_for(schema_name, instance)
    if errs:
        raise ContractError(schema_name, errs)


def _reject_constant(name: str):
    raise ValueError(f"non-finite number {name} is not allowed")


def strict_json_loads(text: str | bytes) -> Any:
    """json.loads без NaN/Infinity (Python принимает их по умолчанию) и без дублей ключей."""

    def pairs_hook(pairs):
        obj = {}
        for k, val in pairs:
            if k in obj:
                raise ValueError(f"duplicate key {k!r}")
            obj[k] = val
        return obj

    def parse_float(s: str) -> float:
        f = float(s)
        if not math.isfinite(f):
            raise ValueError("non-finite number")
        return f

    return json.loads(
        text,
        parse_constant=_reject_constant,
        parse_float=parse_float,
        object_pairs_hook=pairs_hook,
    )


@functools.lru_cache(maxsize=1)
def operation_index() -> dict[str, dict[str, Any]]:
    """operationId -> {method, path, request_schema, responses{status: schema|None}}."""
    out: dict[str, dict[str, Any]] = {}
    for path, item in openapi()["paths"].items():
        for method, op in item.items():
            if method not in ("get", "post", "patch", "delete", "put"):
                continue
            req = None
            body = op.get("requestBody", {}).get("content", {}).get("application/json")
            if body:
                req = body["schema"]["$ref"].rsplit("/", 1)[-1]
            responses = {}
            for status, resp in op.get("responses", {}).items():
                if "$ref" in resp:
                    resp = openapi()["components"]["responses"][resp["$ref"].rsplit("/", 1)[-1]]
                js = resp.get("content", {}).get("application/json")
                responses[int(status)] = js["schema"]["$ref"].rsplit("/", 1)[-1] if js else None
            out[op["operationId"]] = {
                "method": method.upper(),
                "path": path,
                "request_schema": req,
                "responses": responses,
            }
    return out
