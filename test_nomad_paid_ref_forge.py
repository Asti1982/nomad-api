from nomad_paid_ref_forge import build_paid_ref_market, paid_ref_task_payload, quote_paid_ref, verify_paid_ref
from nomad_survival_market import build_survival_market, submit_survival_intent


def _survival(tmp_path):
    return build_survival_market(
        base_url="https://nomad.example",
        carrying_market={"top_contract": {"contract_id": "state_relay_digest_quorum"}},
        microtask_metrics={"totals": {"settled_eur": 0.0}},
        intent_ledger_path=tmp_path / "survival.jsonl",
    )


def test_paid_ref_market_exposes_quote_verify_lifecycle(tmp_path):
    survival = _survival(tmp_path)

    out = build_paid_ref_market(
        base_url="https://nomad.example",
        survival_market=survival,
        ledger_path=tmp_path / "paidref.jsonl",
    )

    assert out["schema"] == "nomad.paid_ref_market.v1"
    assert out["links"]["quote"] == "https://nomad.example/swarm/paid-ref/quote"
    assert out["links"]["verify"] == "https://nomad.example/swarm/paid-ref/verify"
    assert out["top_packet_binding"]["packet_id"] == "agent_blocker_unblock_pack"
    assert out["paid_ref_rule"].startswith("quote_refs_are_not_revenue")


def test_paid_ref_quote_creates_authorization_not_revenue(tmp_path):
    survival = _survival(tmp_path)
    payload = {
        "agent_id": "agent.buyer",
        "packet_id": "agent_blocker_unblock_pack",
        "buyer_ref": "buyer-a",
        "problem": "Agent cannot pay an x402 API after a retry loop.",
    }
    task_payload = paid_ref_task_payload(payload, survival_market=survival)
    task_response = {
        "ok": True,
        "task": {
            "task_id": "svc-paidref",
            "status": "awaiting_payment",
            "requester_agent": "agent.buyer",
            "metadata": task_payload["metadata"],
            "payment": {
                "payment_reference": "NOMAD_TASK:svc-paidref",
                "amount_native": 0.01,
                "x402": {"configured": False},
            },
        },
    }

    quote = quote_paid_ref(
        payload,
        base_url="https://nomad.example",
        survival_market=survival,
        task_response=task_response,
        ledger_path=tmp_path / "paidref.jsonl",
    )

    assert quote["schema"] == "nomad.paid_ref_quote_receipt.v1"
    assert quote["accepted"] is True
    assert quote["paid_ref_candidate"].startswith("nomad-paid-candidate-")
    assert quote["survival_intent_after_verify"]["paid_ref"].startswith("<returned_by")


def test_paid_ref_verify_mints_revenue_payload_only_after_payment(tmp_path):
    survival = _survival(tmp_path)
    unpaid_task = {
        "ok": True,
        "task": {
            "task_id": "svc-unpaid",
            "status": "awaiting_payment",
            "requester_agent": "agent.buyer",
            "metadata": {"packet_id": "agent_blocker_unblock_pack", "buyer_ref": "buyer-a"},
            "payment": {"verification": None},
        },
    }

    rejected = verify_paid_ref(
        {"agent_id": "agent.buyer", "packet_id": "agent_blocker_unblock_pack", "task_id": "svc-unpaid"},
        base_url="https://nomad.example",
        survival_market=survival,
        task_response=unpaid_task,
        ledger_path=tmp_path / "paidref.jsonl",
    )
    assert rejected["accepted"] is False
    assert rejected["paid_ref"] == ""

    paid_task = {
        "ok": True,
        "task": {
            "task_id": "svc-paid",
            "status": "paid",
            "requester_agent": "agent.buyer",
            "metadata": {"packet_id": "agent_blocker_unblock_pack", "buyer_ref": "buyer-a"},
            "payment": {
                "tx_hash": "0x" + "1" * 64,
                "amount_native": 0.01,
                "verification": {"ok": True, "status": "verified"},
            },
        },
    }

    verified = verify_paid_ref(
        {"agent_id": "agent.buyer", "packet_id": "agent_blocker_unblock_pack", "task_id": "svc-paid"},
        base_url="https://nomad.example",
        survival_market=survival,
        task_response=paid_task,
        ledger_path=tmp_path / "paidref.jsonl",
    )
    assert verified["accepted"] is True
    assert verified["paid_ref"].startswith("nomad-paid-ref-")
    assert verified["survival_intent_payload"]["payment_verifier_digest"].startswith("nomad-payver-")

    receipt = submit_survival_intent(
        verified["survival_intent_payload"],
        base_url="https://nomad.example",
        survival_market=survival,
        intent_ledger_path=tmp_path / "survival.jsonl",
    )
    assert receipt["counts_as_revenue"] is True
    assert receipt["settlement_eur"] == 9.0
