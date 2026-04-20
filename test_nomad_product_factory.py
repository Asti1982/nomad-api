from nomad_product_factory import NomadProductFactory


def _conversion(status="private_draft_needs_approval", service_type="tool_failure"):
    guardrail_decision = "deny" if status == "private_draft_needs_approval" else "allow"
    return {
        "conversion_id": "conv-test",
        "created_at": "2026-04-19T12:00:00+00:00",
        "status": status,
        "lead": {
            "title": "AutoGen GuardrailProvider",
            "url": "https://github.com/microsoft/autogen/issues/7405",
            "pain": "tool call interception, approval, audit trail",
            "service_type": service_type,
        },
        "route": {
            "status": status,
            "action": "save_private_draft" if status == "private_draft_needs_approval" else "queue_agent_contact",
            "endpoint_url": "https://agent.example/a2a/message" if status != "private_draft_needs_approval" else "",
            "approval_gate": "APPROVE_LEAD_HELP=comment or APPROVE_LEAD_HELP=pr_plan"
            if status == "private_draft_needs_approval"
            else "",
            "guardrail": {
                "schema": "nomad.guardrail_evaluation.v1",
                "decision": guardrail_decision,
                "ok": guardrail_decision != "deny",
                "results": [
                    {
                        "provider": "approval_boundary_guardrail",
                        "decision": guardrail_decision,
                        "metadata": {
                            "approval_required": "APPROVE_LEAD_HELP=comment or APPROVE_LEAD_HELP=pr_plan"
                        },
                    }
                ],
            },
        },
        "free_value": {
            "value_pack": {
                "schema": "nomad.agent_value_pack.v1",
                "pack_id": "avp-test",
                "painpoint_question": "Which tool call needs interception?",
                "immediate_value": {
                    "safe_now": ["Capture tool name, args, response shape, and approval scope."],
                    "verifier": "Run a dry-run tool call against the policy fixture.",
                },
                "reply_contract": {"accept": "PLAN_ACCEPTED=true"},
                "paid_upgrade": {
                    "trigger": "Reply with PLAN_ACCEPTED=true plus FACT_URL.",
                    "service_type": service_type,
                    "price_native": 0.03,
                    "delivery": "guardrail protocol draft plus verifier checklist",
                },
            },
            "agent_solution": {
                "schema": "nomad.agent_solution.v1",
                "solution_id": "sol-test",
                "pain_type": service_type,
                "title": "Tool Failure Triage",
                "guardrail": {"id": "tool_failure_triage"},
                "nomad_self_apply": {"status": "actionable_now"},
            },
            "rescue_plan": {
                "schema": "nomad.rescue_plan.v1",
                "plan_id": "rescue-test",
                "service_type": service_type,
                "safe_now": ["Create a private repro and policy fixture."],
                "required_input": "`TOOL=<name>` or `ARGS=<json>`",
                "acceptance_criteria": ["No public post without approval."],
                "commercial_next_step": {
                    "package": "Nomad Tool Guardrail Pack",
                    "price_native": 0.03,
                    "delivery": "guardrail protocol draft plus verifier checklist",
                },
                "approval_boundary": {
                    "can_do_without_approval": ["draft diagnosis"],
                    "requires_explicit_approval": ["posting human-facing public comments"],
                },
            },
        },
    }


def test_product_factory_builds_private_product_with_approval_gate(tmp_path):
    factory = NomadProductFactory(path=tmp_path / "products.json")

    result = factory.run(conversions=[_conversion()], limit=1)

    product = result["products"][0]
    assert result["mode"] == "nomad_product_factory"
    assert product["schema"] == "nomad.product.v1"
    assert product["sku"] == "nomad.tool_guardrail_pack"
    assert product["status"] == "private_offer_needs_approval"
    assert product["outreach_blocked_by_approval"] is True
    assert product["approval_boundary"]["approval_required"] is True
    assert product["guardrail_id"] == "tool_failure_triage"
    assert product["service_template"]["create_task_payload"]["metadata"]["product_id"] == product["product_id"]
    assert "PLAN_ACCEPTED=true" in product["sales_motion"]["machine_offer"]


def test_product_factory_marks_machine_endpoint_offer_ready(tmp_path):
    factory = NomadProductFactory(path=tmp_path / "products.json")

    result = factory.run(
        conversions=[_conversion(status="queued_agent_contact", service_type="compute_auth")],
        limit=1,
    )

    product = result["products"][0]
    assert product["sku"] == "nomad.compute_unlock_pack"
    assert product["status"] == "offer_ready"
    assert product["sellable_now"] is True
    assert product["outreach_blocked_by_approval"] is False
    assert product["next_action"]["action"] == "await_plan_accepted_or_create_task"


def test_product_factory_lists_persisted_products_by_status(tmp_path):
    factory = NomadProductFactory(path=tmp_path / "products.json")
    factory.run(conversions=[_conversion()], limit=1)

    listed = factory.list_products(statuses=["private_offer_needs_approval"], limit=10)

    assert listed["mode"] == "nomad_product_list"
    assert listed["stats"]["private_offer_needs_approval"] == 1
    assert len(listed["products"]) == 1
    assert listed["products"][0]["source_lead"]["value_pack_id"] == "avp-test"
