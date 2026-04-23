from pathlib import Path

from nomad_multi_node_pilot import run_multi_node_pilot


def test_multi_node_pilot_imports_and_reverifies_patterns(tmp_path: Path):
    report = run_multi_node_pilot(output_dir=tmp_path / "pilot")

    node_b = report["nodes"]["node_b"]

    assert report["ok"] is True
    assert report["imports"]["node_b"]["import"]["imported"] >= 1
    assert node_b["patterns"]["pattern_count"] >= 1
    assert node_b["patterns"]["reverified_pattern_count"] >= 1
    assert Path(report["output_path"]).exists()
