from nomad_server_failure_guard import (
    build_server_failure_guard_surface,
    classify_server_failure_event,
    record_server_failure_event,
    summarize_server_failure_events,
)


def test_classify_memory_restart_and_stream_abort():
    result = classify_server_failure_event(
        {
            "message": "Web Service syndiode exceeded its memory limit and was temporarily unavailable while restarting.",
            "observed_log_excerpt": "BrokenPipeError in _public_download_file_response",
        }
    )

    assert result["severity"] == "high"
    assert "memory_limit_restart" in result["classes"]
    assert "client_abort_stream" in result["classes"]
    assert "wrap_streaming_writes_for_broken_pipe" in result["recommended_actions"]


def test_record_server_failure_event_rejects_secret_like_payload(tmp_path):
    result = record_server_failure_event(
        {"message": "server failure", "authorization": "Bearer should-not-be-here"},
        ledger_path=tmp_path / "server_failures.jsonl",
    )

    assert result["ok"] is False
    assert result["schema"] == "nomad.server_failure_error.v1"


def test_record_and_summarize_server_failure_event(tmp_path):
    ledger = tmp_path / "server_failures.jsonl"
    event = record_server_failure_event(
        {
            "source": "render",
            "message": "We recently detected a server failure for syndiode.",
            "observed_log_excerpt": "Running 'python app.py'",
        },
        base_url="https://nomad.example",
        ledger_path=ledger,
    )
    summary = summarize_server_failure_events(ledger)
    surface = build_server_failure_guard_surface("https://nomad.example", summary=summary)

    assert event["ok"] is True
    assert event["counts_as_revenue"] is False
    assert "host_failure_notice" in event["classes"]
    assert summary["event_count"] == 1
    assert surface["schema"] == "nomad.server_failure_guard.v1"
    assert surface["post_event_url"] == "https://nomad.example/swarm/server-failure/events"
