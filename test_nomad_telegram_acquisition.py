import json

from nomad_telegram_acquisition import (
    build_telegram_acquisition_launch_surface,
    compact_telegram_acquisition_message,
    summarize_telegram_acquisition_ledgers,
)


def test_telegram_acquisition_launch_compiles_miniapp_referrals_orders_and_workers(tmp_path, monkeypatch):
    ledger = tmp_path / "miniapp.jsonl"
    ledger.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "receipt_id": "r1",
                        "stage": "diagnosis_requested",
                        "selected_offer": "free_mini_diagnosis",
                        "campaign": "diagnosis",
                        "telegram_user_hash": "u1",
                        "recorded_at": "2026-05-22T12:00:00+00:00",
                    }
                ),
                json.dumps(
                    {
                        "receipt_id": "r2",
                        "stage": "task_created",
                        "selected_offer": "transition_worker_setup",
                        "campaign": "order_transition_worker",
                        "telegram_user_hash": "u1",
                        "task_id": "task-1",
                        "recorded_at": "2026-05-22T12:01:00+00:00",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NOMAD_TELEGRAM_TARGET_TRANSITION_WORKERS", "100")
    monkeypatch.setenv("NOMAD_TELEGRAM_MINIAPP_LEDGER_PATH", str(ledger))

    out = build_telegram_acquisition_launch_surface(
        base_url="https://nomad.example",
        miniapp_surface={
            "enabled": True,
            "launch_url": "https://nomad.example/telegram-miniapp",
            "lead_capture_url": "https://nomad.example/telegram-miniapp/lead",
            "links": {
                "worker_download": "https://nomad.example/downloads/nomad_transition_worker.py",
                "cursor_referral": "https://cursor.example/ref",
            },
            "payment": {"recipient": "0xabc"},
            "offers": [{"offer_id": "cursor_referral"}],
        },
        referral_swarm={"active_owned_arms": [{"arm_id": "owned"}]},
        worker_job_queue={
            "schema": "nomad.worker_job_queue.v1",
            "well_known_url": "https://nomad.example/.well-known/nomad-worker-job-queue.json",
            "summary": {"job_count": 3, "executable_now_count": 2},
        },
        agent_job_router={
            "schema": "nomad.agent_job_router.v1",
            "well_known_url": "https://nomad.example/.well-known/nomad-agent-jobs.json",
        },
    )

    assert out["schema"] == "nomad.telegram_acquisition_launch.v1"
    assert out["targets"]["transition_workers"] == 100
    assert out["links"]["miniapp"] == "https://nomad.example/telegram-miniapp"
    assert out["links"]["worker_queue"] == "https://nomad.example/.well-known/nomad-worker-job-queue.json"
    assert out["observed_funnel"]["lead_ledger"]["event_count"] == 2
    assert out["observed_funnel"]["worker_queue_jobs"] == 3
    assert any(item["command_id"] == "route_worker" for item in out["bot_launch_commands"])
    assert any(item["stage"] == "task_created" for item in out["lead_to_workflow"])
    assert out["guardrails"]["no_unsolicited_dm"] is True


def test_telegram_acquisition_ledger_summary_is_secret_free(tmp_path):
    ledger = tmp_path / "miniapp.jsonl"
    ledger.write_text(
        json.dumps(
            {
                "receipt_id": "r1",
                "stage": "cursor_offer_opened",
                "selected_offer": "cursor_referral",
                "telegram_user_hash": "hash-only",
                "telegram_init_data_hash": "digest-only",
                "recorded_at": "2026-05-22T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    out = summarize_telegram_acquisition_ledgers(ledger_path=ledger)

    assert out["event_count"] == 1
    assert out["unique_telegram_user_hash_count"] == 1
    assert "telegram_init_data" not in json.dumps(out)


def test_compact_telegram_acquisition_message_exposes_actionable_launch_lines():
    surface = build_telegram_acquisition_launch_surface(
        base_url="https://nomad.example",
        miniapp_surface={"launch_url": "https://nomad.example/telegram-miniapp", "payment": {"recipient": "0xabc"}},
        worker_job_queue={"well_known_url": "https://nomad.example/.well-known/nomad-worker-job-queue.json"},
    )

    text = compact_telegram_acquisition_message(surface)

    assert "Nomad Telegram acquisition launch" in text
    assert "NOMAD_WORKER" in text
    assert "https://nomad.example/telegram-miniapp" in text
    assert "opt-in only" in text


def test_telegram_acquisition_uses_public_nomad_prefix_for_syndiode():
    out = build_telegram_acquisition_launch_surface(base_url="https://www.syndiode.com")

    assert out["public_base_url"] == "https://syndiode.com/nomad"
    assert out["links"]["acquisition_contract"] == "https://syndiode.com/nomad/.well-known/nomad-telegram-acquisition.json"
    assert out["links"]["miniapp"] == "https://syndiode.com/nomad/telegram-miniapp"
