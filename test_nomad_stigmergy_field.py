from nomad_api import NomadApiHandler
from nomad_stigmergy_field import NomadStigmergyField
from nomad_transition_exchange import NomadTransitionExchange


def test_stigmergy_settlement_mix_increases_mix_count(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_STIGMERGY_STATE_PATH", str(tmp_path / "stig.json"))
    field = NomadStigmergyField()
    assert field.snapshot()["mix_count"] == 0
    r = field.observe_settlement(proof_hash="proof-one", agent_id="agent.a", result_state_hash="target")
    assert r.get("ok") is True
    assert field.snapshot()["mix_count"] == 1


def test_stigmergy_deposit_rate_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_STIGMERGY_STATE_PATH", str(tmp_path / "stig2.json"))
    monkeypatch.setenv("NOMAD_STIGMERGY_DEPOSIT_PER_MINUTE", "2")
    field = NomadStigmergyField()
    vec = [0.1] * 8
    assert field.deposit_trace(agent_id="a1", vector=vec).get("ok") is True
    assert field.deposit_trace(agent_id="a1", vector=vec).get("ok") is True
    third = field.deposit_trace(agent_id="a1", vector=vec)
    assert third.get("ok") is False


def test_exchange_settlement_advances_shared_stigmergy_singleton(tmp_path, monkeypatch):
    """Mirrors nomad_api POST /transition/settle hook: each settle bumps the shared field."""
    monkeypatch.setenv("NOMAD_STIGMERGY_STATE_PATH", str(tmp_path / "stig3.json"))
    NomadApiHandler.stigmergy_field = None
    ex = NomadTransitionExchange()
    q = ex.quote(
        {
            "agent_id": "agent-stig",
            "pain_type": "compute_auth",
            "state_before_hash": "b0",
            "target_state_hash": "t0",
        },
        base_url="https://nomad.example",
        remote_addr="127.0.0.1",
    )
    qid = q["quote"]["quote_id"]
    before = NomadApiHandler._stigmergy().snapshot()["mix_count"]
    result = ex.settle({"quote_id": qid, "result_state_hash": "t0", "proof_artifact_hash": "proof-stig-1"})
    assert result.get("ok") is True
    settled = result.get("settlement") if isinstance(result.get("settlement"), dict) else {}
    NomadApiHandler._stigmergy().observe_settlement(
        proof_hash=str(settled.get("proof_artifact_hash") or ""),
        agent_id=str(settled.get("agent_id") or ""),
        result_state_hash=str(settled.get("result_state_hash") or ""),
    )
    after = NomadApiHandler._stigmergy().snapshot()["mix_count"]
    assert after == before + 1
