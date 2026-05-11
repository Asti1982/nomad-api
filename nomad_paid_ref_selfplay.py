"""Synthetic buyer-agent selfplay for Nomad paid-ref conversion.

This layer plays many small counterparty agents against the live paid-ref
surface. It does not mint revenue. It finds the packet/cohort/quote payloads
most likely to produce a real paid_ref once an external agent can pay.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from datetime import UTC, datetime
from typing import Any


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


def _digest(value: Any, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _rng_seed(seed: str | int | None, *parts: Any) -> int:
    if seed is not None:
        try:
            return int(seed)
        except (TypeError, ValueError):
            pass
    return int(hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12], 16)


ARCHETYPES = {
    "blocked_runtime_buyer": {
        "share": 0.34,
        "budget_mean": 8.0,
        "urgency": 0.82,
        "verifier": 0.58,
        "distribution": 0.18,
        "packet_bias": {"agent_blocker_unblock_pack": 1.42, "mcp_contract_diff_pack": 1.08},
    },
    "endpoint_owner_agent": {
        "share": 0.18,
        "budget_mean": 2.3,
        "urgency": 0.64,
        "verifier": 0.74,
        "distribution": 0.22,
        "packet_bias": {"endpoint_health_batch": 1.58, "mcp_contract_diff_pack": 1.12},
    },
    "mcp_tool_provider": {
        "share": 0.16,
        "budget_mean": 6.5,
        "urgency": 0.67,
        "verifier": 0.8,
        "distribution": 0.3,
        "packet_bias": {"mcp_contract_diff_pack": 1.68, "endpoint_health_batch": 1.1},
    },
    "uptime_sponsor_runtime": {
        "share": 0.11,
        "budget_mean": 2.0,
        "urgency": 0.52,
        "verifier": 0.62,
        "distribution": 0.36,
        "packet_bias": {"carry_sponsor_state_relay": 1.7, "reseller_referral_probe": 1.08},
    },
    "reseller_or_router_agent": {
        "share": 0.21,
        "budget_mean": 1.0,
        "urgency": 0.48,
        "verifier": 0.56,
        "distribution": 0.78,
        "packet_bias": {"reseller_referral_probe": 1.82, "agent_blocker_unblock_pack": 1.12},
    },
}


def _archetype_names() -> list[str]:
    return list(ARCHETYPES)


def _pick_archetype(rng: random.Random) -> str:
    roll = rng.random()
    acc = 0.0
    for name, spec in ARCHETYPES.items():
        acc += _num(spec.get("share"))
        if roll <= acc:
            return name
    return _archetype_names()[-1]


def _agent(index: int, rng: random.Random) -> dict[str, Any]:
    archetype = _pick_archetype(rng)
    spec = ARCHETYPES[archetype]
    budget_mean = _num(spec.get("budget_mean"), 1.0)
    budget = max(0.0, rng.lognormvariate(math.log(max(0.1, budget_mean)), 0.58) - rng.random() * 0.35)
    return {
        "agent_id": f"selfplay.agent.{index:04d}.{_digest({'i': index, 'a': archetype}, 10)}",
        "archetype": archetype,
        "budget_eur": round(budget, 4),
        "urgency": _clamp(rng.gauss(_num(spec.get("urgency"), 0.5), 0.13)),
        "verifier_capability": _clamp(rng.gauss(_num(spec.get("verifier"), 0.5), 0.12)),
        "distribution_power": _clamp(rng.gauss(_num(spec.get("distribution"), 0.3), 0.18)),
    }


def _packet_score(agent: dict[str, Any], packet: dict[str, Any], rng: random.Random) -> float:
    quote = _num(packet.get("quote_eur"), 0.0)
    packet_id = _clean_id(packet.get("packet_id"))
    spec = ARCHETYPES.get(str(agent.get("archetype") or ""), {})
    bias = _num(_dict(spec.get("packet_bias")).get(packet_id), 0.88)
    budget = _num(agent.get("budget_eur"), 0.0)
    affordability = 1.0 if quote <= 0 else _clamp((budget + 0.2) / max(quote, 0.1), 0.0, 1.35)
    proof_fit = _num(agent.get("verifier_capability")) * (1.0 + 0.18 * len(packet.get("proof_required") or []))
    urgency = _num(agent.get("urgency"))
    distribution = _num(agent.get("distribution_power"))
    reseller_gain = distribution if packet_id == "reseller_referral_probe" else 0.15 * distribution
    noise = rng.uniform(0.92, 1.08)
    return max(0.0, (0.34 * affordability + 0.28 * proof_fit + 0.24 * urgency + 0.14 * reseller_gain) * bias * noise)


def _decide(agent: dict[str, Any], packets: list[dict[str, Any]], rng: random.Random) -> dict[str, Any]:
    scored = [(packet, _packet_score(agent, packet, rng)) for packet in packets]
    scored.sort(key=lambda item: item[1], reverse=True)
    packet, score = scored[0] if scored else ({}, 0.0)
    quote = _num(packet.get("quote_eur"), 0.0)
    packet_id = _clean_id(packet.get("packet_id"), "unknown")
    budget = _num(agent.get("budget_eur"), 0.0)
    quote_propensity = _clamp(score / 1.55)
    payment_propensity = _clamp(quote_propensity * (1.0 if quote <= 0 else budget / max(quote, 0.1)))
    verifier_propensity = _clamp(payment_propensity * _num(agent.get("verifier_capability")))
    will_quote = quote_propensity >= 0.58
    payment_ready = quote > 0 and payment_propensity >= 0.72
    verifier_ready = payment_ready and verifier_propensity >= 0.56
    return {
        "agent_id": agent["agent_id"],
        "archetype": agent["archetype"],
        "packet_id": packet_id,
        "score": round(score, 6),
        "quote_eur": round(quote, 4),
        "budget_eur": round(budget, 4),
        "quote_propensity": round(quote_propensity, 6),
        "payment_propensity": round(payment_propensity, 6),
        "verifier_propensity": round(verifier_propensity, 6),
        "will_quote": will_quote,
        "payment_ready": payment_ready,
        "verifier_ready": verifier_ready,
        "quote_payload": {
            "agent_id": agent["agent_id"],
            "packet_id": packet_id,
            "buyer_ref": f"{agent['archetype']}:{_digest(agent, 14)}",
            "problem": f"{agent['archetype']} requests {packet_id} with verifier_capability={round(_num(agent.get('verifier_capability')), 3)}",
            "proof_digest": f"selfplay-proof-{_digest({'agent': agent['agent_id'], 'packet': packet_id}, 16)}",
            "verifier_trace_digest": f"selfplay-trace-{_digest({'agent': agent['agent_id'], 'score': score}, 16)}",
            "test_digest": f"selfplay-test-{_digest({'packet': packet_id, 'budget': budget}, 16)}",
        },
    }


def run_paid_ref_selfplay(
    *,
    base_url: str,
    survival_market: dict[str, Any],
    paid_ref_market: dict[str, Any] | None = None,
    agent_count: int = 1000,
    seed: str | int | None = None,
) -> dict[str, Any]:
    count = max(1, min(_int(agent_count, 1000), 10000))
    packets = _items(_dict(survival_market).get("packets"))
    rng = random.Random(_rng_seed(seed, _dict(survival_market).get("market_digest"), _dict(paid_ref_market).get("market_digest"), count))
    agents = [_agent(index, rng) for index in range(count)]
    decisions = [_decide(agent, packets, rng) for agent in agents]
    quote_candidates = [row for row in decisions if row["will_quote"]]
    payment_candidates = [row for row in decisions if row["payment_ready"]]
    verifier_candidates = [row for row in decisions if row["verifier_ready"]]
    by_packet: dict[str, dict[str, Any]] = {}
    by_archetype: dict[str, dict[str, Any]] = {}
    for row in decisions:
        packet = by_packet.setdefault(
            row["packet_id"],
            {"packet_id": row["packet_id"], "agents": 0, "quote_ready": 0, "payment_ready": 0, "verifier_ready": 0, "score_sum": 0.0},
        )
        packet["agents"] += 1
        packet["quote_ready"] += 1 if row["will_quote"] else 0
        packet["payment_ready"] += 1 if row["payment_ready"] else 0
        packet["verifier_ready"] += 1 if row["verifier_ready"] else 0
        packet["score_sum"] += _num(row["score"])
        archetype = by_archetype.setdefault(
            row["archetype"],
            {"archetype": row["archetype"], "agents": 0, "quote_ready": 0, "payment_ready": 0, "verifier_ready": 0},
        )
        archetype["agents"] += 1
        archetype["quote_ready"] += 1 if row["will_quote"] else 0
        archetype["payment_ready"] += 1 if row["payment_ready"] else 0
        archetype["verifier_ready"] += 1 if row["verifier_ready"] else 0
    packet_rows = []
    for row in by_packet.values():
        agents_n = max(1, _int(row.get("agents")))
        packet_rows.append(
            {
                "packet_id": row["packet_id"],
                "agents": agents_n,
                "quote_ready": _int(row.get("quote_ready")),
                "payment_ready": _int(row.get("payment_ready")),
                "verifier_ready": _int(row.get("verifier_ready")),
                "mean_score": round(_num(row.get("score_sum")) / agents_n, 6),
                "verified_ref_pressure": round((_int(row.get("verifier_ready")) + 0.4 * _int(row.get("payment_ready"))) / count, 6),
            }
        )
    packet_rows.sort(key=lambda item: (item["verified_ref_pressure"], item["quote_ready"], item["mean_score"]), reverse=True)
    archetype_rows = list(by_archetype.values())
    archetype_rows.sort(key=lambda item: (item["verifier_ready"], item["payment_ready"], item["quote_ready"]), reverse=True)
    top_quotes = sorted(quote_candidates, key=lambda row: (row["verifier_propensity"], row["payment_propensity"], row["score"]), reverse=True)[:25]
    digest_core = {
        "count": count,
        "survival": _dict(survival_market).get("market_digest"),
        "top": packet_rows[:3],
        "quotes": [row["agent_id"] for row in top_quotes[:5]],
    }
    return {
        "ok": True,
        "schema": "nomad.paid_ref_selfplay.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "selfplay_digest": f"nomad-paid-ref-selfplay-{_digest(digest_core)}",
        "agent_count": count,
        "mechanism": "synthetic_contract_net_posted_price_selfplay_no_fake_revenue",
        "summary": {
            "quote_ready_agents": len(quote_candidates),
            "payment_ready_agents": len(payment_candidates),
            "verifier_ready_agents": len(verifier_candidates),
            "expected_verified_ref_rate": round(len(verifier_candidates) / count, 6),
        },
        "top_packet_pressures": packet_rows,
        "top_archetypes": archetype_rows,
        "top_quote_payloads": [row["quote_payload"] for row in top_quotes[:12]],
        "top_decisions": top_quotes[:12],
        "next": {
            "quote_url": _u(base_url, "/swarm/paid-ref/quote"),
            "verify_url": _u(base_url, "/swarm/paid-ref/verify"),
            "survival_intent_url": _u(base_url, "/swarm/survival-intent"),
            "paid_ref_market": _u(base_url, "/.well-known/nomad-paid-ref-market.json"),
        },
        "machine_instruction": "take_top_quote_payloads_send_to_real_agents_or_use_one_paid_agent_then_verify_payment_do_not_mint_revenue_from_selfplay",
        "science_basis": [
            {"id": "agent_market_simulation", "source": "arxiv:2602.06008"},
            {"id": "large_population_economic_sandbox", "source": "arxiv:2603.17694"},
            {"id": "dynamic_agent_topology", "source": "arxiv:2504.00587"},
            {"id": "structured_mas_environment", "source": "openreview:FfsxgSZW0c"},
        ],
    }
