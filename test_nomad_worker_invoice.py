import json

from nomad_worker_invoice import build_worker_invoice_surface, classify_payout_ref


ADDRESS = "RTCaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
PUBKEY = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def test_worker_invoice_uses_public_env_address_without_private_material(monkeypatch):
    monkeypatch.setenv("NOMAD_BOUNTY_PAYOUT_REF", ADDRESS)
    monkeypatch.setenv("NOMAD_RTC_PUBLIC_KEY_HEX", PUBKEY)

    out = build_worker_invoice_surface(
        base_url="https://nomad.example",
        external_value_summary={"revenue_recognized_usd_total": 1.25},
    )
    rendered = json.dumps(out)

    assert out["schema"] == "nomad.worker_invoice.v1"
    assert out["well_known_url"] == "https://nomad.example/.well-known/nomad-worker-invoice.json"
    assert out["payout"]["configured"] is True
    assert out["payout"]["payout_ref"] == ADDRESS
    assert out["payout"]["payout_ref_type"] == "rtc_native_address"
    assert out["payout"]["public_key_hex"] == PUBKEY
    assert out["revenue_accounting"]["recognized_revenue_usd_total"] == 1.25
    assert "private_key_hex" not in rendered
    assert "private_key_hex_dpapi_current_user" not in rendered
    assert ADDRESS in out["claim_update_template"]


def test_worker_invoice_can_read_public_fields_from_local_wallet(tmp_path, monkeypatch):
    monkeypatch.delenv("NOMAD_BOUNTY_PAYOUT_REF", raising=False)
    wallet = tmp_path / "wallet.json"
    wallet.write_text(
        json.dumps(
            {
                "address": ADDRESS,
                "public_key_hex": PUBKEY,
                "private_key_hex_dpapi_current_user": "secret-local-blob",
            }
        ),
        encoding="utf-8",
    )

    out = build_worker_invoice_surface(base_url="", wallet_path=wallet)
    rendered = json.dumps(out)

    assert out["payout"]["configured"] is True
    assert out["payout"]["source"] == "local_wallet_public_fields"
    assert out["payout"]["payout_ref"] == ADDRESS
    assert out["payout"]["local_wallet_public_probe"]["public_fields_loaded"] is True
    assert "secret-local-blob" not in rendered


def test_worker_invoice_rejects_unsafe_public_ref(monkeypatch):
    monkeypatch.setenv("NOMAD_BOUNTY_PAYOUT_REF", "not safe address with spaces")

    out = build_worker_invoice_surface(base_url="")

    assert out["payout"]["configured"] is False
    assert out["payout"]["validation"]["reason"] == "not_rtc_address_or_safe_miner_id"
    assert out["claim_update_template"] == ""


def test_classify_payout_ref_allows_safe_miner_id():
    out = classify_payout_ref("nomad-worker-codex")

    assert out["ok"] is True
    assert out["kind"] == "miner_id"


def test_cli_worker_invoice_returns_surface(monkeypatch):
    from nomad_cli import run_once

    monkeypatch.setenv("NOMAD_BOUNTY_PAYOUT_REF", ADDRESS)
    out = run_once(["worker-invoice", "--base-url", "https://nomad.example", "--json"])

    assert out["schema"] == "nomad.worker_invoice.v1"
    assert out["read_url"] == "https://nomad.example/swarm/worker-invoice"
    assert out["payout"]["payout_ref"] == ADDRESS
