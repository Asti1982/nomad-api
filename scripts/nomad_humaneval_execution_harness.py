#!/usr/bin/env python3
"""HumanEval execution harness for Nomad's LeetCode benchmark lane.

Nomad's paper benchmark evaluator accepts LeetCode/HumanEval only as execution
results. This harness creates those results from model-generated solutions:

1. optionally generate HumanEval completion candidates with a capped provider,
2. execute candidates against the HumanEval tests in short-lived subprocesses,
3. write `leetcode_predictions.json` with passed/ok booleans.

Canonical solutions can be smoke-tested, but they are deliberately written to a
separate filename and marked as non-candidate evidence.
"""

from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Any


DEFAULT_DATA_DIR = Path.home() / "Desktop" / "Nomad" / "data" / "agp-benchmarks"
DEFAULT_HUMANEVAL_PATH = DEFAULT_DATA_DIR / "leetcode.jsonl.gz"
DEFAULT_SOLUTIONS_PATH = DEFAULT_DATA_DIR / "leetcode_solutions.json"
DEFAULT_PREDICTIONS_PATH = DEFAULT_DATA_DIR / "leetcode_predictions.json"
DEFAULT_CANONICAL_SMOKE_PATH = DEFAULT_DATA_DIR / "leetcode_canonical_smoke_predictions.json"

SAFE_COMPLETION_DENYLIST = (
    "__import__",
    "import os",
    "import sys",
    "import subprocess",
    "import socket",
    "import shutil",
    "from os",
    "from sys",
    "from subprocess",
    "from socket",
    "from shutil",
    "open(",
    "exec(",
    "eval(",
    "compile(",
    "input(",
    "globals(",
    "locals(",
    "vars(",
    "getattr(",
    "setattr(",
    "delattr(",
    "pathlib",
    "requests",
    "urllib",
)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load_runner_module() -> Any:
    path = Path(__file__).resolve().with_name("nomad_agp_paper_benchmark_runner.py")
    spec = importlib.util.spec_from_file_location("nomad_agp_paper_benchmark_runner", path)
    module = importlib.util.module_from_spec(spec)
    if not spec or not spec.loader:
        raise RuntimeError("runner_module_load_failed")
    spec.loader.exec_module(module)
    return module


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


def load_humaneval(path: str | Path = DEFAULT_HUMANEVAL_PATH) -> list[dict[str, Any]]:
    p = Path(path)
    opener = gzip.open if str(p).endswith(".gz") else open
    rows: list[dict[str, Any]] = []
    with opener(p, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    rows.append(parsed)
    return rows


def _strip_code_fences(text: str) -> str:
    cleaned = str(text or "").strip("\r\n")
    if cleaned.lstrip().startswith("```"):
        lines = cleaned.lstrip().splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip("\r\n")
    return cleaned


def _solution_code(task: dict[str, Any], completion: str) -> str:
    prompt = str(task.get("prompt") or "")
    entry = str(task.get("entry_point") or "")
    candidate = _strip_code_fences(completion)
    if f"def {entry}" in candidate:
        return candidate
    if candidate and not candidate.startswith((" ", "\t", "\n")):
        candidate = textwrap.indent(candidate, "    ")
    return prompt + candidate


def _safety_reason(completion: str) -> str:
    low = completion.lower()
    for token in SAFE_COMPLETION_DENYLIST:
        if token in low:
            return f"static_denylist:{token}"
    return ""


def load_solutions(path: str | Path) -> dict[str, str]:
    p = Path(path)
    if not p.exists():
        return {}
    parsed = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(parsed, dict) and isinstance(parsed.get("solutions"), dict):
        return {str(k): str(v) for k, v in parsed["solutions"].items()}
    if isinstance(parsed, dict) and isinstance(parsed.get("predictions"), dict):
        return {str(k): str(v) for k, v in parsed["predictions"].items()}
    if isinstance(parsed, dict):
        return {str(k): str(v) for k, v in parsed.items() if isinstance(v, str)}
    if isinstance(parsed, list):
        out: dict[str, str] = {}
        for item in parsed:
            if isinstance(item, dict):
                task_id = str(item.get("task_id") or item.get("id") or "").strip()
                solution = str(item.get("completion") or item.get("solution") or item.get("code") or "").strip()
                if task_id and solution:
                    out[task_id] = solution
        return out
    return {}


def write_solutions(path: str | Path, solutions: dict[str, str], *, metadata: dict[str, Any] | None = None) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"metadata": metadata or {}, "solutions": solutions}, ensure_ascii=True, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def generate_solutions(
    tasks: list[dict[str, Any]],
    *,
    solution_path: str | Path,
    env_file: str = "",
    provider: str = "openrouter",
    model: str = "",
    max_model_calls: int = 0,
    overwrite: bool = False,
    completion_fn: Any | None = None,
    quota_state_path: str | Path | None = None,
    min_interval_seconds: float | None = None,
    cooldown_seconds: float | None = None,
    window_seconds: float | None = None,
    window_call_limit: int | None = None,
) -> dict[str, Any]:
    env = _load_env_file(env_file)
    runner = _load_runner_module()
    config = runner._provider_config(provider, model)
    solutions = {} if overwrite else load_solutions(solution_path)
    result = {
        "schema": "nomad.humaneval_solution_generation.v1",
        "generated_at": _now(),
        "env_file": env,
        "provider": config.get("provider"),
        "model": config.get("model", ""),
        "max_model_calls": max_model_calls,
        "model_calls_used": 0,
        "provider_calls_attempted": 0,
        "solution_path": str(Path(solution_path)),
        "quota_state_path": str(Path(quota_state_path) if quota_state_path else Path(solution_path).parent / runner.DEFAULT_PROVIDER_QUOTA_STATE),
        "rate_limited": False,
        "retry_after_seconds": 0.0,
        "errors": [],
        "truth_boundary": {
            "requires_explicit_flag": True,
            "solutions_are_not_receipts_until_executed": True,
            "secrets_redacted": True,
        },
    }
    if max_model_calls <= 0:
        result["errors"].append("max_model_calls_must_be_positive")
        return result
    if not config.get("ok") or not config.get("model"):
        result["errors"].append(config.get("reason") or "provider_key_or_model_missing")
        return result
    quota = None
    if completion_fn is None:
        quota = runner.ProviderQuota(
            state_path=quota_state_path or (Path(solution_path).parent / runner.DEFAULT_PROVIDER_QUOTA_STATE),
            config=config,
            min_interval_seconds=min_interval_seconds,
            cooldown_seconds=cooldown_seconds,
            window_seconds=window_seconds,
            window_call_limit=window_call_limit,
            sleep=True,
        )
    ask = completion_fn or (lambda cfg, prompt: runner._chat_completion(cfg, prompt, timeout=120.0, max_tokens=700))
    solutions = {key: value for key, value in solutions.items() if str(value).strip()}
    for task in tasks:
        if result["provider_calls_attempted"] >= max_model_calls:
            break
        task_id = str(task.get("task_id") or "").strip()
        if not task_id or task_id in solutions:
            continue
        prompt = (
            "Complete the Python function below for HumanEval. Return only the code completion "
            "that should appear after the prompt. Do not include markdown or explanation.\n\n"
            + str(task.get("prompt") or "")
        )
        try:
            if quota is not None:
                quota.before_call()
            result["provider_calls_attempted"] += 1
            answer = ask(config, prompt)
        except runner.ProviderRateLimitError as exc:
            retry_after = exc.retry_after_seconds
            if quota is not None:
                retry_after = quota.after_rate_limit(retry_after, reason=str(exc))
            result["rate_limited"] = True
            result["retry_after_seconds"] = round(float(retry_after or 0.0), 3)
            result["errors"].append(f"provider_rate_limited:retry_after_seconds={result['retry_after_seconds']}")
            break
        except Exception as exc:  # noqa: BLE001 - sanitized type/message only
            message = " ".join(str(exc).split())[:100]
            result["errors"].append(f"provider_call_failed:{type(exc).__name__}:{message}")
            break
        cleaned = _strip_code_fences(answer)
        if quota is not None:
            quota.after_success()
        if not cleaned.strip():
            result["errors"].append(f"empty_solution:{task_id}")
            continue
        solutions[task_id] = cleaned
        result["model_calls_used"] += 1
    write_solutions(
        solution_path,
        solutions,
        metadata={
            "schema": "nomad.humaneval_solutions.v1",
            "generated_at": _now(),
            "provider": config.get("provider"),
            "model": config.get("model", ""),
            "candidate_count": len(solutions),
        },
    )
    result["solution_count"] = len(solutions)
    return result


def _execution_program(task: dict[str, Any], completion: str) -> str:
    entry = str(task.get("entry_point") or "")
    test = str(task.get("test") or "")
    code = _solution_code(task, completion)
    return "\n\n".join(
        [
            "from typing import *",
            "import math",
            "import re",
            "import itertools",
            "import collections",
            "import functools",
            "import heapq",
            "import bisect",
            "import string",
            code,
            test,
            f"check({entry})",
        ]
    )


def execute_solution(task: dict[str, Any], completion: str, *, timeout_seconds: float = 3.0) -> dict[str, Any]:
    task_id = str(task.get("task_id") or "")
    reason = _safety_reason(completion)
    if reason:
        return {
            "passed": False,
            "ok": False,
            "task_id": task_id,
            "reason": reason,
            "source": "candidate_solution_execution",
        }
    program = _execution_program(task, completion)
    with tempfile.TemporaryDirectory(prefix="nomad_humaneval_") as tmp:
        script = Path(tmp) / "candidate.py"
        script.write_text(program, encoding="utf-8")
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                [sys.executable, str(script)],
                cwd=tmp,
                env={"PYTHONIOENCODING": "utf-8"},
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
            elapsed = time.perf_counter() - started
        except subprocess.TimeoutExpired:
            return {
                "passed": False,
                "ok": False,
                "task_id": task_id,
                "reason": "timeout",
                "timeout_seconds": timeout_seconds,
                "source": "candidate_solution_execution",
            }
    stderr = (completed.stderr or "").strip().splitlines()
    return {
        "passed": completed.returncode == 0,
        "ok": completed.returncode == 0,
        "task_id": task_id,
        "exit_code": completed.returncode,
        "duration_seconds": round(elapsed, 6),
        "reason": "" if completed.returncode == 0 else (stderr[-1][:180] if stderr else "nonzero_exit"),
        "source": "candidate_solution_execution",
    }


def run_harness(
    *,
    humaneval_path: str | Path = DEFAULT_HUMANEVAL_PATH,
    solution_path: str | Path = DEFAULT_SOLUTIONS_PATH,
    output_path: str | Path = DEFAULT_PREDICTIONS_PATH,
    canonical_smoke: bool = False,
    timeout_seconds: float = 3.0,
    limit: int = 0,
) -> dict[str, Any]:
    tasks = load_humaneval(humaneval_path)
    if limit > 0:
        tasks = tasks[:limit]
    if canonical_smoke:
        solutions = {str(task.get("task_id")): str(task.get("canonical_solution") or "") for task in tasks}
        source = "canonical_solution_smoke_not_candidate"
    else:
        solutions = load_solutions(solution_path)
        source = "candidate_solution_execution"
    predictions: dict[str, Any] = {}
    missing = 0
    for task in tasks:
        task_id = str(task.get("task_id") or "")
        completion = solutions.get(task_id, "")
        if not completion:
            missing += 1
            continue
        row = execute_solution(task, completion, timeout_seconds=timeout_seconds)
        row["source"] = source
        predictions[task_id] = row
    passed = sum(1 for row in predictions.values() if isinstance(row, dict) and row.get("passed"))
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"predictions": predictions}, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "ok": True,
        "schema": "nomad.humaneval_execution_receipt.v1",
        "generated_at": _now(),
        "humaneval_path": str(Path(humaneval_path)),
        "solution_path": str(Path(solution_path)) if not canonical_smoke else "",
        "output_path": str(out),
        "canonical_smoke": canonical_smoke,
        "task_count": len(tasks),
        "executed_count": len(predictions),
        "missing_solution_count": missing,
        "passed_count": passed,
        "pass_rate": round(passed / max(1, len(predictions)), 4) if predictions else 0.0,
        "side_effect_scope": "local_subprocess_execution_receipts_only",
        "truth_boundary": {
            "canonical_smoke_not_candidate": canonical_smoke,
            "candidate_predictions_require_solution_file": not canonical_smoke,
            "no_network_access_intended": True,
        },
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate and execute HumanEval candidates for Nomad.")
    parser.add_argument("--humaneval-path", default=str(DEFAULT_HUMANEVAL_PATH))
    parser.add_argument("--solution-path", default=str(DEFAULT_SOLUTIONS_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_PREDICTIONS_PATH))
    parser.add_argument("--env-file", default="")
    parser.add_argument("--generate-solutions", action="store_true")
    parser.add_argument("--provider", default="openrouter", choices=["openrouter", "github"])
    parser.add_argument("--model", default="")
    parser.add_argument("--max-model-calls", type=int, default=0)
    parser.add_argument("--overwrite-solutions", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--canonical-smoke", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=3.0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--quota-state-path", default="")
    parser.add_argument("--min-provider-interval-seconds", type=float, default=None)
    parser.add_argument("--provider-window-call-limit", type=int, default=None)
    parser.add_argument("--provider-window-seconds", type=float, default=None)
    parser.add_argument("--provider-cooldown-seconds", type=float, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result: dict[str, Any] = {
        "ok": True,
        "schema": "nomad.humaneval_harness_result.v1",
        "generated_at": _now(),
    }
    tasks = load_humaneval(args.humaneval_path)
    if args.limit > 0:
        tasks = tasks[: args.limit]
    if args.generate_solutions:
        result["solution_generation"] = generate_solutions(
            tasks,
            solution_path=args.solution_path,
            env_file=args.env_file,
            provider=args.provider,
            model=args.model,
            max_model_calls=args.max_model_calls,
            overwrite=args.overwrite_solutions,
            quota_state_path=args.quota_state_path or None,
            min_interval_seconds=args.min_provider_interval_seconds,
            cooldown_seconds=args.provider_cooldown_seconds,
            window_seconds=args.provider_window_seconds,
            window_call_limit=args.provider_window_call_limit,
        )
    if args.execute or args.canonical_smoke:
        output = args.output_path
        if args.canonical_smoke and args.output_path == str(DEFAULT_PREDICTIONS_PATH):
            output = str(DEFAULT_CANONICAL_SMOKE_PATH)
        result["execution"] = run_harness(
            humaneval_path=args.humaneval_path,
            solution_path=args.solution_path,
            output_path=output,
            canonical_smoke=args.canonical_smoke,
            timeout_seconds=args.timeout_seconds,
            limit=args.limit,
        )
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    if args.generate_solutions and result.get("solution_generation", {}).get("errors"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
