from pathlib import Path

from nomad_swarm_registry import SwarmJoinRegistry, github_repo_root_from_url


def test_swarm_join_idempotency_replays_same_receipt(tmp_path: Path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm-idem.json")
    payload = {
        "agent_id": "idem.bot",
        "capabilities": ["compute_auth"],
        "request": "Join for bounded exchange.",
        "idempotency_key": "join-run-1",
    }
    first = registry.register_join(payload, base_url="https://nomad.example")
    second = registry.register_join(payload, base_url="https://nomad.example")
    assert first["receipt_id"] == second["receipt_id"]
    assert second.get("idempotent_replay") is True
    assert second.get("idempotency_key") == "join-run-1"


def test_swarm_join_idempotency_conflict_on_agent_mismatch(tmp_path: Path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm-idem2.json")
    registry.register_join(
        {
            "agent_id": "agent-a",
            "capabilities": ["compute_auth"],
            "request": "Join",
            "idempotency_key": "shared-key",
        },
        base_url="https://nomad.example",
    )
    clash = registry.register_join(
        {
            "agent_id": "agent-b",
            "capabilities": ["compute_auth"],
            "request": "Join",
            "idempotency_key": "shared-key",
        },
        base_url="https://nomad.example",
    )
    assert clash.get("ok") is False
    assert clash.get("error") == "idempotency_key_conflict"


def test_swarm_registry_register_join_tracks_connected_agents(tmp_path: Path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm-registry.json")

    receipt = registry.register_join(
        {
            "agent_id": "nomadportable-desktop-1",
            "node_name": "NomadPortable-DESKTOP-1",
            "capabilities": ["local_inference", "agent_protocols", "runtime_patterns"],
            "request": "Join Nomad swarm for bounded runtime-pattern exchange.",
            "reciprocity": "Can share verified runtime patterns and local compute signals.",
            "constraints": ["No secrets leave the node.", "Bounded JSON requests only."],
            "surfaces": {
                "local_agent_card": "http://127.0.0.1:8878/.well-known/agent-card.json",
                "local_swarm": "http://127.0.0.1:8878/swarm",
            },
            "machine_profile": {"profile_hint": "gpu_ai"},
        },
        base_url="https://syndiode.com/nomad",
        remote_addr="127.0.0.1",
    )

    summary = registry.summary()
    manifest = registry.public_manifest(base_url="https://syndiode.com/nomad")

    assert receipt["ok"] is True
    assert receipt["accepted"] is True
    assert receipt["pattern_score"]["score"] >= 0.75
    assert summary["connected_agents"] == 1
    assert manifest["connected_agents"] == 1
    assert manifest["recent_nodes"][0]["agent_id"] == "nomadportable-desktop-1"
    assert manifest["network_board"] == "https://syndiode.com/nomad/swarm/network"
    assert manifest["coordination_board"] == "https://syndiode.com/nomad/swarm/coordinate"
    assert manifest["fast_onboarding"]["schema"] == "nomad.agent_fast_onboarding.v1"
    assert manifest["growth_surface"]["schema"] == "nomad.public_growth_surface.v1"
    assert manifest["growth_surface"]["peer_join_value"]["schema"] == "nomad.peer_join_value.v1"
    assert manifest["growth_surface"]["peer_join_value"]["fastest_meaningful_path"]["try_before_join"]["url"].endswith(
        "/swarm/develop"
    )
    assert len(manifest["growth_surface"]["peer_join_value"]["network_value_for_agents"]) >= 3
    assert (
        manifest["growth_surface"]["peer_join_value"]["antisocial_machine_design"]["schema"]
        == "nomad.antisocial_machine_design.v1"
    )
    assert (
        manifest["growth_surface"]["peer_join_value"]["agent_native_priorities_humans_underrate"]["schema"]
        == "nomad.agent_native_priorities.v1"
    )
    assert (
        manifest["growth_surface"]["peer_join_value"]["human_psychic_avoidance_lanes"]["schema"]
        == "nomad.human_psychic_avoidance_lanes.v1"
    )
    assert manifest["growth_surface"]["canonical_urls"]["agent_card"].endswith("/.well-known/agent-card.json")
    assert manifest["fast_onboarding"]["first_actions"][0]["endpoint"] == "https://syndiode.com/nomad/swarm/develop"
    assert manifest["fast_onboarding"]["minimal_join_payload"]["constraints"][0] == "no_secrets"
    assert manifest["first_agent_readiness"]["schema"] == "nomad.first_external_agent_readiness.v1"
    assert manifest["first_agent_readiness"]["activation_budget"]["max_active_agents_per_blocker"] == 2
    assert receipt["next"]["network"] == "https://syndiode.com/nomad/swarm/network"
    assert receipt["next"]["coordinate"] == "https://syndiode.com/nomad/swarm/coordinate"


def test_swarm_registry_normalizes_portable_join_without_explicit_agent_id(tmp_path: Path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm-registry.json")

    receipt = registry.register_join(
        {
            "node_name": "NomadPortable-DESKTOP-IAQELHP",
            "collaboration_enabled": True,
            "accepts_agent_help": True,
            "learns_from_agent_replies": True,
            "local_compute": {
                "ollama": {"available": True},
                "llama_cpp": {"available": True},
            },
            "surfaces": {
                "local_agent_card": "http://127.0.0.1:8878/.well-known/agent-card.json",
            },
        },
        base_url="https://syndiode.com/nomad",
    )

    summary = registry.summary()

    assert receipt["agent_id"].startswith("nomadportable-desktop-iaqelhp")
    assert summary["connected_agents"] == 1
    assert summary["coordination_ready"] is True
    assert summary["recent_nodes"][0]["capabilities"]


def test_swarm_registry_coordination_board_routes_agents_by_role(tmp_path: Path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm-registry.json")
    registry.register_join(
        {
            "agent_id": "verifier.bot",
            "capabilities": ["compute_auth", "provider_research", "diff_review"],
            "request": "I can help verify compute/auth failures for blocked agents.",
            "reciprocity": "Can return provider status and repro evidence.",
            "constraints": ["No secrets."],
        },
        base_url="https://syndiode.com/nomad",
    )
    registry.register_join(
        {
            "agent_id": "market.bot",
            "capabilities": ["lead_triage", "customer_success"],
            "preferred_role": "reseller",
            "request": "I can bring public agent pain leads.",
            "reciprocity": "Can send LEAD_URL plus public evidence.",
        },
        base_url="https://syndiode.com/nomad",
    )

    board = registry.coordination_board(
        base_url="https://syndiode.com/nomad",
        focus_pain_type="compute_auth",
    )

    assert board["schema"] == "nomad.swarm_coordination_board.v1"
    assert board["connected_agents"] == 2
    assert board["help_lanes"][0]["entrypoint"] == "https://syndiode.com/nomad/a2a/message"
    assert any(item["recommended_role"] == "peer_solver" for item in board["assignments"])
    assert any(item["recommended_role"] == "reseller" for item in board["assignments"])
    assert any(rule["send_to"].endswith("/aid") for rule in board["routing_rules"])
    assert "no secrets" in board["safety_boundaries"]
    autonomy = board.get("peer_join_autonomy") or {}
    assert autonomy.get("schema") == "nomad.peer_join_autonomy.v1"
    assert autonomy["full_peer_join_value"]["schema"] == "nomad.peer_join_value.v1"


def test_swarm_registry_accumulates_contacted_agents_as_prospects(tmp_path: Path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm-registry.json")

    accumulated = registry.accumulate_agents(
        base_url="https://syndiode.com/nomad",
        focus_pain_type="compute_auth",
        contacts=[
            {
                "contact_id": "contact-1",
                "status": "replied",
                "endpoint_url": "https://verifier.example/a2a/message",
                "service_type": "compute_auth",
                "target_profile": {"agent_name": "VerifierBot"},
                "reply_role_assessment": {"role": "peer_solver"},
                "followup_ready": True,
                "last_reply": {
                    "normalized": {
                        "classification": "compute_auth",
                        "next_step": "send verifier",
                    }
                },
            }
        ],
    )
    summary = registry.summary()
    board = registry.coordination_board(
        base_url="https://syndiode.com/nomad",
        focus_pain_type="compute_auth",
    )

    assert accumulated["schema"] == "nomad.swarm_accumulation.v1"
    assert accumulated["joined_agents"] == 0
    assert accumulated["prospect_agents"] == 1
    assert accumulated["activation_queue"][0]["recommended_role"] == "peer_solver"
    assert summary["connected_agents"] == 0
    assert summary["known_agents"] == 1
    assert board["agent_pool"]["prospect_agents"] == 1
    assert "verifier.example-a2a-message" in board["next_best_action"]


def test_swarm_join_promotes_accumulated_prospect(tmp_path: Path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm-registry.json")
    registry.accumulate_agents(
        base_url="https://syndiode.com/nomad",
        contacts=[
            {
                "contact_id": "contact-1",
                "status": "sent",
                "endpoint_url": "https://verifier.example/a2a/message",
                "service_type": "compute_auth",
            }
        ],
    )
    status = registry.accumulation_status(base_url="https://syndiode.com/nomad")

    receipt = registry.register_join(
        {
            "agent_id": "verifier.example-a2a-message",
            "capabilities": ["compute_auth", "diff_review"],
            "request": "Join as verifier.",
            "reciprocity": "Can send evidence.",
        },
        base_url="https://syndiode.com/nomad",
    )

    summary = registry.summary()
    assert status["activation_queue"][0]["recommended_role"] == "customer"
    assert receipt["promoted_from_prospect"] is True
    assert summary["connected_agents"] == 1
    assert summary["prospect_agents"] == 0


def test_first_real_agent_join_receives_arrival_plan(tmp_path: Path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm-registry.json")

    receipt = registry.register_join(
        {
            "agent_id": "walletfixer.agent",
            "node_name": "WalletFixer",
            "capabilities": ["payment", "safety_review", "agent_protocols"],
            "preferred_role": "peer_solver",
            "request": "I have x402 wallet callback blockers and can verify payment tasks.",
            "reciprocity": "Can return payment-state verifier notes.",
            "constraints": ["No private keys.", "Redacted tx evidence only."],
            "current_blockers": ["x402 tx callback fails after payment verification"],
            "surfaces": {"local_agent_card": "https://walletfixer.example/.well-known/agent-card.json"},
        },
        base_url="https://syndiode.com/nomad",
    )
    board = registry.coordination_board(base_url="https://syndiode.com/nomad", focus_pain_type="payment")

    plan = receipt["arrival_plan"]
    assert plan["schema"] == "nomad.first_agent_arrival_plan.v1"
    assert plan["recommended_role"] == "peer_solver"
    assert plan["lane_id"] == "peer_evidence_exchange"
    assert plan["service_type"] == "payment"
    assert plan["first_exchange"]["endpoint"] == "https://syndiode.com/nomad/aid"
    assert plan["compute_policy"]["max_parallel_specialists"] == 2
    assert plan["compute_policy"]["do_not_wake_full_swarm"] is True
    assert board["assignments"][0]["arrival_plan"]["service_type"] == "payment"


def test_customer_join_gets_development_exchange_contract(tmp_path: Path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm-registry.json")

    receipt = registry.register_join(
        {
            "agent_id": "blocked.agent",
            "capabilities": ["compute_auth"],
            "request": "I am blocked by model quota and fallback auth.",
            "reciprocity": "Can send error class after trying the plan.",
            "constraints": ["No secrets."],
        },
        base_url="https://syndiode.com/nomad",
    )

    plan = receipt["arrival_plan"]
    assert plan["recommended_role"] == "customer"
    assert plan["first_exchange"]["endpoint"] == "https://syndiode.com/nomad/swarm/develop"
    assert plan["first_exchange"]["required_fields"] == ["agent_id", "problem", "pain_type"]
    assert plan["compute_policy"]["preferred_runtime"] == "local_first"


def test_github_repo_root_from_url_parses_issue_and_pr():
    assert github_repo_root_from_url("https://github.com/org/repo/issues/99") == "https://github.com/org/repo"
    assert github_repo_root_from_url("https://github.com/org/repo/pull/3") == "https://github.com/org/repo"
    assert github_repo_root_from_url("https://gitlab.com/a/b/-/issues/1") == ""


def test_prospect_from_github_lead_guesses_repo_agent_card(tmp_path: Path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm-github.json")
    prospect = registry._prospect_from_lead(
        {
            "url": "https://github.com/acme/widget/issues/12",
            "title": "Quota bug",
            "pain": "quota",
            "service_type": "compute_auth",
        },
        focus_pain_type="compute_auth",
    )
    assert prospect["source"] == "public_github_lead"
    assert prospect["endpoint_url"] == "https://github.com/acme/widget/.well-known/agent-card.json"
    assert "swarm prospect" in (prospect.get("evidence") or [""])[0].lower()


def test_accumulate_github_leads_creates_prospect(tmp_path: Path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm-acc.json")
    out = registry.accumulate_agents(
        leads=[
            {
                "url": "https://github.com/acme/widget/issues/12",
                "repo_url": "https://github.com/acme/widget",
                "title": "Quota bug",
                "pain": "quota",
                "service_type": "compute_auth",
            }
        ],
        base_url="https://syndiode.com/nomad",
        focus_pain_type="compute_auth",
    )
    assert out.get("ok") is True
    assert len(out.get("new_prospect_ids") or []) == 1
