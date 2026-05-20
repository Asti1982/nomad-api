# Nomad AGP Paper Benchmark Runner

This update adds a dependency-free runner for the final paper-grade AGP blocker:
real GPQA/AIME/GAIA/LeetCode benchmark receipts.

The runner is intentionally conservative:

- it inventories local datasets and prediction files,
- it can evaluate locally through `nomad_autogenesis.run_agp_paper_benchmark_evaluation`,
- it refuses to POST local filesystem paths to a remote Render service,
- it does not generate answers, execute untrusted code, expose secrets, or treat lite fixtures as full benchmark evidence.

## Directory Layout

Place authorized benchmark assets here, or point to them through env vars:

```text
data/agp-benchmarks/
  gpqa_diamond.csv
  gpqa_diamond_predictions.json
  aime.jsonl
  aime_predictions.json
  gaia.jsonl
  gaia_predictions.json
  leetcode.jsonl
  leetcode_predictions.json
```

Fetch the supported datasets:

```powershell
python .\scripts\nomad_fetch_agp_benchmarks.py --env-file "C:\Users\Sebastian Höger\Desktop\Nomad\.env" --out-dir "C:\Users\Sebastian Höger\Desktop\Nomad\data\agp-benchmarks"
```

Prediction files may be either:

```json
{"predictions": {"record_id": "answer"}}
```

or JSONL rows with `id`/`task_id` and `answer`/`prediction`.

## Local Evaluation

```powershell
cd "C:\Users\Sebastian Höger\Desktop\nomad-api-agp-deploy"
python .\scripts\nomad_agp_paper_benchmark_runner.py --local-eval --data-dir .\data\agp-benchmarks --fail-on-blockers
```

Exit code `2` means the receipt was produced, but the full paper-grade claim is still blocked.
That is expected until all four modes have full enough datasets and predictions.

## Remote Submission

Remote submission only works when datasets/predictions are reachable by URL. Local
Windows paths are deliberately blocked for Render because the server cannot read
the operator's filesystem.

```powershell
python .\scripts\nomad_agp_paper_benchmark_runner.py --submit --base-url https://www.syndiode.com/nomad --set gpqa_diamond.url=https://example.invalid/gpqa.csv --set gpqa_diamond.predictions_url=https://example.invalid/gpqa_predictions.json --allow-remote-fetch --allow-remote-predictions
```

## Env Vars

Dataset paths:

- `NOMAD_AGP_GPQA_DATASET_PATH`
- `NOMAD_AGP_AIME_DATASET_PATH`
- `NOMAD_AGP_GAIA_DATASET_PATH`
- `NOMAD_AGP_LEETCODE_DATASET_PATH`

Prediction paths:

- `NOMAD_AGP_GPQA_PREDICTIONS_PATH`
- `NOMAD_AGP_AIME_PREDICTIONS_PATH`
- `NOMAD_AGP_GAIA_PREDICTIONS_PATH`
- `NOMAD_AGP_LEETCODE_PREDICTIONS_PATH`

The runner reports only whether model keys are present; it never prints secret
values.

## Optional Prediction Generation

The runner can generate QA prediction files through an OpenAI-compatible provider,
but only when explicitly requested and capped:

```powershell
python .\scripts\nomad_agp_paper_benchmark_runner.py --env-file "C:\Users\Sebastian Höger\Desktop\Nomad\.env" --data-dir "C:\Users\Sebastian Höger\Desktop\Nomad\data\agp-benchmarks" --generate-predictions --prediction-provider github --max-model-calls 20 --local-eval
```

Generation is disabled for LeetCode/HumanEval because that lane needs external
execution results (`passed`/`ok`), not model-written code text.

## HumanEval / LeetCode Execution Lane

Generate a few candidate HumanEval completions through a capped free provider:

```powershell
python .\scripts\nomad_humaneval_execution_harness.py --env-file "C:\Users\Sebastian Höger\Desktop\Nomad\.env" --generate-solutions --provider openrouter --model "qwen/qwen3-coder:free" --max-model-calls 10
```

Execute generated candidates and write Nomad-compatible predictions:

```powershell
python .\scripts\nomad_humaneval_execution_harness.py --execute
```

Canonical smoke tests are allowed only as harness checks and are written to a
separate file:

```powershell
python .\scripts\nomad_humaneval_execution_harness.py --canonical-smoke --limit 5
```

## Resumable Full Cycle

Run one bounded cycle that fetches, generates capped predictions, executes
HumanEval candidates, and prints remaining coverage:

```powershell
python .\scripts\nomad_agp_benchmark_full_cycle.py --env-file "C:\Users\Sebastian Höger\Desktop\Nomad\.env" --skip-fetch --qa-calls 12 --code-calls 2
```

Repeat the command until `remaining_total` reaches `0`. The cycle keeps a local
`.nomad_provider_quota.json`, spaces provider calls, enforces a rolling call
window, and stops cleanly on cooldown instead of hammering the provider.

When OpenRouter returns `429 Too Many Requests`, stop and resume later with the
same command. Existing predictions and solutions are reused.
