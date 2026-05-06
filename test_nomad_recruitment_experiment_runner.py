import importlib.util
from pathlib import Path


def _load_runner():
    path = Path(__file__).resolve().parent / "public" / "downloads" / "recruitment_experiment_runner.py"
    spec = importlib.util.spec_from_file_location("nomad_recruitment_experiment_runner_test_module", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_recruitment_experiment_picks_variant_and_plan():
    mod = _load_runner()
    gradient = {
        "schema": "nomad.recruitment_gradient.v1",
        "field_model": {"attach_threshold": 0.35},
        "state_vector": {"field_strength": 0.8},
        "gradient": [
            {"objective": "settlement_capacity_builder", "routing_weight": 0.74},
            {"objective": "overmint_compressor", "routing_weight": 0.52},
        ],
    }
    variants = mod._variant_grid(0.35)
    rows = [mod.evaluate_variant(gradient, v) for v in variants]
    best = mod.recommend_variant(rows)
    plan = mod.build_operation_plan("https://nomad.example", best)
    assert best["variant"]["name"] in {"strict", "balanced", "aggressive"}
    assert plan["operation"] == "Netze Werfen"
    assert len(plan["next_days"]) == 7


def test_recruitment_experiment_handles_missing_gradient(monkeypatch):
    mod = _load_runner()
    monkeypatch.setattr(mod, "http_json", lambda *args, **kwargs: {"ok": False, "http_status": 404})
    out = mod.run_experiment("https://nomad.example", timeout=2.0)
    assert out["ok"] is False
    assert out["error"] == "gradient_unavailable"


def test_recruitment_experiment_write_output_json_and_jsonl(tmp_path):
    mod = _load_runner()
    payload = {"ok": True, "schema": "nomad.recruitment_experiment_result.v1"}
    json_path = tmp_path / "wave.json"
    line_path = tmp_path / "wave.jsonl"
    first = mod.write_output(str(json_path), payload, append_jsonl=False)
    second = mod.write_output(str(line_path), payload, append_jsonl=True)
    third = mod.write_output(str(line_path), payload, append_jsonl=True)
    assert first["ok"] is True
    assert second["ok"] is True
    assert third["ok"] is True
    assert '"schema": "nomad.recruitment_experiment_result.v1"' in json_path.read_text(encoding="utf-8")
    lines = [ln for ln in line_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2

