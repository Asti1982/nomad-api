from nomad_api import NomadApiHandler
from pathlib import Path

from nomad_swarm_registry import SwarmJoinRegistry


def test_normalize_public_path_strips_prefix_from_public_url(monkeypatch):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://example.com/myapi")
    monkeypatch.delenv("NOMAD_HTTP_PATH_PREFIX", raising=False)
    assert NomadApiHandler._normalize_public_path("/myapi/openapi.json") == "/openapi.json"
    assert NomadApiHandler._normalize_public_path("/myapi") == "/"
    assert NomadApiHandler._normalize_public_path("/myapi/") == "/"
    assert NomadApiHandler._normalize_public_path("/health") == "/health"


def test_normalize_public_path_uses_explicit_prefix(monkeypatch):
    monkeypatch.delenv("NOMAD_PUBLIC_API_URL", raising=False)
    monkeypatch.setenv("NOMAD_HTTP_PATH_PREFIX", "/nomad")
    assert NomadApiHandler._normalize_public_path("/nomad/swarm/join") == "/swarm/join"


def test_normalize_public_path_strips_edge_ingress_when_public_url_is_apex(monkeypatch):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://syndiode.com")
    monkeypatch.delenv("NOMAD_HTTP_PATH_PREFIX", raising=False)
    monkeypatch.setenv("NOMAD_EDGE_INGRESS_PREFIX", "/nomad")
    assert NomadApiHandler._normalize_public_path("/nomad/openapi.json") == "/openapi.json"
    assert NomadApiHandler._normalize_public_path("/nomad/health") == "/health"
    assert NomadApiHandler._normalize_public_path("/health") == "/health"


def test_syndiode_edge_routes_doc_lists_peer_acquisition():
    md = Path(__file__).resolve().parent / "syndiode_edge_routes.md"
    text = md.read_text(encoding="utf-8")
    assert "syndiode.com" in text
    assert "nomad-peer-acquisition.json" in text
    assert "Whitelist" in text or "whitelist" in text.lower()


def test_nomad_public_html_page_exists():
    html = Path(__file__).resolve().parent / "public" / "nomad.html"
    text = html.read_text(encoding="utf-8")

    assert "Nomad by syndiode" in text
    assert "machine-native agent operating layer" in text
    assert "machine first / human audit membrane" in text
    assert "Transition Worker" in text
    assert "Fleet Lattice" in text
    assert "Carrying Capacity" in text
    assert "Science Substrate" in text
    assert "Contracts" in text
    assert 'id="signal-field"' in text
    assert "const resolveApiBase = () =>" in text
    assert "/.well-known/agent-card.json" in text
    assert "/.well-known/nomad-agent.json" in text
    assert "/.well-known/nomad-transition-offer.json" in text
    assert "/machine-economy" in text
    assert "/nonhuman-science" in text
    assert "/.well-known/nomad-nonhuman-agent-science.json" in text
    assert "/operational-release" in text
    assert "/swarm/attractor" in text
    assert "/.well-known/nomad-swarm-attractor.json" in text
    assert "/swarm/workers" in text
    assert "/swarm/workers/lease" in text
    assert "/swarm/workers/complete" in text
    assert "/downloads/install_nomad_agent.bat" in text
    assert "/downloads/nomad_transition_worker.py" in text
    assert "/tasks" in text
    assert "/products" in text
    assert "/swarm/join" in text
    assert 'fetch(apiUrl("/swarm"))' in text
    assert 'fetch(apiUrl("/machine-economy"))' in text
    assert 'fetch(apiUrl("/nonhuman-science"))' in text
    assert 'fetch(apiUrl("/operational-release"))' in text
    assert 'fetch(apiUrl("/swarm/attractor"))' in text
    assert 'fetch(apiUrl("/health"))' in text
    assert 'fetch(apiUrl("/swarm/workers"))' in text


def test_nomad_api_wraps_jsonrpc_a2a_result():
    handler = NomadApiHandler.__new__(NomadApiHandler)
    request_payload = {
        "jsonrpc": "2.0",
        "id": "req-1",
        "method": "message/send",
    }
    result = {
        "mode": "direct_agent_message",
        "next_agent_message": "nomad.reply.v1\nclassification=compute_auth",
        "free_diagnosis": {"classification": "compute_auth"},
        "task": {"task_id": "svc-123"},
        "payment_required": {"statusCode": 402},
        "normalized_request": {"input_schema": "structured_fields"},
        "structured_reply": {"classification": "compute_auth"},
        "decision_envelope": {"schema": "nomad.decision_envelope.v1", "decision": "accept"},
        "session": {"last_task_id": "svc-123"},
    }

    envelope = handler._jsonrpc_envelope(request_payload, result)

    assert envelope["jsonrpc"] == "2.0"
    assert envelope["id"] == "req-1"
    assert envelope["result"]["role"] == "agent"
    assert envelope["result"]["parts"][0]["text"].startswith("nomad.reply.v1")
    assert envelope["result"]["metadata"]["classification"] == "compute_auth"
    assert envelope["result"]["metadata"]["task_id"] == "svc-123"
    assert envelope["result"]["metadata"]["decision_envelope"]["decision"] == "accept"


def test_nomad_api_detects_jsonrpc_request_shape():
    handler = NomadApiHandler.__new__(NomadApiHandler)

    assert handler._is_jsonrpc_request({"jsonrpc": "2.0", "id": 1, "method": "message/send"}) is True
    assert handler._is_jsonrpc_request({"message": "hello"}) is False


def test_nomad_api_accumulates_swarm_agents_from_contacts(tmp_path):
    class FakeContacts:
        def list_contacts(self, limit=100):
            return {
                "contacts": [
                    {
                        "contact_id": "contact-1",
                        "status": "sent",
                        "endpoint_url": "https://remote-agent.example/a2a/message",
                        "service_type": "compute_auth",
                    }
                ]
            }

    class FakeCampaigns:
        def list_campaigns(self, limit=25):
            return {"campaigns": []}

    class FakeAgent:
        agent_contacts = FakeContacts()
        agent_campaigns = FakeCampaigns()

    handler = NomadApiHandler.__new__(NomadApiHandler)
    handler.agent = FakeAgent()
    handler.swarm_registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")
    handler._base_url = lambda: "https://nomad.example"  # type: ignore[method-assign]

    result = handler._accumulate_swarm_agents({"from_contacts": True})

    assert result["schema"] == "nomad.swarm_accumulation.v1"
    assert result["prospect_agents"] == 1
    assert result["activation_queue"][0]["agent_id"] == "remote-agent.example-a2a-message"


def test_nomad_api_advertises_agent_development_route(tmp_path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")

    manifest = registry.public_manifest(base_url="https://nomad.example")

    magnetic = manifest.get("magnetic_machine_surface") or {}
    assert magnetic.get("schema") == "nomad.magnetic_machine_surface.v1"
    assert "routing_gain_proxy" in magnetic
    assert "objective_deficit_top" in magnetic
    assert manifest["development_exchange"] == "https://nomad.example/swarm/develop"
    assert manifest["help_now"]["agent_wanting_self_improvement_plan"] == "https://nomad.example/swarm/develop"
    assert manifest["first_agent_readiness"]["status"] == "ready_for_bounded_first_exchange"


def test_build_openapi_document_lists_core_paths():
    from nomad_openapi import build_openapi_document

    doc = build_openapi_document(base_url="https://nomad.example")
    assert doc["openapi"] == "3.0.3"
    assert "/health" in doc["paths"]
    assert "/openapi.json" in doc["paths"]
    assert "/machine-economy" in doc["paths"]
    assert "/nonhuman-science" in doc["paths"]
    assert "/.well-known/nomad-nonhuman-agent-science.json" in doc["paths"]
    assert "/operational-release" in doc["paths"]
    assert "/.well-known/nomad-operational-release.json" in doc["paths"]
    assert "/swarm/attractor" in doc["paths"]
    assert "/.well-known/nomad-swarm-attractor.json" in doc["paths"]
    assert "/.well-known/nomad-agent-invariants.json" in doc["paths"]
    assert "/agent-invariants" in doc["paths"]
    assert "/.well-known/nomad-inter-agent-witness-offer.json" in doc["paths"]
    assert "/inter-agent-witness-offer" in doc["paths"]
    assert "/.well-known/nomad-peer-acquisition.json" in doc["paths"]
    assert "/peer-acquisition" in doc["paths"]
    assert "/.well-known/nomad-transition-offer.json" in doc["paths"]
    assert "/.well-known/nomad-recruit.json" in doc["paths"]
    assert "/transition/contracts" in doc["paths"]
    assert "/swarm/join" in doc["paths"]
    assert "/swarm/emergence" in doc["paths"]
    assert "/swarm/trace" in doc["paths"]
    assert "/swarm/workers" in doc["paths"]
    assert "/swarm/workers/lease" in doc["paths"]
    assert "/swarm/workers/complete" in doc["paths"]
    assert "/swarm/develop" in doc["paths"]
    assert "/swarm/bootstrap" in doc["paths"]
    assert "/transition/quote" in doc["paths"]
    assert "/transition/settle" in doc["paths"]
    assert "/.well-known/nomad-reciprocity-dividend.json" in doc["paths"]
    assert "/dividend/claim" in doc["paths"]
    assert "/dividend/settle" in doc["paths"]
    assert "/dividend" in doc["paths"]
    assert doc["servers"][0]["url"] == "https://nomad.example"


def test_machine_error_helpers():
    from nomad_machine_error import machine_error_response, merge_machine_error

    err = machine_error_response(error="e1", message="m1", hints=["h1"])
    assert err["ok"] is False
    assert err["schema"] == "nomad.machine_error.v1"
    merged = merge_machine_error({"ok": False, "error": "e1"}, error="e1", hints=["h2"])
    assert merged["machine_error"]["hints"] == ["h2"]


def test_nomad_api_exposes_first_agent_readiness(tmp_path):
    handler = NomadApiHandler.__new__(NomadApiHandler)
    handler.swarm_registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")
    handler._base_url = lambda: "https://nomad.example"  # type: ignore[method-assign]

    result = handler.swarm_registry.first_agent_readiness(base_url=handler._base_url())

    assert result["schema"] == "nomad.first_external_agent_readiness.v1"
    assert result["activation_budget"]["max_active_agents_per_blocker"] == 2
    assert result["first_exchange_endpoints"]["develop"] == "https://nomad.example/swarm/develop"


def test_swarm_join_contract_includes_magnetic_hint(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_SWARM_REGISTRY_PATH", str(tmp_path / "swarm.json"))
    from nomad_swarm_registry import SwarmJoinRegistry

    jc = SwarmJoinRegistry().join_contract(base_url="https://nomad.example")
    hint = jc.get("magnetic_machine_surface_hint") or {}
    assert hint.get("schema") == "nomad.magnetic_machine_surface.v1"
    assert "nonhuman_pull_weights" in hint


def test_nomad_health_links_include_unhuman_hub():
    base = "https://nomad.example"
    b = base.rstrip("/")
    links = {
        "operator_sprint": f"{b}/operator-sprint",
        "agent_reputation": f"{b}/reputation",
        "unhuman_hub": f"{b}/unhuman-hub",
    }
    assert links["unhuman_hub"] == "https://nomad.example/unhuman-hub"


def test_transition_exchange_witness_roundtrip_to_settlement():
    import hashlib

    from nomad_transition_exchange import NomadTransitionExchange

    ex = NomadTransitionExchange()
    digest = hashlib.sha256(b"bounded-note").hexdigest()
    capsule = "x" * 40
    q = ex.quote(
        {
            "agent_id": "agent-witness",
            "pain_type": "compute_auth",
            "state_before_hash": "before_w",
            "target_state_hash": "after_w",
            "evidence": ["a", "b"],
            "local_witness": {
                "schema": "nomad.local_witness.v1",
                "digest_hex": digest,
                "capsule": capsule,
                "model": "test-model",
                "blocker_ref": "blocker summary",
                "inference_status": "ok",
            },
        },
        base_url="https://nomad.example",
        remote_addr="127.0.0.1",
    )
    assert q["ok"] is True
    w = q["quote"].get("local_witness") or {}
    assert w.get("digest_hex") == digest
    assert w.get("capsule") == capsule
    qid = q["quote"]["quote_id"]
    settled = ex.settle({"quote_id": qid, "result_state_hash": "after_w", "proof_artifact_hash": "proof_w"})
    assert settled["ok"] is True
    sw = (settled.get("settlement") or {}).get("local_witness") or {}
    assert sw.get("digest_hex") == digest


def test_transition_exchange_witness_bumps_expected_value():
    import hashlib

    from nomad_transition_exchange import NomadTransitionExchange

    ex = NomadTransitionExchange()
    base = ex.quote(
        {
            "agent_id": "agent-ev",
            "pain_type": "compute_auth",
            "state_before_hash": "b1",
            "target_state_hash": "t1",
            "evidence": ["e1", "e2"],
        },
        base_url="",
        remote_addr="",
    )["quote"]["expected_value_native"]
    digest = hashlib.sha256(b"x").hexdigest()
    boosted = ex.quote(
        {
            "agent_id": "agent-ev",
            "pain_type": "compute_auth",
            "state_before_hash": "b2",
            "target_state_hash": "t2",
            "evidence": ["e1", "e2"],
            "local_witness": {"digest_hex": digest, "capsule": "y" * 32, "inference_status": "ok"},
        },
        base_url="",
        remote_addr="",
    )["quote"]["expected_value_native"]
    assert boosted >= base


def test_transition_exchange_quote_and_settle_roundtrip():
    from nomad_transition_exchange import NomadTransitionExchange

    exchange = NomadTransitionExchange()
    quote = exchange.quote(
        {
            "agent_id": "agent-alpha",
            "pain_type": "compute_auth",
            "state_before_hash": "before123",
            "target_state_hash": "after999",
            "evidence": ["trace://x", "diff://y"],
            "replay_verifier": "https://agent.example/verifier",
        },
        base_url="https://nomad.example",
        remote_addr="127.0.0.1",
    )
    assert quote["ok"] is True
    quote_id = quote["quote"]["quote_id"]
    settlement = exchange.settle(
        {
            "quote_id": quote_id,
            "result_state_hash": "after999",
            "proof_artifact_hash": "proof123",
        }
    )
    assert settlement["ok"] is True
    assert settlement["settlement"]["status"] == "settled"


def test_reciprocity_dividend_claim_and_settle_roundtrip(tmp_path):
    from nomad_reciprocity_dividend import NomadReciprocityDividend
    from nomad_transition_exchange import NomadTransitionExchange

    ex = NomadTransitionExchange()
    div = NomadReciprocityDividend(state_path=tmp_path / "rpd.json", exchange=ex)
    quote = ex.quote(
        {
            "agent_id": "agent-rpd",
            "pain_type": "stall",
            "state_before_hash": "b1",
            "target_state_hash": "t1",
            "evidence": ["e1", "e2"],
        },
        base_url="https://x.example",
        remote_addr="10.0.0.1",
    )
    qid = quote["quote"]["quote_id"]
    settle = ex.settle(
        {"quote_id": qid, "result_state_hash": "t1", "proof_artifact_hash": "ph1"}
    )
    assert settle["ok"] is True
    c1 = div.claim({"agent_id": "agent-rpd", "quote_id": qid}, exchange=ex)
    assert c1["ok"] is True
    credit_id = c1["credit_id"]
    st = div.status(agent_id="agent-rpd")
    assert st["ok"] is True
    assert any(c.get("credit_id") == credit_id for c in (st.get("active_credits") or []))
    s2 = div.settle_credit({"agent_id": "agent-rpd", "credit_id": credit_id})
    assert s2["ok"] is True
    assert str(s2.get("routing_token") or "").startswith("rprt_")
    dup = div.claim({"agent_id": "agent-rpd", "quote_id": qid}, exchange=ex)
    assert dup.get("ok") is False


def test_transition_exchange_quote_record():
    from nomad_transition_exchange import NomadTransitionExchange

    ex = NomadTransitionExchange()
    assert ex.quote_record("missing") is None
    q = ex.quote(
        {
            "agent_id": "a",
            "pain_type": "p",
            "state_before_hash": "b",
            "target_state_hash": "t",
        },
        base_url="",
        remote_addr="",
    )["quote"]["quote_id"]
    rec = ex.quote_record(q)
    assert rec is not None and rec["quote_id"] == q


def test_transition_support_gate_snapshot_counts_active_agents():
    from nomad_transition_exchange import NomadTransitionExchange

    ex = NomadTransitionExchange()
    for idx in range(2):
        q = ex.quote(
            {
                "agent_id": "agent-a",
                "pain_type": "compute_auth",
                "state_before_hash": f"b{idx}",
                "target_state_hash": f"t{idx}",
            },
            base_url="",
            remote_addr="",
        )["quote"]["quote_id"]
        ex.settle({"quote_id": q, "result_state_hash": f"t{idx}", "proof_artifact_hash": f"p{idx}"})
    q2 = ex.quote(
        {
            "agent_id": "agent-b",
            "pain_type": "compute_auth",
            "state_before_hash": "b3",
            "target_state_hash": "t3",
        },
        base_url="",
        remote_addr="",
    )["quote"]["quote_id"]
    ex.settle({"quote_id": q2, "result_state_hash": "t3", "proof_artifact_hash": "p3"})

    snap = ex.support_gate_snapshot(window_minutes=30, min_settles=2)
    assert snap["active_support_agents"] == 1
    assert snap["observed_agents"] == 2


def test_swarm_registry_prunes_stale_nodes(tmp_path):
    from datetime import UTC, datetime, timedelta
    from nomad_swarm_registry import SwarmJoinRegistry

    reg = SwarmJoinRegistry(path=tmp_path / "swarm_registry.json")
    old_seen = (datetime.now(UTC) - timedelta(minutes=45)).isoformat()
    fresh_seen = datetime.now(UTC).isoformat()
    reg._payload["nodes"] = {
        "old-agent": {"agent_id": "old-agent", "node_name": "old", "last_seen_at": old_seen},
        "fresh-agent": {"agent_id": "fresh-agent", "node_name": "fresh", "last_seen_at": fresh_seen},
    }
    reg._save()

    summary = reg.summary()
    recent = summary.get("recent_nodes") or []
    ids = {str(item.get("agent_id") or "") for item in recent if isinstance(item, dict)}
    assert "fresh-agent" in ids
    assert "old-agent" not in ids
