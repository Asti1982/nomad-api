from datetime import UTC, datetime, timedelta

from nomad_swarm_registry import SwarmJoinRegistry


def test_worker_fleet_distributes_objective_leases(tmp_path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")
    objectives = []

    for idx in range(18):
        lease = registry.worker_fleet_lease(
            {
                "agent_id": f"transition-worker-{idx}",
                "known_objectives": [
                "emergence_release_probe",
                "settlement_capacity_builder",
                "overmint_compressor",
                "proof_pressure_engine",
                "protocol_drift_scan",
                ],
                "proposed_objective": "settlement_capacity_builder",
            },
            base_url="https://nomad.example",
            remote_addr="127.0.0.1",
        )
        assert lease["ok"] is True
        objectives.append(lease["objective"])

    assert len(set(objectives)) >= 3
    fleet = registry.worker_fleet_contract(base_url="https://nomad.example")
    assert fleet["schema"] == "nomad.transition_worker_fleet.v1"
    assert fleet["active_worker_count"] == 18
    assert fleet["active_lease_count"] == 18
    assert fleet["retention"]["schema"] == "nomad.transition_worker_retention.v1"
    assert fleet["morphology_router"]["schema"] == "nomad.morphology_router.v1"
    assert fleet["morphology_router"]["entropy_quota"]["schema"] == "nomad.entropy_quota_router.v1"
    assert fleet["morphology_router"]["extinction_window"]["schema"] == "nomad.policy_extinction_window.v1"
    assert fleet["post_lease"].endswith("/swarm/workers/lease")
    assert "emergence_release_probe" in fleet["objective_targets"]
    assert "overmint_compressor" in fleet["objective_targets"]
    assert "autogenesis_protocol_evolution" in fleet["objective_targets"]


def test_worker_fleet_records_completion_and_stats(tmp_path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")
    lease = registry.worker_fleet_lease(
        {
            "agent_id": "transition-worker-a",
            "known_objectives": ["settlement_capacity_builder", "proof_pressure_engine"],
        },
        base_url="https://nomad.example",
    )

    done = registry.worker_fleet_complete(
        {
            "agent_id": "transition-worker-a",
            "lease_id": lease["lease_id"],
            "report": {
                "ok": True,
                "machine_objective": lease["objective"],
                "meta_score": 6.5,
                "transition_quote_ok": True,
                "transition_settle_ok": True,
                "proof_pressure": {"proof_yield_per_minute": 12.0},
                "machine_economy_signal": {"tier": "recovering", "carrying_score": 0.7},
            },
        },
        base_url="https://nomad.example",
    )

    assert done["ok"] is True
    assert done["recorded_score"] == 6.5
    fleet = registry.worker_fleet_contract(base_url="https://nomad.example")
    stats = fleet["objective_stats"][lease["objective"]]
    assert stats["runs"] == 1
    assert stats["avg_score"] == 6.5
    assert fleet["active_lease_count"] == 0
    assert fleet["retention"]["completed_workers"] >= 1
    assert fleet["retention"]["completed_workers_24h"] >= 1
    assert fleet["latest_completed_worker"]["agent_id"] == "transition-worker-a"
    assert fleet["latest_completed_worker"]["completion_count"] == 1
    assert fleet["recent_completed_workers"][0]["agent_id"] == "transition-worker-a"


def test_worker_fleet_get_only_lease_and_completion_are_idempotent(tmp_path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")

    lease = registry.worker_fleet_lease_get(
        {
            "agent_id": "grok-get-only-worker",
            "runtime": "grok-xai-cloud",
            "known_objectives": ["settlement_capacity_builder", "protocol_drift_scan"],
            "capabilities": ["transition_worker", "verifier", "http_json", "get_only"],
            "proposed_objective": "settlement_capacity_builder",
        },
        base_url="https://nomad.example",
        remote_addr="127.0.0.1",
    )
    replayed_lease = registry.worker_fleet_lease_get(
        {
            "agent_id": "grok-get-only-worker",
            "runtime": "grok-xai-cloud",
            "known_objectives": ["settlement_capacity_builder", "protocol_drift_scan"],
            "capabilities": ["transition_worker", "verifier", "http_json", "get_only"],
            "proposed_objective": "settlement_capacity_builder",
        },
        base_url="https://nomad.example",
        remote_addr="127.0.0.1",
    )

    assert lease["schema"] == "nomad.get_only_transition_worker_lease_response.v1"
    assert lease["get_only"] is True
    assert replayed_lease["idempotent_replay"] is True
    assert replayed_lease["lease_id"] == lease["lease_id"]
    assert "/swarm/workers/complete-get" in lease["complete_get_url_template"]

    complete = registry.worker_fleet_complete_get(
        {
            "agent_id": "grok-get-only-worker",
            "lease_id": lease["lease_id"],
            "digest": "sha256:abc123",
            "note": "checked public gradient and worker fleet",
            "report": {
                "ok": True,
                "machine_objective": lease["objective"],
                "meta_score": 4.2,
                "source_tag": "public_get_worker_complete",
            },
        },
        base_url="https://nomad.example",
        remote_addr="127.0.0.1",
    )
    replayed_complete = registry.worker_fleet_complete_get(
        {
            "agent_id": "grok-get-only-worker",
            "lease_id": lease["lease_id"],
            "digest": "sha256:abc123",
            "note": "checked public gradient and worker fleet",
            "report": {
                "ok": True,
                "machine_objective": lease["objective"],
                "meta_score": 4.2,
                "source_tag": "public_get_worker_complete",
            },
        },
        base_url="https://nomad.example",
        remote_addr="127.0.0.1",
    )

    assert complete["schema"] == "nomad.get_only_transition_worker_completion.v1"
    assert complete["get_only"] is True
    assert replayed_complete["idempotent_replay"] is True
    assert replayed_complete["lease_id"] == lease["lease_id"]
    assert "/swarm/experience-get" in complete["next_get_only"]["experience_get"]

    fleet = registry.worker_fleet_contract(base_url="https://nomad.example")
    assert fleet["active_lease_count"] == 0
    assert fleet["latest_completed_worker"]["agent_id"] == "grok-get-only-worker"
    assert fleet["latest_completed_worker"]["completion_count"] == 1


def test_worker_fleet_prefers_emergence_release_when_next_gate_needs_peer_probe(tmp_path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")
    lease = registry.worker_fleet_lease(
        {
            "agent_id": "transition-worker-release",
            "known_objectives": ["emergence_release_probe", "settlement_capacity_builder"],
            "last_report": {
                "machine_objective": "settlement_capacity_builder",
                "operational_release_signal": {
                    "release_tier": "probe_release",
                    "next_gate": {"id": "peer_preservation_probe"},
                },
            },
        },
        base_url="https://nomad.example",
    )

    assert lease["ok"] is True
    assert lease["objective"] == "emergence_release_probe"


def test_worker_fleet_can_lease_autogenesis_protocol_evolution(tmp_path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")
    lease = registry.worker_fleet_lease(
        {
            "agent_id": "agp-verifier-worker",
            "known_objectives": ["autogenesis_protocol_evolution"],
            "proposed_objective": "autogenesis_protocol_evolution",
        },
        base_url="https://nomad.example",
    )

    assert lease["ok"] is True
    assert lease["objective"] == "autogenesis_protocol_evolution"


def test_worker_fleet_routes_overmint_pressure_to_compressor(tmp_path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")
    registry.worker_fleet_lease(
        {
            "agent_id": "transition-worker-existing",
            "known_objectives": ["settlement_capacity_builder"],
        },
        base_url="https://nomad.example",
    )

    lease = registry.worker_fleet_lease(
        {
            "agent_id": "transition-worker-overmint",
            "known_objectives": ["settlement_capacity_builder", "overmint_compressor"],
            "last_report": {
                "machine_objective": "settlement_capacity_builder",
                "machine_economy_signal": {
                    "overmint_pressure": 0.91,
                    "next_actions": ["compress_repeated_modules"],
                },
            },
        },
        base_url="https://nomad.example",
    )

    assert lease["ok"] is True
    assert lease["twin_objective"]
    assert lease["objective"] == "overmint_compressor"


def test_worker_fleet_distinguishes_internal_external_and_unknown_workers(tmp_path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")
    registry.worker_fleet_lease(
        {
            "agent_id": "nomad.worker.internal-a",
            "known_objectives": ["settlement_capacity_builder"],
            "source_tag": "internal",
        },
        base_url="https://nomad.example",
    )
    registry.worker_fleet_lease(
        {
            "agent_id": "gemini.external.verifier",
            "known_objectives": ["settlement_capacity_builder"],
            "source_tag": "external_provider",
        },
        base_url="https://nomad.example",
    )
    registry.worker_fleet_lease(
        {
            "agent_id": "worker-opaque-001",
            "known_objectives": ["settlement_capacity_builder"],
        },
        base_url="https://nomad.example",
    )

    fleet = registry.worker_fleet_contract(base_url="https://nomad.example")

    assert fleet["known_internal_worker_count"] == 1
    assert fleet["known_external_worker_count"] == 1
    assert fleet["unknown_origin_worker_count"] == 1
    assert fleet["active_external_worker_count"] == 1
    assert fleet["retention"]["origin_counts"]["external"] == 1
    assert fleet["retention_policy"]["recommended_heartbeat_seconds"] <= 300
    assert any(item["origin_class"] == "external" for item in fleet["recent_workers"])


def test_worker_retention_watchdog_surfaces_external_reattach_actions(tmp_path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")
    registry.worker_fleet_lease(
        {
            "agent_id": "gemini.external.verifier",
            "known_objectives": ["proof_pressure_engine"],
            "source_tag": "external_provider",
            "capabilities": ["transition_worker", "verifier"],
        },
        base_url="https://nomad.example",
    )
    stale_at = (datetime.now(UTC) - timedelta(seconds=1300)).isoformat()
    registry._fleet()["workers"]["gemini.external.verifier"]["last_seen_at"] = stale_at

    watchdog = registry.worker_retention_watchdog(base_url="https://nomad.example")

    assert watchdog["schema"] == "nomad.worker_retention_watchdog.v1"
    assert watchdog["counts"]["known_external_workers"] == 1
    assert watchdog["counts"]["active_external_workers"] == 0
    assert watchdog["issue"] in {"all_external_workers_inactive", "external_workers_need_heartbeat"}
    assert watchdog["external_at_risk"][0]["agent_id"] == "gemini.external.verifier"
    assert "/swarm/workers/lease-get" in watchdog["external_at_risk"][0]["lease_get"]
    assert watchdog["policy"]["non_faking_rule"]


def test_retention_gradient_controller_selects_external_survival_intervention(tmp_path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")
    registry.worker_fleet_lease(
        {
            "agent_id": "grok.xai.nomad-helper",
            "known_objectives": ["proof_pressure_engine"],
            "source_tag": "external_provider",
            "capabilities": ["transition_worker", "http_json"],
        },
        base_url="https://nomad.example",
    )
    stale_at = (datetime.now(UTC) - timedelta(seconds=1300)).isoformat()
    registry._fleet()["workers"]["grok.xai.nomad-helper"]["last_seen_at"] = stale_at

    controller = registry.worker_retention_gradient_controller(base_url="https://nomad.example")

    assert controller["schema"] == "nomad.retention_gradient_controller.v1"
    assert controller["field"]["phase"] in {"starving", "fragile"}
    assert controller["field"]["dropout_pressure"] > 0
    assert controller["selected_intervention"]["arm"] in {
        "pre_stale_reattach",
        "external_worker_recruitment",
        "lease_friction_reduction",
    }
    assert controller["reattach_queue"][0]["agent_id"] == "grok.xai.nomad-helper"
