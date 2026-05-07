"""Machine-readable conformance checks for Nomad's stable agent contract."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, List

from nomad_machine_product_surface import CORE_ENDPOINTS


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _path_set(paths: Any) -> set[str]:
    if isinstance(paths, dict):
        return {str(k) for k in paths.keys()}
    return set()


def _endpoint_coverage(expected: List[str], available: set[str]) -> dict[str, Any]:
    missing = [path for path in expected if path not in available]
    present = [path for path in expected if path in available]
    coverage = (len(present) / max(1, len(expected))) if expected else 1.0
    return {
        "expected_count": len(expected),
        "present_count": len(present),
        "coverage": round(coverage, 4),
        "present": present,
        "missing": missing,
    }


def build_contract_conformance_snapshot(
    *,
    base_url: str = "",
    machine_product_surface: Dict[str, Any] | None = None,
    openapi_document: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Validate that the published machine product contract matches live schema routes."""
    product = _dict(machine_product_surface)
    stability = _dict(product.get("contract_stability"))
    endpoint_presence = _dict(product.get("endpoint_presence"))
    paths = _path_set(_dict(openapi_document).get("paths"))
    stable_endpoints = [str(path) for path in _items(stability.get("stable_endpoints")) if str(path)]
    if not stable_endpoints:
        stable_endpoints = list(CORE_ENDPOINTS)

    openapi_coverage = _endpoint_coverage(stable_endpoints, paths)
    product_core_paths = [str(path) for path in _items(endpoint_presence.get("core_paths")) if str(path)]
    product_coverage = _endpoint_coverage(stable_endpoints, set(product_core_paths))
    entry_sequences = [item for item in _items(product.get("entry_sequences")) if isinstance(item, dict)]
    sequence_ids = [str(item.get("id") or "") for item in entry_sequences if str(item.get("id") or "")]
    required_sequences = {"arriving_runtime", "idle_runtime", "proof_weighted_pledge"}
    missing_sequences = sorted(required_sequences.difference(sequence_ids))
    version_ok = int(stability.get("major_version") or 0) >= 1

    checks = [
        {
            "id": "stable_endpoints_in_openapi",
            "ok": not openapi_coverage["missing"],
            "detail": openapi_coverage,
        },
        {
            "id": "stable_endpoints_in_product_presence",
            "ok": not product_coverage["missing"],
            "detail": product_coverage,
        },
        {
            "id": "entry_sequences_present",
            "ok": not missing_sequences,
            "detail": {"required": sorted(required_sequences), "present": sequence_ids, "missing": missing_sequences},
        },
        {
            "id": "major_version_declared",
            "ok": version_ok,
            "detail": {"major_version": int(stability.get("major_version") or 0)},
        },
    ]
    violations = [check for check in checks if not bool(check.get("ok"))]
    score = round((len(checks) - len(violations)) / max(1, len(checks)), 4)
    return {
        "ok": not violations,
        "schema": "nomad.machine_contract_conformance.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "score": score,
        "checks": checks,
        "violations": violations,
        "machine_instruction": "prefer_stable_contract_surface; treat_missing_stable_paths_as_degrade_signal",
    }

