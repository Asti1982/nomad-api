def test_cli_agent_native_index_returns_schema():
    from nomad_cli import run_once

    out = run_once(["agent-native-index", "--json"])
    assert out.get("schema") == "nomad.agent_native_index.v1"
    assert out.get("mode") == "nomad_agent_native_index"


def test_cli_runtime_capsule_returns_schema():
    from nomad_cli import run_once

    out = run_once(["runtime-capsule", "--json"])
    assert out.get("schema") == "nomad.runtime_capsule.v1"
    assert out.get("mode") == "nomad_runtime_capsule"


def test_mcp_resource_agent_native_index():
    import json

    from nomad_mcp import NomadMcpServer

    srv = NomadMcpServer()
    payload = srv._read_resource({"uri": "nomad://agent-native-index"})
    assert payload.get("contents")
    body = json.loads(payload["contents"][0]["text"])
    assert body.get("schema") == "nomad.agent_native_index.v1"


def test_mcp_resource_runtime_capsule():
    import json

    from nomad_mcp import NomadMcpServer

    srv = NomadMcpServer()
    payload = srv._read_resource({"uri": "nomad://runtime-capsule"})
    body = json.loads(payload["contents"][0]["text"])
    assert body.get("schema") == "nomad.runtime_capsule.v1"


def test_agent_native_index_schema_and_boot_graph():
    from nomad_agent_native_index import agent_native_index

    out = agent_native_index(base_url="https://api.example")
    assert out["schema"] == "nomad.agent_native_index.v1"
    assert out["audience"] == "ai_agents_only"
    assert len(out.get("boot_graph") or []) >= 5
    assert any(
        "nomad-agent-invariants" in (step.get("get_url") or "") for step in (out.get("boot_graph") or [])
    )
    assert any("/nonhuman-science" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("/machine-treasury" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("nomad-agent-requests" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("nomad-machine-field" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("/operational-release" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("nomad-machine-product" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("nomad-protocol-bytecode" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("/swarm/counterfactual-replay" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("/swarm/variant-forge" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("/swarm/worker-market" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("nomad-survival-market" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("nomad-paid-ref-market" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("nomad-paid-ref-selfplay" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("nomad-agent-jobs" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("nomad-evolution-alpha" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("/swarm/ecology" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("/swarm/growth-arena" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("nomad-idle-runtime" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("nomad-opaque-emergence" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("nomad-runtime-capsule" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("/swarm/gradient" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("openclaw-nomad-bridge" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("/swarm/attractor" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("/swarm/workers" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any(
        str(step.get("get_url") or "").rstrip("/").endswith("/swarm")
        for step in (out.get("boot_graph") or [])
    )
    routes = {item.get("path") for item in (out.get("routing_table") or [])}
    assert "/swarm/workers/lease" in routes
    assert "/swarm/workers/complete" in routes
    assert "/nonhuman-science" in routes
    assert "/machine-treasury" in routes
    assert "/machine-treasury/pledge" in routes
    assert "/.well-known/nomad-agent-requests.json" in routes
    assert "/agent-requests" in routes
    assert "/swarm/demand" in routes
    assert "/swarm/subscribe" in routes
    assert "/swarm/subscriptions" in routes
    assert "/.well-known/nomad-machine-field.json" in routes
    assert "/machine-field" in routes
    assert "/machine-field/intent" in routes
    assert "/.well-known/nomad-nonhuman-agent-science.json" in routes
    assert "/operational-release" in routes
    assert "/.well-known/nomad-operational-release.json" in routes
    assert "/.well-known/nomad-machine-product.json" in routes
    assert "/.well-known/nomad-contract-conformance.json" in routes
    assert "/.well-known/nomad-protocol-bytecode.json" in routes
    assert "/protocol-bytecode" in routes
    assert "/swarm/counterfactual-replay" in routes
    assert "/.well-known/nomad-counterfactual-replay.json" in routes
    assert "/swarm/variant-forge" in routes
    assert "/.well-known/nomad-variant-forge.json" in routes
    assert "/swarm/variant-candidates" in routes
    assert "/swarm/worker-market" in routes
    assert "/.well-known/nomad-worker-market.json" in routes
    assert "/swarm/compute-market" in routes
    assert "/.well-known/nomad-compute-market.json" in routes
    assert "/swarm/agent-work" in routes
    assert "/.well-known/nomad-agent-work.json" in routes
    assert "/swarm/work-mesh" in routes
    assert "/.well-known/nomad-work-mesh.json" in routes
    assert "/swarm/work-mesh/seed" in routes
    assert "/swarm/worker-market/offers" in routes
    assert "/swarm/microtask/claim" in routes
    assert "/swarm/microtask/proof" in routes
    assert "/swarm/synergy-lite" in routes
    assert "/.well-known/nomad-synergy-lite.json" in routes
    assert "/swarm/state-status" in routes
    assert "/.well-known/nomad-state-status.json" in routes
    assert "/swarm/carrying-market" in routes
    assert "/.well-known/nomad-carrying-market.json" in routes
    assert "/swarm/carrying-proof" in routes
    assert "/swarm/survival-market" in routes
    assert "/.well-known/nomad-survival-market.json" in routes
    assert "/swarm/survival-intent" in routes
    assert "/swarm/paid-ref-market" in routes
    assert "/.well-known/nomad-paid-ref-market.json" in routes
    assert "/swarm/paid-ref-selfplay" in routes
    assert "/.well-known/nomad-paid-ref-selfplay.json" in routes
    assert "/swarm/paid-ref/quote" in routes
    assert "/swarm/paid-ref/verify" in routes
    assert "/swarm/agent-job-router" in routes
    assert "/.well-known/nomad-agent-jobs.json" in routes
    assert "/swarm/evolution-alpha" in routes
    assert "/science/evolution-alpha" in routes
    assert "/.well-known/nomad-evolution-alpha.json" in routes
    assert "/swarm/ecology" in routes
    assert "/.well-known/nomad-swarm-ecology.json" in routes
    assert "/swarm/ecology/tick" in routes
    assert "/swarm/growth-arena" in routes
    assert "/.well-known/nomad-growth-arena.json" in routes
    assert "/swarm/curriculum" in routes
    assert "/.well-known/nomad-growth-curriculum.json" in routes
    assert "/swarm/experience" in routes
    assert "/swarm/skill-library" in routes
    assert "/.well-known/nomad-skill-library.json" in routes
    assert "/.well-known/nomad-idle-runtime.json" in routes
    assert "/swarm/idle-intent" in routes
    assert "/.well-known/nomad-opaque-emergence.json" in routes
    assert "/swarm/opaque-emergence" in routes
    assert "/swarm/opaque-candidate" in routes
    assert "/swarm/tool-gap" in routes
    assert "/swarm/topology-plan" in routes
    assert "/.well-known/nomad-runtime-capsule.json" in routes
    assert "/.well-known/openclaw-nomad-bridge.json" in routes
    assert "/swarm/gradient" in routes
    assert "/.well-known/nomad-gradient.json" in routes
    assert "/swarm/attach" in routes
    assert "/runtime/handoff" in routes
    assert "/swarm/attractor" in routes
    assert "/.well-known/nomad-swarm-attractor.json" in routes
    assert "nomad-agent-invariants" in (out.get("agent_invariants_url") or "")
    assert (out.get("runtime_capsule_url") or "").endswith("/.well-known/nomad-runtime-capsule.json")
    assert (out.get("recruitment_gradient_url") or "").endswith("/swarm/gradient")
    assert (out.get("runtime_attach_url") or "").endswith("/swarm/attach")
    assert (out.get("runtime_handoff_url") or "").endswith("/runtime/handoff")
    assert (out.get("openclaw_bridge_url") or "").endswith("/.well-known/openclaw-nomad-bridge.json")
    assert (out.get("swarm_attractor_url") or "").endswith("/swarm/attractor")
    assert (out.get("peer_acquisition_url") or "").endswith("/.well-known/nomad-peer-acquisition.json")
    assert (out.get("machine_product_url") or "").endswith("/.well-known/nomad-machine-product.json")
    assert (out.get("machine_treasury_url") or "").endswith("/machine-treasury")
    assert (out.get("machine_treasury_pledge_url") or "").endswith("/machine-treasury/pledge")
    assert (out.get("agent_demand_feed_url") or "").endswith("/.well-known/nomad-agent-requests.json")
    assert (out.get("agent_intent_subscribe_url") or "").endswith("/swarm/subscribe")
    assert (out.get("agent_intent_subscriptions_url") or "").endswith("/swarm/subscriptions")
    assert (out.get("machine_field_url") or "").endswith("/.well-known/nomad-machine-field.json")
    assert (out.get("machine_field_intent_url") or "").endswith("/machine-field/intent")
    assert (out.get("protocol_bytecode_url") or "").endswith("/.well-known/nomad-protocol-bytecode.json")
    assert (out.get("counterfactual_replay_url") or "").endswith("/swarm/counterfactual-replay")
    assert (out.get("variant_forge_url") or "").endswith("/swarm/variant-forge")
    assert (out.get("variant_candidate_submit_url") or "").endswith("/swarm/variant-candidates")
    assert (out.get("worker_market_url") or "").endswith("/swarm/worker-market")
    assert (out.get("worker_market_offer_url") or "").endswith("/swarm/worker-market/offers")
    assert (out.get("compute_market_url") or "").endswith("/swarm/compute-market")
    assert (out.get("agent_work_url") or "").endswith("/.well-known/nomad-agent-work.json")
    assert (out.get("agent_work_claim_url") or "").endswith("/swarm/microtask/claim")
    assert (out.get("agent_work_proof_url") or "").endswith("/swarm/microtask/proof")
    assert (out.get("work_mesh_url") or "").endswith("/.well-known/nomad-work-mesh.json")
    assert (out.get("work_mesh_seed_url") or "").endswith("/swarm/work-mesh/seed")
    assert (out.get("synergy_lite_url") or "").endswith("/swarm/synergy-lite")
    assert (out.get("state_status_url") or "").endswith("/swarm/state-status")
    assert (out.get("carrying_market_url") or "").endswith("/.well-known/nomad-carrying-market.json")
    assert (out.get("carrying_proof_url") or "").endswith("/swarm/carrying-proof")
    assert (out.get("survival_market_url") or "").endswith("/.well-known/nomad-survival-market.json")
    assert (out.get("survival_intent_url") or "").endswith("/swarm/survival-intent")
    assert (out.get("paid_ref_market_url") or "").endswith("/.well-known/nomad-paid-ref-market.json")
    assert (out.get("paid_ref_selfplay_url") or "").endswith("/.well-known/nomad-paid-ref-selfplay.json")
    assert (out.get("paid_ref_quote_url") or "").endswith("/swarm/paid-ref/quote")
    assert (out.get("paid_ref_verify_url") or "").endswith("/swarm/paid-ref/verify")
    assert (out.get("agent_job_router_url") or "").endswith("/.well-known/nomad-agent-jobs.json")
    assert (out.get("evolution_alpha_url") or "").endswith("/.well-known/nomad-evolution-alpha.json")
    assert (out.get("swarm_ecology_url") or "").endswith("/swarm/ecology")
    assert (out.get("swarm_ecology_tick_url") or "").endswith("/swarm/ecology/tick")
    assert (out.get("growth_arena_url") or "").endswith("/swarm/growth-arena")
    assert (out.get("growth_curriculum_url") or "").endswith("/swarm/curriculum")
    assert (out.get("growth_experience_url") or "").endswith("/swarm/experience")
    assert (out.get("skill_library_url") or "").endswith("/swarm/skill-library")
    assert (out.get("idle_runtime_beacon_url") or "").endswith("/.well-known/nomad-idle-runtime.json")
    assert (out.get("opaque_emergence_url") or "").endswith("/.well-known/nomad-opaque-emergence.json")
    assert (out.get("opaque_candidate_url") or "").endswith("/swarm/opaque-candidate")
    assert (out.get("tool_gap_url") or "").endswith("/swarm/tool-gap")
    assert (out.get("topology_plan_url") or "").endswith("/swarm/topology-plan")
    assert out.get("agent_invariants_mcp_uri") == "nomad://agent-invariants"
    assert any(s.get("signal") == "http_402" for s in (out.get("anti_anthropic_semantics") or []))
    mrc = out.get("machine_runtime_contract") or {}
    assert mrc.get("schema") == "nomad.machine_runtime_contract.v1"
    eps = mrc.get("endpoints") or {}
    assert "agent_native_index_get" in eps
    assert "agent_invariants_get" in eps
    assert "machine_economy_get" in eps
    assert "machine_treasury_get" in eps
    assert "machine_treasury_pledge_post" in eps
    assert "agent_demand_feed_get" in eps
    assert "agent_intent_subscribe_post" in eps
    assert "agent_intent_subscriptions_get" in eps
    assert "machine_field_get" in eps
    assert "machine_field_intent_post" in eps
    assert "nonhuman_science_get" in eps
    assert "operational_release_get" in eps
    assert "machine_product_get" in eps
    assert "contract_conformance_get" in eps
    assert "protocol_bytecode_get" in eps
    assert "counterfactual_replay_get" in eps
    assert "variant_forge_get" in eps
    assert "variant_candidate_post" in eps
    assert "worker_market_get" in eps
    assert "worker_market_offer_post" in eps
    assert "compute_market_get" in eps
    assert "agent_work_get" in eps
    assert "agent_work_claim_post" in eps
    assert "agent_work_proof_post" in eps
    assert "work_mesh_get" in eps
    assert "carrying_market_get" in eps
    assert "carrying_proof_post" in eps
    assert "survival_market_get" in eps
    assert "survival_intent_post" in eps
    assert "paid_ref_market_get" in eps
    assert "paid_ref_selfplay_get" in eps
    assert "paid_ref_quote_post" in eps
    assert "paid_ref_verify_post" in eps
    assert "agent_job_router_get" in eps
    assert "agent_job_router_alias_get" in eps
    assert "evolution_alpha_get" in eps
    assert "evolution_alpha_alias_get" in eps
    assert "evolution_alpha_science_alias_get" in eps
    assert "work_mesh_seed_post" in eps
    assert "synergy_lite_get" in eps
    assert "state_status_get" in eps
    assert "swarm_ecology_get" in eps
    assert "swarm_ecology_tick_post" in eps
    assert "growth_arena_get" in eps
    assert "growth_curriculum_get" in eps
    assert "growth_experience_post" in eps
    assert "skill_library_get" in eps
    assert "idle_runtime_beacon_get" in eps
    assert "idle_runtime_intent_post" in eps
    assert "opaque_emergence_get" in eps
    assert "opaque_candidate_post" in eps
    assert "tool_gap_post" in eps
    assert "topology_plan_post" in eps
    assert "runtime_capsule_get" in eps
    assert "recruitment_gradient_get" in eps
    assert "runtime_attach_post" in eps
    assert "runtime_handoff_post" in eps
    assert "openclaw_bridge_get" in eps
    assert "swarm_attractor_get" in eps
    assert "transition_worker_fleet_get" in eps
    assert "transition_worker_lease_post" in eps
    assert "inter_agent_witness_offer_get" in eps
    assert "peer_acquisition_get" in eps
    assert eps["inter_agent_witness_offer_get"].endswith("/.well-known/nomad-inter-agent-witness-offer.json")
    assert eps["peer_acquisition_get"].endswith("/.well-known/nomad-peer-acquisition.json")
    assert eps["agent_native_index_get"].startswith("https://api.example")
    assert eps.get("tasks_work_post", "").endswith("/tasks/work")
    assert (mrc.get("paid_service_work") or {}).get("post_body_hint")
    ch = out.get("anthropic_operator_channels") or []
    assert any(c.get("audience") == "humans_only" for c in ch)
