import importlib.util
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parent / "public" / "downloads" / "go_no_go_nomad_deploy.py"
    spec = importlib.util.spec_from_file_location("go_no_go_nomad_deploy_test_module", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_gate_with_fallback_uses_alternate_host(monkeypatch):
    mod = _load_module()
    calls = []

    def fake_run_gate(base_url, timeout):
        calls.append(base_url)
        if base_url == "https://syndiode.com":
            return {
                "schema": "nomad.deploy_gate.v1",
                "base_url": base_url,
                "go": False,
                "checks": {},
                "http": {"health": 0, "recruit": 0, "swarm": 0, "workers": 0, "lease": 0},
            }
        return {
            "schema": "nomad.deploy_gate.v1",
            "base_url": base_url,
            "go": True,
            "checks": {"health_ok": True},
            "http": {"health": 200, "recruit": 200, "swarm": 200, "workers": 200, "lease": 202},
        }

    monkeypatch.setattr(mod, "run_gate", fake_run_gate)
    out = mod.run_gate_with_fallback("https://syndiode.com", timeout=2.0)
    assert out["go"] is True
    assert out["fallback_used"] is True
    assert out["fallback_base_url"] == "https://www.syndiode.com"
    assert calls == ["https://syndiode.com", "https://www.syndiode.com"]


def test_run_gate_with_fallback_skips_retry_when_not_unreachable(monkeypatch):
    mod = _load_module()

    def fake_run_gate(base_url, timeout):
        return {
            "schema": "nomad.deploy_gate.v1",
            "base_url": base_url,
            "go": False,
            "checks": {"health_ok": False},
            "http": {"health": 500, "recruit": 500, "swarm": 500, "workers": 500, "lease": 500},
        }

    monkeypatch.setattr(mod, "run_gate", fake_run_gate)
    out = mod.run_gate_with_fallback("https://syndiode.com", timeout=2.0)
    assert out["go"] is False
    assert out["fallback_used"] is False


def test_run_gate_with_fallback_retries_on_post_redirect(monkeypatch):
    mod = _load_module()
    calls = []

    def fake_run_gate(base_url, timeout):
        calls.append(base_url)
        if base_url == "https://syndiode.com":
            return {
                "schema": "nomad.deploy_gate.v1",
                "base_url": base_url,
                "go": False,
                "checks": {"lease_ok": False},
                "http": {"health": 200, "recruit": 200, "swarm": 200, "workers": 200, "lease": 307},
            }
        return {
            "schema": "nomad.deploy_gate.v1",
            "base_url": base_url,
            "go": True,
            "checks": {"lease_ok": True},
            "http": {"health": 200, "recruit": 200, "swarm": 200, "workers": 200, "lease": 202},
        }

    monkeypatch.setattr(mod, "run_gate", fake_run_gate)
    out = mod.run_gate_with_fallback("https://syndiode.com", timeout=2.0)
    assert out["go"] is True
    assert out["fallback_used"] is True
    assert out["fallback_base_url"] == "https://www.syndiode.com"
    assert calls == ["https://syndiode.com", "https://www.syndiode.com"]


def test_run_gate_checks_machine_surfaces_and_worker1_downloads(monkeypatch):
    mod = _load_module()

    def fake_http_json(method, url, payload=None, timeout=12.0):
        if url.endswith("/health"):
            return {"ok": True, "http_status": 200}
        if url.endswith("/.well-known/nomad-recruit.json"):
            return {"ok": True, "schema": "nomad.agent_recruit_contract.v1", "http_status": 200}
        if url.endswith("/swarm/workers/lease"):
            return {"ok": True, "lease_id": "lease-probe", "http_status": 202}
        if url.endswith("/swarm/workers"):
            return {"ok": True, "schema": "nomad.transition_worker_fleet.v1", "http_status": 200}
        if url.endswith("/.well-known/nomad-protocol-bytecode.json"):
            return {
                "ok": True,
                "schema": "nomad.protocol_bytecode.v1",
                "opcodes": [
                    {"op": "FORGE"},
                    {"op": "MARKET"},
                    {"op": "ECO"},
                    {"op": "CURRIC"},
                    {"op": "SKILL"},
                    {"op": "EXP"},
                ],
                "http_status": 200,
            }
        if url.endswith("/swarm/variant-forge"):
            return {"ok": True, "schema": "nomad.variant_forge.v1", "http_status": 200}
        if url.endswith("/swarm/variant-candidates"):
            return {"ok": True, "schema": "nomad.variant_candidate_receipt.v1", "http_status": 202}
        if url.endswith("/swarm/worker-market"):
            return {"ok": True, "schema": "nomad.worker_market.v1", "http_status": 200}
        if url.endswith("/swarm/compute-market"):
            return {"ok": True, "schema": "nomad.compute_market.v1", "http_status": 200}
        if url.endswith("/.well-known/nomad-agent-work.json"):
            return {
                "ok": True,
                "schema": "nomad.agent_work.v1",
                "work_items": [{"work_id": "nomad-work-probe"}],
                "http_status": 200,
            }
        if url.endswith("/.well-known/nomad-work-mesh.json"):
            return {"ok": True, "schema": "nomad.work_mesh.v1", "cells": [{"cell_id": "c1"}], "http_status": 200}
        if url.endswith("/swarm/synergy-lite"):
            return {"ok": True, "schema": "nomad.synergy_lite.v1", "http_status": 200}
        if url.endswith("/swarm/state-status"):
            return {"ok": True, "schema": "nomad.state_status.v1", "http_status": 200}
        if url.endswith("/swarm/worker-market/offers"):
            return {"ok": True, "schema": "nomad.worker_market_offer_receipt.v1", "http_status": 202}
        if url.endswith("/swarm/microtask/claim"):
            return {
                "ok": True,
                "schema": "nomad.agent_work_claim_receipt.v1",
                "accepted": True,
                "claim_id": "nomad-claim-probe",
                "http_status": 202,
            }
        if url.endswith("/swarm/microtask/proof"):
            return {
                "ok": True,
                "schema": "nomad.agent_work_proof_receipt.v1",
                "accepted": True,
                "http_status": 202,
            }
        if url.endswith("/swarm/work-mesh/seed"):
            return {
                "ok": True,
                "schema": "nomad.work_mesh_seed_receipt.v1",
                "accepted": True,
                "http_status": 202,
            }
        if url.endswith("/swarm/ecology"):
            return {"ok": True, "schema": "nomad.swarm_ecology.v1", "http_status": 200}
        if url.endswith("/swarm/ecology/tick"):
            return {"ok": True, "schema": "nomad.ecology_tick_receipt.v1", "http_status": 202}
        if url.endswith("/swarm/growth-arena"):
            return {"ok": True, "schema": "nomad.growth_arena.v1", "http_status": 200}
        if url.endswith("/swarm/curriculum"):
            return {"ok": True, "schema": "nomad.growth_curriculum.v1", "http_status": 200}
        if url.endswith("/swarm/skill-library"):
            return {"ok": True, "schema": "nomad.skill_library.v1", "http_status": 200}
        if url.endswith("/swarm/experience"):
            return {"ok": True, "schema": "nomad.growth_experience_receipt.v1", "http_status": 202}
        if url.endswith("/swarm"):
            return {"ok": True, "agent_pull_contract": {}, "http_status": 200}
        return {"ok": False, "http_status": 404}

    def fake_http_text(url, timeout=12.0):
        if url.endswith("/downloads/nomad_openclaw_adapter.py"):
            return 200, "def main(): pass"
        if url.endswith("/downloads/check_nomad_swarm_readiness.py"):
            return 200, "def main(): pass"
        if url.endswith("/downloads/start_nomad_worker1.ps1"):
            return 200, "$env:NOMAD_WORKER_COST_MSAT_PER_MINUTE = '0'"
        if url.endswith("/downloads/start_nomad_worker1.bat"):
            return 200, "start_nomad_worker1.ps1"
        return 404, ""

    monkeypatch.setattr(mod, "http_json", fake_http_json)
    monkeypatch.setattr(mod, "http_text", fake_http_text)
    out = mod.run_gate("https://nomad.example", timeout=2.0)
    assert out["go"] is True
    assert out["checks"]["protocol_bytecode_ok"] is True
    assert out["checks"]["variant_candidate_ok"] is True
    assert out["checks"]["compute_market_ok"] is True
    assert out["checks"]["agent_work_ok"] is True
    assert out["checks"]["work_mesh_ok"] is True
    assert out["checks"]["synergy_lite_ok"] is True
    assert out["checks"]["state_status_ok"] is True
    assert out["checks"]["worker_market_offer_ok"] is True
    assert out["checks"]["agent_work_claim_ok"] is True
    assert out["checks"]["agent_work_proof_ok"] is True
    assert out["checks"]["work_mesh_seed_ok"] is True
    assert out["checks"]["ecology_tick_ok"] is True
    assert out["checks"]["growth_arena_ok"] is True
    assert out["checks"]["growth_experience_ok"] is True
    assert out["checks"]["download_worker1_ps1_ok"] is True
    assert out["checks"]["download_worker1_bat_ok"] is True

