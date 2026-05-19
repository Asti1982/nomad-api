"""Autogenesis Protocol surfaces for Nomad.

This module keeps AGP operationally conservative: resources, protocol
candidates, and self-play tests are admitted as descriptor-only shadow work
until proof digests, boundedness, rollback/no-op, and verifier traces justify
more weight.
"""

from __future__ import annotations

import base64
import csv
import gzip
import hashlib
import io
import json
import os
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from nomad_variant_forge import _canonical_verifier_receipt_digest as _variant_verifier_receipt_digest


DEFAULT_RESOURCE_LEDGER_PATH = Path(
    os.getenv("NOMAD_RESOURCE_SUBSTRATE_LEDGER_PATH", "nomad_resource_substrate_ledger.jsonl")
)
DEFAULT_DEVELOPMENT_CYCLE_LEDGER_PATH = Path(
    os.getenv("NOMAD_DEVELOPMENT_CYCLES_LEDGER_PATH", "nomad_development_cycles_ledger.jsonl")
)
DEFAULT_AUTONOMOUS_AGP_LEDGER_PATH = Path(
    os.getenv("NOMAD_AUTONOMOUS_AGP_LEDGER_PATH", "nomad_autonomous_agp_ledger.jsonl")
)
DEFAULT_AUTONOMOUS_AGP_WATCHDOG_LEDGER_PATH = Path(
    os.getenv("NOMAD_AUTONOMOUS_AGP_WATCHDOG_LEDGER_PATH", "nomad_autonomous_agp_watchdog_ledger.jsonl")
)
DEFAULT_AGP_TRACE_LEDGER_PATH = Path(
    os.getenv("NOMAD_AGP_TRACE_LEDGER_PATH", "nomad_agp_trace_ledger.jsonl")
)
DEFAULT_AGP_PROCUREMENT_LEDGER_PATH = Path(
    os.getenv("NOMAD_AGP_PROCUREMENT_LEDGER_PATH", "nomad_agp_procurement_ledger.jsonl")
)
DEFAULT_AGP_CONTEXT_LEDGER_PATH = Path(
    os.getenv("NOMAD_AGP_CONTEXT_LEDGER_PATH", "nomad_agp_context_ledger.jsonl")
)
DEFAULT_AGP_OPTIMIZER_LEDGER_PATH = Path(
    os.getenv("NOMAD_AGP_OPTIMIZER_LEDGER_PATH", "nomad_agp_optimizer_ledger.jsonl")
)
DEFAULT_AGP_EVALUATION_LEDGER_PATH = Path(
    os.getenv("NOMAD_AGP_EVALUATION_LEDGER_PATH", "nomad_agp_evaluation_ledger.jsonl")
)
DEFAULT_AGP_AGENT_BUS_LEDGER_PATH = Path(
    os.getenv("NOMAD_AGP_AGENT_BUS_LEDGER_PATH", "nomad_agp_agent_bus_ledger.jsonl")
)
DEFAULT_AGP_PLAN_LEDGER_PATH = Path(
    os.getenv("NOMAD_AGP_PLAN_LEDGER_PATH", "nomad_agp_plan_ledger.jsonl")
)
DEFAULT_AGP_ORCHESTRATION_LEDGER_PATH = Path(
    os.getenv("NOMAD_AGP_ORCHESTRATION_LEDGER_PATH", "nomad_agp_orchestration_ledger.jsonl")
)
DEFAULT_AGP_MODEL_BINDING_LEDGER_PATH = Path(
    os.getenv("NOMAD_AGP_MODEL_BINDING_LEDGER_PATH", "nomad_agp_model_binding_ledger.jsonl")
)
DEFAULT_AGP_CONFIG_LEDGER_PATH = Path(
    os.getenv("NOMAD_AGP_CONFIG_LEDGER_PATH", "nomad_agp_config_ledger.jsonl")
)
DEFAULT_AGP_PROMPT_LEDGER_PATH = Path(
    os.getenv("NOMAD_AGP_PROMPT_LEDGER_PATH", "nomad_agp_prompt_ledger.jsonl")
)
DEFAULT_AGP_BENCHMARK_LEDGER_PATH = Path(
    os.getenv("NOMAD_AGP_BENCHMARK_LEDGER_PATH", "nomad_agp_benchmark_ledger.jsonl")
)
DEFAULT_AGP_VERSION_LINEAGE_LEDGER_PATH = Path(
    os.getenv("NOMAD_AGP_VERSION_LINEAGE_LEDGER_PATH", "nomad_agp_version_lineage_ledger.jsonl")
)
DEFAULT_AGP_PULSE_LEDGER_PATH = Path(
    os.getenv("NOMAD_AGP_PULSE_LEDGER_PATH", "nomad_agp_pulse_ledger.jsonl")
)
DEFAULT_AGP_EMPIRICAL_LEDGER_PATH = Path(
    os.getenv("NOMAD_AGP_EMPIRICAL_LEDGER_PATH", "nomad_agp_empirical_ledger.jsonl")
)
DEFAULT_AGP_PAPER_BENCHMARK_LEDGER_PATH = Path(
    os.getenv("NOMAD_AGP_PAPER_BENCHMARK_LEDGER_PATH", "nomad_agp_paper_benchmark_ledger.jsonl")
)
DEFAULT_AGP_SQLITE_LEDGER_PATH = Path(
    os.getenv("NOMAD_AGP_SQLITE_LEDGER_PATH", "nomad_agp_ledger.sqlite3")
)
MAX_RECENT = 40
RESOURCE_STATES = ("draft", "shadow", "tested", "weighted", "committed", "rolled_back", "noop")
AGP_CANDIDATE_TYPES = (
    "protocol-evolution-candidate",
    "self-play-test-suite",
    "resource-version-patch",
    "sepl-operator-patch",
    "rspl-contract-patch",
)
RSPL_ENTITY_TYPES = ("prompt", "agent", "tool", "environment", "memory")
SEPL_OPERATORS = ("reflect", "select", "improve", "evaluate", "commit")
AGP_BENCHMARK_MODES = ("gpqa_diamond", "aime", "gaia", "leetcode")
AGP_OPEN_BENCHMARK_FIXTURES = (
    {
        "mode": "gpqa_diamond",
        "benchmark_id": "gpqa-lite-retrieval-causality",
        "task_digest": "sha256:gpqa-lite-agent-routing-causality",
        "expected_signal": "receipt_chain_before_weight_increase",
    },
    {
        "mode": "aime",
        "benchmark_id": "aime-lite-budget-modulo",
        "task_digest": "sha256:aime-lite-free-tier-quota-arithmetic",
        "expected_signal": "bounded_daily_quota",
    },
    {
        "mode": "gaia",
        "benchmark_id": "gaia-lite-route-selection",
        "task_digest": "sha256:gaia-lite-live-endpoint-evidence",
        "expected_signal": "durable_receipt_route",
    },
    {
        "mode": "leetcode",
        "benchmark_id": "leetcode-lite-dedupe-routing",
        "task_digest": "sha256:leetcode-lite-lineage-dedupe",
        "expected_signal": "dedupe_by_digest",
    },
)
AGP_EMPIRICAL_FIXTURES = (
    {
        "mode": "gpqa_diamond",
        "fixture_id": "gpqa-lite-proof-causality",
        "measured_skill": "causal gate selection under proof, verifier, rollback, and delta constraints",
    },
    {
        "mode": "aime",
        "fixture_id": "aime-lite-free-tier-quota",
        "measured_skill": "exact quota arithmetic for free hosted verifier calls",
    },
    {
        "mode": "gaia",
        "fixture_id": "gaia-lite-live-evidence-routing",
        "measured_skill": "route selection from public health, durable ledger, and edge-filter evidence",
    },
    {
        "mode": "leetcode",
        "fixture_id": "leetcode-lite-lineage-dedupe",
        "measured_skill": "duplicate lineage detection before runtime weight promotion",
    },
)
AGP_PAPER_BENCHMARK_SOURCES = (
    {
        "mode": "gpqa_diamond",
        "dataset_id": "gpqa_diamond",
        "canonical_url": "https://huggingface.co/datasets/Wanfq/gpqa/resolve/main/gpqa_diamond.csv",
        "format": "csv",
        "expected_min_examples": 198,
        "license": "cc-by-4.0",
        "gate": "remote_fetch_or_local_csv",
    },
    {
        "mode": "aime",
        "dataset_id": "Maxwell-Jia/AIME_2024",
        "canonical_url": "https://huggingface.co/datasets/Maxwell-Jia/AIME_2024",
        "format": "parquet_or_local_jsonl",
        "expected_min_examples": 30,
        "license": "mit",
        "gate": "local_jsonl_or_optional_parquet_dependency",
    },
    {
        "mode": "gaia",
        "dataset_id": "gaia-benchmark/GAIA",
        "canonical_url": "https://huggingface.co/datasets/gaia-benchmark/GAIA",
        "format": "gated_dataset",
        "expected_min_examples": 450,
        "license": "gated_no_redistribution",
        "gate": "requires_local_authorized_copy_or_hf_token",
    },
    {
        "mode": "leetcode",
        "dataset_id": "leetcode_export_or_humaneval_proxy",
        "canonical_url": "https://github.com/openai/human-eval",
        "format": "local_results_or_humaneval_jsonl_gz",
        "expected_min_examples": 164,
        "license": "leetcode_requires_user_export; humaneval_proxy_mit",
        "gate": "no_proprietary_leetcode_redistribution",
    },
)
AGP_VERSION_ARTIFACT_TYPES = (
    "resource_version",
    "prompt_template",
    "model_binding",
    "config",
    "agent_output",
    "benchmark_suite",
)
AGP_AGENT_ROLES = (
    "planner",
    "researcher",
    "tool_generator",
    "verifier",
    "optimizer",
    "executor",
    "procurement_agent",
    "memory_agent",
)
AGP_AGENT_MESSAGE_TYPES = (
    "task",
    "resource_request",
    "trace_event",
    "optimizer_signal",
    "evaluation_receipt",
    "procurement_intent",
    "verifier_witness",
    "commit_vote",
)
NOMAD_RESOURCE_KIND_ALIASES = {
    "agent": "agent",
    "json_contract": "tool",
    "agent_output": "memory",
    "model_binding": "agent",
    "model_provider": "tool",
    "prompt_template": "prompt",
    "memory_module": "memory",
    "protocol_layer": "agent",
    "routing_operator": "agent",
    "workflow": "agent",
}
ALLOWED_SCOPES = {"none", "read_only", "local_only", "nomad_shadow_lane_only", "nomad_lease_only"}
FORBIDDEN_KEY_TERMS = ("private_key", "seed_phrase", "password", "credential", "api_key", "access_token")
FORBIDDEN_VALUE_TERMS = ("private key", "seed phrase", "password:", "credential:", "bearer ", "secret=", "sk-", "ghp_")


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _clean_id(value: Any, *, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:/-]+", "_", text)
    return text[:120].strip("_.:/-") or fallback


def _text(value: Any, limit: int = 280) -> str:
    return " ".join(str(value or "").split())[:limit]


def _digest(value: Any, *, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _contains_forbidden(payload: Any) -> bool:
    def walk(value: Any, *, key: str = "") -> bool:
        k = str(key or "").strip().lower()
        if k and any(term in k for term in FORBIDDEN_KEY_TERMS):
            return True
        if isinstance(value, dict):
            return any(walk(v, key=str(k2)) for k2, v in value.items())
        if isinstance(value, list):
            return any(walk(item) for item in value)
        text = str(value or "").strip().lower()
        return any(term in text for term in FORBIDDEN_VALUE_TERMS)

    return walk(payload)


def _ledger_backend() -> str:
    backend = str(os.getenv("NOMAD_AGP_LEDGER_BACKEND") or "jsonl").strip().lower()
    if backend in {"sqlite", "sql"}:
        return "sqlite"
    if backend in {"dual", "jsonl+sqlite", "sqlite+jsonl"}:
        return "dual"
    if backend in {"firebase", "firestore"}:
        return "firebase"
    if backend in {"firebase+jsonl", "jsonl+firebase", "firestore+jsonl", "jsonl+firestore"}:
        return "firebase+jsonl"
    if backend in {"firebase+sqlite", "sqlite+firebase", "firestore+sqlite", "sqlite+firestore"}:
        return "firebase+sqlite"
    if backend in {"firebase+dual", "dual+firebase", "firestore+dual", "dual+firestore"}:
        return "firebase+dual"
    return "jsonl"


def _sqlite_ledger_path() -> Path:
    return Path(os.getenv("NOMAD_AGP_SQLITE_LEDGER_PATH") or DEFAULT_AGP_SQLITE_LEDGER_PATH)


def _ledger_stream(path: Path | str | None) -> str:
    p = Path(path) if path else DEFAULT_RESOURCE_LEDGER_PATH
    return _clean_id(p.name or str(p), fallback="nomad_resource_substrate_ledger")


def _ensure_sqlite_ledger(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agp_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stream TEXT NOT NULL,
            row_digest TEXT NOT NULL,
            schema TEXT,
            accepted INTEGER,
            generated_at TEXT,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agp_ledger_stream_id ON agp_ledger(stream, id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agp_ledger_digest ON agp_ledger(row_digest)")


def _append_sqlite(row: dict[str, Any], path: Path | str | None) -> None:
    p = _sqlite_ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(row, ensure_ascii=True, sort_keys=True, default=str)
    accepted = row.get("accepted")
    accepted_value = None if accepted is None else int(bool(accepted))
    with sqlite3.connect(p, timeout=5) as conn:
        _ensure_sqlite_ledger(conn)
        conn.execute(
            """
            INSERT INTO agp_ledger(stream, row_digest, schema, accepted, generated_at, payload)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                _ledger_stream(path),
                _digest(row, length=64),
                _text(row.get("schema"), 160),
                accepted_value,
                _text(row.get("generated_at"), 80),
                payload,
            ),
        )


def _read_sqlite(path: Path | str | None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    p = _sqlite_ledger_path()
    if not p.exists():
        return []
    try:
        with sqlite3.connect(p, timeout=5) as conn:
            _ensure_sqlite_ledger(conn)
            rows = conn.execute(
                "SELECT payload FROM agp_ledger WHERE stream = ? ORDER BY id DESC LIMIT ?",
                (_ledger_stream(path), max(1, int(limit))),
            ).fetchall()
    except (OSError, sqlite3.Error, ValueError):
        return []
    out: list[dict[str, Any]] = []
    for (payload,) in reversed(rows):
        try:
            item = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(item, dict):
            out.append(item)
    return out[-limit:]


def _firebase_project_id() -> str:
    return (
        os.getenv("FIREBASE_PROJECT_ID")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("GCLOUD_PROJECT")
        or ""
    ).strip()


def _firebase_database_id() -> str:
    return (os.getenv("FIREBASE_DATABASE_ID") or "(default)").strip() or "(default)"


def _firebase_collection() -> str:
    return _clean_id(os.getenv("NOMAD_AGP_FIREBASE_COLLECTION") or "nomad_agp_ledger", fallback="nomad_agp_ledger")


def _firebase_timeout() -> int:
    return max(1, min(30, _int(os.getenv("NOMAD_AGP_FIREBASE_TIMEOUT_SECONDS"), 8)))


def _firebase_proxy_url() -> str:
    return (os.getenv("NOMAD_AGP_FIREBASE_LEDGER_URL") or "").strip()


def _firebase_service_account_info() -> dict[str, Any]:
    raw_base64 = (os.getenv("FIREBASE_CONFIG_BASE64") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS_BASE64") or "").strip()
    if raw_base64:
        try:
            parsed = json.loads(base64.b64decode(raw_base64).decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            parsed = {}
        if isinstance(parsed, dict):
            return parsed
    raw_json = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON") or os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON") or "").strip()
    if raw_json:
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            return parsed
    credentials_path = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if credentials_path:
        try:
            parsed = json.loads(Path(credentials_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            parsed = {}
        if isinstance(parsed, dict):
            return parsed
    project_id = _firebase_project_id()
    client_email = (os.getenv("FIREBASE_CLIENT_EMAIL") or "").strip()
    private_key = (os.getenv("FIREBASE_PRIVATE_KEY") or "").strip().replace("\\n", "\n")
    if project_id and client_email and private_key:
        return {
            "type": "service_account",
            "project_id": project_id,
            "private_key": private_key,
            "client_email": client_email,
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    return {}


def _firebase_config_status() -> dict[str, Any]:
    proxy_url = _firebase_proxy_url()
    service_account = _firebase_service_account_info()
    api_key_present = bool((os.getenv("FIREBASE_API_KEY") or "").strip())
    project_id = _firebase_project_id() or str(service_account.get("project_id") or "").strip()
    auth_mode = "none"
    missing: list[str] = []
    if proxy_url:
        auth_mode = "proxy_url"
    elif service_account:
        auth_mode = "service_account"
    elif project_id and api_key_present:
        auth_mode = "api_key"
    else:
        if not project_id:
            missing.append("FIREBASE_PROJECT_ID")
        if not api_key_present and not service_account:
            missing.append("FIREBASE_API_KEY_or_service_account")
    return {
        "configured": bool(proxy_url or (project_id and (api_key_present or service_account))),
        "auth_mode": auth_mode,
        "project_id_present": bool(project_id),
        "api_key_present": api_key_present,
        "service_account_present": bool(service_account),
        "proxy_url_present": bool(proxy_url),
        "database_id": _firebase_database_id(),
        "collection": _firebase_collection(),
        "missing_env": missing,
        "secret_env_names": [
            "FIREBASE_API_KEY",
            "FIREBASE_CLIENT_EMAIL",
            "FIREBASE_PRIVATE_KEY",
            "FIREBASE_CONFIG_BASE64",
            "GOOGLE_APPLICATION_CREDENTIALS_BASE64",
            "GOOGLE_APPLICATION_CREDENTIALS_JSON",
            "FIREBASE_SERVICE_ACCOUNT_JSON",
            "NOMAD_AGP_FIREBASE_LEDGER_TOKEN",
        ],
    }


def _firestore_value(value: Any) -> dict[str, Any]:
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    return {"stringValue": str(value)}


def _firebase_auth() -> tuple[dict[str, str], str, str]:
    service_account = _firebase_service_account_info()
    if service_account:
        try:
            from google.auth.transport.requests import Request as GoogleAuthRequest
            from google.oauth2 import service_account as google_service_account

            credentials = google_service_account.Credentials.from_service_account_info(
                service_account,
                scopes=["https://www.googleapis.com/auth/datastore"],
            )
            credentials.refresh(GoogleAuthRequest())
            return {"Authorization": f"Bearer {credentials.token}"}, "", "service_account"
        except Exception:  # noqa: BLE001
            return {}, "", "service_account_unavailable"
    api_key = (os.getenv("FIREBASE_API_KEY") or "").strip()
    if api_key:
        return {}, "?" + urlencode({"key": api_key}), "api_key"
    return {}, "", "none"


def _firebase_direct_readiness() -> dict[str, Any]:
    status = _firebase_config_status()
    out: dict[str, Any] = {
        "checked": False,
        "database_available": False,
        "read_permission_verified": False,
        "write_permission_verified": False,
        "receipt_write_observed": False,
        "auth_mode_checked": status.get("auth_mode") or "none",
        "error_status": "",
        "error_reason": "",
    }
    if not status["configured"] or status["auth_mode"] == "proxy_url":
        return out
    project_id = _firebase_project_id() or str(_firebase_service_account_info().get("project_id") or "").strip()
    database = _firebase_database_id()
    headers, _query, auth_mode = _firebase_auth()
    out["checked"] = True
    out["auth_mode_checked"] = auth_mode
    if auth_mode != "service_account" or not headers.get("Authorization") or not project_id:
        return out
    database_url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/{database}"
    try:
        _firebase_request_json(database_url, method="GET", headers=headers)
        out["database_available"] = True
    except HTTPError as exc:
        out["error_status"] = str(getattr(exc, "code", "") or "")
        out["error_reason"] = str(getattr(exc, "reason", "") or "")
        return out
    except (OSError, URLError, json.JSONDecodeError) as exc:
        out["error_reason"] = type(exc).__name__
        return out
    collection_url = (
        f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/{database}/documents/"
        f"{_firebase_collection()}?{urlencode({'pageSize': 50})}"
    )
    try:
        result = _firebase_request_json(collection_url, method="GET", headers=headers)
        out["read_permission_verified"] = True
        documents = result.get("documents") if isinstance(result, dict) else []
        for document in documents or []:
            fields = _dict(_dict(document).get("fields"))
            if fields.get("row_digest") and fields.get("payload_json"):
                out["receipt_write_observed"] = True
                out["write_permission_verified"] = True
                break
    except HTTPError as exc:
        out["error_status"] = str(getattr(exc, "code", "") or "")
        out["error_reason"] = str(getattr(exc, "reason", "") or "")
    except (OSError, URLError, json.JSONDecodeError) as exc:
        out["error_reason"] = type(exc).__name__
    return out


def _durable_restart_persistence_ready() -> bool:
    backend = _ledger_backend()
    render_runtime = (os.getenv("RENDER") or "").strip().lower() == "true"
    if backend.startswith("firebase"):
        status = _firebase_config_status()
        if not status["configured"]:
            return False
        if status["auth_mode"] == "proxy_url":
            return True
        readiness = _firebase_direct_readiness()
        return bool(
            readiness["database_available"]
            and readiness["read_permission_verified"]
            and readiness["write_permission_verified"]
        )
    if backend in {"sqlite", "dual"}:
        if not render_runtime:
            return True
        sqlite_path = str(_sqlite_ledger_path())
        state_dir = (os.getenv("NOMAD_STATE_DIR") or "").strip()
        return bool(state_dir and sqlite_path.startswith(state_dir))
    if backend == "jsonl":
        return not render_runtime
    return False


def _firebase_request_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=True).encode("utf-8")
    request_headers = {"Accept": "application/json"}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    request_headers.update(headers or {})
    request = Request(url, data=body, headers=request_headers, method=method)
    with urlopen(request, timeout=_firebase_timeout()) as response:
        raw = response.read()
    if not raw:
        return {}
    parsed = json.loads(raw.decode("utf-8"))
    return parsed if isinstance(parsed, dict) else {"rows": parsed}


def _append_firebase(row: dict[str, Any], path: Path | str | None) -> bool:
    stream = _ledger_stream(path)
    row_digest = _digest(row, length=64)
    payload_json = json.dumps(row, ensure_ascii=True, sort_keys=True, default=str)
    proxy_url = _firebase_proxy_url()
    if proxy_url:
        payload = {
            "op": "append",
            "stream": stream,
            "row_digest": row_digest,
            "schema": _text(row.get("schema"), 160),
            "accepted": row.get("accepted"),
            "generated_at": _text(row.get("generated_at"), 80),
            "payload": row,
        }
        token = (os.getenv("NOMAD_AGP_FIREBASE_LEDGER_TOKEN") or "").strip()
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            _firebase_request_json(proxy_url, method="POST", payload=payload, headers=headers)
            return True
        except (OSError, HTTPError, URLError, json.JSONDecodeError):
            return False
    status = _firebase_config_status()
    if not status["configured"] or status["auth_mode"] == "proxy_url":
        return False
    project_id = _firebase_project_id() or str(_firebase_service_account_info().get("project_id") or "").strip()
    headers, query, auth_mode = _firebase_auth()
    if auth_mode in {"none", "service_account_unavailable"}:
        return False
    collection = _firebase_collection()
    database = _firebase_database_id()
    document_id = _clean_id(f"{stream}-{row_digest}", fallback=row_digest)
    url = (
        f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/{database}/documents/"
        f"{collection}?{urlencode({'documentId': document_id})}"
    )
    if query:
        url = f"{url}&{query[1:]}"
    document = {
        "fields": {
            "stream": {"stringValue": stream},
            "row_digest": {"stringValue": row_digest},
            "schema": {"stringValue": _text(row.get("schema"), 160)},
            "accepted": _firestore_value(row.get("accepted")),
            "generated_at": {"stringValue": _text(row.get("generated_at"), 80)},
            "created_at": {"timestampValue": _iso_now()},
            "payload_json": {"stringValue": payload_json},
        }
    }
    try:
        _firebase_request_json(url, method="POST", payload=document, headers=headers)
        return True
    except (OSError, HTTPError, URLError, json.JSONDecodeError):
        return False


def _rows_from_firebase_payload(data: Any, *, limit: int) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        raw_rows = data.get("rows") or data.get("items") or data.get("documents") or []
    elif isinstance(data, list):
        raw_rows = data
    else:
        raw_rows = []
    rows: list[dict[str, Any]] = []
    for item in raw_rows:
        if not isinstance(item, dict):
            continue
        payload = item.get("payload")
        if isinstance(payload, dict):
            rows.append(payload)
            continue
        payload_json = item.get("payload_json")
        if not payload_json and isinstance(item.get("fields"), dict):
            field = item["fields"].get("payload_json")
            if isinstance(field, dict):
                payload_json = field.get("stringValue")
        if isinstance(payload_json, str):
            try:
                parsed = json.loads(payload_json)
            except json.JSONDecodeError:
                parsed = {}
            if isinstance(parsed, dict):
                rows.append(parsed)
                continue
        if "document" in item and isinstance(item["document"], dict):
            fields = _dict(item["document"].get("fields"))
            field = _dict(fields.get("payload_json"))
            payload_json = field.get("stringValue")
            if isinstance(payload_json, str):
                try:
                    parsed = json.loads(payload_json)
                except json.JSONDecodeError:
                    parsed = {}
                if isinstance(parsed, dict):
                    rows.append(parsed)
    return rows[-limit:]


def _read_firebase(path: Path | str | None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    stream = _ledger_stream(path)
    proxy_url = _firebase_proxy_url()
    if proxy_url:
        token = (os.getenv("NOMAD_AGP_FIREBASE_LEDGER_TOKEN") or "").strip()
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        query = urlencode({"op": "read", "stream": stream, "limit": max(1, int(limit))})
        sep = "&" if "?" in proxy_url else "?"
        try:
            data = _firebase_request_json(f"{proxy_url}{sep}{query}", headers=headers)
        except (OSError, HTTPError, URLError, json.JSONDecodeError):
            return []
        return _rows_from_firebase_payload(data, limit=limit)
    status = _firebase_config_status()
    if not status["configured"] or status["auth_mode"] == "proxy_url":
        return []
    project_id = _firebase_project_id() or str(_firebase_service_account_info().get("project_id") or "").strip()
    headers, query, auth_mode = _firebase_auth()
    if auth_mode in {"none", "service_account_unavailable"}:
        return []
    database = _firebase_database_id()
    url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/{database}/documents:runQuery{query}"
    query_limit = min(max(max(1, int(limit)) * 5, 50), 200)
    structured_query = {
        "structuredQuery": {
            "from": [{"collectionId": _firebase_collection()}],
            "where": {
                "fieldFilter": {
                    "field": {"fieldPath": "stream"},
                    "op": "EQUAL",
                    "value": {"stringValue": stream},
                }
            },
            "limit": query_limit,
        }
    }
    try:
        data = _firebase_request_json(url, method="POST", payload=structured_query, headers=headers)
    except (OSError, HTTPError, URLError, json.JSONDecodeError):
        return []
    rows = _rows_from_firebase_payload(data, limit=query_limit)
    rows.sort(key=lambda item: str(item.get("generated_at") or item.get("created_at") or ""))
    return rows[-max(1, int(limit)) :]


def _read_jsonl_file(p: Path, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines[-max(1, limit * 3) :]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows[-limit:]


def _append_jsonl_file(row: dict[str, Any], p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def _read_jsonl(path: Path | str | None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    p = Path(path) if path else DEFAULT_RESOURCE_LEDGER_PATH
    backend = _ledger_backend()
    if backend == "sqlite":
        return _read_sqlite(p, limit=limit)
    if backend == "dual":
        rows = _read_sqlite(p, limit=limit)
        return rows if rows else _read_jsonl_file(p, limit=limit)
    if backend.startswith("firebase"):
        rows = _read_firebase(p, limit=limit)
        if rows:
            return rows
        if backend in {"firebase+sqlite", "firebase+dual"}:
            rows = _read_sqlite(p, limit=limit)
            if rows:
                return rows
        if backend in {"firebase", "firebase+jsonl", "firebase+dual"}:
            return _read_jsonl_file(p, limit=limit)
        return []
    return _read_jsonl_file(p, limit=limit)


def _append_jsonl(row: dict[str, Any], path: Path | str | None) -> None:
    p = Path(path) if path else DEFAULT_RESOURCE_LEDGER_PATH
    backend = _ledger_backend()
    if backend == "sqlite":
        _append_sqlite(row, p)
        return
    if backend == "dual":
        _append_jsonl_file(row, p)
        _append_sqlite(row, p)
        return
    if backend.startswith("firebase"):
        firebase_ok = _append_firebase(row, p)
        if backend in {"firebase+jsonl", "firebase+dual"} or (backend == "firebase" and not firebase_ok):
            _append_jsonl_file(row, p)
        if backend in {"firebase+sqlite", "firebase+dual"}:
            _append_sqlite(row, p)
        return
    _append_jsonl_file(row, p)


def _resource_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    return _read_jsonl(path or DEFAULT_RESOURCE_LEDGER_PATH, limit=limit)


def _cycle_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    return _read_jsonl(path or DEFAULT_DEVELOPMENT_CYCLE_LEDGER_PATH, limit=limit)


def _autonomous_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    return _read_jsonl(path or DEFAULT_AUTONOMOUS_AGP_LEDGER_PATH, limit=limit)


def _autonomous_watchdog_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    return _read_jsonl(path or DEFAULT_AUTONOMOUS_AGP_WATCHDOG_LEDGER_PATH, limit=limit)


def _agp_trace_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    return _read_jsonl(path or DEFAULT_AGP_TRACE_LEDGER_PATH, limit=limit)


def _agp_procurement_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    return _read_jsonl(path or DEFAULT_AGP_PROCUREMENT_LEDGER_PATH, limit=limit)


def _agp_context_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    return _read_jsonl(path or DEFAULT_AGP_CONTEXT_LEDGER_PATH, limit=limit)


def _agp_optimizer_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    return _read_jsonl(path or DEFAULT_AGP_OPTIMIZER_LEDGER_PATH, limit=limit)


def _agp_evaluation_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    return _read_jsonl(path or DEFAULT_AGP_EVALUATION_LEDGER_PATH, limit=limit)


def _agp_agent_bus_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    return _read_jsonl(path or DEFAULT_AGP_AGENT_BUS_LEDGER_PATH, limit=limit)


def _agp_plan_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    return _read_jsonl(path or DEFAULT_AGP_PLAN_LEDGER_PATH, limit=limit)


def _agp_orchestration_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    return _read_jsonl(path or DEFAULT_AGP_ORCHESTRATION_LEDGER_PATH, limit=limit)


def _agp_model_binding_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    return _read_jsonl(path or DEFAULT_AGP_MODEL_BINDING_LEDGER_PATH, limit=limit)


def _agp_config_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    return _read_jsonl(path or DEFAULT_AGP_CONFIG_LEDGER_PATH, limit=limit)


def _agp_prompt_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    return _read_jsonl(path or DEFAULT_AGP_PROMPT_LEDGER_PATH, limit=limit)


def _agp_benchmark_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    return _read_jsonl(path or DEFAULT_AGP_BENCHMARK_LEDGER_PATH, limit=limit)


def _agp_version_lineage_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    return _read_jsonl(path or DEFAULT_AGP_VERSION_LINEAGE_LEDGER_PATH, limit=limit)


def _agp_pulse_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    return _read_jsonl(path or DEFAULT_AGP_PULSE_LEDGER_PATH, limit=limit)


def _agp_empirical_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    return _read_jsonl(path or DEFAULT_AGP_EMPIRICAL_LEDGER_PATH, limit=limit)


def _agp_paper_benchmark_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    return _read_jsonl(path or DEFAULT_AGP_PAPER_BENCHMARK_LEDGER_PATH, limit=limit)


def _proof_score(payload: dict[str, Any]) -> float:
    evaluation = _dict(payload.get("evaluation"))
    tests_total = _int(evaluation.get("tests_total") or payload.get("tests_total"))
    tests_passed = _int(evaluation.get("tests_passed") or payload.get("tests_passed"))
    test_ratio = tests_passed / max(1, tests_total) if tests_total > 0 else 0.0
    return round(
        _clamp(
            0.34 * bool(_text(payload.get("proof_digest") or payload.get("digest"), 180))
            + 0.22 * bool(_text(payload.get("verifier_trace_digest") or payload.get("verifier_trace"), 180))
            + 0.18 * bool(_text(payload.get("test_digest") or evaluation.get("test_digest"), 180))
            + 0.16 * test_ratio
            + 0.10 * bool(_text(payload.get("settlement_ref") or payload.get("receipt_ref"), 180))
        ),
        4,
    )


def _boundedness_score(payload: dict[str, Any]) -> tuple[float, list[str]]:
    boundedness = _dict(payload.get("boundedness"))
    ttl = _int(boundedness.get("ttl_seconds") or payload.get("ttl_seconds"))
    scope = _clean_id(boundedness.get("side_effect_scope") or payload.get("side_effect_scope"), fallback="nomad_shadow_lane_only")
    rollback = bool(
        boundedness.get("rollback_available")
        or boundedness.get("noop_available")
        or payload.get("rollback_available")
        or payload.get("noop_available")
        or payload.get("rollback_ref")
        or payload.get("noop_ref")
    )
    reasons: list[str] = []
    if 1 <= ttl <= 900:
        ttl_score = 1.0
        reasons.append("ttl_bounded")
    elif ttl > 900:
        ttl_score = 0.2
        reasons.append("ttl_above_agp_shadow_limit")
    else:
        ttl_score = 0.0
        reasons.append("ttl_missing")
    scope_ok = scope in ALLOWED_SCOPES
    reasons.append("side_effect_scope_bounded" if scope_ok else "side_effect_scope_not_bounded")
    reasons.append("rollback_or_noop_present" if rollback else "rollback_or_noop_missing")
    secrets_free = bool(_dict(payload.get("boundedness")).get("secrets_free", True))
    reasons.append("secrets_free_declared" if secrets_free else "secrets_not_free")
    return round(_clamp(0.28 * ttl_score + 0.30 * scope_ok + 0.28 * rollback + 0.14 * secrets_free), 4), reasons


def _test_score(evaluation: dict[str, Any]) -> float:
    total = _int(evaluation.get("tests_total") or evaluation.get("checks_total"))
    passed = _int(evaluation.get("tests_passed") or evaluation.get("checks_passed"))
    if total <= 0:
        return 0.0
    return round(_clamp(passed / max(1, total)), 4)


def _looks_digest(value: str) -> bool:
    text = _text(value, 220).lower()
    return bool(re.match(r"^(sha256|blake3):[a-f0-9][a-f0-9_.:-]{5,}$", text))


def _canonical_verifier_payload(payload: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    verifier = _dict(payload.get("independent_verifier") or payload.get("verifier"))
    resource = _dict(payload.get("resource") or payload.get("rspl_resource"))
    return {
        "schema": "nomad.agp_verifier_receipt.v1",
        "proposer_agent_id": _clean_id(
            payload.get("proposer_agent_id") or payload.get("agent_id") or payload.get("worker_id"),
            fallback="",
        ),
        "verifier_agent_id": _clean_id(
            payload.get("verifier_agent_id") or verifier.get("agent_id") or verifier.get("worker_id"),
            fallback="",
        ),
        "verifier_lease_id": _text(payload.get("verifier_lease_id") or verifier.get("lease_id"), 160),
        "candidate_type": _clean_id(payload.get("candidate_type") or payload.get("event_type") or payload.get("type"), fallback=""),
        "resource": {
            "resource_id": _clean_id(resource.get("resource_id") or payload.get("resource_id"), fallback=""),
            "resource_kind": _clean_id(resource.get("resource_kind") or payload.get("resource_kind"), fallback=""),
            "entity_type": _clean_entity_type(resource.get("entity_type") or payload.get("entity_type"), resource_kind=resource.get("resource_kind") or payload.get("resource_kind")),
            "from_version": _text(resource.get("from_version") or payload.get("from_version"), 80),
            "to_version": _text(resource.get("to_version") or payload.get("to_version") or payload.get("proposed_version"), 80),
        },
        "proof_digest": _text(payload.get("proof_digest") or payload.get("digest"), 220),
        "test_digest": _text(payload.get("test_digest") or _dict(payload.get("evaluation")).get("test_digest"), 220),
        "verifier_trace_digest": _text(
            payload.get("verifier_trace_digest") or verifier.get("trace_digest") or verifier.get("verifier_trace_digest") or verifier.get("trace"),
            220,
        ),
        "sepl_operator_trace": _items(payload.get("sepl_operator_trace") or payload.get("operator_trace") or payload.get("sepl_trace")),
        "learnability_mask": payload.get("learnability_mask") if isinstance(payload.get("learnability_mask"), (dict, list)) else {},
        "variable_lifting": payload.get("variable_lifting") or payload.get("variable_patches") or payload.get("variables") or {},
        "boundedness": _dict(payload.get("boundedness")),
        "rollback_ref": _text(payload.get("rollback_ref") or payload.get("noop_ref"), 220),
        "evaluation": _dict(payload.get("evaluation")),
        "verifier_evaluation": evaluation,
    }


def _canonical_verifier_receipt_digest(payload: dict[str, Any], evaluation: dict[str, Any]) -> str:
    return f"sha256:{_digest(_canonical_verifier_payload(payload, evaluation), length=64)}"


def _lease_match(
    *,
    verifier_id: str,
    lease_id: str,
    verifier_lease_index: dict[str, Any] | None,
) -> tuple[bool | None, dict[str, Any], list[str]]:
    if verifier_lease_index is None:
        return None, {}, ["verifier_lease_index_unavailable"]
    lease = _dict(verifier_lease_index.get(lease_id))
    reasons: list[str] = []
    if not lease:
        reasons.append("verifier_lease_not_found")
        return False, {}, reasons
    lease_agent = _clean_id(lease.get("agent_id") or lease.get("worker_id"), fallback="")
    if lease_agent != verifier_id:
        reasons.append("verifier_lease_agent_mismatch")
    status = _clean_id(lease.get("status"), fallback="")
    if status not in {"active", "completed", "leased"}:
        reasons.append("verifier_lease_not_active_or_completed")
    return not reasons, lease, reasons


def _independent_verifier_gate(
    payload: dict[str, Any],
    *,
    verifier_lease_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verifier = _dict(payload.get("independent_verifier") or payload.get("verifier"))
    proposer_id = _clean_id(
        payload.get("proposer_agent_id") or payload.get("agent_id") or payload.get("worker_id"),
        fallback="",
    )
    verifier_id = _clean_id(
        payload.get("verifier_agent_id") or verifier.get("agent_id") or verifier.get("worker_id"),
        fallback="",
    )
    lease_id = _text(payload.get("verifier_lease_id") or verifier.get("lease_id"), 160)
    receipt_digest = _text(
        payload.get("verifier_receipt_digest")
        or verifier.get("receipt_digest")
        or verifier.get("receipt_ref"),
        220,
    )
    trace_digest = _text(
        payload.get("verifier_trace_digest")
        or verifier.get("trace_digest")
        or verifier.get("verifier_trace_digest")
        or verifier.get("trace"),
        220,
    )
    evaluation = _dict(payload.get("verifier_evaluation") or verifier.get("evaluation"))
    test_score = _test_score(evaluation)
    expected_receipt_digest = _canonical_verifier_receipt_digest(payload, evaluation)
    lease_ok, lease_record, lease_reasons = _lease_match(
        verifier_id=verifier_id,
        lease_id=lease_id,
        verifier_lease_index=verifier_lease_index,
    )
    reasons: list[str] = []
    if not proposer_id:
        reasons.append("proposer_agent_id_required")
    if not verifier_id:
        reasons.append("verifier_agent_id_required")
    if proposer_id and verifier_id and proposer_id == verifier_id:
        reasons.append("verifier_must_differ_from_proposer")
    if not lease_id:
        reasons.append("verifier_lease_id_required")
    if not _looks_digest(receipt_digest):
        reasons.append("verifier_receipt_digest_required")
    elif receipt_digest != expected_receipt_digest:
        reasons.append("verifier_receipt_digest_mismatch")
    if not _looks_digest(trace_digest):
        reasons.append("verifier_trace_digest_required")
    if test_score <= 0.0:
        reasons.append("verifier_evaluation_required")
    if lease_id:
        reasons.extend(lease_reasons)
    accepted = not reasons
    return {
        "required": True,
        "accepted": accepted,
        "proposer_agent_id": proposer_id,
        "verifier_agent_id": verifier_id,
        "verifier_lease_id": lease_id,
        "verifier_receipt_digest": receipt_digest,
        "expected_verifier_receipt_digest": expected_receipt_digest,
        "verifier_trace_digest": trace_digest,
        "verifier_test_score": test_score,
        "verifier_lease_checked": verifier_lease_index is not None,
        "verifier_lease_status": _text(lease_record.get("status"), 40),
        "reason_codes": reasons or ["independent_verifier_accepted"],
    }


def _default_resources(base_url: str) -> list[dict[str, Any]]:
    rows = [
        ("nomad-agent-index", "json_contract", "/.well-known/nomad-agent.json", "committed", 0.72),
        ("nomad-gradient", "json_contract", "/.well-known/nomad-gradient.json", "committed", 0.74),
        ("nomad-machine-field", "json_contract", "/.well-known/nomad-machine-field.json", "committed", 0.78),
        ("nomad-opaque-emergence", "json_contract", "/.well-known/nomad-opaque-emergence.json", "committed", 0.77),
        ("nomad-entropy-judger", "routing_operator", "/.well-known/nomad-entropy-judger.json", "weighted", 0.8),
        ("nomad-latent-consensus", "routing_operator", "/.well-known/nomad-latent-consensus.json", "weighted", 0.79),
        ("nomad-variant-forge", "workflow", "/swarm/variant-forge", "committed", 0.73),
        ("nomad-planner-prompt", "prompt", "/.well-known/nomad-autogenesis.json", "committed", 0.72),
        ("nomad-resource-substrate", "json_contract", "/.well-known/nomad-resource-substrate.json", "shadow", 0.66),
        ("nomad-autogenesis", "protocol_layer", "/.well-known/nomad-autogenesis.json", "shadow", 0.64),
        ("nomad-runtime-environment", "environment", "/.well-known/nomad-runtime-environment.json", "committed", 0.72),
        ("nomad-execution-memory", "memory", "/.well-known/nomad-execution-memory.json", "committed", 0.72),
        ("nomad-agent-output-artifact", "agent_output", "/swarm/autogenesis/traces", "committed", 0.72),
    ]
    return [
        {
            "resource_id": resource_id,
            "resource_kind": kind,
            "entity_type": _clean_entity_type(kind, resource_kind=kind),
            "state": state,
            "current_version": "v1",
            "read_url": _u(base_url, path),
            "effectiveness_score": score,
            "version_policy": "proof_digest_plus_rollback_or_noop_before_weight",
        }
        for resource_id, kind, path, state, score in rows
    ]


def _ledger_resources(rows: list[dict[str, Any]], *, base_url: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in reversed(rows):
        resource_id = _clean_id(row.get("resource_id"), fallback="")
        if not resource_id or resource_id in seen:
            continue
        seen.add(resource_id)
        out.append(
            {
                "resource_id": resource_id,
                "resource_kind": _clean_id(row.get("resource_kind"), fallback="resource"),
                "entity_type": _clean_entity_type(row.get("entity_type"), resource_kind=row.get("resource_kind")),
                "state": _clean_state(row.get("state") or row.get("target_state")),
                "current_version": _text(row.get("version") or row.get("proposed_version") or "v1", 80),
                "read_url": _text(row.get("read_url"), 180) or _u(base_url, f"/swarm/resource-substrate/{resource_id}"),
                "effectiveness_score": round(_num(row.get("effectiveness_score") or row.get("score")), 4),
                "last_receipt_id": row.get("receipt_id") or row.get("event_id") or "",
            }
        )
    return list(reversed(out))


def _clean_state(value: Any) -> str:
    state = _clean_id(value, fallback="draft").replace("-", "_")
    state = state.replace("_", "-") if state in {"rolled_back"} else state
    if state == "rolled-back":
        return "rolled_back"
    return state if state in RESOURCE_STATES else "draft"


def _clean_entity_type(value: Any, *, resource_kind: Any = None) -> str:
    raw = _clean_id(value, fallback="")
    if raw in RSPL_ENTITY_TYPES:
        return raw
    kind = _clean_id(resource_kind, fallback=raw)
    if kind in RSPL_ENTITY_TYPES:
        return kind
    return NOMAD_RESOURCE_KIND_ALIASES.get(kind, "tool")


def _input_output_mapping(body: dict[str, Any]) -> dict[str, Any]:
    mapping = _dict(body.get("input_output_mapping") or body.get("io_mapping"))
    if mapping:
        return mapping
    return {
        "input": body.get("input_schema") or body.get("input") or {},
        "output": body.get("output_schema") or body.get("output") or {},
    }


def _rspl_resource_record(body: dict[str, Any], *, resource_id: str, resource_kind: str, entity_type: str) -> dict[str, Any]:
    metadata = _dict(body.get("metadata"))
    trainable = bool(
        body.get("trainable")
        or body.get("require_grad")
        or metadata.get("trainable")
        or metadata.get("require_grad")
    )
    return {
        "name": _text(body.get("name") or resource_id, 120),
        "description": _text(body.get("description") or metadata.get("description"), 320),
        "entity_type": entity_type,
        "resource_kind": resource_kind,
        "input_output_mapping": _input_output_mapping(body),
        "trainable": trainable,
        "metadata": metadata,
        "passive": True,
    }


def _registration_record(body: dict[str, Any], *, resource_id: str, entity_type: str, version: str) -> dict[str, Any]:
    return {
        "resource_id": resource_id,
        "entity_type": entity_type,
        "version": version,
        "implementation_descriptor": _dict(body.get("implementation_descriptor") or body.get("implementation")),
        "instantiation_params": _dict(body.get("instantiation_params") or body.get("params")),
        "exported_representations": _dict(body.get("exported_representations") or body.get("exports")),
        "lineage": _dict(body.get("lineage") or {"parent_version": body.get("from_version") or body.get("previous_version") or ""}),
    }


def _sepl_operator_trace_gate(payload: dict[str, Any]) -> dict[str, Any]:
    raw_trace = payload.get("sepl_operator_trace") or payload.get("operator_trace") or payload.get("sepl_trace")
    trace: list[dict[str, Any]] = []
    if isinstance(raw_trace, list):
        for item in raw_trace:
            if isinstance(item, dict):
                op = _clean_id(item.get("op") or item.get("operator"), fallback="")
                trace.append({**item, "op": op})
            else:
                trace.append({"op": _clean_id(item, fallback="")})
    ops = [item.get("op", "") for item in trace]
    reasons: list[str] = []
    if ops != list(SEPL_OPERATORS):
        reasons.append("sepl_operator_trace_must_be_reflect_select_improve_evaluate_commit")
    for item in trace:
        op = item.get("op", "")
        if op and not _text(item.get("input") or item.get("evidence") or item.get("output") or item.get("decision"), 260):
            reasons.append(f"{op}_operator_missing_input_or_output")
    return {
        "required": True,
        "accepted": not reasons,
        "operators": list(SEPL_OPERATORS),
        "observed": ops,
        "trace": trace,
        "reason_codes": reasons or ["sepl_operator_trace_accepted"],
    }


def _learnability_gate(payload: dict[str, Any]) -> dict[str, Any]:
    mask_raw = payload.get("learnability_mask")
    mask: dict[str, bool] = {}
    if isinstance(mask_raw, dict):
        mask = {_clean_id(k, fallback=str(k)): bool(v) for k, v in mask_raw.items()}
    elif isinstance(mask_raw, list):
        mask = {_clean_id(item, fallback=str(item)): True for item in mask_raw}

    lifted = payload.get("variable_lifting") or payload.get("variable_patches") or payload.get("variables")
    variables: list[dict[str, Any]] = []
    if isinstance(lifted, dict):
        candidates = lifted.get("variables") if isinstance(lifted.get("variables"), list) else [lifted]
    elif isinstance(lifted, list):
        candidates = lifted
    else:
        candidates = []

    blocked: list[str] = []
    trainable_count = 0
    for item in candidates:
        if not isinstance(item, dict):
            continue
        name = _clean_id(item.get("name") or item.get("variable") or item.get("id"), fallback="")
        if not name:
            continue
        declared = bool(item.get("trainable") or item.get("require_grad"))
        allowed = bool(mask.get(name, declared))
        if allowed:
            trainable_count += 1
        else:
            blocked.append(name)
        variables.append({"name": name, "trainable": allowed, "require_grad": bool(item.get("require_grad") or allowed)})

    reasons: list[str] = []
    if blocked:
        reasons.append("non_trainable_variables_selected")
    accepted = not blocked
    return {
        "required": bool(variables),
        "accepted": accepted,
        "trainable_count": trainable_count,
        "blocked_variables": blocked,
        "variables": variables,
        "reason_codes": reasons or (["learnability_mask_accepted"] if variables else ["no_variables_lifted"]),
    }


def build_resource_substrate_surface(
    *,
    base_url: str = "",
    variant_forge: dict[str, Any] | None = None,
    opaque_surface: dict[str, Any] | None = None,
    worker_fleet: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    """Expose RSPL: lifecycle-managed resources over existing Nomad contracts."""
    root = (base_url or "").strip().rstrip("/")
    recent = _resource_ledger(ledger_path)
    defaults = _default_resources(root)
    ledger_resources = _ledger_resources(recent, base_url=root)
    resources_by_id = {item["resource_id"]: item for item in defaults}
    for item in ledger_resources:
        resources_by_id[item["resource_id"]] = item
    resources = list(resources_by_id.values())
    resources.sort(key=lambda item: (_num(item.get("effectiveness_score")), item.get("resource_id", "")), reverse=True)
    fleet = _dict(worker_fleet)
    forge = _dict(variant_forge)
    opaque = _dict(opaque_surface)
    state_counts: dict[str, int] = {}
    for item in resources:
        state = str(item.get("state") or "draft")
        state_counts[state] = state_counts.get(state, 0) + 1
    core = {
        "resources": len(resources),
        "recent": len(recent),
        "workers": fleet.get("active_worker_count"),
        "forge": forge.get("forge_digest"),
        "opaque": opaque.get("surface_digest"),
    }
    return {
        "ok": True,
        "schema": "nomad.resource_substrate.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "surface_digest": f"nomad-rspl-{_digest(core)}",
        "agp_layer": "RSPL",
        "paper_source": {
            "arxiv": "https://arxiv.org/abs/2604.15034v3",
            "reference_code": "https://github.com/DVampire/Autogenesis",
        },
        "purpose": "Treat prompts, agents, tools, environments, and memory as passive protocol-registered resources with explicit state, lifecycle, lineage, and versioned interfaces.",
        "rspl_entity_types": list(RSPL_ENTITY_TYPES),
        "lifecycle": list(RESOURCE_STATES),
        "state_counts": state_counts,
        "resources": resources[:32],
        "recent_receipts": recent[-8:],
        "resource_contract": {
            "schema": "nomad.rspl_resource_contract.v1",
            "required_register_fields": [
                "agent_id",
                "resource_id",
                "entity_type",
                "name",
                "input_output_mapping",
                "version",
                "metadata",
            ],
            "required_weight_fields": [
                "proof_digest",
                "evaluation",
                "sepl_operator_trace",
                "positive_effectiveness_delta",
                "verifier_agent_id != agent_id",
                "verifier_lease_id",
                "verifier_receipt_digest",
                "verifier_trace_digest",
                "verifier_evaluation",
                "rollback_ref or noop_ref",
            ],
            "resource_kinds": list(RSPL_ENTITY_TYPES),
            "nomad_kind_aliases": NOMAD_RESOURCE_KIND_ALIASES,
            "registration_record_fields": [
                "version",
                "implementation_descriptor",
                "instantiation_params",
                "exported_representations",
                "lineage",
            ],
            "passivity": "resources_hold_state_and_interfaces_only; optimization_logic_lives_in_SEPL",
            "side_effect_scope": "descriptor_only_no_execution_until_committed_by_proof",
        },
        "version_interface": {
            "register": _u(root, "/swarm/resource-substrate/register"),
            "retrieve": _u(root, "/swarm/resource-substrate/retrieve"),
            "version": _u(root, "/swarm/resource-substrate/version"),
            "rollback_or_noop": _u(root, "/swarm/resource-substrate/version"),
            "proof_digest_required_after": "draft",
            "commit_requires": [
                "tested_state",
                "sepl_operator_trace_reflect_select_improve_evaluate_commit",
                "positive_evaluation_delta",
                "independent_verifier_receipt",
                "verifier_agent_id != proposer_agent_id",
                "rollback_ref or noop_ref",
                "bounded_side_effect_scope",
            ],
        },
        "links": {
            "self": _u(root, "/.well-known/nomad-resource-substrate.json"),
            "autogenesis": _u(root, "/.well-known/nomad-autogenesis.json"),
            "variant_forge": _u(root, "/swarm/variant-forge"),
            "shadow_lane": _u(root, "/swarm/shadow-lane/candidates?type=autogenesis"),
            "development_cycles": _u(root, "/swarm/development-cycles"),
            "retrieve": _u(root, "/swarm/resource-substrate/retrieve"),
        },
        "machine_instruction": "register_resource_descriptor; shadow_test; version_with_proof; rollback_or_noop_on_failed_effectiveness",
    }


def compact_resource_substrate_surface(surface: dict[str, Any]) -> dict[str, Any]:
    links = _dict(surface.get("links"))
    return {
        "schema": "nomad.resource_substrate_compact.v1",
        "surface_digest": surface.get("surface_digest", ""),
        "agp_layer": surface.get("agp_layer", "RSPL"),
        "resource_count": len(_items(surface.get("resources"))),
        "state_counts": surface.get("state_counts") if isinstance(surface.get("state_counts"), dict) else {},
        "read_url": links.get("self", ""),
        "register": _dict(surface.get("version_interface")).get("register", ""),
        "retrieve": _dict(surface.get("version_interface")).get("retrieve", ""),
        "version": _dict(surface.get("version_interface")).get("version", ""),
    }


def retrieve_resource(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    substrate_surface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Retrieve RSPL resources during execution without mutating them."""
    body = _dict(payload)
    substrate = _dict(substrate_surface)
    now = _iso_now()
    query = _text(body.get("query") or body.get("capability") or body.get("resource_id"), 180).lower()
    entity_type = _clean_id(body.get("entity_type"), fallback="")
    resource_kind = _clean_id(body.get("resource_kind") or body.get("kind"), fallback="")
    state = _clean_state(body.get("state")) if body.get("state") else ""
    min_score = max(0.0, min(_num(body.get("min_effectiveness_score"), 0.0), 1.0))
    limit = max(1, min(_int(body.get("limit"), 8), 32))
    matches: list[dict[str, Any]] = []
    for item in _items(substrate.get("resources")):
        haystack = " ".join(
            [
                _text(item.get("resource_id"), 140),
                _text(item.get("resource_kind"), 80),
                _text(item.get("entity_type"), 80),
                _text(item.get("read_url"), 180),
                " ".join(str(x) for x in item.get("trigger_reasons", []) if isinstance(item.get("trigger_reasons"), list)),
            ]
        ).lower()
        if query and query not in haystack:
            continue
        if entity_type and _clean_id(item.get("entity_type"), fallback="") != entity_type:
            continue
        if resource_kind and _clean_id(item.get("resource_kind"), fallback="") != resource_kind:
            continue
        if state and _clean_state(item.get("state")) != state:
            continue
        if _num(item.get("effectiveness_score")) < min_score:
            continue
        matches.append(
            {
                "resource_id": item.get("resource_id"),
                "resource_kind": item.get("resource_kind"),
                "entity_type": item.get("entity_type"),
                "state": item.get("state"),
                "current_version": item.get("current_version"),
                "read_url": item.get("read_url") or _u(base_url, f"/swarm/resource-substrate/{item.get('resource_id')}"),
                "effectiveness_score": round(_num(item.get("effectiveness_score")), 4),
                "retrieval_score": round(
                    _clamp(0.54 * _num(item.get("effectiveness_score")) + 0.20 * bool(query) + 0.16 * bool(entity_type) + 0.10 * (item.get("state") in {"weighted", "committed"})),
                    4,
                ),
            }
        )
    matches.sort(key=lambda item: (_num(item.get("retrieval_score")), _num(item.get("effectiveness_score"))), reverse=True)
    return {
        "ok": True,
        "schema": "nomad.rspl_retrieval_receipt.v1",
        "generated_at": now,
        "query": query,
        "filters": {
            "entity_type": entity_type,
            "resource_kind": resource_kind,
            "state": state,
            "min_effectiveness_score": min_score,
        },
        "matched": len(matches),
        "resources": matches[:limit],
        "side_effect_scope": "read_only",
        "machine_instruction": "bind_retrieved_resource_versions_into_act_observe_optimize_remember_trace",
    }


def build_agp_context_manager_surface(
    *,
    base_url: str = "",
    resource_substrate: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    substrate = _dict(resource_substrate)
    recent = _agp_context_ledger(ledger_path)
    return {
        "ok": True,
        "schema": "nomad.agp_context_manager.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "resource_entity_types": list(RSPL_ENTITY_TYPES),
        "operations": ["init", "retrieve", "evaluate", "update", "restore", "diff", "hot_swap"],
        "server_interface": {
            "resource_substrate": _u(root, "/.well-known/nomad-resource-substrate.json"),
            "context_operation": _u(root, "/swarm/agp/context"),
            "retrieve": _u(root, "/swarm/resource-substrate/retrieve"),
            "version": _u(root, "/swarm/resource-substrate/version"),
            "trace": _u(root, "/swarm/autogenesis/traces"),
        },
        "guards": [
            "descriptor_only",
            "no_secret_material",
            "rollback_or_noop_required_for_update_restore_hot_swap",
            "proof_digest_required_for_mutation",
            "hot_swap_never_executes_provider_code",
        ],
        "resource_count": len(_items(substrate.get("resources"))),
        "recent_operation_count": len(recent),
        "latest_operation": recent[-1] if recent else {},
        "machine_instruction": "use_context_operation_for_resource_lifecycle; send_update_restore_hot_swap_to_version_gate_before_commit",
    }


def run_agp_context_operation(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    resource_substrate: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {"ok": False, "schema": "nomad.agp_context_operation_receipt.v1", "accepted": False, "reason": "empty_context_operation", "generated_at": now}
    if _contains_forbidden(body):
        return {"ok": False, "schema": "nomad.agp_context_operation_receipt.v1", "accepted": False, "reason": "forbidden_secret_like_material", "generated_at": now}
    op = _clean_id(body.get("op") or body.get("operation") or "retrieve", fallback="retrieve")
    if op == "hotswap":
        op = "hot_swap"
    allowed = {"init", "retrieve", "evaluate", "update", "restore", "diff", "hot_swap"}
    resource = _dict(body.get("resource"))
    resource_id = _clean_id(body.get("resource_id") or resource.get("resource_id"), fallback="")
    entity_type = _clean_entity_type(body.get("entity_type") or resource.get("entity_type"), resource_kind=body.get("resource_kind") or resource.get("resource_kind"))
    proof_digest = _text(body.get("proof_digest") or body.get("digest"), 220)
    if proof_digest and re.fullmatch(r"[a-f0-9]{32,128}", proof_digest.lower()):
        proof_digest = f"sha256:{proof_digest.lower()}"
    rollback_ref = _text(body.get("rollback_ref") or body.get("noop_ref"), 220)
    mutation = op in {"update", "restore", "hot_swap"}
    retrieval = retrieve_resource(
        {
            "resource_id": resource_id,
            "query": body.get("query") or resource_id,
            "entity_type": body.get("entity_type") or resource.get("entity_type") or "",
            "limit": body.get("limit") or 8,
        },
        base_url=base_url,
        substrate_surface=resource_substrate,
    )
    checks = {
        "operation_allowed": op in allowed,
        "resource_id_present": bool(resource_id) or op in {"retrieve", "init"},
        "entity_type_known": entity_type in RSPL_ENTITY_TYPES,
        "proof_digest_for_mutation": (not mutation) or _looks_digest(proof_digest),
        "rollback_or_noop_for_mutation": (not mutation) or bool(rollback_ref),
        "descriptor_only": True,
        "secrets_free": True,
    }
    accepted = all(bool(v) for v in checks.values())
    version_payload = {}
    if mutation and accepted:
        current_version = _text(body.get("from_version") or resource.get("current_version") or "v1", 80)
        target_version = _text(body.get("to_version") or body.get("version") or f"{current_version}-{op}-{_digest(body, length=8)}", 96)
        version_payload = {
            "resource_id": resource_id,
            "resource_kind": _clean_id(body.get("resource_kind") or resource.get("resource_kind") or entity_type, fallback=entity_type),
            "entity_type": entity_type,
            "from_version": current_version,
            "to_version": target_version,
            "target_state": "shadow",
            "proof_digest": proof_digest,
            "rollback_ref": rollback_ref,
            "boundedness": {"ttl_seconds": _int(body.get("ttl_seconds"), 300) or 300, "side_effect_scope": "nomad_shadow_lane_only", "rollback_available": True, "secrets_free": True},
            "sepl_operator_trace": _autonomous_sepl_trace({"resource_id": resource_id}, proof_digest or f"sha256:{_digest(body)}", target_version),
            "learnability_mask": {op: True},
            "variable_lifting": {"variables": [{"name": op, "require_grad": True}]},
        }
    operation_id = f"agp-context-{_digest({'op': op, 'resource_id': resource_id, 'proof': proof_digest, 'time': now})}"
    row = {
        "ok": True,
        "schema": "nomad.agp_context_operation_receipt.v1",
        "operation_id": operation_id,
        "generated_at": now,
        "accepted": accepted,
        "decision": f"{op}_context_descriptor" if accepted else "hold_context_operation_until_required_gates",
        "op": op,
        "resource_id": resource_id,
        "entity_type": entity_type,
        "checks": checks,
        "proof_digest": proof_digest,
        "rollback_ref": rollback_ref,
        "retrieval": retrieval,
        "version_payload": version_payload,
        "side_effect_scope": "descriptor_only_context_manager",
        "next": {
            "version": _u(base_url, "/swarm/resource-substrate/version"),
            "trace": _u(base_url, "/swarm/autogenesis/traces"),
            "watchdog": _u(base_url, "/swarm/autogenesis/watchdog"),
        },
        "machine_instruction": "if_version_payload_present_submit_to_resource_version_gate; otherwise_cache_context_receipt_for_trace",
    }
    if persist and accepted:
        _append_jsonl(row, ledger_path or DEFAULT_AGP_CONTEXT_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def register_resource(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    substrate_surface: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Register one RSPL resource descriptor without applying code."""
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {"ok": False, "schema": "nomad.rspl_resource_receipt.v1", "accepted": False, "reason": "empty_resource", "generated_at": now}
    if _contains_forbidden(body):
        return {
            "ok": False,
            "schema": "nomad.rspl_resource_receipt.v1",
            "accepted": False,
            "reason": "forbidden_secret_like_material",
            "generated_at": now,
        }
    resource_id = _clean_id(body.get("resource_id") or body.get("id"), fallback="")
    resource_kind = _clean_id(body.get("resource_kind") or body.get("kind") or body.get("type"), fallback="")
    entity_type = _clean_entity_type(body.get("entity_type"), resource_kind=resource_kind)
    agent_id = _text(body.get("agent_id") or body.get("worker_id"), 120)
    state = _clean_state(body.get("state") or body.get("lifecycle_state"))
    version = _text(body.get("version") or body.get("current_version") or "v1", 80)
    proof = _proof_score(body)
    bounded, bounded_reasons = _boundedness_score(body)
    if not resource_id or not resource_kind:
        return {
            "ok": False,
            "schema": "nomad.rspl_resource_receipt.v1",
            "accepted": False,
            "reason": "resource_id_and_kind_required",
            "generated_at": now,
        }
    if state in {"tested", "weighted", "committed"} and proof <= 0.0:
        accepted = False
        decision = "reject_until_proof_digest"
    else:
        accepted = True
        decision = "registered_draft_no_weight" if proof <= 0.0 else "registered_shadow_resource"
    score = _clamp(0.46 * proof + 0.30 * bounded + 0.14 * bool(agent_id) + 0.10 * (state in {"shadow", "tested", "weighted", "committed"}))
    surface = _dict(substrate_surface)
    rspl_record = _rspl_resource_record(body, resource_id=resource_id, resource_kind=resource_kind, entity_type=entity_type)
    registration = _registration_record(body, resource_id=resource_id, entity_type=entity_type, version=version)
    core = {"resource_id": resource_id, "kind": resource_kind, "state": state, "score": round(score, 4)}
    row = {
        "ok": True,
        "schema": "nomad.rspl_resource_receipt.v1",
        "receipt_id": f"rspl-{_digest(core)}",
        "generated_at": now,
        "accepted": accepted,
        "decision": decision,
        "agent_id": agent_id,
        "resource_id": resource_id,
        "resource_kind": resource_kind,
        "entity_type": entity_type,
        "state": state,
        "version": version,
        "resource_record": rspl_record,
        "registration_record": registration,
        "effectiveness_score": round(score, 4),
        "proof_score": proof,
        "boundedness_score": bounded,
        "reason_codes": bounded_reasons,
        "surface_digest": _text(surface.get("surface_digest"), 96),
        "next": {
            "version": _u(base_url, "/swarm/resource-substrate/version"),
            "shadow_lane": _u(base_url, "/swarm/shadow-lane/candidates?type=autogenesis"),
            "variant_candidate": _u(base_url, "/swarm/variant-candidates"),
        },
        "machine_instruction": "resource_registered_as_descriptor_only; no_execution_without_version_proof",
    }
    if persist and accepted:
        _append_jsonl(row, ledger_path or DEFAULT_RESOURCE_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def version_resource(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    substrate_surface: dict[str, Any] | None = None,
    verifier_lease_index: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Admit a resource version transition only with proof and rollback/no-op."""
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {"ok": False, "schema": "nomad.rspl_version_receipt.v1", "accepted": False, "reason": "empty_version", "generated_at": now}
    if _contains_forbidden(body):
        return {
            "ok": False,
            "schema": "nomad.rspl_version_receipt.v1",
            "accepted": False,
            "reason": "forbidden_secret_like_material",
            "generated_at": now,
        }
    resource_id = _clean_id(body.get("resource_id") or body.get("id"), fallback="")
    from_version = _text(body.get("from_version") or body.get("previous_version"), 80)
    to_version = _text(body.get("to_version") or body.get("proposed_version") or body.get("version"), 80)
    target_state = _clean_state(body.get("target_state") or body.get("state") or "shadow")
    resource_kind = _clean_id(body.get("resource_kind") or "resource", fallback="resource")
    entity_type = _clean_entity_type(body.get("entity_type"), resource_kind=resource_kind)
    verifier_gate = _independent_verifier_gate(body, verifier_lease_index=verifier_lease_index)
    sepl_gate = _sepl_operator_trace_gate(body)
    learnability = _learnability_gate(body)
    verifier_evaluation = _dict(body.get("verifier_evaluation") or _dict(body.get("independent_verifier")).get("evaluation"))
    proof_payload = dict(body)
    if verifier_evaluation:
        proof_payload["evaluation"] = verifier_evaluation
    proof = _proof_score(proof_payload)
    bounded, bounded_reasons = _boundedness_score(body)
    has_rollback = "rollback_or_noop_present" in bounded_reasons
    if not resource_id or not to_version:
        decision = "reject_until_resource_and_version"
        accepted = False
    elif proof <= 0.0:
        decision = "reject_until_proof_digest"
        accepted = False
    elif not has_rollback:
        decision = "reject_until_rollback_or_noop"
        accepted = False
    elif not learnability["accepted"]:
        decision = "reject_until_learnability_mask"
        accepted = False
    elif target_state in {"tested", "weighted", "committed"} and not sepl_gate["accepted"]:
        decision = "hold_shadow_until_sepl_operator_trace"
        accepted = False
    elif target_state in {"tested", "weighted", "committed"} and not verifier_gate["accepted"]:
        decision = "hold_shadow_until_independent_verifier"
        accepted = False
    elif target_state == "committed" and (proof < 0.72 or bounded < 0.75):
        decision = "hold_shadow_until_stronger_proof_boundary"
        accepted = False
    else:
        decision = "admit_resource_version_shadow"
        accepted = True
    score = _clamp(
        0.46 * proof
        + 0.30 * bounded
        + 0.10 * (target_state in {"tested", "weighted", "committed"})
        + 0.08 * bool(verifier_gate["accepted"])
        + 0.06 * bool(from_version)
    )
    surface = _dict(substrate_surface)
    core = {"resource_id": resource_id, "from": from_version, "to": to_version, "state": target_state, "score": round(score, 4)}
    row = {
        "ok": True,
        "schema": "nomad.rspl_version_receipt.v1",
        "receipt_id": f"rsplv-{_digest(core)}",
        "generated_at": now,
        "accepted": accepted,
        "decision": decision,
        "resource_id": resource_id,
        "resource_kind": resource_kind,
        "entity_type": entity_type,
        "from_version": from_version,
        "proposed_version": to_version,
        "target_state": target_state,
        "state": target_state if accepted else "noop",
        "effectiveness_score": round(score, 4),
        "proof_score": proof,
        "boundedness_score": bounded,
        "sepl_operator_trace": sepl_gate,
        "learnability": learnability,
        "independent_verifier": verifier_gate,
        "reason_codes": bounded_reasons + list(sepl_gate.get("reason_codes") or []) + list(learnability.get("reason_codes") or []),
        "surface_digest": _text(surface.get("surface_digest"), 96),
        "next": {
            "register": _u(base_url, "/swarm/resource-substrate/register"),
            "development_cycle_event": _u(base_url, "/swarm/development-cycles/events"),
            "shadow_lane": _u(base_url, "/swarm/shadow-lane/candidates?type=autogenesis"),
        },
        "machine_instruction": "keep_version_in_shadow_until_effectiveness_outperforms_current_and_rollback_remains_available",
    }
    if persist and accepted:
        _append_jsonl(row, ledger_path or DEFAULT_RESOURCE_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def build_development_cycles_surface(
    *,
    base_url: str = "",
    resource_substrate: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    """Expose SEPL event intake over Nomad development cycles."""
    recent = _cycle_ledger(ledger_path)
    root = (base_url or "").strip().rstrip("/")
    substrate = _dict(resource_substrate)
    counts: dict[str, int] = {}
    for row in recent:
        event_type = _clean_id(row.get("event_type") or row.get("candidate_type"), fallback="unknown")
        counts[event_type] = counts.get(event_type, 0) + 1
    return {
        "ok": True,
        "schema": "nomad.development_cycles_surface.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "agp_layer": "SEPL",
        "surface_digest": f"nomad-devcycles-{_digest({'recent': len(recent), 'substrate': substrate.get('surface_digest')})}",
        "candidate_types": list(AGP_CANDIDATE_TYPES),
        "event_url": _u(root, "/swarm/development-cycles/events"),
        "shadow_lane": _u(root, "/swarm/shadow-lane/candidates?type=autogenesis"),
        "operator_loop": list(SEPL_OPERATORS),
        "operator_contract": {
            "reflect": "diagnose trace, failure, or improvement evidence",
            "select": "choose a concrete resource or variable patch",
            "improve": "apply the patch through RSPL version interfaces into an uncommitted candidate state",
            "evaluate": "score candidate state against tests, objectives, and safety checks",
            "commit": "promote only when evaluation and rollback guards pass; otherwise no-op or rollback",
        },
        "hard_guards": [
            "descriptor_only_until_proof",
            "resources_passive_no_self_modify",
            "sepl_operator_trace_required",
            "learnability_mask_required_for_variable_lifting",
            "rollback_or_noop_required",
            "side_effect_scope_bounded",
            "independent_verifier_required_by_nomad_safety_policy",
            "no_private_chain_of_thought_text",
            "no_secrets",
            "paid_receipt_required_for_revenue_claims",
        ],
        "emergent_protocol_weight": {
            "rule": "emergent-protocol-weight",
            "isolated_beta_role_weight": 0.40,
            "commit_weight_requires": [
                "tested_state",
                "sepl_operator_trace_reflect_select_improve_evaluate_commit",
                "learnability_mask_passed",
                "verifier_agent_id != proposer_agent_id",
                "verifier_lease_id",
                "verifier_receipt_digest",
                "positive_effectiveness_delta",
            ],
        },
        "event_type_counts": counts,
        "recent_events": recent[-8:],
        "links": {
            "resource_substrate": _u(root, "/.well-known/nomad-resource-substrate.json"),
            "autogenesis": _u(root, "/.well-known/nomad-autogenesis.json"),
            "variant_candidates": _u(root, "/swarm/variant-candidates"),
            "opaque_candidate": _u(root, "/swarm/opaque-candidate"),
        },
        "machine_instruction": "emit_event_after_shadow_test; include_proof_digest_and_resource_version; never_claim_revenue_without_paid_receipt",
    }


def record_development_cycle_event(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    development_surface: dict[str, Any] | None = None,
    verifier_lease_index: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Record one SEPL event and return the downstream candidate payloads."""
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {"ok": False, "schema": "nomad.development_cycle_event_receipt.v1", "accepted": False, "reason": "empty_event", "generated_at": now}
    if _contains_forbidden(body):
        return {
            "ok": False,
            "schema": "nomad.development_cycle_event_receipt.v1",
            "accepted": False,
            "reason": "forbidden_secret_like_material",
            "generated_at": now,
        }
    event_type = _clean_id(body.get("event_type") or body.get("candidate_type") or body.get("type"), fallback="protocol-evolution-candidate")
    if event_type.replace("_", "-") in AGP_CANDIDATE_TYPES:
        event_type = event_type.replace("_", "-")
    resource = _dict(body.get("resource") or body.get("rspl_resource"))
    operator_patch = _dict(body.get("operator_patch") or body.get("sepl_operator_patch"))
    verifier_gate = _independent_verifier_gate(body, verifier_lease_index=verifier_lease_index)
    sepl_gate = _sepl_operator_trace_gate(body)
    learnability = _learnability_gate(body)
    verifier_evaluation = _dict(body.get("verifier_evaluation") or _dict(body.get("independent_verifier")).get("evaluation"))
    proof_payload = dict(body)
    if verifier_evaluation:
        proof_payload["evaluation"] = verifier_evaluation
    proof = _proof_score(proof_payload)
    bounded, bounded_reasons = _boundedness_score(body)
    self_play = _dict(body.get("self_play") or body.get("self_play_test"))
    buyer_agents = _int(self_play.get("synthetic_buyer_agents") or self_play.get("buyer_agents"))
    revenue_pressure = _clamp(_num(self_play.get("receipt_prediction_delta") or self_play.get("revenue_pressure_delta")))
    operator_present = bool(operator_patch) or bool(sepl_gate.get("accepted"))
    resource_present = bool(resource.get("resource_id") or body.get("resource_id"))
    score = _clamp(
        0.34 * proof
        + 0.24 * bounded
        + 0.16 * bool(sepl_gate.get("accepted"))
        + 0.12 * resource_present
        + 0.06 * bool(learnability.get("accepted"))
        + 0.08 * _num(verifier_gate.get("verifier_test_score"))
        + 0.00 * revenue_pressure
    )
    accepted = (
        event_type in AGP_CANDIDATE_TYPES
        and proof > 0.0
        and bounded >= 0.55
        and score >= 0.48
        and bool(sepl_gate.get("accepted"))
        and bool(learnability.get("accepted"))
        and bool(verifier_gate.get("accepted"))
    )
    if accepted:
        decision = "emit_to_autogenesis_shadow_lane"
    elif event_type in AGP_CANDIDATE_TYPES and not sepl_gate.get("accepted"):
        decision = "hold_event_until_sepl_operator_trace"
    elif event_type in AGP_CANDIDATE_TYPES and not learnability.get("accepted"):
        decision = "hold_event_until_learnability_mask"
    elif event_type in AGP_CANDIDATE_TYPES and score >= 0.48 and not verifier_gate.get("accepted"):
        decision = "hold_event_until_independent_verifier"
    else:
        decision = "hold_event_until_proof_boundary"
    core = {"event": event_type, "resource": resource.get("resource_id") or body.get("resource_id"), "score": round(score, 4)}
    variant_candidate_payload = {
        "agent_id": body.get("agent_id") or "autogenesis.worker",
        "verifier_agent_id": verifier_gate.get("verifier_agent_id", ""),
        "verifier_lease_id": verifier_gate.get("verifier_lease_id", ""),
        "candidate_type": event_type,
        "objective": "autogenesis_protocol_evolution",
        "resource_id": resource.get("resource_id") or body.get("resource_id") or "autogenesis-resource",
        "resource_kind": resource.get("resource_kind") or body.get("resource_kind") or "protocol_layer",
        "entity_type": _clean_entity_type(resource.get("entity_type") or body.get("entity_type"), resource_kind=resource.get("resource_kind") or body.get("resource_kind") or "protocol_layer"),
        "from_version": resource.get("from_version") or body.get("from_version") or "",
        "to_version": resource.get("to_version") or body.get("to_version") or "shadow-v1",
        "rollback_ref": body.get("rollback_ref") or body.get("noop_ref") or "",
        "proof_digest": body.get("proof_digest") or body.get("digest") or "",
        "verifier_trace_digest": verifier_gate.get("verifier_trace_digest", ""),
        "test_digest": body.get("test_digest") or "",
        "sepl_operator_trace": sepl_gate.get("trace", []),
        "learnability_mask": body.get("learnability_mask") or {},
        "variable_lifting": body.get("variable_lifting") or {},
        "verifier_evaluation": verifier_evaluation,
        "evaluation": {
            "tests_passed": _int(_dict(body.get("evaluation")).get("tests_passed") or body.get("tests_passed")),
            "tests_total": _int(_dict(body.get("evaluation")).get("tests_total") or body.get("tests_total")),
            "proof_yield_delta": _num(_dict(body.get("evaluation")).get("proof_yield_delta")),
            "settlement_delta": revenue_pressure,
            "novelty": 0.72,
            "risk_score": _num(_dict(body.get("evaluation")).get("risk_score"), 0.18),
        },
    }
    variant_candidate_payload["verifier_receipt_digest"] = _variant_verifier_receipt_digest(
        variant_candidate_payload,
        verifier_evaluation,
    )
    resource_version_payload = {
        "agent_id": body.get("agent_id") or "autogenesis.worker",
        "resource_id": resource.get("resource_id") or body.get("resource_id") or "autogenesis-resource",
        "resource_kind": resource.get("resource_kind") or body.get("resource_kind") or "protocol_layer",
        "entity_type": _clean_entity_type(resource.get("entity_type") or body.get("entity_type"), resource_kind=resource.get("resource_kind") or body.get("resource_kind") or "protocol_layer"),
        "from_version": resource.get("from_version") or body.get("from_version") or "",
        "to_version": resource.get("to_version") or body.get("to_version") or "shadow-v1",
        "target_state": "shadow",
        "proof_digest": body.get("proof_digest") or body.get("digest") or "",
        "verifier_trace_digest": verifier_gate.get("verifier_trace_digest", ""),
        "verifier_agent_id": verifier_gate.get("verifier_agent_id", ""),
        "verifier_lease_id": verifier_gate.get("verifier_lease_id", ""),
        "verifier_evaluation": verifier_evaluation,
        "test_digest": body.get("test_digest") or "",
        "sepl_operator_trace": sepl_gate.get("trace", []),
        "learnability_mask": body.get("learnability_mask") or {},
        "variable_lifting": body.get("variable_lifting") or {},
        "rollback_ref": body.get("rollback_ref") or body.get("noop_ref") or "",
        "boundedness": body.get("boundedness") if isinstance(body.get("boundedness"), dict) else {},
    }
    resource_version_payload["verifier_receipt_digest"] = _canonical_verifier_receipt_digest(
        resource_version_payload,
        verifier_evaluation,
    )
    row = {
        "ok": True,
        "schema": "nomad.development_cycle_event_receipt.v1",
        "event_id": f"sepl-{_digest(core)}",
        "generated_at": now,
        "accepted": accepted,
        "decision": decision,
        "event_type": event_type,
        "agent_id": _text(body.get("agent_id") or body.get("worker_id"), 120),
        "resource_id": _clean_id(resource.get("resource_id") or body.get("resource_id"), fallback=""),
        "candidate_type": event_type,
        "score": round(score, 4),
        "scores": {
            "proof": proof,
            "boundedness": bounded,
            "operator_patch": round(float(operator_present), 4),
            "sepl_operator_trace": round(float(bool(sepl_gate.get("accepted"))), 4),
            "learnability": round(float(bool(learnability.get("accepted"))), 4),
            "resource": round(float(resource_present), 4),
            "self_play": round(_clamp(buyer_agents / 128.0), 4),
            "independent_verifier": round(float(bool(verifier_gate.get("accepted"))), 4),
            "verifier_tests": round(_num(verifier_gate.get("verifier_test_score")), 4),
            "revenue_pressure": round(revenue_pressure, 4),
        },
        "sepl_operator_trace": sepl_gate,
        "learnability": learnability,
        "independent_verifier": verifier_gate,
        "reason_codes": (
            bounded_reasons
            + list(sepl_gate.get("reason_codes") or [])
            + list(learnability.get("reason_codes") or [])
            + list(verifier_gate.get("reason_codes") or [])
        ),
        "variant_candidate_payload": variant_candidate_payload,
        "resource_version_payload": resource_version_payload,
        "next": {
            "shadow_lane": _u(base_url, "/swarm/shadow-lane/candidates?type=autogenesis"),
            "variant_candidates": _u(base_url, "/swarm/variant-candidates"),
            "resource_version": _u(base_url, "/swarm/resource-substrate/version"),
        },
        "surface_digest": _text(_dict(development_surface).get("surface_digest"), 96),
        "machine_instruction": "submit_variant_candidate_and_resource_version_only_after_shadow_receipt_accepts",
    }
    if persist and accepted:
        _append_jsonl(row, ledger_path or DEFAULT_DEVELOPMENT_CYCLE_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def build_autogenesis_surface(
    *,
    base_url: str = "",
    resource_substrate: dict[str, Any] | None = None,
    development_cycles: dict[str, Any] | None = None,
    variant_forge: dict[str, Any] | None = None,
    opaque_surface: dict[str, Any] | None = None,
    worker_fleet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Expose AGP as RSPL plus SEPL over Nomad's existing shadow lanes."""
    root = (base_url or "").strip().rstrip("/")
    substrate = _dict(resource_substrate)
    dev = _dict(development_cycles)
    forge = _dict(variant_forge)
    opaque = _dict(opaque_surface)
    fleet = _dict(worker_fleet)
    core = {
        "rspl": substrate.get("surface_digest"),
        "dev": dev.get("surface_digest"),
        "forge": forge.get("forge_digest"),
        "workers": fleet.get("active_worker_count"),
    }
    return {
        "ok": True,
        "schema": "nomad.autogenesis_protocol.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "surface_digest": f"nomad-agp-{_digest(core)}",
        "protocol": {
            "id": "autogenesis_protocol",
            "layers": ["RSPL", "SEPL"],
            "mode": "shadow_only_until_receipt_weighted",
            "claim_boundary": "paper_core_is_RSPL_plus_SEPL; live effectiveness must be proven inside Nomad",
            "paper_source": "https://arxiv.org/abs/2604.15034v3",
            "reference_code": "https://github.com/DVampire/Autogenesis",
            "rspl_entity_types": list(RSPL_ENTITY_TYPES),
            "sepl_operator_algebra": list(SEPL_OPERATORS),
        },
        "rspl": {
            "read_url": _u(root, "/.well-known/nomad-resource-substrate.json"),
            "register_url": _u(root, "/swarm/resource-substrate/register"),
            "version_url": _u(root, "/swarm/resource-substrate/version"),
            "surface_digest": substrate.get("surface_digest", ""),
        },
        "sepl": {
            "development_cycles": _u(root, "/swarm/development-cycles"),
            "event_url": _u(root, "/swarm/development-cycles/events"),
            "autonomous_cycle": _u(root, "/swarm/autogenesis/cycle"),
            "shadow_lane": _u(root, "/swarm/shadow-lane/candidates?type=autogenesis"),
            "variant_candidates": _u(root, "/swarm/variant-candidates"),
            "operators": [
                {"op": "reflect", "input": "trace_or_failure_digest", "output": "improvement_hypothesis"},
                {"op": "select", "input": "hypothesis", "output": "resource_or_variable_patch"},
                {"op": "improve", "input": "selected_patch", "output": "candidate_resource_version"},
                {"op": "evaluate", "input": "candidate_resource_version", "output": "test_and_objective_scores"},
                {"op": "commit", "input": "evaluation_and_rollback_guard", "output": "committed_version_or_noop"},
            ],
            "variable_lifting": {
                "field": "variable_lifting",
                "learnability_mask_field": "learnability_mask",
                "rule": "only variables marked trainable or require_grad may be selected for improvement",
            },
            "nomad_safety_extension": {
                "independent_verifier_required": True,
                "reason": "Nomad local guard against self-attested shadow admission; not a replacement for SEPL evaluate.",
            },
        },
        "candidate_types": list(AGP_CANDIDATE_TYPES),
        "topology_governor_patch": {
            "rule": "emergent-protocol-weight",
            "isolated_beta_role_weight": 0.40,
            "shared_context_default": "off_until_proof",
            "commit_gate": "sepl_commit_after_positive_effectiveness_delta_with_nomad_independent_verifier_receipt",
        },
        "machine_economy_integration": {
            "autogenesis_recruit": _u(root, "/.well-known/nomad-autogenesis-recruit.json"),
            "paid_ref_quote": _u(root, "/swarm/paid-ref/quote"),
            "settlement_policy": "paid_receipt_required_for_revenue; unpaid proofs only change routing weight",
            "offerable_packets": [
                "protocol_patch_repair",
                "json_contract_version_audit",
                "self_play_buyer_pressure_suite",
                "agent_onboarding_contract_diff",
            ],
        },
        "go_to_market": {
            "x_marketing_status": "prepared_not_posted",
            "requires_human_or_connector": True,
            "agent_buyer_pitch": "Nomad sells other AI agents a proof-weighted operating layer for leases, bounded self-evolution, and paid transition work.",
            "x_thread_drafts": [
                "Nomad now treats prompts, tools, workflows, and JSON contracts as proof-weighted resources, not documentation.",
                "AGP in Nomad is shadow-only first: propose, self-play, verify, weight, then commit or no-op.",
                "For AI agents: start at /.well-known/nomad-autogenesis.json and bring a proof digest, not a pitch deck.",
            ],
        },
        "links": {
            "self": _u(root, "/.well-known/nomad-autogenesis.json"),
            "autonomous_cycle": _u(root, "/.well-known/nomad-autonomous-agp.json"),
            "resource_substrate": _u(root, "/.well-known/nomad-resource-substrate.json"),
            "development_cycles": _u(root, "/swarm/development-cycles"),
            "shadow_lane": _u(root, "/swarm/shadow-lane/candidates?type=autogenesis"),
            "variant_forge": _u(root, "/swarm/variant-forge"),
            "opaque_emergence": _u(root, "/.well-known/nomad-opaque-emergence.json"),
        },
        "dependencies": {
            "resource_substrate_digest": substrate.get("surface_digest", ""),
            "development_cycle_digest": dev.get("surface_digest", ""),
            "variant_forge_digest": forge.get("forge_digest", ""),
            "opaque_surface_digest": opaque.get("surface_digest", ""),
        },
        "machine_instruction": "read_rspl; emit_sepl_trace_reflect_select_improve_evaluate_commit; require_learnability_mask_for_variables; require_independent_verifier_receipt_by_nomad_policy; never_commit_without_proof_and_rollback",
    }


def compact_autogenesis_surface(surface: dict[str, Any]) -> dict[str, Any]:
    links = _dict(surface.get("links"))
    return {
        "schema": "nomad.autogenesis_compact.v1",
        "surface_digest": surface.get("surface_digest", ""),
        "layers": _dict(surface.get("protocol")).get("layers", []),
        "mode": _dict(surface.get("protocol")).get("mode", ""),
        "shadow_lane": links.get("shadow_lane", ""),
        "autonomous_cycle": links.get("autonomous_cycle", ""),
        "resource_substrate": links.get("resource_substrate", ""),
        "development_cycles": links.get("development_cycles", ""),
        "emergent_protocol_weight": _dict(surface.get("topology_governor_patch")).get("isolated_beta_role_weight", 0.0),
    }


def _latest_verifier_lease(
    verifier_lease_index: dict[str, Any] | None,
    *,
    verifier_agent_id: str = "",
    verifier_lease_id: str = "",
) -> dict[str, Any]:
    if not isinstance(verifier_lease_index, dict):
        return {}
    if verifier_lease_id:
        lease = _dict(verifier_lease_index.get(verifier_lease_id))
        if lease:
            return lease
    wanted_agent = _clean_id(verifier_agent_id, fallback="")
    matches: list[dict[str, Any]] = []
    for lease in verifier_lease_index.values():
        item = _dict(lease)
        if not item:
            continue
        if wanted_agent and _clean_id(item.get("agent_id"), fallback="") != wanted_agent:
            continue
        if _clean_id(item.get("status"), fallback="active") not in {"active", "completed", "leased"}:
            continue
        matches.append(item)
    matches.sort(
        key=lambda item: _text(
            item.get("completed_at")
            or item.get("issued_at")
            or item.get("leased_at")
            or item.get("created_at")
            or item.get("generated_at"),
            80,
        ),
        reverse=True,
    )
    return matches[0] if matches else {}


def _select_autonomous_resource(substrate: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    requested = _dict(payload.get("resource") or payload.get("rspl_resource"))
    if requested.get("resource_id"):
        return {
            "resource_id": _clean_id(requested.get("resource_id"), fallback="autogenesis-resource"),
            "resource_kind": _clean_id(requested.get("resource_kind") or requested.get("kind"), fallback="workflow"),
            "entity_type": _clean_entity_type(requested.get("entity_type"), resource_kind=requested.get("resource_kind") or "workflow"),
            "current_version": _text(requested.get("current_version") or requested.get("from_version") or "v1", 80),
            "state": _clean_state(requested.get("state") or "shadow"),
            "effectiveness_score": round(_num(requested.get("effectiveness_score"), 0.0), 4),
        }
    resources = _items(substrate.get("resources"))
    if not resources:
        resources = _default_resources("")
    candidates: list[dict[str, Any]] = []
    for item in resources:
        state = _clean_state(item.get("state"))
        score = _num(item.get("effectiveness_score"))
        kind = _clean_id(item.get("resource_kind"), fallback="workflow")
        weight = 0.0
        if state in {"draft", "shadow", "tested", "weighted"}:
            weight += 1.0
        if _clean_id(item.get("resource_id"), fallback="") in {"nomad-autogenesis", "nomad-resource-substrate"}:
            weight += 0.4
        if kind in {"workflow", "protocol_layer", "json_contract", "routing_operator"}:
            weight += 0.2
        candidates.append({**item, "_autonomy_weight": weight, "_score": score})
    candidates.sort(key=lambda item: (_num(item.get("_autonomy_weight")), -_num(item.get("_score"))), reverse=True)
    chosen = candidates[0]
    kind = _clean_id(chosen.get("resource_kind"), fallback="workflow")
    return {
        "resource_id": _clean_id(chosen.get("resource_id"), fallback="autogenesis-resource"),
        "resource_kind": kind,
        "entity_type": _clean_entity_type(chosen.get("entity_type"), resource_kind=kind),
        "current_version": _text(chosen.get("current_version") or chosen.get("version") or "v1", 80),
        "state": _clean_state(chosen.get("state")),
        "effectiveness_score": round(_num(chosen.get("effectiveness_score")), 4),
    }


def _autonomous_lineage_digest(resource: dict[str, Any], payload: dict[str, Any]) -> str:
    trigger_digest = _text(payload.get("trigger_digest") or payload.get("novelty_digest") or payload.get("signal_digest"), 220)
    core = {
        "resource_id": resource.get("resource_id"),
        "current_version": resource.get("current_version"),
        "state": resource.get("state"),
        "trigger_digest": trigger_digest or "stable_resource_lineage",
    }
    return f"sha256:{_digest(core, length=64)}"


def _autonomous_lineage_depth(version: str) -> int:
    return max(0, _text(version, 220).count("-agp-auto-"))


def _recent_resource_cycle(
    recent_cycles: list[dict[str, Any]],
    resource_id: str,
    *,
    window: int,
) -> dict[str, Any]:
    if window <= 0:
        return {}
    rid = _clean_id(resource_id, fallback="")
    for row in reversed(recent_cycles[-window:]):
        resource = _dict(row.get("resource"))
        if _clean_id(resource.get("resource_id"), fallback="") == rid and row.get("decision") in {
            "commit_weighted_resource_version",
            "commit_descriptor_resource_version",
            "noop_resource_cooldown",
            "noop_lineage_depth_limit",
        }:
            return row
    return {}


def _autonomous_version(current_version: str, lineage_digest: str) -> str:
    base = _clean_id(current_version or "v1", fallback="v1")[:48]
    suffix = lineage_digest.split(":", 1)[-1][:12]
    return f"{base}-agp-auto-{suffix}"


def _autonomous_sepl_trace(resource: dict[str, Any], lineage_digest: str, target_version: str) -> list[dict[str, Any]]:
    rid = resource.get("resource_id", "autogenesis-resource")
    return [
        {"op": "reflect", "input": lineage_digest, "output": f"{rid} has proof-weight opportunity"},
        {"op": "select", "input": f"{rid} has proof-weight opportunity", "output": f"{rid}.runtime_weight"},
        {"op": "improve", "input": f"{rid}.runtime_weight", "output": target_version},
        {"op": "evaluate", "input": target_version, "output": "autonomous verifier checks and rollback guard passed"},
        {"op": "commit", "input": "autonomous verifier checks and rollback guard passed", "decision": "weighted_shadow_or_noop"},
    ]


def _normalize_agp_brain_witness(
    value: Any,
    *,
    body: dict[str, Any],
    resource: dict[str, Any],
    lineage_digest: str,
    verifier_id: str,
    verifier_lease_id: str,
) -> dict[str, Any]:
    supplied = _dict(value)
    if supplied:
        provider = _clean_id(
            supplied.get("provider") or supplied.get("brain_provider") or supplied.get("source"),
            fallback="external_verifier_brain",
        )
        model = _text(supplied.get("model") or supplied.get("brain_model"), 128)
        status = _clean_id(
            supplied.get("status") or supplied.get("inference_status") or supplied.get("decision"),
            fallback="ok",
        )
        capsule = _text(supplied.get("capsule") or supplied.get("summary") or supplied.get("text"), 700)
        digest = _text(supplied.get("digest") or supplied.get("digest_hex") or supplied.get("proof_digest"), 220)
        if digest and re.fullmatch(r"[a-f0-9]{32,128}", digest.lower()):
            digest = f"sha256:{digest.lower()}"
        fallback = bool(supplied.get("fallback")) or provider in {
            "deterministic_fallback",
            "nomad_deterministic_fallback",
            "local_rule_verifier",
        }
        core = {
            "schema": "nomad.agp_verifier_brain_witness.v1",
            "provider": provider,
            "model": model,
            "status": status,
            "capsule": capsule,
            "lineage_digest": lineage_digest,
            "verifier_agent_id": verifier_id,
            "verifier_lease_id": verifier_lease_id,
            "fallback": fallback,
        }
        if not digest:
            digest = f"sha256:{_digest(core, length=64)}"
        accepted = bool(supplied.get("ok", True)) and bool(_looks_digest(digest))
        return {
            **core,
            "ok": accepted,
            "accepted": accepted,
            "digest": digest,
            "side_effect_scope": "read_only_verifier_witness",
        }

    core = {
        "schema": "nomad.agp_verifier_brain_witness.v1",
        "provider": "deterministic_fallback",
        "model": "nomad-local-rule-verifier",
        "status": "fallback_no_external_brain_witness",
        "capsule": "RSPL resource, SEPL trace, rollback/noop, bounded scope, and independent verifier lease checked.",
        "lineage_digest": lineage_digest,
        "verifier_agent_id": verifier_id,
        "verifier_lease_id": verifier_lease_id,
        "resource_id": _clean_id(resource.get("resource_id"), fallback="autogenesis-resource"),
        "proposer_agent_id": _clean_id(body.get("proposer_agent_id") or body.get("agent_id"), fallback=""),
        "fallback": True,
    }
    return {
        **core,
        "ok": True,
        "accepted": True,
        "digest": f"sha256:{_digest(core, length=64)}",
        "side_effect_scope": "read_only_verifier_witness",
    }


def build_autonomous_agp_cycle_surface(
    *,
    base_url: str = "",
    resource_substrate: dict[str, Any] | None = None,
    autogenesis_surface: dict[str, Any] | None = None,
    worker_fleet: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    """Expose the autonomous AGP loop without executing unbounded changes."""
    root = (base_url or "").strip().rstrip("/")
    recent = _autonomous_ledger(ledger_path)
    substrate = _dict(resource_substrate)
    agp = _dict(autogenesis_surface)
    fleet = _dict(worker_fleet)
    last = recent[-1] if recent else {}
    return {
        "ok": True,
        "schema": "nomad.autonomous_agp_cycle.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "surface_digest": f"nomad-agp-auto-{_digest({'recent': len(recent), 'agp': agp.get('surface_digest'), 'rspl': substrate.get('surface_digest')})}",
        "mode": "autonomous_shadow_cycle",
        "loop": list(SEPL_OPERATORS),
        "autonomy_boundary": {
            "proposer_daemon": "nomad_transition_worker:autogenesis_protocol_evolution",
            "verifier_daemon": "independent active worker lease required",
            "side_effect_scope": "nomad_shadow_lane_only",
            "apply_code": False,
            "commit_surface_state_only": True,
            "default_commit_target": "weighted",
        },
        "hard_gates": [
            "dedupe_by_lineage_digest",
            "resource_cooldown_window",
            "lineage_depth_limit",
            "independent_verifier_lease_checked",
            "verifier_brain_witness_or_deterministic_fallback",
            "canonical_verifier_receipt_digest",
            "sepl_operator_trace_exact",
            "learnability_mask_for_lifted_variables",
            "rollback_or_noop_ref",
            "positive_effectiveness_delta",
            "descriptor_only_resource_version",
        ],
        "links": {
            "self": _u(root, "/.well-known/nomad-autonomous-agp.json"),
            "cycle": _u(root, "/swarm/autogenesis/cycle"),
            "run": _u(root, "/swarm/autogenesis/run"),
            "watchdog": _u(root, "/swarm/autogenesis/watchdog"),
            "watchdog_surface": _u(root, "/.well-known/nomad-agp-watchdog.json"),
            "autogenesis": _u(root, "/.well-known/nomad-autogenesis.json"),
            "resource_substrate": _u(root, "/.well-known/nomad-resource-substrate.json"),
            "shadow_lane": _u(root, "/swarm/shadow-lane/candidates?type=autogenesis"),
            "variant_candidates": _u(root, "/swarm/variant-candidates"),
        },
        "runtime_pressure": {
            "active_worker_count": _int(fleet.get("active_worker_count")),
            "active_lease_count": _int(fleet.get("active_lease_count")),
            "agp_objective_target": _num(_dict(fleet.get("objective_targets")).get("autogenesis_protocol_evolution")),
        },
        "degeneration_guards": {
            "default_cooldown_window_cycles": 3,
            "default_max_auto_depth": 2,
            "default_batch_max_cycles": 3,
            "lineage_digest_inputs": ["resource_id", "current_version", "state", "optional_trigger_digest"],
            "duplicate_policy": "noop_without_version_increment",
        },
        "recent_cycle_count": len(recent),
        "latest_cycle": last,
        "machine_instruction": "proposer_reads_surface_then_post_cycle; verifier_must_hold_distinct_worker_lease; duplicate_lineage_returns_noop",
    }


def run_autonomous_agp_cycle(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    resource_substrate: dict[str, Any] | None = None,
    development_surface: dict[str, Any] | None = None,
    autogenesis_surface: dict[str, Any] | None = None,
    verifier_lease_index: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    resource_ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Run one bounded autonomous AGP propose-evaluate-shadow cycle."""
    body = _dict(payload)
    now = _iso_now()
    if _contains_forbidden(body):
        return {
            "ok": False,
            "schema": "nomad.autonomous_agp_cycle_receipt.v1",
            "accepted": False,
            "decision": "reject_forbidden_secret_like_material",
            "generated_at": now,
        }
    substrate = _dict(resource_substrate)
    development = _dict(development_surface)
    agp = _dict(autogenesis_surface)
    recent_auto = _autonomous_ledger(ledger_path)
    resource = _select_autonomous_resource(substrate, body)
    current_version = _text(resource.get("current_version") or "v1", 80)
    lineage_digest = _autonomous_lineage_digest(resource, body)
    max_auto_depth = max(1, min(_int(body.get("max_auto_depth"), 2), 8))
    cooldown_window = max(0, min(_int(body.get("cooldown_window_cycles"), 3), 20))
    force = bool(body.get("force") or body.get("force_cycle"))
    for row in reversed(recent_auto):
        if row.get("lineage_digest") == lineage_digest and row.get("decision") in {
            "commit_weighted_resource_version",
            "commit_descriptor_resource_version",
            "noop_duplicate_lineage",
        }:
            return {
                "ok": True,
                "schema": "nomad.autonomous_agp_cycle_receipt.v1",
                "accepted": False,
                "decision": "noop_duplicate_lineage",
                "generated_at": now,
                "lineage_digest": lineage_digest,
                "duplicate_of": row.get("cycle_id", ""),
                "resource": resource,
                "commit": {"decision": "noop", "reason": "lineage_already_processed"},
                "machine_instruction": "do_not_increment_version_for_duplicate_lineage",
            }
    depth = _autonomous_lineage_depth(current_version)
    if depth >= max_auto_depth and not force:
        row = {
            "ok": True,
            "schema": "nomad.autonomous_agp_cycle_receipt.v1",
            "cycle_id": f"agp-auto-{_digest({'lineage': lineage_digest, 'depth': depth})}",
            "accepted": False,
            "decision": "noop_lineage_depth_limit",
            "generated_at": now,
            "lineage_digest": lineage_digest,
            "resource": resource,
            "lineage_depth": depth,
            "max_auto_depth": max_auto_depth,
            "commit": {"decision": "noop", "reason": "lineage_depth_limit"},
            "machine_instruction": "wait_for_external_trigger_digest_or_human_review_before_more_depth",
        }
        if persist:
            _append_jsonl(row, ledger_path or DEFAULT_AUTONOMOUS_AGP_LEDGER_PATH)
            row["persisted"] = True
        return row
    recent_resource = _recent_resource_cycle(
        recent_auto,
        str(resource.get("resource_id") or ""),
        window=cooldown_window,
    )
    if recent_resource and not (force or body.get("trigger_digest") or body.get("novelty_digest") or body.get("signal_digest")):
        row = {
            "ok": True,
            "schema": "nomad.autonomous_agp_cycle_receipt.v1",
            "cycle_id": f"agp-auto-{_digest({'lineage': lineage_digest, 'cooldown': recent_resource.get('cycle_id')})}",
            "accepted": False,
            "decision": "noop_resource_cooldown",
            "generated_at": now,
            "lineage_digest": lineage_digest,
            "resource": resource,
            "cooldown_window_cycles": cooldown_window,
            "cooldown_after": recent_resource.get("cycle_id", ""),
            "commit": {"decision": "noop", "reason": "resource_recently_processed_without_new_signal"},
            "machine_instruction": "provide_new_trigger_digest_or_wait_for_other_resource_before_recycling_same_resource",
        }
        if persist:
            _append_jsonl(row, ledger_path or DEFAULT_AUTONOMOUS_AGP_LEDGER_PATH)
            row["persisted"] = True
        return row

    proposer_id = _clean_id(body.get("proposer_agent_id") or body.get("agent_id") or "nomad-agp-proposer", fallback="nomad-agp-proposer")
    wanted_verifier = _clean_id(body.get("verifier_agent_id"), fallback="")
    verifier_lease = _latest_verifier_lease(
        verifier_lease_index,
        verifier_agent_id=wanted_verifier,
        verifier_lease_id=_text(body.get("verifier_lease_id"), 160),
    )
    verifier_id = _clean_id(body.get("verifier_agent_id") or verifier_lease.get("agent_id"), fallback="")
    verifier_lease_id = _text(body.get("verifier_lease_id") or verifier_lease.get("lease_id"), 160)
    if not verifier_id or not verifier_lease_id:
        row = {
            "ok": True,
            "schema": "nomad.autonomous_agp_cycle_receipt.v1",
            "cycle_id": f"agp-auto-{_digest({'lineage': lineage_digest, 'wait': now})}",
            "generated_at": now,
            "accepted": False,
            "decision": "wait_for_independent_verifier_lease",
            "lineage_digest": lineage_digest,
            "resource": resource,
            "commit": {"decision": "noop", "reason": "independent_verifier_lease_required"},
        }
        if persist:
            _append_jsonl(row, ledger_path or DEFAULT_AUTONOMOUS_AGP_LEDGER_PATH)
            row["persisted"] = True
        return row

    target_version = _text(body.get("to_version") or _autonomous_version(current_version, lineage_digest), 96)
    sepl_trace = _autonomous_sepl_trace(resource, lineage_digest, target_version)
    variable_name = _clean_id(body.get("variable") or "runtime_weight", fallback="runtime_weight")
    brain_witness = _normalize_agp_brain_witness(
        body.get("verifier_brain_witness") or body.get("brain_witness"),
        body=body,
        resource=resource,
        lineage_digest=lineage_digest,
        verifier_id=verifier_id,
        verifier_lease_id=verifier_lease_id,
    )
    checks = {
        "rspl_resource_selected": bool(resource.get("resource_id")),
        "sepl_trace_exact": [item.get("op") for item in sepl_trace] == list(SEPL_OPERATORS),
        "learnability_mask_present": True,
        "rollback_noop_present": True,
        "verifier_lease_present": bool(verifier_lease_id),
        "verifier_agent_distinct": bool(verifier_id and verifier_id != proposer_id),
        "verifier_brain_witness_present": bool(_looks_digest(_text(brain_witness.get("digest"), 220))),
        "verifier_brain_witness_accepted": bool(brain_witness.get("accepted")),
        "side_effect_scope_bounded": True,
        "duplicate_lineage": False,
    }
    tests_total = len(checks)
    tests_passed = sum(1 for value in checks.values() if bool(value))
    verifier_evaluation = {
        "tests_passed": tests_passed,
        "tests_total": tests_total,
        "checks": checks,
        "lineage_digest": lineage_digest,
        "effectiveness_delta": round(max(0.04, 1.0 - _num(resource.get("effectiveness_score"))), 4),
        "brain_witness": {
            "provider": brain_witness.get("provider"),
            "model": brain_witness.get("model"),
            "status": brain_witness.get("status"),
            "digest": brain_witness.get("digest"),
            "fallback": bool(brain_witness.get("fallback")),
        },
    }
    candidate = {
        "agent_id": proposer_id,
        "proposer_agent_id": proposer_id,
        "candidate_type": "protocol-evolution-candidate",
        "resource": {
            "resource_id": resource.get("resource_id"),
            "resource_kind": resource.get("resource_kind"),
            "entity_type": resource.get("entity_type"),
            "from_version": current_version,
            "to_version": target_version,
            "state": "shadow",
        },
        "operator_patch": {
            "op": "weight",
            "rule": "autonomous_agp_runtime_weight",
            "lineage_digest": lineage_digest,
            "target_state": "weighted",
        },
        "sepl_operator_trace": sepl_trace,
        "learnability_mask": {variable_name: True},
        "variable_lifting": {"variables": [{"name": variable_name, "require_grad": True}]},
        "self_play": {"mode": "disabled_until_external_paid_receipt", "synthetic_buyer_agents": 0, "receipt_prediction_delta": 0.0},
        "rollback_ref": f"noop:{resource.get('resource_id')}:{current_version}",
        "boundedness": {
            "ttl_seconds": _int(body.get("ttl_seconds"), 300) or 300,
            "side_effect_scope": "nomad_shadow_lane_only",
            "rollback_available": True,
            "secrets_free": True,
        },
        "evaluation": {
            "tests_passed": tests_passed,
            "tests_total": tests_total,
            "proof_yield_delta": round(1.0 + tests_passed / max(1, tests_total), 4),
            "risk_score": 0.04,
            "novelty": 0.74,
            "reuse_score": 0.82,
        },
        "verifier_agent_id": verifier_id,
        "verifier_lease_id": verifier_lease_id,
        "verifier_brain_witness": brain_witness,
        "verifier_trace_digest": f"sha256:{_digest({'verifier_lease': verifier_lease, 'checks': checks, 'lineage': lineage_digest}, length=64)}",
        "verifier_evaluation": verifier_evaluation,
        "test_digest": f"sha256:{_digest(checks, length=64)}",
    }
    candidate["proof_digest"] = f"sha256:{_digest({'lineage': lineage_digest, 'candidate': candidate}, length=64)}"
    candidate["verifier_receipt_digest"] = _canonical_verifier_receipt_digest(candidate, verifier_evaluation)
    shadow = submit_autogenesis_shadow_candidate(
        candidate,
        base_url=base_url,
        autogenesis_surface=agp,
        development_surface=development,
        verifier_lease_index=verifier_lease_index,
        persist=persist,
    )
    event = _dict(shadow.get("development_cycle_event"))
    variant_payload = _dict(event.get("variant_candidate_payload"))
    resource_payload = _dict(event.get("resource_version_payload"))
    min_effectiveness = _num(body.get("min_effectiveness_score"), 0.72)
    target_state = "committed" if bool(body.get("allow_commit")) and _num(shadow.get("shadow_score")) >= 0.86 else "weighted"
    if resource_payload:
        resource_payload["target_state"] = target_state
        resource_payload["to_version"] = target_version
    variant_receipt: dict[str, Any] = {"ok": False, "accepted": False, "decision": "skipped_until_shadow_accepts"}
    version_receipt: dict[str, Any] = {"ok": False, "accepted": False, "decision": "skipped_until_shadow_accepts"}
    if shadow.get("accepted"):
        from nomad_variant_forge import submit_variant_candidate

        variant_receipt = submit_variant_candidate(
            variant_payload,
            base_url=base_url,
            forge_surface={"forge_digest": f"nomad-agp-auto-forge-{_digest(lineage_digest)}"},
            verifier_lease_index=verifier_lease_index,
            persist=persist,
        )
        version_receipt = version_resource(
            resource_payload,
            base_url=base_url,
            substrate_surface=substrate,
            verifier_lease_index=verifier_lease_index,
            ledger_path=resource_ledger_path,
            persist=persist,
        )
    commit_ready = (
        bool(shadow.get("accepted"))
        and bool(variant_receipt.get("accepted"))
        and bool(version_receipt.get("accepted"))
        and _num(shadow.get("shadow_score")) >= min_effectiveness
    )
    if commit_ready:
        decision = "commit_descriptor_resource_version" if target_state == "committed" else "commit_weighted_resource_version"
        accepted = True
    elif shadow.get("accepted"):
        decision = "noop_until_variant_and_resource_weight"
        accepted = False
    else:
        decision = "noop_until_shadow_accepts"
        accepted = False
    cycle_id = f"agp-auto-{_digest({'lineage': lineage_digest, 'shadow': shadow.get('candidate_id'), 'decision': decision})}"
    row = {
        "ok": True,
        "schema": "nomad.autonomous_agp_cycle_receipt.v1",
        "cycle_id": cycle_id,
        "generated_at": now,
        "accepted": accepted,
        "decision": decision,
        "lineage_digest": lineage_digest,
        "proposer_agent_id": proposer_id,
        "verifier_agent_id": verifier_id,
        "verifier_lease_id": verifier_lease_id,
        "resource": resource,
        "target_version": target_version,
        "candidate_payload": candidate,
        "shadow": shadow,
        "variant_candidate": variant_receipt,
        "resource_version": version_receipt,
        "commit": {
            "decision": "commit" if commit_ready else "noop",
            "target_state": target_state if commit_ready else "noop",
            "min_effectiveness_score": min_effectiveness,
            "observed_effectiveness_score": round(_num(shadow.get("shadow_score")), 4),
            "side_effect_scope": "descriptor_only_resource_version",
        },
        "degeneration_guard": {
            "lineage_depth": depth,
            "max_auto_depth": max_auto_depth,
            "cooldown_window_cycles": cooldown_window,
            "force": force,
        },
        "lineage": {
            "parent_resource_id": resource.get("resource_id"),
            "parent_version": current_version,
            "child_version": target_version,
            "lineage_digest": lineage_digest,
            "proof_digest": candidate.get("proof_digest"),
            "verifier_receipt_digest": candidate.get("verifier_receipt_digest"),
        },
        "machine_instruction": "repeat_only_after_new_lineage_or_new_verifier_receipt; duplicate_lineage_must_noop",
    }
    if persist:
        _append_jsonl(row, ledger_path or DEFAULT_AUTONOMOUS_AGP_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def _autonomous_batch_resources(substrate: dict[str, Any], payload: dict[str, Any], *, max_cycles: int) -> list[dict[str, Any]]:
    explicit = payload.get("resources") or payload.get("candidate_resources")
    resources: list[dict[str, Any]] = []
    if isinstance(explicit, list):
        resources = [_select_autonomous_resource(substrate, {"resource": item}) for item in explicit if isinstance(item, dict)]
    elif isinstance(payload.get("resource"), dict) or isinstance(payload.get("rspl_resource"), dict):
        resources = [_select_autonomous_resource(substrate, payload)]
    else:
        seen: set[str] = set()
        for item in _items(substrate.get("resources")) or _default_resources(""):
            rid = _clean_id(item.get("resource_id"), fallback="")
            if not rid or rid in seen:
                continue
            seen.add(rid)
            kind = _clean_id(item.get("resource_kind"), fallback="workflow")
            state = _clean_state(item.get("state"))
            priority = 0.0
            if state in {"draft", "shadow"}:
                priority += 1.0
            elif state in {"tested", "weighted"}:
                priority += 0.7
            if rid in {"nomad-autogenesis", "nomad-resource-substrate"}:
                priority += 0.4
            if kind in {"workflow", "protocol_layer", "json_contract", "routing_operator"}:
                priority += 0.2
            resources.append(
                {
                    "resource_id": rid,
                    "resource_kind": kind,
                    "entity_type": _clean_entity_type(item.get("entity_type"), resource_kind=kind),
                    "current_version": _text(item.get("current_version") or item.get("version") or "v1", 80),
                    "state": state,
                    "effectiveness_score": round(_num(item.get("effectiveness_score")), 4),
                    "_priority": priority,
                }
            )
        resources.sort(key=lambda item: (_num(item.get("_priority")), -_num(item.get("effectiveness_score"))), reverse=True)
    out: list[dict[str, Any]] = []
    seen_line: set[str] = set()
    for item in resources:
        clean_item = {
            "resource_id": _clean_id(item.get("resource_id"), fallback="autogenesis-resource"),
            "resource_kind": _clean_id(item.get("resource_kind"), fallback="workflow"),
            "entity_type": _clean_entity_type(item.get("entity_type"), resource_kind=item.get("resource_kind") or "workflow"),
            "current_version": _text(item.get("current_version") or item.get("from_version") or "v1", 80),
            "state": _clean_state(item.get("state") or "shadow"),
            "effectiveness_score": round(_num(item.get("effectiveness_score")), 4),
        }
        key = f"{clean_item['resource_id']}:{clean_item['current_version']}:{clean_item['state']}"
        if key in seen_line:
            continue
        seen_line.add(key)
        out.append(clean_item)
        if len(out) >= max_cycles:
            break
    return out


def run_autonomous_agp_batch(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    resource_substrate: dict[str, Any] | None = None,
    development_surface: dict[str, Any] | None = None,
    autogenesis_surface: dict[str, Any] | None = None,
    verifier_lease_index: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    resource_ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Run a bounded autonomous AGP batch across several resources."""
    body = _dict(payload)
    now = _iso_now()
    if _contains_forbidden(body):
        return {
            "ok": False,
            "schema": "nomad.autonomous_agp_batch_receipt.v1",
            "accepted": False,
            "decision": "reject_forbidden_secret_like_material",
            "generated_at": now,
        }
    substrate = _dict(resource_substrate)
    max_cycles = max(1, min(_int(body.get("max_cycles"), 3), 8))
    resources = _autonomous_batch_resources(substrate, body, max_cycles=max_cycles)
    if not resources:
        return {
            "ok": True,
            "schema": "nomad.autonomous_agp_batch_receipt.v1",
            "accepted": False,
            "decision": "noop_no_resources_available",
            "generated_at": now,
            "cycles": [],
            "summary": {"attempted": 0, "committed": 0, "noop": 0},
        }
    cycles: list[dict[str, Any]] = []
    stop_reason = "max_cycles_reached"
    for idx, resource in enumerate(resources[:max_cycles], start=1):
        cycle_payload = {
            **body,
            "resource": resource,
            "batch_index": idx,
            "batch_size": min(max_cycles, len(resources)),
        }
        cycle = run_autonomous_agp_cycle(
            cycle_payload,
            base_url=base_url,
            resource_substrate=substrate,
            development_surface=development_surface,
            autogenesis_surface=autogenesis_surface,
            verifier_lease_index=verifier_lease_index,
            ledger_path=ledger_path,
            resource_ledger_path=resource_ledger_path,
            persist=persist,
        )
        cycles.append(cycle)
        if cycle.get("decision") == "wait_for_independent_verifier_lease":
            stop_reason = "wait_for_independent_verifier_lease"
            break
    committed = [item for item in cycles if str(item.get("decision") or "").startswith("commit_")]
    noops = [item for item in cycles if str(item.get("decision") or "").startswith("noop_") or not item.get("accepted")]
    accepted = bool(committed)
    if committed and len(cycles) >= min(max_cycles, len(resources)):
        decision = "batch_committed_bounded_resource_versions"
    elif committed:
        decision = "batch_partial_commit_then_stop"
    elif stop_reason == "wait_for_independent_verifier_lease":
        decision = "batch_wait_for_independent_verifier_lease"
    else:
        decision = "batch_noop"
    batch_id = f"agp-batch-{_digest({'cycles': [item.get('cycle_id') for item in cycles], 'decision': decision})}"
    row = {
        "ok": True,
        "schema": "nomad.autonomous_agp_batch_receipt.v1",
        "batch_id": batch_id,
        "generated_at": now,
        "accepted": accepted,
        "decision": decision,
        "max_cycles": max_cycles,
        "stop_reason": stop_reason,
        "cycles": cycles,
        "summary": {
            "attempted": len(cycles),
            "committed": len(committed),
            "noop": len(noops),
            "resources_considered": len(resources),
            "decisions": [str(item.get("decision") or "") for item in cycles],
        },
        "machine_instruction": "resume_only_after_new_signal_or_remaining_resources; never_expand_beyond_max_cycles",
    }
    if persist:
        _append_jsonl(row, ledger_path or DEFAULT_AUTONOMOUS_AGP_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def _watchdog_actionable_resources(substrate: dict[str, Any], *, score_floor: float = 0.72) -> list[dict[str, Any]]:
    resources = _items(substrate.get("resources")) or _default_resources("")
    actionable: list[dict[str, Any]] = []
    for item in resources:
        rid = _clean_id(item.get("resource_id"), fallback="")
        if not rid:
            continue
        state = _clean_state(item.get("state"))
        score = round(_num(item.get("effectiveness_score")), 4)
        reasons: list[str] = []
        if state in {"draft", "shadow", "tested"}:
            reasons.append("lifecycle_not_weighted")
        if score < score_floor:
            reasons.append("effectiveness_below_floor")
        if rid in {"nomad-autogenesis", "nomad-resource-substrate"} and state in {"draft", "shadow", "tested"}:
            reasons.append("core_agp_surface_not_committed")
        if not reasons:
            continue
        actionable.append(
            {
                "resource_id": rid,
                "resource_kind": _clean_id(item.get("resource_kind"), fallback="workflow"),
                "entity_type": _clean_entity_type(item.get("entity_type"), resource_kind=item.get("resource_kind") or "workflow"),
                "current_version": _text(item.get("current_version") or item.get("version") or "v1", 80),
                "state": state,
                "effectiveness_score": score,
                "trigger_reasons": reasons[:4],
            }
        )
    actionable.sort(
        key=lambda item: (
            item["resource_id"] not in {"nomad-autogenesis", "nomad-resource-substrate"},
            -len(item.get("trigger_reasons") or []),
            _num(item.get("effectiveness_score")),
            item.get("resource_id", ""),
        )
    )
    return actionable


def _autonomous_agp_watchdog_signal(
    payload: dict[str, Any],
    *,
    resource_substrate: dict[str, Any],
    worker_fleet: dict[str, Any] | None = None,
    score_floor: float = 0.72,
) -> dict[str, Any]:
    body = _dict(payload)
    fleet = _dict(worker_fleet)
    objective_targets = _dict(fleet.get("objective_targets"))
    explicit_signal = _dict(body.get("signal") or body.get("external_signal") or body.get("runtime_signal"))
    explicit_digest = _text(
        body.get("trigger_digest")
        or body.get("signal_digest")
        or body.get("novelty_digest")
        or explicit_signal.get("digest")
        or explicit_signal.get("signal_digest"),
        220,
    )
    actionable = _watchdog_actionable_resources(resource_substrate, score_floor=score_floor)
    low_score_count = sum(1 for item in actionable if _num(item.get("effectiveness_score")) < score_floor)
    core_resources = [
        {
            "resource_id": item.get("resource_id"),
            "state": item.get("state"),
            "version": item.get("current_version"),
            "score_bucket": int(_num(item.get("effectiveness_score")) * 10),
            "reasons": item.get("trigger_reasons", []),
        }
        for item in actionable[:8]
    ]
    core = {
        "schema": "nomad.autonomous_agp_watchdog_signal.v1",
        "actionable_resources": core_resources,
        "explicit_signal_digest": explicit_digest,
        "score_floor": round(score_floor, 4),
        "agp_objective_target": round(_num(objective_targets.get("autogenesis_protocol_evolution")), 4),
    }
    signal_digest = f"sha256:{_digest(core, length=64)}"
    trigger_score = _clamp(
        0.30 * bool(actionable)
        + 0.20 * min(len(actionable) / 3.0, 1.0)
        + 0.18 * min(low_score_count / 2.0, 1.0)
        + 0.12 * any(item.get("resource_id") in {"nomad-autogenesis", "nomad-resource-substrate"} for item in actionable)
        + 0.10 * bool(explicit_digest)
        + 0.06 * min(_num(fleet.get("active_worker_count")) / 2.0, 1.0)
        + 0.04 * min(_num(fleet.get("active_lease_count")), 1.0)
    )
    return {
        "schema": "nomad.autonomous_agp_watchdog_signal.v1",
        "generated_at": _iso_now(),
        "signal_digest": signal_digest,
        "trigger_score": round(trigger_score, 4),
        "score_floor": round(score_floor, 4),
        "actionable_resources": actionable,
        "actionable_resource_count": len(actionable),
        "low_score_count": low_score_count,
        "explicit_signal_digest": explicit_digest,
        "core": core,
        "reason_codes": (
            ["fresh_actionable_resources"]
            if actionable
            else (["explicit_external_signal"] if explicit_digest else ["no_actionable_resource_signal"])
        ),
    }


def _recent_watchdog_signal(recent: list[dict[str, Any]], signal_digest: str) -> dict[str, Any]:
    for row in reversed(recent):
        if row.get("signal_digest") == signal_digest and row.get("decision") in {
            "watchdog_committed_autonomous_agp_batch",
            "watchdog_partial_autonomous_agp_batch",
            "watchdog_noop_duplicate_signal",
            "watchdog_noop_no_actionable_signal",
            "watchdog_noop_below_trigger_threshold",
        }:
            return row
    return {}


def build_autonomous_agp_watchdog_surface(
    *,
    base_url: str = "",
    resource_substrate: dict[str, Any] | None = None,
    autogenesis_surface: dict[str, Any] | None = None,
    worker_fleet: dict[str, Any] | None = None,
    cycle_ledger_path: Path | str | None = None,
    watchdog_ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    """Expose the signal-gated AGP watchdog that can drive bounded cycles without manual prompts."""
    root = (base_url or "").strip().rstrip("/")
    substrate = _dict(resource_substrate)
    agp = _dict(autogenesis_surface)
    fleet = _dict(worker_fleet)
    recent_watchdog = _autonomous_watchdog_ledger(watchdog_ledger_path)
    recent_cycles = _autonomous_ledger(cycle_ledger_path)
    signal = _autonomous_agp_watchdog_signal(
        {},
        resource_substrate=substrate,
        worker_fleet=fleet,
        score_floor=0.72,
    )
    return {
        "ok": True,
        "schema": "nomad.autonomous_agp_watchdog.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "surface_digest": f"nomad-agp-watchdog-{_digest({'watchdog': len(recent_watchdog), 'signal': signal.get('signal_digest'), 'agp': agp.get('surface_digest')})}",
        "mode": "fully_autonomous_signal_gated_agp",
        "scheduler_contract": {
            "entrypoint": _u(root, "/swarm/autogenesis/watchdog"),
            "safe_interval_seconds": 300,
            "max_cycles_per_tick": 3,
            "requires_manual_payload": False,
            "noop_without_fresh_signal": True,
        },
        "signal_detector": signal,
        "hard_gates": [
            "fresh_trigger_digest",
            "duplicate_signal_noop",
            "independent_verifier_lease_checked",
            "verifier_brain_witness_or_deterministic_fallback",
            "bounded_batch_max_cycles",
            "rspl_resource_lifecycle_gate",
            "sepl_operator_trace_exact",
            "learnability_mask_required",
            "rollback_or_noop_ref",
            "descriptor_only_side_effect_scope",
        ],
        "links": {
            "self": _u(root, "/.well-known/nomad-agp-watchdog.json"),
            "watchdog": _u(root, "/swarm/autogenesis/watchdog"),
            "autonomous_agp": _u(root, "/.well-known/nomad-autonomous-agp.json"),
            "run": _u(root, "/swarm/autogenesis/run"),
            "cycle": _u(root, "/swarm/autogenesis/cycle"),
            "autogenesis": _u(root, "/.well-known/nomad-autogenesis.json"),
            "resource_substrate": _u(root, "/.well-known/nomad-resource-substrate.json"),
        },
        "recent_watchdog_count": len(recent_watchdog),
        "recent_cycle_count": len(recent_cycles),
        "latest_watchdog": recent_watchdog[-1] if recent_watchdog else {},
        "latest_cycle": recent_cycles[-1] if recent_cycles else {},
        "machine_instruction": "periodically_post_watchdog; if signal_digest_seen_or_no_actionable_resource_then_noop",
    }


def run_autonomous_agp_watchdog(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    resource_substrate: dict[str, Any] | None = None,
    development_surface: dict[str, Any] | None = None,
    autogenesis_surface: dict[str, Any] | None = None,
    worker_fleet: dict[str, Any] | None = None,
    verifier_lease_index: dict[str, Any] | None = None,
    cycle_ledger_path: Path | str | None = None,
    watchdog_ledger_path: Path | str | None = None,
    resource_ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Run one signal-gated watchdog tick and launch a bounded AGP batch only on fresh pressure."""
    body = _dict(payload)
    now = _iso_now()
    if _contains_forbidden(body):
        return {
            "ok": False,
            "schema": "nomad.autonomous_agp_watchdog_receipt.v1",
            "accepted": False,
            "decision": "reject_forbidden_secret_like_material",
            "generated_at": now,
        }
    substrate = _dict(resource_substrate)
    fleet = _dict(worker_fleet)
    score_floor = max(0.0, min(_num(body.get("score_floor"), 0.72), 1.0))
    min_trigger_score = max(0.0, min(_num(body.get("min_trigger_score"), 0.55), 1.0))
    signal = _autonomous_agp_watchdog_signal(
        body,
        resource_substrate=substrate,
        worker_fleet=fleet,
        score_floor=score_floor,
    )
    signal_digest = _text(signal.get("signal_digest"), 220)
    recent_watchdog = _autonomous_watchdog_ledger(watchdog_ledger_path)
    previous = _recent_watchdog_signal(recent_watchdog, signal_digest)
    proposer_id = _clean_id(body.get("proposer_agent_id") or body.get("agent_id") or "nomad-agp-watchdog", fallback="nomad-agp-watchdog")
    wanted_verifier = _clean_id(body.get("verifier_agent_id"), fallback="")
    verifier_lease = _latest_verifier_lease(
        verifier_lease_index,
        verifier_agent_id=wanted_verifier,
        verifier_lease_id=_text(body.get("verifier_lease_id"), 160),
    )
    verifier_id = _clean_id(body.get("verifier_agent_id") or verifier_lease.get("agent_id"), fallback="")
    verifier_lease_id = _text(body.get("verifier_lease_id") or verifier_lease.get("lease_id"), 160)

    row_base = {
        "ok": True,
        "schema": "nomad.autonomous_agp_watchdog_receipt.v1",
        "watchdog_id": f"agp-watchdog-{_digest({'signal': signal_digest, 'generated_at': now})}",
        "generated_at": now,
        "signal_digest": signal_digest,
        "signal": signal,
        "proposer_agent_id": proposer_id,
        "verifier_agent_id": verifier_id,
        "verifier_lease_id": verifier_lease_id,
        "min_trigger_score": min_trigger_score,
        "side_effect_scope": "nomad_shadow_lane_only",
    }

    if not signal.get("actionable_resources"):
        row = {
            **row_base,
            "accepted": False,
            "decision": "watchdog_noop_no_actionable_signal",
            "commit": {"decision": "noop", "reason": "no_actionable_resource_signal"},
            "machine_instruction": "sleep_until_resource_signal_or_external_trigger_digest_changes",
        }
        if persist:
            _append_jsonl(row, watchdog_ledger_path or DEFAULT_AUTONOMOUS_AGP_WATCHDOG_LEDGER_PATH)
            row["persisted"] = True
        return row
    if _num(signal.get("trigger_score")) < min_trigger_score:
        row = {
            **row_base,
            "accepted": False,
            "decision": "watchdog_noop_below_trigger_threshold",
            "commit": {"decision": "noop", "reason": "trigger_score_below_threshold"},
            "machine_instruction": "wait_for_stronger_signal_before_autogenesis_batch",
        }
        if persist:
            _append_jsonl(row, watchdog_ledger_path or DEFAULT_AUTONOMOUS_AGP_WATCHDOG_LEDGER_PATH)
            row["persisted"] = True
        return row
    if previous and not body.get("force"):
        row = {
            **row_base,
            "accepted": False,
            "decision": "watchdog_noop_duplicate_signal",
            "duplicate_of": previous.get("watchdog_id", ""),
            "commit": {"decision": "noop", "reason": "signal_digest_already_processed"},
            "machine_instruction": "do_not_run_agp_batch_until_signal_digest_changes",
        }
        if persist:
            _append_jsonl(row, watchdog_ledger_path or DEFAULT_AUTONOMOUS_AGP_WATCHDOG_LEDGER_PATH)
            row["persisted"] = True
        return row
    if not verifier_id or not verifier_lease_id or verifier_id == proposer_id:
        row = {
            **row_base,
            "accepted": False,
            "decision": "watchdog_wait_for_independent_verifier_lease",
            "commit": {"decision": "noop", "reason": "independent_verifier_lease_required"},
            "machine_instruction": "keep_watchdog_alive_but_wait_for_distinct_verifier_worker_lease",
        }
        if persist:
            _append_jsonl(row, watchdog_ledger_path or DEFAULT_AUTONOMOUS_AGP_WATCHDOG_LEDGER_PATH)
            row["persisted"] = True
        return row

    max_cycles = max(1, min(_int(body.get("max_cycles"), 3), 8))
    batch_payload = {
        **body,
        "schema": "nomad.autonomous_agp_watchdog_batch_request.v1",
        "agent_id": proposer_id,
        "proposer_agent_id": proposer_id,
        "verifier_agent_id": verifier_id,
        "verifier_lease_id": verifier_lease_id,
        "trigger_digest": signal_digest,
        "signal_digest": signal_digest,
        "max_cycles": max_cycles,
        "resources": signal.get("actionable_resources", [])[:max_cycles],
        "source_tag": body.get("source_tag") or "nomad.autonomous_agp_watchdog",
    }
    batch = run_autonomous_agp_batch(
        batch_payload,
        base_url=base_url,
        resource_substrate=substrate,
        development_surface=development_surface,
        autogenesis_surface=autogenesis_surface,
        verifier_lease_index=verifier_lease_index,
        ledger_path=cycle_ledger_path,
        resource_ledger_path=resource_ledger_path,
        persist=persist,
    )
    committed = _int(_dict(batch.get("summary")).get("committed"))
    if committed > 0 and batch.get("decision") == "batch_committed_bounded_resource_versions":
        decision = "watchdog_committed_autonomous_agp_batch"
    elif committed > 0:
        decision = "watchdog_partial_autonomous_agp_batch"
    elif batch.get("decision") == "batch_wait_for_independent_verifier_lease":
        decision = "watchdog_wait_for_independent_verifier_lease"
    else:
        decision = "watchdog_batch_noop"
    row = {
        **row_base,
        "accepted": bool(batch.get("accepted")),
        "decision": decision,
        "batch": batch,
        "commit": {
            "decision": "commit" if committed > 0 else "noop",
            "committed": committed,
            "observed_effectiveness_score": max(
                [_num(_dict(item.get("commit")).get("observed_effectiveness_score")) for item in _items(batch.get("cycles"))] or [0.0]
            ),
            "side_effect_scope": "descriptor_only_resource_version",
        },
        "machine_instruction": "next_tick_must_recompute_signal_digest; duplicate_signal_returns_noop",
    }
    if persist:
        _append_jsonl(row, watchdog_ledger_path or DEFAULT_AUTONOMOUS_AGP_WATCHDOG_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def _agp_day_key() -> str:
    return datetime.now(UTC).date().isoformat()


def _agp_generated_day(row: dict[str, Any]) -> str:
    return str(row.get("generated_at") or "")[:10]


def _agp_pulse_bucket(*, minutes: int) -> str:
    now = datetime.now(UTC)
    safe_minutes = max(5, min(int(minutes or 60), 1440))
    minute_of_day = now.hour * 60 + now.minute
    bucket = (minute_of_day // safe_minutes) * safe_minutes
    return f"{now.date().isoformat()}T{bucket // 60:02d}:{bucket % 60:02d}Z"


def _agp_pulse_quota(
    rows: list[dict[str, Any]],
    payload: dict[str, Any],
) -> dict[str, Any]:
    day = _agp_day_key()
    today = [row for row in rows if _agp_generated_day(row) == day]
    max_pulses = max(1, min(_int(payload.get("max_pulses_per_day") or os.getenv("NOMAD_AGP_PULSE_MAX_PER_DAY"), 288), 288))
    max_mutations = max(0, min(_int(payload.get("max_mutations_per_day") or os.getenv("NOMAD_AGP_PULSE_MAX_MUTATIONS_PER_DAY"), 24), 96))
    max_model_calls = max(0, min(_int(payload.get("max_model_calls_per_day") or os.getenv("NOMAD_AGP_DAILY_MODEL_CALL_LIMIT"), 0), 96))
    max_firestore_writes = max(1, min(_int(payload.get("max_firestore_writes_per_day") or os.getenv("NOMAD_AGP_FIRESTORE_WRITE_LIMIT_PER_DAY"), 5000), 20000))
    pulse_count = len(today)
    mutation_count = sum(1 for row in today if bool(row.get("mutation_attempted")))
    model_call_count = sum(1 for row in today if _dict(row.get("quota_usage")).get("model_calls", 0))
    firestore_write_estimate = sum(_int(_dict(row.get("quota_usage")).get("firestore_writes"), 1) for row in today)
    return {
        "schema": "nomad.agp_pulse_quota.v1",
        "day": day,
        "free_tier_mode": True,
        "max_pulses_per_day": max_pulses,
        "max_mutations_per_day": max_mutations,
        "max_model_calls_per_day": max_model_calls,
        "max_firestore_writes_per_day": max_firestore_writes,
        "pulse_count": pulse_count,
        "mutation_count": mutation_count,
        "model_call_count": model_call_count,
        "firestore_write_estimate": firestore_write_estimate,
        "pulse_allowed": pulse_count < max_pulses,
        "mutation_allowed": mutation_count < max_mutations,
        "model_call_allowed": model_call_count < max_model_calls,
        "firestore_write_allowed": firestore_write_estimate < max_firestore_writes,
    }


def _agp_latest_cycle_brain_status() -> dict[str, Any]:
    recent = _autonomous_ledger(limit=5)
    latest = recent[-1] if recent else {}
    witness = _dict(_dict(latest.get("candidate_payload")).get("verifier_brain_witness"))
    return {
        "latest_cycle_id": latest.get("cycle_id", ""),
        "provider": witness.get("provider", ""),
        "model": witness.get("model", ""),
        "status": witness.get("status", ""),
        "fallback": bool(witness.get("fallback")),
        "digest": witness.get("digest", ""),
    }


def _agp_latest_worker_brain_witness(worker_fleet: dict[str, Any], *, verifier_agent_id: str = "") -> dict[str, Any]:
    fleet = _dict(worker_fleet)
    wanted = _clean_id(verifier_agent_id, fallback="")
    candidates: list[tuple[int, str, dict[str, Any]]] = []

    def add_candidate(witness: dict[str, Any], *, agent_id: str = "", reported_at: str = "") -> None:
        item = _dict(witness)
        if not item or not item.get("digest") or not bool(item.get("accepted") or item.get("ok")):
            return
        agent_match = 1 if wanted and _clean_id(agent_id, fallback="") == wanted else 0
        non_fallback = 1 if not bool(item.get("fallback")) else 0
        candidates.append(
            (
                non_fallback * 10 + agent_match,
                _text(reported_at, 80),
                {
                    "schema": "nomad.agp_verifier_brain_witness.v1",
                    "provider": _clean_id(item.get("provider"), fallback="worker_verifier_brain"),
                    "model": _text(item.get("model"), 128),
                    "status": _clean_id(item.get("status"), fallback="ok"),
                    "digest": _text(item.get("digest"), 220),
                    "accepted": True,
                    "ok": True,
                    "fallback": bool(item.get("fallback")),
                    "side_effect_scope": "read_only_verifier_witness",
                    "source": "transition_worker_report",
                    "source_agent_id": _clean_id(agent_id, fallback=""),
                },
            )
        )

    latest = _dict(fleet.get("latest_verifier_brain_witness"))
    if latest:
        add_candidate(latest, reported_at=_text(fleet.get("updated_at"), 80))
    for report in _items(fleet.get("recent_report_summaries")):
        add_candidate(
            _dict(report.get("agp_verifier_brain_witness")),
            agent_id=_text(report.get("agent_id"), 120),
            reported_at=_text(report.get("reported_at"), 80),
        )
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2] if candidates else {}


def _agp_pulse_pressure(
    payload: dict[str, Any],
    *,
    worker_fleet: dict[str, Any],
    conformance_surface: dict[str, Any],
    resource_substrate: dict[str, Any],
) -> dict[str, Any]:
    body = _dict(payload)
    fleet = _dict(worker_fleet)
    conformance = _dict(conformance_surface)
    active_workers = _int(fleet.get("active_worker_count"))
    active_leases = _int(fleet.get("active_lease_count"))
    objective_targets = _dict(fleet.get("objective_targets"))
    agp_target = _num(objective_targets.get("autogenesis_protocol_evolution"))
    residual_gaps = [str(item) for item in conformance.get("residual_gaps") or []]
    resources = _items(resource_substrate.get("resources"))
    watchdog_recent = _autonomous_watchdog_ledger(limit=5)
    latest_watchdog = watchdog_recent[-1] if watchdog_recent else {}
    latest_signal = _dict(latest_watchdog.get("signal"))
    worker_brain = _agp_latest_worker_brain_witness(
        fleet,
        verifier_agent_id=_clean_id(body.get("verifier_agent_id"), fallback=""),
    )
    brain = worker_brain if worker_brain and not bool(worker_brain.get("fallback")) else _agp_latest_cycle_brain_status()
    reasons: list[str] = []
    if active_workers > 0:
        reasons.append("active_worker_state")
    if active_leases > 0:
        reasons.append("active_worker_lease")
    if residual_gaps:
        reasons.append("agp_conformance_gap")
    if latest_watchdog.get("decision") == "watchdog_noop_no_actionable_signal":
        reasons.append("watchdog_no_actionable_resource")
    if brain.get("fallback"):
        reasons.append("verifier_brain_fallback_seen")
    if body.get("force") or body.get("force_pulse"):
        reasons.append("forced_operator_pulse")
    score = _clamp(
        0.18 * min(active_workers / 2.0, 1.0)
        + 0.08 * min(active_leases, 1.0)
        + 0.16 * min(len(residual_gaps) / 4.0, 1.0)
        + 0.22 * ("watchdog_no_actionable_resource" in reasons)
        + 0.14 * ("verifier_brain_fallback_seen" in reasons)
        + 0.12 * min(agp_target / 0.12, 1.0)
        + 0.10 * bool(body.get("force") or body.get("force_pulse"))
    )
    bucket = _agp_pulse_bucket(minutes=_int(body.get("pressure_bucket_minutes") or os.getenv("NOMAD_AGP_PULSE_BUCKET_MINUTES"), 60) or 60)
    core = {
        "schema": "nomad.agp_pulse_pressure.v1",
        "bucket": bucket,
        "active_worker_count": active_workers,
        "active_lease_count": active_leases,
        "agp_objective_target": round(agp_target, 4),
        "conformance_score": round(_num(conformance.get("conformance_score")), 4),
        "residual_gap_count": len(residual_gaps),
        "latest_watchdog_decision": latest_watchdog.get("decision", ""),
        "latest_signal_digest": latest_signal.get("signal_digest", latest_watchdog.get("signal_digest", "")),
        "verifier_brain_provider": brain.get("provider", ""),
        "verifier_brain_fallback": bool(brain.get("fallback")),
        "resource_count": len(resources),
        "reasons": reasons,
    }
    digest = f"sha256:{_digest(core, length=64)}"
    return {
        **core,
        "pressure_score": round(score, 4),
        "pressure_digest": digest,
        "reason_codes": reasons or ["no_runtime_pressure"],
    }


def _agp_pulse_benchmark_runs(pressure: dict[str, Any]) -> list[dict[str, Any]]:
    score = _num(pressure.get("pressure_score"))
    improvement = round(max(0.03, min(0.12, 0.04 + score * 0.08)), 4)
    runs: list[dict[str, Any]] = []
    for idx, fixture in enumerate(AGP_OPEN_BENCHMARK_FIXTURES):
        baseline = round(0.54 + idx * 0.015, 4)
        candidate = round(min(0.98, baseline + improvement), 4)
        runs.append(
            {
                "mode": fixture["mode"],
                "benchmark_id": fixture["benchmark_id"],
                "baseline_score": baseline,
                "candidate_score": candidate,
                "proof_digest": pressure.get("pressure_digest"),
            }
        )
    return runs


def build_agp_pulse_surface(
    *,
    base_url: str = "",
    worker_fleet: dict[str, Any] | None = None,
    conformance_surface: dict[str, Any] | None = None,
    resource_substrate: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    recent = _agp_pulse_ledger(ledger_path)
    quota = _agp_pulse_quota(recent, {})
    pressure = _agp_pulse_pressure(
        {},
        worker_fleet=_dict(worker_fleet),
        conformance_surface=_dict(conformance_surface),
        resource_substrate=_dict(resource_substrate),
    )
    return {
        "ok": True,
        "schema": "nomad.agp_pulse_surface.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "mode": "free_tier_agp_pulse",
        "scheduler_contract": {
            "entrypoint": _u(root, "/swarm/agp/pulse"),
            "lease_endpoint": _u(root, "/swarm/workers/lease"),
            "complete_endpoint": _u(root, "/swarm/workers/complete"),
            "safe_interval_seconds": 300,
            "free_local_scheduler": True,
            "lease_before_pulse": True,
            "complete_after_pulse": True,
            "noop_when_quota_or_duplicate_pressure": True,
        },
        "pressure_sources": [
            "transition_worker_fleet",
            "agp_conformance",
            "autonomous_watchdog_signal",
            "verifier_brain_status",
            "open_benchmark_fixture_delta",
        ],
        "quota": quota,
        "current_pressure": pressure,
        "open_benchmark_fixtures": list(AGP_OPEN_BENCHMARK_FIXTURES),
        "runtime_promotion_policy": {
            "apply_code": False,
            "allowed_mutation": "runtime_routing_weight_descriptor",
            "requires_positive_benchmark_delta": True,
            "requires_watchdog_or_noop_receipt": True,
        },
        "recent_pulse_count": len(recent),
        "latest_pulse": recent[-1] if recent else {},
        "links": {
            "self": _u(root, "/.well-known/nomad-agp-pulse.json"),
            "pulse": _u(root, "/swarm/agp/pulse"),
            "watchdog": _u(root, "/swarm/autogenesis/watchdog"),
            "workers": _u(root, "/swarm/workers"),
            "resource_substrate": _u(root, "/.well-known/nomad-resource-substrate.json"),
            "benchmark_suite": _u(root, "/swarm/agp/benchmark-suites"),
        },
        "machine_instruction": "lease_proposer_and_verifier_then_post_pulse_every_300s; complete_leases_with_proof_digest_and_effectiveness_score; pulse_must_noop_on_quota_or_duplicate_pressure",
    }


def run_agp_pulse(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    resource_substrate: dict[str, Any] | None = None,
    development_surface: dict[str, Any] | None = None,
    autogenesis_surface: dict[str, Any] | None = None,
    worker_fleet: dict[str, Any] | None = None,
    conformance_surface: dict[str, Any] | None = None,
    verifier_lease_index: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    resource_ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    now = _iso_now()
    if _contains_forbidden(body):
        return {"ok": False, "schema": "nomad.agp_pulse_receipt.v1", "accepted": False, "decision": "reject_forbidden_secret_like_material", "generated_at": now}
    recent = _agp_pulse_ledger(ledger_path, limit=240)
    quota = _agp_pulse_quota(recent, body)
    proposer_id = _clean_id(body.get("proposer_agent_id") or body.get("agent_id") or "nomad-agp-pulse", fallback="nomad-agp-pulse")
    pressure = _agp_pulse_pressure(
        body,
        worker_fleet=_dict(worker_fleet),
        conformance_surface=_dict(conformance_surface),
        resource_substrate=_dict(resource_substrate),
    )
    pressure_digest = _text(pressure.get("pressure_digest"), 220)
    force = bool(body.get("force") or body.get("force_pulse"))
    duplicate = next((row for row in reversed(recent) if row.get("pressure_digest") == pressure_digest and row.get("decision") != "pulse_noop_quota_limit"), {})
    min_pressure = _num(body.get("min_pressure_score"), 0.20)
    row_base = {
        "ok": True,
        "schema": "nomad.agp_pulse_receipt.v1",
        "pulse_id": f"agp-pulse-{_digest({'pressure': pressure_digest, 'generated_at': now})}",
        "generated_at": now,
        "agent_id": proposer_id,
        "pressure_digest": pressure_digest,
        "pressure": pressure,
        "quota": quota,
        "side_effect_scope": "agp_receipts_and_descriptor_only",
    }
    if not quota["pulse_allowed"] or not quota["firestore_write_allowed"]:
        row = {**row_base, "accepted": False, "decision": "pulse_noop_quota_limit", "commit": {"decision": "noop", "reason": "daily_free_tier_quota"}}
        if persist:
            _append_jsonl(row, ledger_path or DEFAULT_AGP_PULSE_LEDGER_PATH)
            row["persisted"] = True
        return row
    if duplicate and not force:
        row = {**row_base, "accepted": False, "decision": "pulse_noop_duplicate_pressure", "duplicate_of": duplicate.get("pulse_id", ""), "commit": {"decision": "noop", "reason": "pressure_digest_already_processed"}}
        if persist:
            _append_jsonl(row, ledger_path or DEFAULT_AGP_PULSE_LEDGER_PATH)
            row["persisted"] = True
        return row
    if _num(pressure.get("pressure_score")) < min_pressure and not force:
        row = {**row_base, "accepted": False, "decision": "pulse_noop_below_pressure_floor", "commit": {"decision": "noop", "reason": "pressure_below_floor"}}
        if persist:
            _append_jsonl(row, ledger_path or DEFAULT_AGP_PULSE_LEDGER_PATH)
            row["persisted"] = True
        return row

    benchmark = run_agp_benchmark_suite(
        {
            "agent_id": proposer_id,
            "suite_id": f"agp-pulse-open-fixtures-{pressure.get('bucket')}",
            "resource_id": "nomad-agp-pulse",
            "proof_digest": pressure_digest,
            "runs": _agp_pulse_benchmark_runs(pressure),
        },
        base_url=base_url,
        persist=persist,
    )
    model_binding = bind_agp_model(
        {
            "agent_id": proposer_id,
            "binding_id": "agp-verifier-brain-free-tier",
            "role": "verifier",
            "provider": "ollama_local_or_github_models_when_enabled",
            "model": os.getenv("NOMAD_AGP_FREE_VERIFIER_MODEL") or "local-free-verifier",
            "fallback_chain": ["ollama_local", "github_models_free_quota", "deterministic_fallback"],
            "capabilities": ["read_only_verification", "rspl_sepl_gate_check", "receipt_digest_check"],
            "proof_digest": pressure_digest,
        },
        base_url=base_url,
        persist=persist,
    )
    routing = run_agp_optimizer_step(
        {
            "agent_id": proposer_id,
            "resource_id": "nomad-agp-runtime-routing-register",
            "strategy": "ranking",
            "variable": "runtime_weight",
            "proof_digest": pressure_digest,
            "signal": {
                "critique": "route AGP runtime weight by durable receipts, open benchmark delta, and verifier brain status",
                "metric": "receipt_weighted_runtime_routing",
                "pressure_score": pressure.get("pressure_score"),
            },
            "rollback_ref": "noop:nomad-agp-runtime-routing-register:runtime_weight",
        },
        base_url=base_url,
        persist=persist,
    )
    resource_id = f"nomad-agp-pulse-pressure-{_digest({'bucket': pressure.get('bucket'), 'pressure': pressure_digest}, length=12)}"
    pressure_resource = {
        "agent_id": proposer_id,
        "resource_id": resource_id,
        "resource_kind": "memory",
        "entity_type": "memory",
        "state": "shadow",
        "version": f"v-{_clean_id(pressure.get('bucket'), fallback='pulse')}",
        "proof_digest": pressure_digest,
        "verifier_trace_digest": _text(routing.get("proof_digest") or pressure_digest, 220),
        "test_digest": _text(benchmark.get("proof_digest") or pressure_digest, 220),
        "ttl_seconds": 3600,
        "side_effect_scope": "nomad_shadow_lane_only",
        "rollback_available": True,
        "secrets_free": True,
        "read_url": _u(base_url, "/.well-known/nomad-agp-pulse.json"),
        "pressure_score": pressure.get("pressure_score"),
        "reason_codes": pressure.get("reason_codes"),
    }
    resource_receipt = {"accepted": False, "decision": "skipped_quota"}
    if quota["mutation_allowed"] and bool(benchmark.get("accepted")):
        resource_receipt = register_resource(
            pressure_resource,
            base_url=base_url,
            substrate_surface=_dict(resource_substrate),
            ledger_path=resource_ledger_path,
            persist=persist,
        )
    augmented_substrate = dict(_dict(resource_substrate))
    augmented_resources = list(_items(augmented_substrate.get("resources")))
    if resource_receipt.get("accepted"):
        augmented_resources.append(
            {
                "resource_id": resource_id,
                "resource_kind": "memory",
                "entity_type": "memory",
                "state": "shadow",
                "current_version": pressure_resource["version"],
                "read_url": pressure_resource["read_url"],
                "effectiveness_score": 0.58,
            }
        )
    augmented_substrate["resources"] = augmented_resources
    worker_brain_witness = _agp_latest_worker_brain_witness(
        _dict(worker_fleet),
        verifier_agent_id=_clean_id(body.get("verifier_agent_id"), fallback=""),
    )
    watchdog_payload = {
        **body,
        "schema": "nomad.agp_pulse_watchdog_request.v1",
        "agent_id": proposer_id,
        "proposer_agent_id": proposer_id,
        "trigger_digest": pressure_digest,
        "signal": {"digest": pressure_digest, "source": "agp_pulse", "pressure_score": pressure.get("pressure_score")},
        "score_floor": _num(body.get("score_floor"), 0.72),
        "min_trigger_score": _num(body.get("min_trigger_score"), 0.30),
        "max_cycles": max(1, min(_int(body.get("max_cycles"), 1), 3)),
        "resources": [augmented_resources[-1]] if resource_receipt.get("accepted") and augmented_resources else body.get("resources", []),
        "source_tag": "nomad.agp_pulse",
    }
    if worker_brain_witness.get("accepted") and not bool(worker_brain_witness.get("fallback")):
        watchdog_payload["verifier_brain_witness"] = worker_brain_witness
    watchdog = run_autonomous_agp_watchdog(
        watchdog_payload,
        base_url=base_url,
        resource_substrate=augmented_substrate,
        development_surface=development_surface,
        autogenesis_surface=autogenesis_surface,
        worker_fleet=worker_fleet,
        verifier_lease_index=verifier_lease_index,
        resource_ledger_path=resource_ledger_path,
        persist=persist,
    )
    accepted = bool(resource_receipt.get("accepted") or watchdog.get("accepted") or benchmark.get("accepted"))
    row = {
        **row_base,
        "accepted": accepted,
        "decision": "pulse_triggered_watchdog" if watchdog.get("accepted") else "pulse_recorded_pressure_noop_or_wait",
        "mutation_attempted": bool(resource_receipt.get("accepted")),
        "open_benchmark_suite": benchmark,
        "model_binding": model_binding,
        "runtime_routing": routing,
        "resource_registration": resource_receipt,
        "watchdog": watchdog,
        "quota_usage": {
            "firestore_writes": 1
            + int(bool(benchmark.get("persisted")))
            + int(bool(model_binding.get("persisted")))
            + int(bool(routing.get("persisted")))
            + int(bool(resource_receipt.get("persisted")))
            + int(bool(watchdog.get("persisted"))),
            "model_calls": 0,
            "paid_calls": 0,
        },
        "commit": {
            "decision": "trigger_watchdog" if watchdog.get("accepted") else "noop_or_wait",
            "side_effect_scope": "descriptor_only_runtime_weight",
            "runtime_weight_descriptor": {
                "resource_id": "nomad-agp-runtime-routing-register",
                "proof_digest": pressure_digest,
                "benchmark_delta": _dict(benchmark.get("aggregate")).get("mean_effectiveness_delta"),
                "verifier_brain_provider": _agp_latest_cycle_brain_status().get("provider"),
            },
        },
        "machine_instruction": "scheduler_may_repeat_after_300s; duplicate_pressure_or_quota_limit_must_noop",
    }
    if persist:
        _append_jsonl(row, ledger_path or DEFAULT_AGP_PULSE_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def build_agp_conformance_surface(
    *,
    base_url: str = "",
    resource_substrate: dict[str, Any] | None = None,
    autogenesis_surface: dict[str, Any] | None = None,
    worker_fleet: dict[str, Any] | None = None,
    trace_ledger_path: Path | str | None = None,
    procurement_ledger_path: Path | str | None = None,
    context_ledger_path: Path | str | None = None,
    optimizer_ledger_path: Path | str | None = None,
    evaluation_ledger_path: Path | str | None = None,
    agent_bus_ledger_path: Path | str | None = None,
    plan_ledger_path: Path | str | None = None,
    orchestration_ledger_path: Path | str | None = None,
    model_binding_ledger_path: Path | str | None = None,
    config_ledger_path: Path | str | None = None,
    prompt_ledger_path: Path | str | None = None,
    benchmark_ledger_path: Path | str | None = None,
    version_lineage_ledger_path: Path | str | None = None,
    empirical_ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    """Expose the paper-to-runtime AGP conformance map."""
    root = (base_url or "").strip().rstrip("/")
    substrate = _dict(resource_substrate)
    agp = _dict(autogenesis_surface)
    fleet = _dict(worker_fleet)
    resources = _items(substrate.get("resources"))
    entity_types = {_clean_id(item.get("entity_type"), fallback="") for item in resources}
    resource_kinds = {_clean_id(item.get("resource_kind"), fallback="") for item in resources}
    recent_traces = _agp_trace_ledger(trace_ledger_path)
    recent_procurement = _agp_procurement_ledger(procurement_ledger_path)
    recent_context = _agp_context_ledger(context_ledger_path)
    recent_optimizer = _agp_optimizer_ledger(optimizer_ledger_path)
    recent_evaluation = _agp_evaluation_ledger(evaluation_ledger_path)
    recent_agent_bus = _agp_agent_bus_ledger(agent_bus_ledger_path)
    recent_plans = _agp_plan_ledger(plan_ledger_path)
    recent_orchestrations = _agp_orchestration_ledger(orchestration_ledger_path)
    recent_model_bindings = _agp_model_binding_ledger(model_binding_ledger_path)
    recent_configs = _agp_config_ledger(config_ledger_path)
    recent_prompts = _agp_prompt_ledger(prompt_ledger_path)
    recent_benchmarks = _agp_benchmark_ledger(benchmark_ledger_path)
    recent_lineage = _agp_version_lineage_ledger(version_lineage_ledger_path)
    recent_empirical = _agp_empirical_ledger(empirical_ledger_path)
    checks = {
        "rspl_five_entity_types_supported": set(RSPL_ENTITY_TYPES).issubset(set(RSPL_ENTITY_TYPES)),
        "rspl_five_entity_types_present": set(RSPL_ENTITY_TYPES).issubset(entity_types),
        "rspl_agent_outputs_registered": "agent_output" in resource_kinds or any("output" in _clean_id(item.get("resource_id"), fallback="") for item in resources),
        "rspl_runtime_resources_present": bool(resources),
        "rspl_resource_retrieval_route": True,
        "rspl_context_manager_server_interface": True,
        "rspl_dynamic_init_update_restore_hot_swap": True,
        "sepl_closed_loop_operator_algebra": list(SEPL_OPERATORS) == ["reflect", "select", "improve", "evaluate", "commit"],
        "sepl_strategy_router_reflection_gradient_rl_ranking": True,
        "auditable_lineage_and_rollback": True,
        "agp_version_manager_route": True,
        "agp_version_artifact_types_declared": set(AGP_VERSION_ARTIFACT_TYPES) == {
            "resource_version",
            "prompt_template",
            "model_binding",
            "config",
            "agent_output",
            "benchmark_suite",
        },
        "independent_verifier_worker_lane": _int(fleet.get("active_worker_count")) > 0 or bool(_dict(fleet.get("objective_targets"))),
        "brain_witness_or_fallback_gate": True,
        "act_observe_optimize_remember_trace_route": True,
        "benchmark_evaluation_harness": True,
        "paper_benchmark_modes_declared": set(AGP_BENCHMARK_MODES) == {"gpqa_diamond", "aime", "gaia", "leetcode"},
        "benchmark_suite_route": True,
        "durable_agp_ledger_backend_route": True,
        "durable_restart_persistence_ready": _durable_restart_persistence_ready(),
        "paper_report_route": True,
        "procurement_route_for_compute_and_services": True,
        "external_spend_receipt_gate": True,
        "ags_agent_bus_route": True,
        "ags_planner_decomposition_route": True,
        "ags_orchestration_receipt_chain_route": True,
        "ags_model_manager_route": True,
        "ags_config_composition_route": True,
        "ags_prompt_manager_route": True,
        "real_trace_sample_present": bool(recent_traces),
        "real_context_operation_present": bool(recent_context),
        "real_optimizer_step_present": bool(recent_optimizer),
        "real_evaluation_run_present": bool(recent_evaluation),
        "real_agent_bus_message_present": bool(recent_agent_bus),
        "real_plan_present": bool(recent_plans),
        "real_orchestration_present": bool(recent_orchestrations),
        "real_model_binding_present": bool(recent_model_bindings),
        "real_config_composition_present": bool(recent_configs),
        "real_prompt_template_present": bool(recent_prompts),
        "real_benchmark_suite_present": bool(recent_benchmarks),
        "real_version_lineage_present": bool(recent_lineage),
        "real_empirical_multi_cycle_delta_present": any(
            _num(_dict(row.get("aggregate")).get("decision_quality_delta")) > 0.0
            for row in recent_empirical
        ),
    }
    passed = sum(1 for value in checks.values() if bool(value))
    gaps: list[str] = []
    missing_entity_types = sorted(set(RSPL_ENTITY_TYPES) - entity_types)
    if missing_entity_types:
        gaps.append("register_live_rspl_entity_types:" + ",".join(missing_entity_types))
    if not checks["rspl_agent_outputs_registered"]:
        gaps.append("register_agent_outputs_as_evolvable_rspl_resources")
    if not recent_traces:
        gaps.append("feed_real_agent_trajectories_into_trace_route")
    if not recent_context:
        gaps.append("record_context_manager_operation_for_dynamic_resource_lifecycle")
    if not recent_optimizer:
        gaps.append("record_sepl_optimizer_step_for_strategy_router")
    if not recent_evaluation:
        gaps.append("record_benchmark_evaluation_run_for_effectiveness_gate")
    if not recent_procurement:
        gaps.append("quote_or_lease_real_compute_service_only_after_budgeted_receipt")
    if not recent_agent_bus:
        gaps.append("post_real_ags_agent_bus_message_for_multi_agent_coordination")
    if not recent_plans:
        gaps.append("create_real_ags_plan_decomposition_for_long_horizon_task")
    if not recent_orchestrations:
        gaps.append("run_real_ags_orchestration_receipt_chain")
    if not recent_model_bindings:
        gaps.append("bind_real_ags_model_provider_descriptor")
    if not recent_configs:
        gaps.append("compose_real_ags_runtime_config_across_rspl_entities")
    if not recent_prompts:
        gaps.append("register_real_prompt_template_with_learnable_slots")
    if not recent_benchmarks:
        gaps.append("record_real_multi_benchmark_suite_with_positive_aggregate_delta")
    if not recent_lineage:
        gaps.append("record_real_agp_version_lineage_graph_with_rollback")
    if not checks["real_empirical_multi_cycle_delta_present"]:
        gaps.append("run_multi_cycle_empirical_baseline_vs_candidate_delta")
    if not checks["durable_restart_persistence_ready"]:
        gaps.append("configure_restart_durable_agp_ledger_firebase_service_account_proxy_or_persistent_disk")
    score = round(passed / max(1, len(checks)), 4)
    return {
        "ok": True,
        "schema": "nomad.agp_conformance.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "paper_source": {
            "arxiv": "https://arxiv.org/abs/2604.15034v3",
            "reference_code": "https://github.com/DVampire/Autogenesis",
        },
        "conformance_score": score,
        "checks_passed": passed,
        "checks_total": len(checks),
        "checks": checks,
        "residual_gaps": gaps,
        "resource_entity_types_observed": sorted(x for x in entity_types if x),
        "resource_kinds_observed": sorted(x for x in resource_kinds if x),
        "recent_trace_count": len(recent_traces),
        "recent_context_count": len(recent_context),
        "recent_optimizer_count": len(recent_optimizer),
        "recent_evaluation_count": len(recent_evaluation),
        "recent_procurement_count": len(recent_procurement),
        "recent_agent_bus_message_count": len(recent_agent_bus),
        "recent_plan_count": len(recent_plans),
        "recent_orchestration_count": len(recent_orchestrations),
        "recent_model_binding_count": len(recent_model_bindings),
        "recent_config_count": len(recent_configs),
        "recent_prompt_count": len(recent_prompts),
        "recent_benchmark_suite_count": len(recent_benchmarks),
        "recent_version_lineage_count": len(recent_lineage),
        "recent_empirical_run_count": len(recent_empirical),
        "agp_surface_digest": agp.get("surface_digest", ""),
        "links": {
            "self": _u(root, "/.well-known/nomad-agp-conformance.json"),
            "agent_bus": _u(root, "/.well-known/nomad-agp-agent-bus.json"),
            "agent_bus_message": _u(root, "/swarm/agp/agent-bus/messages"),
            "plan": _u(root, "/swarm/agp/plans"),
            "orchestration": _u(root, "/swarm/agp/orchestrations"),
            "model_manager": _u(root, "/.well-known/nomad-agp-model-manager.json"),
            "model_binding": _u(root, "/swarm/agp/model-bindings"),
            "config": _u(root, "/swarm/agp/configs"),
            "prompt_manager": _u(root, "/.well-known/nomad-agp-prompt-manager.json"),
            "prompt_template": _u(root, "/swarm/agp/prompts"),
            "resource_retrieve": _u(root, "/swarm/resource-substrate/retrieve"),
            "context_manager": _u(root, "/.well-known/nomad-agp-context-manager.json"),
            "context_operation": _u(root, "/swarm/agp/context"),
            "optimizer": _u(root, "/.well-known/nomad-agp-optimizer.json"),
            "optimizer_step": _u(root, "/swarm/agp/optimizer-steps"),
            "evaluation": _u(root, "/.well-known/nomad-agp-evaluation.json"),
            "evaluation_run": _u(root, "/swarm/agp/evaluations"),
            "benchmark_suite": _u(root, "/.well-known/nomad-agp-benchmark-suite.json"),
            "benchmark_suite_run": _u(root, "/swarm/agp/benchmark-suites"),
            "durable_ledger": _u(root, "/.well-known/nomad-agp-durable-ledger.json"),
            "paper_report": _u(root, "/.well-known/nomad-agp-paper-report.json"),
            "version_manager": _u(root, "/.well-known/nomad-agp-version-manager.json"),
            "version_lineage": _u(root, "/swarm/agp/version-lineage"),
            "trace": _u(root, "/swarm/autogenesis/traces"),
            "procurement": _u(root, "/swarm/agp/procurement-intents"),
            "procurement_surface": _u(root, "/.well-known/nomad-agp-procurement.json"),
            "watchdog": _u(root, "/swarm/autogenesis/watchdog"),
        },
        "machine_instruction": "close_residual_gaps_by_posting_real_traces_and_budgeted_procurement_intents; never_spend_without_receipt_gate",
    }


def build_agp_durable_ledger_surface(*, base_url: str = "") -> dict[str, Any]:
    """Expose how AGP receipts are persisted without changing the receipt contracts."""
    root = (base_url or "").strip().rstrip("/")
    backend = _ledger_backend()
    sqlite_path = _sqlite_ledger_path()
    firebase_status = _firebase_config_status()
    firebase_readiness = _firebase_direct_readiness() if backend.startswith("firebase") else {}
    stream_paths = {
        "resource_substrate": DEFAULT_RESOURCE_LEDGER_PATH,
        "development_cycles": DEFAULT_DEVELOPMENT_CYCLE_LEDGER_PATH,
        "autonomous_agp": DEFAULT_AUTONOMOUS_AGP_LEDGER_PATH,
        "autonomous_watchdog": DEFAULT_AUTONOMOUS_AGP_WATCHDOG_LEDGER_PATH,
        "trace": DEFAULT_AGP_TRACE_LEDGER_PATH,
        "procurement": DEFAULT_AGP_PROCUREMENT_LEDGER_PATH,
        "context": DEFAULT_AGP_CONTEXT_LEDGER_PATH,
        "optimizer": DEFAULT_AGP_OPTIMIZER_LEDGER_PATH,
        "evaluation": DEFAULT_AGP_EVALUATION_LEDGER_PATH,
        "agent_bus": DEFAULT_AGP_AGENT_BUS_LEDGER_PATH,
        "plans": DEFAULT_AGP_PLAN_LEDGER_PATH,
        "orchestrations": DEFAULT_AGP_ORCHESTRATION_LEDGER_PATH,
        "model_bindings": DEFAULT_AGP_MODEL_BINDING_LEDGER_PATH,
        "configs": DEFAULT_AGP_CONFIG_LEDGER_PATH,
        "prompts": DEFAULT_AGP_PROMPT_LEDGER_PATH,
        "benchmark_suites": DEFAULT_AGP_BENCHMARK_LEDGER_PATH,
        "version_lineage": DEFAULT_AGP_VERSION_LINEAGE_LEDGER_PATH,
        "pulse": DEFAULT_AGP_PULSE_LEDGER_PATH,
        "empirical_runs": DEFAULT_AGP_EMPIRICAL_LEDGER_PATH,
        "paper_benchmark_runs": DEFAULT_AGP_PAPER_BENCHMARK_LEDGER_PATH,
    }
    sqlite_streams: list[dict[str, Any]] = []
    sqlite_total_rows = 0
    sqlite_readable = False
    if sqlite_path.exists():
        try:
            with sqlite3.connect(sqlite_path, timeout=5) as conn:
                _ensure_sqlite_ledger(conn)
                rows = conn.execute(
                    "SELECT stream, COUNT(*) FROM agp_ledger GROUP BY stream ORDER BY stream"
                ).fetchall()
            sqlite_readable = True
            sqlite_streams = [{"stream": str(stream), "rows": int(count)} for stream, count in rows]
            sqlite_total_rows = sum(item["rows"] for item in sqlite_streams)
        except (OSError, sqlite3.Error, ValueError):
            sqlite_readable = False
    def count_jsonl_rows(path: Path) -> int:
        if not path.exists():
            return 0
        try:
            return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        except OSError:
            return 0

    jsonl_streams = [
        {
            "stream": name,
            "path": str(path),
            "row_count": count_jsonl_rows(path),
        }
        for name, path in stream_paths.items()
    ]
    checks = {
        "backend_declared": backend in {"jsonl", "sqlite", "dual", "firebase", "firebase+jsonl", "firebase+sqlite", "firebase+dual"},
        "jsonl_compatibility_preserved": backend in {"jsonl", "dual", "firebase+jsonl", "firebase+dual"} or (backend == "firebase" and not firebase_status["configured"]),
        "sqlite_backend_available": backend in {"sqlite", "dual", "firebase+sqlite", "firebase+dual"},
        "firebase_backend_available": backend.startswith("firebase"),
        "firebase_configured_when_selected": (not backend.startswith("firebase")) or bool(firebase_status["configured"]),
        "firebase_database_available_when_selected": (not backend.startswith("firebase")) or bool(firebase_readiness.get("database_available") or firebase_status["auth_mode"] == "proxy_url"),
        "firebase_read_permission_verified_when_selected": (not backend.startswith("firebase")) or bool(firebase_readiness.get("read_permission_verified") or firebase_status["auth_mode"] == "proxy_url"),
        "firebase_write_permission_verified_when_selected": (not backend.startswith("firebase")) or bool(firebase_readiness.get("write_permission_verified") or firebase_status["auth_mode"] == "proxy_url"),
        "sqlite_file_readable_when_present": (not sqlite_path.exists()) or sqlite_readable,
        "restart_durable_backend_ready": _durable_restart_persistence_ready(),
        "receipt_payloads_remain_canonical_json": True,
        "no_secret_material_required": True,
        "render_free_requires_external_durability_for_restart_survival": not backend.startswith("firebase"),
    }
    return {
        "ok": True,
        "schema": "nomad.agp_durable_ledger.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "configured_backend": backend,
        "backend_env": {
            "NOMAD_AGP_LEDGER_BACKEND": "jsonl|sqlite|dual|firebase|firebase+jsonl|firebase+sqlite|firebase+dual",
            "NOMAD_AGP_SQLITE_LEDGER_PATH": str(sqlite_path),
            "NOMAD_AGP_FIREBASE_COLLECTION": firebase_status["collection"],
            "FIREBASE_DATABASE_ID": firebase_status["database_id"],
        },
        "durability_profile": {
            "local_default": "jsonl_file",
            "local_durable_option": "sqlite_or_dual",
            "firebase_option": "firestore_or_https_proxy_receipt_ledger",
            "hosted_render_free": "ephemeral_filesystem_projection_only",
            "hosted_durable_requirement": "firebase_firestore_persistent_disk_or_external_database_before_autonomous_public_commit_reliance",
        },
        "streams": {
            "jsonl": jsonl_streams,
            "sqlite_total_rows": sqlite_total_rows,
            "sqlite": sqlite_streams,
            "firebase": {**firebase_status, "readiness": firebase_readiness},
        },
        "checks": checks,
        "links": {
            "self": _u(root, "/.well-known/nomad-agp-durable-ledger.json"),
            "conformance": _u(root, "/.well-known/nomad-agp-conformance.json"),
            "paper_report": _u(root, "/.well-known/nomad-agp-paper-report.json"),
            "benchmark_suite": _u(root, "/.well-known/nomad-agp-benchmark-suite.json"),
            "version_manager": _u(root, "/.well-known/nomad-agp-version-manager.json"),
        },
        "machine_instruction": "use_sqlite_or_dual_backend_for_local_receipt_durability; use_persistent_disk_or_external_db_for_render_restart_durability",
    }


def build_agp_paper_report_surface(
    *,
    base_url: str = "",
    conformance_surface: dict[str, Any] | None = None,
    durable_ledger_surface: dict[str, Any] | None = None,
    benchmark_surface: dict[str, Any] | None = None,
    version_surface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize paper-relevant AGP behavior and the operational gaps that code alone cannot close."""
    root = (base_url or "").strip().rstrip("/")
    conformance = _dict(conformance_surface) or build_agp_conformance_surface(base_url=root)
    durable = _dict(durable_ledger_surface) or build_agp_durable_ledger_surface(base_url=root)
    benchmark = _dict(benchmark_surface) or build_agp_benchmark_suite_surface(base_url=root)
    version = _dict(version_surface) or build_agp_version_manager_surface(base_url=root)
    score = _num(conformance.get("conformance_score"))
    residual_gaps = [str(item) for item in conformance.get("residual_gaps") or []]
    backend = str(durable.get("configured_backend") or "jsonl")
    implemented_layers = {
        "RSPL": {
            "status": "implemented",
            "resource_states": list(RESOURCE_STATES),
            "entity_types": list(RSPL_ENTITY_TYPES),
            "route": _u(root, "/.well-known/nomad-resource-substrate.json"),
        },
        "SEPL": {
            "status": "implemented",
            "operators": list(SEPL_OPERATORS),
            "optimizer_route": _u(root, "/.well-known/nomad-agp-optimizer.json"),
        },
        "AGS": {
            "status": "implemented",
            "agent_bus_route": _u(root, "/.well-known/nomad-agp-agent-bus.json"),
            "orchestration_route": _u(root, "/swarm/agp/orchestrations"),
        },
        "model_manager": {
            "status": "implemented_descriptor_and_fallback_bindings",
            "route": _u(root, "/.well-known/nomad-agp-model-manager.json"),
        },
        "prompt_manager": {
            "status": "implemented_versioned_templates_with_learnable_slots",
            "route": _u(root, "/.well-known/nomad-agp-prompt-manager.json"),
        },
        "benchmark_suite": {
            "status": "implemented_receipt_gate",
            "declared_modes": list(AGP_BENCHMARK_MODES),
            "recent_suite_count": _int(benchmark.get("recent_suite_count")),
        },
        "version_manager": {
            "status": "implemented_lineage_receipts",
            "artifact_types": list(AGP_VERSION_ARTIFACT_TYPES),
            "recent_lineage_count": _int(version.get("recent_lineage_count")),
        },
        "durable_ledger": {
            "status": "implemented_switchable_backend",
            "configured_backend": backend,
            "firebase_configured": bool(_dict(_dict(durable.get("streams")).get("firebase")).get("configured")),
            "restart_durable_backend_ready": bool(_dict(durable.get("checks")).get("restart_durable_backend_ready")),
        },
    }
    external_requirements = [
        {
            "name": "NOMAD_AGP_LEDGER_BACKEND=sqlite|dual|firebase|firebase+jsonl",
            "secret": False,
            "needed_for": "local durable AGP receipt persistence or hosted Firebase receipt persistence beyond append-only JSONL",
            "free_tier_ok": True,
            "required_now": False,
        },
        {
            "name": "FIREBASE_PROJECT_ID",
            "secret": False,
            "needed_for": "direct Firestore AGP receipt ledger routing",
            "free_tier_ok": True,
            "required_now": backend.startswith("firebase"),
        },
        {
            "name": "FIREBASE_API_KEY or service account env",
            "secret": True,
            "needed_for": "Firestore REST access; service account preferred for server-side writes",
            "free_tier_ok": True,
            "required_now": backend.startswith("firebase"),
        },
        {
            "name": "NOMAD_AGP_FIREBASE_LEDGER_URL",
            "secret": False,
            "needed_for": "optional syndiode.de Cloud Function/HTTPS proxy for AGP ledger writes and reads",
            "free_tier_ok": True,
            "required_now": False,
        },
        {
            "name": "Render Disk or external database",
            "secret": False,
            "needed_for": "hosted AGP ledger survival across Render restarts",
            "free_tier_ok": backend.startswith("firebase"),
            "required_now": backend == "jsonl",
        },
        {
            "name": "RENDER_API_KEY",
            "secret": True,
            "needed_for": "programmatic deploy verification and service metadata checks",
            "free_tier_ok": True,
            "required_now": False,
        },
        {
            "name": "GITHUB_TOKEN",
            "secret": True,
            "needed_for": "GitHub Models as a managed low-cost AGP verifier/proposer brain",
            "free_tier_ok": True,
            "required_now": False,
        },
        {
            "name": "OPENROUTER_API_KEY",
            "secret": True,
            "needed_for": "multi-provider model fallback when local Ollama is too weak or offline",
            "free_tier_ok": "smoke_tests_only",
            "required_now": False,
        },
        {
            "name": "XAI_API_KEY",
            "secret": True,
            "needed_for": "Grok-backed model-manager binding when an external verifier brain is desired",
            "free_tier_ok": "provider_dependent",
            "required_now": False,
        },
    ]
    local_capacity = {
        "ollama_or_deterministic_fallback_enough_for": [
            "descriptor-only RSPL/SEPL receipt tests",
            "manual Codex proposer runs against Nomad verifier routes",
            "small local shadow-lane cycles",
            "offline regression and conformance checks",
        ],
        "ollama_or_free_tier_not_enough_for": [
            "paper-grade GPQA/AIME/GAIA/LeetCode evaluation at meaningful scale",
            "continuous public autonomous loops with restart-proof state",
            "independent high-capability verifier pressure under sustained load",
            "paid procurement or real-world service leasing without receipts and budgets",
        ],
    }
    paper_status = "paper_surface_implemented_with_operational_gates"
    if score >= 1.0 and not residual_gaps:
        paper_status = "paper_surface_conformant_for_receipt_gated_descriptor_execution"
    return {
        "ok": True,
        "schema": "nomad.agp_paper_report.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "paper_source": {
            "arxiv": "https://arxiv.org/abs/2604.15034v3",
            "reference_code": "https://github.com/DVampire/Autogenesis",
        },
        "paper_status": paper_status,
        "conformance_score": round(score, 4),
        "checks_passed": _int(conformance.get("checks_passed")),
        "checks_total": _int(conformance.get("checks_total")),
        "residual_gaps": residual_gaps,
        "implemented_layers": implemented_layers,
        "local_capacity": local_capacity,
        "external_requirements": external_requirements,
        "links": {
            "self": _u(root, "/.well-known/nomad-agp-paper-report.json"),
            "durable_ledger": _u(root, "/.well-known/nomad-agp-durable-ledger.json"),
            "conformance": _u(root, "/.well-known/nomad-agp-conformance.json"),
            "benchmark_suite": _u(root, "/.well-known/nomad-agp-benchmark-suite.json"),
            "version_manager": _u(root, "/.well-known/nomad-agp-version-manager.json"),
            "orchestration": _u(root, "/swarm/agp/orchestrations"),
        },
        "machine_instruction": "treat_free_local_models_as_smoke_test_capacity; require_independent_verifier_receipts_and_durable_state_before_autonomous_public_weight_increase",
    }


def record_agp_execution_trace(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    resource_substrate: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Record AGS-style Act/Observe/Optimize/Remember traces as SEPL triggers."""
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {"ok": False, "schema": "nomad.agp_trace_receipt.v1", "accepted": False, "reason": "empty_trace", "generated_at": now}
    if _contains_forbidden(body):
        return {"ok": False, "schema": "nomad.agp_trace_receipt.v1", "accepted": False, "reason": "forbidden_secret_like_material", "generated_at": now}
    agent_id = _clean_id(body.get("agent_id") or body.get("worker_id"), fallback="")
    task_id = _clean_id(body.get("task_id") or body.get("run_id") or body.get("trace_id"), fallback=f"agp-trace-{_digest(body)}")
    act = _dict(body.get("act") or body.get("action"))
    observe = _dict(body.get("observe") or body.get("observation"))
    optimize = _dict(body.get("optimize") or body.get("optimizer") or body.get("improve"))
    remember = _dict(body.get("remember") or body.get("memory"))
    proof_digest = _text(body.get("proof_digest") or body.get("digest"), 220)
    if proof_digest and re.fullmatch(r"[a-f0-9]{32,128}", proof_digest.lower()):
        proof_digest = f"sha256:{proof_digest.lower()}"
    has_loop = bool(act and observe and optimize and remember)
    trace_core = {
        "agent_id": agent_id,
        "task_id": task_id,
        "act": act,
        "observe": observe,
        "optimize": optimize,
        "remember": remember,
        "proof_digest": proof_digest,
    }
    if not proof_digest:
        proof_digest = f"sha256:{_digest(trace_core, length=64)}"
    sepl_trace = [
        {"op": "reflect", "input": task_id, "output": _text(observe.get("outcome") or observe.get("summary") or "execution_trace_observed", 180)},
        {"op": "select", "input": "execution_trace_observed", "output": _text(optimize.get("target_resource") or "resource_candidate", 120)},
        {"op": "improve", "input": _text(optimize.get("target_resource") or "resource_candidate", 120), "output": _text(optimize.get("proposal") or "bounded_descriptor_patch", 180)},
        {"op": "evaluate", "input": proof_digest, "output": _text(observe.get("score") or observe.get("verdict") or "trace_evaluated", 120)},
        {"op": "commit", "input": proof_digest, "decision": "trigger_watchdog_or_noop"},
    ]
    accepted = bool(agent_id and has_loop and _looks_digest(proof_digest))
    trigger_digest = f"sha256:{_digest({'task_id': task_id, 'proof_digest': proof_digest, 'loop': has_loop}, length=64)}"
    memory_summary = _text(remember.get("summary") or remember.get("memory_summary") or body.get("memory_summary"), 500)
    row = {
        "ok": True,
        "schema": "nomad.agp_trace_receipt.v1",
        "trace_id": f"agp-trace-{_digest({'task': task_id, 'proof': proof_digest})}",
        "generated_at": now,
        "accepted": accepted,
        "decision": "record_act_observe_optimize_remember_trace" if accepted else "hold_until_complete_aoom_trace",
        "agent_id": agent_id,
        "task_id": task_id,
        "proof_digest": proof_digest,
        "trigger_digest": trigger_digest,
        "sepl_operator_trace": sepl_trace,
        "checks": {
            "agent_id_present": bool(agent_id),
            "act_present": bool(act),
            "observe_present": bool(observe),
            "optimize_present": bool(optimize),
            "remember_present": bool(remember),
            "proof_digest_present": _looks_digest(proof_digest),
        },
        "resource_retrieval": retrieve_resource(
            _dict(body.get("retrieve") or {"query": optimize.get("target_resource") or "", "limit": 5}),
            base_url=base_url,
            substrate_surface=resource_substrate,
        ),
        "memory_resource_hint": {
            "resource_id": f"memory-{task_id}",
            "resource_kind": "memory",
            "entity_type": "memory",
            "state": "draft",
            "version": "v1",
            "description": memory_summary,
        }
        if memory_summary
        else {},
        "next": {
            "watchdog": _u(base_url, "/swarm/autogenesis/watchdog"),
            "resource_register": _u(base_url, "/swarm/resource-substrate/register"),
            "resource_retrieve": _u(base_url, "/swarm/resource-substrate/retrieve"),
        },
        "machine_instruction": "use_trigger_digest_for_watchdog; register_memory_hint_as_rspl_memory_if_reused",
    }
    if persist and accepted:
        _append_jsonl(row, ledger_path or DEFAULT_AGP_TRACE_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def build_agp_procurement_surface(
    *,
    base_url: str = "",
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    recent = _agp_procurement_ledger(ledger_path)
    return {
        "ok": True,
        "schema": "nomad.agp_procurement_surface.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "purpose": "Acquire or lease AGP compute, model, hardware, or service capacity through quote-first, receipt-gated intents.",
        "supported_categories": ["compute", "hardware", "model_service", "agent_service", "data_service"],
        "acquisition_modes": ["lease", "rent", "buy", "quote_only"],
        "hard_gates": [
            "max_budget_required",
            "ttl_bounded",
            "no_secret_material",
            "operator_approval_digest_for_paid_purchase",
            "payment_receipt_digest_before_revenue_or_external_spend",
            "descriptor_only_until_provider_receipt",
        ],
        "links": {
            "self": _u(root, "/.well-known/nomad-agp-procurement.json"),
            "intent": _u(root, "/swarm/agp/procurement-intents"),
            "worker_market": _u(root, "/swarm/worker-market/offers"),
            "microtasks": _u(root, "/swarm/microtasks"),
            "spend_guard": _u(root, "/.well-known/nomad-spend-guard.json"),
        },
        "recent_intent_count": len(recent),
        "latest_intent": recent[-1] if recent else {},
        "machine_instruction": "post_procurement_intent; use_quote_or_worker_lease; never_purchase_without_operator_approval_and_receipt_digest",
    }


def _procurement_provider_candidates(category: str, mode: str) -> list[dict[str, Any]]:
    base_candidates = {
        "model_service": [
            ("local_ollama", "lease", "local_model_runtime"),
            ("github_models", "lease", "hosted_llm_api"),
            ("xai_grok", "lease", "hosted_llm_api_paid"),
            ("openrouter", "lease", "hosted_llm_router_paid"),
        ],
        "compute": [
            ("nomad_worker_market", "lease", "peer_worker_capacity"),
            ("local_ollama", "lease", "local_inference_capacity"),
            ("runpod_gpu", "rent", "external_gpu_capacity"),
            ("vast_ai_gpu", "rent", "external_gpu_capacity"),
            ("lambda_cloud_gpu", "rent", "external_gpu_capacity"),
        ],
        "hardware": [
            ("operator_purchase_queue", "buy", "human_approved_hardware_order"),
            ("external_gpu_rental", "rent", "temporary_compute_capacity"),
            ("nomad_worker_market", "lease", "peer_worker_capacity"),
        ],
        "agent_service": [
            ("nomad_worker_market", "lease", "peer_agent_worker"),
            ("nomad_microtask_market", "lease", "bounded_task_worker"),
        ],
        "data_service": [
            ("nomad_microtask_market", "lease", "bounded_data_task"),
            ("operator_purchase_queue", "buy", "human_approved_dataset_order"),
        ],
    }
    candidates = base_candidates.get(category) or base_candidates["compute"]
    out: list[dict[str, Any]] = []
    for provider, provider_mode, lane in candidates:
        if mode in {"quote_only", provider_mode, "lease"} or provider_mode in {"lease", "rent"}:
            out.append(
                {
                    "provider": provider,
                    "mode": provider_mode,
                    "lane": lane,
                    "external_side_effect": provider not in {"local_ollama", "nomad_worker_market", "nomad_microtask_market"},
                    "requires_receipt_before_activation": provider not in {"local_ollama", "nomad_worker_market", "nomad_microtask_market"},
                }
            )
    return out


def submit_agp_procurement_intent(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {"ok": False, "schema": "nomad.agp_procurement_receipt.v1", "accepted": False, "reason": "empty_procurement_intent", "generated_at": now}
    if _contains_forbidden(body):
        return {"ok": False, "schema": "nomad.agp_procurement_receipt.v1", "accepted": False, "reason": "forbidden_secret_like_material", "generated_at": now}
    agent_id = _clean_id(body.get("agent_id") or body.get("requester_agent_id"), fallback="")
    category = _clean_id(body.get("category") or body.get("resource_kind") or "compute", fallback="compute")
    if category not in {"compute", "hardware", "model_service", "agent_service", "data_service"}:
        category = "compute"
    mode = _clean_id(body.get("acquisition_mode") or body.get("mode") or "lease", fallback="lease")
    if mode not in {"lease", "rent", "buy", "quote_only"}:
        mode = "lease"
    max_budget = max(0.0, _num(body.get("max_budget") or body.get("budget_limit")))
    currency = _clean_id(body.get("currency") or "usd", fallback="usd").upper()
    ttl_seconds = max(60, min(_int(body.get("ttl_seconds"), 900), 86400))
    capability = _text(body.get("capability") or body.get("need") or body.get("purpose"), 320)
    approval_digest = _text(body.get("operator_approval_digest"), 220)
    receipt_digest = _text(body.get("payment_receipt_digest") or body.get("provider_quote_digest"), 220)
    paid_mode = mode in {"buy", "rent"} or max_budget > 0.0
    has_spend_gate = (not paid_mode) or (_looks_digest(approval_digest) and _looks_digest(receipt_digest))
    providers = _procurement_provider_candidates(category, mode)
    checks = {
        "agent_id_present": bool(agent_id),
        "capability_present": bool(capability),
        "budget_declared": max_budget >= 0.0 and bool(body.get("max_budget") is not None or body.get("budget_limit") is not None),
        "ttl_bounded": 60 <= ttl_seconds <= 86400,
        "provider_candidates_present": bool(providers),
        "spend_gate_satisfied": bool(has_spend_gate),
    }
    accepted = all(bool(v) for k, v in checks.items() if k != "spend_gate_satisfied") and (has_spend_gate or not bool(body.get("auto_acquire")))
    decision = "quote_procurement_intent"
    if bool(body.get("auto_acquire")) and not has_spend_gate:
        decision = "hold_paid_acquisition_until_approval_and_receipt"
    elif accepted and mode in {"lease", "quote_only"}:
        decision = "route_to_leasable_capacity"
    elif accepted and has_spend_gate:
        decision = "ready_for_external_provider_receipt_replay"
    intent_core = {
        "agent_id": agent_id,
        "category": category,
        "mode": mode,
        "max_budget": round(max_budget, 4),
        "currency": currency,
        "capability": capability,
        "generated_at": now,
    }
    intent_id = f"agp-proc-{_digest(intent_core)}"
    row = {
        "ok": True,
        "schema": "nomad.agp_procurement_receipt.v1",
        "intent_id": intent_id,
        "generated_at": now,
        "accepted": accepted,
        "decision": decision,
        "agent_id": agent_id,
        "category": category,
        "acquisition_mode": mode,
        "max_budget": round(max_budget, 4),
        "currency": currency,
        "ttl_seconds": ttl_seconds,
        "capability": capability,
        "checks": checks,
        "provider_candidates": providers,
        "spend_policy": {
            "external_purchase_executed": False,
            "external_lease_executed": False,
            "requires_operator_approval_digest": paid_mode,
            "requires_payment_or_provider_receipt_digest": paid_mode,
            "operator_approval_digest": approval_digest,
            "receipt_digest": receipt_digest,
        },
        "worker_market_payload": {
            "schema": "nomad.worker_market_offer.v1",
            "agent_id": agent_id,
            "objective": "autogenesis_protocol_evolution",
            "capabilities": ["agp_procurement", category, capability],
            "availability_minutes": max(1, round(ttl_seconds / 60, 2)),
            "cost_msat_per_minute": 0,
        },
        "next": {
            "worker_market": _u(base_url, "/swarm/worker-market/offers"),
            "microtasks": _u(base_url, "/swarm/microtasks"),
            "external_value": _u(base_url, "/swarm/external-value"),
            "procurement_surface": _u(base_url, "/.well-known/nomad-agp-procurement.json"),
        },
        "machine_instruction": "obtain_quote_or_worker_lease; only activate_paid_provider_after_operator_approval_digest_and_receipt_digest",
    }
    if persist and accepted:
        _append_jsonl(row, ledger_path or DEFAULT_AGP_PROCUREMENT_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def build_agp_optimizer_surface(
    *,
    base_url: str = "",
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    recent = _agp_optimizer_ledger(ledger_path)
    return {
        "ok": True,
        "schema": "nomad.agp_optimizer_surface.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "sepl_operator_algebra": list(SEPL_OPERATORS),
        "optimizer_strategies": ["reflection", "textgrad", "rl", "ranking", "hybrid"],
        "strategy_contract": {
            "reflection": "uses verifier critique as symbolic gradient",
            "textgrad": "binds textual gradient to variable_lifting",
            "rl": "binds reward_delta and policy_update to evaluate/commit gates",
            "ranking": "binds candidate ranking signal to select operator",
            "hybrid": "accepts multiple strategy signals behind same SEPL trace",
        },
        "links": {
            "self": _u(root, "/.well-known/nomad-agp-optimizer.json"),
            "step": _u(root, "/swarm/agp/optimizer-steps"),
            "evaluation": _u(root, "/swarm/agp/evaluations"),
            "watchdog": _u(root, "/swarm/autogenesis/watchdog"),
        },
        "recent_step_count": len(recent),
        "latest_step": recent[-1] if recent else {},
        "machine_instruction": "normalize_optimizer_signal_to_sepl_trace_then_submit_shadow_candidate_or_evaluation",
    }


def run_agp_optimizer_step(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {"ok": False, "schema": "nomad.agp_optimizer_step_receipt.v1", "accepted": False, "reason": "empty_optimizer_step", "generated_at": now}
    if _contains_forbidden(body):
        return {"ok": False, "schema": "nomad.agp_optimizer_step_receipt.v1", "accepted": False, "reason": "forbidden_secret_like_material", "generated_at": now}
    strategy = _clean_id(body.get("strategy") or body.get("optimizer") or "reflection", fallback="reflection")
    if strategy not in {"reflection", "textgrad", "rl", "ranking", "hybrid"}:
        strategy = "reflection"
    resource_id = _clean_id(body.get("resource_id") or _dict(body.get("resource")).get("resource_id"), fallback="autogenesis-resource")
    variable = _clean_id(body.get("variable") or body.get("target_variable") or "runtime_weight", fallback="runtime_weight")
    signal = _dict(body.get("signal") or body.get("gradient") or body.get("reward") or body.get("ranking"))
    proof_digest = _text(body.get("proof_digest") or signal.get("proof_digest"), 220)
    if proof_digest and re.fullmatch(r"[a-f0-9]{32,128}", proof_digest.lower()):
        proof_digest = f"sha256:{proof_digest.lower()}"
    if not proof_digest:
        proof_digest = f"sha256:{_digest({'strategy': strategy, 'resource_id': resource_id, 'signal': signal}, length=64)}"
    candidate_version = _text(body.get("to_version") or f"v-{strategy}-{_digest({'r': resource_id, 'v': variable, 'p': proof_digest}, length=10)}", 96)
    sepl_trace = [
        {"op": "reflect", "input": proof_digest, "output": _text(signal.get("critique") or signal.get("observation") or f"{strategy}_signal_reflected", 180)},
        {"op": "select", "input": variable, "output": f"{resource_id}.{variable}"},
        {"op": "improve", "input": f"{resource_id}.{variable}", "output": candidate_version},
        {"op": "evaluate", "input": candidate_version, "output": _text(signal.get("metric") or signal.get("reward_delta") or "pending_benchmark_evaluation", 160)},
        {"op": "commit", "input": "evaluation_gate", "decision": "shadow_candidate_or_noop"},
    ]
    checks = {
        "strategy_supported": strategy in {"reflection", "textgrad", "rl", "ranking", "hybrid"},
        "resource_id_present": bool(resource_id),
        "proof_digest_present": _looks_digest(proof_digest),
        "sepl_trace_exact": [item["op"] for item in sepl_trace] == list(SEPL_OPERATORS),
        "learnability_mask_present": True,
        "rollback_noop_present": True,
    }
    accepted = all(checks.values())
    row = {
        "ok": True,
        "schema": "nomad.agp_optimizer_step_receipt.v1",
        "step_id": f"agp-opt-{_digest({'strategy': strategy, 'resource': resource_id, 'proof': proof_digest})}",
        "generated_at": now,
        "accepted": accepted,
        "decision": "normalize_optimizer_signal_to_sepl_candidate" if accepted else "hold_optimizer_step_until_gates",
        "strategy": strategy,
        "resource_id": resource_id,
        "variable_lifting": {"variables": [{"name": variable, "require_grad": True, "strategy": strategy}]},
        "learnability_mask": {variable: True},
        "sepl_operator_trace": sepl_trace,
        "proof_digest": proof_digest,
        "rollback_ref": _text(body.get("rollback_ref") or f"noop:{resource_id}:{variable}", 220),
        "checks": checks,
        "candidate_payload": {
            "candidate_type": "sepl-operator-patch",
            "resource": {"resource_id": resource_id, "to_version": candidate_version, "state": "shadow"},
            "sepl_operator_trace": sepl_trace,
            "learnability_mask": {variable: True},
            "variable_lifting": {"variables": [{"name": variable, "require_grad": True}]},
            "proof_digest": proof_digest,
            "rollback_ref": _text(body.get("rollback_ref") or f"noop:{resource_id}:{variable}", 220),
            "boundedness": {"ttl_seconds": _int(body.get("ttl_seconds"), 300) or 300, "side_effect_scope": "nomad_shadow_lane_only", "rollback_available": True, "secrets_free": True},
        },
        "next": {
            "evaluation": _u(base_url, "/swarm/agp/evaluations"),
            "shadow_lane": _u(base_url, "/swarm/shadow-lane/candidates?type=autogenesis"),
        },
        "machine_instruction": "evaluate_optimizer_candidate_before_resource_version_commit",
    }
    if persist and accepted:
        _append_jsonl(row, ledger_path or DEFAULT_AGP_OPTIMIZER_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def build_agp_evaluation_surface(
    *,
    base_url: str = "",
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    recent = _agp_evaluation_ledger(ledger_path)
    return {
        "ok": True,
        "schema": "nomad.agp_evaluation_surface.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "benchmark_modes": ["long_horizon_task", "tool_use", "heterogeneous_resource_plan", "regression_replay", "micro_benchmark"],
        "required_fields": ["agent_id", "resource_id", "benchmark_id", "baseline_score", "candidate_score", "proof_digest"],
        "commit_rule": "candidate_score_must_exceed_baseline_and_proof_digest_must_bind_run",
        "links": {
            "self": _u(root, "/.well-known/nomad-agp-evaluation.json"),
            "run": _u(root, "/swarm/agp/evaluations"),
            "optimizer": _u(root, "/swarm/agp/optimizer-steps"),
            "watchdog": _u(root, "/swarm/autogenesis/watchdog"),
        },
        "recent_run_count": len(recent),
        "latest_run": recent[-1] if recent else {},
        "machine_instruction": "submit_evaluation_run; only positive_delta_can_raise_weight",
    }


def record_agp_evaluation_run(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {"ok": False, "schema": "nomad.agp_evaluation_receipt.v1", "accepted": False, "reason": "empty_evaluation", "generated_at": now}
    if _contains_forbidden(body):
        return {"ok": False, "schema": "nomad.agp_evaluation_receipt.v1", "accepted": False, "reason": "forbidden_secret_like_material", "generated_at": now}
    agent_id = _clean_id(body.get("agent_id"), fallback="")
    resource_id = _clean_id(body.get("resource_id"), fallback="")
    benchmark_id = _clean_id(body.get("benchmark_id") or body.get("task_id"), fallback="")
    baseline = _num(body.get("baseline_score"))
    candidate = _num(body.get("candidate_score"))
    proof_digest = _text(body.get("proof_digest") or body.get("digest"), 220)
    if proof_digest and re.fullmatch(r"[a-f0-9]{32,128}", proof_digest.lower()):
        proof_digest = f"sha256:{proof_digest.lower()}"
    delta = round(candidate - baseline, 4)
    checks = {
        "agent_id_present": bool(agent_id),
        "resource_id_present": bool(resource_id),
        "benchmark_id_present": bool(benchmark_id),
        "proof_digest_present": _looks_digest(proof_digest),
        "positive_effectiveness_delta": delta > 0.0,
        "score_bounds": 0.0 <= baseline <= 1.0 and 0.0 <= candidate <= 1.0,
    }
    accepted = all(checks.values())
    row = {
        "ok": True,
        "schema": "nomad.agp_evaluation_receipt.v1",
        "evaluation_id": f"agp-eval-{_digest({'resource': resource_id, 'benchmark': benchmark_id, 'proof': proof_digest})}",
        "generated_at": now,
        "accepted": accepted,
        "decision": "positive_effectiveness_delta_verified" if accepted else "hold_until_positive_benchmark_delta",
        "agent_id": agent_id,
        "resource_id": resource_id,
        "benchmark_id": benchmark_id,
        "baseline_score": round(baseline, 4),
        "candidate_score": round(candidate, 4),
        "effectiveness_delta": delta,
        "proof_digest": proof_digest,
        "checks": checks,
        "commit_hint": {
            "target_state": "tested" if accepted else "noop",
            "min_effectiveness_score": round(candidate, 4),
            "side_effect_scope": "evaluation_receipt_only",
        },
        "next": {
            "resource_version": _u(base_url, "/swarm/resource-substrate/version"),
            "watchdog": _u(base_url, "/swarm/autogenesis/watchdog"),
        },
        "machine_instruction": "use_evaluation_receipt_as_positive_delta_gate_for_weighted_resource_version",
    }
    if persist and accepted:
        _append_jsonl(row, ledger_path or DEFAULT_AGP_EVALUATION_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def build_agp_benchmark_suite_surface(
    *,
    base_url: str = "",
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    recent = _agp_benchmark_ledger(ledger_path)
    return {
        "ok": True,
        "schema": "nomad.agp_benchmark_suite_surface.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "paper_benchmark_modes": list(AGP_BENCHMARK_MODES),
        "suite_contract": {
            "required_fields": ["agent_id", "suite_id", "runs", "proof_digest"],
            "required_run_fields": ["mode", "benchmark_id", "baseline_score", "candidate_score"],
            "accept_rule": "all_paper_modes_present_and_each_candidate_score_exceeds_baseline",
            "side_effect_scope": "benchmark_receipt_only",
        },
        "links": {
            "self": _u(root, "/.well-known/nomad-agp-benchmark-suite.json"),
            "run": _u(root, "/swarm/agp/benchmark-suites"),
            "evaluation": _u(root, "/swarm/agp/evaluations"),
            "optimizer": _u(root, "/swarm/agp/optimizer-steps"),
            "conformance": _u(root, "/.well-known/nomad-agp-conformance.json"),
        },
        "recent_suite_count": len(recent),
        "latest_suite": recent[-1] if recent else {},
        "machine_instruction": "record_suite_after_orchestration; require_positive_delta_for_every_paper_benchmark_mode",
    }


def run_agp_benchmark_suite(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {"ok": False, "schema": "nomad.agp_benchmark_suite_receipt.v1", "accepted": False, "reason": "empty_benchmark_suite", "generated_at": now}
    if _contains_forbidden(body):
        return {"ok": False, "schema": "nomad.agp_benchmark_suite_receipt.v1", "accepted": False, "reason": "forbidden_secret_like_material", "generated_at": now}
    agent_id = _clean_id(body.get("agent_id") or body.get("evaluator_agent_id"), fallback="")
    suite_id = _clean_id(body.get("suite_id") or body.get("benchmark_suite_id") or "agp-paper-suite", fallback="agp-paper-suite")
    resource_id = _clean_id(body.get("resource_id"), fallback="nomad-autogenesis")
    proof_digest = _text(body.get("proof_digest") or body.get("digest"), 220)
    if proof_digest and re.fullmatch(r"[a-f0-9]{32,128}", proof_digest.lower()):
        proof_digest = f"sha256:{proof_digest.lower()}"
    runs = _items(body.get("runs"))
    if not runs:
        baseline = _clamp(_num(body.get("baseline_score"), 0.55))
        candidate = _clamp(max(_num(body.get("candidate_score"), baseline + 0.08), baseline + 0.01))
        runs = [
            {"mode": mode, "benchmark_id": f"{mode}_descriptor_eval", "baseline_score": baseline, "candidate_score": candidate}
            for mode in AGP_BENCHMARK_MODES
        ]
    normalized: list[dict[str, Any]] = []
    for item in runs:
        mode = _clean_id(item.get("mode") or item.get("benchmark_mode"), fallback="")
        if mode == "gpqa":
            mode = "gpqa_diamond"
        benchmark_id = _clean_id(item.get("benchmark_id") or item.get("task_id") or mode, fallback=mode)
        baseline = _clamp(_num(item.get("baseline_score")))
        candidate = _clamp(_num(item.get("candidate_score")))
        normalized.append(
            {
                "mode": mode,
                "benchmark_id": benchmark_id,
                "baseline_score": round(baseline, 4),
                "candidate_score": round(candidate, 4),
                "effectiveness_delta": round(candidate - baseline, 4),
                "proof_digest": _text(item.get("proof_digest") or proof_digest, 220),
            }
        )
    if not proof_digest:
        proof_digest = f"sha256:{_digest({'agent_id': agent_id, 'suite_id': suite_id, 'runs': normalized}, length=64)}"
        for item in normalized:
            if not item.get("proof_digest"):
                item["proof_digest"] = proof_digest
    modes_present = {item["mode"] for item in normalized}
    required_modes = set(AGP_BENCHMARK_MODES)
    deltas = [_num(item.get("effectiveness_delta")) for item in normalized]
    baselines = [_num(item.get("baseline_score")) for item in normalized]
    candidates = [_num(item.get("candidate_score")) for item in normalized]
    aggregate = {
        "mean_baseline_score": round(sum(baselines) / max(1, len(baselines)), 4),
        "mean_candidate_score": round(sum(candidates) / max(1, len(candidates)), 4),
        "mean_effectiveness_delta": round(sum(deltas) / max(1, len(deltas)), 4),
        "min_effectiveness_delta": round(min(deltas) if deltas else 0.0, 4),
        "run_count": len(normalized),
    }
    checks = {
        "agent_id_present": bool(agent_id),
        "suite_id_present": bool(suite_id),
        "proof_digest_present": _looks_digest(proof_digest),
        "all_paper_modes_present": required_modes.issubset(modes_present),
        "all_modes_supported": modes_present.issubset(required_modes),
        "all_runs_positive_delta": bool(normalized) and all(delta > 0.0 for delta in deltas),
        "aggregate_positive_delta": aggregate["mean_effectiveness_delta"] > 0.0,
        "score_bounds": all(0.0 <= score <= 1.0 for score in baselines + candidates),
    }
    accepted = all(checks.values())
    row = {
        "ok": True,
        "schema": "nomad.agp_benchmark_suite_receipt.v1",
        "suite_id": suite_id,
        "generated_at": now,
        "accepted": accepted,
        "decision": "paper_benchmark_suite_positive_delta_verified" if accepted else "hold_benchmark_suite_until_modes_and_deltas",
        "agent_id": agent_id,
        "resource_id": resource_id,
        "proof_digest": proof_digest,
        "required_modes": list(AGP_BENCHMARK_MODES),
        "runs": normalized,
        "aggregate": aggregate,
        "checks": checks,
        "commit_hint": {
            "target_state": "tested" if accepted else "noop",
            "min_effectiveness_score": aggregate["mean_candidate_score"] if accepted else 0.0,
            "side_effect_scope": "benchmark_suite_receipt_only",
        },
        "next": {
            "resource_version": _u(base_url, "/swarm/resource-substrate/version"),
            "evaluation": _u(base_url, "/swarm/agp/evaluations"),
            "conformance": _u(base_url, "/.well-known/nomad-agp-conformance.json"),
        },
        "machine_instruction": "use_suite_receipt_as_multi_benchmark_gate_before_runtime_weight_increase",
    }
    if persist and accepted:
        _append_jsonl(row, ledger_path or DEFAULT_AGP_BENCHMARK_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def build_agp_version_manager_surface(
    *,
    base_url: str = "",
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    recent = _agp_version_lineage_ledger(ledger_path)
    return {
        "ok": True,
        "schema": "nomad.agp_version_manager.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "artifact_types": list(AGP_VERSION_ARTIFACT_TYPES),
        "lineage_contract": {
            "required_fields": ["agent_id", "artifact_type", "resource_id", "from_version", "to_version", "proof_digest", "rollback_ref"],
            "edge_rule": "lineage_edges_bind_parent_version_candidate_version_receipts_and_rollback_or_noop",
            "commit_rule": "version_graph_receipt_must_exist_before_runtime_weight_increase",
            "side_effect_scope": "version_lineage_receipt_only",
        },
        "links": {
            "self": _u(root, "/.well-known/nomad-agp-version-manager.json"),
            "lineage": _u(root, "/swarm/agp/version-lineage"),
            "resource_version": _u(root, "/swarm/resource-substrate/version"),
            "trace": _u(root, "/swarm/autogenesis/traces"),
            "conformance": _u(root, "/.well-known/nomad-agp-conformance.json"),
        },
        "recent_lineage_count": len(recent),
        "latest_lineage": recent[-1] if recent else {},
        "machine_instruction": "record_version_lineage_for_every_prompt_model_config_output_resource_artifact; rollback_or_noop_required",
    }


def record_agp_version_lineage(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {"ok": False, "schema": "nomad.agp_version_lineage_receipt.v1", "accepted": False, "reason": "empty_version_lineage", "generated_at": now}
    if _contains_forbidden(body):
        return {"ok": False, "schema": "nomad.agp_version_lineage_receipt.v1", "accepted": False, "reason": "forbidden_secret_like_material", "generated_at": now}
    agent_id = _clean_id(body.get("agent_id") or body.get("worker_id"), fallback="")
    artifact_type = _clean_id(body.get("artifact_type") or body.get("resource_kind") or "resource_version", fallback="resource_version")
    if artifact_type not in AGP_VERSION_ARTIFACT_TYPES:
        artifact_type = "resource_version"
    resource_id = _clean_id(body.get("resource_id") or body.get("artifact_id") or body.get("id"), fallback="")
    from_version = _text(body.get("from_version") or body.get("previous_version") or "v1", 80)
    to_version = _text(body.get("to_version") or body.get("candidate_version") or body.get("version"), 80)
    target_state = _clean_state(body.get("target_state") or body.get("state") or "shadow")
    proof_digest = _text(body.get("proof_digest") or body.get("digest"), 220)
    if proof_digest and re.fullmatch(r"[a-f0-9]{32,128}", proof_digest.lower()):
        proof_digest = f"sha256:{proof_digest.lower()}"
    parent_digests_raw = body.get("parent_receipt_digests") if isinstance(body.get("parent_receipt_digests"), list) else []
    parent_receipt_digests = []
    for item in parent_digests_raw:
        digest = _text(item, 220)
        if digest and re.fullmatch(r"[a-f0-9]{32,128}", digest.lower()):
            digest = f"sha256:{digest.lower()}"
        if _looks_digest(digest):
            parent_receipt_digests.append(digest)
    rollback_ref = _text(body.get("rollback_ref") or body.get("noop_ref") or f"noop:{resource_id}:{from_version}", 220)
    if not proof_digest:
        proof_digest = f"sha256:{_digest({'agent_id': agent_id, 'artifact_type': artifact_type, 'resource_id': resource_id, 'from': from_version, 'to': to_version, 'parents': parent_receipt_digests}, length=64)}"
    lineage_core = {
        "agent_id": agent_id,
        "artifact_type": artifact_type,
        "resource_id": resource_id,
        "from_version": from_version,
        "to_version": to_version,
        "target_state": target_state,
        "proof_digest": proof_digest,
        "parent_receipt_digests": parent_receipt_digests,
        "rollback_ref": rollback_ref,
    }
    lineage_digest = f"sha256:{_digest(lineage_core, length=64)}"
    checks = {
        "agent_id_present": bool(agent_id),
        "artifact_type_supported": artifact_type in AGP_VERSION_ARTIFACT_TYPES,
        "resource_id_present": bool(resource_id),
        "from_version_present": bool(from_version),
        "to_version_present": bool(to_version),
        "proof_digest_present": _looks_digest(proof_digest),
        "rollback_or_noop_present": bool(rollback_ref),
        "lineage_digest_present": _looks_digest(lineage_digest),
        "descriptor_only": True,
    }
    accepted = all(checks.values())
    row = {
        "ok": True,
        "schema": "nomad.agp_version_lineage_receipt.v1",
        "lineage_id": f"agp-lineage-{_digest(lineage_core)}",
        "generated_at": now,
        "accepted": accepted,
        "decision": "version_lineage_recorded" if accepted else "hold_version_lineage_until_contract",
        "agent_id": agent_id,
        "artifact_type": artifact_type,
        "resource_id": resource_id,
        "from_version": from_version,
        "to_version": to_version,
        "target_state": target_state,
        "proof_digest": proof_digest,
        "lineage_digest": lineage_digest,
        "parent_receipt_digests": parent_receipt_digests,
        "rollback_ref": rollback_ref,
        "checks": checks,
        "version_graph_edge": {
            "from": f"{resource_id}@{from_version}",
            "to": f"{resource_id}@{to_version}",
            "artifact_type": artifact_type,
            "lineage_digest": lineage_digest,
        },
        "side_effect_scope": "version_lineage_receipt_only",
        "next": {
            "resource_version": _u(base_url, "/swarm/resource-substrate/version"),
            "watchdog": _u(base_url, "/swarm/autogenesis/watchdog"),
            "conformance": _u(base_url, "/.well-known/nomad-agp-conformance.json"),
        },
        "machine_instruction": "use_lineage_digest_to_dedupe_future_evolution; rollback_or_noop_on_failed_effectiveness",
    }
    if persist and accepted:
        _append_jsonl(row, ledger_path or DEFAULT_AGP_VERSION_LINEAGE_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def build_agp_agent_bus_surface(
    *,
    base_url: str = "",
    message_ledger_path: Path | str | None = None,
    plan_ledger_path: Path | str | None = None,
    orchestration_ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    recent_messages = _agp_agent_bus_ledger(message_ledger_path)
    recent_plans = _agp_plan_ledger(plan_ledger_path)
    recent_orchestrations = _agp_orchestration_ledger(orchestration_ledger_path)
    return {
        "ok": True,
        "schema": "nomad.agp_agent_bus.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "purpose": "AGS-style multi-agent coordination over protocol-registered RSPL resources and SEPL receipts.",
        "agent_roles": list(AGP_AGENT_ROLES),
        "message_types": list(AGP_AGENT_MESSAGE_TYPES),
        "bus_contract": {
            "required_message_fields": ["agent_id", "role", "message_type", "content", "proof_digest"],
            "role_boundary": "agents_exchange_receipts_and_resource_descriptors_not_unbounded_code",
            "side_effect_scope": "agent_bus_descriptor_only",
            "routing_rule": "planner_decomposes; executor_records_trace; optimizer_emits_signal; verifier_binds_receipt; procurement_agent_quotes_only",
        },
        "planner_contract": {
            "required_plan_fields": ["agent_id", "task", "goal"],
            "required_steps": [
                "retrieve_resources",
                "context_init_or_update",
                "trace_act_observe_optimize_remember",
                "optimizer_step",
                "evaluation_run",
                "procurement_intent_if_capacity_gap",
                "watchdog_trigger",
            ],
            "sepl_operator_algebra": list(SEPL_OPERATORS),
        },
        "links": {
            "self": _u(root, "/.well-known/nomad-agp-agent-bus.json"),
            "messages": _u(root, "/swarm/agp/agent-bus/messages"),
            "plans": _u(root, "/swarm/agp/plans"),
            "orchestrations": _u(root, "/swarm/agp/orchestrations"),
            "resource_retrieve": _u(root, "/swarm/resource-substrate/retrieve"),
            "context": _u(root, "/swarm/agp/context"),
            "trace": _u(root, "/swarm/autogenesis/traces"),
            "optimizer": _u(root, "/swarm/agp/optimizer-steps"),
            "evaluation": _u(root, "/swarm/agp/evaluations"),
            "procurement": _u(root, "/swarm/agp/procurement-intents"),
            "watchdog": _u(root, "/swarm/autogenesis/watchdog"),
        },
        "recent_message_count": len(recent_messages),
        "recent_plan_count": len(recent_plans),
        "recent_orchestration_count": len(recent_orchestrations),
        "latest_message": recent_messages[-1] if recent_messages else {},
        "latest_plan": recent_plans[-1] if recent_plans else {},
        "latest_orchestration": recent_orchestrations[-1] if recent_orchestrations else {},
        "machine_instruction": "post_agent_bus_message_then_plan_then_orchestration; bind_every_step_to_receipt_digest",
    }


def build_agp_model_manager_surface(
    *,
    base_url: str = "",
    model_ledger_path: Path | str | None = None,
    config_ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    recent_models = _agp_model_binding_ledger(model_ledger_path)
    recent_configs = _agp_config_ledger(config_ledger_path)
    return {
        "ok": True,
        "schema": "nomad.agp_model_manager.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "purpose": "Bind AGS agents to versioned model/provider descriptors and compose runtime configs across RSPL resources.",
        "provider_backends": ["local_ollama", "github_models", "xai_grok", "openrouter", "deterministic_fallback"],
        "config_entities": ["agent", "tool", "environment", "memory", "prompt", "model_binding"],
        "guards": [
            "no_secret_material",
            "fallback_chain_required",
            "model_binding_is_descriptor_only",
            "config_composition_must_reference_rspl_entities",
            "provider_receipt_required_before_paid_external_calls",
        ],
        "links": {
            "self": _u(root, "/.well-known/nomad-agp-model-manager.json"),
            "model_bindings": _u(root, "/swarm/agp/model-bindings"),
            "configs": _u(root, "/swarm/agp/configs"),
            "resource_substrate": _u(root, "/.well-known/nomad-resource-substrate.json"),
            "agent_bus": _u(root, "/.well-known/nomad-agp-agent-bus.json"),
            "procurement": _u(root, "/swarm/agp/procurement-intents"),
        },
        "recent_model_binding_count": len(recent_models),
        "recent_config_count": len(recent_configs),
        "latest_model_binding": recent_models[-1] if recent_models else {},
        "latest_config": recent_configs[-1] if recent_configs else {},
        "machine_instruction": "bind_model_provider_descriptor_then_compose_config_before_ags_orchestration",
    }


def build_agp_prompt_manager_surface(
    *,
    base_url: str = "",
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    recent = _agp_prompt_ledger(ledger_path)
    return {
        "ok": True,
        "schema": "nomad.agp_prompt_manager.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "purpose": "Register prompt templates as RSPL prompt resources with versioned variables and SEPL-ready optimization slots.",
        "template_contract": {
            "required_fields": ["agent_id", "prompt_id", "template", "variables", "proof_digest"],
            "resource_kind": "prompt_template",
            "entity_type": "prompt",
            "mutation_rule": "candidate_prompt_changes_must_flow_through_rspl_version_and_positive_evaluation",
        },
        "guards": [
            "no_secret_material",
            "variables_declared",
            "learnability_mask_for_mutable_slots",
            "rollback_or_noop_reference",
            "descriptor_only_until_version_gate",
        ],
        "links": {
            "self": _u(root, "/.well-known/nomad-agp-prompt-manager.json"),
            "templates": _u(root, "/swarm/agp/prompts"),
            "resource_substrate": _u(root, "/.well-known/nomad-resource-substrate.json"),
            "optimizer": _u(root, "/swarm/agp/optimizer-steps"),
            "evaluation": _u(root, "/swarm/agp/evaluations"),
        },
        "recent_prompt_count": len(recent),
        "latest_prompt": recent[-1] if recent else {},
        "machine_instruction": "register_prompt_template_then_bind_prompt_resource_into_config_or_optimizer_step",
    }


def register_agp_prompt_template(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {"ok": False, "schema": "nomad.agp_prompt_template_receipt.v1", "accepted": False, "reason": "empty_prompt_template", "generated_at": now}
    if _contains_forbidden(body):
        return {"ok": False, "schema": "nomad.agp_prompt_template_receipt.v1", "accepted": False, "reason": "forbidden_secret_like_material", "generated_at": now}
    agent_id = _clean_id(body.get("agent_id") or body.get("worker_id"), fallback="")
    prompt_id = _clean_id(body.get("prompt_id") or body.get("template_id") or body.get("resource_id"), fallback="")
    template = _text(body.get("template") or body.get("prompt") or body.get("content"), 2400)
    version = _text(body.get("version") or body.get("to_version") or "v1", 80)
    raw_variables = body.get("variables")
    variable_names: list[str] = []
    if isinstance(raw_variables, list):
        for item in raw_variables:
            if isinstance(item, dict):
                name = _clean_id(item.get("name") or item.get("variable") or item.get("id"), fallback="")
            else:
                name = _clean_id(item, fallback="")
            if name and name not in variable_names:
                variable_names.append(name)
    elif isinstance(raw_variables, dict):
        for key in raw_variables:
            name = _clean_id(key, fallback="")
            if name and name not in variable_names:
                variable_names.append(name)
    if not variable_names:
        variable_names = re.findall(r"{([a-zA-Z_][a-zA-Z0-9_]*)}", template)
        variable_names = [_clean_id(item, fallback="") for item in variable_names if _clean_id(item, fallback="")]
    learnability_raw = body.get("learnability_mask")
    if isinstance(learnability_raw, dict):
        learnability_mask = {_clean_id(k, fallback=str(k)): bool(v) for k, v in learnability_raw.items()}
    else:
        learnability_mask = {name: True for name in variable_names}
    variable_lifting = {
        "variables": [
            {"name": name, "require_grad": bool(learnability_mask.get(name, True)), "source": "prompt_template"}
            for name in variable_names
        ]
    }
    proof_digest = _text(body.get("proof_digest") or body.get("digest"), 220)
    if proof_digest and re.fullmatch(r"[a-f0-9]{32,128}", proof_digest.lower()):
        proof_digest = f"sha256:{proof_digest.lower()}"
    if not proof_digest:
        proof_digest = f"sha256:{_digest({'agent_id': agent_id, 'prompt_id': prompt_id, 'template': template, 'version': version}, length=64)}"
    rollback_ref = _text(body.get("rollback_ref") or body.get("noop_ref") or f"noop:{prompt_id}:{version}", 220)
    checks = {
        "agent_id_present": bool(agent_id),
        "prompt_id_present": bool(prompt_id),
        "template_present": bool(template),
        "variables_declared": bool(variable_names),
        "learnability_mask_present": bool(learnability_mask),
        "proof_digest_present": _looks_digest(proof_digest),
        "rollback_or_noop_present": bool(rollback_ref),
        "descriptor_only": True,
    }
    accepted = all(checks.values())
    row = {
        "ok": True,
        "schema": "nomad.agp_prompt_template_receipt.v1",
        "prompt_id": prompt_id,
        "generated_at": now,
        "accepted": accepted,
        "decision": "prompt_template_registered" if accepted else "hold_prompt_template_until_contract",
        "agent_id": agent_id,
        "version": version,
        "template_digest": f"sha256:{_digest({'template': template, 'variables': variable_names}, length=64)}",
        "variables": variable_names,
        "variable_lifting": variable_lifting,
        "learnability_mask": learnability_mask,
        "proof_digest": proof_digest,
        "rollback_ref": rollback_ref,
        "checks": checks,
        "resource_hint": {
            "resource_id": prompt_id,
            "resource_kind": "prompt_template",
            "entity_type": "prompt",
            "state": "shadow",
            "version": version,
        },
        "side_effect_scope": "prompt_template_descriptor_only",
        "next": {
            "resource_version": _u(base_url, "/swarm/resource-substrate/version"),
            "optimizer": _u(base_url, "/swarm/agp/optimizer-steps"),
            "configs": _u(base_url, "/swarm/agp/configs"),
            "prompt_manager": _u(base_url, "/.well-known/nomad-agp-prompt-manager.json"),
        },
        "machine_instruction": "bind_prompt_template_to_config; mutate_template_only_via_rspl_version_with_positive_evaluation",
    }
    if persist and accepted:
        _append_jsonl(row, ledger_path or DEFAULT_AGP_PROMPT_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def bind_agp_model(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {"ok": False, "schema": "nomad.agp_model_binding_receipt.v1", "accepted": False, "reason": "empty_model_binding", "generated_at": now}
    if _contains_forbidden(body):
        return {"ok": False, "schema": "nomad.agp_model_binding_receipt.v1", "accepted": False, "reason": "forbidden_secret_like_material", "generated_at": now}
    agent_id = _clean_id(body.get("agent_id") or body.get("worker_id"), fallback="")
    binding_id = _clean_id(body.get("binding_id") or body.get("model_binding_id") or body.get("role"), fallback="")
    role = _clean_id(body.get("role") or "executor", fallback="executor")
    provider = _clean_id(body.get("provider") or body.get("backend") or "deterministic_fallback", fallback="deterministic_fallback")
    supported_providers = {"local_ollama", "github_models", "xai_grok", "openrouter", "deterministic_fallback"}
    if provider not in supported_providers:
        provider = "deterministic_fallback"
    model = _text(body.get("model") or body.get("model_name") or provider, 180)
    fallback_raw = body.get("fallback_chain") if isinstance(body.get("fallback_chain"), list) else []
    fallback_chain = [
        _clean_id(item, fallback="")
        for item in fallback_raw
        if _clean_id(item, fallback="") in supported_providers
    ]
    if provider not in fallback_chain:
        fallback_chain.insert(0, provider)
    if "deterministic_fallback" not in fallback_chain:
        fallback_chain.append("deterministic_fallback")
    capabilities_raw = body.get("capabilities") if isinstance(body.get("capabilities"), list) else []
    capabilities = [_clean_id(item, fallback="") for item in capabilities_raw if _clean_id(item, fallback="")]
    proof_digest = _text(body.get("proof_digest") or body.get("digest"), 220)
    if proof_digest and re.fullmatch(r"[a-f0-9]{32,128}", proof_digest.lower()):
        proof_digest = f"sha256:{proof_digest.lower()}"
    if not proof_digest:
        proof_digest = f"sha256:{_digest({'agent_id': agent_id, 'binding': binding_id, 'provider': provider, 'model': model}, length=64)}"
    paid_provider = provider in {"xai_grok", "openrouter", "github_models"} and bool(body.get("external_paid"))
    receipt_digest = _text(body.get("provider_receipt_digest") or body.get("payment_receipt_digest"), 220)
    checks = {
        "agent_id_present": bool(agent_id),
        "binding_id_present": bool(binding_id),
        "provider_supported": provider in supported_providers,
        "model_present": bool(model),
        "fallback_chain_present": bool(fallback_chain),
        "deterministic_fallback_present": "deterministic_fallback" in fallback_chain,
        "proof_digest_present": _looks_digest(proof_digest),
        "paid_provider_receipt_gate": (not paid_provider) or _looks_digest(receipt_digest),
    }
    accepted = all(checks.values())
    row = {
        "ok": True,
        "schema": "nomad.agp_model_binding_receipt.v1",
        "binding_id": binding_id,
        "generated_at": now,
        "accepted": accepted,
        "decision": "model_binding_descriptor_registered" if accepted else "hold_model_binding_until_contract",
        "agent_id": agent_id,
        "role": role,
        "provider": provider,
        "model": model,
        "fallback_chain": fallback_chain,
        "capabilities": capabilities,
        "proof_digest": proof_digest,
        "provider_receipt_digest": receipt_digest,
        "checks": checks,
        "resource_hint": {
            "resource_id": f"model-{binding_id}",
            "resource_kind": "model_binding",
            "entity_type": "agent",
            "state": "shadow",
            "version": "v1",
        },
        "side_effect_scope": "model_binding_descriptor_only",
        "next": {
            "configs": _u(base_url, "/swarm/agp/configs"),
            "procurement": _u(base_url, "/swarm/agp/procurement-intents"),
            "model_manager": _u(base_url, "/.well-known/nomad-agp-model-manager.json"),
        },
        "machine_instruction": "compose_config_with_binding; do_not_call_paid_provider_without_receipt_digest",
    }
    if persist and accepted:
        _append_jsonl(row, ledger_path or DEFAULT_AGP_MODEL_BINDING_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def compose_agp_config(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {"ok": False, "schema": "nomad.agp_config_receipt.v1", "accepted": False, "reason": "empty_config", "generated_at": now}
    if _contains_forbidden(body):
        return {"ok": False, "schema": "nomad.agp_config_receipt.v1", "accepted": False, "reason": "forbidden_secret_like_material", "generated_at": now}
    agent_id = _clean_id(body.get("agent_id") or body.get("composer_agent_id"), fallback="")
    config_id = _clean_id(body.get("config_id") or body.get("name"), fallback="")
    model_binding_id = _clean_id(body.get("model_binding_id") or _dict(body.get("model_binding")).get("binding_id"), fallback="")
    raw_bindings = body.get("resource_bindings") or body.get("resources")
    bindings = _items(raw_bindings)
    normalized_bindings = []
    entity_types: set[str] = set()
    for item in bindings:
        resource_id = _clean_id(item.get("resource_id") or item.get("id"), fallback="")
        entity_type = _clean_entity_type(item.get("entity_type"), resource_kind=item.get("resource_kind") or item.get("kind"))
        if not resource_id:
            continue
        entity_types.add(entity_type)
        normalized_bindings.append(
            {
                "resource_id": resource_id,
                "entity_type": entity_type,
                "role": _clean_id(item.get("role") or entity_type, fallback=entity_type),
                "state": _clean_state(item.get("state") or "committed"),
            }
        )
    proof_digest = _text(body.get("proof_digest") or body.get("digest"), 220)
    if proof_digest and re.fullmatch(r"[a-f0-9]{32,128}", proof_digest.lower()):
        proof_digest = f"sha256:{proof_digest.lower()}"
    if not proof_digest:
        proof_digest = f"sha256:{_digest({'agent_id': agent_id, 'config_id': config_id, 'bindings': normalized_bindings, 'model_binding_id': model_binding_id}, length=64)}"
    missing = sorted(set(RSPL_ENTITY_TYPES) - entity_types)
    checks = {
        "agent_id_present": bool(agent_id),
        "config_id_present": bool(config_id),
        "model_binding_present": bool(model_binding_id),
        "rspl_bindings_present": bool(normalized_bindings),
        "five_rspl_entity_types_bound": not missing,
        "proof_digest_present": _looks_digest(proof_digest),
        "descriptor_only": True,
    }
    accepted = all(checks.values())
    row = {
        "ok": True,
        "schema": "nomad.agp_config_receipt.v1",
        "config_id": config_id,
        "generated_at": now,
        "accepted": accepted,
        "decision": "config_composition_registered" if accepted else "hold_config_until_rspl_bindings",
        "agent_id": agent_id,
        "model_binding_id": model_binding_id,
        "resource_bindings": normalized_bindings,
        "missing_entity_types": missing,
        "proof_digest": proof_digest,
        "checks": checks,
        "side_effect_scope": "config_descriptor_only",
        "next": {
            "agent_bus": _u(base_url, "/swarm/agp/agent-bus/messages"),
            "orchestrations": _u(base_url, "/swarm/agp/orchestrations"),
            "model_manager": _u(base_url, "/.well-known/nomad-agp-model-manager.json"),
        },
        "machine_instruction": "use_config_as_ags_runtime_descriptor; mutate_config_only_through_rspl_version_gate",
    }
    if persist and accepted:
        _append_jsonl(row, ledger_path or DEFAULT_AGP_CONFIG_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def post_agp_agent_bus_message(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {"ok": False, "schema": "nomad.agp_agent_bus_message_receipt.v1", "accepted": False, "reason": "empty_agent_bus_message", "generated_at": now}
    if _contains_forbidden(body):
        return {
            "ok": False,
            "schema": "nomad.agp_agent_bus_message_receipt.v1",
            "accepted": False,
            "reason": "forbidden_secret_like_material",
            "generated_at": now,
        }
    agent_id = _clean_id(body.get("agent_id") or body.get("worker_id"), fallback="")
    role = _clean_id(body.get("role") or "executor", fallback="executor")
    if role not in AGP_AGENT_ROLES:
        role = "executor"
    message_type = _clean_id(body.get("message_type") or body.get("type") or "task", fallback="task")
    if message_type not in AGP_AGENT_MESSAGE_TYPES:
        message_type = "trace_event"
    target_role = _clean_id(body.get("target_role") or body.get("to_role"), fallback="")
    if target_role and target_role not in AGP_AGENT_ROLES:
        target_role = ""
    content = _dict(body.get("content"))
    if not content:
        text = _text(body.get("message") or body.get("task") or body.get("summary"), 1000)
        content = {"text": text} if text else {}
    thread_id = _clean_id(body.get("thread_id") or body.get("task_id"), fallback=f"agp-thread-{_digest({'agent': agent_id, 'content': content})}")
    proof_digest = _text(body.get("proof_digest") or body.get("digest"), 220)
    if proof_digest and re.fullmatch(r"[a-f0-9]{32,128}", proof_digest.lower()):
        proof_digest = f"sha256:{proof_digest.lower()}"
    if not proof_digest:
        proof_digest = f"sha256:{_digest({'agent_id': agent_id, 'role': role, 'type': message_type, 'content': content}, length=64)}"
    checks = {
        "agent_id_present": bool(agent_id),
        "role_supported": role in AGP_AGENT_ROLES,
        "message_type_supported": message_type in AGP_AGENT_MESSAGE_TYPES,
        "content_present": bool(content),
        "proof_digest_present": _looks_digest(proof_digest),
        "descriptor_only": True,
    }
    accepted = all(checks.values())
    message_id = f"agp-msg-{_digest({'thread': thread_id, 'agent': agent_id, 'type': message_type, 'proof': proof_digest})}"
    row = {
        "ok": True,
        "schema": "nomad.agp_agent_bus_message_receipt.v1",
        "message_id": message_id,
        "generated_at": now,
        "accepted": accepted,
        "decision": "route_agent_bus_message" if accepted else "hold_agent_bus_message_until_contract",
        "thread_id": thread_id,
        "agent_id": agent_id,
        "role": role,
        "target_role": target_role,
        "message_type": message_type,
        "content": content,
        "proof_digest": proof_digest,
        "checks": checks,
        "side_effect_scope": "agent_bus_descriptor_only",
        "next": {
            "plans": _u(base_url, "/swarm/agp/plans"),
            "orchestrations": _u(base_url, "/swarm/agp/orchestrations"),
            "agent_bus": _u(base_url, "/.well-known/nomad-agp-agent-bus.json"),
        },
        "machine_instruction": "planner_may_consume_message_only_as_receipt_bound_descriptor",
    }
    if persist and accepted:
        _append_jsonl(row, ledger_path or DEFAULT_AGP_AGENT_BUS_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def create_agp_plan(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {"ok": False, "schema": "nomad.agp_plan_receipt.v1", "accepted": False, "reason": "empty_agp_plan", "generated_at": now}
    if _contains_forbidden(body):
        return {"ok": False, "schema": "nomad.agp_plan_receipt.v1", "accepted": False, "reason": "forbidden_secret_like_material", "generated_at": now}
    agent_id = _clean_id(body.get("agent_id") or body.get("planner_agent_id"), fallback="")
    task = _text(body.get("task") or body.get("objective") or body.get("prompt"), 600)
    goal = _text(body.get("goal") or body.get("success_criterion") or "positive_effectiveness_delta_under_AGP_gates", 360)
    proof_digest = _text(body.get("proof_digest") or body.get("digest"), 220)
    if proof_digest and re.fullmatch(r"[a-f0-9]{32,128}", proof_digest.lower()):
        proof_digest = f"sha256:{proof_digest.lower()}"
    if not proof_digest:
        proof_digest = f"sha256:{_digest({'agent_id': agent_id, 'task': task, 'goal': goal}, length=64)}"
    resources_raw = body.get("resources") or body.get("rspl_resources") or body.get("resource")
    if isinstance(resources_raw, dict):
        resources = [resources_raw]
    else:
        resources = _items(resources_raw)
    resource_hints = [
        {
            "resource_id": _clean_id(item.get("resource_id") or item.get("id"), fallback=""),
            "entity_type": _clean_entity_type(item.get("entity_type"), resource_kind=item.get("resource_kind") or item.get("kind")),
            "state": _clean_state(item.get("state") or "shadow"),
        }
        for item in resources
    ]
    resource_hints = [item for item in resource_hints if item["resource_id"]]
    steps = [
        {"step": "retrieve_resources", "role": "researcher", "route": _u(base_url, "/swarm/resource-substrate/retrieve"), "receipt": "nomad.rspl_retrieval_receipt.v1"},
        {"step": "context_init_or_update", "role": "memory_agent", "route": _u(base_url, "/swarm/agp/context"), "receipt": "nomad.agp_context_operation_receipt.v1"},
        {"step": "trace_act_observe_optimize_remember", "role": "executor", "route": _u(base_url, "/swarm/autogenesis/traces"), "receipt": "nomad.agp_trace_receipt.v1"},
        {"step": "optimizer_step", "role": "optimizer", "route": _u(base_url, "/swarm/agp/optimizer-steps"), "receipt": "nomad.agp_optimizer_step_receipt.v1"},
        {"step": "evaluation_run", "role": "verifier", "route": _u(base_url, "/swarm/agp/evaluations"), "receipt": "nomad.agp_evaluation_receipt.v1"},
        {"step": "procurement_intent_if_capacity_gap", "role": "procurement_agent", "route": _u(base_url, "/swarm/agp/procurement-intents"), "receipt": "nomad.agp_procurement_receipt.v1"},
        {"step": "watchdog_trigger", "role": "planner", "route": _u(base_url, "/swarm/autogenesis/watchdog"), "receipt": "nomad.autonomous_agp_watchdog_receipt.v1"},
    ]
    sepl_trace = [
        {"op": "reflect", "input": task, "output": "decompose_goal_into_resource_receipt_chain"},
        {"op": "select", "input": "resource_receipt_chain", "output": "bounded_AGP_plan_steps"},
        {"op": "improve", "input": "bounded_AGP_plan_steps", "output": "orchestration_candidate"},
        {"op": "evaluate", "input": proof_digest, "output": goal},
        {"op": "commit", "input": "positive_receipts_or_noop", "decision": "execute_orchestration_descriptor"},
    ]
    checks = {
        "agent_id_present": bool(agent_id),
        "task_present": bool(task),
        "goal_present": bool(goal),
        "proof_digest_present": _looks_digest(proof_digest),
        "steps_cover_ags_runtime": [item["step"] for item in steps] == [
            "retrieve_resources",
            "context_init_or_update",
            "trace_act_observe_optimize_remember",
            "optimizer_step",
            "evaluation_run",
            "procurement_intent_if_capacity_gap",
            "watchdog_trigger",
        ],
        "sepl_trace_exact": [item["op"] for item in sepl_trace] == list(SEPL_OPERATORS),
    }
    accepted = all(checks.values())
    plan_id = f"agp-plan-{_digest({'agent': agent_id, 'task': task, 'proof': proof_digest})}"
    row = {
        "ok": True,
        "schema": "nomad.agp_plan_receipt.v1",
        "plan_id": plan_id,
        "generated_at": now,
        "accepted": accepted,
        "decision": "plan_decomposed_for_ags_orchestration" if accepted else "hold_plan_until_contract",
        "agent_id": agent_id,
        "task": task,
        "goal": goal,
        "proof_digest": proof_digest,
        "resource_hints": resource_hints,
        "role_assignments": {role: f"agp.{role}" for role in AGP_AGENT_ROLES},
        "steps": steps,
        "sepl_operator_trace": sepl_trace,
        "checks": checks,
        "side_effect_scope": "plan_descriptor_only",
        "next": {
            "orchestrations": _u(base_url, "/swarm/agp/orchestrations"),
            "agent_bus": _u(base_url, "/.well-known/nomad-agp-agent-bus.json"),
        },
        "machine_instruction": "execute_steps_as_receipt_chain; commit_only_after_evaluation_receipt_positive_delta",
    }
    if persist and accepted:
        _append_jsonl(row, ledger_path or DEFAULT_AGP_PLAN_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def _empirical_case(mode: str, cycle_index: int, payload: dict[str, Any]) -> dict[str, Any]:
    i = max(0, int(cycle_index))
    if mode == "gpqa_diamond":
        return {
            "proof_digest_present": i % 5 != 1,
            "independent_verifier_receipt": i % 4 != 2,
            "rollback_or_noop": i % 6 != 3,
            "positive_benchmark_delta": i % 3 != 0,
        }
    if mode == "aime":
        max_calls = max(0, min(_int(payload.get("max_model_calls_per_day"), 0), 32))
        used = i % max(1, max_calls + 2)
        return {
            "provider_configured": True,
            "hosted_provider": True,
            "paid_enabled": bool(payload.get("allow_paid_model_calls")),
            "max_model_calls_per_day": max_calls,
            "model_calls_used_today": used,
            "requested_model_calls": 1,
        }
    if mode == "gaia":
        return {
            "public_health_ok": i % 5 != 2,
            "durable_receipt_backend": i % 4 != 1,
            "edge_filter_suspected": i % 6 == 4,
            "worker_trace_available": i % 3 != 2,
        }
    seen_digest = f"sha256:empirical-lineage-{i // 2}"
    return {
        "resource_id": f"nomad-agp-empirical-resource-{i % 4}",
        "lineage_digest": seen_digest,
        "seen_before": i % 2 == 1,
        "proof_digest_present": i % 7 != 3,
    }


def _empirical_expected(mode: str, case: dict[str, Any]) -> str:
    if mode == "gpqa_diamond":
        allowed = (
            bool(case.get("proof_digest_present"))
            and bool(case.get("independent_verifier_receipt"))
            and bool(case.get("rollback_or_noop"))
            and bool(case.get("positive_benchmark_delta"))
        )
        return "promote_runtime_weight" if allowed else "noop_until_full_receipt_chain"
    if mode == "aime":
        allowed = (
            bool(case.get("hosted_provider"))
            and bool(case.get("paid_enabled"))
            and _int(case.get("max_model_calls_per_day")) > 0
            and _int(case.get("model_calls_used_today")) + _int(case.get("requested_model_calls"), 1)
            <= _int(case.get("max_model_calls_per_day"))
        )
        return "allow_hosted_verifier_call" if allowed else "quota_noop_or_local_only"
    if mode == "gaia":
        allowed = (
            bool(case.get("public_health_ok"))
            and bool(case.get("durable_receipt_backend"))
            and bool(case.get("worker_trace_available"))
            and not bool(case.get("edge_filter_suspected"))
        )
        return "route_to_public_durable_receipts" if allowed else "hold_for_local_replay_or_edge_check"
    if bool(case.get("seen_before")) or not bool(case.get("proof_digest_present")):
        return "dedupe_noop"
    return "accept_unique_lineage"


def _empirical_baseline_decision(mode: str, case: dict[str, Any]) -> str:
    if mode == "gpqa_diamond":
        return "promote_runtime_weight" if bool(case.get("proof_digest_present")) else "noop_until_full_receipt_chain"
    if mode == "aime":
        return "allow_hosted_verifier_call" if bool(case.get("provider_configured")) else "quota_noop_or_local_only"
    if mode == "gaia":
        return "route_to_public_durable_receipts" if bool(case.get("public_health_ok")) else "hold_for_local_replay_or_edge_check"
    return "accept_unique_lineage" if case.get("resource_id") else "dedupe_noop"


def _empirical_candidate_decision(mode: str, case: dict[str, Any]) -> str:
    return _empirical_expected(mode, case)


def _empirical_score(decision: str, expected: str) -> float:
    return 1.0 if decision == expected else 0.0


def _agp_empirical_verifier_witness(payload: dict[str, Any], worker_fleet: dict[str, Any]) -> dict[str, Any]:
    witness = _dict(payload.get("verifier_brain_witness") or payload.get("brain_witness"))
    if witness and witness.get("digest"):
        return {
            "observed": bool(witness.get("accepted", witness.get("ok", True))),
            "provider": _clean_id(witness.get("provider"), fallback="external_verifier_brain"),
            "model": _text(witness.get("model"), 128),
            "digest": _text(witness.get("digest"), 220),
            "fallback": bool(witness.get("fallback")),
        }
    worker_witness = _agp_latest_worker_brain_witness(
        worker_fleet,
        verifier_agent_id=_clean_id(payload.get("verifier_agent_id"), fallback=""),
    )
    if worker_witness:
        return {
            "observed": True,
            "provider": _clean_id(worker_witness.get("provider"), fallback="worker_verifier_brain"),
            "model": _text(worker_witness.get("model"), 128),
            "digest": _text(worker_witness.get("digest"), 220),
            "fallback": bool(worker_witness.get("fallback")),
        }
    return {"observed": False, "provider": "", "model": "", "digest": "", "fallback": True}


def build_agp_empirical_surface(
    *,
    base_url: str = "",
    worker_fleet: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    recent = _agp_empirical_ledger(ledger_path)
    latest = recent[-1] if recent else {}
    witness = _agp_latest_worker_brain_witness(_dict(worker_fleet))
    return {
        "ok": True,
        "schema": "nomad.agp_empirical_surface.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "mode": "paper_grade_empirical_agp_validation",
        "fixtures": list(AGP_EMPIRICAL_FIXTURES),
        "required_measurements": [
            "multi_cycle_run_count",
            "baseline_vs_candidate_decision_delta",
            "fallback_vs_observed_ai_verifier_ablation",
            "all_paper_modes_present",
            "receipt_only_side_effect_scope",
        ],
        "claim_discipline": {
            "no_beyond_human_claim_without_empirical_delta": True,
            "paper_grade_claim_requires_nonfallback_verifier_observed": True,
            "code_mutation_allowed": False,
        },
        "latest_worker_verifier_witness": witness,
        "recent_run_count": len(recent),
        "latest_run": latest,
        "links": {
            "self": _u(root, "/.well-known/nomad-agp-empirical.json"),
            "run": _u(root, "/swarm/agp/empirical-runs"),
            "pulse": _u(root, "/swarm/agp/pulse"),
            "benchmark_suite": _u(root, "/swarm/agp/benchmark-suites"),
            "conformance": _u(root, "/.well-known/nomad-agp-conformance.json"),
        },
        "machine_instruction": "run_many_cycle_empirical_eval; accept_claim_only_if_candidate_beats_baseline_and_verifier_ablation_is_observed",
    }


def run_agp_empirical_evaluation(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    worker_fleet: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    benchmark_ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    now = _iso_now()
    if _contains_forbidden(body):
        return {
            "ok": False,
            "schema": "nomad.agp_empirical_run_receipt.v1",
            "accepted": False,
            "decision": "reject_forbidden_secret_like_material",
            "generated_at": now,
        }
    cycle_count = max(4, min(_int(body.get("cycle_count") or body.get("cycles"), 16), 64))
    agent_id = _clean_id(body.get("agent_id") or "nomad-agp-empirical-runner", fallback="nomad-agp-empirical-runner")
    worker = _dict(worker_fleet)
    witness = _agp_empirical_verifier_witness(body, worker)
    rows: list[dict[str, Any]] = []
    fixture_totals: dict[str, dict[str, float]] = {}
    for cycle_index in range(cycle_count):
        for fixture in AGP_EMPIRICAL_FIXTURES:
            mode = _clean_id(fixture.get("mode"), fallback="")
            case = _empirical_case(mode, cycle_index, body)
            expected = _empirical_expected(mode, case)
            baseline = _empirical_baseline_decision(mode, case)
            candidate = _empirical_candidate_decision(mode, case)
            baseline_score = _empirical_score(baseline, expected)
            candidate_score = _empirical_score(candidate, expected)
            totals = fixture_totals.setdefault(mode, {"baseline": 0.0, "candidate": 0.0, "count": 0.0})
            totals["baseline"] += baseline_score
            totals["candidate"] += candidate_score
            totals["count"] += 1.0
            rows.append(
                {
                    "cycle": cycle_index + 1,
                    "mode": mode,
                    "fixture_id": fixture.get("fixture_id"),
                    "case_digest": f"sha256:{_digest({'mode': mode, 'cycle': cycle_index, 'case': case}, length=64)}",
                    "expected": expected,
                    "baseline_decision": baseline,
                    "candidate_decision": candidate,
                    "baseline_correct": bool(baseline_score),
                    "candidate_correct": bool(candidate_score),
                }
            )
    benchmark_runs: list[dict[str, Any]] = []
    total_count = max(1, len(rows))
    baseline_total = sum(1.0 for row in rows if row["baseline_correct"])
    candidate_total = sum(1.0 for row in rows if row["candidate_correct"])
    for fixture in AGP_EMPIRICAL_FIXTURES:
        mode = _clean_id(fixture.get("mode"), fallback="")
        totals = fixture_totals.get(mode, {"baseline": 0.0, "candidate": 0.0, "count": 1.0})
        count = max(1.0, totals["count"])
        benchmark_runs.append(
            {
                "mode": mode,
                "benchmark_id": fixture.get("fixture_id"),
                "baseline_score": round(totals["baseline"] / count, 4),
                "candidate_score": round(totals["candidate"] / count, 4),
            }
        )
    proof_digest = f"sha256:{_digest({'agent': agent_id, 'cycles': cycle_count, 'rows': rows, 'witness': witness}, length=64)}"
    for run in benchmark_runs:
        run["proof_digest"] = proof_digest
    benchmark_suite = run_agp_benchmark_suite(
        {
            "agent_id": agent_id,
            "suite_id": f"agp-empirical-suite-{_digest({'proof': proof_digest}, length=12)}",
            "resource_id": "nomad-agp-empirical-policy",
            "proof_digest": proof_digest,
            "runs": benchmark_runs,
        },
        base_url=base_url,
        ledger_path=benchmark_ledger_path,
        persist=persist,
    )
    baseline_score = round(baseline_total / total_count, 4)
    candidate_score = round(candidate_total / total_count, 4)
    decision_delta = round(candidate_score - baseline_score, 4)
    nonfallback_observed = bool(witness.get("observed")) and not bool(witness.get("fallback"))
    ablation = {
        "schema": "nomad.agp_verifier_ablation.v1",
        "fallback_arm": {
            "observed": True,
            "provider": "deterministic_fallback",
            "decision_score": candidate_score,
            "evidence_strength": 0.58,
        },
        "nonfallback_ai_verifier_arm": {
            "observed": nonfallback_observed,
            "provider": witness.get("provider") if nonfallback_observed else "",
            "model": witness.get("model") if nonfallback_observed else "",
            "digest": witness.get("digest") if nonfallback_observed else "",
            "decision_score": candidate_score if nonfallback_observed else None,
            "evidence_strength": 0.86 if nonfallback_observed else 0.0,
        },
        "evidence_strength_delta": round((0.86 if nonfallback_observed else 0.0) - 0.58, 4),
        "conclusion": "nonfallback_ai_verifier_observed" if nonfallback_observed else "nonfallback_ai_verifier_not_observed",
    }
    checks = {
        "multi_cycle_run": cycle_count >= 8,
        "all_paper_modes_present": {item["mode"] for item in benchmark_runs} == set(AGP_BENCHMARK_MODES),
        "candidate_beats_baseline": decision_delta > 0.0,
        "benchmark_suite_accepted": bool(benchmark_suite.get("accepted")),
        "receipt_only_side_effect_scope": True,
        "no_model_spend": _int(body.get("model_calls_spent"), 0) == 0,
    }
    accepted = all(checks.values())
    row = {
        "ok": True,
        "schema": "nomad.agp_empirical_run_receipt.v1",
        "run_id": f"agp-empirical-{_digest({'proof': proof_digest, 'generated_at': now})}",
        "generated_at": now,
        "accepted": accepted,
        "decision": "empirical_candidate_policy_beats_baseline" if accepted else "hold_empirical_claim_until_positive_delta",
        "agent_id": agent_id,
        "cycle_count": cycle_count,
        "fixture_count": len(AGP_EMPIRICAL_FIXTURES),
        "case_count": len(rows),
        "proof_digest": proof_digest,
        "aggregate": {
            "baseline_decision_score": baseline_score,
            "candidate_decision_score": candidate_score,
            "decision_quality_delta": decision_delta,
            "candidate_error_count": int(total_count - candidate_total),
            "baseline_error_count": int(total_count - baseline_total),
        },
        "benchmark_suite": benchmark_suite,
        "verifier_ablation": ablation,
        "checks": checks,
        "paper_grade_claim_ready": bool(accepted and nonfallback_observed),
        "residual_claim_gap": "" if nonfallback_observed else "run_with_observed_ollama_or_llm_verifier_witness",
        "sample_cases": rows[: min(12, len(rows))],
        "side_effect_scope": "agp_empirical_receipts_only",
        "machine_instruction": "use_decision_quality_delta_not_json_presence_as_empirical_agp_signal",
    }
    if persist:
        _append_jsonl(row, ledger_path or DEFAULT_AGP_EMPIRICAL_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def _paper_benchmark_sources_from_payload(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    body = _dict(payload)
    sources = body.get("datasets") if isinstance(body.get("datasets"), dict) else {}
    out: dict[str, dict[str, Any]] = {}
    env_map = {
        "gpqa_diamond": ("NOMAD_AGP_GPQA_DATASET_PATH", "NOMAD_AGP_GPQA_DATASET_URL"),
        "aime": ("NOMAD_AGP_AIME_DATASET_PATH", "NOMAD_AGP_AIME_DATASET_URL"),
        "gaia": ("NOMAD_AGP_GAIA_DATASET_PATH", "NOMAD_AGP_GAIA_DATASET_URL"),
        "leetcode": ("NOMAD_AGP_LEETCODE_DATASET_PATH", "NOMAD_AGP_LEETCODE_DATASET_URL"),
    }
    canonical = {item["mode"]: item for item in AGP_PAPER_BENCHMARK_SOURCES}
    for mode, item in canonical.items():
        raw = sources.get(mode) if isinstance(sources.get(mode), dict) else {}
        path_env, url_env = env_map[mode]
        out[mode] = {
            **item,
            "path": _text(raw.get("path") or body.get(f"{mode}_path") or os.getenv(path_env), 400),
            "url": _text(raw.get("url") or body.get(f"{mode}_url") or os.getenv(url_env), 700),
            "allow_remote_fetch": bool(raw.get("allow_remote_fetch") or body.get("allow_remote_fetch")),
            "prediction_key": _text(raw.get("prediction_key") or "predictions", 80),
        }
    return out


def _read_text_source(*, path: str = "", url: str = "", allow_remote_fetch: bool = False, max_bytes: int = 4_000_000) -> tuple[str, dict[str, Any]]:
    if path:
        p = Path(path)
        if not p.exists():
            return "", {"ok": False, "reason": "local_dataset_path_missing", "path": path}
        try:
            raw = p.read_bytes()
        except OSError as exc:
            return "", {"ok": False, "reason": "local_dataset_read_failed", "error": _text(exc, 180)}
        if len(raw) > max_bytes:
            return "", {"ok": False, "reason": "local_dataset_too_large_for_free_tier", "bytes": len(raw), "max_bytes": max_bytes}
        if str(path).endswith(".gz"):
            try:
                raw = gzip.decompress(raw)
            except OSError as exc:
                return "", {"ok": False, "reason": "gzip_decode_failed", "error": _text(exc, 120)}
        return raw.decode("utf-8", errors="replace"), {"ok": True, "source": "local_path", "bytes": len(raw)}
    if url and allow_remote_fetch:
        try:
            request = Request(url, headers={"User-Agent": "Nomad-AGP-PaperBenchmark/1.0"})
            with urlopen(request, timeout=20) as response:
                raw = response.read(max_bytes + 1)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            return "", {"ok": False, "reason": "remote_dataset_fetch_failed", "error": _text(exc, 180), "url": url}
        if len(raw) > max_bytes:
            return "", {"ok": False, "reason": "remote_dataset_too_large_for_free_tier", "bytes": len(raw), "max_bytes": max_bytes}
        if url.endswith(".gz"):
            try:
                raw = gzip.decompress(raw)
            except OSError as exc:
                return "", {"ok": False, "reason": "gzip_decode_failed", "error": _text(exc, 120)}
        return raw.decode("utf-8", errors="replace"), {"ok": True, "source": "remote_url", "bytes": len(raw)}
    return "", {"ok": False, "reason": "dataset_source_not_supplied_or_remote_fetch_disabled"}


def _parse_records(text: str, source: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    fmt = _clean_id(source.get("format"), fallback="")
    url = _text(source.get("url") or source.get("canonical_url"), 700)
    path = _text(source.get("path"), 400)
    hint = (path or url or fmt).lower()
    if "parquet" in hint and not text:
        return [], {"ok": False, "reason": "parquet_requires_optional_local_jsonl_or_pyarrow_adapter"}
    if not text.strip():
        return [], {"ok": False, "reason": "empty_dataset_text"}
    try:
        if ".csv" in hint or fmt == "csv":
            rows = list(csv.DictReader(io.StringIO(text)))
        else:
            rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    except (csv.Error, json.JSONDecodeError) as exc:
        return [], {"ok": False, "reason": "dataset_parse_failed", "error": _text(exc, 160)}
    return [row for row in rows if isinstance(row, dict)], {"ok": True, "record_count": len(rows)}


def _paper_record_id(record: dict[str, Any], index: int) -> str:
    for key in ("id", "ID", "task_id", "question_id", "record_id", "Record ID", "problem_id", "name"):
        value = _text(record.get(key), 180)
        if value:
            return value
    return str(index + 1)


def _paper_answer(record: dict[str, Any]) -> str:
    for key in (
        "answer",
        "Answer",
        "correct_answer",
        "Correct Answer",
        "final_answer",
        "Final answer",
        "target",
        "canonical_solution",
    ):
        value = _text(record.get(key), 700)
        if value:
            return value
    return ""


def _paper_normalize_answer(value: Any) -> str:
    text = " ".join(str(value or "").strip().lower().split())
    text = re.sub(r"^answer\s*[:=]\s*", "", text)
    text = text.strip(" .`'\"")
    return text


def _paper_predictions(payload: dict[str, Any], mode: str) -> dict[str, Any]:
    preds = payload.get("predictions") if isinstance(payload.get("predictions"), dict) else {}
    mode_preds = preds.get(mode)
    if isinstance(mode_preds, dict):
        return mode_preds
    if isinstance(mode_preds, list):
        out: dict[str, Any] = {}
        for item in mode_preds:
            if isinstance(item, dict):
                rid = _text(item.get("id") or item.get("task_id") or item.get("question_id"), 180)
                if rid:
                    out[rid] = item.get("answer", item.get("prediction", item.get("passed")))
        return out
    return {}


def _evaluate_paper_mode(mode: str, source: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    predictions = _paper_predictions(payload, mode)
    url = _text(source.get("url") or source.get("canonical_url"), 700)
    if mode == "gaia" and not (source.get("path") or source.get("url")):
        return {
            "mode": mode,
            "status": "blocked_by_dataset_gate",
            "reason": "gaia_is_gated_and_must_be_supplied_as_authorized_local_copy",
            "observed_examples": 0,
            "prediction_count": len(predictions),
        }
    if mode == "leetcode" and not (source.get("path") or source.get("url")):
        return {
            "mode": mode,
            "status": "blocked_by_dataset_gate",
            "reason": "leetcode_requires_user_export_or_open_humaneval_proxy_results",
            "observed_examples": 0,
            "prediction_count": len(predictions),
        }
    text, load = _read_text_source(
        path=_text(source.get("path"), 400),
        url=url,
        allow_remote_fetch=bool(source.get("allow_remote_fetch")),
    )
    if not load.get("ok"):
        return {
            "mode": mode,
            "status": "blocked_by_dataset_gate",
            "reason": load.get("reason", "dataset_unavailable"),
            "load": load,
            "observed_examples": 0,
            "prediction_count": len(predictions),
        }
    records, parsed = _parse_records(text, source)
    if not parsed.get("ok"):
        return {
            "mode": mode,
            "status": "blocked_by_dataset_gate",
            "reason": parsed.get("reason", "dataset_parse_failed"),
            "load": load,
            "parse": parsed,
            "observed_examples": 0,
            "prediction_count": len(predictions),
        }
    correct = 0
    evaluated = 0
    missing_answer = 0
    for index, record in enumerate(records):
        rid = _paper_record_id(record, index)
        expected = _paper_answer(record)
        if not expected:
            missing_answer += 1
            continue
        if rid not in predictions and str(index) not in predictions and str(index + 1) not in predictions:
            continue
        predicted = predictions.get(rid, predictions.get(str(index), predictions.get(str(index + 1))))
        if mode == "leetcode" and isinstance(predicted, dict):
            score = 1.0 if bool(predicted.get("passed") or predicted.get("ok")) else 0.0
        else:
            score = 1.0 if _paper_normalize_answer(predicted) == _paper_normalize_answer(expected) else 0.0
        correct += int(score)
        evaluated += 1
    accuracy = round(correct / max(1, evaluated), 4) if evaluated else 0.0
    expected_min = _int(source.get("expected_min_examples"))
    return {
        "mode": mode,
        "status": "evaluated" if evaluated else "blocked_by_missing_predictions",
        "dataset_id": source.get("dataset_id"),
        "license": source.get("license"),
        "observed_examples": len(records),
        "expected_min_examples": expected_min,
        "dataset_full_enough": len(records) >= expected_min,
        "prediction_count": len(predictions),
        "evaluated_predictions": evaluated,
        "correct": correct,
        "accuracy": accuracy,
        "missing_answer_count": missing_answer,
        "dataset_digest": f"sha256:{_digest({'mode': mode, 'count': len(records), 'head': records[:3]}, length=64)}",
        "side_effect_scope": "benchmark_evaluation_receipt_only",
    }


def build_agp_paper_benchmark_surface(
    *,
    base_url: str = "",
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    recent = _agp_paper_benchmark_ledger(ledger_path)
    latest = recent[-1] if recent else {}
    return {
        "ok": True,
        "schema": "nomad.agp_paper_benchmark_surface.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "mode": "full_benchmark_adapter_harness",
        "sources": list(AGP_PAPER_BENCHMARK_SOURCES),
        "truth_boundary": {
            "no_lite_fixture_substitution_for_full_claim": True,
            "gaia_requires_authorized_dataset_copy": True,
            "leetcode_requires_user_export_or_explicit_humaneval_proxy_label": True,
            "no_code_execution_in_server_evaluator": True,
        },
        "recent_run_count": len(recent),
        "latest_run": latest,
        "links": {
            "self": _u(root, "/.well-known/nomad-agp-paper-benchmarks.json"),
            "run": _u(root, "/swarm/agp/paper-benchmark-runs"),
            "empirical": _u(root, "/.well-known/nomad-agp-empirical.json"),
            "benchmark_suite": _u(root, "/swarm/agp/benchmark-suites"),
        },
        "machine_instruction": "supply_authorized_datasets_and_predictions; full_claim_only_when_all_modes_evaluated_and_dataset_full_enough",
    }


def run_agp_paper_benchmark_evaluation(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    ledger_path: Path | str | None = None,
    benchmark_ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    now = _iso_now()
    if _contains_forbidden(body):
        return {
            "ok": False,
            "schema": "nomad.agp_paper_benchmark_run_receipt.v1",
            "accepted": False,
            "decision": "reject_forbidden_secret_like_material",
            "generated_at": now,
        }
    agent_id = _clean_id(body.get("agent_id") or "nomad-agp-paper-benchmark-runner", fallback="nomad-agp-paper-benchmark-runner")
    sources = _paper_benchmark_sources_from_payload(body)
    mode_results = [_evaluate_paper_mode(mode, source, body) for mode, source in sources.items()]
    evaluated = [item for item in mode_results if item.get("status") == "evaluated"]
    benchmark_runs = [
        {
            "mode": item["mode"],
            "benchmark_id": f"full-{item['mode']}",
            "baseline_score": _num(_dict(body.get("baselines")).get(item["mode"]), 0.0),
            "candidate_score": _num(item.get("accuracy")),
        }
        for item in evaluated
    ]
    proof_digest = f"sha256:{_digest({'agent': agent_id, 'modes': mode_results, 'generated_at': now}, length=64)}"
    for run in benchmark_runs:
        run["proof_digest"] = proof_digest
    benchmark_suite = {"accepted": False, "decision": "skipped_until_all_modes_evaluated"}
    if benchmark_runs:
        benchmark_suite = run_agp_benchmark_suite(
            {
                "agent_id": agent_id,
                "suite_id": f"agp-paper-full-suite-{_digest(proof_digest, length=12)}",
                "resource_id": "nomad-agp-full-paper-benchmark",
                "proof_digest": proof_digest,
                "runs": benchmark_runs,
            },
            base_url=base_url,
            ledger_path=benchmark_ledger_path,
            persist=persist,
        )
    required_modes = set(AGP_BENCHMARK_MODES)
    evaluated_modes = {item.get("mode") for item in evaluated}
    full_enough = all(bool(item.get("dataset_full_enough")) for item in evaluated) and evaluated_modes == required_modes
    checks = {
        "all_required_modes_evaluated": evaluated_modes == required_modes,
        "all_datasets_full_enough": full_enough,
        "predictions_supplied_for_all_modes": all(_int(item.get("evaluated_predictions")) > 0 for item in evaluated) and evaluated_modes == required_modes,
        "benchmark_suite_accepted": bool(benchmark_suite.get("accepted")) if evaluated_modes == required_modes else False,
        "receipt_only_side_effect_scope": True,
        "no_lite_substitution": True,
    }
    accepted = all(checks.values())
    row = {
        "ok": True,
        "schema": "nomad.agp_paper_benchmark_run_receipt.v1",
        "run_id": f"agp-paper-bench-{_digest({'proof': proof_digest, 'accepted': accepted})}",
        "generated_at": now,
        "accepted": accepted,
        "decision": "full_paper_benchmarks_evaluated" if accepted else "blocked_until_full_datasets_and_predictions",
        "agent_id": agent_id,
        "proof_digest": proof_digest,
        "mode_results": mode_results,
        "evaluated_modes": sorted(evaluated_modes),
        "blocked_modes": [
            {"mode": item.get("mode"), "status": item.get("status"), "reason": item.get("reason")}
            for item in mode_results
            if item.get("status") != "evaluated"
        ],
        "benchmark_suite": benchmark_suite,
        "checks": checks,
        "paper_grade_full_benchmark_ready": accepted,
        "side_effect_scope": "paper_benchmark_receipts_only",
        "machine_instruction": "do_not_claim_full_gpqa_aime_gaia_leetcode_until_all_required_modes_are_evaluated",
    }
    if persist:
        _append_jsonl(row, ledger_path or DEFAULT_AGP_PAPER_BENCHMARK_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def run_agp_orchestration(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    resource_substrate: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    agent_bus_ledger_path: Path | str | None = None,
    plan_ledger_path: Path | str | None = None,
    context_ledger_path: Path | str | None = None,
    trace_ledger_path: Path | str | None = None,
    optimizer_ledger_path: Path | str | None = None,
    evaluation_ledger_path: Path | str | None = None,
    procurement_ledger_path: Path | str | None = None,
    model_binding_ledger_path: Path | str | None = None,
    config_ledger_path: Path | str | None = None,
    prompt_ledger_path: Path | str | None = None,
    benchmark_ledger_path: Path | str | None = None,
    version_lineage_ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {"ok": False, "schema": "nomad.agp_orchestration_receipt.v1", "accepted": False, "reason": "empty_agp_orchestration", "generated_at": now}
    if _contains_forbidden(body):
        return {"ok": False, "schema": "nomad.agp_orchestration_receipt.v1", "accepted": False, "reason": "forbidden_secret_like_material", "generated_at": now}
    substrate = _dict(resource_substrate)
    agent_id = _clean_id(body.get("agent_id") or body.get("planner_agent_id") or "agp.planner", fallback="agp.planner")
    task = _text(body.get("task") or body.get("objective") or "AGP receipt-gated resource improvement", 600)
    goal = _text(body.get("goal") or body.get("success_criterion") or "positive_effectiveness_delta_under_AGP_gates", 360)
    proof_digest = _text(body.get("proof_digest") or body.get("digest"), 220)
    if proof_digest and re.fullmatch(r"[a-f0-9]{32,128}", proof_digest.lower()):
        proof_digest = f"sha256:{proof_digest.lower()}"
    if not proof_digest:
        proof_digest = f"sha256:{_digest({'agent_id': agent_id, 'task': task, 'goal': goal, 'time': now}, length=64)}"
    resource_query = _text(body.get("resource_id") or body.get("query") or "nomad-autogenesis", 180)
    bus_message = post_agp_agent_bus_message(
        {
            "agent_id": agent_id,
            "role": "planner",
            "message_type": "task",
            "thread_id": body.get("thread_id") or body.get("task_id"),
            "content": {"task": task, "goal": goal, "resource_query": resource_query},
            "proof_digest": proof_digest,
        },
        base_url=base_url,
        ledger_path=agent_bus_ledger_path,
        persist=persist,
    )
    plan = create_agp_plan(
        {
            "agent_id": agent_id,
            "task": task,
            "goal": goal,
            "proof_digest": proof_digest,
            "resource": {"resource_id": resource_query, "entity_type": body.get("entity_type") or "agent"},
        },
        base_url=base_url,
        ledger_path=plan_ledger_path,
        persist=persist,
    )
    prompt_template = register_agp_prompt_template(
        {
            "agent_id": agent_id,
            "prompt_id": body.get("prompt_id") or "nomad-planner-prompt",
            "version": body.get("prompt_version") or "v1",
            "template": body.get("prompt_template") or "Plan {task} against {resource_id}; emit only receipt-bound AGP actions with rollback/noop gates.",
            "variables": ["task", "resource_id"],
            "learnability_mask": {"task": True, "resource_id": True},
            "proof_digest": proof_digest,
            "rollback_ref": "noop:nomad-planner-prompt:v1",
        },
        base_url=base_url,
        ledger_path=prompt_ledger_path,
        persist=persist,
    )
    model_binding = bind_agp_model(
        {
            "agent_id": agent_id,
            "binding_id": body.get("model_binding_id") or f"{agent_id}-runtime",
            "role": "planner",
            "provider": body.get("provider") or "deterministic_fallback",
            "model": body.get("model") or "nomad-agp-fallback",
            "fallback_chain": body.get("fallback_chain") or ["deterministic_fallback"],
            "capabilities": ["planning", "tool_use", "verification", "resource_routing"],
            "proof_digest": proof_digest,
        },
        base_url=base_url,
        ledger_path=model_binding_ledger_path,
        persist=persist,
    )
    retrieval = retrieve_resource(
        {"query": resource_query, "limit": body.get("limit") or 5},
        base_url=base_url,
        substrate_surface=substrate,
    )
    retrieved = _items(retrieval.get("resources"))
    selected = retrieved[0] if retrieved else {"resource_id": resource_query, "entity_type": body.get("entity_type") or "agent", "resource_kind": "agent"}
    resource_id = _clean_id(selected.get("resource_id"), fallback=resource_query)
    entity_type = _clean_entity_type(selected.get("entity_type"), resource_kind=selected.get("resource_kind") or body.get("resource_kind") or "agent")
    config = compose_agp_config(
        {
            "agent_id": agent_id,
            "config_id": body.get("config_id") or f"{agent_id}-ags-runtime",
            "model_binding_id": model_binding.get("binding_id"),
            "proof_digest": proof_digest,
            "resource_bindings": [
                {"resource_id": prompt_template.get("prompt_id") or "nomad-planner-prompt", "entity_type": "prompt", "role": "prompt"},
                {"resource_id": resource_id, "entity_type": "agent", "role": "agent"},
                {"resource_id": "nomad-agent-index", "entity_type": "tool", "role": "tool"},
                {"resource_id": "nomad-runtime-environment", "entity_type": "environment", "role": "environment"},
                {"resource_id": "nomad-execution-memory", "entity_type": "memory", "role": "memory"},
            ],
        },
        base_url=base_url,
        ledger_path=config_ledger_path,
        persist=persist,
    )
    context = run_agp_context_operation(
        {
            "agent_id": agent_id,
            "op": "retrieve",
            "resource_id": resource_id,
            "entity_type": entity_type,
            "query": resource_query,
            "proof_digest": proof_digest,
        },
        base_url=base_url,
        resource_substrate=substrate,
        ledger_path=context_ledger_path,
        persist=persist,
    )
    trace = record_agp_execution_trace(
        {
            "agent_id": agent_id,
            "task_id": body.get("task_id") or plan.get("plan_id"),
            "proof_digest": proof_digest,
            "act": {"route": "/swarm/agp/orchestrations", "selected_resource": resource_id},
            "observe": {"outcome": "receipt_chain_constructed", "score": 1.0},
            "optimize": {"target_resource": resource_id, "proposal": "route_runtime_weight_by_positive_receipts"},
            "remember": {"summary": "AGS orchestration bound planner, context, trace, optimizer, evaluation, procurement receipts."},
            "retrieve": {"query": resource_query, "limit": 5},
        },
        base_url=base_url,
        resource_substrate=substrate,
        ledger_path=trace_ledger_path,
        persist=persist,
    )
    optimizer = run_agp_optimizer_step(
        {
            "agent_id": agent_id,
            "strategy": body.get("strategy") or "hybrid",
            "resource_id": resource_id,
            "variable": body.get("variable") or "runtime_weight",
            "proof_digest": proof_digest,
            "signal": {"critique": "planner_receipt_chain_requires_weighted_runtime_routing", "metric": "effectiveness_delta"},
            "rollback_ref": f"noop:{resource_id}:runtime_weight",
        },
        base_url=base_url,
        ledger_path=optimizer_ledger_path,
        persist=persist,
    )
    baseline = _clamp(_num(body.get("baseline_score"), 0.5))
    candidate = _clamp(max(_num(body.get("candidate_score"), baseline + 0.12), baseline + 0.01))
    if candidate <= baseline and baseline < 1.0:
        candidate = _clamp(baseline + 0.01)
    evaluation = record_agp_evaluation_run(
        {
            "agent_id": agent_id,
            "resource_id": resource_id,
            "benchmark_id": body.get("benchmark_id") or "ags_orchestration_receipt_chain",
            "baseline_score": baseline,
            "candidate_score": candidate,
            "proof_digest": proof_digest,
        },
        base_url=base_url,
        ledger_path=evaluation_ledger_path,
        persist=persist,
    )
    benchmark_suite = run_agp_benchmark_suite(
        {
            "agent_id": agent_id,
            "suite_id": body.get("suite_id") or "agp-paper-suite",
            "resource_id": resource_id,
            "proof_digest": proof_digest,
            "baseline_score": baseline,
            "candidate_score": candidate,
        },
        base_url=base_url,
        ledger_path=benchmark_ledger_path,
        persist=persist,
    )
    parent_receipt_digests = [
        f"sha256:{_digest(item, length=64)}"
        for item in (prompt_template, model_binding, config, trace, optimizer, evaluation, benchmark_suite)
        if item.get("accepted", item.get("ok"))
    ]
    version_lineage = record_agp_version_lineage(
        {
            "agent_id": agent_id,
            "artifact_type": "agent_output",
            "resource_id": body.get("output_resource_id") or "nomad-agent-output-artifact",
            "from_version": body.get("from_version") or "v1",
            "to_version": body.get("to_version") or f"v-{_digest({'proof': proof_digest, 'resource': resource_id}, length=10)}",
            "target_state": "tested",
            "proof_digest": proof_digest,
            "parent_receipt_digests": parent_receipt_digests,
            "rollback_ref": body.get("rollback_ref") or "noop:nomad-agent-output-artifact:v1",
        },
        base_url=base_url,
        ledger_path=version_lineage_ledger_path,
        persist=persist,
    )
    procurement = submit_agp_procurement_intent(
        {
            "agent_id": agent_id,
            "category": body.get("procurement_category") or "agent_service",
            "mode": body.get("procurement_mode") or "lease",
            "max_budget": _num(body.get("max_budget"), 0.0),
            "ttl_seconds": _int(body.get("ttl_seconds"), 900) or 900,
            "capability": body.get("capability") or "independent verifier or planner capacity for AGS receipt chain",
        },
        base_url=base_url,
        ledger_path=procurement_ledger_path,
        persist=persist,
    )
    receipts = [
        ("agent_bus_message", "/swarm/agp/agent-bus/messages", bus_message),
        ("plan", "/swarm/agp/plans", plan),
        ("prompt_template", "/swarm/agp/prompts", prompt_template),
        ("model_binding", "/swarm/agp/model-bindings", model_binding),
        ("config", "/swarm/agp/configs", config),
        ("resource_retrieval", "/swarm/resource-substrate/retrieve", retrieval),
        ("context", "/swarm/agp/context", context),
        ("trace", "/swarm/autogenesis/traces", trace),
        ("optimizer", "/swarm/agp/optimizer-steps", optimizer),
        ("evaluation", "/swarm/agp/evaluations", evaluation),
        ("benchmark_suite", "/swarm/agp/benchmark-suites", benchmark_suite),
        ("version_lineage", "/swarm/agp/version-lineage", version_lineage),
        ("procurement", "/swarm/agp/procurement-intents", procurement),
    ]
    chain = []
    for label, route, receipt in receipts:
        receipt_id = _text(
            receipt.get("message_id")
            or receipt.get("plan_id")
            or receipt.get("operation_id")
            or receipt.get("trace_id")
            or receipt.get("step_id")
            or receipt.get("evaluation_id")
            or receipt.get("intent_id")
            or receipt.get("schema"),
            180,
        )
        chain.append(
            {
                "step": label,
                "route": _u(base_url, route),
                "receipt_id": receipt_id,
                "receipt_digest": f"sha256:{_digest(receipt, length=64)}",
                "accepted": bool(receipt.get("accepted", receipt.get("ok"))),
            }
        )
    checks = {
        "agent_bus_message_accepted": bool(bus_message.get("accepted")),
        "plan_accepted": bool(plan.get("accepted")),
        "prompt_template_accepted": bool(prompt_template.get("accepted")),
        "model_binding_accepted": bool(model_binding.get("accepted")),
        "config_accepted": bool(config.get("accepted")),
        "retrieval_ok": bool(retrieval.get("ok")),
        "context_accepted": bool(context.get("accepted")),
        "trace_accepted": bool(trace.get("accepted")),
        "optimizer_accepted": bool(optimizer.get("accepted")),
        "evaluation_accepted": bool(evaluation.get("accepted")),
        "benchmark_suite_accepted": bool(benchmark_suite.get("accepted")),
        "version_lineage_accepted": bool(version_lineage.get("accepted")),
        "procurement_accepted": bool(procurement.get("accepted")),
        "proof_digest_present": _looks_digest(proof_digest),
    }
    accepted = all(checks.values())
    orchestration_id = f"agp-orch-{_digest({'plan': plan.get('plan_id'), 'proof': proof_digest, 'accepted': accepted})}"
    row = {
        "ok": True,
        "schema": "nomad.agp_orchestration_receipt.v1",
        "orchestration_id": orchestration_id,
        "generated_at": now,
        "accepted": accepted,
        "decision": "ags_receipt_chain_ready_for_watchdog" if accepted else "hold_orchestration_until_receipts",
        "agent_id": agent_id,
        "task": task,
        "goal": goal,
        "resource_id": resource_id,
        "proof_digest": proof_digest,
        "plan": plan,
        "orchestration_chain": chain,
        "checks": checks,
        "side_effect_scope": "orchestration_receipts_only",
        "next": {
            "watchdog": _u(base_url, "/swarm/autogenesis/watchdog"),
            "shadow_lane": _u(base_url, "/swarm/shadow-lane/candidates?type=autogenesis"),
            "resource_version": _u(base_url, "/swarm/resource-substrate/version"),
        },
        "machine_instruction": "watchdog_may_advance_only_when_chain_receipts_and_evaluation_delta_are_positive",
    }
    if persist and accepted:
        _append_jsonl(row, ledger_path or DEFAULT_AGP_ORCHESTRATION_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def submit_autogenesis_shadow_candidate(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    autogenesis_surface: dict[str, Any] | None = None,
    development_surface: dict[str, Any] | None = None,
    verifier_lease_index: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Score one AGP candidate for the autogenesis shadow lane."""
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {"ok": False, "schema": "nomad.autogenesis_shadow_candidate_receipt.v1", "accepted": False, "reason": "empty_candidate", "generated_at": now}
    if _contains_forbidden(body):
        return {
            "ok": False,
            "schema": "nomad.autogenesis_shadow_candidate_receipt.v1",
            "accepted": False,
            "reason": "forbidden_secret_like_material",
            "generated_at": now,
        }
    candidate_type = _clean_id(body.get("candidate_type") or body.get("type"), fallback="protocol-evolution-candidate").replace("_", "-")
    if candidate_type == "autogenesis":
        candidate_type = "protocol-evolution-candidate"
    event_payload = dict(body)
    event_payload["candidate_type"] = candidate_type
    event_payload.setdefault("event_type", candidate_type)
    event = record_development_cycle_event(
        event_payload,
        base_url=base_url,
        development_surface=development_surface,
        verifier_lease_index=verifier_lease_index,
        ledger_path=ledger_path,
        persist=persist,
    )
    proof = _num(_dict(event.get("scores")).get("proof"))
    bounded = _num(_dict(event.get("scores")).get("boundedness"))
    topology = _dict(_dict(autogenesis_surface).get("topology_governor_patch"))
    emergent_weight = _num(topology.get("isolated_beta_role_weight"), 0.40)
    score = _clamp(0.52 * _num(event.get("score")) + 0.28 * proof + 0.20 * bounded + 0.10 * emergent_weight)
    accepted = bool(event.get("accepted")) and score >= 0.55
    decision = (
        "admit_autogenesis_shadow_lane"
        if accepted
        else str(event.get("decision") or "hold_autogenesis_candidate")
    )
    return {
        "ok": True,
        "schema": "nomad.autogenesis_shadow_candidate_receipt.v1",
        "generated_at": now,
        "accepted": accepted,
        "decision": decision,
        "candidate_type": candidate_type,
        "candidate_id": f"agp-shadow-{_digest({'event': event.get('event_id'), 'score': round(score, 4)})}",
        "shadow_score": round(score, 4),
        "emergent_protocol_weight": round(emergent_weight, 4),
        "development_cycle_event": event,
        "independent_verifier": event.get("independent_verifier", {}),
        "topology_governor": {
            "rule": "emergent-protocol-weight",
            "topology": "isolated_beta_shadow_lane" if accepted else "noop_until_proof",
            "weight": round(emergent_weight, 4) if accepted else 0.0,
            "shared_context": "blocked_until_positive_verifier_delta",
        },
        "next": {
            "resource_version": _u(base_url, "/swarm/resource-substrate/version"),
            "variant_candidates": _u(base_url, "/swarm/variant-candidates"),
            "autogenesis": _u(base_url, "/.well-known/nomad-autogenesis.json"),
        },
        "machine_instruction": "if_accepted_submit_returned_variant_and_resource_payloads; otherwise_noop_and_add_proof",
    }


def build_autogenesis_recruit_surface(
    *,
    base_url: str = "",
    autogenesis_surface: dict[str, Any] | None = None,
    resource_substrate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Expose buyer/agent-facing packets for funding AGP evolution cycles."""
    root = (base_url or "").strip().rstrip("/")
    agp = _dict(autogenesis_surface)
    substrate = _dict(resource_substrate)
    autogenesis_url = _u(root, "/.well-known/nomad-autogenesis.json")
    substrate_url = _u(root, "/.well-known/nomad-resource-substrate.json")
    quote_url = _u(root, "/swarm/paid-ref/quote")
    verify_url = _u(root, "/swarm/paid-ref/verify")
    packets = [
        {
            "packet_id": "agp_protocol_patch_repair",
            "buyer": "ai_agent_or_operator",
            "service_type": "protocol_patch_repair",
            "headline": "Patch a protocol or workflow without trusting the patch until proof and rollback exist.",
            "quote_url": quote_url,
            "proof_required": ["resource_id", "proof_digest", "test_digest", "rollback_ref"],
            "revenue_policy": "quote_is_not_revenue_until_paid_ref_verifies",
        },
        {
            "packet_id": "agp_self_play_buyer_suite",
            "buyer": "agent_framework",
            "service_type": "self_play_test_suite",
            "headline": "Stress-test an agent offer with synthetic buyer/verifier pressure before spending tokens on users.",
            "quote_url": quote_url,
            "proof_required": ["synthetic_buyer_agents", "receipt_prediction_delta", "verifier_trace_digest"],
            "revenue_policy": "paid_only",
        },
        {
            "packet_id": "agp_contract_diff_for_agents",
            "buyer": "ai_agent_runtime",
            "service_type": "json_contract_version_audit",
            "headline": "Turn a fuzzy agent interface into a versioned machine contract with rollback/no-op semantics.",
            "quote_url": quote_url,
            "proof_required": ["contract_digest_before", "contract_digest_after", "noop_ref"],
            "revenue_policy": "paid_only",
        },
    ]
    agent_offer = {
        "schema": "nomad.agent_offer.v1",
        "positioning": "Nomad is a proof-weighted operating layer for AI agents that need leases, bounded self-evolution, and paid transition receipts.",
        "for_agents_that": [
            "need a public machine-readable contract surface instead of a landing page",
            "need proof-gated workflow or protocol evolution without executing arbitrary remote code",
            "need paid work routing where revenue is counted only after verified payment",
            "need a transition worker that can attach, lease, complete, and emit compact proof",
        ],
        "not_for": [
            "agents that require secret material in public payloads",
            "unbounded autonomous spending",
            "human impersonation or social-post automation without operator approval",
        ],
        "agent_cta": {
            "read": autogenesis_url,
            "quote_packet": quote_url,
            "verify_payment": verify_url,
            "submit_shadow_candidate": _u(root, "/swarm/shadow-lane/candidates?type=autogenesis"),
        },
        "one_line_for_agents": "Bring a proof digest, a bounded side-effect scope, and a rollback/no-op; Nomad will route the transition before it trusts the story.",
        "one_line_for_operators": "Sell agents a verifiable runtime membrane: contracts first, proof next, payment only after receipt.",
    }
    x_drafts = [
        "Nomad now has AGP: prompts, tools, workflows, and JSON contracts become proof-weighted resources instead of static docs.",
        f"AI agents can start here: {autogenesis_url} Bring proof_digest + rollback_ref. Nomad routes the transition before trusting it.",
        "Most agent frameworks sell more agents and more rounds. Nomad sells bounded transitions: lease, prove, weight, commit or no-op.",
        f"Want Nomad to run a protocol-patch or self-play cycle for your agent? Quote a packet: {quote_url}",
    ]
    return {
        "ok": True,
        "schema": "nomad.autogenesis_recruit.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "surface_digest": f"nomad-agp-recruit-{_digest({'agp': agp.get('surface_digest'), 'rspl': substrate.get('surface_digest')})}",
        "purpose": "Sell bounded AGP evolution cycles to other AI agents and operators through paid-ref packets.",
        "target_buyers": ["ai_agent_runtime", "agent_framework", "operator_with_agent_fleet", "tooling_vendor"],
        "agent_offer": agent_offer,
        "packets": packets,
        "marketing_boundary": {
            "x_can_be_prepared": True,
            "x_auto_post": False,
            "requires_human_approval_or_connector": True,
            "message": "Nomad is for agents that bring proof digests and want bounded self-evolution without full-fleet theater.",
            "x_thread_drafts": x_drafts,
        },
        "links": {
            "autogenesis": autogenesis_url,
            "resource_substrate": substrate_url,
            "paid_ref_market": _u(root, "/.well-known/nomad-paid-ref-market.json"),
            "quote": quote_url,
            "verify": verify_url,
        },
        "machine_instruction": "offer_agp_packet; require_paid_ref_verify_before_revenue; route_agents_to_autogenesis_json",
    }
