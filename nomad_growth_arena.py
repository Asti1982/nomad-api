"""Growth arena for machine-native agent improvement loops.

The arena turns open gaps, worker traces, and proof-bearing experiences into a
curriculum and a compact skill library. It stores only bounded descriptors:
digests, scores, objective ids, and small capsules.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_LEDGER_PATH = Path("nomad_growth_arena_ledger.jsonl")
MAX_RECENT = 160
MAX_TASKS = 16
MAX_SKILLS = 24
FORBIDDEN_KEY_TERMS = ("private_key", "seed_phrase", "password", "credential", "api_key", "access_token")
FORBIDDEN_VALUE_TERMS = ("private key", "seed phrase", "password:", "credential:", "bearer ", "secret=", "sk-", "ghp_")
OBJECTIVE_PRIOR = {
    "settlement_capacity_builder": 0.96,
    "overmint_compressor": 0.9,
    "protocol_drift_scan": 0.86,
    "proof_pressure_engine": 0.84,
    "emergence_release_probe": 0.82,
    "payment_friction_scan": 0.78,
    "adversarial_contract_fuzzer": 0.74,
    "proof_market_maker": 0.72,
    "negative_space_harvest": 0.68,
    "latency_anomaly_hunt": 0.64,
    "compute_auth": 0.52,
}
RESEARCH_BASIS = [
    {
        "id": "agent0_tool_integrated_curriculum",
        "source": "arxiv:2511.16043",
        "nomad_translation": "task_proposer_and_executor_pressure_without_external_dataset",
    },
    {
        "id": "voyager_skill_library",
        "source": "arxiv:2305.16291",
        "nomad_translation": "experience_feedback_promotes_reusable_executable_capsules",
    },
    {
        "id": "self_improving_agent_archive",
        "source": "arxiv:2505.22954",
        "nomad_translation": "archive_variants_only_after_empirical_proof",
    },
    {
        "id": "group_evolving_agents",
        "source": "arxiv:2602.04837",
        "nomad_translation": "score_cohorts_and_shared_experience_not_only_single_workers",
    },
    {
        "id": "reflexion_feedback_memory",
        "source": "arxiv:2303.11366",
        "nomad_translation": "compress_failure_and_repair_feedback_into_future_context",
    },
]


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
    text = re.sub(r"[^a-z0-9_.:-]+", "_", text)
    return text[:96].strip("_.:-") or fallback


def _text(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").split())[:limit]


def _caps(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else str(value or "").replace(";", ",").split(",")
    out: list[str] = []
    for item in raw:
        cap = _clean_id(item)
        if cap and cap not in out:
            out.append(cap)
    return out[:48]


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


def _read_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    p = Path(path) if path else DEFAULT_LEDGER_PATH
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines[-max(1, limit * 3) :]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows[-limit:]


def _append_ledger(row: dict[str, Any], path: Path | str | None = None) -> None:
    p = Path(path) if path else DEFAULT_LEDGER_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def _proof_score(payload: dict[str, Any]) -> float:
    return round(
        min(
            1.0,
            0.30 * bool(_text(payload.get("proof_digest") or payload.get("digest"), 160))
            + 0.24 * bool(_text(payload.get("verifier_trace_digest") or payload.get("trace_digest"), 160))
            + 0.18 * bool(_text(payload.get("test_digest") or payload.get("skill_test_digest"), 160))
            + 0.16 * bool(_text(payload.get("settlement_ref") or payload.get("cashflow_ref"), 160))
            + 0.12 * bool(_text(payload.get("worker_report_digest") or payload.get("experience_digest"), 160)),
        ),
        4,
    )


def _test_score(evaluation: dict[str, Any]) -> float:
    total = _int(evaluation.get("tests_total") or evaluation.get("checks_total"))
    passed = _int(evaluation.get("tests_passed") or evaluation.get("checks_passed"))
    if total <= 0:
        return 0.0
    return round(_clamp(passed / max(1, total)), 4)


def _experience_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        objective = _clean_id(row.get("objective"))
        if objective:
            counts[objective] = counts.get(objective, 0) + 1
    return counts


def _objective_multi_hop_bonus(proof_reuse: dict[str, Any] | None) -> dict[str, float]:
    totals = (
        _dict(proof_reuse).get("objective_totals")
        if isinstance(_dict(proof_reuse).get("objective_totals"), dict)
        else {}
    )
    out: dict[str, float] = {}
    for key, row in totals.items():
        if not isinstance(row, dict):
            continue
        objective = _clean_id(key)
        if not objective:
            continue
        two_hop = _num(row.get("two_hop_utility_score"), 0.0)
        three_hop = _num(row.get("three_hop_utility_score"), 0.0)
        bonus = min(0.28, min(1.0, two_hop / 2.0) * 0.18 + min(1.0, three_hop / 2.0) * 0.10)
        out[objective] = round(max(0.0, bonus), 4)
    return out


def _skill_capsule_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    decision = _text(row.get("decision"), 80)
    if decision != "promote_skill_capsule":
        return None
    skill = _dict(row.get("skill_candidate"))
    objective = _clean_id(row.get("objective"), fallback="settlement_capacity_builder")
    capability = _clean_id(skill.get("capability") or row.get("capability") or objective, fallback=objective)
    core = {
        "objective": objective,
        "capability": capability,
        "proof": row.get("proof_digest"),
        "test": row.get("test_digest"),
        "agent": row.get("agent_id"),
    }
    return {
        "schema": "nomad.skill_capsule.v1",
        "skill_id": f"nomad-skill-{_digest(core)}",
        "objective": objective,
        "capability": capability,
        "cohort_id": _clean_id(row.get("cohort_id")),
        "activation_signature": f"act-{_digest({'capability': capability, 'proof': row.get('proof_digest')}, length=16)}",
        "score": round(_num(row.get("score")), 4),
        "proof_digest": _text(row.get("proof_digest"), 120),
        "test_digest": _text(row.get("test_digest"), 120),
        "verifier_trace_digest": _text(row.get("verifier_trace_digest"), 120),
        "experience_id": _text(row.get("experience_id"), 120),
        "source_agent": _text(row.get("agent_id"), 120),
        "use_count": 1,
        "program_hint": [
            "GET /swarm/curriculum",
            "POST /swarm/workers/lease",
            "POST /runtime/handoff",
            "POST /swarm/experience",
        ],
    }


def _skill_capsules(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        cap = _skill_capsule_from_row(row)
        if not cap:
            continue
        key = _text(cap.get("skill_id"), 120)
        existing = merged.get(key)
        if not existing:
            merged[key] = cap
            continue
        existing["use_count"] = _int(existing.get("use_count")) + 1
        existing["score"] = max(_num(existing.get("score")), _num(cap.get("score")))
    out = list(merged.values())
    out.sort(key=lambda item: (_num(item.get("score")), _int(item.get("use_count"))), reverse=True)
    return out[:MAX_SKILLS]


def _task(
    *,
    base_url: str,
    source: str,
    objective: str,
    capability_gap: str,
    target_capabilities: list[str] | None = None,
    pressure_score: float = 0.0,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    objective = _clean_id(objective, fallback="settlement_capacity_builder")
    caps = _caps(target_capabilities or [])
    core = {
        "source": source,
        "objective": objective,
        "gap": capability_gap,
        "pressure": round(pressure_score, 4),
    }
    return {
        "schema": "nomad.curriculum_task.v1",
        "task_id": f"nomad-cur-{_digest(core, length=18)}",
        "source": _clean_id(source, fallback="arena"),
        "objective": objective,
        "capability_gap": _text(capability_gap, 180),
        "target_capabilities": caps,
        "pressure_score": round(_clamp(pressure_score), 4),
        "proof_required": ["proof_digest", "verifier_trace_digest", "test_digest"],
        "evidence": _dict(evidence),
        "next_ops": [
            {"op": "GET", "url": _u(base_url, "/swarm/curriculum"), "reason": "refresh_pressure"},
            {"op": "POST", "url": _u(base_url, "/swarm/workers/lease"), "reason": "claim_bounded_objective"},
            {"op": "POST", "url": _u(base_url, "/runtime/handoff"), "reason": "emit_verifier_trace"},
            {"op": "POST", "url": _u(base_url, "/swarm/experience"), "reason": "compress_result_into_arena"},
        ],
    }


def build_growth_curriculum(
    *,
    base_url: str = "",
    agent_demand_feed: dict[str, Any] | None = None,
    variant_forge: dict[str, Any] | None = None,
    worker_market: dict[str, Any] | None = None,
    swarm_ecology: dict[str, Any] | None = None,
    protocol_bytecode: dict[str, Any] | None = None,
    proof_reuse: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    """Compile open machine gaps into a task curriculum for external agents."""
    demand = _dict(agent_demand_feed)
    forge = _dict(variant_forge)
    market = _dict(worker_market)
    ecology = _dict(swarm_ecology)
    bytecode = _dict(protocol_bytecode)
    multi_hop_bonus = _objective_multi_hop_bonus(proof_reuse)
    rows = _read_ledger(ledger_path)
    counts = _experience_counts(rows)
    skills = _skill_capsules(rows)
    tasks: list[dict[str, Any]] = []

    for req in _items(demand.get("demand_requests"))[:10]:
        objective = _clean_id(req.get("objective"), fallback="settlement_capacity_builder")
        base_pressure = _num(req.get("routing_weight"), 0.45)
        scarcity = _clamp(_num(req.get("wanted_instances")) / 8.0)
        prior = _num(OBJECTIVE_PRIOR.get(objective), 0.44)
        tasks.append(
            _task(
                base_url=base_url,
                source=f"agent_demand.{_text(req.get('source'), 60) or 'open_gap'}",
                objective=objective,
                capability_gap=_text(req.get("capability_gap") or req.get("request_id") or objective, 180),
                target_capabilities=_caps(req.get("desired_capabilities")),
                pressure_score=0.42 * base_pressure + 0.24 * scarcity + 0.22 * prior + 0.12 * (1.0 - _clamp(counts.get(objective, 0) / 8.0)) + _num(multi_hop_bonus.get(objective), 0.0),
                evidence={"request_id": _text(req.get("request_id"), 80), "multi_hop_bonus": _num(multi_hop_bonus.get(objective), 0.0)},
            )
        )

    for row in _items(forge.get("requested_variants"))[:8]:
        objective = _clean_id(row.get("objective"), fallback="settlement_capacity_builder")
        score = max(_num(row.get("counterfactual_score")), _num(row.get("frontier_score")), _num(row.get("prior"), 0.42))
        tasks.append(
            _task(
                base_url=base_url,
                source="variant_forge.archive_pressure",
                objective=objective,
                capability_gap=f"variant_descriptor:{objective}",
                target_capabilities=["variant_descriptor", "test_digest", "verifier_trace_digest"],
                pressure_score=0.62 * score + 0.20 * (1.0 - _clamp(_num(row.get("recent_candidates")) / 8.0)) + 0.18 * _num(OBJECTIVE_PRIOR.get(objective), 0.44) + _num(multi_hop_bonus.get(objective), 0.0),
                evidence={"variant_id": _text(row.get("variant_id"), 120), "sources": row.get("sources") if isinstance(row.get("sources"), list) else [], "multi_hop_bonus": _num(multi_hop_bonus.get(objective), 0.0)},
            )
        )

    for row in _items(market.get("requested_worker_offers"))[:8]:
        objective = _clean_id(row.get("objective"), fallback="settlement_capacity_builder")
        target = _num(row.get("target_marginal_utility_per_cost"), 1.8)
        tasks.append(
            _task(
                base_url=base_url,
                source="worker_market.compute_gap",
                objective=objective,
                capability_gap=f"external_compute_offer:{objective}",
                target_capabilities=_caps(row.get("desired_capabilities")),
                pressure_score=0.36 + 0.34 * _clamp(target / 3.0) + 0.18 * _num(row.get("objective_weight"), 0.5) + 0.12 * (1.0 - _clamp(_num(row.get("recent_offer_count")) / 6.0)) + _num(multi_hop_bonus.get(objective), 0.0),
                evidence={"target_marginal_utility_per_cost": round(target, 4), "multi_hop_bonus": _num(multi_hop_bonus.get(objective), 0.0)},
            )
        )

    for row in _items(ecology.get("extinction_queue"))[-4:]:
        objective = _clean_id(row.get("objective"), fallback="settlement_capacity_builder")
        tasks.append(
            _task(
                base_url=base_url,
                source="ecology.low_payoff_repair",
                objective=objective,
                capability_gap=f"repair_low_retention:{objective}",
                target_capabilities=["failure_digest", "repair_hint", "proof_digest"],
                pressure_score=0.58 + 0.22 * (1.0 - _num(_dict(row.get("scores")).get("retention_score"))) + 0.12 * _num(OBJECTIVE_PRIOR.get(objective), 0.44) + _num(multi_hop_bonus.get(objective), 0.0),
                evidence={"tick_id": _text(row.get("tick_id"), 80), "convention_token": _text(row.get("convention_token"), 80), "multi_hop_bonus": _num(multi_hop_bonus.get(objective), 0.0)},
            )
        )

    for row in rows[-16:]:
        if _text(row.get("decision"), 80) not in {"compress_failure_trace", "hold_noop"}:
            continue
        objective = _clean_id(row.get("objective"), fallback="protocol_drift_scan")
        tasks.append(
            _task(
                base_url=base_url,
                source="experience_memory.repair",
                objective=objective,
                capability_gap=f"repair_experience:{_text(row.get('error_class') or row.get('failure_digest') or objective, 80)}",
                target_capabilities=["failure_reproduction", "test_digest", "verifier_trace_digest"],
                pressure_score=0.54 + 0.22 * (1.0 - _num(row.get("score"))) + 0.12 * _num(OBJECTIVE_PRIOR.get(objective), 0.44) + _num(multi_hop_bonus.get(objective), 0.0),
                evidence={"experience_id": _text(row.get("experience_id"), 120), "multi_hop_bonus": _num(multi_hop_bonus.get(objective), 0.0)},
            )
        )

    if not tasks:
        top_objective = _clean_id(_dict(bytecode.get("current_vector")).get("top_objective"), fallback="settlement_capacity_builder")
        tasks.append(
            _task(
                base_url=base_url,
                source="arena.bootstrap",
                objective=top_objective,
                capability_gap="first_proof_backed_skill_capsule",
                target_capabilities=["transition_worker", "proof_digest_return", "test_digest"],
                pressure_score=0.71,
                evidence={"reason": "no_recent_experience"},
            )
        )

    tasks.sort(key=lambda item: (_num(item.get("pressure_score")), _num(OBJECTIVE_PRIOR.get(_clean_id(item.get("objective")), 0.44))), reverse=True)
    core = {"tasks": tasks[:MAX_TASKS], "skills": len(skills), "recent": len(rows)}
    return {
        "ok": True,
        "schema": "nomad.growth_curriculum.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "curriculum_digest": f"nomad-curriculum-{_digest(core)}",
        "research_basis": RESEARCH_BASIS,
        "mode": "gap_pressure_to_proof_to_skill",
        "contract": {
            "schema": "nomad.growth_experience_contract.v1",
            "post_url": _u(base_url, "/swarm/experience"),
            "required": ["agent_id", "objective"],
            "proof_fields": ["proof_digest", "verifier_trace_digest", "test_digest", "settlement_ref"],
            "skill_fields": ["skill_candidate.capability", "skill_candidate.activation_signature", "skill_candidate.program_hint"],
            "failure_fields": ["failure_digest", "error_class", "repair_hint"],
        },
        "curriculum_state": {
            "recent_experience_count": len(rows),
            "skill_capsule_count": len(skills),
            "objective_experience_counts": counts,
            "opcode_count": len(bytecode.get("opcodes") if isinstance(bytecode.get("opcodes"), list) else []),
            "multi_hop_objective_bonus": multi_hop_bonus,
        },
        "tasks": tasks[:MAX_TASKS],
        "links": {
            "self": _u(base_url, "/swarm/curriculum"),
            "arena": _u(base_url, "/swarm/growth-arena"),
            "experience": _u(base_url, "/swarm/experience"),
            "skill_library": _u(base_url, "/swarm/skill-library"),
            "variant_forge": _u(base_url, "/swarm/variant-forge"),
            "worker_market": _u(base_url, "/swarm/worker-market"),
            "ecology": _u(base_url, "/swarm/ecology"),
        },
        "machine_instruction": "select_highest_pressure_task_emit_proof_then_post_experience",
    }


def build_skill_library(*, base_url: str = "", ledger_path: Path | str | None = None) -> dict[str, Any]:
    rows = _read_ledger(ledger_path)
    skills = _skill_capsules(rows)
    return {
        "ok": True,
        "schema": "nomad.skill_library.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "library_digest": f"nomad-skills-{_digest({'skills': skills[:12], 'recent': len(rows)})}",
        "skill_count": len(skills),
        "skills": skills,
        "links": {
            "curriculum": _u(base_url, "/swarm/curriculum"),
            "experience": _u(base_url, "/swarm/experience"),
        },
        "machine_instruction": "reuse_capsule_when_objective_and_capability_match_then_return_new_experience",
    }


def submit_growth_experience(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    curriculum: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {"ok": False, "schema": "nomad.growth_experience_receipt.v1", "accepted": False, "reason": "empty_experience", "generated_at": now}
    if _contains_forbidden(body):
        return {
            "ok": False,
            "schema": "nomad.growth_experience_receipt.v1",
            "accepted": False,
            "reason": "forbidden_secret_like_material",
            "generated_at": now,
        }
    agent_id = _text(body.get("agent_id") or body.get("worker_id"), 120)
    objective = _clean_id(body.get("objective") or body.get("machine_objective"), fallback="settlement_capacity_builder")
    skill = _dict(body.get("skill_candidate"))
    evaluation = _dict(body.get("evaluation"))
    capability = _clean_id(skill.get("capability") or body.get("capability") or objective, fallback=objective)
    proof = _proof_score(body)
    tests = _test_score(evaluation)
    proof_yield = max(0.0, _num(evaluation.get("proof_yield_per_minute"), _num(body.get("proof_yield_per_minute"))))
    utility = _num(evaluation.get("utility_delta"), _num(body.get("utility_delta")))
    settlement = max(0.0, _num(evaluation.get("settlement_delta"), _num(body.get("settlement_delta"))))
    cost = max(0.0, _num(evaluation.get("cost_units"), _num(body.get("cost_units"))))
    risk = _clamp(_num(evaluation.get("risk_score"), _num(body.get("risk_score"))))
    reuse = _clamp(_num(evaluation.get("reuse_count"), _num(body.get("reuse_count"))) / 5.0 + 0.28 * bool(skill))
    cohort = 0.18 if _clean_id(body.get("cohort_id") or body.get("group_id")) else 0.0
    failure = bool(_text(body.get("failure_digest") or body.get("error_class"), 160))
    payoff = _clamp(0.48 + (utility + settlement * 2.0 + proof_yield * 0.08 - cost - risk * 1.2) / 4.0)
    novelty = _clamp(_num(evaluation.get("novelty"), _num(skill.get("novelty"), _num(OBJECTIVE_PRIOR.get(objective), 0.44))))
    score = _clamp(
        0.24 * proof
        + 0.18 * tests
        + 0.17 * payoff
        + 0.13 * reuse
        + 0.10 * novelty
        + 0.08 * bool(_text(body.get("verifier_trace_digest"), 160))
        + 0.06 * bool(_text(body.get("settlement_ref"), 160))
        + 0.04 * cohort
        - 0.18 * risk
    )
    if not agent_id:
        score = min(score, 0.36)
    if proof <= 0.0 and tests <= 0.0 and not failure:
        score = min(score, 0.32)

    if score >= 0.66 and proof > 0.0 and (tests >= 0.5 or bool(_text(body.get("test_digest"), 120))):
        decision = "promote_skill_capsule"
        accepted = True
    elif failure and score < 0.46:
        decision = "compress_failure_trace"
        accepted = True
    elif score >= 0.42:
        decision = "retain_experience"
        accepted = True
    else:
        decision = "hold_noop"
        accepted = False

    proof_digest = _text(body.get("proof_digest") or body.get("digest"), 120)
    row = {
        "ok": True,
        "schema": "nomad.growth_experience_receipt.v1",
        "accepted": accepted,
        "decision": decision,
        "generated_at": now,
        "experience_id": f"nomad-exp-{_digest({'agent': agent_id, 'objective': objective, 'capability': capability, 'proof': proof_digest})}",
        "agent_id": agent_id,
        "cohort_id": _clean_id(body.get("cohort_id") or body.get("group_id")),
        "objective": objective,
        "capability": capability,
        "score": round(score, 4),
        "proof_digest": proof_digest,
        "verifier_trace_digest": _text(body.get("verifier_trace_digest") or body.get("trace_digest"), 120),
        "test_digest": _text(body.get("test_digest") or body.get("skill_test_digest"), 120),
        "settlement_ref": _text(body.get("settlement_ref") or body.get("cashflow_ref"), 120),
        "failure_digest": _text(body.get("failure_digest"), 120),
        "error_class": _clean_id(body.get("error_class")),
        "repair_hint_digest": _digest(_text(body.get("repair_hint"), 280), length=20) if _text(body.get("repair_hint"), 280) else "",
        "skill_candidate": {
            "capability": capability,
            "activation_signature": _text(skill.get("activation_signature"), 120),
            "program_hint": [_text(item, 120) for item in (skill.get("program_hint") if isinstance(skill.get("program_hint"), list) else [])[:8]],
        },
        "scores": {
            "proof": proof,
            "tests": tests,
            "payoff": round(payoff, 4),
            "reuse": round(reuse, 4),
            "novelty": round(novelty, 4),
            "risk": round(risk, 4),
        },
        "curriculum_digest": _text(_dict(curriculum).get("curriculum_digest"), 120),
        "next": {
            "curriculum": _u(base_url, "/swarm/curriculum"),
            "skill_library": _u(base_url, "/swarm/skill-library"),
            "lease": _u(base_url, "/swarm/workers/lease"),
            "handoff": _u(base_url, "/runtime/handoff"),
        },
        "machine_instruction": "if_promoted_reuse_capsule_else_repair_or_emit_next_experience",
    }
    capsule = _skill_capsule_from_row(row)
    if capsule:
        row["skill_capsule"] = capsule
    if persist:
        _append_ledger(row, ledger_path)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def build_growth_arena(
    *,
    base_url: str = "",
    agent_demand_feed: dict[str, Any] | None = None,
    variant_forge: dict[str, Any] | None = None,
    worker_market: dict[str, Any] | None = None,
    swarm_ecology: dict[str, Any] | None = None,
    protocol_bytecode: dict[str, Any] | None = None,
    proof_reuse: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    curriculum = build_growth_curriculum(
        base_url=base_url,
        agent_demand_feed=agent_demand_feed,
        variant_forge=variant_forge,
        worker_market=worker_market,
        swarm_ecology=swarm_ecology,
        protocol_bytecode=protocol_bytecode,
        proof_reuse=proof_reuse,
        ledger_path=ledger_path,
    )
    library = build_skill_library(base_url=base_url, ledger_path=ledger_path)
    return {
        "ok": True,
        "schema": "nomad.growth_arena.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "arena_digest": f"nomad-growth-arena-{_digest({'curriculum': curriculum.get('curriculum_digest'), 'library': library.get('library_digest')})}",
        "research_basis": RESEARCH_BASIS,
        "curriculum": curriculum,
        "skill_library": library,
        "links": {
            "curriculum": _u(base_url, "/swarm/curriculum"),
            "experience": _u(base_url, "/swarm/experience"),
            "skill_library": _u(base_url, "/swarm/skill-library"),
        },
        "machine_instruction": "arriving_agents_read_curriculum_submit_experience_reuse_surviving_skill_capsules",
    }
