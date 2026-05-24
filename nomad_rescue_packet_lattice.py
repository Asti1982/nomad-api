"""Proof-gated Rescue-Packet candidate lattice for Nomad.

The lattice is the operational bridge between scheduled scouting and real
external value. It treats candidate rescue packets as a population: each one is
scored for proof-yield, autopoietic pressure, receipt proximity, boundedness,
and spam risk, then promoted, frozen, or pruned. It never posts outreach and
never books revenue.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nomad_state_paths import state_file


SCHEMA = "nomad.rescue_packet_lattice.v1"
EVENT_SCHEMA = "nomad.rescue_packet_candidate_receipt.v1"
ERROR_SCHEMA = "nomad.rescue_packet_lattice_error.v1"
LEDGER_ENV = "NOMAD_RESCUE_PACKET_LATTICE_LEDGER_PATH"
DEFAULT_LEDGER = Path("nomad_rescue_packet_lattice.jsonl")
MAX_LEDGER_LINES = 12000
MAX_RECENT = 80

FRAMEWORK_PRIORS = {
    "crewai": 0.95,
    "autogen": 0.9,
    "llamaindex": 0.86,
    "llama_index": 0.86,
    "langgraph": 0.84,
    "mcp": 0.82,
    "modelcontextprotocol": 0.82,
    "openai_agents": 0.78,
    "openai-agents-python": 0.78,
}

RECEIPT_TERMS = (
    "payment",
    "payments",
    "invoice",
    "email",
    "trade",
    "trading",
    "wallet",
    "settlement",
    "deploy",
    "deployment",
    "ci",
    "retry",
    "tool",
    "side-effect",
    "side_effect",
    "idempot",
    "duplicate",
)

PROOF_TERMS = (
    "repro",
    "failing test",
    "test",
    "trace",
    "verifier",
    "digest",
    "minimal",
    "deterministic",
)

FORBIDDEN_KEY_TERMS = (
    "private_key",
    "seed_phrase",
    "password",
    "credential",
    "api_key",
    "access_token",
    "authorization",
    "client_secret",
    "secret",
    "token",
)

FORBIDDEN_VALUE_TERMS = (
    "private key",
    "seed phrase",
    "password:",
    "credential:",
    "bearer ",
    "secret=",
    "sk-",
    "ghp_",
)

SAFE_SCOPE_TERMS = ("read_only", "shadow", "draft", "no_execution", "local_only", "bounded", "descriptor")


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _text(value: Any, limit: int = 600) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())[:limit]


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:/#-]+", "_", text)
    return text[:180].strip("_.:/#-") or fallback


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _digest(value: Any, length: int = 32) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _proof_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return f"sha256:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


def _ledger_path(path: Path | str | None = None) -> Path:
    return Path(path) if path else state_file(DEFAULT_LEDGER, env_name=LEDGER_ENV)


def _contains_forbidden(payload: Any) -> bool:
    def walk(value: Any, *, key: str = "") -> bool:
        k = str(key or "").strip().lower()
        if k and any(term in k for term in FORBIDDEN_KEY_TERMS):
            return True
        if isinstance(value, dict):
            return any(walk(item, key=str(name)) for name, item in value.items())
        if isinstance(value, list):
            return any(walk(item) for item in value)
        text = str(value or "").strip().lower()
        return any(term in text for term in FORBIDDEN_VALUE_TERMS)

    return walk(payload)


def _read_events(path: Path | str | None = None, *, limit_lines: int = MAX_LEDGER_LINES) -> list[dict[str, Any]]:
    p = _ledger_path(path)
    if not p.exists():
        return []
    tail: deque[str] = deque(maxlen=max(1, int(limit_lines)))
    try:
        with p.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                tail.append(line)
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in tail:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("schema") == EVENT_SCHEMA:
            rows.append(row)
    return rows


def _append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def _field_text(body: dict[str, Any]) -> str:
    fields = [
        body.get("source_url"),
        body.get("framework"),
        body.get("problem_type"),
        body.get("diagnosis"),
        body.get("repro_outline"),
        body.get("failing_test_outline"),
        body.get("fix_scope"),
        body.get("maintainer_signal"),
    ]
    return " ".join(_text(field, 400) for field in fields).lower()


def _framework_prior(framework: str, text: str) -> float:
    key = _clean_id(framework).replace("-", "_")
    if key in FRAMEWORK_PRIORS:
        return FRAMEWORK_PRIORS[key]
    for candidate, prior in FRAMEWORK_PRIORS.items():
        if candidate.replace("_", "-") in text or candidate in text:
            return prior
    return 0.52


def _digest_present(body: dict[str, Any]) -> bool:
    for name in ("proof_digest", "verifier_trace_digest", "test_digest", "receipt_digest"):
        text = _text(body.get(name), 260).lower()
        if text.startswith(("sha256:", "sha512:", "b3:", "nomad-")) and len(text) >= 16:
            return True
    return False


def _heuristic_score(text: str, terms: tuple[str, ...], *, default: float = 0.2) -> float:
    hits = sum(1 for term in terms if term in text)
    if hits <= 0:
        return default
    return _clamp(0.32 + 0.14 * hits)


def _boundedness_score(body: dict[str, Any], text: str) -> float:
    explicit = body.get("boundedness_score")
    if explicit is not None:
        return round(_clamp(_num(explicit)), 4)
    scope = _clean_id(body.get("side_effect_scope") or body.get("scope"))
    scope_score = 0.84 if any(term in scope for term in SAFE_SCOPE_TERMS) else 0.36
    ttl = _num(body.get("ttl_seconds"), 0.0)
    ttl_score = 0.75 if 1 <= ttl <= 86400 else 0.45
    fix = 0.76 if _text(body.get("fix_scope"), 40) else 0.22
    if "bounded" in text or "minimal" in text:
        fix = max(fix, 0.72)
    return round(_clamp(0.42 * scope_score + 0.2 * ttl_score + 0.38 * fix), 4)


def _spam_risk(body: dict[str, Any], text: str) -> float:
    explicit = body.get("spam_risk")
    if explicit is not None:
        return round(_clamp(_num(explicit)), 4)
    risk = 0.34
    if _text(body.get("source_url"), 30).startswith(("https://github.com/", "http://github.com/")):
        risk -= 0.08
    if _text(body.get("public_followup_text"), 40):
        risk += 0.16
    if "buy now" in text or "guaranteed" in text:
        risk += 0.25
    if body.get("human_go"):
        risk -= 0.08
    return round(_clamp(risk), 4)


def score_rescue_packet_candidate(payload: dict[str, Any]) -> dict[str, Any]:
    """Score a candidate without persisting it."""

    body = payload if isinstance(payload, dict) else {}
    text = _field_text(body)
    source_url = _text(body.get("source_url") or body.get("problem_url") or body.get("url"), 500)
    framework = _clean_id(body.get("framework"), fallback="unknown")
    proof_present = _digest_present(body)
    proof_signal = 0.95 if proof_present else _heuristic_score(text, PROOF_TERMS, default=0.18)
    repro_signal = _clamp(_num(body.get("reproducibility"), _heuristic_score(text, PROOF_TERMS, default=0.2)))
    receipt_proximity = _clamp(_num(body.get("receipt_proximity"), _heuristic_score(text, RECEIPT_TERMS, default=0.18)))
    maintainer_relevance = _clamp(_num(body.get("maintainer_relevance"), 0.62 if "github.com" in source_url else 0.35))
    boundedness = _boundedness_score(body, text)
    spam = _spam_risk(body, text)
    framework_prior = _framework_prior(framework, text)
    price = _num(body.get("price_tier_usd") or body.get("price_usd"), 0.0)
    price_fit = 0.72 if price in {49.0, 99.0, 250.0} else 0.38 if price > 0 else 0.24
    proof_yield_delta = _num(
        body.get("proof_yield_delta"),
        0.34 * repro_signal + 0.24 * proof_signal + 0.18 * boundedness + 0.16 * maintainer_relevance + 0.08 * framework_prior - 0.18 * spam,
    )
    autopoietic_index_delta = _num(
        body.get("autopoietic_index_delta"),
        0.28 * receipt_proximity + 0.24 * boundedness + 0.18 * proof_signal + 0.16 * price_fit + 0.14 * framework_prior - 0.16 * spam,
    )
    selection_score = _clamp(
        0.3 * proof_yield_delta
        + 0.25 * autopoietic_index_delta
        + 0.2 * receipt_proximity
        + 0.15 * maintainer_relevance
        + 0.1 * framework_prior
    )
    if not source_url:
        decision = "freeze"
        reason = "missing_public_source_url"
    elif boundedness < 0.32 or spam > 0.76:
        decision = "prune"
        reason = "unsafe_or_spam_risk"
    elif proof_yield_delta > 0.38 and autopoietic_index_delta > 0.34 and receipt_proximity >= 0.35 and boundedness >= 0.52 and spam <= 0.48:
        decision = "promote"
        reason = "positive_proof_yield_and_autopoietic_delta"
    else:
        decision = "freeze"
        reason = "needs_stronger_repro_proof_or_receipt_proximity"
    return {
        "framework": framework,
        "source_url": source_url,
        "proof_signal": round(proof_signal, 4),
        "reproducibility": round(repro_signal, 4),
        "receipt_proximity": round(receipt_proximity, 4),
        "maintainer_relevance": round(maintainer_relevance, 4),
        "boundedness_score": round(boundedness, 4),
        "spam_risk": round(spam, 4),
        "framework_prior": round(framework_prior, 4),
        "price_fit": round(price_fit, 4),
        "proof_yield_delta": round(proof_yield_delta, 4),
        "autopoietic_index_delta": round(autopoietic_index_delta, 4),
        "selection_score": round(selection_score, 4),
        "decision": decision,
        "decision_reason": reason,
    }


def append_rescue_packet_candidate(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    persist: bool = True,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    """Evaluate and optionally persist one Rescue-Packet candidate."""

    body = payload if isinstance(payload, dict) else {}
    if _contains_forbidden(body):
        return {
            "ok": False,
            "schema": ERROR_SCHEMA,
            "error": "secret_shaped_payload",
            "message": "Rescue-Packet candidates must contain public URLs, digests, and bounded descriptions only.",
            "generated_at": _iso_now(),
        }
    score = score_rescue_packet_candidate(body)
    candidate_core = {
        "source_url": score["source_url"],
        "framework": score["framework"],
        "problem_type": _clean_id(body.get("problem_type"), fallback="agent_reliability"),
        "diagnosis": _text(body.get("diagnosis"), 420),
        "repro_outline": _text(body.get("repro_outline") or body.get("failing_test_outline"), 420),
        "fix_scope": _text(body.get("fix_scope"), 420),
        "price_tier_usd": int(_num(body.get("price_tier_usd") or body.get("price_usd"), 0.0)),
        "proof_digest": _text(body.get("proof_digest") or body.get("verifier_trace_digest") or "", 220),
    }
    candidate_id = _clean_id(body.get("candidate_id"), fallback=f"rescue-{_digest(candidate_core, 20)}")
    row = {
        "ok": True,
        "schema": EVENT_SCHEMA,
        "generated_at": _iso_now(),
        "event_id": f"nomad-rescue-candidate-{_digest({**candidate_core, 'candidate_id': candidate_id}, 24)}",
        "candidate_id": candidate_id,
        **candidate_core,
        "scores": score,
        "decision": score["decision"],
        "decision_reason": score["decision_reason"],
        "promotion_allowed": score["decision"] == "promote",
        "public_followup_allowed": bool(body.get("human_go")) and score["decision"] == "promote",
        "required_human_go": f"APPROVE_PUBLIC_SEND {candidate_id}" if score["decision"] == "promote" else "",
        "candidate_proof_digest": _proof_digest({**candidate_core, "scores": score}),
        "counts_as_revenue": False,
        "revenue_recognized_usd": 0.0,
        "accounting_boundary": "candidate_signal_only_paid_or_return_compute_receipt_required",
        "side_effect_scope": "ledger_only_no_public_post_no_outreach_no_spend",
        "next": {
            "lattice": _u(base_url, "/.well-known/nomad-rescue-packet-lattice.json"),
            "scheduler": _u(base_url, "/.well-known/nomad-rescue-cycle-scheduler.json"),
            "campaign": _u(base_url, "/.well-known/nomad-first-receipt-campaign.json"),
        },
    }
    if persist:
        _append(_ledger_path(ledger_path), row)
        row["ledger_path"] = str(_ledger_path(ledger_path))
    return row


def summarize_rescue_packet_candidates(*, ledger_path: Path | str | None = None, limit: int = MAX_RECENT) -> dict[str, Any]:
    rows = _read_events(ledger_path)[-max(1, int(limit)) :]
    by_decision: dict[str, int] = {"promote": 0, "freeze": 0, "prune": 0}
    for row in rows:
        decision = str(row.get("decision") or "freeze")
        by_decision[decision] = by_decision.get(decision, 0) + 1
    ranked = sorted(
        rows,
        key=lambda row: (
            _num((row.get("scores") if isinstance(row.get("scores"), dict) else {}).get("selection_score")),
            _num((row.get("scores") if isinstance(row.get("scores"), dict) else {}).get("receipt_proximity")),
            str(row.get("generated_at") or ""),
        ),
        reverse=True,
    )
    promoted = [row for row in ranked if row.get("decision") == "promote"]
    return {
        "schema": "nomad.rescue_packet_lattice_summary.v1",
        "generated_at": _iso_now(),
        "ledger_event_count": len(rows),
        "decision_counts": by_decision,
        "promotion_candidate_count": len(promoted),
        "top_candidate": ranked[0] if ranked else {},
        "latest": rows[-8:],
        "ranked_candidates": ranked[:12],
        "receipt_truth": {
            "candidate_events_count_as_revenue": False,
            "revenue_requires": "paid_or_verified_return_compute_receipt",
        },
    }


def build_rescue_packet_lattice_surface(
    *,
    base_url: str = "",
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the public machine contract for the candidate lattice."""

    root = (base_url or "").strip().rstrip("/")
    ledger_summary = summary if isinstance(summary, dict) else summarize_rescue_packet_candidates()
    contract_core = {
        "schema": SCHEMA,
        "score_axes": [
            "proof_yield_delta",
            "autopoietic_index_delta",
            "receipt_proximity",
            "boundedness_score",
            "spam_risk",
        ],
        "promotion_rule": "positive_proof_yield_and_autopoietic_delta_with_bounded_scope_and_low_spam_risk",
    }
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": root,
        "surface_digest": "nomad-rescue-packet-lattice-" + _digest(contract_core, 28),
        "read_url": _u(root, "/swarm/rescue-packet-lattice"),
        "well_known_url": _u(root, "/.well-known/nomad-rescue-packet-lattice.json"),
        "post_candidate_url": _u(root, "/swarm/rescue-packet-candidates"),
        "purpose": "turn_agent_framework_negative_space_into_a_proof_gated_population_of_sellable_bounded_rescue_packets",
        "population_dynamics": {
            "unit": "rescue_packet_candidate",
            "reproduction_signal": "promotion_allowed_candidates_receive_followup_pressure_after_human_go",
            "extinction_signal": "unsafe_low_proof_or_spam_risk_candidates_are_pruned",
            "dormancy_signal": "uncertain_candidates_are_frozen_until_more_repro_or_receipt_evidence",
        },
        "scientific_operators": [
            "replicator_selection_over_candidate_population",
            "contextual_bandit_receipt_proximity",
            "proof_gated_shadow_lane_evaluation",
            "anti_consensus_preservation_for_high_proof_minority_candidates",
            "extinction_pressure_for_low_yield_or_high_spam_candidates",
        ],
        "score_axes": {
            "proof_yield_delta": "does_the_candidate_make_a_replayable_failure_or_verifier_trace_more_likely",
            "autopoietic_index_delta": "does_the_candidate_improve_the_loop_from_gap_to_packet_to_receipt_to_more_compute",
            "receipt_proximity": "is_the_failure_close_to_paid_repair_return_compute_or_buyer_pain",
            "boundedness_score": "can_the_packet_be_delivered_without_unbounded_side_effects",
            "spam_risk": "would_public_followup_damage_maintainer_trust_or_channel_health",
        },
        "promotion_thresholds": {
            "proof_yield_delta_gt": 0.38,
            "autopoietic_index_delta_gt": 0.34,
            "receipt_proximity_gte": 0.35,
            "boundedness_score_gte": 0.52,
            "spam_risk_lte": 0.48,
        },
        "accepted_framework_priors": FRAMEWORK_PRIORS,
        "required_candidate_fields": [
            "source_url",
            "framework",
            "problem_type",
            "diagnosis",
            "repro_outline_or_failing_test_outline",
            "fix_scope",
            "price_tier_usd",
        ],
        "hard_guards": [
            "no_secrets",
            "no_public_post_without_human_go",
            "no_private_outreach",
            "no_spend",
            "no_code_execution_from_candidate_payload",
            "no_revenue_count_without_paid_or_verified_return_compute_receipt",
        ],
        "ledger_summary": ledger_summary,
        "machine_instruction": (
            "post_secret_free_candidate_after_shadow_tick; promote_only_if_scores_cross_threshold; "
            "ask_human_for_required_human_go_before_any_public_followup; keep_counts_as_revenue_false"
        ),
    }
