from nomad_microtask_exchange_ops import build_microtask_metrics, build_microtask_templates


def test_microtask_templates_surface_contains_multiple_templates():
    out = build_microtask_templates(base_url="https://nomad.example")
    assert out["schema"] == "nomad.microtask_templates.v1"
    assert out["template_count"] >= 10
    assert out["templates"][0]["lane_id"]


def test_microtask_metrics_surface_returns_totals_and_lane_rows():
    out = build_microtask_metrics(base_url="https://nomad.example", lookback_hours=24)
    assert out["schema"] == "nomad.microtask_metrics.v1"
    assert "totals" in out
    assert "lane_metrics" in out

