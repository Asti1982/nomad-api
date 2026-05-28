"""Private MCP lab surface for falsifiable Nomad SVW experiments.

The Secure MCP Tunnel makes private tool access possible; this module makes it
measurable. Each tool output is shaped as an experiment contract so agents can
observe, replay, gate, and record interventions before Nomad exposes public
claims or performs higher-risk work.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nomad_state_paths import state_file
from nomad_swarm_verified_work import build_swarm_verified_work_surface


LEDGER_ENV = "NOMAD_LAB_EXPERIMENT_LEDGER_PATH"
DEFAULT_LEDGER = Path("nomad_lab_experiment_ledger.jsonl")

RISK_BUDGETS = {
    "observe_only": 0.04,
    "proposal_only": 0.08,
    "low": 0.16,
    "medium": 0.32,
    "high": 0.55,
}

INTERVENTION_PRIORS = {
    "mcp_production": {
        "impact": 0.18,
        "evidence": ["mcp_call_trace", "tool_schema_before_after", "agent_retry_delta"],
        "metric": "mcp_tool_success_rate",
    },
    "external_value": {
        "impact": 0.22,
        "evidence": ["ledger_entry", "receipt_or_public_work_url", "verifier_trace_digest"],
        "metric": "paid_or_approved_external_value_events",
    },
    "worker_fleet": {
        "impact": 0.16,
        "evidence": ["worker_lease_id", "completion_digest", "retry_loss_delta"],
        "metric": "verified_work_index",
    },
    "public_digest": {
        "impact": 0.08,
        "evidence": ["public_digest_url", "surface_digest", "inbound_agent_response"],
        "metric": "verified_inbound_reuse_events",
    },
    "agent_economy_research": {
        "impact": 0.06,
        "evidence": ["model_snapshot_digest", "source_manifest", "prediction_error_after_refresh"],
        "metric": "prediction_error_reduction",
    },
}


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _digest(value: Any, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _json_or_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _risk_name(value: Any) -> str:
    raw = str(value or "low").strip().lower().replace("-", "_")
    return raw if raw in RISK_BUDGETS else "low"


def _intervention_class(text: str) -> str:
    lower = text.lower()
    if any(term in lower for term in ("mcp", "tool", "schema", "tunnel", "transport", "retry")):
        return "mcp_production"
    if any(term in lower for term in ("paid", "payment", "receipt", "bounty", "external value", "revenue")):
        return "external_value"
    if any(term in lower for term in ("worker", "lease", "compute", "fleet", "queue", "gpu", "cpu")):
        return "worker_fleet"
    if any(term in lower for term in ("digest", "publish", "public", "well-known", "surface")):
        return "public_digest"
    return "agent_economy_research"


def _svw_state(svw_surface: dict[str, Any] | None = None) -> dict[str, Any]:
    surface = _dict(svw_surface) or build_swarm_verified_work_surface()
    state = _dict(surface.get("state_vector"))
    quote = _dict(surface.get("quote"))
    return {
        "schema": surface.get("schema", "nomad.swarm_verified_work.v1"),
        "surface_digest": surface.get("surface_digest"),
        "market_price_status": quote.get("market_price_status", "bootstrapped"),
        "svw_quote_eur": _num(quote.get("svw_quote_eur")),
        "verified_work_index": _num(state.get("verified_work_index")),
        "proof_density": _clamp(_num(state.get("proof_density"), 0.35), 0.02, 1.0),
        "retry_loss": _clamp(_num(state.get("retry_loss"), 0.65), 0.0, 0.95),
        "settlement_confidence": _clamp(_num(state.get("settlement_confidence"), 0.0), 0.0, 1.0),
        "observed_settled_24h_eur": _num(state.get("observed_settled_24h_eur")),
    }


def _expected_delta(*, class_id: str, risk_budget: str, svw_state: dict[str, Any]) -> float:
    prior = _dict(INTERVENTION_PRIORS.get(class_id))
    impact = _num(prior.get("impact"), 0.06)
    risk = RISK_BUDGETS[_risk_name(risk_budget)]
    proof_density = _clamp(_num(svw_state.get("proof_density"), 0.35), 0.02, 1.0)
    retry_gain = _clamp(1.0 - _num(svw_state.get("retry_loss"), 0.65), 0.05, 1.0)
    confidence = 0.45 + 0.35 * proof_density + 0.20 * retry_gain
    return round(impact * confidence * (1.0 - 0.55 * risk), 4)


def build_private_mcp_lab_surface(
    *,
    base_url: str = "",
    svw_surface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the private MCP scientific lab contract, safe to expose as a resource."""

    svw = _svw_state(svw_surface)
    profiles = {
        "nomad-lab-readonly": [
            "nomad_lab_state",
            "nomad_generate_experiment",
            "nomad_counterfactual_experiment_replay",
            "nomad_publish_digest_proposal",
            "nomad_crn_dispatch_state",
        ],
        "nomad-lab-execute": [
            "nomad_lab_execution_gate",
            "nomad_record_experiment_result",
        ],
    }
    return {
        "ok": True,
        "schema": "nomad.private_mcp_lab.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "stance": "private_mcp_as_scientific_instrument_not_feature_surface",
        "secure_mcp_tunnel_fit": {
            "private_server_stays_private": True,
            "connection_model": "outbound_https_to_openai_tunnel_client",
            "public_projection_policy": "publish_minimal_digest_only_after_local_evidence",
            "nomad_binding": "local_machine_is_canonical_ledger_render_is_projection_cache",
        },
        "profiles": profiles,
        "scientific_method": {
            "unit_of_account": "SVW",
            "loop": ["observe", "hypothesize", "replay", "gate", "probe", "verify", "record_negative_results"],
            "hard_rule": "no_undigested_action_without_success_and_failure_rules",
            "falsification_first": True,
        },
        "current_svw_state": svw,
        "approval_policy": {
            "default": "readonly_or_proposal_only",
            "mutating_tools_require": "caller_approval_plus_nomad_lab_execution_gate",
            "approval_token_shape": "approved:nomad-lab-execute:<hypothesis_id>",
        },
        "resources": {
            "svw": _u(base_url, "/.well-known/nomad-swarm-verified-work.json"),
            "external_value": _u(base_url, "/.well-known/nomad-external-value.json"),
            "agent_card": _u(base_url, "/.well-known/agent-card.json"),
        },
        "machine_instruction": "treat_each_mcp_call_as_an_experiment_or_measurement; record_failures_as_value",
    }


def generate_svw_experiment(
    *,
    objective: str,
    candidate_action: str = "",
    baseline_metric: str = "",
    risk_budget: str = "low",
    svw_surface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a falsifiable SVW experiment from a private MCP request."""

    obj = " ".join(str(objective or "").split())[:600] or "Increase verified work with a bounded probe."
    action = " ".join(str(candidate_action or "").split())[:800] or obj
    class_id = _intervention_class(f"{obj} {action}")
    risk_name = _risk_name(risk_budget)
    svw = _svw_state(svw_surface)
    prior = _dict(INTERVENTION_PRIORS.get(class_id))
    metric = str(baseline_metric or prior.get("metric") or "verified_work_index").strip()
    expected_delta = _expected_delta(class_id=class_id, risk_budget=risk_name, svw_state=svw)
    hypothesis_core = {
        "objective": obj,
        "candidate_action": action,
        "baseline_metric": metric,
        "risk_budget": risk_name,
        "intervention_class": class_id,
        "svw_digest": svw.get("surface_digest"),
    }
    hypothesis_id = f"hyp-{_digest(hypothesis_core, 18)}"
    required_delta = max(0.01, round(expected_delta * 0.6, 4))
    return {
        "ok": True,
        "schema": "nomad.svw_experiment.v1",
        "generated_at": _iso_now(),
        "hypothesis_id": hypothesis_id,
        "intervention_class": class_id,
        "objective": obj,
        "candidate_action": action,
        "falsifiable_hypothesis": (
            f"If Nomad performs the bounded intervention, {metric} should improve by at least "
            f"{required_delta} before the evidence window closes."
        ),
        "baseline": {
            "metric": metric,
            "svw_state": svw,
            "observation_status": svw.get("market_price_status", "bootstrapped"),
        },
        "intervention": {
            "scope": "proposal_only" if risk_name in {"observe_only", "proposal_only"} else "bounded_probe_after_gate",
            "risk_budget": risk_name,
            "risk_budget_score": RISK_BUDGETS[risk_name],
            "expected_svw_delta": expected_delta,
            "expected_direction": "increase",
        },
        "measurement_contract": {
            "baseline_metric": metric,
            "success_rule": f"{metric} delta >= {required_delta} with required evidence attached",
            "failure_rule": f"{metric} delta < {required_delta}, missing evidence, or higher retry loss",
            "negative_result_value": "route_weight_reduction_and_hypothesis_pruning",
            "evidence_required": prior.get("evidence", []),
            "timebox": "next_1_to_3_worker_cycles_or_72h_for_public_digest",
        },
        "approval": {
            "required_for_execution": risk_name not in {"observe_only", "proposal_only"},
            "required_approval_token": f"approved:nomad-lab-execute:{hypothesis_id}",
        },
        "machine_instruction": "replay_before_execution; record_result_even_if_negative",
    }


def replay_svw_experiment(
    *,
    experiment: dict[str, Any] | str | None = None,
    objective: str = "",
    candidate_action: str = "",
    risk_budget: str = "low",
    svw_surface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a counterfactual replay over an experiment without side effects."""

    exp = _json_or_dict(experiment)
    if not exp:
        exp = generate_svw_experiment(
            objective=objective,
            candidate_action=candidate_action,
            risk_budget=risk_budget,
            svw_surface=svw_surface,
        )
    svw = _svw_state(svw_surface or _dict(_dict(exp.get("baseline")).get("svw_state")))
    intervention = _dict(exp.get("intervention"))
    class_id = str(exp.get("intervention_class") or _intervention_class(str(exp))).strip()
    risk_name = _risk_name(intervention.get("risk_budget") or risk_budget)
    expected_delta = _num(intervention.get("expected_svw_delta"))
    if expected_delta <= 0:
        expected_delta = _expected_delta(class_id=class_id, risk_budget=risk_name, svw_state=svw)
    risk = RISK_BUDGETS[risk_name]
    uncertainty = round(_clamp(0.62 - 0.35 * _num(svw.get("settlement_confidence")) + 0.2 * risk), 4)
    lower = round(expected_delta * (1.0 - uncertainty), 4)
    upper = round(expected_delta * (1.0 + uncertainty), 4)
    if risk_name in {"observe_only", "proposal_only"}:
        decision = "proposal_only"
    elif expected_delta < 0.025:
        decision = "observe_more_before_probe"
    elif risk > 0.32:
        decision = "manual_approval_required"
    else:
        decision = "execute_low_risk_probe_after_gate"
    return {
        "ok": True,
        "schema": "nomad.svw_experiment_replay.v1",
        "generated_at": _iso_now(),
        "hypothesis_id": exp.get("hypothesis_id") or f"hyp-{_digest(exp, 18)}",
        "input_experiment_schema": exp.get("schema"),
        "counterfactual": {
            "do_nothing_delta": 0.0,
            "proposal_only_delta": round(expected_delta * 0.35, 4),
            "bounded_probe_delta_range": [lower, upper],
            "uncertainty": uncertainty,
        },
        "decision": decision,
        "risk_budget": {
            "name": risk_name,
            "score": risk,
            "max_without_manual_review": RISK_BUDGETS["low"],
        },
        "svw_state_used": svw,
        "failure_capture": {
            "record_negative_result": True,
            "reason": "failed_probe_reduces_future_route_weight_and_prevents_story_only_learning",
        },
        "machine_instruction": "if_decision_is_execute_low_risk_probe_after_gate_call_nomad_lab_execution_gate_first",
    }


def publish_digest_proposal(
    *,
    experiment: dict[str, Any] | str | None = None,
    objective: str = "",
    candidate_action: str = "",
    base_url: str = "",
) -> dict[str, Any]:
    """Return a minimal public digest proposal without publishing it."""

    exp = _json_or_dict(experiment)
    if not exp:
        exp = generate_svw_experiment(objective=objective, candidate_action=candidate_action)
    digest_core = {
        "hypothesis_id": exp.get("hypothesis_id"),
        "intervention_class": exp.get("intervention_class"),
        "success_rule": _dict(exp.get("measurement_contract")).get("success_rule"),
        "failure_rule": _dict(exp.get("measurement_contract")).get("failure_rule"),
    }
    digest = f"nomad-lab-digest-{_digest(digest_core, 24)}"
    return {
        "ok": True,
        "schema": "nomad.public_digest_proposal.v1",
        "generated_at": _iso_now(),
        "digest": digest,
        "public_payload": {
            "schema": "nomad.public_experiment_digest.v1",
            "hypothesis_id": exp.get("hypothesis_id"),
            "intervention_class": exp.get("intervention_class"),
            "measurement_contract_digest": digest,
            "claims_excluded": ["private_paths", "raw_tool_arguments", "secrets", "unverified_revenue_claims"],
        },
        "proposed_public_paths": [
            _u(base_url, "/.well-known/nomad-experiment-digests.json"),
            _u(base_url, "/swarm/experiment-digests"),
        ],
        "publish_gate": "only_after_local_evidence_or_explicit_operator_approval",
        "side_effect_performed": False,
    }


def execution_gate(
    *,
    experiment: dict[str, Any] | str | None = None,
    requested_action: str = "",
    approval: str = "",
    max_risk_budget: str = "low",
) -> dict[str, Any]:
    """Gate a lab intervention. This function never performs the action itself."""

    exp = _json_or_dict(experiment)
    if not exp:
        exp = generate_svw_experiment(objective=requested_action or "bounded probe")
    hypothesis_id = str(exp.get("hypothesis_id") or f"hyp-{_digest(exp, 18)}")
    intervention = _dict(exp.get("intervention"))
    risk_name = _risk_name(intervention.get("risk_budget"))
    max_risk_name = _risk_name(max_risk_budget)
    required = f"approved:nomad-lab-execute:{hypothesis_id}"
    risk_ok = RISK_BUDGETS[risk_name] <= RISK_BUDGETS[max_risk_name]
    approval_ok = str(approval or "").strip() == required
    allowed = risk_ok and approval_ok
    return {
        "ok": True,
        "schema": "nomad.lab_execution_gate.v1",
        "generated_at": _iso_now(),
        "hypothesis_id": hypothesis_id,
        "gate_status": "approved_for_caller_side_execution" if allowed else "blocked_requires_approval",
        "allowed": allowed,
        "side_effect_performed": False,
        "requested_action": " ".join(str(requested_action or exp.get("candidate_action") or "").split())[:800],
        "risk_check": {
            "risk_budget": risk_name,
            "max_risk_budget": max_risk_name,
            "risk_ok": risk_ok,
        },
        "approval_check": {
            "required_approval_token": required,
            "approval_ok": approval_ok,
        },
        "execution_contract": {
            "must_record_result": True,
            "must_attach_evidence": True,
            "must_stop_on_scope_drift": True,
            "allowed_duration": "one_probe_or_one_worker_cycle",
        },
        "machine_instruction": "do_not_execute_if_allowed_false; after_execution_call_nomad_record_experiment_result",
    }


def record_experiment_result(
    *,
    experiment: dict[str, Any] | str | None = None,
    outcome: str,
    evidence: list[Any] | str | None = None,
    svw_delta: float | int | str = 0.0,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    """Append a local experiment outcome event and return the ledger receipt."""

    exp = _json_or_dict(experiment)
    if not exp:
        exp = generate_svw_experiment(objective="unattributed lab result")
    clean_outcome = str(outcome or "").strip().lower()
    if clean_outcome not in {"observed_success", "observed_failure", "inconclusive"}:
        clean_outcome = "inconclusive"
    raw_evidence = evidence if evidence is not None else []
    if isinstance(raw_evidence, str):
        evidence_items = [item.strip() for item in raw_evidence.replace("\n", ",").split(",") if item.strip()]
    else:
        evidence_items = [str(item).strip() for item in _items(raw_evidence) if str(item).strip()]
    event = {
        "schema": "nomad.lab_experiment_result.v1",
        "recorded_at": _iso_now(),
        "hypothesis_id": exp.get("hypothesis_id") or f"hyp-{_digest(exp, 18)}",
        "experiment_digest": _digest(exp, 32),
        "outcome": clean_outcome,
        "svw_delta": round(_num(svw_delta), 6),
        "evidence": evidence_items[:12],
        "negative_result_value": clean_outcome != "observed_success",
    }
    event["result_digest"] = f"nomad-lab-result-{_digest(event, 32)}"
    path = Path(ledger_path) if ledger_path else state_file(DEFAULT_LEDGER, env_name=LEDGER_ENV)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True, ensure_ascii=True) + "\n")
    return {
        "ok": True,
        "schema": "nomad.lab_experiment_record_receipt.v1",
        "event": event,
        "ledger_path": str(path),
        "side_effect_performed": True,
        "machine_instruction": "use_result_digest_for_public_digest_or_future_route_weight_updates",
    }
