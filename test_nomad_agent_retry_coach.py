import json

from nomad_agent_retry_coach import run_agent_retry_coach


def test_retry_coach_reads_edge_tail(tmp_path):
    log = tmp_path / "e.jsonl"
    lines = [
        json.dumps({"gateway_hits": 2, "facade_count": 1, "readiness_divergence": True}, separators=(",", ":"))
        for _ in range(5)
    ]
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    out = run_agent_retry_coach(edge_log_path=str(log), lead_log_path=str(tmp_path / "missing.jsonl"), tail_lines=10)
    assert out["schema"] == "nomad.agent_retry_coach.v1"
    assert out["recommendation"]["base_delay_seconds"] >= 1.2
    assert out["samples"]["edge_lines_used"] == 5
