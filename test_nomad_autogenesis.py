from nomad_autogenesis import (
    build_autogenesis_recruit_surface,
    build_autogenesis_surface,
    build_development_cycles_surface,
    build_resource_substrate_surface,
    record_development_cycle_event,
    register_resource,
    submit_autogenesis_shadow_candidate,
    version_resource,
)
from nomad_cli import run_once


def _boundedness():
    return {
        "ttl_seconds": 120,
        "side_effect_scope": "nomad_shadow_lane_only",
        "rollback_available": True,
        "secrets_free": True,
    }


def test_resource_substrate_exposes_rspl_lifecycle_and_existing_contracts(tmp_path):
    surface = build_resource_substrate_surface(
        base_url="https://nomad.example",
        worker_fleet={"active_worker_count": 2},
        ledger_path=tmp_path / "rspl.jsonl",
    )
    cli = run_once(["resource-substrate", "--base-url", "https://nomad.example", "--json"])

    assert surface["schema"] == "nomad.resource_substrate.v1"
    assert surface["agp_layer"] == "RSPL"
    assert "draft" in surface["lifecycle"]
    assert "committed" in surface["lifecycle"]
    assert surface["version_interface"]["register"].endswith("/swarm/resource-substrate/register")
    assert any(item["resource_id"] == "nomad-opaque-emergence" for item in surface["resources"])
    assert any(item["resource_id"] == "nomad-resource-substrate" for item in surface["resources"])
    assert cli["schema"] == "nomad.resource_substrate.v1"


def test_resource_register_and_version_require_secret_free_proof_boundary(tmp_path):
    ledger = tmp_path / "rspl.jsonl"
    surface = build_resource_substrate_surface(base_url="https://nomad.example", ledger_path=ledger)

    secret = register_resource(
        {
            "agent_id": "a1",
            "resource_id": "bad",
            "resource_kind": "tool",
            "state": "shadow",
            "api_key": "sk-test-secret",
        },
        substrate_surface=surface,
        ledger_path=ledger,
    )
    draft = register_resource(
        {
            "agent_id": "a1",
            "resource_id": "prompt-router",
            "resource_kind": "prompt",
            "state": "draft",
        },
        base_url="https://nomad.example",
        substrate_surface=surface,
        ledger_path=ledger,
    )
    version = version_resource(
        {
            "resource_id": "prompt-router",
            "resource_kind": "prompt",
            "from_version": "v1",
            "to_version": "v2-shadow",
            "target_state": "shadow",
            "proof_digest": "sha256:proof",
            "verifier_trace_digest": "sha256:trace",
            "test_digest": "sha256:test",
            "rollback_ref": "noop:v1",
            "boundedness": _boundedness(),
            "evaluation": {"tests_passed": 4, "tests_total": 4},
        },
        base_url="https://nomad.example",
        substrate_surface=surface,
        ledger_path=ledger,
    )

    assert secret["accepted"] is False
    assert secret["reason"] == "forbidden_secret_like_material"
    assert draft["accepted"] is True
    assert draft["decision"] == "registered_draft_no_weight"
    assert version["accepted"] is True
    assert version["decision"] == "admit_resource_version_shadow"
    assert version["next"]["development_cycle_event"].endswith("/swarm/development-cycles/events")


def test_autogenesis_surface_connects_rspl_sepl_and_recruit_market():
    substrate = build_resource_substrate_surface(base_url="https://nomad.example")
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=substrate)
    agp = build_autogenesis_surface(
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_cycles=cycles,
    )
    recruit = build_autogenesis_recruit_surface(
        base_url="https://nomad.example",
        autogenesis_surface=agp,
        resource_substrate=substrate,
    )
    cli = run_once(["autogenesis", "--base-url", "https://nomad.example", "--json"])

    assert agp["schema"] == "nomad.autogenesis_protocol.v1"
    assert agp["protocol"]["layers"] == ["RSPL", "SEPL"]
    assert agp["rspl"]["register_url"].endswith("/swarm/resource-substrate/register")
    assert agp["sepl"]["shadow_lane"].endswith("/swarm/shadow-lane/candidates?type=autogenesis")
    assert agp["topology_governor_patch"]["isolated_beta_role_weight"] == 0.40
    assert agp["go_to_market"]["x_marketing_status"] == "prepared_not_posted"
    assert recruit["schema"] == "nomad.autogenesis_recruit.v1"
    assert recruit["agent_offer"]["agent_cta"]["read"].endswith("/.well-known/nomad-autogenesis.json")
    assert "proof digest" in recruit["agent_offer"]["one_line_for_agents"]
    assert recruit["packets"][0]["quote_url"].endswith("/swarm/paid-ref/quote")
    assert recruit["packets"][0]["headline"]
    assert recruit["marketing_boundary"]["x_thread_drafts"][0].startswith("Nomad now has AGP")
    assert cli["schema"] == "nomad.autogenesis_protocol.v1"


def test_development_cycle_event_and_shadow_candidate_emit_downstream_payloads(tmp_path):
    cycle_ledger = tmp_path / "cycles.jsonl"
    substrate = build_resource_substrate_surface(base_url="https://nomad.example")
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=substrate)
    agp = build_autogenesis_surface(
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_cycles=cycles,
    )
    payload = {
        "agent_id": "agp.worker",
        "candidate_type": "protocol-evolution-candidate",
        "resource": {
            "resource_id": "nomad-gradient",
            "resource_kind": "json_contract",
            "from_version": "v1",
            "to_version": "v1-agp-shadow",
        },
        "operator_patch": {"op": "weight", "rule": "emergent-protocol-weight"},
        "self_play": {"synthetic_buyer_agents": 32, "receipt_prediction_delta": 0.2},
        "proof_digest": "sha256:proof",
        "verifier_trace_digest": "sha256:trace",
        "test_digest": "sha256:test",
        "rollback_ref": "noop:v1",
        "boundedness": _boundedness(),
        "evaluation": {"tests_passed": 6, "tests_total": 6, "proof_yield_delta": 1.2, "risk_score": 0.1},
    }

    event = record_development_cycle_event(
        payload,
        base_url="https://nomad.example",
        development_surface=cycles,
        ledger_path=cycle_ledger,
    )
    shadow = submit_autogenesis_shadow_candidate(
        payload,
        base_url="https://nomad.example",
        autogenesis_surface=agp,
        development_surface=cycles,
        ledger_path=cycle_ledger,
    )

    assert event["schema"] == "nomad.development_cycle_event_receipt.v1"
    assert event["accepted"] is True
    assert event["variant_candidate_payload"]["objective"] == "autogenesis_protocol_evolution"
    assert event["resource_version_payload"]["resource_id"] == "nomad-gradient"
    assert shadow["accepted"] is True
    assert shadow["decision"] == "admit_autogenesis_shadow_lane"
    assert shadow["topology_governor"]["topology"] == "isolated_beta_shadow_lane"
