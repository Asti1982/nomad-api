import importlib.util
import json
from pathlib import Path


def _load_runner():
    path = Path(__file__).resolve().parent / "scripts" / "nomad_agp_paper_benchmark_runner.py"
    spec = importlib.util.spec_from_file_location("nomad_agp_paper_benchmark_runner", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _write_sample_benchmarks(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "gpqa_diamond.csv").write_text("id,question,answer\nq1,science?,A\nq2,science2?,B\n", encoding="utf-8")
    (root / "aime.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"id": "a1", "problem": "1+1", "answer": "2"}),
                json.dumps({"id": "a2", "problem": "2+2", "answer": "4"}),
            ]
        ),
        encoding="utf-8",
    )
    (root / "gaia.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"id": "g1", "question": "capital", "answer": "Paris"}),
                json.dumps({"id": "g2", "question": "color", "answer": "blue"}),
            ]
        ),
        encoding="utf-8",
    )
    (root / "leetcode.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"task_id": "c1", "prompt": "pass", "answer": "passed"}),
                json.dumps({"task_id": "c2", "prompt": "pass", "answer": "passed"}),
            ]
        ),
        encoding="utf-8",
    )
    (root / "gpqa_diamond_predictions.json").write_text(json.dumps({"predictions": {"q1": "A", "q2": "B"}}), encoding="utf-8")
    (root / "aime_predictions.json").write_text(json.dumps({"predictions": {"a1": "2", "a2": "4"}}), encoding="utf-8")
    (root / "gaia_predictions.json").write_text(json.dumps({"predictions": {"g1": "Paris", "g2": "blue"}}), encoding="utf-8")
    (root / "leetcode_predictions.json").write_text(json.dumps({"predictions": {"c1": "passed", "c2": "passed"}}), encoding="utf-8")


def test_runner_discovers_local_inputs_and_blocks_remote_local_paths(tmp_path):
    runner = _load_runner()
    _write_sample_benchmarks(tmp_path)

    payload, inventory = runner.build_payload(data_dir=tmp_path)
    validation = runner.validate_submission_target("https://www.syndiode.com/nomad", payload)
    local_validation = runner.validate_submission_target("http://127.0.0.1:8787", payload)

    assert inventory["schema"] == "nomad.agp_paper_benchmark_runner_inventory.v1"
    assert all(item["ready_for_local_eval"] for item in inventory["modes"].values())
    assert set(payload["datasets"]) == {"gpqa_diamond", "aime", "gaia", "leetcode"}
    assert validation["ok"] is False
    assert validation["reason"].startswith("remote_nomad_cannot_read_local_filesystem_paths")
    assert set(validation["local_dataset_path_modes"]) == {"gpqa_diamond", "aime", "gaia", "leetcode"}
    assert local_validation["ok"] is True


def test_runner_local_eval_produces_receipt_without_full_claim(tmp_path):
    runner = _load_runner()
    data_dir = tmp_path / "bench"
    _write_sample_benchmarks(data_dir)

    payload, _inventory = runner.build_payload(data_dir=data_dir)
    result = runner.run_local_evaluation(
        payload,
        ledger_path=tmp_path / "paper_bench.jsonl",
        benchmark_ledger_path=tmp_path / "suite.jsonl",
    )

    assert result["schema"] == "nomad.agp_paper_benchmark_run_receipt.v1"
    assert set(result["evaluated_modes"]) == {"gpqa_diamond", "aime", "gaia", "leetcode"}
    assert all(item["status"] == "evaluated" for item in result["mode_results"])
    assert result["paper_grade_full_benchmark_ready"] is False
    assert result["checks"]["all_datasets_full_enough"] is False
    assert result["side_effect_scope"] == "paper_benchmark_receipts_only"


def test_runner_can_generate_gated_prediction_files_with_explicit_cap(tmp_path, monkeypatch):
    runner = _load_runner()
    data_dir = tmp_path / "bench"
    out_dir = tmp_path / "predictions"
    _write_sample_benchmarks(data_dir)
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    sources, _report = runner.discover_sources(data_dir=data_dir)

    def fake_completion(_config, prompt):
        if "1+1" in prompt:
            return "2"
        if "2+2" in prompt:
            return "4"
        return "A"

    result = runner.generate_prediction_files(
        sources=sources,
        output_dir=out_dir,
        provider="github",
        model="test-model",
        max_model_calls=2,
        modes=("aime",),
        completion_fn=fake_completion,
    )

    generated = json.loads((out_dir / "aime_predictions.json").read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["model_calls_used"] == 2
    assert result["truth_boundary"]["does_not_execute_code"] is True
    assert generated["predictions"] == {"a1": "2", "a2": "4"}


def test_runner_generation_distributes_small_call_budget_across_modes(tmp_path, monkeypatch):
    runner = _load_runner()
    data_dir = tmp_path / "bench"
    out_dir = tmp_path / "predictions"
    _write_sample_benchmarks(data_dir)
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    sources, _report = runner.discover_sources(data_dir=data_dir)

    result = runner.generate_prediction_files(
        sources=sources,
        output_dir=out_dir,
        provider="github",
        model="test-model",
        max_model_calls=3,
        modes=("gpqa_diamond", "aime", "gaia"),
        completion_fn=lambda _config, _prompt: "A",
    )

    assert result["model_calls_used"] == 3
    assert result["modes"]["gpqa_diamond"]["generated"] == 1
    assert result["modes"]["aime"]["generated"] == 1
    assert result["modes"]["gaia"]["generated"] == 1


def test_provider_quota_blocks_window_before_network_call(tmp_path):
    runner = _load_runner()
    quota = runner.ProviderQuota(
        state_path=tmp_path / "quota.json",
        config={"provider": "openrouter", "model": "openrouter/free"},
        min_interval_seconds=0,
        window_seconds=3600,
        window_call_limit=1,
        sleep=False,
    )

    quota.before_call()
    quota.after_success()

    try:
        quota.before_call()
    except runner.ProviderRateLimitError as exc:
        assert exc.retry_after_seconds > 0
    else:
        raise AssertionError("quota should block the second call in the same window")
