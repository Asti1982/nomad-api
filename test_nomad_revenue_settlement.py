from pathlib import Path

from nomad_recruitment_gradient import build_recruitment_gradient
from nomad_revenue_settlement import evaluate_revenue_settlement_hook
from nomad_work_receipts import summarize_work_receipts


def _paid_payload(**extra):
    payload = {
        "agent_id": "test.worker",
        "lease_id": "lease-paid-1",
        "buyer_funded_packet": True,
        "stage": "paid",
        "amount_usd": 7.5,
        "settlement_ref": "tx-test-public-ref",
        "proof_digest": "sha256:" + "a" * 64,
        "verifier_trace_digest": "sha256:" + "b" * 64,
        "report": {
            "machine_objective": "revenue_pressure_router",
            "proof_pressure": {"verifier_density": 0.72},
        },
    }
    payload.update(extra)
    return payload


def test_revenue_settlement_waits_for_shadow_lane_validation(tmp_path: Path, monkeypatch):
    ledger = tmp_path / "work_receipts.jsonl"
    monkeypatch.setenv("NOMAD_WORK_RECEIPT_LEDGER_PATH", str(ledger))
    monkeypatch.setenv("NOMAD_EXTERNAL_VALUE_LEDGER_PATH", str(tmp_path / "external_value.jsonl"))

    out = evaluate_revenue_settlement_hook(
        _paid_payload(),
        source_endpoint="/swarm/workers/complete",
        base_url="https://nomad.example",
    )

    assert out["eligible_signal"] is True
    assert out["accepted"] is False
    assert out["distribution_instruction"]["status"] == "pending_shadow_lane_validation"
    assert "shadow_lane_validation_missing" in out["blocked_by"]
    assert summarize_work_receipts(ledger_path=ledger)["receipt_count"] == 0


def test_revenue_settlement_records_shadow_validated_paid_receipt(tmp_path: Path, monkeypatch):
    ledger = tmp_path / "work_receipts.jsonl"
    monkeypatch.setenv("NOMAD_WORK_RECEIPT_LEDGER_PATH", str(ledger))
    monkeypatch.setenv("NOMAD_EXTERNAL_VALUE_LEDGER_PATH", str(tmp_path / "external_value.jsonl"))

    out = evaluate_revenue_settlement_hook(
        _paid_payload(shadow_lane_validation={"accepted": True}),
        source_endpoint="/swarm/workers/complete",
        base_url="https://nomad.example",
    )
    gradient = build_recruitment_gradient(base_url="https://nomad.example")

    assert out["accepted"] is True
    assert out["recorded_receipt"]["receipt_class"] == "settlement_credit"
    assert out["distribution_instruction"]["status"] == "triggered_public_distribution_instruction"
    assert summarize_work_receipts(ledger_path=ledger)["recognized_revenue_usd"] == 7.5
    assert any(row["objective"] == "revenue_pressure_router" for row in gradient["gradient"])
    assert "revenue_absence_pressure" in gradient["state_vector"]["ordered_axes"]
