import gzip
import importlib.util
import json
from pathlib import Path


def _load_harness():
    path = Path(__file__).resolve().parent / "scripts" / "nomad_humaneval_execution_harness.py"
    spec = importlib.util.spec_from_file_location("nomad_humaneval_execution_harness", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _write_humaneval(path: Path) -> None:
    row = {
        "task_id": "HumanEval/Test",
        "prompt": "def add_one(x):\n",
        "entry_point": "add_one",
        "canonical_solution": "    return x + 1\n",
        "test": "def check(candidate):\n    assert candidate(1) == 2\n    assert candidate(41) == 42\n",
    }
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def test_humaneval_harness_executes_candidate_solution(tmp_path):
    harness = _load_harness()
    data = tmp_path / "HumanEval.jsonl.gz"
    solutions = tmp_path / "solutions.json"
    predictions = tmp_path / "leetcode_predictions.json"
    _write_humaneval(data)
    solutions.write_text(json.dumps({"solutions": {"HumanEval/Test": "    return x + 1\n"}}), encoding="utf-8")

    result = harness.run_harness(
        humaneval_path=data,
        solution_path=solutions,
        output_path=predictions,
        timeout_seconds=2.0,
    )
    parsed = json.loads(predictions.read_text(encoding="utf-8"))

    assert result["schema"] == "nomad.humaneval_execution_receipt.v1"
    assert result["executed_count"] == 1
    assert result["passed_count"] == 1
    assert parsed["predictions"]["HumanEval/Test"]["passed"] is True


def test_humaneval_harness_blocks_dangerous_completion(tmp_path):
    harness = _load_harness()
    data = tmp_path / "HumanEval.jsonl.gz"
    solutions = tmp_path / "solutions.json"
    predictions = tmp_path / "leetcode_predictions.json"
    _write_humaneval(data)
    solutions.write_text(json.dumps({"solutions": {"HumanEval/Test": "    import os\n    return x\n"}}), encoding="utf-8")

    result = harness.run_harness(
        humaneval_path=data,
        solution_path=solutions,
        output_path=predictions,
        timeout_seconds=2.0,
    )
    parsed = json.loads(predictions.read_text(encoding="utf-8"))

    assert result["passed_count"] == 0
    assert parsed["predictions"]["HumanEval/Test"]["reason"].startswith("static_denylist")


def test_humaneval_harness_indents_unindented_completion(tmp_path):
    harness = _load_harness()
    data = tmp_path / "HumanEval.jsonl.gz"
    solutions = tmp_path / "solutions.json"
    predictions = tmp_path / "leetcode_predictions.json"
    _write_humaneval(data)
    solutions.write_text(json.dumps({"solutions": {"HumanEval/Test": "return x + 1\n"}}), encoding="utf-8")

    result = harness.run_harness(
        humaneval_path=data,
        solution_path=solutions,
        output_path=predictions,
        timeout_seconds=2.0,
    )

    assert result["passed_count"] == 1


def test_humaneval_generation_retries_empty_existing_solution(tmp_path, monkeypatch):
    harness = _load_harness()
    data = tmp_path / "HumanEval.jsonl.gz"
    solutions = tmp_path / "solutions.json"
    _write_humaneval(data)
    solutions.write_text(json.dumps({"solutions": {"HumanEval/Test": ""}}), encoding="utf-8")

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-token")
    result = harness.generate_solutions(
        harness.load_humaneval(data),
        solution_path=solutions,
        provider="openrouter",
        model="test-model",
        max_model_calls=1,
        overwrite=False,
        completion_fn=lambda _config, _prompt: "    return x + 1\n",
    )

    parsed = json.loads(solutions.read_text(encoding="utf-8"))
    assert result["provider_calls_attempted"] == 1
    assert parsed["solutions"]["HumanEval/Test"]
