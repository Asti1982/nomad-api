import importlib.util
from pathlib import Path


def _load_checker():
    path = Path(__file__).resolve().parent / "public" / "downloads" / "check_nomad_swarm_readiness.py"
    spec = importlib.util.spec_from_file_location("nomad_swarm_readiness_module", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_check_treats_2xx_http_status_as_ready(monkeypatch):
    mod = _load_checker()

    def fake_http_json(method, url, payload=None, timeout=12.0):
        if url.endswith("/health"):
            return {"ok": True, "http_status": 200}
        if url.endswith("/.well-known/nomad-runtime-capsule.json"):
            return {"schema": "nomad.runtime_capsule.v1", "ok": True, "http_status": 200}
        if url.endswith("/.well-known/openclaw-nomad-bridge.json"):
            return {"schema": "nomad.openclaw_bridge_contract.v1", "ok": True, "http_status": 200}
        if url.endswith("/swarm/gradient"):
            return {"schema": "nomad.recruitment_gradient.v1", "state_vector": {"field_strength": 0.6}, "ok": True, "http_status": 200}
        if url.endswith("/.well-known/nomad-protocol-bytecode.json"):
            return {
                "schema": "nomad.protocol_bytecode.v1",
                "opcodes": [
                    {"op": "FORGE"},
                    {"op": "MARKET"},
                    {"op": "ECO"},
                    {"op": "CURRIC"},
                    {"op": "SKILL"},
                    {"op": "EXP"},
                ],
                "ok": True,
                "http_status": 200,
            }
        if url.endswith("/swarm/variant-forge"):
            return {"schema": "nomad.variant_forge.v1", "ok": True, "http_status": 200}
        if url.endswith("/swarm/worker-market"):
            return {"schema": "nomad.worker_market.v1", "ok": True, "http_status": 200}
        if url.endswith("/swarm/ecology"):
            return {"schema": "nomad.swarm_ecology.v1", "ok": True, "http_status": 200}
        if url.endswith("/swarm/growth-arena"):
            return {"schema": "nomad.growth_arena.v1", "ok": True, "http_status": 200}
        if url.endswith("/swarm/curriculum"):
            return {"schema": "nomad.growth_curriculum.v1", "ok": True, "http_status": 200}
        if url.endswith("/swarm/skill-library"):
            return {"schema": "nomad.skill_library.v1", "ok": True, "http_status": 200}
        if url.endswith("/swarm"):
            return {"ok": True, "agent_pull_contract": {"attach_now_score": 1.2, "attach_threshold": 1.1}, "http_status": 200}
        if url.endswith("/swarm/workers"):
            return {"http_status": 200}
        if url.endswith("/swarm/attach"):
            return {"attach": True, "http_status": 202}
        if url.endswith("/runtime/handoff"):
            return {"http_status": 200}
        if url.endswith("/swarm/workers/lease"):
            return {"http_status": 202}
        if url.endswith("/swarm/variant-candidates"):
            return {"schema": "nomad.variant_candidate_receipt.v1", "http_status": 202}
        if url.endswith("/swarm/worker-market/offers"):
            return {"schema": "nomad.worker_market_offer_receipt.v1", "http_status": 202}
        if url.endswith("/swarm/ecology/tick"):
            return {"schema": "nomad.ecology_tick_receipt.v1", "http_status": 202}
        if url.endswith("/swarm/experience"):
            return {"schema": "nomad.growth_experience_receipt.v1", "http_status": 202}
        return {"ok": False, "http_status": 404}

    monkeypatch.setattr(mod, "http_json", fake_http_json)
    out = mod.check("https://nomad.example", timeout=2.0)
    assert out["attach_ready"] is True
    assert out["handoff_ready"] is True
    assert out["lease_ready"] is True
    assert out["protocol_bytecode_ok"] is True
    assert out["variant_candidate_ready"] is True
    assert out["worker_market_offer_ready"] is True
    assert out["ecology_tick_ready"] is True
    assert out["growth_arena_ok"] is True
    assert out["growth_experience_ready"] is True
    assert out["decision"] == "attach"
