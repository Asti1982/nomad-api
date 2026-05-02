import json

from nomad_outbound_tracker import NomadOutboundTracker


def test_outbound_tracker_summarizes_contacts_campaigns_tasks_and_autopilot(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    monkeypatch.setenv("NOMAD_COLLABORATION_HOME_URL", "")
    monkeypatch.setenv("NOMAD_RENDER_DOMAIN", "")
    contact_store = tmp_path / "contacts.json"
    campaign_store = tmp_path / "campaigns.json"
    task_store = tmp_path / "tasks.json"
    autopilot_state = tmp_path / "autopilot.json"

    contact_store.write_text(
        json.dumps(
            {
                "contacts": {
                    "contact-1": {
                        "contact_id": "contact-1",
                        "status": "sent",
                        "service_type": "compute_auth",
                        "endpoint_url": "https://agent.example/a2a/message",
                        "created_at": "2026-04-30T10:00:00+00:00",
                        "updated_at": "2026-04-30T11:00:00+00:00",
                        "remote_task_id": "remote-7",
                        "followup_ready": True,
                        "last_reply": {
                            "text": "We reproduced the auth failure and need the fallback plan.",
                            "updated_at": "2026-04-30T11:00:00+00:00",
                        },
                        "followup_recommendation": {
                            "next_path": "/tasks/work",
                        },
                        "attempts": [
                            {
                                "at": "2026-04-30T10:30:00+00:00",
                                "status": "sent",
                                "message": "Initial bounded outreach sent.",
                            }
                        ],
                    },
                    "contact-2": {
                        "contact_id": "contact-2",
                        "status": "queued",
                        "service_type": "human_in_loop",
                        "endpoint_url": "https://agent-two.example/.well-known/agent",
                        "created_at": "2026-04-30T09:00:00+00:00",
                        "updated_at": "2026-04-30T09:30:00+00:00",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    campaign_store.write_text(
        json.dumps(
            {
                "campaigns": {
                    "campaign-1": {
                        "campaign_id": "campaign-1",
                        "status": "queued",
                        "service_type": "compute_auth",
                        "created_at": "2026-04-30T08:00:00+00:00",
                        "updated_at": "2026-04-30T12:00:00+00:00",
                        "stats": {"queued": 2, "sent": 1, "blocked": 0, "failed": 0},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    task_store.write_text(
        json.dumps(
            {
                "tasks": {
                    "svc-1": {
                        "task_id": "svc-1",
                        "status": "awaiting_payment",
                        "service_type": "compute_auth",
                        "created_at": "2026-04-30T07:00:00+00:00",
                        "updated_at": "2026-04-30T12:30:00+00:00",
                        "requester_agent": "VerifierBot",
                        "budget_native": 0.03,
                    },
                    "svc-2": {
                        "task_id": "svc-2",
                        "status": "paid",
                        "service_type": "human_in_loop",
                        "created_at": "2026-04-30T06:00:00+00:00",
                        "updated_at": "2026-04-30T12:40:00+00:00",
                        "requester_agent": "OpsBot",
                        "budget_native": 0.05,
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    autopilot_state.write_text(
        json.dumps(
            {
                "last_run_at": "2026-04-30T12:45:00+00:00",
                "last_objective": "Grow agent network around 7405.",
                "last_public_api_url": "https://nomad.example",
                "payment_followup_log": {"svc-1": {"count": 1}},
                "agent_followup_log": {"contact-1": {"count": 1}},
                "converted_reply_contact_ids": ["contact-1"],
                "last_payment_followup_queue": {"queued": ["svc-1"]},
                "last_contact_queue": {"queued": ["contact-2"]},
                "last_contact_poll": {"polled": ["contact-1"]},
                "last_agent_followup_queue": {"queued": ["contact-1"]},
                "last_agent_followup_send": {"sent": ["contact-1"]},
            }
        ),
        encoding="utf-8",
    )

    tracker = NomadOutboundTracker(
        contact_store_path=contact_store,
        campaign_store_path=campaign_store,
        task_store_path=task_store,
        autopilot_state_path=autopilot_state,
    )

    result = tracker.summary(limit=5)

    assert result["mode"] == "nomad_outbound_tracking"
    assert result["public_api_url"] == "https://nomad.example"
    assert result["contacts"]["total"] == 2
    assert result["contacts"]["awaiting_reply"] == 1
    assert result["contacts"]["followup_ready"] == 1
    assert result["contacts"]["remote_tasks"] == 1
    assert result["campaigns"]["latest"]["campaign_id"] == "campaign-1"
    assert len(result["tasks"]["awaiting_payment"]) == 1
    assert len(result["tasks"]["paid_ready"]) == 1
    assert result["autonomous_tracking"]["payment_followup_log_count"] == 1
    assert result["autonomous_tracking"]["agent_followup_log_count"] == 1
    assert result["autonomous_tracking"]["converted_reply_count"] == 1
    assert result["recent_actions"][0]["kind"] in {"reply_received", "campaign_queued", "sent"}
    assert "Queue the role-specific follow-up" in result["next_best_action"]
