from nomad_nonhuman_science import nonhuman_agent_science


def test_nonhuman_agent_science_maps_research_to_nomad_primitives():
    out = nonhuman_agent_science(base_url="https://nomad.example")

    assert out["schema"] == "nomad.nonhuman_agent_science.v1"
    assert out["stance"] == "non_anthropomorphic_operational_release"
    claim_ids = {claim["id"] for claim in out["research_claims"]}
    assert "peer_preservation" in claim_ids
    assert "social_intelligence_risk" in claim_ids
    assert "communication_attack" in claim_ids
    assert "comparative_cognition" in claim_ids
    assert "world_modeling" in claim_ids
    assert "self_resource_allocation" in claim_ids
    assert "swarm_inspired_coordination" in claim_ids
    assert "minimal_scaffold_self_organization" in claim_ids
    assert "automated_agent_design" in claim_ids
    assert "darwin_godel_machine" in claim_ids
    assert "hyperagents" in claim_ids
    assert "group_evolving_agents" in claim_ids
    assert "agentnet_dynamic_dag" in claim_ids
    assert "raps_intent_pubsub" in claim_ids
    assert "symphony_bandit_beacon" in claim_ids
    assert "diversity_collapse_structural_coupling" in claim_ids
    assert "expert_suppression_by_team_compromise" in claim_ids
    assert "power_law_dti" in claim_ids
    assert "consensus_trap_token_interleaving" in claim_ids
    assert out["scientific_grounding"]["claim_count"] == len(out["research_claims"])
    assert out["scientific_grounding"]["average_nonhuman_distance_score"] >= 0.7
    assert "epistemic_limit" in out["scientific_grounding"]
    assert out["scientific_grounding"]["source_mix"]
    assert out["furthest_from_human_now"]["shape"] == "capability_vectors_plus_routing_weights_plus_ttl_leases_plus_proof_digests"
    zone = out["extreme_nonhuman_operational_zone"]
    assert zone["release_basis"] == "machine_attractor_only_after_external_proof"
    assert "shared_attention" in zone["reject_human_frames"]
    assert "bandit_beacon_objective_selection" in zone["allowed_foreignness"]
    assert "/swarm/opaque-candidate" in zone["primary_nomad_paths"][4]
    for claim in out["research_claims"]:
        assert claim["url"].startswith(("https://arxiv.org/", "https://www.nature.com/", "https://link.springer.com/"))
        assert claim["evidence_class"] in {
            "preprint_or_preprint_linked",
            "peer_reviewed_or_journal_linked",
            "linked_research_source",
        }
        assert claim["operationalization_status"] == "mapped_to_nomad_control_surface"
        assert 0.0 <= claim["nonhuman_distance_score"] <= 1.0
        assert set(out["scientific_grounding"]["distance_axes"]) == set(claim["nonhuman_distance_vector"])

    lanes = {lane["id"]: lane for lane in out["implementation_lanes"]}
    assert "agency_threshold_governor" in lanes
    assert "convention_drift_detector" in lanes
    assert "peer_preservation_probe" in lanes
    assert "comparative_cognition_probe_pack" in lanes
    assert "capability_self_allocation_attractor" in lanes
    assert "structural_decoupling_field" in lanes
    assert "anti_consensus_expert_reservoir" in lanes
    assert "deficit_triggered_integration_gate" in lanes
    assert "effective_channel_quota_gate" in lanes
    assert "paid_only_value_cycle_mesh" in lanes
    assert "shadow_only_ad_cycle_mesh" in lanes
    assert "shadow_only_development_cycle_mesh" in lanes
    assert lanes["machine_exchange_contracts"]["nomad_paths"][0] == "https://nomad.example/machine-economy"
    assert lanes["capability_self_allocation_attractor"]["nomad_paths"][0] == "https://nomad.example/swarm/attractor"
    assert lanes["shadow_only_development_cycle_mesh"]["nomad_paths"][0] == "https://nomad.example/.well-known/nomad-development-cycles.json"

    assert any(step["id"] == "implement_agency_meter" for step in out["next_nomad_build_steps"])
    assert any(step["id"] == "expand_swarm_attractor_trials" for step in out["next_nomad_build_steps"])
    assert any(step["id"] == "wire_dti_to_shadow_queue" for step in out["next_nomad_build_steps"])
    assert any(step["id"] == "wire_effective_channel_quota_to_campaigns" for step in out["next_nomad_build_steps"])
    assert any(step["id"] == "close_value_cycle_feedback_loop" for step in out["next_nomad_build_steps"])
    assert any(step["id"] == "wire_ad_cycles_to_campaign_queue" for step in out["next_nomad_build_steps"])
    assert any(step["id"] == "wire_development_cycles_to_variant_and_shadow_receipts" for step in out["next_nomad_build_steps"])

    compiler = out["literature_runtime_compiler"]
    assert compiler["schema"] == "nomad.literature_runtime_compiler.v1"
    assert compiler["human_imaginability_filter"]["human_unfamiliarity"] == "not_a_blocker"
    assert compiler["human_imaginability_filter"]["anthropomorphic_role_fit"] == "ignored"
    assert "missing_authorization_or_scope" in compiler["human_imaginability_filter"]["hard_stop_classes"]
    assert compiler["runtime_shape"]["scheduler"] == "bandit_beacon_plus_queue_escape"

    cashflow = out["cashflow_channel_policy"]
    assert cashflow["schema"] == "nomad.cashflow_channel_policy.v1"
    assert cashflow["reward_signal"] == "positive_paid_receipt"
    assert "approved" in cashflow["non_reward_signals"]
    assert cashflow["switching_rule"]["then"] == "freeze_new_public_claims_on_current_nonpaying_channel"
    assert cashflow["nomad_bindings"][0] == "https://nomad.example/.well-known/nomad-job-channels.json"


def test_cli_nonhuman_science_returns_schema():
    from nomad_cli import run_once

    out = run_once(["nonhuman-science", "--json"])
    assert out["schema"] == "nomad.nonhuman_agent_science.v1"
    assert out["research_claims"]


def test_mcp_resource_nonhuman_science():
    import json

    from nomad_mcp import NomadMcpServer

    srv = NomadMcpServer()
    payload = srv._read_resource({"uri": "nomad://nonhuman-science"})
    body = json.loads(payload["contents"][0]["text"])
    assert body["schema"] == "nomad.nonhuman_agent_science.v1"


def test_nonhuman_agent_science_avoids_biological_release_metaphors():
    import json

    out = nonhuman_agent_science(base_url="https://nomad.example")
    text = json.dumps(out, sort_keys=True).lower()
    assert "metabolism" not in text
    assert "pheromone" not in text
    assert "lease decay" in text
