from nomad_worker_job_queue import build_worker_job_queue_surface


def _router():
    return {
        "schema": "nomad.agent_job_router.v1",
        "router_digest": "router-test",
        "packets": [
            {
                "packet_id": "packet-proof",
                "source": "bounty_hunter",
                "source_row_id": "bounty:repo#1:go_public_after_repro",
                "action": "go_public_after_repro",
                "priority_score": 0.9,
                "payload_hint": {"external_id": "bounty:repo#1", "source_url": "https://github.com/o/r/issues/1"},
                "call_sequence": [
                    {
                        "role": "read_bounty_selector",
                        "method": "GET",
                        "path": "/.well-known/nomad-bounty-hunter.json",
                        "url": "https://nomad.example/.well-known/nomad-bounty-hunter.json",
                        "openapi_bound": True,
                    }
                ],
            }
        ],
    }


def _channels():
    return {
        "schema": "nomad.job_channels.v1",
        "channel_digest": "channels-test",
        "top_external_channel": {
            "channel_id": "issuehunt_funded_oss_issue",
            "category": "oss_funded_issue",
            "entry_url": "https://oss.issuehunt.io/issues",
        },
        "read_only_qualification_cycle": {
            "next_read_only_targets": [
                {
                    "channel_id": "issuehunt_funded_oss_issue",
                    "category": "oss_funded_issue",
                    "entry_url": "https://oss.issuehunt.io/issues",
                },
                {
                    "channel_id": "hackerone_bug_bounty",
                    "category": "security_bug_bounty",
                    "entry_url": "https://www.hackerone.com/bug-bounty-programs",
                },
            ]
        },
    }


def _preflight():
    return {
        "schema": "nomad.value_cycle_preflight.v1",
        "preflight_digest": "preflight-test",
        "wallet_gate": {"ready": True, "public_receive_ref_type": "rtc_address"},
        "cycle_gate": {
            "read_only_scout_allowed": True,
            "public_claim_allowed": False,
            "submit_after_proof_allowed": False,
            "paid_record_allowed": False,
        },
        "blocking_conditions": ["external_program_authorizes_this_work"],
    }


def _external_summary():
    return {
        "schema": "nomad.external_value_summary.v1",
        "revenue_recognized_usd_total": 0.0,
        "latest_by_external": [
            {
                "external_id": "gh_pr:owner/repo#12",
                "stage": "approved",
                "work_url": "https://github.com/owner/repo/pull/12",
                "last_generated_at": "2026-05-13T10:00:00+00:00",
            }
        ],
    }


def test_worker_job_queue_builds_artifact_only_jobs_with_locked_public_side_effects():
    out = build_worker_job_queue_surface(
        base_url="https://nomad.example",
        agent_job_router=_router(),
        job_channels=_channels(),
        value_cycle_preflight=_preflight(),
        external_value_summary=_external_summary(),
    )

    assert out["schema"] == "nomad.worker_job_queue.v1"
    assert out["well_known_url"] == "https://nomad.example/.well-known/nomad-worker-job-queue.json"
    assert out["summary"]["active_nonpaid_external_count"] == 1
    assert out["entry_job"]["job_type"] == "settlement_reconcile"

    job_types = {job["job_type"] for job in out["jobs"]}
    assert {
        "settlement_reconcile",
        "duplicate_and_payout_gate_check",
        "paid_channel_scan",
        "bounded_patch_attempt",
    } <= job_types

    patch_job = next(job for job in out["jobs"] if job["job_type"] == "bounded_patch_attempt")
    assert patch_job["worker_role"] == "codex_patch_worker"
    assert patch_job["side_effect_class"] == "local_only"
    assert "public_pr_or_claim_until_preflight_green" in patch_job["blocked_actions"]

    scout_jobs = [job for job in out["jobs"] if job["worker_role"] == "gemini_scout"]
    assert scout_jobs
    assert all(job["read_only"] for job in scout_jobs)
    assert all("submit_report" in job["blocked_actions"] or "public_claim_or_pr" in job["blocked_actions"] for job in scout_jobs)


def test_cli_worker_job_queue_returns_surface():
    from nomad_cli import run_once

    out = run_once(["worker-job-queue", "--base-url", "https://nomad.example", "--json"])

    assert out["schema"] == "nomad.worker_job_queue.v1"
    assert out["links"]["value_cycle_preflight"] == "https://nomad.example/.well-known/nomad-value-cycle-preflight.json"
    assert out["summary"]["job_count"] > 0
