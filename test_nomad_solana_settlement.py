from nomad_solana_settlement import (
    build_solana_settlement_surface,
    create_solana_pay_intent,
    verify_solana_tx_receipt,
)


RECIPIENT = "So11111111111111111111111111111111111111112"
REFERENCE = "11111111111111111111111111111111"


def test_solana_settlement_surface_has_no_signing_boundary(monkeypatch):
    monkeypatch.setenv("NOMAD_SOLANA_RECEIVER", RECIPIENT)

    surface = build_solana_settlement_surface(base_url="https://nomad.example")

    assert surface["schema"] == "nomad.solana_settlement.v1"
    assert surface["configured"] is True
    assert surface["truth_boundary"]["no_private_keys"] is True
    assert surface["links"]["intent"] == "https://nomad.example/swarm/settlement/solana-pay-intents"


def test_solana_pay_intent_encodes_reference_and_amount():
    intent = create_solana_pay_intent(
        {
            "recipient": RECIPIENT,
            "reference": REFERENCE,
            "amount_sol": "0.01",
            "task_id": "nomad-test-payment",
        },
        base_url="https://nomad.example",
    )

    assert intent["accepted"] is True
    assert intent["expected_lamports"] == 10_000_000
    assert intent["solana_pay_url"].startswith(f"solana:{RECIPIENT}?")
    assert "reference=11111111111111111111111111111111" in intent["solana_pay_url"]
    assert intent["proof_digest"].startswith("sha256:")


def test_solana_tx_receipt_verifies_balance_delta_and_builds_resolution_payload():
    transaction = {
        "slot": 123,
        "blockTime": 1_700_000_000,
        "transaction": {
            "message": {
                "accountKeys": [
                    {"pubkey": "Payer111111111111111111111111111111111111"},
                    {"pubkey": RECIPIENT},
                    {"pubkey": REFERENCE},
                ]
            }
        },
        "meta": {
            "err": None,
            "preBalances": [2_000_000_000, 5_000_000, 1],
            "postBalances": [1_989_000_000, 15_000_000, 1],
        },
    }

    receipt = verify_solana_tx_receipt(
        {
            "tx_signature": "4x" + ("a" * 86),
            "recipient": RECIPIENT,
            "reference": REFERENCE,
            "amount_sol": "0.01",
            "task_id": "nomad-test-payment",
            "work_url": "https://nomad.example/work",
        },
        base_url="https://nomad.example",
        transaction=transaction,
    )

    assert receipt["accepted"] is True
    assert receipt["delta"]["observed_lamports_delta"] == 10_000_000
    assert receipt["delta"]["reference_verified"] is True
    payload = receipt["resolution_ladder_payload"]
    assert payload["receipt"]["amount"] == 0.01
    assert payload["receipt"]["currency"] == "SOL"
    assert payload["receipt"]["paid_receipt_ref"].startswith("https://solscan.io/tx/")
    assert payload["side_effect_scope"] == "runtime_weight_receipt_only"
