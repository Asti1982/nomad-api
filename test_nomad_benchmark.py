from pathlib import Path

from nomad_benchmark import default_harness
from nomad_market_patterns import ComputeLane


def test_runtime_benchmark_shows_adaptive_improvement(tmp_path: Path):
    harness = default_harness(benchmark_dir=tmp_path / "benchmark")

    report = harness.run(
        baseline_lane=ComputeLane.XAI_GROK,
        output_path=tmp_path / "benchmark-report.json",
    )

    assert report["comparison"]["latency_reduction_ms"] > 0
    assert report["comparison"]["cost_reduction_usd"] > 0
    assert report["comparison"]["error_rate_reduction"] >= 0
    assert Path(report["output_path"]).exists()
