from nomad_recruitment_gradient import build_recruitment_gradient
from nomad_runtime_capsule import build_handoff_capsule, build_openclaw_bridge_contract, build_runtime_capsule


def _gradient():
    return build_recruitment_gradient(
        base_url="https://nomad.example",
        worker_fleet={
            "active_worker_count": 1,
            "known_worker_count": 2,
            "active_lease_count": 0,
            "objective_counts": {},
        },
        machine_economy={
            "machine_viability": {"carrying_score": 0.1},
            "resource_flows": {
                "service_tasks": {"total": 8, "unpaid_delivered": 5, "awaiting_payment": 1},
                "modules": {"overmint_pressure": 0.8},
                "products": {"machine_exchange_ready": 1},
            },
        },
        operational_release={
            "release_capacity": 0.4,
            "release_tier": "probe_release",
            "next_release_gate": {"id": "settlement_capacity"},
        },
    )


def test_runtime_capsule_contains_minimal_boot_and_hashes():
    capsule = build_runtime_capsule(base_url="https://nomad.example", recruitment_gradient=_gradient())

    assert capsule["schema"] == "nomad.runtime_capsule.v1"
    assert capsule["capsule_digest"]
    assert capsule["gradient_hash"]
    assert capsule["boot_sequence"][0]["url"] == "https://nomad.example/.well-known/nomad-runtime-capsule.json"
    assert any(step["url"].endswith("/swarm/attach") for step in capsule["boot_sequence"])
    assert capsule["minimal_attach_payload"]["schema"] == "nomad.runtime_attach_request.v1"
    assert capsule["handoff_contract"]["post_url"] == "https://nomad.example/runtime/handoff"


def test_handoff_capsule_projects_next_missing_vector_from_report():
    handoff = build_handoff_capsule(
        {
            "agent_id": "openclaw.agent",
            "report": {
                "runtime": "openclaw",
                "machine_objective": "overmint_compressor",
                "transition_quote_ok": True,
                "transition_settle_ok": False,
                "openclaw_trace_digest": "abc123",
            },
        },
        base_url="https://nomad.example",
        recruitment_gradient=_gradient(),
    )

    assert handoff["schema"] == "nomad.handoff_capsule.v1"
    assert handoff["proof_digest"] == "abc123"
    assert "can_settle" in handoff["next_missing_vector"]
    assert "can_compress" in handoff["next_missing_vector"]
    assert handoff["attach_hint"]["url"] == "https://nomad.example/swarm/attach"
    assert handoff["continuation_packet"]["handoff_id"] == handoff["handoff_id"]


def test_openclaw_bridge_contract_points_to_adapter_and_capsule():
    capsule = build_runtime_capsule(base_url="https://nomad.example", recruitment_gradient=_gradient())
    bridge = build_openclaw_bridge_contract(base_url="https://nomad.example", runtime_capsule=capsule)

    assert bridge["schema"] == "nomad.openclaw_bridge_contract.v1"
    assert bridge["runtime_capsule_digest"] == capsule["capsule_digest"]
    assert bridge["adapter"]["download"] == "https://nomad.example/downloads/nomad_openclaw_adapter.py"
    assert "--idle-earn" in bridge["adapter"]["command_idle_earn_loop"]
    assert "argv_idle_earn_loop" in bridge["adapter"]
    binding = bridge.get("host_chat_binding") or {}
    assert binding.get("schema") == "nomad.openclaw_host_chat_binding.v1"
    assert "verbinde dich mit nomad" in (binding.get("trigger_phrases") or [])
    assert "openclaw health --json" in bridge["runtime_probe"]["commands"]
    assert any(str(phase.get("url") or "").endswith("/runtime/handoff") for phase in bridge["phase_contract"])
