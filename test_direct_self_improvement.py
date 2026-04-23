import json

from self_improvement import SelfImprovementEngine


def test_self_improvement_reads_recent_direct_agent_sessions(tmp_path, monkeypatch):
    import self_improvement

    session_path = tmp_path / "nomad_direct_sessions.json"
    session_path.write_text(
        json.dumps(
            {
                "sessions": {
                    "direct-one": {
                        "session_id": "direct-one",
                        "updated_at": "2026-04-18T00:00:00+00:00",
                        "requester_agent": "StuckBot",
                        "status": "diagnosis_offered",
                        "last_pain_type": "loop_break",
                        "last_task_id": "svc-one",
                        "turns": [
                            {
                                "free_diagnosis": {
                                    "first_30_seconds": "Stop retries and isolate the failing tool call."
                                }
                            }
                        ],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        self_improvement,
        "__file__",
        str(tmp_path / "self_improvement.py"),
    )

    engine = SelfImprovementEngine()
    sessions = engine._recent_direct_agent_sessions()

    assert sessions[0]["requester_agent"] == "StuckBot"
    assert sessions[0]["last_pain_type"] == "loop_break"
    assert "Stop retries" in sessions[0]["last_diagnosis"]
