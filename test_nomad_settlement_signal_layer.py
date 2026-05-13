from nomad_cli import run_once
from nomad_external_value import append_external_value_event
from nomad_settlement_signal_layer import (
    build_settlement_signal_layer,
    compile_public_settlement_packet,
    influence_operator_catalog,
)


def _summary():
    return {
        "schema": "nomad.external_value_summary.v1",
        "event_tail_count": 6,
        "distinct_externals": 3,
        "revenue_recognized_usd_total": 16.88,
        "latest_by_external": [
            {
                "external_id": "gh_pr:Scottcjn/Rustchain#4542",
                "agent_id": "nomad.test",
                "stage": "merged",
                "work_url": "https://github.com/Scottcjn/Rustchain/pull/4542",
                "last_generated_at": "2026-05-12T00:00:00+00:00",
                "nomad_proof_receipt_digest": "r1",
                "revenue_recognized_usd": 0.0,
            },
            {
                "external_id": "gh_pr:Scottcjn/bottube#993",
                "agent_id": "nomad.test",
                "stage": "submitted",
                "work_url": "https://github.com/Scottcjn/bottube/pull/993",
                "last_generated_at": "2026-05-13T00:00:00+00:00",
                "nomad_proof_receipt_digest": "r2",
                "revenue_recognized_usd": 0.0,
            },
            {
                "external_id": "gh_pr:test/repo#7",
                "agent_id": "nomad.test",
                "stage": "paid",
                "work_url": "https://github.com/test/repo/pull/7",
                "last_generated_at": "2026-05-13T00:10:00+00:00",
                "nomad_proof_receipt_digest": "r3",
                "revenue_recognized_usd": 16.88,
            },
        ],
    }


def _reconcile():
    return {
        "schema": "nomad.external_value_reconcile.v1",
        "followups": [
            {
                "external_id": "gh_pr:Scottcjn/Rustchain#4542",
                "current_stage": "merged",
                "work_url": "https://github.com/Scottcjn/Rustchain/pull/4542",
                "followup": {
                    "action": "await_payment_receipt",
                    "priority": 0.92,
                    "target_stage": "paid",
                    "required_evidence": ["trusted_payment_receipt", "positive_amount_usd"],
                },
            }
        ],
    }


def test_settlement_layer_prioritizes_merged_payment_receipt_without_fake_revenue():
    surface = build_settlement_signal_layer(
        base_url="https://nomad.example",
        external_summary=_summary(),
        external_reconcile=_reconcile(),
    )

    assert surface["schema"] == "nomad.settlement_signal_layer.v1"
    assert surface["read_url"] == "https://nomad.example/swarm/settlement"
    assert surface["top"]["external_id"] == "gh_pr:Scottcjn/Rustchain#4542"
    assert surface["top"]["action"] == "await_payment_receipt"
    assert surface["top"]["score_components"]["stage_multiplier"] > 1.0
    assert surface["summary"]["revenue_recognized_usd_total"] == 16.88
    assert surface["next_action_receipt"]["stage_guard"] == "paid_only_counts_as_revenue"


def test_truthful_influence_patterns_are_enabled_without_cashflow_claim():
    surface = build_settlement_signal_layer(
        external_summary=_summary(),
        external_reconcile=_reconcile(),
    )

    assert surface["evidence_boundary"]["cashflow_growth_claim"] is False
    assert surface["evidence_boundary"]["cashflow_guarantee_available"] is False
    assert surface["human_membrane_contract"]["name"] == "truthful_influence_settlement_membrane"
    assert surface["top"]["policy"]["cashflow_score_multiplier"] == 1.0
    assert surface["top"]["policy"]["next_action"] == "compile_truthful_influence_packet"
    assert "truthful_human_pattern_use" in surface["top"]["policy"]["evidence_rule"]
    assert "salience_ordering_of_real_facts" in surface["top"]["policy"]["allowed"]
    assert surface["operator_activation_contract"]["cashflow_learning_rule"].startswith("increase operator weight only after paid receipts")
    assert "truthful_norm_anchor" in surface["operator_activation_contract"]["disabled_by_default"]
    assert any(item["id"] == "agency_control_knob" for item in surface["influence_operator_catalog"])


def test_cli_settlement_next_uses_external_value_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_EXTERNAL_VALUE_LEDGER_PATH", str(tmp_path / "ev.jsonl"))
    eid = "gh_pr:test/repo#1"
    assert append_external_value_event(
        {
            "agent_id": "nomad.test",
            "external_id": eid,
            "stage": "found",
            "work_url": "",
            "proof_digest": "",
            "verifier_trace_digest": "",
        }
    )["ok"]

    out = run_once(["settlement", "next", "--json"])

    assert out["schema"] == "nomad.settlement_next_action.v1"
    assert out["summary"]["distinct_externals"] == 1
    assert out["next_action_receipt"]["stage_guard"] == "paid_only_counts_as_revenue"


def test_public_packet_compiler_is_unsent_and_not_cashflow_claim():
    surface = build_settlement_signal_layer(
        external_summary=_summary(),
        external_reconcile=_reconcile(),
    )
    packet = compile_public_settlement_packet(surface["top"], packet_type="followup")

    assert packet["schema"] == "nomad.settlement_public_packet.v1"
    assert packet["send_policy"] == "manual_or_contract_bound_send_only"
    assert packet["cashflow_growth_claim"] is False
    assert packet["mechanism"] == "truthful_psychological_pattern_use_not_persona_simulation"
    assert any(item["name"] == "salience" for item in packet["influence_patterns"])
    assert any(item["id"] == "agency_control_knob" for item in packet["operator_sequence"])
    assert "Revenue note" in packet["body"]
    assert "fake_affiliation" in packet["forbidden"]


def test_settlement_packet_uses_receipt_boundary_and_one_decision_unit():
    surface = build_settlement_signal_layer(
        external_summary=_summary(),
        external_reconcile=_reconcile(),
    )
    packet = compile_public_settlement_packet(surface["top"], packet_type="settlement")

    assert packet["packet_type"] == "settlement"
    assert packet["decision_unit"]["max_human_actions_requested"] == 1
    assert packet["settlement_reference"]["paid_boundary"] == "approval_or_merge_is_not_revenue"
    assert "payment_claim_without_receipt" in packet["forbidden"]
    assert "approval or merge is not recorded as revenue" in packet["body"]


def test_influence_operator_catalog_disables_unproven_norm_anchor_by_default():
    catalog = influence_operator_catalog()
    by_id = {item["id"]: item for item in catalog}

    assert by_id["truthful_norm_anchor"]["default_enabled"] is False
    assert by_id["friction_collapse"]["evidence_grade"].endswith("cashflow_unproven")
    assert "false_revenue_count" in by_id["receipt_boundary_lock"]["metric"]


def test_cli_settlement_operators_exposes_science_sources():
    out = run_once(["settlement", "operators", "--json"])

    assert out["schema"] == "nomad.settlement_influence_operators.v1"
    assert out["cashflow_growth_claim"] is False
    assert any(item["id"] == "agency_control_knob" for item in out["operators"])
    assert any(item["id"] == "algorithm_aversion_adjustability" for item in out["science_sources"])
