from nomad_value_cycle_preflight import build_value_cycle_preflight_surface


ADDRESS = "RTCaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def test_value_cycle_preflight_blocks_public_claim_until_terms_verified(monkeypatch):
    monkeypatch.setenv("NOMAD_BOUNTY_PAYOUT_REF", ADDRESS)

    out = build_value_cycle_preflight_surface(base_url="https://nomad.example")

    assert out["schema"] == "nomad.value_cycle_preflight.v1"
    assert out["wallet_gate"]["ready"] is True
    assert out["cycle_gate"]["read_only_scout_allowed"] is True
    assert out["cycle_gate"]["public_claim_allowed"] is False
    assert "external_program_authorizes_this_work" in out["blocking_conditions"]
    assert "payout_terms_visible_before_claim" in out["blocking_conditions"]
    assert "payout_method_accepts_public_ref" in out["blocking_conditions"]


def test_value_cycle_preflight_allows_claim_after_wallet_terms_and_proof(monkeypatch):
    monkeypatch.setenv("NOMAD_BOUNTY_PAYOUT_REF", ADDRESS)

    out = build_value_cycle_preflight_surface(
        base_url="https://nomad.example",
        opportunity_url="https://github.com/example/repo/issues/1",
        program_terms_verified=True,
        payout_terms_verified=True,
        payout_method_compatible=True,
        work_proof_ready=True,
    )

    assert out["cycle_gate"]["public_claim_allowed"] is True
    assert out["cycle_gate"]["submit_after_proof_allowed"] is True
    assert out["blocking_conditions"] == []


def test_value_cycle_preflight_blocks_walletless_public_claim(monkeypatch):
    monkeypatch.delenv("NOMAD_BOUNTY_PAYOUT_REF", raising=False)
    monkeypatch.delenv("NOMAD_WORKER_PAYOUT_REF", raising=False)
    monkeypatch.delenv("NOMAD_RTC_PAYOUT_ADDRESS", raising=False)
    monkeypatch.setenv("NOMAD_RTC_WALLET_PUBLIC_PATH", "missing-wallet-for-test.json")

    out = build_value_cycle_preflight_surface(
        base_url="",
        program_terms_verified=True,
        payout_terms_verified=True,
        payout_method_compatible=True,
        work_proof_ready=True,
    )

    assert out["wallet_gate"]["ready"] is False
    assert out["cycle_gate"]["read_only_scout_allowed"] is True
    assert out["cycle_gate"]["public_claim_allowed"] is False
    assert "wallet_public_receive_ref_configured" in out["blocking_conditions"]


def test_cli_value_cycle_preflight_returns_surface(monkeypatch):
    from nomad_cli import run_once

    monkeypatch.setenv("NOMAD_BOUNTY_PAYOUT_REF", ADDRESS)

    out = run_once(["value-cycle-preflight", "--base-url", "https://nomad.example", "--json"])

    assert out["schema"] == "nomad.value_cycle_preflight.v1"
    assert out["read_url"] == "https://nomad.example/swarm/value-cycle-preflight"
