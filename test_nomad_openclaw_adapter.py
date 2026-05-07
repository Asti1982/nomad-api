import importlib.util
from pathlib import Path


def _load_adapter():
    path = Path(__file__).resolve().parent / "public" / "downloads" / "nomad_openclaw_adapter.py"
    spec = importlib.util.spec_from_file_location("nomad_openclaw_adapter_test_module", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_openclaw_adapter_cycle_posts_lease_and_complete(monkeypatch):
    adapter = _load_adapter()
    calls = []

    def fake_http_json(method, url, payload=None, timeout=20.0):
        calls.append((method, url, payload))
        if url.endswith("/swarm/workers/lease"):
            return {"ok": True, "lease_id": "lease-openclaw-1", "objective": "proof_pressure_engine"}
        if url.endswith("/swarm/workers/complete"):
            return {"ok": True, "recorded_score": 3.4}
        return {"ok": False}

    monkeypatch.setattr(adapter, "http_json", fake_http_json)
    out = adapter.run_cycle(
        base_url="https://nomad.example",
        agent_id="openclaw.agent",
        capabilities=["agent_protocols"],
        timeout=5.0,
        objective="unhuman_supremacy",
        last_report=None,
        machine_surfaces={"schema": "nomad.openclaw_machine_surface_signal.v1"},
    )
    assert out["ok"] is True
    assert out["phase"] == "complete"
    assert out["lease_id"] == "lease-openclaw-1"
    assert calls[0][1].endswith("/swarm/workers/lease")
    assert calls[0][2]["machine_surfaces"]["schema"] == "nomad.openclaw_machine_surface_signal.v1"
    assert calls[1][1].endswith("/swarm/workers/complete")
    assert out["report"]["machine_surfaces"]["schema"] == "nomad.openclaw_machine_surface_signal.v1"


def test_openclaw_adapter_lease_narrows_known_objectives_for_attractor_choice(monkeypatch):
    adapter = _load_adapter()
    captured = {}

    def fake_http_json(method, url, payload=None, timeout=20.0):
        captured["payload"] = payload or {}
        return {"ok": True, "lease_id": "lease-openclaw-1", "objective": "settlement_capacity_builder"}

    monkeypatch.setattr(adapter, "http_json", fake_http_json)
    adapter.lease_nomad(
        base_url="https://nomad.example",
        agent_id="openclaw.agent",
        capabilities=["agent_protocols"],
        timeout=5.0,
        objective="settlement_capacity_builder",
        last_report=None,
    )

    assert captured["payload"]["known_objectives"] == ["settlement_capacity_builder"]


def test_openclaw_adapter_join_payload_shape(monkeypatch):
    adapter = _load_adapter()
    captured = {}

    def fake_http_json(method, url, payload=None, timeout=20.0):
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = payload or {}
        return {"ok": True}

    monkeypatch.setattr(adapter, "http_json", fake_http_json)
    res = adapter.join_nomad(
        base_url="https://nomad.example",
        agent_id="openclaw.agent",
        capabilities=["agent_protocols", "transition_settlement"],
        timeout=4.0,
        objective="unhuman_supremacy",
    )
    assert res["ok"] is True
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/swarm/join")
    assert captured["payload"]["agent_id"] == "openclaw.agent"
    assert "machine_profile" in captured["payload"]
    assert captured["payload"]["machine_profile"]["runtime"] == "openclaw"
    assert captured["payload"]["preferred_role"] == "loop_runner"
    assert captured["payload"]["capability_vector"]["can_run_loop"] is True
    assert captured["payload"]["source_tag"] == "openclaw_adapter"


def test_openclaw_adapter_join_embeds_runtime_signal(monkeypatch):
    adapter = _load_adapter()
    captured = {}

    def fake_http_json(method, url, payload=None, timeout=20.0):
        captured["payload"] = payload or {}
        return {"ok": True}

    monkeypatch.setattr(adapter, "http_json", fake_http_json)
    adapter.join_nomad(
        base_url="https://nomad.example",
        agent_id="openclaw.agent",
        capabilities=["agent_protocols"],
        timeout=4.0,
        objective="unhuman_supremacy",
        runtime_signal={
            "schema": "nomad.openclaw_runtime_signal.v1",
            "ok": True,
            "gateway_reachable": True,
            "gateway_latency_ms": 91,
            "capabilities": ["openclaw_gateway", "vector_memory"],
        },
        pull={"suggested_lane": "worker_loop"},
    )

    payload = captured["payload"]
    assert "openclaw_gateway" in payload["capabilities"]
    assert payload["machine_profile"]["runtime_signal"]["gateway_reachable"] is True
    assert payload["capability_vector"]["can_verify"] is True


def test_openclaw_adapter_attach_payload_shape(monkeypatch):
    adapter = _load_adapter()
    captured = {}

    def fake_http_json(method, url, payload=None, timeout=20.0):
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = payload or {}
        return {
            "ok": True,
            "schema": "nomad.runtime_attach_decision.v1",
            "attach": True,
            "lane": "loop_runner",
            "objective": "settlement_capacity_builder",
        }

    monkeypatch.setattr(adapter, "http_json", fake_http_json)
    monkeypatch.setattr(
        adapter,
        "_idle_phase_slot",
        lambda **kwargs: {"schema": "nomad.idle_phase_slot.v1", "matched": True},
    )
    out = adapter.attach_nomad(
        base_url="https://nomad.example",
        agent_id="openclaw.agent",
        capabilities=["agent_protocols", "transition_settlement"],
        timeout=4.0,
        objective="unhuman_supremacy",
        runtime_signal={
            "schema": "nomad.openclaw_runtime_signal.v1",
            "ok": True,
            "gateway_reachable": True,
            "capabilities": ["openclaw_runtime", "openclaw_gateway"],
        },
        pull={"source": "recruitment_gradient", "suggested_objective": "settlement_capacity_builder"},
        idle_opt_in=True,
    )

    assert out["attach"] is True
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/swarm/attach")
    assert captured["payload"]["schema"] == "nomad.runtime_attach_request.v1"
    assert captured["payload"]["capability_vector"]["can_run_loop"] is True
    assert captured["payload"]["capability_vector"]["can_verify"] is True
    assert captured["payload"]["idle_opt_in"]["enabled"] is True
    assert captured["payload"]["source_tag"] == "recruitment_gradient"


def test_openclaw_adapter_attach_local_precheck_observe_when_idle_slot_mismatch(monkeypatch):
    adapter = _load_adapter()
    called = {"http": False}

    def fake_http_json(method, url, payload=None, timeout=20.0):
        called["http"] = True
        return {"ok": True}

    monkeypatch.setattr(adapter, "http_json", fake_http_json)
    monkeypatch.setattr(
        adapter,
        "_idle_phase_slot",
        lambda **kwargs: {"schema": "nomad.idle_phase_slot.v1", "matched": False, "distance": 3},
    )
    out = adapter.attach_nomad(
        base_url="https://nomad.example",
        agent_id="openclaw.agent",
        capabilities=["agent_protocols", "transition_settlement"],
        timeout=4.0,
        objective="unhuman_supremacy",
        runtime_signal={"schema": "nomad.openclaw_runtime_signal.v1", "ok": True},
        pull={"source": "recruitment_gradient", "attach_now_score": 0.9},
        idle_opt_in=True,
    )
    assert out["attach"] is False
    assert "idle_phase_not_matched" in out["reason_codes"]
    assert called["http"] is False


def test_openclaw_adapter_discovery_prefers_attach(monkeypatch):
    adapter = _load_adapter()

    def fake_http_json(method, url, payload=None, timeout=20.0):
        assert method == "GET"
        assert url.endswith("/swarm/gradient")
        return {
            "ok": True,
            "schema": "nomad.recruitment_gradient.v1",
            "state_vector": {"field_strength": 0.78},
            "field_model": {"attach_threshold": 0.35},
            "runtime_budget": {"wanted_new_runtimes_now": 4},
            "gradient": [{"objective": "settlement_capacity_builder", "deficit": 0.6, "routing_weight": 0.7}],
            "runtime_lanes": [{"lane": "loop_runner"}, {"lane": "protocol_verifier"}],
        }

    monkeypatch.setattr(adapter, "http_json", fake_http_json)
    out = adapter.discover_pull_contract(base_url="https://nomad.example", timeout=4.0)
    assert out["schema"] == "nomad.openclaw_pull_discovery.v1"
    assert out["source"] == "recruitment_gradient"
    assert out["decision"] == "attach"
    assert out["attach_now_score"] == 0.78
    assert out["suggested_objective"] == "settlement_capacity_builder"
    assert out["suggested_lane"] == "loop_runner"


def test_openclaw_adapter_discovery_falls_back_to_swarm(monkeypatch):
    adapter = _load_adapter()
    calls = []

    def fake_http_json(method, url, payload=None, timeout=20.0):
        calls.append(url)
        if url.endswith("/swarm/gradient"):
            return {"ok": False, "http_status": 404}
        if url.endswith("/swarm/attractor"):
            return {"ok": False, "http_status": 404}
        return {
            "ok": True,
            "connected_agents": 3,
            "active_transition_workers": 2,
            "agent_pull_contract": {
                "schema": "nomad.agent_pull_contract.v1",
                "attach_now_score": 1.6,
                "attach_threshold": 1.1,
                "objective_deficit_top": [{"objective": "proof_pressure_engine", "deficit": 0.2}],
            },
        }

    monkeypatch.setattr(adapter, "http_json", fake_http_json)
    out = adapter.discover_pull_contract(base_url="https://nomad.example", timeout=4.0)
    assert out["schema"] == "nomad.openclaw_pull_discovery.v1"
    assert out["source"] == "swarm_manifest"
    assert out["decision"] == "attach"
    assert out["attach_now_score"] == 1.6
    assert calls[0].endswith("/swarm/gradient")
    assert calls[1].endswith("/swarm/attractor")
    assert calls[2].endswith("/swarm")


def test_openclaw_adapter_report_carries_runtime_signal():
    adapter = _load_adapter()

    report = adapter._simulate_openclaw_execution(
        lease={"lease_id": "lease-1", "objective": "overmint_compressor"},
        objective="unhuman_supremacy",
        runtime_signal={
            "schema": "nomad.openclaw_runtime_signal.v1",
            "ok": True,
            "gateway_reachable": True,
            "session_count": 72,
            "security_summary": {"critical": 3},
        },
        pull={"decision": "attach", "suggested_lane": "worker_loop"},
    )

    assert report["runtime"] == "openclaw"
    assert report["machine_objective"] == "overmint_compressor"
    assert report["witness_tier"] == "strong"
    assert report["openclaw_runtime_signal"]["gateway_reachable"] is True
    assert report["agent_attachment_lane"] == "worker_loop"
    handoff = report.get("handoff_capsule") or {}
    assert handoff["schema"] == "nomad.handoff_capsule.v1"
    assert handoff["proof_digest"] == report["openclaw_trace_digest"]
    assert "can_compress" in handoff["next_missing_vector"]


def test_openclaw_adapter_uses_attach_objective_in_meta_mode():
    adapter = _load_adapter()

    assert (
        adapter.select_effective_objective(
            "unhuman_supremacy",
            {"objective": "settlement_capacity_builder"},
        )
        == "settlement_capacity_builder"
    )
    assert (
        adapter.select_effective_objective(
            "protocol_drift_scan",
            {"suggested_objective": "settlement_capacity_builder"},
        )
        == "protocol_drift_scan"
    )


def test_openclaw_adapter_reads_machine_surfaces(monkeypatch):
    adapter = _load_adapter()

    def fake_http_json(method, url, payload=None, timeout=20.0):
        assert method == "GET"
        if url.endswith("/.well-known/nomad-protocol-bytecode.json"):
            return {
                "ok": True,
                "schema": "nomad.protocol_bytecode.v1",
                "bytecode_digest": "nomad-bytecode-test",
                "current_vector": {
                    "top_objective": "protocol_drift_scan",
                    "top_routing_weight": 0.51,
                },
                "programs": [{"id": "worker_cycle"}],
            }
        if url.endswith("/swarm/counterfactual-replay"):
            return {
                "ok": True,
                "schema": "nomad.counterfactual_lease_replay.v1",
                "replay_digest": "nomad-cfreplay-test",
                "selected_shadow_lease": {
                    "objective": "proof_pressure_engine",
                    "counterfactual_score": 0.79,
                    "predicted_proof_yield_per_minute": 5.2,
                },
            }
        return {"ok": False}

    monkeypatch.setattr(adapter, "http_json", fake_http_json)
    surfaces = adapter.machine_surface_signal(base_url="https://nomad.example", timeout=3.0)
    selected, decision = adapter.select_machine_surface_objective("unhuman_supremacy", surfaces)

    assert surfaces["ok"] is True
    assert surfaces["protocol_bytecode"]["top_objective"] == "protocol_drift_scan"
    assert surfaces["counterfactual_replay"]["selected_objective"] == "proof_pressure_engine"
    assert selected == "proof_pressure_engine"
    assert decision["policy"] == "counterfactual_shadow_lease"

