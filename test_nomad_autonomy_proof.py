from nomad_autonomy_proof import AutonomyProofHarness


def test_autonomy_proof_accepts_payment_followup_artifact():
    report = {
        "service": {
            "awaiting_payment_task_ids": ["svc-await"],
            "payment_followups": [{"task_id": "svc-await"}],
        },
        "payment_followup_queue": {"reason": "send_disabled_or_public_url_missing"},
    }

    proof = AutonomyProofHarness().evaluate(report, previous_state={})

    assert proof["schema"] == "nomad.autonomy_proof.v1"
    assert proof["cycle_was_useful"] is True
    assert proof["money_progress"] is True
    assert proof["useful_artifact_created"] == "payment_followup_draft"
    assert proof["useless_cycle_streak"] == 0
    assert proof["stop_self_deception"] is False


def test_autonomy_proof_blocks_after_three_empty_cycles():
    report = {
        "service": {"awaiting_payment_task_ids": []},
        "self_improvement": {},
    }

    proof = AutonomyProofHarness().evaluate(
        report,
        previous_state={"useless_cycle_streak": 2},
    )

    assert proof["cycle_was_useful"] is False
    assert proof["status"] == "blocked"
    assert proof["useless_cycle_streak"] == 3
    assert proof["should_pause_autonomy"] is True
    assert proof["next_required_unlock"] == "PROVIDE_REAL_BLOCKER_OR_APPROVE_NEXT_ACTION=yes"
