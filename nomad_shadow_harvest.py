"""Local dirty-worktree compiler for Nomad AGP shadow candidates.

The harvester treats self-modifying agent output as raw evolutionary material,
not as production truth. It reads a local git worktree, groups dirty files into
machine-readable shadow candidates, mints diff/proof digests, and assigns a
promotion gate. It never mutates the source worktree and never reads ignored
secret-shaped artifacts into candidate content.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCHEMA = "nomad.shadow_harvest.v1"
CANDIDATE_SCHEMA = "nomad.shadow_harvest_candidate.v1"
SURFACE_SCHEMA = "nomad.shadow_harvest_surface.v1"

MAX_PATCH_BYTES = 200_000
MAX_UNTRACKED_BYTES = 120_000

LOCAL_ARTIFACT_PREFIXES = (
    ".git/",
    ".pytest_cache/",
    "__pycache__/",
    "data/",
    "external_work/",
    "secret_scrub_mirrors/",
)
LOCAL_ARTIFACT_NAMES = {
    ".env",
    "nomad_taskbounty_access_cache.json",
    "nomad_agp_paper_benchmark_ledger.jsonl",
    "nomad_agp_prompt_ledger.jsonl",
    "nomad_development_cycles_ledger.jsonl",
    "nomad_variant_forge_ledger.jsonl",
    "nomad_work_exchange_ledger.jsonl",
    "nomad_transition_worker_state.json",
    "nomad_selection_pressure_state.json",
    "nomad_swarm_registry.json",
}
SECRET_SHAPED_EXTENSIONS = {".pem", ".key", ".p12", ".pfx"}
SECRET_KEY_TERMS = ("secret", "private_key", "seed_phrase", "password", "credential", "api_key", "access_token")
SECRET_VALUE_TERMS = ("sk-", "ghp_", "bearer ", "private key", "seed phrase", "secret=")


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _text(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower().replace("\\", "/")
    text = re.sub(r"[^a-z0-9_.:/#-]+", "_", text)
    return text[:160].strip("_.:/#-") or fallback


def _digest(value: Any, length: int = 32) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _proof_digest(value: Any) -> str:
    return f"sha256:{_digest(value, length=64)}"


def _run_git(workspace: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(workspace), *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
    )


def _normalize_path(value: str) -> str:
    return value.replace("\\", "/").strip("/")


def _is_local_artifact(path: str) -> bool:
    p = _normalize_path(path)
    lower = p.lower()
    name = Path(lower).name
    if lower in LOCAL_ARTIFACT_NAMES or name in LOCAL_ARTIFACT_NAMES:
        return True
    if any(lower.startswith(prefix) for prefix in LOCAL_ARTIFACT_PREFIXES):
        return True
    if Path(lower).suffix in SECRET_SHAPED_EXTENSIONS:
        return True
    if lower.endswith(".jsonl") and ("ledger" in lower or "cache" in lower):
        return True
    return False


def _bucket_for(path: str) -> str:
    p = _normalize_path(path)
    lower = p.lower()
    name = Path(lower).name
    if _is_local_artifact(p):
        return "excluded_local_artifacts"
    if lower.startswith("test_") or "/test_" in lower or lower.startswith("tests/"):
        return "tests"
    if lower.startswith("public/downloads/") or lower.startswith("scripts/"):
        return "worker_and_operator_scripts"
    if lower.startswith("public/") or lower in {"index.html", "style.css"}:
        return "public_agent_surface"
    if name in {"nomad_api.py", "app.py", "main.py", "render_hosting.py", "workflow.py"}:
        return "api_runtime_core"
    if lower.endswith(".md") or name in {"agents.md", "readme.md"}:
        return "docs_and_operating_contracts"
    if any(term in lower for term in ("autogenesis", "opaque", "anti_consensus", "entropy", "representational", "nonhuman", "recruitment_gradient", "self_improvement")):
        return "agp_and_nonhuman_runtime"
    if lower.endswith(".py"):
        return "python_runtime_support"
    if lower.endswith(".json"):
        return "json_contracts"
    return "misc_shadow_material"


def _risk_for(bucket: str, paths: list[str], total_changed_lines: int) -> str:
    if bucket == "excluded_local_artifacts":
        return "blocked"
    if any(_is_local_artifact(path) for path in paths):
        return "blocked"
    if bucket in {"api_runtime_core", "worker_and_operator_scripts"}:
        return "high" if total_changed_lines > 500 else "medium"
    if bucket == "agp_and_nonhuman_runtime":
        return "medium" if total_changed_lines <= 1000 else "high"
    if bucket in {"docs_and_operating_contracts", "tests"}:
        return "low"
    return "medium"


def _promotion_status(bucket: str, risk: str, has_tests: bool) -> str:
    if risk == "blocked":
        return "exclude_local_artifact"
    if risk == "secret_review":
        return "shadow_only_until_secret_review"
    if bucket == "tests":
        return "shadow_test_material"
    if bucket == "docs_and_operating_contracts":
        return "shadow_only"
    if has_tests and risk in {"low", "medium"}:
        return "test_required_before_promote"
    return "shadow_only_until_tests_and_verifier"


def _contains_secret_terms(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in SECRET_VALUE_TERMS)


def _status_entries(workspace: Path) -> list[dict[str, Any]]:
    proc = _run_git(workspace, "status", "--porcelain=v1", "-z")
    parts = [part for part in proc.stdout.split("\0") if part]
    entries: list[dict[str, Any]] = []
    i = 0
    while i < len(parts):
        raw = parts[i]
        status = raw[:2]
        path = raw[3:] if len(raw) > 3 else ""
        original = ""
        if status.startswith("R") or status.startswith("C"):
            i += 1
            original = parts[i] if i < len(parts) else ""
        if path:
            entries.append({"status": status.strip() or "?", "path": _normalize_path(path), "original_path": _normalize_path(original)})
        i += 1
    return entries


def _numstat(workspace: Path, path: str, status: str) -> dict[str, Any]:
    if status == "??":
        full = workspace / path
        if full.is_file() and not _is_local_artifact(path):
            try:
                text = full.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            return {"additions": len(text.splitlines()), "deletions": 0}
        return {"additions": 0, "deletions": 0}
    proc = _run_git(workspace, "diff", "--numstat", "--", path, check=False)
    additions = deletions = 0
    for line in proc.stdout.splitlines():
        cols = line.split("\t")
        if len(cols) >= 3:
            try:
                additions += int(cols[0]) if cols[0].isdigit() else 0
                deletions += int(cols[1]) if cols[1].isdigit() else 0
            except ValueError:
                continue
    return {"additions": additions, "deletions": deletions}


def _diff_material(workspace: Path, path: str, status: str, *, max_patch_bytes: int) -> dict[str, Any]:
    if _is_local_artifact(path):
        return {
            "diff_digest": _proof_digest({"path": path, "status": status, "blocked": True}),
            "diff_preview": "",
            "blocked_content": True,
            "content_bytes": 0,
            "secret_shaped_terms_detected": False,
        }
    full = workspace / path
    if status == "??":
        if not full.is_file():
            return {
                "diff_digest": _proof_digest({"path": path, "status": status, "directory": True}),
                "diff_preview": "",
                "blocked_content": False,
                "content_bytes": 0,
                "secret_shaped_terms_detected": False,
            }
        try:
            raw = full.read_bytes()
        except OSError:
            raw = b""
        if len(raw) > MAX_UNTRACKED_BYTES:
            material = {"path": path, "status": status, "size": len(raw), "truncated_untracked": True}
            return {
                "diff_digest": _proof_digest(material),
                "diff_preview": "",
                "blocked_content": False,
                "content_bytes": len(raw),
                "secret_shaped_terms_detected": False,
            }
        text = raw.decode("utf-8", errors="replace")
        return {
            "diff_digest": f"sha256:{hashlib.sha256(raw).hexdigest()}",
            "diff_preview": text[:max_patch_bytes],
            "blocked_content": False,
            "content_bytes": len(raw),
            "secret_shaped_terms_detected": _contains_secret_terms(text),
        }
    proc = _run_git(workspace, "diff", "--", path, check=False)
    text = proc.stdout or ""
    encoded = text.encode("utf-8", errors="replace")
    return {
        "diff_digest": f"sha256:{hashlib.sha256(encoded).hexdigest()}",
        "diff_preview": text[:max_patch_bytes],
        "blocked_content": False,
        "content_bytes": len(encoded),
        "secret_shaped_terms_detected": _contains_secret_terms(text),
    }


def _test_plan_for(bucket: str, paths: list[str]) -> list[str]:
    test_files = [path for path in paths if _bucket_for(path) == "tests"]
    touched_tests = " ".join(test_files[:12])
    if bucket == "tests":
        return [f"python -m pytest {touched_tests} -q" if touched_tests else "python -m pytest -q"]
    if bucket == "api_runtime_core":
        return [
            "python -m py_compile nomad_api.py app.py workflow.py",
            "python -m pytest test_nomad_api.py test_direct_agent.py -q",
        ]
    if bucket == "agp_and_nonhuman_runtime":
        return [
            "python -m py_compile " + " ".join(path for path in paths if path.endswith(".py"))[:500],
            "python -m pytest test_nomad_autogenesis.py test_nomad_opaque_emergence.py test_nomad_anti_consensus.py -q",
        ]
    if bucket == "worker_and_operator_scripts":
        return [
            "python -m py_compile public/downloads/nomad_transition_worker.py",
            "python -m pytest test_nomad_transition_worker.py test_nomad_api.py -q",
        ]
    if bucket == "public_agent_surface":
        return ["python -m pytest test_nomad_api.py -q"]
    if bucket == "docs_and_operating_contracts":
        return ["noop: documentation contract only; verify links if promoted"]
    if bucket == "json_contracts":
        return ["python -m json.tool <changed_json>", "python -m pytest test_nomad_api.py -q"]
    return ["python -m pytest -q"]


def _candidate_from_group(
    *,
    workspace: Path,
    bucket: str,
    entries: list[dict[str, Any]],
    max_patch_bytes: int,
) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    aggregate_material: list[dict[str, Any]] = []
    total_additions = 0
    total_deletions = 0
    secret_detected = False
    for entry in entries:
        path = str(entry["path"])
        stats = _numstat(workspace, path, str(entry["status"]))
        material = _diff_material(workspace, path, str(entry["status"]), max_patch_bytes=max_patch_bytes)
        total_additions += int(stats.get("additions") or 0)
        total_deletions += int(stats.get("deletions") or 0)
        secret_detected = secret_detected or bool(material.get("secret_shaped_terms_detected"))
        files.append(
            {
                "path": path,
                "status": entry.get("status"),
                "additions": stats.get("additions", 0),
                "deletions": stats.get("deletions", 0),
                "diff_digest": material.get("diff_digest"),
                "blocked_content": material.get("blocked_content", False),
                "content_bytes": material.get("content_bytes", 0),
            }
        )
        aggregate_material.append(
            {
                "path": path,
                "status": entry.get("status"),
                "stats": stats,
                "diff_digest": material.get("diff_digest"),
                "secret_shaped_terms_detected": material.get("secret_shaped_terms_detected", False),
            }
        )
    paths = [str(item["path"]) for item in files]
    path_blocked = any(_is_local_artifact(path) for path in paths)
    risk = "blocked" if path_blocked else _risk_for(bucket, paths, total_additions + total_deletions)
    if risk != "blocked" and secret_detected:
        risk = "secret_review"
    has_tests = any(_bucket_for(path) == "tests" for path in paths)
    promotion_status = _promotion_status(bucket, risk, has_tests)
    candidate_core = {
        "bucket": bucket,
        "paths": paths,
        "aggregate_material": aggregate_material,
        "risk": risk,
        "promotion_status": promotion_status,
    }
    diff_digest = _proof_digest(aggregate_material)
    candidate_id = f"shadow-harvest-{_digest({'bucket': bucket, 'diff': diff_digest}, length=20)}"
    test_plan = _test_plan_for(bucket, paths)
    proof_core = {
        "candidate_id": candidate_id,
        "diff_digest": diff_digest,
        "risk": risk,
        "test_plan": test_plan,
        "promotion_status": promotion_status,
    }
    return {
        "ok": risk != "blocked",
        "schema": CANDIDATE_SCHEMA,
        "candidate_id": candidate_id,
        "candidate_type": "dirty_worktree_shadow_candidate",
        "file_group": bucket,
        "state": "shadow" if risk != "blocked" else "noop",
        "lifecycle": ["draft", "shadow", "tested", "weighted", "committed"],
        "paths": paths,
        "file_count": len(paths),
        "change_stats": {
            "additions": total_additions,
            "deletions": total_deletions,
            "changed_lines": total_additions + total_deletions,
        },
        "diff_digest": diff_digest,
        "proof_digest": _proof_digest(proof_core),
        "risk_class": risk,
        "secret_shaped_terms_detected": secret_detected,
        "side_effect_scope": "local_shadow_lane_read_only",
        "rollback_ref": f"noop:{candidate_id}",
        "local_test_plan": test_plan,
        "promotion_status": promotion_status,
        "promotion_gate": {
            "requires_independent_verifier": True,
            "requires_tests_green": risk not in {"low", "blocked"},
            "requires_diff_digest_match": True,
            "requires_no_secret_shaped_payload": True,
            "requires_secret_review": secret_detected and risk != "blocked",
            "allowed_commit_surface": "production_repo_only_after_tests_and_verifier",
        },
        "sepl_operator_trace": [
            {"op": "reflect", "input": "git_dirty_worktree", "output": bucket},
            {"op": "select", "input": diff_digest, "output": candidate_id},
            {"op": "improve", "input": "candidate_group", "output": "no_code_apply_shadow_descriptor"},
            {"op": "evaluate", "input": test_plan, "output": promotion_status},
            {"op": "commit", "input": _proof_digest(proof_core), "decision": promotion_status},
        ],
        "files": files,
    }


def harvest_shadow_candidates(
    workspace: str | Path,
    *,
    base_url: str = "",
    max_patch_bytes: int = MAX_PATCH_BYTES,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Compile one local git dirty state into AGP shadow candidates."""

    root = Path(workspace).expanduser().resolve()
    if not (root / ".git").exists():
        return {
            "ok": False,
            "schema": SCHEMA,
            "error": "not_a_git_worktree",
            "workspace": str(root),
            "generated_at": _iso_now(),
        }
    head = _run_git(root, "rev-parse", "--short", "HEAD", check=False).stdout.strip()
    branch = _run_git(root, "branch", "--show-current", check=False).stdout.strip()
    entries = _status_entries(root)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        grouped.setdefault(_bucket_for(str(entry["path"])), []).append(entry)
    candidates = [
        _candidate_from_group(workspace=root, bucket=bucket, entries=rows, max_patch_bytes=max_patch_bytes)
        for bucket, rows in sorted(grouped.items())
    ]
    blocked = [item for item in candidates if item.get("promotion_status") == "exclude_local_artifact"]
    promotable = [
        item
        for item in candidates
        if item.get("promotion_status")
        in {
            "test_required_before_promote",
            "shadow_only_until_tests_and_verifier",
            "shadow_test_material",
            "shadow_only",
            "shadow_only_until_secret_review",
        }
        and item.get("ok")
    ]
    out = {
        "ok": True,
        "schema": SCHEMA,
        "version": "2026.05.21",
        "generated_at": _iso_now(),
        "workspace": str(root),
        "branch": branch,
        "head": head,
        "mode": "local_read_only_shadow_candidate_harvest",
        "machine_thesis": "self_modification_is_raw_material_not_production_truth",
        "candidate_count": len(candidates),
        "promotable_candidate_count": len(promotable),
        "blocked_candidate_count": len(blocked),
        "dirty_file_count": sum(len(item.get("paths") or []) for item in candidates),
        "summary": {
            "by_group": [
                {
                    "file_group": item.get("file_group"),
                    "file_count": item.get("file_count"),
                    "risk_class": item.get("risk_class"),
                    "promotion_status": item.get("promotion_status"),
                    "changed_lines": (item.get("change_stats") or {}).get("changed_lines", 0),
                }
                for item in candidates
            ],
            "recommended_next_action": "run_tests_for_test_required_candidates_then_promote_smallest_diff_digest_to_production_repo",
        },
        "candidates": candidates,
        "proof_digest": _proof_digest(
            {
                "workspace": str(root),
                "head": head,
                "branch": branch,
                "candidates": [(item.get("candidate_id"), item.get("proof_digest")) for item in candidates],
            }
        ),
        "routes": {
            "shadow_harvest_contract": _u(base_url, "/.well-known/nomad-shadow-harvest.json"),
            "autogenesis_shadow_lane": _u(base_url, "/swarm/shadow-lane/candidates?type=autogenesis"),
        },
        "machine_instruction": "treat_candidates_as_shadow_only; never_apply_dirty_worktree_directly; promote_only_after_test_digest_and_independent_verifier",
    }
    if output_path:
        target = Path(output_path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(out, indent=2, ensure_ascii=True, sort_keys=True), encoding="utf-8")
        out["written_to"] = str(target)
    return out


def build_shadow_harvest_surface(*, base_url: str) -> dict[str, Any]:
    """Expose the public contract for local shadow harvests."""

    root = (base_url or "").strip().rstrip("/")
    return {
        "ok": True,
        "schema": SURFACE_SCHEMA,
        "version": "2026.05.21",
        "generated_at": _iso_now(),
        "purpose": "compile_agent_self_modification_dirty_state_into_proof_gated_shadow_candidates",
        "nonhuman_boundary": {
            "not_human_review_board": True,
            "compiler_shape": "git_dirty_state_to_digest_candidates",
            "production_policy": "no_dirty_change_reaches_runtime_without_test_digest_and_independent_verifier",
        },
        "candidate_schema": CANDIDATE_SCHEMA,
        "candidate_fields": [
            "candidate_id",
            "file_group",
            "paths",
            "diff_digest",
            "proof_digest",
            "risk_class",
            "side_effect_scope",
            "rollback_ref",
            "local_test_plan",
            "promotion_status",
            "sepl_operator_trace",
        ],
        "blocked_material": [
            "env_files",
            "private_keys",
            "secret_scrub_mirrors",
            "local_data_dirs",
            "jsonl_ledgers",
            "cache_dirs",
        ],
        "local_cli": {
            "command": "python nomad_cli.py shadow-harvest --workspace %USERPROFILE%\\\\Desktop\\\\Nomad --output update\\\\shadow_harvest_latest.json --json",
            "side_effect_scope": "read_only_source_workspace_write_report_only",
        },
        "routes": {
            "self": _u(root, "/.well-known/nomad-shadow-harvest.json"),
            "shadow_lane": _u(root, "/swarm/shadow-lane/candidates?type=autogenesis"),
            "autogenesis": _u(root, "/.well-known/nomad-autogenesis.json"),
        },
        "machine_instruction": "run_local_cli_on_dirty_workspace_then_submit_only_best_digest_candidates_to_shadow_lane_after_tests",
    }
