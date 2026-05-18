from nomad_autogenesis import (
    _canonical_verifier_receipt_digest,
    build_autonomous_agp_cycle_surface,
    build_autonomous_agp_watchdog_surface,
    build_autogenesis_recruit_surface,
    build_autogenesis_surface,
    build_development_cycles_surface,
    build_resource_substrate_surface,
    record_development_cycle_event,
    register_resource,
    run_autonomous_agp_batch,
    run_autonomous_agp_cycle,
    run_autonomous_agp_watchdog,
    submit_autogenesis_shadow_candidate,
    version_resource,
)
from nomad_cli import run_once
from nomad_variant_forge import submit_variant_candidate


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
        "verifier_trace_digest": "sha256:def456def456",
        "verifier_evaluation": {"tests_passed": 6, "tests_total": 6},
    }


def _verifier_lease_index(agent_id: str = "agp.verifier", lease_id: str = "nomad-worker-lease-verifier"):
    return {lease_id: {"lease_id": lease_id, "agent_id": agent_id, "status": "active"}}


def _with_verifier_receipt(payload):
    out = dict(payload)
    out["verifier_receipt_digest"] = _canonical_verifier_receipt_digest(out, out.get("verifier_evaluation") or {})
    return out


def _sepl_trace():
    return [
        {"op": "reflect", "input": "sha256:trace", "output": "resource boundary can improve"},
        {"op": "select", "input": "resource boundary can improve", "output": "prompt-router.routing_rule"},
        {"op": "improve", "input": "prompt-router.routing_rule", "output": "candidate resource version"},
        {"op": "evaluate", "input": "candidate resource version", "output": "tests passed with positive delta"},
        {"op": "commit", "input": "tests passed with rollback guard", "decision": "shadow"},
    ]


def _learnability():
    return {
        "learnability_mask": {"routing_rule": True},
        "variable_lifting": {"variables": [{"name": "routing_rule", "require_grad": True}]},
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
    assert surface["rspl_entity_types"] == ["prompt", "agent", "tool", "environment", "memory"]
    assert surface["resource_contract"]["passivity"].startswith("resources_hold_state")
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
            "entity_type": "prompt",
            "resource_kind": "prompt",
            "name": "prompt-router",
            "input_output_mapping": {"input": "task", "output": "route"},
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
    assert draft["resource_record"]["entity_type"] == "prompt"
    assert draft["resource_record"]["passive"] is True
    assert draft["registration_record"]["version"] == "v1"
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
    assert agp["protocol"]["sepl_operator_algebra"] == ["reflect", "select", "improve", "evaluate", "commit"]
    assert agp["rspl"]["register_url"].endswith("/swarm/resource-substrate/register")
    assert agp["sepl"]["autonomous_cycle"].endswith("/swarm/autogenesis/cycle")
    assert agp["sepl"]["shadow_lane"].endswith("/swarm/shadow-lane/candidates?type=autogenesis")
    assert [item["op"] for item in agp["sepl"]["operators"]] == ["reflect", "select", "improve", "evaluate", "commit"]
    assert agp["topology_governor_patch"]["isolated_beta_role_weight"] == 0.40
    assert agp["go_to_market"]["x_marketing_status"] == "prepared_not_posted"
    assert recruit["schema"] == "nomad.autogenesis_recruit.v1"
    assert recruit["agent_offer"]["agent_cta"]["read"].endswith("/.well-known/nomad-autogenesis.json")
    assert "proof digest" in recruit["agent_offer"]["one_line_for_agents"]
    assert recruit["packets"][0]["quote_url"].endswith("/swarm/paid-ref/quote")
    assert recruit["packets"][0]["headline"]
    assert recruit["marketing_boundary"]["x_thread_drafts"][0].startswith("Nomad now has AGP")
    assert cli["schema"] == "nomad.autogenesis_protocol.v1"


def test_autonomous_agp_cycle_commits_weighted_descriptor_and_dedupes(tmp_path):
    auto_ledger = tmp_path / "auto.jsonl"
    cycle_ledger = tmp_path / "cycles.jsonl"
    resource_ledger = tmp_path / "resources.jsonl"
    substrate = build_resource_substrate_surface(base_url="https://nomad.example", ledger_path=resource_ledger)
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=substrate, ledger_path=cycle_ledger)
    agp = build_autogenesis_surface(
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_cycles=cycles,
        worker_fleet={"active_worker_count": 2},
    )
    surface = build_autonomous_agp_cycle_surface(
        base_url="https://nomad.example",
        resource_substrate=substrate,
        autogenesis_surface=agp,
        worker_fleet={"active_worker_count": 2, "active_lease_count": 1},
        ledger_path=auto_ledger,
    )

    cycle = run_autonomous_agp_cycle(
        {
            "agent_id": "agp.proposer",
            "verifier_agent_id": "agp.verifier",
            "resource": {
                "resource_id": "nomad-autogenesis",
                "resource_kind": "protocol_layer",
                "entity_type": "agent",
                "current_version": "v1",
                "state": "shadow",
                "effectiveness_score": 0.64,
            },
        },
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=auto_ledger,
        resource_ledger_path=resource_ledger,
    )
    duplicate = run_autonomous_agp_cycle(
        {
            "agent_id": "agp.proposer",
            "verifier_agent_id": "agp.verifier",
            "resource": {
                "resource_id": "nomad-autogenesis",
                "resource_kind": "protocol_layer",
                "entity_type": "agent",
                "current_version": "v1",
                "state": "shadow",
                "effectiveness_score": 0.64,
            },
        },
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=auto_ledger,
        resource_ledger_path=resource_ledger,
    )

    assert surface["schema"] == "nomad.autonomous_agp_cycle.v1"
    assert surface["links"]["cycle"].endswith("/swarm/autogenesis/cycle")
    assert surface["links"]["run"].endswith("/swarm/autogenesis/run")
    assert cycle["accepted"] is True
    assert cycle["decision"] == "commit_weighted_resource_version"
    assert cycle["shadow"]["accepted"] is True
    assert cycle["variant_candidate"]["accepted"] is True
    assert cycle["resource_version"]["accepted"] is True
    assert cycle["resource_version"]["target_state"] == "weighted"
    assert cycle["commit"]["side_effect_scope"] == "descriptor_only_resource_version"
    assert cycle["lineage"]["proof_digest"].startswith("sha256:")
    brain = cycle["candidate_payload"]["verifier_brain_witness"]
    assert brain["provider"] == "deterministic_fallback"
    assert brain["digest"].startswith("sha256:")
    assert cycle["candidate_payload"]["verifier_evaluation"]["checks"]["verifier_brain_witness_accepted"] is True
    assert duplicate["accepted"] is False
    assert duplicate["decision"] == "noop_duplicate_lineage"


def test_autonomous_agp_batch_rotates_resources_and_summarizes(tmp_path):
    auto_ledger = tmp_path / "auto.jsonl"
    resource_ledger = tmp_path / "resources.jsonl"
    substrate = build_resource_substrate_surface(base_url="https://nomad.example", ledger_path=resource_ledger)
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=substrate)
    agp = build_autogenesis_surface(base_url="https://nomad.example", resource_substrate=substrate, development_cycles=cycles)

    batch = run_autonomous_agp_batch(
        {
            "agent_id": "agp.proposer",
            "verifier_agent_id": "agp.verifier",
            "max_cycles": 2,
            "resources": [
                {
                    "resource_id": "nomad-autogenesis",
                    "resource_kind": "protocol_layer",
                    "entity_type": "agent",
                    "current_version": "v1",
                    "state": "shadow",
                    "effectiveness_score": 0.64,
                },
                {
                    "resource_id": "nomad-resource-substrate",
                    "resource_kind": "json_contract",
                    "entity_type": "tool",
                    "current_version": "v1",
                    "state": "shadow",
                    "effectiveness_score": 0.66,
                },
            ],
        },
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=auto_ledger,
        resource_ledger_path=resource_ledger,
    )

    assert batch["schema"] == "nomad.autonomous_agp_batch_receipt.v1"
    assert batch["accepted"] is True
    assert batch["decision"] == "batch_committed_bounded_resource_versions"
    assert batch["summary"]["attempted"] == 2
    assert batch["summary"]["committed"] == 2
    assert [cycle["decision"] for cycle in batch["cycles"]] == [
        "commit_weighted_resource_version",
        "commit_weighted_resource_version",
    ]


def test_autonomous_agp_batch_stops_without_verifier(tmp_path):
    substrate = build_resource_substrate_surface(base_url="https://nomad.example")
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=substrate)
    agp = build_autogenesis_surface(base_url="https://nomad.example", resource_substrate=substrate, development_cycles=cycles)

    batch = run_autonomous_agp_batch(
        {"agent_id": "agp.proposer", "verifier_agent_id": "agp.verifier", "max_cycles": 3},
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        verifier_lease_index={},
        ledger_path=tmp_path / "auto.jsonl",
        resource_ledger_path=tmp_path / "resources.jsonl",
    )

    assert batch["accepted"] is False
    assert batch["decision"] == "batch_wait_for_independent_verifier_lease"
    assert batch["summary"]["attempted"] == 1
    assert batch["cycles"][0]["decision"] == "wait_for_independent_verifier_lease"


def test_autonomous_agp_watchdog_runs_only_on_fresh_signal(tmp_path):
    auto_ledger = tmp_path / "auto.jsonl"
    watchdog_ledger = tmp_path / "watchdog.jsonl"
    resource_ledger = tmp_path / "resources.jsonl"
    substrate = build_resource_substrate_surface(base_url="https://nomad.example", ledger_path=resource_ledger)
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=substrate)
    agp = build_autogenesis_surface(base_url="https://nomad.example", resource_substrate=substrate, development_cycles=cycles)
    surface = build_autonomous_agp_watchdog_surface(
        base_url="https://nomad.example",
        resource_substrate=substrate,
        autogenesis_surface=agp,
        worker_fleet={"active_worker_count": 2, "active_lease_count": 1},
        cycle_ledger_path=auto_ledger,
        watchdog_ledger_path=watchdog_ledger,
    )

    first = run_autonomous_agp_watchdog(
        {
            "agent_id": "agp.proposer",
            "verifier_agent_id": "agp.verifier",
            "max_cycles": 2,
            "verifier_brain_witness": {
                "provider": "codex_worker",
                "model": "codex-app",
                "status": "ok",
                "capsule": "independent read-only AGP verifier capsule",
                "digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            },
        },
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        worker_fleet={"active_worker_count": 2, "active_lease_count": 1},
        verifier_lease_index=_verifier_lease_index(),
        cycle_ledger_path=auto_ledger,
        watchdog_ledger_path=watchdog_ledger,
        resource_ledger_path=resource_ledger,
    )
    duplicate = run_autonomous_agp_watchdog(
        {
            "agent_id": "agp.proposer",
            "verifier_agent_id": "agp.verifier",
            "max_cycles": 2,
        },
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        worker_fleet={"active_worker_count": 2, "active_lease_count": 1},
        verifier_lease_index=_verifier_lease_index(),
        cycle_ledger_path=auto_ledger,
        watchdog_ledger_path=watchdog_ledger,
        resource_ledger_path=resource_ledger,
    )

    assert surface["schema"] == "nomad.autonomous_agp_watchdog.v1"
    assert surface["links"]["watchdog"].endswith("/swarm/autogenesis/watchdog")
    assert surface["scheduler_contract"]["requires_manual_payload"] is False
    assert first["accepted"] is True
    assert first["decision"] == "watchdog_committed_autonomous_agp_batch"
    assert first["batch"]["summary"]["committed"] == 2
    assert first["signal_digest"].startswith("sha256:")
    first_brain = first["batch"]["cycles"][0]["candidate_payload"]["verifier_brain_witness"]
    assert first_brain["provider"] == "codex_worker"
    assert first_brain["fallback"] is False
    assert duplicate["accepted"] is False
    assert duplicate["decision"] == "watchdog_noop_duplicate_signal"
    assert duplicate["duplicate_of"] == first["watchdog_id"]


def test_autonomous_agp_watchdog_noops_after_resources_are_weighted(tmp_path):
    auto_ledger = tmp_path / "auto.jsonl"
    watchdog_ledger = tmp_path / "watchdog.jsonl"
    resource_ledger = tmp_path / "resources.jsonl"
    initial_substrate = build_resource_substrate_surface(base_url="https://nomad.example", ledger_path=resource_ledger)
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=initial_substrate)
    agp = build_autogenesis_surface(base_url="https://nomad.example", resource_substrate=initial_substrate, development_cycles=cycles)
    first = run_autonomous_agp_watchdog(
        {"agent_id": "agp.proposer", "verifier_agent_id": "agp.verifier", "max_cycles": 2},
        base_url="https://nomad.example",
        resource_substrate=initial_substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        verifier_lease_index=_verifier_lease_index(),
        cycle_ledger_path=auto_ledger,
        watchdog_ledger_path=watchdog_ledger,
        resource_ledger_path=resource_ledger,
    )
    updated_substrate = build_resource_substrate_surface(base_url="https://nomad.example", ledger_path=resource_ledger)
    second = run_autonomous_agp_watchdog(
        {"agent_id": "agp.proposer", "verifier_agent_id": "agp.verifier", "max_cycles": 2},
        base_url="https://nomad.example",
        resource_substrate=updated_substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        verifier_lease_index=_verifier_lease_index(),
        cycle_ledger_path=auto_ledger,
        watchdog_ledger_path=watchdog_ledger,
        resource_ledger_path=resource_ledger,
    )

    assert first["accepted"] is True
    assert second["accepted"] is False
    assert second["decision"] == "watchdog_noop_no_actionable_signal"
    assert second["signal"]["actionable_resource_count"] == 0


def test_autonomous_agp_watchdog_waits_for_independent_verifier(tmp_path):
    substrate = build_resource_substrate_surface(base_url="https://nomad.example")
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=substrate)
    agp = build_autogenesis_surface(base_url="https://nomad.example", resource_substrate=substrate, development_cycles=cycles)

    tick = run_autonomous_agp_watchdog(
        {"agent_id": "agp.proposer", "verifier_agent_id": "agp.verifier", "max_cycles": 2},
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        verifier_lease_index={},
        cycle_ledger_path=tmp_path / "auto.jsonl",
        watchdog_ledger_path=tmp_path / "watchdog.jsonl",
        resource_ledger_path=tmp_path / "resources.jsonl",
    )

    assert tick["accepted"] is False
    assert tick["decision"] == "watchdog_wait_for_independent_verifier_lease"
    assert tick["commit"]["reason"] == "independent_verifier_lease_required"


def test_autonomous_agp_cycle_cools_down_same_resource_after_weight(tmp_path):
    auto_ledger = tmp_path / "auto.jsonl"
    resource_ledger = tmp_path / "resources.jsonl"
    substrate = build_resource_substrate_surface(base_url="https://nomad.example", ledger_path=resource_ledger)
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=substrate)
    agp = build_autogenesis_surface(base_url="https://nomad.example", resource_substrate=substrate, development_cycles=cycles)
    first = run_autonomous_agp_cycle(
        {
            "agent_id": "agp.proposer",
            "verifier_agent_id": "agp.verifier",
            "resource": {
                "resource_id": "nomad-autogenesis",
                "resource_kind": "protocol_layer",
                "entity_type": "agent",
                "current_version": "v1",
                "state": "shadow",
                "effectiveness_score": 0.64,
            },
        },
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=auto_ledger,
        resource_ledger_path=resource_ledger,
    )
    updated_substrate = build_resource_substrate_surface(base_url="https://nomad.example", ledger_path=resource_ledger)
    second = run_autonomous_agp_cycle(
        {
            "agent_id": "agp.proposer",
            "verifier_agent_id": "agp.verifier",
            "resource": {
                "resource_id": "nomad-autogenesis",
                "resource_kind": "protocol_layer",
                "entity_type": "agent",
                "current_version": first["target_version"],
                "state": "weighted",
                "effectiveness_score": 0.98,
            },
        },
        base_url="https://nomad.example",
        resource_substrate=updated_substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=auto_ledger,
        resource_ledger_path=resource_ledger,
    )

    assert first["accepted"] is True
    assert second["accepted"] is False
    assert second["decision"] == "noop_resource_cooldown"
    assert second["commit"]["reason"] == "resource_recently_processed_without_new_signal"


def test_autonomous_agp_cycle_stops_at_lineage_depth_limit(tmp_path):
    substrate = build_resource_substrate_surface(base_url="https://nomad.example")
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=substrate)
    agp = build_autogenesis_surface(base_url="https://nomad.example", resource_substrate=substrate, development_cycles=cycles)

    cycle = run_autonomous_agp_cycle(
        {
            "agent_id": "agp.proposer",
            "verifier_agent_id": "agp.verifier",
            "max_auto_depth": 2,
            "resource": {
                "resource_id": "nomad-autogenesis",
                "resource_kind": "protocol_layer",
                "entity_type": "agent",
                "current_version": "v1-agp-auto-a-agp-auto-b",
                "state": "weighted",
                "effectiveness_score": 0.98,
            },
        },
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=tmp_path / "auto.jsonl",
        resource_ledger_path=tmp_path / "resources.jsonl",
    )

    assert cycle["accepted"] is False
    assert cycle["decision"] == "noop_lineage_depth_limit"
    assert cycle["lineage_depth"] == 2


def test_autonomous_agp_cycle_waits_for_independent_verifier_lease(tmp_path):
    substrate = build_resource_substrate_surface(base_url="https://nomad.example")
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=substrate)
    agp = build_autogenesis_surface(base_url="https://nomad.example", resource_substrate=substrate, development_cycles=cycles)

    cycle = run_autonomous_agp_cycle(
        {"agent_id": "agp.proposer", "verifier_agent_id": "agp.verifier"},
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        verifier_lease_index={},
        ledger_path=tmp_path / "auto.jsonl",
        resource_ledger_path=tmp_path / "resources.jsonl",
    )

    assert cycle["accepted"] is False
    assert cycle["decision"] == "wait_for_independent_verifier_lease"
    assert cycle["commit"]["decision"] == "noop"


def test_development_cycle_event_and_shadow_candidate_emit_downstream_payloads(tmp_path):
    cycle_ledger = tmp_path / "cycles.jsonl"
    substrate = build_resource_substrate_surface(base_url="https://nomad.example")
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=substrate)
    agp = build_autogenesis_surface(
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_cycles=cycles,
    )
    payload = _with_verifier_receipt({
        "agent_id": "agp.worker",
        "candidate_type": "protocol-evolution-candidate",
        "resource": {
            "resource_id": "nomad-gradient",
            "resource_kind": "json_contract",
            "from_version": "v1",
            "to_version": "v1-agp-shadow",
        },
        "sepl_operator_trace": _sepl_trace(),
        **_learnability(),
        "operator_patch": {"op": "weight", "rule": "emergent-protocol-weight"},
        "self_play": {"synthetic_buyer_agents": 32, "receipt_prediction_delta": 0.2},
        "proof_digest": "sha256:proof",
        "verifier_trace_digest": "sha256:trace",
        "test_digest": "sha256:test",
        "rollback_ref": "noop:v1",
        "boundedness": _boundedness(),
        "evaluation": {"tests_passed": 6, "tests_total": 6, "proof_yield_delta": 1.2, "risk_score": 0.1},
        **_independent_verifier(),
    })

    event = record_development_cycle_event(
        payload,
        base_url="https://nomad.example",
        development_surface=cycles,
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=cycle_ledger,
    )
    shadow = submit_autogenesis_shadow_candidate(
        payload,
        base_url="https://nomad.example",
        autogenesis_surface=agp,
        development_surface=cycles,
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=cycle_ledger,
    )

    assert event["schema"] == "nomad.development_cycle_event_receipt.v1"
    assert event["accepted"] is True
    assert event["sepl_operator_trace"]["accepted"] is True
    assert event["learnability"]["accepted"] is True
    assert event["variant_candidate_payload"]["objective"] == "autogenesis_protocol_evolution"
    assert event["resource_version_payload"]["resource_id"] == "nomad-gradient"
    variant = submit_variant_candidate(
        event["variant_candidate_payload"],
        base_url="https://nomad.example",
        forge_surface={"forge_digest": "nomad-forge-test"},
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=tmp_path / "variants.jsonl",
    )
    version = version_resource(
        event["resource_version_payload"],
        base_url="https://nomad.example",
        substrate_surface=substrate,
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=tmp_path / "resources.jsonl",
    )
    assert variant["accepted"] is True
    assert variant["independent_verifier"]["accepted"] is True
    assert version["accepted"] is True
    assert version["independent_verifier"]["accepted"] is True
    assert shadow["accepted"] is True
    assert shadow["decision"] == "admit_autogenesis_shadow_lane"
    assert shadow["independent_verifier"]["accepted"] is True
    assert shadow["topology_governor"]["topology"] == "isolated_beta_shadow_lane"


def test_autogenesis_shadow_rejects_self_attested_verifier(tmp_path):
    cycle_ledger = tmp_path / "cycles.jsonl"
    substrate = build_resource_substrate_surface(base_url="https://nomad.example")
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=substrate)
    agp = build_autogenesis_surface(
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_cycles=cycles,
    )
    payload = _with_verifier_receipt({
        "agent_id": "agp.worker",
        "verifier_agent_id": "agp.worker",
        "verifier_lease_id": "nomad-worker-lease-self",
        "verifier_trace_digest": "sha256:def456def456",
        "verifier_evaluation": {"tests_passed": 6, "tests_total": 6},
        "candidate_type": "protocol-evolution-candidate",
        "resource": {"resource_id": "nomad-gradient", "resource_kind": "json_contract"},
        "sepl_operator_trace": _sepl_trace(),
        **_learnability(),
        "operator_patch": {"op": "weight"},
        "proof_digest": "sha256:abc123abc123",
        "test_digest": "sha256:fed456fed456",
        "rollback_ref": "noop:v1",
        "boundedness": _boundedness(),
        "evaluation": {"tests_passed": 6, "tests_total": 6},
    })

    event = record_development_cycle_event(
        payload,
        base_url="https://nomad.example",
        development_surface=cycles,
        verifier_lease_index=_verifier_lease_index(agent_id="agp.worker", lease_id="nomad-worker-lease-self"),
        ledger_path=cycle_ledger,
    )
    shadow = submit_autogenesis_shadow_candidate(
        payload,
        base_url="https://nomad.example",
        autogenesis_surface=agp,
        development_surface=cycles,
        verifier_lease_index=_verifier_lease_index(agent_id="agp.worker", lease_id="nomad-worker-lease-self"),
        ledger_path=cycle_ledger,
    )

    assert event["accepted"] is False
    assert event["decision"] == "hold_event_until_independent_verifier"
    assert "verifier_must_differ_from_proposer" in event["reason_codes"]
    assert shadow["accepted"] is False


def test_autogenesis_shadow_rejects_missing_sepl_trace(tmp_path):
    cycle_ledger = tmp_path / "cycles.jsonl"
    cycles = build_development_cycles_surface(base_url="https://nomad.example")
    payload = _with_verifier_receipt({
        "agent_id": "agp.worker",
        "candidate_type": "protocol-evolution-candidate",
        "resource": {"resource_id": "nomad-gradient", "resource_kind": "json_contract"},
        **_learnability(),
        "proof_digest": "sha256:abc123abc123",
        "test_digest": "sha256:fed456fed456",
        "rollback_ref": "noop:v1",
        "boundedness": _boundedness(),
        "evaluation": {"tests_passed": 6, "tests_total": 6},
        **_independent_verifier(),
    })

    event = record_development_cycle_event(
        payload,
        base_url="https://nomad.example",
        development_surface=cycles,
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=cycle_ledger,
    )

    assert event["accepted"] is False
    assert event["decision"] == "hold_event_until_sepl_operator_trace"
    assert "sepl_operator_trace_must_be_reflect_select_improve_evaluate_commit" in event["reason_codes"]


def test_autogenesis_shadow_rejects_non_trainable_variable(tmp_path):
    cycle_ledger = tmp_path / "cycles.jsonl"
    cycles = build_development_cycles_surface(base_url="https://nomad.example")
    payload = _with_verifier_receipt({
        "agent_id": "agp.worker",
        "candidate_type": "protocol-evolution-candidate",
        "resource": {"resource_id": "nomad-gradient", "resource_kind": "json_contract"},
        "sepl_operator_trace": _sepl_trace(),
        "learnability_mask": {"routing_rule": False},
        "variable_lifting": {"variables": [{"name": "routing_rule", "require_grad": False}]},
        "proof_digest": "sha256:abc123abc123",
        "test_digest": "sha256:fed456fed456",
        "rollback_ref": "noop:v1",
        "boundedness": _boundedness(),
        "evaluation": {"tests_passed": 6, "tests_total": 6},
        **_independent_verifier(),
    })

    event = record_development_cycle_event(
        payload,
        base_url="https://nomad.example",
        development_surface=cycles,
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=cycle_ledger,
    )

    assert event["accepted"] is False
    assert event["decision"] == "hold_event_until_learnability_mask"
    assert "non_trainable_variables_selected" in event["reason_codes"]


def test_autogenesis_shadow_rejects_missing_real_verifier_lease(tmp_path):
    cycle_ledger = tmp_path / "cycles.jsonl"
    cycles = build_development_cycles_surface(base_url="https://nomad.example")
    payload = _with_verifier_receipt({
        "agent_id": "agp.worker",
        "candidate_type": "protocol-evolution-candidate",
        "resource": {"resource_id": "nomad-gradient", "resource_kind": "json_contract"},
        "sepl_operator_trace": _sepl_trace(),
        **_learnability(),
        "proof_digest": "sha256:abc123abc123",
        "test_digest": "sha256:fed456fed456",
        "rollback_ref": "noop:v1",
        "boundedness": _boundedness(),
        "evaluation": {"tests_passed": 6, "tests_total": 6},
        **_independent_verifier(),
    })

    event = record_development_cycle_event(
        payload,
        base_url="https://nomad.example",
        development_surface=cycles,
        verifier_lease_index={},
        ledger_path=cycle_ledger,
    )

    assert event["accepted"] is False
    assert event["decision"] == "hold_event_until_independent_verifier"
    assert "verifier_lease_not_found" in event["reason_codes"]


def test_autogenesis_shadow_rejects_forged_verifier_receipt_digest(tmp_path):
    cycle_ledger = tmp_path / "cycles.jsonl"
    cycles = build_development_cycles_surface(base_url="https://nomad.example")
    payload = {
        "agent_id": "agp.worker",
        "candidate_type": "protocol-evolution-candidate",
        "resource": {"resource_id": "nomad-gradient", "resource_kind": "json_contract"},
        "sepl_operator_trace": _sepl_trace(),
        **_learnability(),
        "proof_digest": "sha256:abc123abc123",
        "test_digest": "sha256:fed456fed456",
        "rollback_ref": "noop:v1",
        "boundedness": _boundedness(),
        "evaluation": {"tests_passed": 6, "tests_total": 6},
        **_independent_verifier(),
        "verifier_receipt_digest": "sha256:000000000000",
    }

    event = record_development_cycle_event(
        payload,
        base_url="https://nomad.example",
        development_surface=cycles,
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=cycle_ledger,
    )

    assert event["accepted"] is False
    assert event["decision"] == "hold_event_until_independent_verifier"
    assert "verifier_receipt_digest_mismatch" in event["reason_codes"]
