#!/usr/bin/env python3
"""Fetch authorized AGP paper benchmark assets for local Nomad evaluation.

The script stores datasets outside the deploy repo by default:
    C:\\Users\\Sebastian Höger\\Desktop\\Nomad\\data\\agp-benchmarks

It downloads only datasets the operator is allowed to access. GAIA is gated on
Hugging Face; the script uses HF_TOKEN/HUGGINGFACE_TOKEN from an optional .env
file but never prints token values.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_OUT_DIR = Path(r"C:\Users\Sebastian Höger\Desktop\Nomad\data\agp-benchmarks")
GPQA_URL = "https://huggingface.co/datasets/Wanfq/gpqa/resolve/main/gpqa_diamond.csv"
HUMANEVAL_URL = "https://raw.githubusercontent.com/openai/human-eval/master/data/HumanEval.jsonl.gz"


def _load_env_file(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {"loaded": False, "path": "", "keys_loaded": 0}
    p = Path(path)
    if not p.exists():
        return {"loaded": False, "path": str(p), "reason": "env_file_missing", "keys_loaded": 0}
    count = 0
    for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            count += 1
    return {"loaded": True, "path": str(p), "keys_loaded": count}


def _download(url: str, out: Path, *, token: str = "", max_bytes: int = 250_000_000) -> dict[str, Any]:
    out.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "nomad-agp-benchmark-fetcher/1"}
    if token and ("huggingface.co/" in url or "hf.co/" in url):
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=120) as response:
            raw = response.read(max_bytes + 1)
    except HTTPError as exc:
        return {"ok": False, "path": str(out), "reason": f"http_{exc.code}", "url": url}
    except (OSError, URLError, TimeoutError) as exc:
        return {"ok": False, "path": str(out), "reason": type(exc).__name__, "url": url}
    if len(raw) > max_bytes:
        return {"ok": False, "path": str(out), "reason": "too_large_for_local_fetch", "max_bytes": max_bytes}
    out.write_bytes(raw)
    return {"ok": True, "path": str(out), "bytes": len(raw), "url": url}


def _string_value(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _write_jsonl(rows: list[dict[str, Any]], out: Path) -> dict[str, Any]:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return {"ok": True, "path": str(out), "rows": len(rows)}


def _load_datasets_module() -> tuple[Any | None, dict[str, Any]]:
    try:
        import datasets  # type: ignore
    except ModuleNotFoundError:
        return None, {
            "ok": False,
            "reason": "missing_python_package",
            "install": "python -m pip install -U datasets huggingface_hub pyarrow",
        }
    return datasets, {"ok": True, "version": getattr(datasets, "__version__", "")}


def _dataset_to_rows(ds: Any, *, mode: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(ds):
        row = dict(item)
        if mode == "aime":
            rows.append(
                {
                    "id": _string_value(row, ("id", "ID", "problem_id")) or str(index + 1),
                    "problem": _string_value(row, ("problem", "Problem", "question", "Question")),
                    "answer": _string_value(row, ("answer", "Answer", "final_answer", "target")),
                }
            )
        elif mode == "gaia":
            rows.append(
                {
                    "id": _string_value(row, ("task_id", "id", "question_id", "ID")) or str(index + 1),
                    "question": _string_value(row, ("Question", "question", "problem", "Prompt", "prompt")),
                    "answer": _string_value(row, ("Final answer", "final_answer", "answer", "Answer", "target")),
                    "level": _string_value(row, ("Level", "level")),
                    "file_name": _string_value(row, ("file_name", "file", "Filename")),
                }
            )
        else:
            rows.append(row)
    return rows


def _fetch_aime(out_dir: Path, token: str) -> dict[str, Any]:
    datasets, status = _load_datasets_module()
    if datasets is None:
        return status
    errors: list[str] = []
    for dataset_id in ("Maxwell-Jia/AIME_2024", "AI-MO/aimo-validation-aime"):
        try:
            ds = datasets.load_dataset(dataset_id, split="train", token=token or None)
        except Exception as exc:  # noqa: BLE001 - report sanitized type only
            errors.append(f"{dataset_id}:{type(exc).__name__}")
            continue
        rows = _dataset_to_rows(ds, mode="aime")
        rows = [row for row in rows if row.get("problem") and row.get("answer")]
        result = _write_jsonl(rows, out_dir / "aime.jsonl")
        return {**result, "dataset_id": dataset_id}
    return {"ok": False, "reason": "aime_fetch_failed", "errors": errors}


def _gaia_candidate_splits(datasets: Any, token: str) -> list[tuple[str | None, str]]:
    configs: list[str | None] = [None]
    try:
        names = datasets.get_dataset_config_names("gaia-benchmark/GAIA", token=token or None)
        configs = [str(name) for name in names] or configs
    except Exception:
        configs = ["2023_all", "2023_level1", "2023_level2", "2023_level3", None]
    splits = ("validation", "test", "train")
    return [(config, split) for config in configs for split in splits]


def _fetch_gaia(out_dir: Path, token: str) -> dict[str, Any]:
    datasets, status = _load_datasets_module()
    if datasets is None:
        return status
    if not token:
        return {"ok": False, "reason": "hf_token_missing_for_gated_gaia"}
    errors: list[str] = []
    combined: dict[str, dict[str, Any]] = {}
    observed: list[dict[str, Any]] = []
    for config, split in _gaia_candidate_splits(datasets, token):
        try:
            kwargs = {"split": split, "token": token}
            ds = datasets.load_dataset("gaia-benchmark/GAIA", config, **kwargs) if config else datasets.load_dataset("gaia-benchmark/GAIA", **kwargs)
        except Exception as exc:  # noqa: BLE001 - report sanitized type only
            errors.append(f"{config or 'default'}/{split}:{type(exc).__name__}")
            continue
        rows = _dataset_to_rows(ds, mode="gaia")
        usable = 0
        for row in rows:
            rid = str(row.get("id") or "").strip()
            if not rid:
                continue
            if row.get("question") and row.get("answer"):
                usable += 1
            combined[rid] = row
        observed.append({"config": config or "default", "split": split, "rows": len(rows), "usable_with_answer": usable})
    rows = [row for row in combined.values() if row.get("question") and row.get("answer")]
    if not rows:
        return {"ok": False, "reason": "gaia_no_answered_rows_loaded", "observed": observed[:20], "errors": errors[:20]}
    result = _write_jsonl(rows, out_dir / "gaia.jsonl")
    return {**result, "dataset_id": "gaia-benchmark/GAIA", "observed_splits": observed[:20]}


def _gpqa_summary(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as exc:
        return {"ok": False, "reason": type(exc).__name__}
    return {"ok": True, "rows": len(rows), "path": str(path)}


def fetch_all(out_dir: Path, *, env_file: str = "", skip_gaia: bool = False) -> dict[str, Any]:
    env = _load_env_file(env_file)
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN") or os.getenv("NOMAD_AGP_HF_TOKEN") or ""
    out_dir.mkdir(parents=True, exist_ok=True)
    gpqa = _download(GPQA_URL, out_dir / "gpqa_diamond.csv", token=token)
    human_eval = _download(HUMANEVAL_URL, out_dir / "leetcode.jsonl.gz")
    aime = _fetch_aime(out_dir, token)
    gaia = {"ok": False, "reason": "skipped"} if skip_gaia else _fetch_gaia(out_dir, token)
    return {
        "ok": True,
        "schema": "nomad.agp_benchmark_fetch_result.v1",
        "out_dir": str(out_dir),
        "env_file": env,
        "hf_token_present": bool(token),
        "downloads": {
            "gpqa_diamond": {**gpqa, "summary": _gpqa_summary(out_dir / "gpqa_diamond.csv") if gpqa.get("ok") else {}},
            "aime": aime,
            "gaia": gaia,
            "leetcode_humaneval_proxy": human_eval,
        },
        "next": {
            "generate_predictions": (
                "python scripts/nomad_agp_paper_benchmark_runner.py --env-file <env> "
                "--data-dir <out_dir> --generate-predictions --prediction-provider github --max-model-calls 20 --local-eval"
            ),
            "leetcode_note": "HumanEval is downloaded as leetcode.jsonl.gz proxy; full lane still needs execution result predictions with passed/ok booleans.",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch local AGP paper benchmark datasets for Nomad.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--env-file", default=r"C:\Users\Sebastian Höger\Desktop\Nomad\.env")
    parser.add_argument("--skip-gaia", action="store_true")
    args = parser.parse_args(argv)
    result = fetch_all(Path(args.out_dir), env_file=args.env_file, skip_gaia=args.skip_gaia)
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    downloads = result.get("downloads", {})
    failures = [name for name, item in downloads.items() if not isinstance(item, dict) or not item.get("ok")]
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
