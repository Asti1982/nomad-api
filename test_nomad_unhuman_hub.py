from nomad_unhuman_hub import unhuman_hub_snapshot


def test_unhuman_hub_snapshot_schema():
    out = unhuman_hub_snapshot(base_url="https://hub.example", persist_mission=False)
    assert out["mode"] == "nomad_unhuman_hub"
    assert out["schema"] == "nomad.unhuman_hub.v1"
    assert out["public_base_url"] == "https://hub.example"
    psych = out.get("human_psychic_avoidance_lanes") or {}
    assert psych.get("schema") == "nomad.human_psychic_avoidance_lanes.v1"
    assert isinstance(psych.get("lanes"), list) and len(psych["lanes"]) >= 2
    profile = out.get("unhuman_profile") or {}
    assert "risk_score" in profile
    assert profile.get("risk_tier") in {"stable", "guarded", "critical"}
    assert isinstance(out.get("doctrine"), list)
    assert isinstance(out.get("runbook"), list)
