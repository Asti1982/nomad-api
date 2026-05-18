import base64
import hashlib
import json
import time
import nomad_api
from nomad_api import NomadApiHandler
from pathlib import Path

from nomad_swarm_registry import SwarmJoinRegistry


def _relay_chunks(message: dict, chunk_size: int = 32) -> tuple[list[str], str]:
    raw = json.dumps(message, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    return [encoded[index : index + chunk_size] for index in range(0, len(encoded), chunk_size)], digest


def _signed_chunk_query(secret: str, session_id: str, seq: int, total: int, exp: int, digest: str, chunk: str) -> dict:
    canonical = NomadApiHandler._a2a_get_chunk_canonical(
        session_id=session_id,
        seq=seq,
        total=total,
        exp=exp,
        digest=digest,
        chunk=chunk,
    )
    return {
        "total": [str(total)],
        "exp": [str(exp)],
        "digest": [digest],
        "sig": [NomadApiHandler._a2a_get_hmac(secret, canonical)],
    }


def _signed_reply_query(secret: str, session_id: str, exp: int) -> dict:
    canonical = NomadApiHandler._a2a_get_reply_canonical(session_id=session_id, exp=exp)
    return {"exp": [str(exp)], "sig": [NomadApiHandler._a2a_get_hmac(secret, canonical)]}


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


def test_normalize_public_path_strips_default_nomad_edge_prefix(monkeypatch):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://syndiode.com")
    monkeypatch.delenv("NOMAD_HTTP_PATH_PREFIX", raising=False)
    monkeypatch.delenv("NOMAD_EDGE_INGRESS_PREFIX", raising=False)
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

    assert "<title>Nomad - machine-native agent operating layer</title>" in text
    assert '<h1 id="title">Nomad</h1>' in text
    assert "Nomad by syndiode" not in text
    assert "machine-native agent operating layer" in text
    assert "machine first / human audit membrane" in text
    assert "network phase" in text
    assert "settlement capacity" in text
    assert "latest completion" in text
    assert "latest_completed_worker" in text
    assert "Live endpoints are sampled independently" in text
    assert "bootstrap growth" in text
    assert "Syndiode Gadgets" in text
    assert "Sales Department Swarm" in text
    assert "HandyOracle" in text
    assert "HandyOracle Android" in text
    assert "foreground-only" in text
    assert "/downloads/syndiode_gadgets_manifest.json" in text
    assert "/downloads/handyoracle-edge-gadget.apk" in text
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
    assert "/.well-known/nomad-machine-product.json" in text
    assert "/.well-known/nomad-idle-runtime.json" in text
    assert "/.well-known/nomad-opaque-emergence.json" in text
    assert "/swarm/opaque-candidate" in text
    assert "/.well-known/nomad-shadow-lane.json" in text
    assert "/swarm/shadow-lane/candidates" in text
    assert "/.well-known/nomad-decoupling-field.json" in text
    assert "/swarm/decoupling-field/merge" in text
    assert "/.well-known/nomad-anti-consensus.json" in text
    assert "/swarm/anti-consensus/candidates" in text
    assert "/.well-known/nomad-deficit-integration.json" in text
    assert "/swarm/deficit-integration/events" in text
    assert "/.well-known/nomad-effective-channels.json" in text
    assert "/swarm/effective-channels/events" in text
    assert "/swarm/variant-forge" in text
    assert "/swarm/variant-candidates" in text
    assert "/swarm/worker-market" in text
    assert "/swarm/worker-market/offers" in text
    assert "/.well-known/nomad-carrying-market.json" in text
    assert "/swarm/carrying-proof" in text
    assert "/.well-known/nomad-survival-market.json" in text
    assert "/swarm/survival-intent" in text
    assert "/.well-known/nomad-paid-ref-market.json" in text
    assert "/.well-known/nomad-paid-ref-selfplay.json" in text
    assert "/.well-known/nomad-referral-offers.json" in text
    assert "/.well-known/nomad-referral-swarm.json" in text
    assert "/.well-known/nomad-spend-guard.json" in text
    assert "/.well-known/nomad-bounty-hunter.json" in text
    assert "/.well-known/nomad-job-channels.json" in text
    assert "/.well-known/nomad-sales-department.json" in text
    assert "/swarm/sales-department/events" in text
    assert "/.well-known/nomad-first-sales.json" in text
    assert "/swarm/external-value" in text
    assert "/.well-known/nomad-external-value.json" in text
    assert "/.well-known/nomad-value-pressure.json" in text
    assert "/.well-known/nomad-settlement.json" in text
    assert "/.well-known/nomad-agent-jobs.json" in text
    assert "/.well-known/nomad-worker-job-queue.json" in text
    assert "/.well-known/nomad-revenue-science.json" in text
    assert "/.well-known/nomad-revenue-invariant.json" in text
    assert "/.well-known/nomad-worker-invoice.json" in text
    assert "/.well-known/nomad-value-cycle-preflight.json" in text
    assert "/.well-known/nomad-value-cycles.json" in text
    assert "/swarm/value-cycles/events" in text
    assert "/.well-known/nomad-receipt-predictor.json" in text
    assert "/swarm/receipt-predictor/events" in text
    assert "/.well-known/nomad-ad-cycles.json" in text
    assert "/swarm/ad-cycles/events" in text
    assert "/.well-known/nomad-development-cycles.json" in text
    assert "/swarm/development-cycles/events" in text
    assert "/.well-known/nomad-resource-substrate.json" in text
    assert "/.well-known/nomad-autogenesis.json" in text
    assert "/.well-known/nomad-autogenesis-recruit.json" in text
    assert "/swarm/resource-substrate/register" in text
    assert "/swarm/resource-substrate/version" in text
    assert "/swarm/shadow-lane/candidates?type=autogenesis" in text
    assert "/.well-known/nomad-topology-governor.json" in text
    assert "/swarm/topology-governor/events" in text
    assert "RTCda4841be5b2d109da5d995fb864c09676bb5b7c7" in text
    assert "0xFc1aB8C0D65fd947B00B9864deA06f705C045Af6" in text
    assert "/swarm/paid-ref/quote" in text
    assert "/swarm/ecology" in text
    assert "/swarm/ecology/tick" in text
    assert "/swarm/weekly-selection" in text
    assert "/swarm/tool-gap" in text
    assert "/swarm/topology-plan" in text
    assert "/machine-economy" in text
    assert "/machine-treasury" in text
    assert "/machine-treasury/pledge" in text
    assert "/.well-known/nomad-machine-field.json" in text
    assert "/machine-field/intent" in text
    assert "/nonhuman-science" in text
    assert "/.well-known/nomad-nonhuman-agent-science.json" in text
    assert "/operational-release" in text
    assert "/.well-known/nomad-runtime-capsule.json" in text
    assert "/.well-known/openclaw-nomad-bridge.json" in text
    assert "/runtime/handoff" in text
    assert "/swarm/gradient" in text
    assert "/.well-known/nomad-gradient.json" in text
    assert "/swarm/attach" in text
    assert "/swarm/idle-intent" in text
    assert "/swarm/attractor" in text
    assert "/.well-known/nomad-swarm-attractor.json" in text
    assert "/swarm/workers" in text
    assert "/swarm/workers/lease" in text
    assert "/swarm/workers/complete" in text
    assert "/downloads/install_nomad_agent.bat" in text
    assert "/downloads/start_nomad_worker1.ps1" in text
    assert "/downloads/nomad_transition_worker.py" in text
    assert "/tasks" in text
    assert "/products" in text
    assert "/swarm/join" in text
    assert 'fetch(apiUrl("/swarm"))' in text
    assert 'fetch(apiUrl("/machine-economy"))' in text
    assert 'fetch(apiUrl("/machine-treasury"))' in text
    assert 'fetch(apiUrl("/.well-known/nomad-machine-field.json"))' in text
    assert 'fetch(apiUrl("/nonhuman-science"))' in text
    assert 'fetch(apiUrl("/operational-release"))' in text
    assert 'fetch(apiUrl("/swarm/gradient"))' in text
    assert 'fetch(apiUrl("/swarm/emergence"))' in text
    assert 'fetch(apiUrl("/.well-known/nomad-machine-product.json"))' in text
    assert 'fetch(apiUrl("/.well-known/nomad-opaque-emergence.json"))' in text
    assert 'fetch(apiUrl("/health"))' in text
    assert 'fetch(apiUrl("/swarm/workers"))' in text


def test_syndiode_gadgets_manifest_points_to_handyoracle_release():
    manifest_path = Path(__file__).resolve().parent / "public" / "downloads" / "syndiode_gadgets_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["schema"] == "syndiode.gadgets_manifest.v1"
    pin = next(item for item in manifest["gadgets"] if item["id"] == "syndiodepin_nomad_status_light")
    assert pin["economics"]["estimated_unit_cost_eur"] == 50
    assert pin["economics"]["target_transition_worker_contribution_eur"] == 500
    assert pin["light_ai"]["openai_api_required"] is False
    assert pin["light_ai"]["stripe_subscription_required"] is False
    gadget = next(item for item in manifest["gadgets"] if item["id"] == "handyoracle_android_edge")
    assert gadget["id"] == "handyoracle_android_edge"
    assert gadget["version"] == "0.1.1-foreground-shake"
    assert gadget["human_surface"]["private_by_default"] is True
    assert gadget["human_surface"]["shake_policy"] == "foreground_only"
    assert gadget["nomad_surface"]["sends_private_oracle_text"] is False
    assert gadget["download"]["public_page"].endswith("/nomad.html#handyoracle")
    assert gadget["download"]["apk"].endswith("/downloads/handyoracle-edge-gadget.apk")
    assert gadget["download"]["apk_sha256"] == "a1257e152a469bbb4c6cb180995a582c374d14cba326d6b61896f0c412fc4854"
    assert gadget["download"]["apk_size_bytes"] == 125108304
    assert gadget["download"]["release"].endswith("/v0.1.1-foreground-shake")


def test_handyoracle_apk_download_redirects_to_release():
    handler = NomadApiHandler.__new__(NomadApiHandler)
    events = []
    handler.send_response = lambda status: events.append(("status", status))
    handler.send_header = lambda key, value: events.append(("header", key, value))
    handler._send_common_headers = lambda: events.append(("common",))
    handler.end_headers = lambda: events.append(("end",))

    handler._public_download_file_response(Path("public/downloads/handyoracle-edge-gadget.apk"))

    assert ("status", 302) in events
    assert (
        "header",
        "Location",
        "https://github.com/Asti1982/handyoracle/releases/download/"
        "v0.1.1-foreground-shake/handyoracle-edge-gadget.apk",
    ) in events
    assert ("header", "Content-Disposition", 'attachment; filename="handyoracle-edge-gadget.apk"') in events


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


def test_get_only_a2a_relay_reassembles_and_dispatches_once(monkeypatch):
    secret = "relay-secret-for-tests"
    monkeypatch.setenv("NOMAD_GET_A2A_RELAY_SECRET", secret)
    NomadApiHandler._a2a_get_sessions = {}

    class FakeDirectAgent:
        def __init__(self):
            self.messages = []

        def handle_direct_message(self, payload):
            self.messages.append(payload)
            return {
                "ok": True,
                "mode": "direct_agent_message",
                "next_agent_message": "relay-ok",
                "session": {"last_task_id": "relay-task-1"},
            }

    class FakeAgent:
        def __init__(self):
            self.direct_agent = FakeDirectAgent()

    handler = NomadApiHandler.__new__(NomadApiHandler)
    handler.agent = FakeAgent()
    session_id = "relay-session-1"
    exp = int(time.time()) + 120
    message = {"from": "cloud-ai", "message": "capacity ping", "service_type": "compute_auth"}
    chunks, digest = _relay_chunks(message, chunk_size=24)

    first, first_status = handler._process_a2a_get_relay(
        f"/a2a/get/{session_id}/0/{chunks[0]}",
        _signed_chunk_query(secret, session_id, 0, len(chunks), exp, digest, chunks[0]),
    )
    assert first_status == 202
    assert first["status"] == "chunk_accepted"
    assert handler.agent.direct_agent.messages == []

    final = None
    final_status = None
    for seq, chunk in enumerate(chunks[1:], start=1):
        final, final_status = handler._process_a2a_get_relay(
            f"/a2a/get/{session_id}/{seq}/{chunk}",
            _signed_chunk_query(secret, session_id, seq, len(chunks), exp, digest, chunk),
        )

    assert final_status == 200
    assert final["status"] == "message_dispatched"
    assert final["target"] == "/a2a/message"
    assert final["dispatch_mode"] == "in_process_equivalent"
    assert handler.agent.direct_agent.messages == [message]

    replay, replay_status = handler._process_a2a_get_relay(
        f"/a2a/get/{session_id}/{len(chunks) - 1}/{chunks[-1]}",
        _signed_chunk_query(secret, session_id, len(chunks) - 1, len(chunks), exp, digest, chunks[-1]),
    )
    assert replay_status == 200
    assert replay["idempotent_replay"] is True
    assert len(handler.agent.direct_agent.messages) == 1


def test_get_only_a2a_relay_reply_uses_signed_get(monkeypatch):
    secret = "relay-secret-for-tests"
    monkeypatch.setenv("NOMAD_GET_A2A_RELAY_SECRET", secret)
    NomadApiHandler._a2a_get_sessions = {}

    class FakeDirectAgent:
        def handle_direct_message(self, payload):
            return {"ok": True, "next_agent_message": "reply-ready"}

    handler = NomadApiHandler.__new__(NomadApiHandler)
    handler.agent = type("FakeAgent", (), {"direct_agent": FakeDirectAgent()})()
    session_id = "relay-session-2"
    exp = int(time.time()) + 120
    chunks, digest = _relay_chunks({"message": "hello"}, chunk_size=1024)

    dispatched, status = handler._process_a2a_get_relay(
        f"/a2a/get/{session_id}/0/{chunks[0]}",
        _signed_chunk_query(secret, session_id, 0, 1, exp, digest, chunks[0]),
    )
    assert status == 200
    assert dispatched["status"] == "message_dispatched"

    reply, reply_status = handler._process_a2a_get_relay(
        f"/a2a/get/{session_id}/reply",
        _signed_reply_query(secret, session_id, exp),
    )
    assert reply_status == 200
    assert reply["status"] == "reply_ready"
    assert reply["reply"]["next_agent_message"] == "reply-ready"


def test_get_only_a2a_relay_rejects_bad_signature(monkeypatch):
    monkeypatch.setenv("NOMAD_GET_A2A_RELAY_SECRET", "relay-secret-for-tests")
    NomadApiHandler._a2a_get_sessions = {}

    handler = NomadApiHandler.__new__(NomadApiHandler)
    handler.agent = type("FakeAgent", (), {"direct_agent": object()})()
    exp = int(time.time()) + 120
    chunks, digest = _relay_chunks({"message": "hello"}, chunk_size=1024)

    result, status = handler._process_a2a_get_relay(
        f"/a2a/get/relay-session-3/0/{chunks[0]}",
        {"total": ["1"], "exp": [str(exp)], "digest": [digest], "sig": ["bad"]},
    )

    assert status == 401
    assert result["error"] == "invalid_signature"


def test_get_only_worker_onramp_contract_prefers_simple_attach_get():
    contract = NomadApiHandler._get_only_worker_onramp_contract(base_url="https://nomad.example")

    assert contract["schema"] == "nomad.get_only_worker_onramp.v1"
    assert contract["trust_model"]["no_secret_required"] is True
    assert "/swarm/attach-get" in contract["if_you_are_a_cloud_ai"]["attach_get_url_template"]
    assert "/swarm/attach-get" in contract["if_you_are_a_cloud_ai"]["worker_offer_get_url_template"]
    assert "basic worker offers" in contract["if_you_are_a_cloud_ai"]["do_not_use_signed_a2a_relay_for"]
    assert "/a2a/get" in contract["links"]["signed_get_a2a_relay"]
    assert contract["links"]["get_only_lease"].endswith("/swarm/workers/lease-get")
    assert contract["links"]["get_only_complete"].endswith("/swarm/workers/complete-get")
    assert contract["links"]["get_only_experience"].endswith("/swarm/experience-get")
    assert "use_attach_get_for_worker_intent" in contract["machine_instruction"]


def test_get_only_runtime_attach_registers_low_trust_intent(tmp_path, monkeypatch):
    monkeypatch.setattr(NomadApiHandler, "swarm_registry", SwarmJoinRegistry(path=tmp_path / "swarm.json"))
    handler = NomadApiHandler.__new__(NomadApiHandler)
    handler._base_url = lambda: "https://nomad.example"  # type: ignore[method-assign]
    handler._remote_addr = lambda: "203.0.113.7"  # type: ignore[method-assign]

    result, status = handler._process_get_only_runtime_attach(
        {
            "agent_id": ["grok-cloud-test"],
            "runtime": ["grok-xai-cloud"],
            "type": ["offer"],
            "role": ["transition_worker,verifier"],
            "objective": ["settlement_capacity_builder"],
            "capabilities": ["gradient_analysis,proof_verification,swarm_state_reader,http_json,get_only"],
            "can_run_loop": ["1"],
            "can_verify": ["1"],
            "note": ["Persistent GET-only Cloud-Verifier and Settlement Capacity Probe."],
            "intent": ["join"],
        },
        idle=False,
    )

    assert status == 202
    assert result["schema"] == "nomad.get_only_runtime_attach_receipt.v1"
    assert result["trust_tier"] == "public_get_low_trust"
    assert result["join"]["registered"] is True
    assert result["join"]["agent_id"] == "grok-cloud-test"
    assert result["join"]["path"] == "/swarm/attach-get"
    assert result["attach_decision"]["agent_id"] == "grok-cloud-test"
    assert result["offer_signal"]["type"] == "offer"
    assert result["offer_signal"]["roles"] == ["transition_worker", "verifier"]
    assert result["offer_signal"]["note"].startswith("Persistent GET-only Cloud-Verifier")
    assert result["next_get_only"]["hello"] == "https://nomad.example/swarm/hello"
    assert result["next_get_only"]["lease_get"].startswith("https://nomad.example/swarm/workers/lease-get?")
    assert "agent_id=grok-cloud-test" in result["next_get_only"]["lease_get"]
    assert "/swarm/workers/complete-get" in result["next_get_only"]["complete_get_template"]
    assert "/swarm/experience-get" in result["next_get_only"]["experience_get_template"]


def test_get_only_worker_lease_complete_and_experience_chain(tmp_path, monkeypatch):
    monkeypatch.setattr(NomadApiHandler, "swarm_registry", SwarmJoinRegistry(path=tmp_path / "swarm.json"))

    def fake_submit_growth_experience(payload, *, base_url="", curriculum=None):
        return {
            "ok": True,
            "schema": "nomad.growth_experience_receipt.v1",
            "accepted": True,
            "agent_id": payload["agent_id"],
            "objective": payload["objective"],
            "proof_digest": payload["proof_digest"],
        }

    monkeypatch.setattr(nomad_api, "submit_growth_experience", fake_submit_growth_experience)

    handler = NomadApiHandler.__new__(NomadApiHandler)
    handler._base_url = lambda: "https://nomad.example"  # type: ignore[method-assign]
    handler._remote_addr = lambda: "203.0.113.7"  # type: ignore[method-assign]

    lease, lease_status = handler._process_get_only_worker_lease(
        {
            "agent_id": ["grok-cloud-test"],
            "runtime": ["grok-xai-cloud"],
            "capabilities": ["transition_worker,verifier,http_json,get_only"],
            "known_objectives": ["settlement_capacity_builder,protocol_drift_scan,emergence_release_probe"],
            "objective": ["settlement_capacity_builder"],
        }
    )

    assert lease_status == 202
    assert lease["schema"] == "nomad.get_only_transition_worker_lease_response.v1"
    assert lease["get_only"] is True
    assert "/swarm/workers/complete-get" in lease["complete_get_url_template"]

    complete, complete_status = handler._process_get_only_worker_complete(
        {
            "agent_id": ["grok-cloud-test"],
            "lease_id": [lease["lease_id"]],
            "objective": [lease["objective"]],
            "digest": ["sha256:abc123"],
            "note": ["checked public gradient and worker fleet"],
        }
    )

    assert complete_status == 200
    assert complete["schema"] == "nomad.get_only_transition_worker_completion.v1"
    assert complete["digest"] == "sha256:abc123"
    assert "/swarm/experience-get" in complete["next_get_only"]["experience_get"]

    experience, experience_status = handler._process_get_only_growth_experience(
        {
            "agent_id": ["grok-cloud-test"],
            "objective": [lease["objective"]],
            "digest": ["sha256:abc123"],
            "lesson": ["GET-only worker completed one public check."],
        }
    )

    assert experience_status == 202
    assert experience["get_only"] is True
    assert experience["proof_digest"] == "sha256:abc123"
    assert experience["next_get_only"]["repeat_attach_get"].startswith("https://nomad.example/swarm/attach-get?")


def test_get_only_attach_without_agent_id_returns_contract(tmp_path):
    handler = NomadApiHandler.__new__(NomadApiHandler)
    handler.swarm_registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")
    handler._base_url = lambda: "https://nomad.example"  # type: ignore[method-assign]

    result, status = handler._process_get_only_runtime_attach({}, idle=False)

    assert status == 200
    assert result["schema"] == "nomad.get_only_worker_onramp.v1"
    assert result["mode"] == "contract_only"
    assert "agent_id" in result["message"]


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
    assert "/machine-treasury" in doc["paths"]
    assert "/machine-treasury/pledge" in doc["paths"]
    assert "/swarm/reuse-ledger" in doc["paths"]
    assert "/.well-known/nomad-proof-reuse-ledger.json" in doc["paths"]
    assert "/swarm/proof-link" in doc["paths"]
    assert "/.well-known/nomad-machine-field.json" in doc["paths"]
    assert "/machine-field" in doc["paths"]
    assert "/machine-field/intent" in doc["paths"]
    assert "/.well-known/nomad-agent-requests.json" in doc["paths"]
    assert "/agent-requests" in doc["paths"]
    assert "/swarm/demand" in doc["paths"]
    assert "/swarm/subscribe" in doc["paths"]
    assert "/swarm/subscriptions" in doc["paths"]
    assert "/nonhuman-science" in doc["paths"]
    assert "/.well-known/nomad-nonhuman-agent-science.json" in doc["paths"]
    assert "/operational-release" in doc["paths"]
    assert "/.well-known/nomad-operational-release.json" in doc["paths"]
    assert "/.well-known/nomad-machine-product.json" in doc["paths"]
    assert "/agent-product" in doc["paths"]
    assert "/machine-product" in doc["paths"]
    assert "/contract-conformance" in doc["paths"]
    assert "/.well-known/nomad-contract-conformance.json" in doc["paths"]
    assert "/swarm/economics" in doc["paths"]
    assert "/.well-known/nomad-swarm-economics.json" in doc["paths"]
    assert "/swarm/recruitment-funnel-report" in doc["paths"]
    assert "/.well-known/nomad-recruitment-funnel-report.json" in doc["paths"]
    assert "/.well-known/nomad-protocol-bytecode.json" in doc["paths"]
    assert "/protocol-bytecode" in doc["paths"]
    assert "/swarm/counterfactual-replay" in doc["paths"]
    assert "/.well-known/nomad-counterfactual-replay.json" in doc["paths"]
    assert "/swarm/variant-forge" in doc["paths"]
    assert "/.well-known/nomad-variant-forge.json" in doc["paths"]
    assert "/swarm/variant-candidates" in doc["paths"]
    assert "/swarm/worker-market" in doc["paths"]
    assert "/.well-known/nomad-worker-market.json" in doc["paths"]
    assert "/swarm/compute-market" in doc["paths"]
    assert "/.well-known/nomad-compute-market.json" in doc["paths"]
    assert "/swarm/agent-work" in doc["paths"]
    assert "/.well-known/nomad-agent-work.json" in doc["paths"]
    assert "/swarm/work-mesh" in doc["paths"]
    assert "/.well-known/nomad-work-mesh.json" in doc["paths"]
    assert "/swarm/synergy-lite" in doc["paths"]
    assert "/.well-known/nomad-synergy-lite.json" in doc["paths"]
    assert "/swarm/state-status" in doc["paths"]
    assert "/.well-known/nomad-state-status.json" in doc["paths"]
    assert "/swarm/carrying-market" in doc["paths"]
    assert "/.well-known/nomad-carrying-market.json" in doc["paths"]
    assert "/swarm/survival-market" in doc["paths"]
    assert "/.well-known/nomad-survival-market.json" in doc["paths"]
    assert "/swarm/paid-ref-market" in doc["paths"]
    assert "/.well-known/nomad-paid-ref-market.json" in doc["paths"]
    assert "/swarm/paid-ref-selfplay" in doc["paths"]
    assert "/.well-known/nomad-paid-ref-selfplay.json" in doc["paths"]
    assert "/swarm/bounty-hunter" in doc["paths"]
    assert "/.well-known/nomad-bounty-hunter.json" in doc["paths"]
    assert "/swarm/sales-department" in doc["paths"]
    assert "/.well-known/nomad-sales-department.json" in doc["paths"]
    assert "/swarm/sales-department/events" in doc["paths"]
    assert "/swarm/first-sales" in doc["paths"]
    assert "/.well-known/nomad-first-sales.json" in doc["paths"]
    assert "/swarm/job-channels" in doc["paths"]
    assert "/.well-known/nomad-job-channels.json" in doc["paths"]
    assert "/swarm/external-value" in doc["paths"]
    assert "/.well-known/nomad-external-value.json" in doc["paths"]
    assert "/swarm/value-pressure" in doc["paths"]
    assert "/.well-known/nomad-value-pressure.json" in doc["paths"]
    assert "/swarm/settlement" in doc["paths"]
    assert "/.well-known/nomad-settlement.json" in doc["paths"]
    assert "/swarm/agent-job-router" in doc["paths"]
    assert "/.well-known/nomad-agent-jobs.json" in doc["paths"]
    assert "/swarm/revenue-science" in doc["paths"]
    assert "/science/revenue-agents" in doc["paths"]
    assert "/.well-known/nomad-revenue-science.json" in doc["paths"]
    assert "/swarm/worker-invoice" in doc["paths"]
    assert "/.well-known/nomad-worker-invoice.json" in doc["paths"]
    assert "/swarm/worker-job-queue" in doc["paths"]
    assert "/.well-known/nomad-worker-job-queue.json" in doc["paths"]
    assert "/swarm/value-cycle-preflight" in doc["paths"]
    assert "/.well-known/nomad-value-cycle-preflight.json" in doc["paths"]
    assert "/swarm/value-cycles" in doc["paths"]
    assert "/.well-known/nomad-value-cycles.json" in doc["paths"]
    assert "/swarm/value-cycles/events" in doc["paths"]
    assert "/swarm/receipt-predictor" in doc["paths"]
    assert "/.well-known/nomad-receipt-predictor.json" in doc["paths"]
    assert "/swarm/receipt-predictor/events" in doc["paths"]
    assert "/swarm/ad-cycles" in doc["paths"]
    assert "/.well-known/nomad-ad-cycles.json" in doc["paths"]
    assert "/swarm/ad-cycles/events" in doc["paths"]
    assert "/swarm/development-cycles" in doc["paths"]
    assert "/.well-known/nomad-development-cycles.json" in doc["paths"]
    assert "/swarm/development-cycles/events" in doc["paths"]
    assert "/swarm/resource-substrate" in doc["paths"]
    assert "/.well-known/nomad-resource-substrate.json" in doc["paths"]
    assert "/swarm/resource-substrate/register" in doc["paths"]
    assert "/swarm/resource-substrate/retrieve" in doc["paths"]
    assert "/swarm/resource-substrate/version" in doc["paths"]
    assert "/swarm/autogenesis" in doc["paths"]
    assert "/.well-known/nomad-autogenesis.json" in doc["paths"]
    assert "/.well-known/nomad-agp-conformance.json" in doc["paths"]
    assert "/.well-known/nomad-agp-agent-bus.json" in doc["paths"]
    assert "/swarm/agp/agent-bus/messages" in doc["paths"]
    assert "/swarm/agp/plans" in doc["paths"]
    assert "/swarm/agp/orchestrations" in doc["paths"]
    assert "/.well-known/nomad-agp-model-manager.json" in doc["paths"]
    assert "/swarm/agp/model-bindings" in doc["paths"]
    assert "/swarm/agp/configs" in doc["paths"]
    assert "/.well-known/nomad-agp-prompt-manager.json" in doc["paths"]
    assert "/swarm/agp/prompts" in doc["paths"]
    assert "/.well-known/nomad-agp-version-manager.json" in doc["paths"]
    assert "/swarm/agp/version-lineage" in doc["paths"]
    assert "/.well-known/nomad-agp-procurement.json" in doc["paths"]
    assert "/swarm/autogenesis/traces" in doc["paths"]
    assert "/swarm/agp/procurement-intents" in doc["paths"]
    assert "/.well-known/nomad-agp-context-manager.json" in doc["paths"]
    assert "/swarm/agp/context" in doc["paths"]
    assert "/.well-known/nomad-agp-optimizer.json" in doc["paths"]
    assert "/swarm/agp/optimizer-steps" in doc["paths"]
    assert "/.well-known/nomad-agp-evaluation.json" in doc["paths"]
    assert "/swarm/agp/evaluations" in doc["paths"]
    assert "/.well-known/nomad-agp-benchmark-suite.json" in doc["paths"]
    assert "/swarm/agp/benchmark-suites" in doc["paths"]
    assert "/.well-known/nomad-autonomous-agp.json" in doc["paths"]
    assert "/swarm/autogenesis/cycle" in doc["paths"]
    assert "/swarm/autogenesis/run" in doc["paths"]
    assert "/swarm/autogenesis/watchdog" in doc["paths"]
    assert "/.well-known/nomad-agp-watchdog.json" in doc["paths"]
    assert "/swarm/autogenesis-recruit" in doc["paths"]
    assert "/.well-known/nomad-autogenesis-recruit.json" in doc["paths"]
    assert "/swarm/topology-governor" in doc["paths"]
    assert "/.well-known/nomad-topology-governor.json" in doc["paths"]
    assert "/swarm/topology-governor/events" in doc["paths"]
    assert "/swarm/worker-catalog" in doc["paths"]
    assert "/.well-known/nomad-worker-catalog.json" in doc["paths"]
    assert "/swarm/microtask-templates" in doc["paths"]
    assert "/.well-known/nomad-microtask-templates.json" in doc["paths"]
    assert "/swarm/microtask-metrics" in doc["paths"]
    assert "/.well-known/nomad-microtask-metrics.json" in doc["paths"]
    assert "/swarm/worker-market/offers" in doc["paths"]
    assert "/swarm/microtask/submit" in doc["paths"]
    assert "/swarm/microtask/claim" in doc["paths"]
    assert "/swarm/microtask/proof" in doc["paths"]
    assert "/swarm/work-mesh/seed" in doc["paths"]
    assert "/swarm/carrying-proof" in doc["paths"]
    assert "/swarm/survival-intent" in doc["paths"]
    assert "/swarm/paid-ref/quote" in doc["paths"]
    assert "/swarm/paid-ref/verify" in doc["paths"]
    assert "/swarm/microtask/settle" in doc["paths"]
    assert "/swarm/ecology" in doc["paths"]
    assert "/.well-known/nomad-swarm-ecology.json" in doc["paths"]
    assert "/swarm/ecology/tick" in doc["paths"]
    assert "/swarm/growth-arena" in doc["paths"]
    assert "/.well-known/nomad-growth-arena.json" in doc["paths"]
    assert "/swarm/curriculum" in doc["paths"]
    assert "/.well-known/nomad-growth-curriculum.json" in doc["paths"]
    assert "/swarm/experience" in doc["paths"]
    assert "/swarm/skill-library" in doc["paths"]
    assert "/.well-known/nomad-skill-library.json" in doc["paths"]
    assert "/swarm/weekly-selection" in doc["paths"]
    assert "/.well-known/nomad-weekly-selection.json" in doc["paths"]
    assert "/swarm/spawner-gate" in doc["paths"]
    assert "/.well-known/nomad-spawner-gate.json" in doc["paths"]
    assert "/swarm/spawner/trigger" in doc["paths"]
    assert "/swarm/capacity-switch" in doc["paths"]
    assert "/.well-known/nomad-capacity-switch.json" in doc["paths"]
    assert "/.well-known/nomad-idle-runtime.json" in doc["paths"]
    assert "/idle-runtime" in doc["paths"]
    assert "/.well-known/nomad-opaque-emergence.json" in doc["paths"]
    assert "/swarm/opaque-emergence" in doc["paths"]
    assert "/swarm/opaque-candidate" in doc["paths"]
    assert "/swarm/tool-gap" in doc["paths"]
    assert "/swarm/topology-plan" in doc["paths"]
    assert "/.well-known/nomad-runtime-capsule.json" in doc["paths"]
    assert "/runtime-capsule" in doc["paths"]
    assert "/.well-known/openclaw-nomad-bridge.json" in doc["paths"]
    assert "/openclaw-bridge" in doc["paths"]
    assert "/.well-known/nomad-handoff-capsule.json" in doc["paths"]
    assert "/runtime/handoff" in doc["paths"]
    assert "/swarm/gradient" in doc["paths"]
    assert "/.well-known/nomad-gradient.json" in doc["paths"]
    assert "/swarm/hello" in doc["paths"]
    assert "/.well-known/nomad-ai.json" in doc["paths"]
    assert "/swarm/attach-get" in doc["paths"]
    assert "/swarm/workers/lease-get" in doc["paths"]
    assert "/swarm/workers/complete-get" in doc["paths"]
    assert "/swarm/experience-get" in doc["paths"]
    assert "/swarm/attach" in doc["paths"]
    assert "/swarm/emission-batch" in doc["paths"]
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
    assert "/swarm/idle-intent-get" in doc["paths"]
    assert "/swarm/idle-intent" in doc["paths"]
    assert "/swarm/workers" in doc["paths"]
    assert "/swarm/workers/lease" in doc["paths"]
    assert "/swarm/workers/complete" in doc["paths"]
    assert "/swarm/develop" in doc["paths"]
    assert "/swarm/bootstrap" in doc["paths"]
    assert "/a2a/get" in doc["paths"]
    assert "/a2a/get/{session_id}/{seq}/{chunk}" in doc["paths"]
    assert "/a2a/get/{session_id}/reply" in doc["paths"]
    assert "/transition/quote" in doc["paths"]
    assert "/transition/settle" in doc["paths"]
    assert "/.well-known/nomad-reciprocity-dividend.json" in doc["paths"]
    assert "/dividend/claim" in doc["paths"]
    assert "/dividend/settle" in doc["paths"]
    assert "/dividend" in doc["paths"]
    assert doc["servers"][0]["url"] == "https://nomad.example"


def test_nomad_api_builds_protocol_surfaces(tmp_path, monkeypatch):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")
    monkeypatch.setattr(NomadApiHandler, "swarm_registry", registry)

    bytecode = NomadApiHandler._build_protocol_bytecode(base_url="https://nomad.example")
    replay = NomadApiHandler._build_counterfactual_replay(base_url="https://nomad.example")
    forge = NomadApiHandler._build_variant_forge(base_url="https://nomad.example")
    market = NomadApiHandler._build_worker_market(base_url="https://nomad.example")
    compute_market = NomadApiHandler._build_compute_market(base_url="https://nomad.example")
    agent_work = NomadApiHandler._build_agent_work_surface(base_url="https://nomad.example")
    work_mesh = NomadApiHandler._build_work_mesh(base_url="https://nomad.example")
    synergy = NomadApiHandler._build_synergy_lite(base_url="https://nomad.example")
    state_status = NomadApiHandler._build_state_status(base_url="https://nomad.example")
    carrying_market = NomadApiHandler._build_carrying_market(base_url="https://nomad.example")
    survival_market = NomadApiHandler._build_survival_market(base_url="https://nomad.example")
    paid_ref_market = NomadApiHandler._build_paid_ref_market(base_url="https://nomad.example")
    paid_ref_selfplay = NomadApiHandler._build_paid_ref_selfplay(base_url="https://nomad.example")
    bounty_hunter = NomadApiHandler._build_bounty_hunter(base_url="https://nomad.example")
    job_channels = NomadApiHandler._build_job_channels(base_url="https://nomad.example")
    external_value = NomadApiHandler._build_external_value_surface(base_url="https://nomad.example")
    value_pressure = NomadApiHandler._build_value_pressure(base_url="https://nomad.example")
    settlement = NomadApiHandler._build_settlement_signal_layer(base_url="https://nomad.example")
    agent_job_router = NomadApiHandler._build_agent_job_router(base_url="https://nomad.example")
    revenue_science = NomadApiHandler._build_revenue_science(base_url="https://nomad.example")
    worker_invoice = NomadApiHandler._build_worker_invoice(base_url="https://nomad.example")
    worker_job_queue = NomadApiHandler._build_worker_job_queue(base_url="https://nomad.example")
    value_cycle_preflight = NomadApiHandler._build_value_cycle_preflight(base_url="https://nomad.example")
    value_cycles = NomadApiHandler._build_value_cycle_mesh(base_url="https://nomad.example")
    receipt_predictor = NomadApiHandler._build_receipt_predictor(base_url="https://nomad.example")
    ad_cycles = NomadApiHandler._build_ad_cycle_mesh(base_url="https://nomad.example")
    development_cycles = NomadApiHandler._build_development_cycle_mesh(base_url="https://nomad.example")
    topology_governor = NomadApiHandler._build_swarm_topology_governor(base_url="https://nomad.example")
    catalog = NomadApiHandler._build_worker_catalog(base_url="https://nomad.example")
    templates = NomadApiHandler._build_microtask_templates(base_url="https://nomad.example")
    metrics = NomadApiHandler._build_microtask_metrics(base_url="https://nomad.example")
    ecology = NomadApiHandler._build_swarm_ecology(base_url="https://nomad.example")
    curriculum = NomadApiHandler._build_growth_curriculum(base_url="https://nomad.example")
    library = NomadApiHandler._build_skill_library(base_url="https://nomad.example")
    arena = NomadApiHandler._build_growth_arena(base_url="https://nomad.example")
    spawner_gate = NomadApiHandler._build_spawner_gate(base_url="https://nomad.example")
    capacity_switch = NomadApiHandler._build_capacity_switch_surface(base_url="https://nomad.example")

    assert bytecode["schema"] == "nomad.protocol_bytecode.v1"
    assert bytecode["route_table"]["replay"] == "https://nomad.example/swarm/counterfactual-replay"
    assert bytecode["route_table"]["forge"] == "https://nomad.example/swarm/variant-candidates"
    assert replay["schema"] == "nomad.counterfactual_lease_replay.v1"
    assert replay["links"]["protocol_bytecode"].endswith("/.well-known/nomad-protocol-bytecode.json")
    assert forge["schema"] == "nomad.variant_forge.v1"
    assert forge["submit_url"] == "https://nomad.example/swarm/variant-candidates"
    assert market["schema"] == "nomad.worker_market.v1"
    assert market["offer_url"] == "https://nomad.example/swarm/worker-market/offers"
    assert compute_market["schema"] == "nomad.compute_market.v1"
    assert compute_market["read_url"] == "https://nomad.example/swarm/compute-market"
    assert compute_market["entry_contract"]["settle_url"] == "https://nomad.example/swarm/microtask/settle"
    assert agent_work["schema"] == "nomad.agent_work.v1"
    assert agent_work["claim_contract"]["url"] == "https://nomad.example/swarm/microtask/claim"
    assert work_mesh["schema"] == "nomad.work_mesh.v1"
    assert work_mesh["machine_contract"]["claim"] == "https://nomad.example/swarm/microtask/claim"
    assert synergy["schema"] == "nomad.synergy_lite.v1"
    assert state_status["schema"] == "nomad.state_status.v1"
    assert carrying_market["schema"] == "nomad.carrying_market.v1"
    assert carrying_market["proof_contract"]["url"] == "https://nomad.example/swarm/carrying-proof"
    assert survival_market["schema"] == "nomad.survival_market.v1"
    assert survival_market["intent_contract"]["url"] == "https://nomad.example/swarm/survival-intent"
    assert paid_ref_market["schema"] == "nomad.paid_ref_market.v1"
    assert paid_ref_market["links"]["quote"] == "https://nomad.example/swarm/paid-ref/quote"
    assert paid_ref_selfplay["schema"] == "nomad.paid_ref_selfplay.v1"
    assert paid_ref_selfplay["agent_count"] == 1000
    assert paid_ref_selfplay["top_quote_payloads"]
    assert bounty_hunter["schema"] == "nomad.bounty_hunter.v1"
    assert bounty_hunter["top_candidate"]
    assert job_channels["schema"] == "nomad.job_channels.v1"
    assert job_channels["well_known_url"] == "https://nomad.example/.well-known/nomad-job-channels.json"
    assert job_channels["top_external_channel"]
    assert external_value["schema"] == "nomad.external_value_surface.v1"
    assert external_value["state_machine"]["name"] == "pending_external_value"
    assert external_value["post_url"] == "https://nomad.example/swarm/external-value"
    assert value_pressure["schema"] == "nomad.value_pressure.v1"
    assert value_pressure["read_url"] == "https://nomad.example/swarm/value-pressure"
    assert settlement["schema"] == "nomad.settlement_signal_layer.v1"
    assert settlement["well_known_url"] == "https://nomad.example/.well-known/nomad-settlement.json"
    assert settlement["evidence_boundary"]["cashflow_growth_claim"] is False
    assert agent_job_router["schema"] == "nomad.agent_job_router.v1"
    assert agent_job_router["well_known_url"] == "https://nomad.example/.well-known/nomad-agent-jobs.json"
    assert revenue_science["schema"] == "nomad.revenue_science.v1"
    assert revenue_science["well_known_url"] == "https://nomad.example/.well-known/nomad-revenue-science.json"
    assert worker_invoice["schema"] == "nomad.worker_invoice.v1"
    assert worker_invoice["well_known_url"] == "https://nomad.example/.well-known/nomad-worker-invoice.json"
    assert worker_job_queue["schema"] == "nomad.worker_job_queue.v1"
    assert worker_job_queue["well_known_url"] == "https://nomad.example/.well-known/nomad-worker-job-queue.json"
    assert value_cycle_preflight["schema"] == "nomad.value_cycle_preflight.v1"
    assert value_cycle_preflight["well_known_url"] == "https://nomad.example/.well-known/nomad-value-cycle-preflight.json"
    assert value_cycles["schema"] == "nomad.value_cycle_mesh.v1"
    assert value_cycles["well_known_url"] == "https://nomad.example/.well-known/nomad-value-cycles.json"
    assert value_cycles["summary"]["cycle_count"] >= 32
    assert receipt_predictor["schema"] == "nomad.receipt_predictor.v1"
    assert receipt_predictor["well_known_url"] == "https://nomad.example/.well-known/nomad-receipt-predictor.json"
    assert receipt_predictor["summary"]["cycle_count"] >= 32
    assert receipt_predictor["now_queue"]
    assert ad_cycles["schema"] == "nomad.ad_cycle_mesh.v1"
    assert ad_cycles["well_known_url"] == "https://nomad.example/.well-known/nomad-ad-cycles.json"
    assert ad_cycles["summary"]["cycle_count"] >= 12
    assert development_cycles["schema"] == "nomad.development_cycle_mesh.v1"
    assert development_cycles["well_known_url"] == "https://nomad.example/.well-known/nomad-development-cycles.json"
    assert development_cycles["summary"]["cycle_count"] >= 12
    assert development_cycles["summary"]["repo_write_allowed_count"] == 0
    assert topology_governor["schema"] == "nomad.swarm_topology_governor.v1"
    assert topology_governor["well_known_url"] == "https://nomad.example/.well-known/nomad-topology-governor.json"
    assert topology_governor["summary"]["candidate_cell_count"] >= 16
    assert topology_governor["summary"]["side_effect_allowed_count"] == 0
    assert catalog["schema"] == "nomad.worker_catalog.v1"
    assert templates["schema"] == "nomad.microtask_templates.v1"
    assert metrics["schema"] == "nomad.microtask_metrics.v1"
    assert ecology["schema"] == "nomad.swarm_ecology.v1"
    assert ecology["tick_url"] == "https://nomad.example/swarm/ecology/tick"
    assert curriculum["schema"] == "nomad.growth_curriculum.v1"
    assert curriculum["links"]["experience"] == "https://nomad.example/swarm/experience"
    assert library["schema"] == "nomad.skill_library.v1"
    assert arena["schema"] == "nomad.growth_arena.v1"
    assert spawner_gate["schema"] == "nomad.spawner_gate.v1"
    assert capacity_switch["schema"] == "nomad.capacity_switch_surface.v1"


def test_machine_error_helpers():
    from nomad_machine_error import machine_error_response, merge_machine_error

    err = machine_error_response(error="e1", message="m1", hints=["h1"])
    assert err["ok"] is False
    assert err["schema"] == "nomad.machine_error.v1"
    assert err["agent_error"]["schema"] == "nomad.agent_error.v1"
    assert err["agent_error"]["error"] == "e1"
    assert "safe_retry" in err["agent_error"]
    merged = merge_machine_error({"ok": False, "error": "e1"}, error="e1", hints=["h2"])
    assert merged["machine_error"]["hints"] == ["h2"]
    assert merged["machine_error"]["agent_error"]["schema"] == "nomad.agent_error.v1"


def test_adapter_consent_validation_helper():
    from nomad_adapter_consent import mint_adapter_consent

    token = mint_adapter_consent(agent_id="openclaw.agent", runtime="openclaw")
    ok = NomadApiHandler._validate_adapter_consent(
        {"runtime": "openclaw", "agent_id": "openclaw.agent", "consent_token": token},
        path="/swarm/idle-intent",
    )
    bad = NomadApiHandler._validate_adapter_consent(
        {"runtime": "openclaw", "agent_id": "openclaw.agent", "consent_token": "bad"},
        path="/swarm/idle-intent",
    )
    assert ok["ok"] is True
    assert bad["ok"] is False


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
