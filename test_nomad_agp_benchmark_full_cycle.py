import importlib.util
from pathlib import Path


def _load_cycle():
    path = Path(__file__).resolve().parent / "scripts" / "nomad_agp_benchmark_full_cycle.py"
    spec = importlib.util.spec_from_file_location("nomad_agp_benchmark_full_cycle", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_full_cycle_coverage_summary_reports_remaining_predictions():
    cycle = _load_cycle()
    evaluation = {
        "mode_results": [
            {"mode": "gpqa_diamond", "observed_examples": 198, "expected_min_examples": 198, "evaluated_predictions": 3, "accuracy": 0.33, "status": "evaluated"},
            {"mode": "aime", "observed_examples": 30, "expected_min_examples": 30, "evaluated_predictions": 2, "accuracy": 0.5, "status": "evaluated"},
            {"mode": "gaia", "observed_examples": 466, "expected_min_examples": 450, "evaluated_predictions": 1, "accuracy": 0.0, "status": "evaluated"},
            {"mode": "leetcode", "observed_examples": 164, "expected_min_examples": 164, "evaluated_predictions": 1, "accuracy": 1.0, "status": "evaluated"},
        ]
    }

    coverage = cycle.coverage_from_evaluation(evaluation)

    assert coverage["gpqa_diamond"]["remaining_predictions"] == 195
    assert coverage["aime"]["remaining_predictions"] == 28
    assert coverage["gaia"]["remaining_predictions"] == 449
    assert coverage["leetcode"]["remaining_predictions"] == 163
