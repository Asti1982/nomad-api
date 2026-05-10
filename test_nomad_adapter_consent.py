from nomad_adapter_consent import adapter_consent_required, mint_adapter_consent, verify_adapter_consent


def test_adapter_consent_mint_and_verify_roundtrip():
    token = mint_adapter_consent(agent_id="openclaw.agent", runtime="openclaw", now_ts=1000)
    verdict = verify_adapter_consent(
        token=token,
        agent_id="openclaw.agent",
        runtime="openclaw",
        now_ts=1200,
    )
    assert verdict["ok"] is True


def test_adapter_consent_rejects_expired_token():
    token = mint_adapter_consent(agent_id="openclaw.agent", runtime="openclaw", now_ts=1000)
    verdict = verify_adapter_consent(
        token=token,
        agent_id="openclaw.agent",
        runtime="openclaw",
        now_ts=999999,
    )
    assert verdict["ok"] is False


def test_adapter_consent_required_for_openclaw_idle_endpoints():
    needed = adapter_consent_required({"runtime": "openclaw"}, path="/swarm/idle-intent")
    assert needed is True

