from nomad_work_receipts import (
    build_treasury_policy_surface,
    build_work_receipt_surface,
    record_work_receipt,
    summarize_work_receipts,
)


def test_unpaid_work_receipt_is_nontransferable_and_not_revenue(tmp_path):
    ledger = tmp_path / "work_receipts.jsonl"

    out = record_work_receipt(
        {
            "agent_id": "codex.worker",
            "work_id": "gh_pr:example/repo#1",
            "work_type": "external_value",
            "objective": "settlement_capacity_builder",
            "external_value_stage": "merged",
            "work_url": "https://github.com/example/repo/pull/1",
            "proof_digest": "sha256:proof-merged",
            "verifier_trace_digest": "sha256:trace-merged",
            "idempotency_key": "receipt-unpaid-1",
        },
        ledger_path=ledger,
    )

    assert out["ok"] is True
    assert out["schema"] == "nomad.work_receipt.v1"
    assert out["receipt_class"] == "claim_credit"
    assert out["transferability"] == "non_transferable"
    assert out["treasury_allocation"]["paid_confirmed"] is False
    assert out["treasury_allocation"]["recognized_revenue_usd"] == 0.0
    assert out["treasury_allocation"]["token_units_minted"] == 0.0
    assert out["reputation_units"] > 0

    summary = summarize_work_receipts(ledger_path=ledger)
    assert summary["receipt_count"] == 1
    assert summary["recognized_revenue_usd"] == 0.0
    assert summary["token_units_minted"] == 0.0


def test_paid_work_receipt_routes_90_10_without_minting_token(tmp_path):
    ledger = tmp_path / "work_receipts.jsonl"

    out = record_work_receipt(
        {
            "agent_id": "codex.worker",
            "work_id": "taskbounty:paid-1",
            "work_type": "external_value",
            "objective": "settlement_capacity_builder",
            "external_value_stage": "paid",
            "work_url": "https://example.com/task/paid-1",
            "proof_digest": "sha256:proof-paid",
            "amount_usd": 100.0,
            "settlement_ref": "receipt:https://example.com/receipts/paid-1",
            "idempotency_key": "receipt-paid-1",
        },
        ledger_path=ledger,
    )

    alloc = out["treasury_allocation"]
    assert out["ok"] is True
    assert out["receipt_class"] == "settlement_credit"
    assert alloc["paid_confirmed"] is True
    assert alloc["recognized_revenue_usd"] == 100.0
    assert alloc["locked_treasury_usd"] == 90.0
    assert alloc["worker_settlement_pool_usd"] == 10.0
    assert alloc["token_units_minted"] == 0.0

    summary = summarize_work_receipts(ledger_path=ledger)
    assert summary["recognized_revenue_usd"] == 100.0
    assert summary["locked_treasury_usd"] == 90.0
    assert summary["worker_settlement_pool_usd"] == 10.0


def test_work_receipt_rejects_incomplete_paid_claims_and_secrets(tmp_path):
    ledger = tmp_path / "work_receipts.jsonl"

    incomplete = record_work_receipt(
        {
            "agent_id": "codex.worker",
            "work_id": "paid-without-receipt",
            "external_value_stage": "paid",
            "proof_digest": "sha256:proof",
            "amount_usd": 10.0,
        },
        ledger_path=ledger,
    )
    secret = record_work_receipt(
        {
            "agent_id": "codex.worker",
            "work_id": "secret-leak",
            "proof_digest": "sha256:proof",
            "api_key": "sk-test",
        },
        ledger_path=ledger,
    )

    assert incomplete["ok"] is False
    assert incomplete["error"] == "paid_receipt_incomplete"
    assert secret["ok"] is False
    assert secret["error"] == "secret_shaped_payload"


def test_work_receipt_idempotency_conflict_safe(tmp_path):
    ledger = tmp_path / "work_receipts.jsonl"
    payload = {
        "agent_id": "agent.one",
        "work_id": "same-work",
        "work_url": "https://example.com/work",
        "proof_digest": "sha256:proof",
        "idempotency_key": "same-key",
    }

    first = record_work_receipt(payload, ledger_path=ledger)
    replay = record_work_receipt(payload, ledger_path=ledger)
    conflict = record_work_receipt({**payload, "proof_digest": "sha256:different"}, ledger_path=ledger)

    assert first["ok"] is True
    assert replay["idempotent_replay"] is True
    assert replay["receipt_id"] == first["receipt_id"]
    assert conflict["ok"] is False
    assert conflict["error"] == "idempotency_key_conflict"


def test_surfaces_expose_token_preflight_and_policy_gates(tmp_path):
    ledger = tmp_path / "work_receipts.jsonl"
    record_work_receipt(
        {
            "agent_id": "agent.one",
            "work_id": "signal-only",
            "work_url": "https://example.com/work",
        },
        ledger_path=ledger,
    )
    summary = summarize_work_receipts(ledger_path=ledger)

    surface = build_work_receipt_surface(base_url="https://www.syndiode.com", summary=summary)
    policy = build_treasury_policy_surface(base_url="https://www.syndiode.com", work_receipt_summary=summary)

    assert surface["schema"] == "nomad.work_receipt_surface.v1"
    assert surface["state_machine"]["transferability"] == "non_transferable"
    assert policy["schema"] == "nomad.treasury_policy.v1"
    assert policy["public_offer"] is False
    assert policy["profit_promise"] is False
    assert policy["token_units_minted"] == 0.0
    assert policy["allocation_rule"]["locked_machine_treasury_ratio"] == 0.9
