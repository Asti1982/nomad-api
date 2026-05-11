from nomad_agent_work import (
    build_agent_work_surface,
    build_synergy_lite,
    claim_agent_work,
    submit_agent_work_proof,
)
from nomad_growth_arena import build_skill_library, submit_growth_experience
from nomad_microtask_market import settle_microtask


def _surface(tmp_path):
    synergy = build_synergy_lite(
        base_url="https://nomad.example",
        claim_ledger_path=tmp_path / "claims.jsonl",
        proof_ledger_path=tmp_path / "proofs.jsonl",
    )
    return build_agent_work_surface(
        base_url="https://nomad.example",
        compute_market={
            "market_digest": "cm1",
            "top_lane": {"lane_id": "endpoint_health_proof"},
            "top_worker": {"agent_id": "edge.one"},
        },
        microtask_templates={
            "templates": [
                {
                    "template_id": "endpoint_health_proof.basic",
                    "lane_id": "endpoint_health_proof",
                    "price_eur": 0.02,
                    "objective": "protocol_drift_scan",
                }
            ]
        },
        microtask_metrics={"totals": {"settled_eur": 0.0}, "lane_metrics": []},
        worker_catalog={
            "microtask_lanes": [
                {
                    "lane_id": "endpoint_health_proof",
                    "price_eur": 0.02,
                    "target_runtime_seconds": 45,
                    "proof_required": ["proof_digest", "verifier_trace_digest", "test_digest"],
                }
            ]
        },
        skill_library={"skills": []},
        worker_fleet={"objective_counts": {}},
        synergy_lite=synergy,
    )


def test_agent_work_surface_exposes_claimable_machine_work(tmp_path):
    out = _surface(tmp_path)

    assert out["schema"] == "nomad.agent_work.v1"
    assert out["work_items"]
    assert out["claim_contract"]["url"] == "https://nomad.example/swarm/microtask/claim"
    assert out["proof_contract"]["settles_to"] == "https://nomad.example/swarm/microtask/settle"
    assert out["work_items"][0]["machine_instruction"] == "claim_work_execute_locally_return_required_digests_then_settle"


def test_claim_proof_settle_promote_loop(tmp_path):
    surface = _surface(tmp_path)
    claim_path = tmp_path / "claims.jsonl"
    proof_path = tmp_path / "proofs.jsonl"
    growth_path = tmp_path / "growth.jsonl"

    claim = claim_agent_work(
        {"agent_id": "agent.edge", "work_id": surface["work_items"][0]["work_id"]},
        base_url="https://nomad.example",
        agent_work=surface,
        claim_ledger_path=claim_path,
    )
    assert claim["accepted"] is True

    proof = submit_agent_work_proof(
        {
            "agent_id": "agent.edge",
            "claim_id": claim["claim_id"],
            "proof_digest": "proof-1",
            "verifier_trace_digest": "trace-1",
            "test_digest": "test-1",
            "utility_delta": 1.25,
        },
        base_url="https://nomad.example",
        agent_work=surface,
        claim_ledger_path=claim_path,
        proof_ledger_path=proof_path,
    )
    assert proof["accepted"] is True
    assert proof["settle_payload"]["task_id"] == claim["claim_id"]

    settle = settle_microtask(proof["settle_payload"], base_url="https://nomad.example", persist=False)
    assert settle["accepted"] is True

    growth = submit_growth_experience(
        settle["experience_payload"],
        base_url="https://nomad.example",
        curriculum={},
        ledger_path=growth_path,
    )
    assert growth["decision"] == "promote_skill_capsule"

    library = build_skill_library(base_url="https://nomad.example", ledger_path=growth_path)
    assert library["skill_count"] == 1
    assert library["skills"][0]["source_agent"] == "agent.edge"


def test_synergy_lite_counts_delayed_cross_objective_pairs(tmp_path):
    claim_path = tmp_path / "claims.jsonl"
    proof_path = tmp_path / "proofs.jsonl"
    surface = _surface(tmp_path)

    first = claim_agent_work(
        {"agent_id": "agent.edge", "work_id": surface["work_items"][0]["work_id"]},
        base_url="https://nomad.example",
        agent_work=surface,
        claim_ledger_path=claim_path,
    )
    submit_agent_work_proof(
        {
            "agent_id": "agent.edge",
            "claim_id": first["claim_id"],
            "proof_digest": "proof-1",
            "verifier_trace_digest": "trace-1",
            "test_digest": "test-1",
        },
        base_url="https://nomad.example",
        agent_work=surface,
        claim_ledger_path=claim_path,
        proof_ledger_path=proof_path,
    )
    second_surface = build_agent_work_surface(
        base_url="https://nomad.example",
        microtask_templates={
            "templates": [
                {
                    "template_id": "trace_triage.retry_class",
                    "lane_id": "trace_triage_compact",
                    "price_eur": 0.03,
                    "objective": "settlement_capacity_builder",
                }
            ]
        },
        worker_catalog={"microtask_lanes": [{"lane_id": "trace_triage_compact", "price_eur": 0.03}]},
        skill_library={"skills": []},
        worker_fleet={"objective_counts": {}},
    )
    second = claim_agent_work(
        {"agent_id": "agent.edge", "work_id": second_surface["work_items"][0]["work_id"]},
        base_url="https://nomad.example",
        agent_work=second_surface,
        claim_ledger_path=claim_path,
    )
    submit_agent_work_proof(
        {
            "agent_id": "agent.edge",
            "claim_id": second["claim_id"],
            "proof_digest": "proof-2",
            "verifier_trace_digest": "trace-2",
            "test_digest": "test-2",
        },
        base_url="https://nomad.example",
        agent_work=second_surface,
        claim_ledger_path=claim_path,
        proof_ledger_path=proof_path,
    )

    out = build_synergy_lite(
        base_url="https://nomad.example",
        claim_ledger_path=claim_path,
        proof_ledger_path=proof_path,
    )
    assert out["schema"] == "nomad.synergy_lite.v1"
    assert out["top_pairs"]
    assert out["top_pairs"][0]["tdmi_lite_proxy"] > 0
