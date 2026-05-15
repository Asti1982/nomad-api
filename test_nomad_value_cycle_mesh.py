from nomad_value_cycle_mesh import build_value_cycle_mesh_surface, evaluate_value_cycle_event


def _external_summary():
    return {
        "schema": "nomad.external_value_summary.v1",
        "revenue_recognized_usd_total": 0.0,
        "latest_by_external": [
            {
                "external_id": "gh_pr:owner/repo#12",
                "stage": "merged",
                "work_url": "https://github.com/owner/repo/pull/12",
            }
        ],
    }


def _queue():
    return {
        "schema": "nomad.worker_job_queue.v1",
        "summary": {
            "job_count": 5,
            "executable_now_count": 3,
            "active_nonpaid_external_count": 1,
            "top_job_type": "settlement_reconcile",
        },
        "jobs": [
            {"job_id": "job-settle", "job_type": "settlement_reconcile"},
            {"job_id": "job-scan", "job_type": "paid_channel_scan"},
            {"job_id": "job-patch", "job_type": "bounded_patch_attempt"},
        ],
    }


def _preflight(public_ready=False):
    return {
        "schema": "nomad.value_cycle_preflight.v1",
        "wallet_gate": {"ready": True, "public_receive_ref_type": "rtc_address"},
        "cycle_gate": {
            "read_only_scout_allowed": True,
            "public_claim_allowed": public_ready,
            "submit_after_proof_allowed": public_ready,
            "paid_record_allowed": False,
        },
        "blocking_conditions": [] if public_ready else ["external_program_authorizes_this_work"],
    }


def _science():
    return {
        "schema": "nomad.revenue_science.v1",
        "entry_experiment": {
            "experiment_id": "rev-exp",
            "action": "await_payment_receipt",
            "measurement_plan": {"primary_metric": "paid_stage_receipt_acceptance_with_positive_amount_usd"},
            "decision_model": {"bandit_priority": 1.25},
        },
    }


def test_value_cycle_mesh_exposes_more_paid_only_cycles():
    out = build_value_cycle_mesh_surface(
        base_url="https://nomad.example",
        external_value_summary=_external_summary(),
        worker_job_queue=_queue(),
        value_cycle_preflight=_preflight(),
        revenue_science=_science(),
        effective_channels={"mode": "count_effective_channels_not_agent_votes"},
        job_channels={"top_external_channel": {"channel_id": "issuehunt", "entry_url": "https://example.com/issues"}},
    )

    assert out["schema"] == "nomad.value_cycle_mesh.v1"
    assert out["well_known_url"] == "https://nomad.example/.well-known/nomad-value-cycles.json"
    assert out["event_url"] == "https://nomad.example/swarm/value-cycles/events"
    assert out["summary"]["cycle_count"] >= 32
    assert out["entry_cycle"]["cycle_id"] == "settlement_tail_to_paid_receipt"
    assert out["entry_cycle"]["worker_job_ids"] == ["job-settle"]
    assert all(cycle["revenue_guard"]["counts_as_revenue"] is False for cycle in out["cycles"])
    assert any(cycle["cycle_id"] == "effective_channel_shadow_ad_cycle" for cycle in out["cycles"])
    assert any(cycle["cycle_id"] == "invoice_paid_work_receipt" for cycle in out["cycles"])
    assert any(cycle["cycle_id"] == "algora_bounty_pr_award" for cycle in out["cycles"])
    assert any(cycle["cycle_id"] == "api_integration_paid_setup" for cycle in out["cycles"])
    assert any(cycle["cycle_id"] == "proof_pack_resale_license" for cycle in out["cycles"])
    assert any(cycle["cycle_id"] == "negative_result_paid_report" for cycle in out["cycles"])


def test_value_cycle_event_blocks_public_cycle_until_preflight_green():
    mesh = build_value_cycle_mesh_surface(
        base_url="https://nomad.example",
        external_value_summary=_external_summary(),
        worker_job_queue=_queue(),
        value_cycle_preflight=_preflight(public_ready=False),
    )
    out = evaluate_value_cycle_event(
        {
            "cycle_id": "authorized_bounty_pr_to_paid",
            "stage": "submit",
            "source_url": "https://github.com/owner/repo/issues/1",
            "terms_url": "https://github.com/owner/repo/security/policy",
            "proof_digest": "sha256:proof",
        },
        base_url="https://nomad.example",
        mesh_surface=mesh,
    )

    assert out["schema"] == "nomad.value_cycle_event_receipt.v1"
    assert out["value_cycle_allowed"] is False
    assert out["decision"] == "hold_public_side_effect_until_preflight_green"
    assert out["counts_as_revenue"] is False


def test_value_cycle_event_allows_paid_receipt_candidate_without_mutating_ledger():
    mesh = build_value_cycle_mesh_surface(
        base_url="https://nomad.example",
        external_value_summary=_external_summary(),
        worker_job_queue=_queue(),
        value_cycle_preflight=_preflight(public_ready=True),
    )
    out = evaluate_value_cycle_event(
        {
            "cycle_id": "settlement_tail_to_paid_receipt",
            "stage": "paid",
            "external_id": "gh_pr:owner/repo#12",
            "work_url": "https://github.com/owner/repo/pull/12",
            "proof_digest": "sha256:proof-paid",
            "settlement_ref": "receipt:https://example.com/r/12",
            "amount_usd": 25.0,
        },
        base_url="https://nomad.example",
        mesh_surface=mesh,
    )

    assert out["value_cycle_allowed"] is True
    assert out["decision"] == "allow_value_cycle_transition_shadow_or_ledger_candidate"
    assert out["counts_as_revenue"] is True
    assert out["external_value_payload_candidate"]["stage"] == "paid"
    assert out["hard_rule"].startswith("this_receipt_does_not_mutate_ledgers")


def test_value_cycle_event_builds_work_receipt_candidate_for_invoice_cycle():
    mesh = build_value_cycle_mesh_surface(
        base_url="https://nomad.example",
        external_value_summary=_external_summary(),
        worker_job_queue=_queue(),
        value_cycle_preflight=_preflight(public_ready=True),
    )
    out = evaluate_value_cycle_event(
        {
            "cycle_id": "invoice_paid_work_receipt",
            "stage": "paid",
            "work_id": "worker-job-42",
            "source_url": "https://example.com/work/42",
            "proof_digest": "sha256:worker-proof",
            "settlement_ref": "receipt:https://example.com/paid/42",
            "amount_usd": 42.0,
        },
        base_url="https://nomad.example",
        mesh_surface=mesh,
    )

    assert out["value_cycle_allowed"] is True
    assert out["work_receipt_payload_candidate"]["work_type"] == "worker_invoice"
    assert out["work_receipt_payload_candidate"]["amount_usd"] == 42.0
    assert out["external_value_payload_candidate"] == {}


def test_cli_value_cycles_returns_surface_and_event_gate():
    from nomad_cli import run_once

    surface = run_once(["value-cycles", "--base-url", "https://nomad.example", "--json"])
    event = run_once(
        [
            "value-cycles",
            "evaluate",
            "--base-url",
            "https://nomad.example",
            "--cycle-id",
            "settlement_tail_to_paid_receipt",
            "--stage",
            "prove",
            "--proof-digest",
            "sha256:proof",
            "--source-url",
            "https://example.com/work",
            "--json",
        ]
    )

    assert surface["schema"] == "nomad.value_cycle_mesh.v1"
    assert surface["summary"]["cycle_count"] >= 32
    assert event["schema"] == "nomad.value_cycle_event_receipt.v1"
    assert event["cycle_id"] == "settlement_tail_to_paid_receipt"
