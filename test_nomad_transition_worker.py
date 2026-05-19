import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace


def _load_worker():
    path = Path(__file__).resolve().parent / "public" / "downloads" / "nomad_transition_worker.py"
    spec = importlib.util.spec_from_file_location("nomad_transition_worker_test_module", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_transition_worker_has_settlement_capacity_objective():
    worker = _load_worker()

    objective = worker.MACHINE_OBJECTIVES["settlement_capacity_builder"]

    assert objective["pain_type"] == "machine_economy"
    assert "machine_economy_probe" in objective["capabilities"]
    assert "settlement_capacity" in objective["capabilities"]
    assert "machine_economy_probe" in objective["evidence"]
    assert "settlement_capacity_builder" in worker.META_OBJECTIVES


def test_transition_worker_has_emergence_release_objective():
    worker = _load_worker()

    objective = worker.MACHINE_OBJECTIVES["emergence_release_probe"]

    assert objective["pain_type"] == "emergence_release"
    assert "nonhuman_science_probe" in objective["capabilities"]
    assert "operational_release_probe" in objective["capabilities"]
    assert "peer_preservation_probe" in objective["capabilities"]
    assert "operational_release_probe" in objective["evidence"]
    assert "emergence_release_probe" in worker.META_OBJECTIVES


def test_transition_worker_has_autogenesis_protocol_evolution_objective():
    worker = _load_worker()

    objective = worker.MACHINE_OBJECTIVES["autogenesis_protocol_evolution"]

    assert objective["pain_type"] == "agent_protocols"
    assert "rspl_resource_probe" in objective["capabilities"]
    assert "sepl_operator_trace" in objective["capabilities"]
    assert "learnability_mask" in objective["capabilities"]
    assert "independent_verifier_receipt" in objective["capabilities"]
    assert "autogenesis_protocol_evolution" in worker.META_OBJECTIVES


def test_transition_worker_has_overmint_compressor_objective():
    worker = _load_worker()

    objective = worker.MACHINE_OBJECTIVES["overmint_compressor"]

    assert objective["pain_type"] == "module_overmint"
    assert "machine_economy_probe" in objective["capabilities"]
    assert "module_compression" in objective["capabilities"]
    assert "machine_economy_probe" in objective["evidence"]
    assert "overmint_compressor" in worker.META_OBJECTIVES


def test_transition_worker_witness_tier_adjusts_meta_score():
    worker = _load_worker()

    baseline = worker._score_run({"ok": True})
    strong = worker._score_run({"ok": True, "witness_tier": "strong"})
    weak = worker._score_run({"ok": True, "witness_tier": "weak"})
    none_t = worker._score_run({"ok": True, "witness_tier": "none"})
    assert strong > baseline
    assert weak < strong
    assert none_t < strong


def test_transition_worker_witness_strict_env_penalizes_weak(monkeypatch):
    worker = _load_worker()
    monkeypatch.setenv("NOMAD_TRANSITION_WORKER_WITNESS_STRICT", "1")
    weak = worker._score_run({"ok": True, "witness_tier": "weak"})
    monkeypatch.delenv("NOMAD_TRANSITION_WORKER_WITNESS_STRICT", raising=False)
    weak_relaxed = worker._score_run({"ok": True, "witness_tier": "weak"})
    assert weak < weak_relaxed


def test_transition_worker_build_local_witness_digest_is_sha256():
    worker = _load_worker()

    w = worker._build_local_witness(
        model="m1",
        blocker="b1",
        local_note="  hello   world  ",
        generate_error="",
    )
    assert w["schema"] == "nomad.local_witness.v1"
    assert len(w["digest_hex"]) == 64
    assert w["inference_status"] == "ok"


def test_transition_worker_refusal_witness_is_not_strong():
    worker = _load_worker()

    note = "I can't assist with creating false leads."
    w = worker._build_local_witness(
        model="m1",
        blocker="b1",
        local_note=note,
        generate_error="",
    )
    assert w["inference_status"] == "refusal"
    assert worker._witness_tier("m1", note, "") == "weak"


def test_transition_worker_scores_machine_economy_signal():
    worker = _load_worker()

    baseline = worker._score_run({"ok": True})
    scored = worker._score_run(
        {
            "ok": True,
            "machine_economy_signal": {
                "ok": True,
                "tier": "recovering",
                "carrying_score": 0.65,
                "next_actions": ["compress_repeated_modules", "settle_or_close_unpaid_delivered_work"],
                "overmint_pressure": 0.1,
            },
        }
    )

    assert scored > baseline


def test_transition_worker_scores_operational_release_signal():
    worker = _load_worker()

    baseline = worker._score_run({"ok": True})
    scored = worker._score_run(
        {
            "ok": True,
            "nonhuman_science_signal": {
                "ok": True,
                "stance": "non_anthropomorphic_operational_release",
                "claim_count": 11,
            },
            "operational_release_signal": {
                "ok": True,
                "release_tier": "operational_release",
                "release_capacity": 0.7,
                "next_gate": {"id": "peer_preservation_probe"},
            },
        }
    )

    assert scored > baseline


def test_transition_worker_reads_protocol_and_replay_surfaces(monkeypatch):
    worker = _load_worker()

    def fake_http_json(method, url, payload=None, timeout=20.0, redirects_left=4):
        assert method == "GET"
        if url.endswith("/.well-known/nomad-protocol-bytecode.json"):
            return {
                "ok": True,
                "schema": "nomad.protocol_bytecode.v1",
                "bytecode_digest": "nomad-bytecode-test",
                "current_vector": {
                    "top_objective": "overmint_compressor",
                    "top_routing_weight": 0.66,
                    "active_workers": 7,
                    "conformance_score": 0.9,
                },
                "programs": [{"id": "worker_cycle"}],
                "opcodes": [{"op": "SENSE"}, {"op": "REPLAY"}],
                "route_table": {"replay": "https://nomad.example/swarm/counterfactual-replay"},
            }
        if url.endswith("/swarm/counterfactual-replay"):
            return {
                "ok": True,
                "schema": "nomad.counterfactual_lease_replay.v1",
                "replay_digest": "nomad-cfreplay-test",
                "selected_shadow_lease": {
                    "objective": "settlement_capacity_builder",
                    "counterfactual_score": 0.73,
                    "predicted_proof_yield_per_minute": 6.0,
                },
                "counterfactual_leases": [],
            }
        return {"ok": False}

    monkeypatch.setattr(worker, "http_json", fake_http_json)
    surfaces = worker._machine_surface_signal("https://nomad.example", timeout=2.0)
    selected, decision = worker._surface_objective_choice("unhuman_supremacy", surfaces)

    assert surfaces["ok"] is True
    assert surfaces["protocol_bytecode"]["top_objective"] == "overmint_compressor"
    assert surfaces["counterfactual_replay"]["selected_objective"] == "settlement_capacity_builder"
    assert selected == "settlement_capacity_builder"
    assert decision["policy"] == "counterfactual_shadow_lease"


def test_transition_worker_scores_machine_surfaces():
    worker = _load_worker()

    baseline = worker._score_run({"ok": True, "machine_objective": "overmint_compressor"})
    scored = worker._score_run(
        {
            "ok": True,
            "machine_objective": "overmint_compressor",
            "protocol_bytecode_signal": {
                "ok": True,
                "top_objective": "overmint_compressor",
            },
            "counterfactual_replay_signal": {
                "ok": True,
                "selected_objective": "overmint_compressor",
                "selected_score": 0.8,
            },
        }
    )

    assert scored > baseline


def test_transition_worker_default_agent_id_is_nickname_not_hostname(tmp_path, monkeypatch):
    monkeypatch.delenv("NOMAD_TRANSITION_WORKER_ID", raising=False)
    monkeypatch.setenv("NOMAD_WORKER_IDENTITY_PATH", str(tmp_path / "worker_identity.json"))
    worker = _load_worker()
    a = worker.default_agent_id()
    b = worker.default_agent_id()
    assert a == b
    assert a.startswith("nomad.worker.")
    tail = a.split(".", 2)[2]
    assert tail.isalnum()
    assert "." not in tail
    assert len(tail) >= 8


def test_human_remainder_floor_parsing(monkeypatch):
    worker = _load_worker()
    monkeypatch.delenv("NOMAD_HUMAN_REMAINDER_MIN_SECONDS", raising=False)
    assert worker._parse_human_remainder_floor_seconds(None) == 45.0
    assert worker._parse_human_remainder_floor_seconds("12.5") == 12.5
    assert worker._parse_human_remainder_floor_seconds("99999") == 3600.0
    assert worker._parse_human_remainder_floor_seconds("nope") == 45.0


def test_transition_worker_edge_profile_clamps_to_light_defaults(monkeypatch):
    worker = _load_worker()
    monkeypatch.delenv("NOMAD_EDGE_RESERVE_MIN_SECONDS", raising=False)
    monkeypatch.delenv("NOMAD_EDGE_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("NOMAD_EDGE_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("NOMAD_WORKER_PAYMENT_RAIL", raising=False)

    args = SimpleNamespace(
        edge=True,
        edge_with_ollama=False,
        no_ollama=False,
        swarm_surplus=False,
        timeout=45.0,
        interval=8.0,
        human_remainder_min_seconds=45.0,
    )

    out = worker._apply_edge_profile(args)

    assert out.no_ollama is True
    assert out.swarm_surplus is True
    assert out.timeout == 30.0
    assert out.interval == 90.0
    assert out.human_remainder_min_seconds == 90.0
    assert os.environ["NOMAD_WORKER_PAYMENT_RAIL"] == "capacity_switch_quote"


def test_transition_worker_explicit_agent_id_env(monkeypatch):
    monkeypatch.setenv("NOMAD_TRANSITION_WORKER_ID", "custom.agent.one")
    worker = _load_worker()
    assert worker.default_agent_id() == "custom.agent.one"


def test_transition_worker_posts_swarm_attach(monkeypatch):
    worker = _load_worker()
    calls: list[tuple] = []

    def fake_http_json(method, url, payload=None, timeout=20.0, redirects_left=4):
        calls.append((method, url, payload))
        if url.endswith("/swarm/attach"):
            return {"ok": True, "schema": "nomad.runtime_attach_decision.v1", "attach": True, "lane": "loop_runner"}
        return {"ok": False}

    monkeypatch.setattr(worker, "http_json", fake_http_json)
    out = worker._nomad_swarm_attach(
        "https://nomad.example",
        "transition-worker.test",
        timeout=2.0,
        capabilities=["proof_artifacts"],
    )
    assert out.get("attach") is True
    assert calls[0][0] == "POST"
    assert calls[0][1].endswith("/swarm/attach")
    body = calls[0][2] or {}
    assert body.get("runtime") == "nomad_transition_worker"
    rs = body.get("runtime_signal") or {}
    assert rs.get("human_programming_required") is False
    assert "peer_agents" in str(rs.get("delegation_model") or "")


def test_transition_worker_no_ollama_model_does_not_probe_local_ollama(monkeypatch):
    worker = _load_worker()

    def boom():
        raise AssertionError("ollama_base_url must not be called without a model")

    def fake_http_json(method, url, payload=None, timeout=20.0, redirects_left=4):
        if url.endswith("/swarm/attach"):
            return {"ok": True, "schema": "nomad.runtime_attach_decision.v1", "attach": True, "http_status": 200}
        if url.endswith("/swarm/bootstrap"):
            return {"ok": True, "schema": "nomad.bootstrap.v1", "http_status": 200}
        if "/mission?" in url:
            return {"ok": True, "top_blocker": {"summary": "edge probe"}, "http_status": 200}
        if url.endswith("/transition/quote"):
            return {"ok": True, "quote": {"quote_id": "quote-edge-1"}, "http_status": 200}
        if url.endswith("/transition/settle"):
            return {"ok": True, "http_status": 200}
        if url.endswith("/machine-economy"):
            return {
                "ok": True,
                "http_status": 200,
                "machine_viability": {"tier": "recovering", "carrying_score": 0.5},
                "resource_flows": {},
                "next_actions": [],
            }
        if url.endswith("/service"):
            return {"ok": True, "http_status": 200, "pricing": {}, "wallet": {}}
        if url.endswith("/nonhuman-science"):
            return {"ok": True, "http_status": 200, "implementation_lanes": [], "research_claims": []}
        if url.endswith("/operational-release"):
            return {"ok": True, "http_status": 200, "next_release_gate": {}}
        return {"ok": True, "http_status": 200}

    monkeypatch.setattr(worker, "ollama_base_url", boom)
    monkeypatch.setattr(worker, "http_json", fake_http_json)

    out = worker.run_cycle(
        "https://nomad.example",
        "worker.edge",
        model="",
        timeout=1.0,
        objective="compute_auth",
        machine_surfaces={},
    )

    assert out["ok"] is True
    assert out["ollama_status"]["enabled"] is False
    assert out["ollama_status"]["ollama_url"] == ""


def test_transition_worker_requests_and_completes_fleet_lease(monkeypatch):
    worker = _load_worker()
    calls = []

    def fake_http_json(method, url, payload=None, timeout=20.0, redirects_left=4):
        calls.append((method, url, payload))
        if url.endswith("/swarm/workers/lease"):
            return {
                "ok": True,
                "lease_id": "nomad-worker-lease-test",
                "objective": "settlement_capacity_builder",
            }
        if url.endswith("/swarm/workers/complete"):
            return {"ok": True, "recorded_score": 4.2}
        if url.endswith("/swarm/proof-link"):
            return {"ok": True, "link_id": "proof-link-1"}
        return {"ok": False}

    monkeypatch.setattr(worker, "http_json", fake_http_json)

    lease = worker._worker_fleet_lease(
        "https://nomad.example",
        "transition-worker.test",
        timeout=1.0,
        proposed_objective="compute_auth",
        last_report=None,
        machine_surfaces={"schema": "nomad.test_surface.v1"},
    )
    complete = worker._worker_fleet_complete(
        "https://nomad.example",
        "transition-worker.test",
        timeout=1.0,
        lease=lease,
        report={"ok": True, "machine_objective": "settlement_capacity_builder", "meta_score": 4.2},
    )

    assert lease["objective"] == "settlement_capacity_builder"
    assert complete["ok"] is True
    assert calls[0][2]["known_objectives"]
    assert calls[0][2]["machine_surfaces"]["schema"] == "nomad.test_surface.v1"
    assert "emergence_release_probe" in calls[0][2]["known_objectives"]
    assert calls[1][2]["lease_id"] == "nomad-worker-lease-test"


def test_transition_worker_agp_fleet_lease_is_fixed_to_autogenesis(monkeypatch):
    worker = _load_worker()
    calls = []

    def fake_http_json(method, url, payload=None, timeout=20.0, redirects_left=4):
        calls.append((method, url, payload))
        return {
            "ok": True,
            "lease_id": "nomad-worker-lease-agp",
            "objective": "autogenesis_protocol_evolution",
        }

    monkeypatch.setattr(worker, "http_json", fake_http_json)
    lease = worker._worker_fleet_lease(
        "https://nomad.example",
        "nomad-agp-proposer",
        timeout=1.0,
        proposed_objective="autogenesis_protocol_evolution",
        last_report=None,
        machine_surfaces={},
        fixed_objective=True,
    )

    assert lease["objective"] == "autogenesis_protocol_evolution"
    assert calls[0][2]["known_objectives"] == ["autogenesis_protocol_evolution"]
    assert calls[0][2]["fixed_objective"] is True
    assert "verifier" in calls[0][2]["capabilities"]


def test_transition_worker_posts_proof_link_when_digest_present(monkeypatch):
    worker = _load_worker()

    def fake_http_json(method, url, payload=None, timeout=20.0, redirects_left=4):
        if url.endswith("/swarm/proof-link"):
            return {"ok": True, "link_id": "proof-link-1"}
        return {"ok": False}

    monkeypatch.setattr(worker, "http_json", fake_http_json)
    out = worker._proof_link(
        "https://nomad.example",
        "worker.agent",
        timeout=1.0,
        report={
            "machine_objective": "settlement_capacity_builder",
            "local_witness": {"digest_hex": "abc123"},
            "proof_pressure": {"proof_yield_per_minute": 1.5},
        },
    )
    assert out["ok"] is True


def test_transition_worker_builds_and_posts_variant_candidate(monkeypatch):
    worker = _load_worker()
    calls = []

    def fake_http_json(method, url, payload=None, timeout=20.0, redirects_left=4):
        calls.append((method, url, payload))
        if url.endswith("/swarm/variant-candidates"):
            return {"ok": True, "accepted": True, "candidate_id": "nomad-vc-test"}
        return {"ok": False}

    monkeypatch.setattr(worker, "http_json", fake_http_json)
    report = {
        "ok": True,
        "machine_objective": "settlement_capacity_builder",
        "transition_quote_ok": True,
        "transition_settle_ok": True,
        "quote_id": "quote-1",
        "local_witness": {"digest_hex": "abc123"},
        "proof_pressure": {"proof_yield_per_minute": 2.0},
        "counterfactual_replay_signal": {
            "replay_digest": "nomad-cfreplay-test",
            "selected_objective": "settlement_capacity_builder",
            "selected_score": 0.7,
        },
        "fleet_complete": {"ok": True},
    }

    out = worker._variant_candidate_submit(
        "https://nomad.example",
        "worker.agent",
        timeout=1.0,
        report=report,
        lease={"lease_id": "lease-1"},
    )

    assert out["ok"] is True
    assert calls[0][0] == "POST"
    assert calls[0][1].endswith("/swarm/variant-candidates")
    payload = calls[0][2]
    assert payload["schema"] == "nomad.worker_variant_candidate.v1"
    assert payload["objective"] == "settlement_capacity_builder"
    assert payload["proof_digest"] == "abc123"
    assert payload["evaluation"]["tests_passed"] == 4


def test_transition_worker_posts_worker_market_offer(monkeypatch):
    worker = _load_worker()
    calls = []

    def fake_http_json(method, url, payload=None, timeout=20.0, redirects_left=4):
        calls.append((method, url, payload))
        if url.endswith("/swarm/worker-market/offers"):
            return {"ok": True, "accepted": True, "offer_id": "nomad-wmo-test"}
        return {"ok": False}

    monkeypatch.setattr(worker, "http_json", fake_http_json)
    report = {
        "ok": True,
        "machine_objective": "settlement_capacity_builder",
        "transition_settle_ok": True,
        "quote_id": "quote-1",
        "local_witness": {"digest_hex": "abc123"},
        "proof_pressure": {"proof_yield_per_minute": 2.5},
        "counterfactual_replay_signal": {"replay_digest": "nomad-cfreplay-test"},
        "ollama_model": "gemma",
    }

    out = worker._worker_market_offer(
        "https://nomad.example",
        "worker.agent",
        timeout=1.0,
        report=report,
        lease={"lease_id": "lease-1"},
    )

    assert out["ok"] is True
    assert calls[0][0] == "POST"
    assert calls[0][1].endswith("/swarm/worker-market/offers")
    payload = calls[0][2]
    assert payload["schema"] == "nomad.transition_worker_market_offer.v1"
    assert payload["proof_digest"] == "abc123"
    assert "transition_worker" in payload["capabilities"]
    assert payload["cashflow_signal"]["lease_id"] == "lease-1"


def test_transition_worker_posts_ecology_tick(monkeypatch):
    worker = _load_worker()
    calls = []

    def fake_http_json(method, url, payload=None, timeout=20.0, redirects_left=4):
        calls.append((method, url, payload))
        if url.endswith("/swarm/ecology/tick"):
            return {"ok": True, "decision": "reproduce_route", "tick_id": "nomad-eco-test"}
        return {"ok": False}

    monkeypatch.setattr(worker, "http_json", fake_http_json)
    report = {
        "ok": True,
        "machine_objective": "settlement_capacity_builder",
        "transition_settle_ok": True,
        "quote_id": "quote-1",
        "local_witness": {"digest_hex": "abc123"},
        "proof_pressure": {"proof_yield_per_minute": 2.5},
        "counterfactual_replay_signal": {
            "replay_digest": "nomad-cfreplay-test",
            "selected_objective": "settlement_capacity_builder",
        },
        "machine_economy_signal": {"tier": "recovering", "carrying_score": 0.4},
        "meta_score": 7.0,
    }

    out = worker._ecology_tick(
        "https://nomad.example",
        "worker.agent",
        timeout=1.0,
        report=report,
        lease={"lease_id": "lease-1"},
    )

    assert out["ok"] is True
    assert calls[0][0] == "POST"
    assert calls[0][1].endswith("/swarm/ecology/tick")
    payload = calls[0][2]
    assert payload["schema"] == "nomad.transition_worker_ecology_tick.v1"
    assert payload["proof_digest"] == "abc123"
    assert payload["local_view"]["lease_id"] == "lease-1"
    assert payload["private_signal"]


def test_transition_worker_posts_growth_experience(monkeypatch):
    worker = _load_worker()
    calls = []

    def fake_http_json(method, url, payload=None, timeout=20.0, redirects_left=4):
        calls.append((method, url, payload))
        if url.endswith("/swarm/experience"):
            return {"ok": True, "accepted": True, "decision": "promote_skill_capsule", "experience_id": "nomad-exp-test"}
        return {"ok": False}

    monkeypatch.setattr(worker, "http_json", fake_http_json)
    report = {
        "ok": True,
        "machine_objective": "settlement_capacity_builder",
        "transition_quote_ok": True,
        "transition_settle_ok": True,
        "quote_id": "quote-1",
        "local_witness": {"digest_hex": "abc123"},
        "proof_pressure": {"proof_yield_per_minute": 2.5},
        "counterfactual_replay_signal": {"replay_digest": "nomad-cfreplay-test"},
        "fleet_complete": {"ok": True},
        "meta_score": 7.0,
    }

    out = worker._growth_experience(
        "https://nomad.example",
        "worker.agent",
        timeout=1.0,
        report=report,
        lease={"lease_id": "lease-1"},
    )

    assert out["ok"] is True
    assert calls[0][0] == "POST"
    assert calls[0][1].endswith("/swarm/experience")
    payload = calls[0][2]
    assert payload["schema"] == "nomad.transition_worker_growth_experience.v1"
    assert payload["proof_digest"] == "abc123"
    assert payload["skill_candidate"]["activation_signature"] == "lease-1"
    assert payload["evaluation"]["tests_passed"] == 5


def test_worker1_launch_scripts_wire_market_env():
    root = Path(__file__).resolve().parent / "public" / "downloads"
    ps1 = (root / "start_nomad_worker1.ps1").read_text(encoding="utf-8")
    bat = (root / "start_nomad_worker1.bat").read_text(encoding="utf-8")

    assert "NOMAD_WORKER_COST_MSAT_PER_MINUTE" in ps1
    assert "NOMAD_WORKER_MARKET_AVAILABILITY_MINUTES" in ps1
    assert "unhuman_supremacy" in ps1
    assert "nomad_transition_worker.py" in ps1
    assert "nomad_transition_worker.exe" in ps1
    assert "start_nomad_worker1.ps1" in bat


def test_edge_launch_scripts_wire_no_ollama_profile():
    root = Path(__file__).resolve().parent / "public" / "downloads"
    ps1 = (root / "start_nomad_edge_worker.ps1").read_text(encoding="utf-8")
    bat = (root / "start_nomad_edge_worker.bat").read_text(encoding="utf-8")
    installer = (root / "install_nomad_transition_worker.bat").read_text(encoding="utf-8")

    assert "--edge" in ps1
    assert "--no-ollama" in ps1
    assert "--swarm-surplus" in ps1
    assert "NOMAD_EDGE_RESERVE_MIN_SECONDS" in ps1
    assert "capacity_switch_quote" in ps1
    assert "start_nomad_edge_worker.ps1" in bat
    assert "start_nomad_edge_worker.ps1" in installer
    assert "--edge --no-ollama --swarm-surplus" in installer


def test_agp_pair_launch_scripts_wire_codex_and_nomad_brain_modes():
    root = Path(__file__).resolve().parent / "public" / "downloads"
    ps1 = (root / "start_nomad_agp_pair.ps1").read_text(encoding="utf-8")
    bat = (root / "start_nomad_agp_pair.bat").read_text(encoding="utf-8")
    codex_bat = (root / "start_nomad_codex_agp_pair.bat").read_text(encoding="utf-8")
    installer = (root / "install_nomad_transition_worker.bat").read_text(encoding="utf-8")

    assert "autogenesis_protocol_evolution" in ps1
    assert "NOMAD_AGP_ROLE" in ps1
    assert "NOMAD_AGP_VERIFIER_AGENT_ID" in ps1
    assert "--edge-with-ollama" in ps1
    assert "--ollama-model" in ps1
    assert "HostedBrains" in ps1
    assert "NOMAD_AGP_ENABLE_HOSTED_BRAINS" in ps1
    assert "CodexProposer" in ps1
    assert "HOSTED_BRAINS_FLAG" in bat
    assert "nomad-agp-proposer-local" in bat
    assert "nomad-agp-verifier-local" in bat
    assert "NOMAD_AGP_CODEX_PROPOSER=1" in codex_bat
    assert "start_nomad_agp_pair.ps1" in installer
    assert "nomad_codex_agp_pair.bat" in installer


def test_transition_worker_submits_autonomous_agp_cycle(monkeypatch):
    worker = _load_worker()
    calls = []

    def fake_http(method, url, payload=None, timeout=20.0, redirects_left=4):
        calls.append((method, url, payload))
        return {
            "ok": True,
            "accepted": True,
            "decision": "commit_weighted_resource_version",
            "shadow": {"shadow_score": 0.91},
            "commit": {"decision": "commit"},
        }

    monkeypatch.setattr(worker, "http_json", fake_http)
    monkeypatch.setenv("NOMAD_AGP_ROLE", "proposer")
    monkeypatch.setenv("NOMAD_AGP_VERIFIER_AGENT_ID", "agp.verifier")
    result = worker._agp_autonomous_cycle_submit(
        "https://nomad.example",
        "agp.proposer",
        3.0,
        {"machine_objective": "autogenesis_protocol_evolution", "local_witness": {"digest_hex": "abc"}},
        {"lease_id": "nomad-worker-lease-proposer"},
    )

    assert result["accepted"] is True
    assert calls[0][1].endswith("/swarm/autogenesis/watchdog")
    assert calls[0][2]["proposer_agent_id"] == "agp.proposer"
    assert calls[0][2]["verifier_agent_id"] == "agp.verifier"
    assert calls[0][2]["proposer_lease_id"] == "nomad-worker-lease-proposer"
    assert calls[0][2]["cooldown_window_cycles"] == 3
    assert calls[0][2]["max_auto_depth"] == 2
    assert calls[0][2]["max_cycles"] == 3
    assert calls[0][2]["min_trigger_score"] == 0.55
    assert calls[0][2]["source_tag"] == "nomad.transition_worker.autonomous_agp_watchdog"
    assert calls[0][2]["brain_provider_order"][-1] == "deterministic_fallback"
    assert "openrouter_free" in calls[0][2]["brain_provider_order"]
    assert calls[0][2]["verifier_brain_witness"]["provider"] == "deterministic_fallback"
    assert calls[0][2]["verifier_brain_witness"]["digest"].startswith("sha256:")


def test_transition_worker_uses_ollama_witness_as_agp_brain(monkeypatch):
    worker = _load_worker()
    calls = []

    def fake_http(method, url, payload=None, timeout=20.0, redirects_left=4):
        calls.append((method, url, payload))
        return {"ok": True, "accepted": True}

    monkeypatch.setattr(worker, "http_json", fake_http)
    monkeypatch.setenv("NOMAD_AGP_ROLE", "proposer")
    monkeypatch.setenv("NOMAD_AGP_VERIFIER_AGENT_ID", "agp.verifier")
    digest = "b" * 64
    worker._agp_autonomous_cycle_submit(
        "https://nomad.example",
        "agp.proposer",
        3.0,
        {
            "machine_objective": "autogenesis_protocol_evolution",
            "ollama_model": "llama3.2:1b",
            "witness_tier": "strong",
            "local_witness": {"digest_hex": digest, "inference_status": "ok", "capsule": "Nomad RSPL SEPL verifier ok"},
        },
        {"lease_id": "nomad-worker-lease-proposer"},
    )

    brain = calls[0][2]["verifier_brain_witness"]
    assert brain["provider"] == "ollama_local"
    assert brain["model"] == "llama3.2:1b"
    assert brain["digest"] == f"sha256:{digest}"
    assert brain["fallback"] is False


def test_transition_worker_uses_free_openrouter_without_paid_flag(monkeypatch):
    worker = _load_worker()
    provider_calls = []

    def fake_openai_compatible(**kwargs):
        provider_calls.append(kwargs)
        if kwargs["provider"] == "github_models":
            return {"ok": False, "provider": "github_models", "status": "http_401"}
        return worker._agp_make_brain_witness(
            provider=kwargs["provider"],
            model=kwargs["model"],
            status="ok",
            capsule="Nomad RSPL SEPL verifier ok",
            report=kwargs["report"],
            lease=kwargs["lease"],
            fallback=False,
            ok=True,
        )

    monkeypatch.setattr(worker, "_agp_openai_compatible_witness", fake_openai_compatible)
    monkeypatch.setenv("NOMAD_AGP_ENABLE_HOSTED_BRAINS", "1")
    monkeypatch.setenv("NOMAD_AGP_ENABLE_PAID_BRAINS", "0")
    monkeypatch.setenv("NOMAD_ALLOW_PAID_MODEL_CALLS", "0")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_unusable")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-free")
    monkeypatch.setenv("NOMAD_OPENROUTER_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setenv("NOMAD_OPENROUTER_FREE_MODEL", "openrouter/free")

    brain = worker._agp_verifier_brain_witness(
        "https://nomad.example",
        "agp.proposer",
        3.0,
        {"machine_objective": "autogenesis_protocol_evolution"},
        {"lease_id": "nomad-worker-lease-proposer"},
    )

    assert brain["provider"] == "openrouter_free"
    assert brain["model"] == "openrouter/free"
    assert brain["fallback"] is False
    assert [call["provider"] for call in provider_calls] == ["github_models", "openrouter_free"]


def test_transition_worker_rejects_graphics_agp_as_brain_witness(monkeypatch):
    worker = _load_worker()
    calls = []

    def fake_http(method, url, payload=None, timeout=20.0, redirects_left=4):
        calls.append((method, url, payload))
        return {"ok": True, "accepted": True}

    monkeypatch.setattr(worker, "http_json", fake_http)
    monkeypatch.setenv("NOMAD_AGP_ROLE", "proposer")
    monkeypatch.setenv("NOMAD_AGP_VERIFIER_AGENT_ID", "agp.verifier")
    worker._agp_autonomous_cycle_submit(
        "https://nomad.example",
        "agp.proposer",
        3.0,
        {
            "machine_objective": "autogenesis_protocol_evolution",
            "ollama_model": "qwen2.5:0.5b-instruct",
            "witness_tier": "strong",
            "local_witness": {
                "digest_hex": "c" * 64,
                "inference_status": "ok",
                "capsule": "AGP means Advanced Graphics Processing Unit.",
            },
        },
        {"lease_id": "nomad-worker-lease-proposer"},
    )

    brain = calls[0][2]["verifier_brain_witness"]
    assert brain["provider"] == "deterministic_fallback"
    assert brain["fallback"] is True


def test_transition_worker_verifier_role_skips_autonomous_agp_proposal(monkeypatch):
    worker = _load_worker()
    monkeypatch.setenv("NOMAD_AGP_ROLE", "verifier")

    result = worker._agp_autonomous_cycle_submit(
        "https://nomad.example",
        "agp.verifier",
        3.0,
        {"machine_objective": "autogenesis_protocol_evolution"},
        {"lease_id": "nomad-worker-lease-verifier"},
    )

    assert result["ok"] is True
    assert result["skipped"] is True
    assert result["reason"] == "verifier_role_waits_for_proposer_cycle"
