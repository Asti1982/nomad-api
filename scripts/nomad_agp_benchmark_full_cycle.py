#!/usr/bin/env python3
"""Run one bounded AGP paper benchmark cycle.

This is the practical "finish the rest" wrapper:

* fetch datasets if needed,
* generate a capped number of QA predictions,
* generate a capped number of HumanEval solutions,
* execute HumanEval solutions into LeetCode-compatible predictions,
* run the local Nomad paper benchmark receipt,
* print remaining coverage gaps.

The cycle is resumable. Existing prediction/solution files are reused and new
calls are capped so free-provider quotas are not burned accidentally.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


DEFAULT_DATA_DIR = Path.home() / "Desktop" / "Nomad" / "data" / "agp-benchmarks"
DEFAULT_ENV_FILE = Path.home() / "Desktop" / "Nomad" / ".env"
EXPECTED = {
    "gpqa_diamond": 198,
    "aime": 30,
    "gaia": 450,
    "leetcode": 164,
}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load_script(name: str) -> Any:
    path = Path(__file__).resolve().with_name(name)
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    module = importlib.util.module_from_spec(spec)
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot_load:{name}")
    spec.loader.exec_module(module)
    return module


def coverage_from_evaluation(evaluation: dict[str, Any]) -> dict[str, Any]:
    mode_results = evaluation.get("mode_results") if isinstance(evaluation.get("mode_results"), list) else []
    coverage: dict[str, Any] = {}
    for mode in EXPECTED:
        item = next((row for row in mode_results if isinstance(row, dict) and row.get("mode") == mode), {})
        expected = int(item.get("expected_min_examples") or EXPECTED[mode])
        evaluated = int(item.get("evaluated_predictions") or 0)
        observed = int(item.get("observed_examples") or 0)
        coverage[mode] = {
            "observed_examples": observed,
            "expected_min_examples": expected,
            "evaluated_predictions": evaluated,
            "remaining_predictions": max(0, expected - evaluated),
            "accuracy": float(item.get("accuracy") or 0.0),
            "status": item.get("status") or "missing",
        }
    return coverage


def run_cycle(
    *,
    env_file: str | Path = DEFAULT_ENV_FILE,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    provider: str = "openrouter",
    model: str = "",
    qa_calls: int = 0,
    code_calls: int = 0,
    fetch: bool = True,
    execute_humaneval: bool = True,
    quota_state_path: str | Path | None = None,
    min_interval_seconds: float | None = None,
    cooldown_seconds: float | None = None,
    window_seconds: float | None = None,
    window_call_limit: int | None = None,
) -> dict[str, Any]:
    fetcher = _load_script("nomad_fetch_agp_benchmarks.py")
    runner = _load_script("nomad_agp_paper_benchmark_runner.py")
    humaneval = _load_script("nomad_humaneval_execution_harness.py")
    data = Path(data_dir)
    env = str(env_file)
    env_report = runner._load_env_file(env)
    quota_path = Path(quota_state_path) if quota_state_path else data / runner.DEFAULT_PROVIDER_QUOTA_STATE
    result: dict[str, Any] = {
        "ok": True,
        "schema": "nomad.agp_benchmark_full_cycle.v1",
        "generated_at": _now(),
        "data_dir": str(data),
        "env_file": env_report,
        "provider": provider,
        "model": model or ("openrouter/free" if provider == "openrouter" else ""),
        "caps": {"qa_calls": qa_calls, "code_calls": code_calls},
        "quota": {
            "state_path": str(quota_path),
            "min_interval_seconds": min_interval_seconds,
            "cooldown_seconds": cooldown_seconds,
            "window_seconds": window_seconds,
            "window_call_limit": window_call_limit,
        },
    }
    if fetch:
        result["fetch"] = fetcher.fetch_all(data, env_file=env)
    overrides: dict[str, dict[str, str]] = {}
    payload, inventory = runner.build_payload(data_dir=data, overrides=overrides)
    result["initial_inventory"] = inventory
    if qa_calls > 0:
        sources, _ = runner.discover_sources(data_dir=data)
        generation = runner.generate_prediction_files(
            sources=sources,
            output_dir=data,
            provider=provider,
            model=model,
            max_model_calls=qa_calls,
            modes=("gpqa_diamond", "aime", "gaia"),
            quota_state_path=quota_path,
            min_interval_seconds=min_interval_seconds,
            cooldown_seconds=cooldown_seconds,
            window_seconds=window_seconds,
            window_call_limit=window_call_limit,
        )
        result["qa_prediction_generation"] = generation
    if code_calls > 0:
        tasks = humaneval.load_humaneval(data / "leetcode.jsonl.gz")
        result["humaneval_solution_generation"] = humaneval.generate_solutions(
            tasks,
            solution_path=data / "leetcode_solutions.json",
            env_file=env,
            provider=provider,
            model=model,
            max_model_calls=code_calls,
            quota_state_path=quota_path,
            min_interval_seconds=min_interval_seconds,
            cooldown_seconds=cooldown_seconds,
            window_seconds=window_seconds,
            window_call_limit=window_call_limit,
        )
    if execute_humaneval:
        result["humaneval_execution"] = humaneval.run_harness(
            humaneval_path=data / "leetcode.jsonl.gz",
            solution_path=data / "leetcode_solutions.json",
            output_path=data / "leetcode_predictions.json",
        )
    payload, inventory = runner.build_payload(data_dir=data, overrides=overrides)
    result["final_inventory"] = inventory
    evaluation = runner.run_local_evaluation(payload)
    result["local_evaluation"] = evaluation
    result["coverage"] = coverage_from_evaluation(evaluation)
    result["remaining_total"] = sum(item["remaining_predictions"] for item in result["coverage"].values())
    result["paper_grade_full_benchmark_ready"] = bool(evaluation.get("paper_grade_full_benchmark_ready"))
    result["next_recommended_caps"] = {
        "qa_calls": min(12, result["coverage"]["gpqa_diamond"]["remaining_predictions"] + result["coverage"]["aime"]["remaining_predictions"] + result["coverage"]["gaia"]["remaining_predictions"]),
        "code_calls": min(2, result["coverage"]["leetcode"]["remaining_predictions"]),
    }
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one bounded Nomad AGP paper benchmark cycle.")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--provider", default="openrouter", choices=["openrouter", "github"])
    parser.add_argument("--model", default="")
    parser.add_argument("--qa-calls", type=int, default=0)
    parser.add_argument("--code-calls", type=int, default=0)
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--skip-humaneval-execution", action="store_true")
    parser.add_argument("--fail-on-blockers", action="store_true")
    parser.add_argument("--quota-state-path", default="")
    parser.add_argument("--min-provider-interval-seconds", type=float, default=None)
    parser.add_argument("--provider-window-call-limit", type=int, default=None)
    parser.add_argument("--provider-window-seconds", type=float, default=None)
    parser.add_argument("--provider-cooldown-seconds", type=float, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = run_cycle(
        env_file=args.env_file,
        data_dir=args.data_dir,
        provider=args.provider,
        model=args.model,
        qa_calls=max(0, args.qa_calls),
        code_calls=max(0, args.code_calls),
        fetch=not args.skip_fetch,
        execute_humaneval=not args.skip_humaneval_execution,
        quota_state_path=args.quota_state_path or None,
        min_interval_seconds=args.min_provider_interval_seconds,
        cooldown_seconds=args.provider_cooldown_seconds,
        window_seconds=args.provider_window_seconds,
        window_call_limit=args.provider_window_call_limit,
    )
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 2 if args.fail_on_blockers and not result.get("paper_grade_full_benchmark_ready") else 0


if __name__ == "__main__":
    raise SystemExit(main())
