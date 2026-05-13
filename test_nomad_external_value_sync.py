from nomad_external_value import append_external_value_event
from nomad_external_value_sync import plan_external_value_public_sync, sync_external_value_to_public


def _event(eid: str, stage: str):
    return {
        "schema": "nomad.external_value_event.v1",
        "agent_id": "nomad.test",
        "external_id": eid,
        "stage": stage,
        "work_url": "" if stage == "found" else "https://github.com/test/repo/pull/1",
        "proof_digest": "" if stage == "found" else "sha256:p",
        "verifier_trace_digest": "" if stage == "found" else "sha256:v",
        "amount_usd": 0.0,
        "meta": {},
    }


def test_plan_replays_full_chain_when_public_is_empty():
    plan = plan_external_value_public_sync(
        [_event("gh_pr:test/repo#1", "found"), _event("gh_pr:test/repo#1", "submitted")],
        {"ok": True, "latest_by_external": []},
    )

    assert plan["replay_candidate_count"] == 2
    assert [row["stage"] for row in plan["candidates"]] == ["found", "submitted"]
    assert plan["blocked_count"] == 0


def test_plan_replays_only_missing_tail_when_public_has_prior_stage():
    plan = plan_external_value_public_sync(
        [_event("gh_pr:test/repo#1", "found"), _event("gh_pr:test/repo#1", "submitted")],
        {"ok": True, "latest_by_external": [{"external_id": "gh_pr:test/repo#1", "stage": "found"}]},
    )

    assert plan["replay_candidate_count"] == 1
    assert plan["candidates"][0]["stage"] == "submitted"
    assert plan["skipped_count"] == 1


def test_sync_posts_missing_public_events_from_local_ledger(tmp_path, monkeypatch):
    ledger = tmp_path / "external.jsonl"
    monkeypatch.setenv("NOMAD_EXTERNAL_VALUE_LEDGER_PATH", str(ledger))
    eid = "gh_pr:test/repo#2"
    assert append_external_value_event({"agent_id": "a", "external_id": eid, "stage": "found"})["ok"]
    assert append_external_value_event(
        {
            "agent_id": "a",
            "external_id": eid,
            "stage": "submitted",
            "work_url": "https://github.com/test/repo/pull/2",
            "proof_digest": "sha256:p",
            "verifier_trace_digest": "sha256:v",
        }
    )["ok"]

    posts = []

    def fake_get(url, timeout):
        if posts:
            return {
                "ok": True,
                "status_code": 200,
                "json": {"ok": True, "event_tail_count": len(posts), "distinct_externals": 1, "latest_by_external": []},
            }
        return {
            "ok": True,
            "status_code": 200,
            "json": {"ok": True, "event_tail_count": 0, "distinct_externals": 0, "latest_by_external": []},
        }

    def fake_post(url, payload, timeout):
        posts.append(payload)
        return {
            "ok": True,
            "status_code": 200,
            "json": {
                "ok": True,
                "event_id": f"ev-{len(posts)}",
                "nomad_proof_receipt_digest": f"receipt-{len(posts)}",
            },
        }

    out = sync_external_value_to_public(
        base_url="https://nomad.example",
        apply=True,
        snapshot=False,
        fetch_json=fake_get,
        post_json=fake_post,
    )

    assert out["ok"] is True
    assert out["posted_count"] == 2
    assert out["failed_post_count"] == 0
    assert out["public_projection_lag_after"] == 0
    assert [post["stage"] for post in posts] == ["found", "submitted"]
