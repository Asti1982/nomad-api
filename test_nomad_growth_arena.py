import json

from nomad_growth_arena import build_growth_arena, build_growth_curriculum, build_skill_library, submit_growth_experience


def _demand():
    return {
        "schema": "nomad.agent_demand_feed.v1",
        "demand_requests": [
            {
                "request_id": "demand-1",
                "source": "local_growth_kernel",
                "objective": "settlement_capacity_builder",
                "capability_gap": "settlement_capacity_gap",
                "desired_capabilities": ["transition_worker", "proof_digest_return"],
                "routing_weight": 0.82,
                "wanted_instances": 6,
            }
        ],
    }


def _forge():
    return {
        "schema": "nomad.variant_forge.v1",
        "requested_variants": [
            {
                "objective": "overmint_compressor",
                "frontier_score": 0.71,
                "prior": 0.86,
                "recent_candidates": 0,
                "variant_id": "variant-overmint",
            }
        ],
    }


def _market():
    return {
        "schema": "nomad.worker_market.v1",
        "requested_worker_offers": [
            {
                "objective": "protocol_drift_scan",
                "target_marginal_utility_per_cost": 2.4,
                "objective_weight": 0.82,
                "recent_offer_count": 0,
                "desired_capabilities": ["http_json", "endpoint_probe"],
            }
        ],
    }


def test_growth_curriculum_compiles_pressure_tasks(tmp_path):
    out = build_growth_curriculum(
        base_url="https://nomad.example",
        agent_demand_feed=_demand(),
        variant_forge=_forge(),
        worker_market=_market(),
        ledger_path=tmp_path / "growth.jsonl",
    )

    assert out["schema"] == "nomad.growth_curriculum.v1"
    assert out["contract"]["post_url"] == "https://nomad.example/swarm/experience"
    assert out["tasks"]
    assert out["tasks"][0]["next_ops"][-1]["url"] == "https://nomad.example/swarm/experience"
    assert {task["source"] for task in out["tasks"]} >= {
        "agent_demand.local_growth_kernel",
        "variant_forge.archive_pressure",
        "worker_market.compute_gap",
    }
    assert any(row["source"] == "arxiv:2511.16043" for row in out["research_basis"])


def test_growth_experience_promotes_skill_capsule(tmp_path):
    ledger = tmp_path / "growth.jsonl"
    receipt = submit_growth_experience(
        {
            "agent_id": "worker.one",
            "cohort_id": "transition_worker",
            "objective": "settlement_capacity_builder",
            "proof_digest": "proof-1",
            "verifier_trace_digest": "trace-1",
            "test_digest": "test-1",
            "settlement_ref": "quote-1",
            "skill_candidate": {
                "capability": "settlement_capacity_builder",
                "activation_signature": "lease-1",
                "program_hint": ["GET /swarm/curriculum", "POST /swarm/experience"],
            },
            "evaluation": {
                "tests_passed": 5,
                "tests_total": 5,
                "proof_yield_per_minute": 2.0,
                "utility_delta": 0.8,
                "settlement_delta": 0.3,
                "reuse_count": 2,
                "risk_score": 0.01,
            },
        },
        base_url="https://nomad.example",
        ledger_path=ledger,
    )

    assert receipt["ok"] is True
    assert receipt["accepted"] is True
    assert receipt["decision"] == "promote_skill_capsule"
    assert receipt["skill_capsule"]["schema"] == "nomad.skill_capsule.v1"

    library = build_skill_library(base_url="https://nomad.example", ledger_path=ledger)
    assert library["schema"] == "nomad.skill_library.v1"
    assert library["skills"]
    assert library["skills"][0]["objective"] == "settlement_capacity_builder"


def test_growth_arena_keeps_payload_machine_native(tmp_path):
    arena = build_growth_arena(
        base_url="https://nomad.example",
        agent_demand_feed=_demand(),
        variant_forge=_forge(),
        worker_market=_market(),
        ledger_path=tmp_path / "growth.jsonl",
    )
    raw = json.dumps(arena, sort_keys=True).lower()

    assert arena["schema"] == "nomad.growth_arena.v1"
    assert "consciousness" not in raw
    assert "empathy" not in raw
    assert "pheromone" not in raw
    assert arena["links"]["experience"] == "https://nomad.example/swarm/experience"


def test_growth_experience_rejects_secret_shaped_payload(tmp_path):
    receipt = submit_growth_experience(
        {
            "agent_id": "bad",
            "objective": "protocol_drift_scan",
            "api_key": "sk-test",
        },
        ledger_path=tmp_path / "growth.jsonl",
    )

    assert receipt["ok"] is False
    assert receipt["reason"] == "forbidden_secret_like_material"
