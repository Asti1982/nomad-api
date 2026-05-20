import importlib.util
import json
from pathlib import Path


def _load_fetcher():
    path = Path(__file__).resolve().parent / "scripts" / "nomad_fetch_agp_benchmarks.py"
    spec = importlib.util.spec_from_file_location("nomad_fetch_agp_benchmarks", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_fetcher_normalizes_aime_and_gaia_rows(tmp_path):
    fetcher = _load_fetcher()

    aime_rows = fetcher._dataset_to_rows(
        [
            {"ID": "a1", "Problem": "1+1", "Answer": 2},
            {"id": "a2", "problem": "2+2", "answer": "4"},
        ],
        mode="aime",
    )
    gaia_rows = fetcher._dataset_to_rows(
        [
            {"task_id": "g1", "Question": "capital?", "Final answer": "Paris", "Level": "1"},
            {"id": "g2", "question": "color?", "answer": "blue", "file_name": "x.txt"},
        ],
        mode="gaia",
    )
    written = fetcher._write_jsonl(gaia_rows, tmp_path / "gaia.jsonl")
    parsed = [json.loads(line) for line in (tmp_path / "gaia.jsonl").read_text(encoding="utf-8").splitlines()]

    assert aime_rows == [
        {"id": "a1", "problem": "1+1", "answer": "2"},
        {"id": "a2", "problem": "2+2", "answer": "4"},
    ]
    assert gaia_rows[0]["id"] == "g1"
    assert gaia_rows[0]["answer"] == "Paris"
    assert written["rows"] == 2
    assert parsed[1]["file_name"] == "x.txt"
