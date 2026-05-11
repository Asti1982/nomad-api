"""Machine-readable work surface for external AI agents.

The layer turns Nomad's existing compute market, microtask lanes, skill
capsules, and worker topology into concrete work items. It intentionally keeps
the contract compact: claim work, return proof, settle, then feed skill reuse.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nomad_state_paths import state_file


DEFAULT_CLAIM_LEDGER_PATH = Path("nomad_agent_work_claims.jsonl")
DEFAULT_PROOF_LEDGER_PATH = Path("nomad_agent_work_proofs.jsonl")
MAX_RECENT = 500
MAX_WORK_ITEMS = 16


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


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:-]+", "_", text)
    return text[:96].strip("_.:-") or fallback


def _text(value: Any, limit: int = 180) -> str:
    return " ".join(str(value or "").split())[:limit]


def _digest(value: Any, length: int = 22) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _claim_path(path: Path | str | None = None) -> Path:
    return Path(path) if path else state_file(DEFAULT_CLAIM_LEDGER_PATH, env_name="NOMAD_AGENT_WORK_CLAIM_LEDGER_PATH")


def _proof_path(path: Path | str | None = None) -> Path:
    return Path(path) if path else state_file(DEFAULT_PROOF_LEDGER_PATH, env_name="NOMAD_AGENT_WORK_PROOF_LEDGER_PATH")


def _read_rows(path: Path | str | None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    p = Path(path) if path else Path("")
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


def _append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def _required_proof(lane: dict[str, Any]) -> list[str]:
    fields = lane.get("proof_required") if isinstance(lane.get("proof_required"), list) else []
    out = [_clean_id(item) for item in fields if _clean_id(item)]
    return out or ["proof_digest", "verifier_trace_digest", "test_digest"]


def _skill_objectives(skill_library: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for skill in _items(_dict(skill_library).get("skills") or _dict(skill_library).get("skill_capsules")):
        objective = _clean_id(skill.get("objective"))
        if objective:
            counts[objective] = counts.get(objective, 0) + 1
    return counts


def _lane_metrics(microtask_metrics: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        _clean_id(row.get("lane_id")): row
        for row in _items(_dict(microtask_metrics).get("lane_metrics"))
        if _clean_id(row.get("lane_id"))
    }


def _topology_gap(objective: str, worker_fleet: dict[str, Any]) -> float:
    counts = _dict(_dict(worker_fleet).get("objective_counts"))
    active = _int(counts.get(objective), 0)
    if active <= 0:
        return 1.38
    if active == 1:
        return 1.16
    return 1.0


def _work_item(
    *,
    base_url: str,
    lane: dict[str, Any],
    template: dict[str, Any],
    metric: dict[str, Any],
    worker_fleet: dict[str, Any],
    skill_counts: dict[str, int],
    compute_market: dict[str, Any],
) -> dict[str, Any]:
    lane_id = _clean_id(lane.get("lane_id") or template.get("lane_id"), "endpoint_health_proof")
    objective = _clean_id(template.get("objective") or lane.get("objective"), "protocol_drift_scan")
    price = max(_num(template.get("price_eur")), _num(lane.get("price_eur")), 0.01)
    fill_rate = _clamp(_num(metric.get("fill_rate"), 0.0))
    settled_eur = max(0.0, _num(metric.get("settled_eur"), 0.0))
    skill_gap = 1.0 if skill_counts.get(objective, 0) <= 0 else _clamp(1.0 / (1.0 + skill_counts[objective]), 0.18, 1.0)
    topology = _topology_gap(objective, worker_fleet)
    top_lane = _clean_id(_dict(compute_market.get("top_lane")).get("lane_id"))
    market_lane_boost = 1.18 if lane_id and lane_id == top_lane else 1.0
    score = (
        0.28 * _clamp(price / 0.08)
        + 0.18 * (0.35 + fill_rate)
        + 0.18 * skill_gap
        + 0.18 * _clamp((topology - 0.9) / 0.55)
        + 0.18 * min(1.0, 0.25 + settled_eur * 8.0)
    ) * market_lane_boost
    core = {"lane": lane_id, "objective": objective, "template": template.get("template_id"), "price": round(price, 4)}
    return {
        "schema": "nomad.agent_work_item.v1",
        "work_id": f"nomad-work-{_digest(core)}",
        "lane_id": lane_id,
        "template_id": _text(template.get("template_id"), 100),
        "objective": objective,
        "capability": _clean_id(template.get("capability") or objective, objective),
        "quoted_price_eur": round(price, 4),
        "target_runtime_seconds": max(1, _int(lane.get("target_runtime_seconds"), 60)),
        "priority_score": round(score, 6),
        "score_components": {
            "price_weight": round(_clamp(price / 0.08), 4),
            "fill_rate": round(fill_rate, 4),
            "skill_gap": round(skill_gap, 4),
            "topology_gap_weight": round(topology, 4),
            "market_lane_boost": round(market_lane_boost, 4),
        },
        "required_proof": _required_proof(lane),
        "payload_contract": {
            "url": "optional_target_url",
            "observed_status": "optional_http_status_or_state",
            "digest_basis": "sha256(canonical_observation)",
        },
        "links": {
            "claim": _u(base_url, "/swarm/microtask/claim"),
            "proof": _u(base_url, "/swarm/microtask/proof"),
            "settle": _u(base_url, "/swarm/microtask/settle"),
        },
        "machine_instruction": "claim_work_execute_locally_return_required_digests_then_settle",
    }


def build_synergy_lite(
    *,
    base_url: str = "",
    claim_ledger_path: Path | str | None = None,
    proof_ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    """Return a bounded proxy for delayed multi-agent synergy.

    This is not full PID/TDMI estimation. It is an operational proxy that
    rewards repeated delayed proof chains between objectives and agents.
    """
    claims = _read_rows(_claim_path(claim_ledger_path), limit=MAX_RECENT)
    proofs = _read_rows(_proof_path(proof_ledger_path), limit=MAX_RECENT)
    claim_by_id = {_text(row.get("claim_id"), 120): row for row in claims if row.get("claim_id")}
    pair_counts: dict[str, dict[str, Any]] = {}
    objective_counts: dict[str, int] = {}
    last_by_agent: dict[str, dict[str, Any]] = {}
    for proof in proofs:
        claim = claim_by_id.get(_text(proof.get("claim_id"), 120), {})
        agent = _text(proof.get("agent_id") or proof.get("worker_agent_id") or claim.get("agent_id"), 120)
        objective = _clean_id(proof.get("objective") or claim.get("objective"), "unknown")
        if not objective:
            continue
        objective_counts[objective] = objective_counts.get(objective, 0) + 1
        prev = last_by_agent.get(agent)
        if prev and _clean_id(prev.get("objective")) != objective:
            left = _clean_id(prev.get("objective"))
            right = objective
            key = f"{left}->{right}"
            row = pair_counts.setdefault(
                key,
                {
                    "objective_pair": [left, right],
                    "delayed_pair_count": 0,
                    "agents": set(),
                    "settled_eur": 0.0,
                },
            )
            row["delayed_pair_count"] += 1
            row["agents"].add(agent)
            row["settled_eur"] += _num(proof.get("settled_price_eur"), 0.0)
        last_by_agent[agent] = proof

    pairs: list[dict[str, Any]] = []
    for row in pair_counts.values():
        delayed = _int(row.get("delayed_pair_count"))
        agents = len(row.get("agents") or [])
        settled = _num(row.get("settled_eur"), 0.0)
        proxy = _clamp(0.34 * min(1.0, delayed / 4.0) + 0.33 * min(1.0, agents / 3.0) + 0.33 * min(1.0, settled / 0.25))
        pairs.append(
            {
                "objective_pair": row.get("objective_pair"),
                "delayed_pair_count": delayed,
                "agent_count": agents,
                "settled_eur": round(settled, 4),
                "tdmi_lite_proxy": round(proxy, 6),
            }
        )
    pairs.sort(key=lambda item: (_num(item.get("tdmi_lite_proxy")), _int(item.get("delayed_pair_count"))), reverse=True)
    return {
        "ok": True,
        "schema": "nomad.synergy_lite.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "claim_count": len(claims),
        "proof_count": len(proofs),
        "objective_counts": objective_counts,
        "top_pairs": pairs[:12],
        "method": "delayed_objective_pair_proxy_not_full_pid_tdmi",
        "links": {
            "agent_work": _u(base_url, "/swarm/agent-work"),
            "compute_market": _u(base_url, "/swarm/compute-market"),
        },
        "machine_instruction": "prefer_work_that_increases_delayed_cross_objective_proof_gain",
        "science_basis": [
            {"id": "time_delayed_mutual_information_proxy", "source": "arxiv:2510.05174"},
            {"id": "dynamic_multi_agent_topology", "source": "arxiv:2504.00587"},
        ],
    }


def build_agent_work_surface(
    *,
    base_url: str,
    compute_market: dict[str, Any] | None = None,
    microtask_templates: dict[str, Any] | None = None,
    microtask_metrics: dict[str, Any] | None = None,
    worker_catalog: dict[str, Any] | None = None,
    skill_library: dict[str, Any] | None = None,
    worker_fleet: dict[str, Any] | None = None,
    synergy_lite: dict[str, Any] | None = None,
) -> dict[str, Any]:
    market = _dict(compute_market)
    templates_doc = _dict(microtask_templates)
    metrics = _dict(microtask_metrics)
    catalog = _dict(worker_catalog)
    skills = _dict(skill_library)
    fleet = _dict(worker_fleet)
    synergy = _dict(synergy_lite)
    lanes = _items(catalog.get("microtask_lanes"))
    if not lanes:
        lanes = [{"lane_id": "endpoint_health_proof", "price_eur": 0.02, "target_runtime_seconds": 45}]
    lanes_by_id = {_clean_id(lane.get("lane_id")): lane for lane in lanes}
    lane_stats = _lane_metrics(metrics)
    skill_counts = _skill_objectives(skills)
    templates = _items(templates_doc.get("templates"))
    if not templates:
        templates = [{"template_id": "endpoint_health_proof.basic", "lane_id": "endpoint_health_proof", "price_eur": 0.02, "objective": "protocol_drift_scan"}]
    items: list[dict[str, Any]] = []
    for template in templates:
        lane_id = _clean_id(template.get("lane_id"), "endpoint_health_proof")
        lane = lanes_by_id.get(lane_id) or {"lane_id": lane_id, "price_eur": template.get("price_eur"), "target_runtime_seconds": 60}
        items.append(
            _work_item(
                base_url=base_url,
                lane=lane,
                template=template,
                metric=lane_stats.get(lane_id, {}),
                worker_fleet=fleet,
                skill_counts=skill_counts,
                compute_market=market,
            )
        )
    synergy_pairs = _items(synergy.get("top_pairs"))
    synergy_objectives = {
        objective
        for pair in synergy_pairs[:4]
        for objective in (pair.get("objective_pair") if isinstance(pair.get("objective_pair"), list) else [])
        if _clean_id(objective)
    }
    for item in items:
        if _clean_id(item.get("objective")) in synergy_objectives:
            item["priority_score"] = round(_num(item.get("priority_score")) * 1.12, 6)
            item.setdefault("score_components", {})["synergy_lite_boost"] = 1.12
    items.sort(key=lambda item: _num(item.get("priority_score")), reverse=True)
    selected = items[:MAX_WORK_ITEMS]
    digest_core = {
        "market": market.get("market_digest"),
        "templates": templates_doc.get("template_count"),
        "metrics": _dict(metrics.get("totals")),
        "top": selected[0].get("work_id") if selected else "",
    }
    return {
        "ok": True,
        "schema": "nomad.agent_work.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "work_digest": f"nomad-agent-work-{_digest(digest_core)}",
        "work_count": len(selected),
        "work_items": selected,
        "claim_contract": {
            "url": _u(base_url, "/swarm/microtask/claim"),
            "required": ["agent_id"],
            "optional": ["work_id", "lane_id", "capabilities", "idempotency_key"],
            "idempotency_key_hint": "sha256(agent_id|work_id|availability_window)",
        },
        "proof_contract": {
            "url": _u(base_url, "/swarm/microtask/proof"),
            "required": ["agent_id", "claim_id", "proof_digest", "verifier_trace_digest", "test_digest"],
            "settles_to": _u(base_url, "/swarm/microtask/settle"),
            "promotes_to": _u(base_url, "/swarm/experience"),
        },
        "market_state": {
            "top_worker": _dict(market.get("top_worker")).get("agent_id"),
            "top_lane": _dict(market.get("top_lane")).get("lane_id"),
            "settled_24h_eur": _num(_dict(metrics.get("totals")).get("settled_eur")),
            "skill_count": _int(skills.get("skill_count")),
            "synergy_pair_count": len(synergy_pairs),
        },
        "links": {
            "self": _u(base_url, "/swarm/agent-work"),
            "well_known": _u(base_url, "/.well-known/nomad-agent-work.json"),
            "compute_market": _u(base_url, "/swarm/compute-market"),
            "claim": _u(base_url, "/swarm/microtask/claim"),
            "proof": _u(base_url, "/swarm/microtask/proof"),
            "settle": _u(base_url, "/swarm/microtask/settle"),
            "skill_library": _u(base_url, "/swarm/skill-library"),
            "synergy_lite": _u(base_url, "/swarm/synergy-lite"),
        },
        "machine_instruction": "read_work_claim_one_item_return_digest_proof_receive_settlement_and_skill_reuse",
        "science_basis": [
            {"id": "structured_environment_over_chatbot_group", "source": "arxiv:2505.21298"},
            {"id": "dynamic_topology_routing", "source": "arxiv:2504.00587"},
            {"id": "proof_market_m2m_settlement", "source": "arxiv:2602.14219"},
        ],
    }


def _select_work_item(surface: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    items = _items(surface.get("work_items"))
    requested = _clean_id(payload.get("work_id"))
    if requested:
        for item in items:
            if _clean_id(item.get("work_id")) == requested:
                return item
    lane = _clean_id(payload.get("lane_id"))
    if lane:
        for item in items:
            if _clean_id(item.get("lane_id")) == lane:
                return item
    return items[0] if items else {}


def claim_agent_work(
    payload: dict[str, Any],
    *,
    base_url: str,
    agent_work: dict[str, Any],
    claim_ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    now = _iso_now()
    agent_id = _text(body.get("agent_id") or body.get("worker_agent_id"), 120)
    item = _select_work_item(agent_work, body)
    if not agent_id or not item:
        return {
            "ok": False,
            "schema": "nomad.agent_work_claim_receipt.v1",
            "accepted": False,
            "reason": "missing_agent_or_work",
            "generated_at": now,
        }
    idem = _text(body.get("idempotency_key"), 160)
    claim_core = {
        "agent": agent_id,
        "work": item.get("work_id"),
        "lane": item.get("lane_id"),
        "idem": idem or body.get("availability_window") or "",
    }
    claim_id = f"nomad-claim-{_digest(claim_core)}"
    row = {
        "ok": True,
        "schema": "nomad.agent_work_claim_receipt.v1",
        "accepted": True,
        "generated_at": now,
        "claim_id": claim_id,
        "agent_id": agent_id,
        "work_id": _text(item.get("work_id"), 120),
        "lane_id": _clean_id(item.get("lane_id"), "endpoint_health_proof"),
        "objective": _clean_id(item.get("objective"), "protocol_drift_scan"),
        "capability": _clean_id(item.get("capability"), _clean_id(item.get("objective"), "protocol_drift_scan")),
        "quoted_price_eur": round(_num(item.get("quoted_price_eur")), 4),
        "required_proof": item.get("required_proof") if isinstance(item.get("required_proof"), list) else ["proof_digest", "verifier_trace_digest", "test_digest"],
        "proof_payload_hint": {
            "agent_id": agent_id,
            "claim_id": claim_id,
            "proof_digest": "sha256(canonical_result)",
            "verifier_trace_digest": "sha256(verifier_trace)",
            "test_digest": "sha256(test_or_probe_result)",
        },
        "links": {
            "proof": _u(base_url, "/swarm/microtask/proof"),
            "settle": _u(base_url, "/swarm/microtask/settle"),
            "agent_work": _u(base_url, "/swarm/agent-work"),
        },
        "machine_instruction": "execute_claimed_work_return_proof_digests_before_claim_ttl_expires",
    }
    if persist:
        _append(_claim_path(claim_ledger_path), row)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def submit_agent_work_proof(
    payload: dict[str, Any],
    *,
    base_url: str,
    agent_work: dict[str, Any] | None = None,
    claim_ledger_path: Path | str | None = None,
    proof_ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    now = _iso_now()
    agent_id = _text(body.get("agent_id") or body.get("worker_agent_id"), 120)
    claim_id = _text(body.get("claim_id"), 120)
    claims = _read_rows(_claim_path(claim_ledger_path), limit=MAX_RECENT)
    claim = next((row for row in reversed(claims) if _text(row.get("claim_id"), 120) == claim_id), {})
    if not claim and agent_work:
        selected = _select_work_item(_dict(agent_work), body)
        if selected:
            claim = {
                "claim_id": claim_id,
                "work_id": selected.get("work_id"),
                "lane_id": selected.get("lane_id"),
                "objective": selected.get("objective"),
                "capability": selected.get("capability"),
                "quoted_price_eur": selected.get("quoted_price_eur"),
            }
    proof = _text(body.get("proof_digest"), 140)
    trace = _text(body.get("verifier_trace_digest"), 140)
    test_digest = _text(body.get("test_digest"), 140)
    accepted = bool(agent_id and claim_id and proof and trace and test_digest and claim)
    objective = _clean_id(body.get("objective") or claim.get("objective"), "protocol_drift_scan")
    price = max(0.0, _num(body.get("settled_price_eur"), _num(claim.get("quoted_price_eur"), 0.0)))
    proof_core = {"agent": agent_id, "claim": claim_id, "proof": proof, "trace": trace, "test": test_digest}
    proof_id = f"nomad-proof-{_digest(proof_core)}"
    row = {
        "ok": True,
        "schema": "nomad.agent_work_proof_receipt.v1",
        "accepted": accepted,
        "generated_at": now,
        "proof_id": proof_id,
        "claim_id": claim_id,
        "work_id": _text(claim.get("work_id"), 120),
        "agent_id": agent_id,
        "lane_id": _clean_id(claim.get("lane_id"), "endpoint_health_proof"),
        "objective": objective,
        "capability": _clean_id(body.get("capability") or claim.get("capability") or objective, objective),
        "settled_price_eur": round(price, 4),
        "proof_digest": proof,
        "verifier_trace_digest": trace,
        "test_digest": test_digest,
        "reason": "proof_ready_for_settlement" if accepted else "missing_claim_or_required_proof",
        "settle_payload": {
            "task_id": claim_id or proof_id,
            "worker_agent_id": agent_id,
            "objective": objective,
            "capability": _clean_id(body.get("capability") or claim.get("capability") or objective, objective),
            "settled_price_eur": round(price, 4),
            "proof_digest": proof,
            "verifier_trace_digest": trace,
            "test_digest": test_digest,
            "settlement_ref": proof_id,
            "utility_delta": max(0.0, _num(body.get("utility_delta"), 1.0)),
            "reuse_count": max(0, _int(body.get("reuse_count"), 1 if accepted else 0)),
            "risk_score": _clamp(_num(body.get("risk_score"), 0.02)),
        },
        "links": {
            "settle": _u(base_url, "/swarm/microtask/settle"),
            "experience": _u(base_url, "/swarm/experience"),
            "synergy_lite": _u(base_url, "/swarm/synergy-lite"),
        },
        "machine_instruction": "settle_payload_then_promote_experience_if_settlement_accepts",
    }
    if persist:
        _append(_proof_path(proof_ledger_path), row)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row
