import json

from nomad_lead_workbench import NomadLeadWorkbench


def test_lead_workbench_prioritizes_and_works_products_and_conversions(tmp_path):
    conversions_path = tmp_path / "conversions.json"
    products_path = tmp_path / "products.json"
    state_path = tmp_path / "lead_workbench.json"
    conversions_path.write_text(
        json.dumps(
            {
                "conversions": {
                    "conv-1": {
                        "conversion_id": "conv-1",
                        "created_at": "2026-04-30T00:00:00+00:00",
                        "status": "private_draft_needs_approval",
                        "lead": {
                            "title": "Public issue needs agent help",
                            "url": "https://github.com/example/agent/issues/1",
                            "service_type": "compute_auth",
                            "monetizable_now": True,
                        },
                        "score": {"value": 11, "fit": "strong", "reasons": ["buyer_intent"]},
                        "route": {
                            "approval_gate": "APPROVE_LEAD_HELP=comment",
                        },
                        "customer_next_step": {
                            "ask": "Approve public comment or provide machine endpoint.",
                            "required_input": "`ERROR=<message>`",
                        },
                    }
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    products_path.write_text(
        json.dumps(
            {
                "products": {
                    "prod-1": {
                        "product_id": "prod-1",
                        "updated_at": "2026-04-30T01:00:00+00:00",
                        "status": "private_offer_needs_approval",
                        "name": "Nomad Compute Unlock Pack",
                        "pain_type": "compute_auth",
                        "priority_score": 507,
                        "variant_sku": "nomad.compute_unlock_pack.test",
                        "sellable_channels": ["private_catalog"],
                        "free_value": {"safe_now": ["Probe provider without secrets."]},
                        "paid_offer": {
                            "delivery": "diagnosis plus fallback plan",
                            "price_native": 0.01,
                            "trigger": "PLAN_ACCEPTED=true plus ERROR",
                        },
                        "approval_boundary": {"approval_required": True, "approval_gate": "NOMAD_OPERATOR_GRANT includes productization"},
                    }
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    workbench = NomadLeadWorkbench(
        conversion_path=conversions_path,
        product_path=products_path,
        state_path=state_path,
    )

    result = workbench.status(limit=2, work=True)

    assert result["schema"] == "nomad.lead_workbench.v1"
    assert result["worked_count"] == 2
    assert result["queue"][0]["kind"] == "product_offer"
    assert result["queue"][0]["safe_next_action"] == "reuse_private_offer_in_agent_attractor"
    assert result["self_help"]["worked_this_call"] == 2
    assert result["self_help"]["latest_learning"]["by_service_type"]["compute_auth"] == 2
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert "product:prod-1" in state["worked_item_ids"]
    assert state["lead_learning"]["human_gate_count"] == 2
