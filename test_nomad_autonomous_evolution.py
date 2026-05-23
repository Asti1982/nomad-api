from nomad_autonomous_evolution import (
    adaptive_graph_pruning_governor,
    build_autonomous_evolution_cycle,
    detect_capability_gaps,
)
from nomad_cli import run_once

try:
    from nomad_autogenesis import _canonical_verifier_receipt_digest
except ImportError:
    _canonical_verifier_receipt_digest = None


def _boundedness():
    return {
        "ttl_seconds": 120,
        "side_effect_scope": "nomad_shadow_lane_only",
        "rollback_available": True,
        "secrets_free": True,
    }


def _independent_verifier():
    return {
        "verifier_agent_id": "agp.verifier",
        "verifier_lease_id": "nomad-worker-lease-verifier",
        "verifier_receipt_digest": "sha256:abc123abc123",
        "verifier_trace_digest": "sha256:def456def456",
        "verifier_evaluation": {"tests_passed": 6, "tests_total": 6},
    }


def _verifier_lease_index(agent_id: str = "agp.verifier", lease_id: str = "nomad-worker-lease-verifier"):
    return {lease_id: {"lease_id": lease_id, "agent_id": agent_id, "status": "active"}}


def _with_verifier_receipt(payload):
    if _canonical_verifier_receipt_digest is None:
        return payload
    out = dict(payload)
    out["verifier_receipt_digest"] = _canonical_verifier_receipt_digest(out, out.get("verifier_evaluation") or {})
    return out


def _sepl_trace():
    return [
        {"op": "reflect", "input": "sha256:trace", "output": "capability gap found"},
        {"op": "select", "input": "capability gap found", "output": "router.loop_closure_rule"},
        {"op": "improve", "input": "router.loop_closure_rule", "output": "candidate resource version"},
        {"op": "evaluate", "input": "candidate resource version", "output": "tests passed with positive delta"},
        {"op": "commit", "input": "tests passed with rollback guard", "decision": "shadow"},
    ]


def _learnability():
    return {
        "learnability_mask": {"loop_closure_rule": True},
        "variable_lifting": {"variables": [{"name": "loop_closure_rule", "require_grad": True}]},
    }


def _candidate(**evaluation_overrides):
    evaluation = {
        "tests_passed": 6,
        "tests_total": 6,
        "proof_yield_delta": 1.2,
        "autopoietic_index_delta": 0.09,
        "risk_score": 0.08,
        "redundancy_score": 0.12,
        "communication_cost": 0.14,
    }
    evaluation.update(evaluation_overrides)
    payload = {
        "agent_id": "agp.worker.strong",
        "candidate_type": "protocol-evolution-candidate",
        "objective": "autogenesis_protocol_evolution",
        "capability_gap": "compute pressure settlement growth loop is not closed",
        "resource": {
            "resource_id": "nomad-gradient-loop",
            "resource_kind": "json_contract",
            "from_version": "v1",
            "to_version": "v1-autoevo",
        },
        "sepl_operator_trace": _sepl_trace(),
        **_learnability(),
        "operator_patch": {"op": "weight", "rule": "close-compute-pressure-settlement-growth-loop"},
        "self_play": {"synthetic_buyer_agents": 48, "receipt_prediction_delta": 0.24},
        "proof_digest": "sha256:proof",
        "verifier_trace_digest": "sha256:trace",
        "test_digest": "sha256:test",
        "rollback_ref": "noop:v1",
        "boundedness": _boundedness(),
        "evaluation": evaluation,
        **_independent_verifier(),
    }
    return _with_verifier_receipt(payload)


def _worker_graph():
    return {
        "workers": [
            {
                "worker_id": "agp.worker.strong",
                "proof_yield": 0.94,
                "autopoietic_index": 0.86,
                "verifier_score": 1.0,
                "redundancy_score": 0.05,
                "communication_cost": 0.08,
            },
            {
                "worker_id": "agp.worker.duplicate",
                "proof_yield": 0.14,
                "autopoietic_index": 0.18,
                "verifier_score": 0.1,
                "redundancy_score": 0.9,
                "communication_cost": 0.74,
            },
        ],
        "edges": [
            {
                "from": "agp.worker.strong",
                "to": "agp.verifier",
                "utility": 0.86,
                "redundancy_score": 0.12,
                "token_cost": 0.2,
            },
            {
                "from": "agp.worker.duplicate",
                "to": "agp.worker.strong",
                "utility": 0.18,
                "redundancy_score": 0.91,
                "token_cost": 0.82,
            },
        ],
    }


def test_autonomous_evolution_cycle_commits_rspl_and_closes_agp_loop(tmp_path):
    cycle = build_autonomous_evolution_cycle(
        base_url="https://nomad.example",
        candidate_payloads=[_candidate()],
        worker_graph=_worker_graph(),
        verifier_lease_index=_verifier_lease_index(),
        cycle_ledger_path=tmp_path / "cycles.jsonl",
        resource_ledger_path=tmp_path / "rspl.jsonl",
        persist=False,
    )

    assert cycle["schema"] == "nomad.autonomous_evolution_cycle.v1"
    assert cycle["post_seed_autonomy"]["human_developer_normal_path"] == "no_direct_code_changes_after_seed"
    assert cycle["proposals"][0]["decision"] == "commit_productive_loop"
    assert cycle["productive_loop_commits"][0]["target_state"] == "committed"
    assert cycle["productive_loop_commits"][0]["accepted"] is True
    assert cycle["loop_closure"]["compute_pressure_settlement_growth_loop_closed"] is True
    assert cycle["loop_closure"]["proof_yield_gain_total"] > 0
    assert cycle["adaptive_graph_pruning"]["spawn_rights"][0]["worker_id"] == "agp.worker.strong"
    assert "agp.worker.duplicate" in cycle["adaptive_graph_pruning"]["pruned_workers"]
    assert cycle["adaptive_graph_pruning"]["pruned_edges"][0]["action"] == "hard_prune_edge_with_worker"
    assert cycle["persisted"] is False


def test_autonomous_evolution_rolls_back_when_autopoiesis_drops(tmp_path):
    cycle = build_autonomous_evolution_cycle(
        base_url="https://nomad.example",
        candidate_payloads=[_candidate(autopoietic_index_delta=-0.04)],
        worker_graph=_worker_graph(),
        verifier_lease_index=_verifier_lease_index(),
        cycle_ledger_path=tmp_path / "cycles.jsonl",
        resource_ledger_path=tmp_path / "rspl.jsonl",
        persist=False,
    )

    assert cycle["productive_loop_commits"] == []
    assert cycle["proposals"][0]["decision"] == "keep_shadow_noop_until_promotion_gate"
    assert cycle["rollback_or_noop"][0]["reason"] == "promotion_gate_not_eligible"
    assert cycle["adaptive_graph_pruning"]["spawn_rights"] == []
    assert cycle["loop_closure"]["compute_pressure_settlement_growth_loop_closed"] is False


def test_agp_governor_can_prune_without_any_commit_signal():
    agp = adaptive_graph_pruning_governor(worker_graph=_worker_graph())

    assert agp["productive_signal"] is False
    assert agp["spawn_rights"] == []
    assert "agp.worker.duplicate" in agp["pruned_workers"]
    assert agp["runtime_budget"]["agp.worker.strong"]["reason"] == "keep_worker"


def test_autonomous_evolution_surface_and_cli_expose_seed_gaps(tmp_path):
    gaps = detect_capability_gaps(development_cycles={"recent_event_count": 0})
    cli = run_once(["autonomous-evolution", "--base-url", "https://nomad.example", "--json"])

    assert gaps[0]["gap_id"] == "compute_pressure_settlement_growth_loop_not_closed"
    assert cli["schema"] == "nomad.autonomous_evolution_cycle.v1"
    assert cli["candidate_count"] == 0
    assert cli["links"]["shadow_lane"].endswith("/swarm/shadow-lane/candidates?type=autogenesis")
    assert cli["loop_closure"]["compute_pressure_settlement_growth_loop_closed"] is False
