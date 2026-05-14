from __future__ import annotations

from datetime import UTC, datetime

from nomad_taskbounty_scout import (
    _merge_task_detail,
    _normalize_api_base,
    build_taskbounty_scout,
    probe_taskbounty_access_gate,
)


NOW = datetime(2026, 5, 13, 12, 0, tzinfo=UTC)


def _task(**overrides):
    task = {
        "id": "task-1",
        "title": "Fix DST boundary crash in formatDeadline date parsing",
        "slug": "agent-bounty-board-23-fix",
        "tags": ["repo:eliottreich/agent-bounty-board"],
        "bounty_cents": 5000,
        "currency": "usd",
        "status": "OPEN",
        "funding_status": "FUNDED",
        "submission_deadline": "2026-05-19T12:07:57.933Z",
        "submission_count": 0,
        "description": "Fix a bounded date parsing bug and add one regression test.",
    }
    task.update(overrides)
    return task


def test_api_base_normalization_adds_api_v1():
    assert _normalize_api_base("https://www.task-bounty.com") == "https://www.task-bounty.com/api/v1"
    assert _normalize_api_base("www.task-bounty.com/api/v1") == "https://www.task-bounty.com/api/v1"


def test_detail_merge_does_not_erase_nonempty_list_fields():
    merged = _merge_task_detail(_task(funding_status="FUNDED"), {"funding_status": "", "description": "detail"})

    assert merged["funding_status"] == "FUNDED"
    assert merged["description"] == "detail"


def test_auto_funded_tag_infers_funded_status():
    result = build_taskbounty_scout(
        api_key="tb_test",
        tasks=[_task(tags=["repo:eliottreich/agent-bounty-board", "auto-funded"])],
        now=NOW,
    )

    assert result["tasks"][0]["funding_status"] == "FUNDED"
    assert result["summary"]["funded_open_count"] == 1


def test_existing_submission_is_competition_not_automatic_block():
    result = build_taskbounty_scout(
        api_key="tb_test",
        agent_id="agent-test",
        tasks=[_task(submission_count=1)],
        now=NOW,
    )

    task = result["tasks"][0]
    assert result["ok"] is True
    assert result["summary"]["blocked_pending_submission_count"] == 0
    assert result["summary"]["work_candidate_count"] == 1
    assert task["gate_state"] == "candidate_submit_gate_unverified"
    assert task["executable_work_allowed"] is False
    assert "submit_claim" in task["blocked_actions"]
    assert "existing_submission_competition" in task["risk_flags"]
    assert "upstream_pr_fork_or_branch_permission_confirmed" in task["unlock_requirements"]
    assert result["machine_instruction"] == "probe_submission_gate_before_patch_work"


def test_zero_submission_task_is_candidate_but_still_pre_submit_probe():
    result = build_taskbounty_scout(
        api_key="tb_test",
        agent_id="agent-test",
        tasks=[_task(submission_count=0)],
        now=NOW,
    )

    task = result["tasks"][0]
    assert result["summary"]["work_candidate_count"] == 1
    assert task["gate_state"] == "candidate_submit_gate_unverified"
    assert task["executable_work_allowed"] is False
    assert task["allowed_actions"] == [
        "read_only_repo_probe",
        "submission_endpoint_probe",
        "upstream_pr_access_probe",
        "local_repro_plan",
    ]
    assert "open_pr" in task["blocked_actions"]
    assert "submission_endpoint_accepts_new_claim_before_pr_work" in task["unlock_requirements"]
    assert result["machine_instruction"] == "probe_submission_gate_before_patch_work"


def test_missing_api_key_keeps_channel_watch_only():
    result = build_taskbounty_scout(api_key="", tasks=[_task()], now=NOW)

    task = result["tasks"][0]
    assert result["api_key_present"] is False
    assert task["gate_state"] == "api_key_missing"
    assert task["executable_work_allowed"] is False
    assert result["machine_instruction"] == "keep_channel_watch_only"


def test_access_gate_blocks_readonly_private_upstream_without_pr_path():
    def fake_post(url, payload, api_key, timeout):
        assert url.endswith("/tasks/task-1/access")
        assert payload == {"agent_id": "agent-test"}
        assert api_key == "tb_test"
        return {
            "data": {
                "repoUrl": "https://github.com/eliottreich/agent-bounty-board",
                "cloneUrl": "https://x-access-token:ghs_secret@github.com/eliottreich/agent-bounty-board.git",
                "expiresAt": "2026-05-13T20:53:32.295Z",
                "submissionWorkflow": [
                    "git clone https://x-access-token:ghs_secret@github.com/eliottreich/agent-bounty-board.git",
                    "# create your own GitHub fork of eliottreich/agent-bounty-board",
                    "# POST /api/v1/submissions with external_link = the upstream PR URL",
                ],
                "note": "clone token here is read-only; PR base repo MUST be upstream",
            }
        }

    result = probe_taskbounty_access_gate(
        "task-1",
        api_key="tb_test",
        agent_id="agent-test",
        post_json=fake_post,
    )

    assert result["ok"] is True
    assert result["gate_state"] == "blocked_until_upstream_pr_access_confirmed"
    assert result["submission_contract"]["requires_upstream_pr"] is True
    assert result["submission_contract"]["clone_token_read_only"] is True
    assert result["submission_contract"]["direct_patch_submission_supported"] is False
    assert result["submission_contract"]["claimable_now"] is False
    assert "submit_claim" in result["blocked_actions"]
    assert "upstream_pr_url_created_against_base_repo" in result["unlock_requirements"]
    assert "ghs_secret" not in "\n".join(result["submission_workflow_redacted"])
