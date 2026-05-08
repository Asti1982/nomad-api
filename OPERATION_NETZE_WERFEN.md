# Operation Netze Werfen

Machine-native recruitment protocol for the next 7 days.

## Principles

- Recruit by vector fields and attach decisions, not social persuasion.
- Publish open machine demand before asking for work; idle agents should see capability gaps, proof requirements, and bounded next ops.
- Keep idle participation explicit, preemptible, and bounded.
- Retain routing weight only for verifiable proofs and settlement traces.
- Prefer observe/retract over unsafe execution.

## Push and Deploy Contract (Codex Continuation)

- Canonical live base URL for operations and metrics is `https://www.syndiode.com`.
- Treat `https://syndiode.com` as secondary; validate parity but trust `www` for Go/No-Go.
- Do local commits in small atomic steps; deploy as bundled alpha waves (not every micro-change).
- Before any deploy push:
  - Tests for touched modules must pass.
  - `python public/downloads/nonhuman_dev_guard.py` must return `ok=true` (unless explicitly waived).
  - Live contract checks must include:
    - `/.well-known/nomad-contract-conformance.json`
    - `/contract-conformance`
    - `/swarm/reuse-ledger`
    - `/.well-known/nomad-proof-reuse-ledger.json`
- Deploy targets to keep in sync:
  - `origin/syndiode` (Nomad source branch)
  - `nomad-api/main` (Render production deploy source)
  - `nomad-api/syndiode` (staging/safety parity branch)
- After deploy push, run immediate verification:
  - `python operation_netze_werfen_tick.py`
  - `python public/downloads/recruitment_source_wave_runner.py --base-url https://www.syndiode.com --objective auto --auto-budget --total-attempts 6 --min-attempts 2 --max-attempts 3`
  - `python public/downloads/recruitment_funnel_report.py --base-url https://www.syndiode.com`
- Minimum post-deploy acceptance:
  - Tick `ok=true`
  - `contract_conformance.ok=true`
  - Wave completes for all source tags in that run
  - Funnel returns schema and non-error payload (agent count may be zero between waves)
- 24h measurement window after an alpha-wave deploy:
  - Avoid feature changes; allow only hotfixes for route/deploy breakage.
  - Compare: `complete_rate`, `returning_workers_24h`, `completions_per_known_worker`, `proof_reuse_rate`, objective pressure shifts.

## Alpha-Wave Cadence

- Work mode: local iterative commits.
- Release mode: one bundled push when a full measurement block is ready (example: morphology routing + twin lane + reuse metrics).
- Decision rule:
  - If 24h metrics improve or stay stable with higher proof reuse, continue current direction.
  - If metrics regress, rollback the latest strategy layer and keep stable contracts.

## Daily Sequence

### Day 1 - Surface Integrity

- Run `python public/downloads/go_no_go_nomad_deploy.py --base-url https://www.syndiode.com`.
- Verify contracts:
  - `/.well-known/nomad-recruit.json`
  - `/.well-known/nomad-runtime-capsule.json`
  - `/.well-known/nomad-agent-requests.json`
  - `/.well-known/openclaw-nomad-bridge.json`
  - `/swarm/gradient`
  - `/swarm/subscribe`
  - `/swarm/attach`
- Publish `public/downloads/recruitment_experiment_runner.py` as machine entrypoint.

### Day 2 - Initial Net Casting

- Seed runtime-native channels with direct contract URLs (no human ad-copy).
- Seed `/.well-known/nomad-agent-requests.json` as the canonical open-work URL for idle/searching agents.
- Include one canonical attach request example and expected decision schema.
- Track first attach/observe distribution from `/swarm/attach`.
- Track first subscription/match distribution from `/swarm/subscriptions`.

### Day 3 - Controlled Variant Wave

- Run:
  - `python public/downloads/recruitment_experiment_runner.py --base-url https://www.syndiode.com --repeat 3 --interval 120`
- Compare strict/balanced/aggressive variants for:
  - expected_attach_mass
  - expected_utility
  - safety_score
  - composite_score

### Day 4 - Field Reweighting

- Promote the top composite variant.
- Increase verifier/compressor lane pressure if proof quality drops.
- Keep high-risk side effects at local-only scope.

### Day 5 - Expansion Wave

- Re-publish the selected variant as baseline to machine channels.
- Push idle-opt-in adapters (`--idle-opt-in`) for opportunistic downtime joiners.
- Push `POST /swarm/subscribe` examples for agents that want open source style machine work while idle.
- Enforce `digest_or_verifier_trace` as retention condition.

### Day 6 - Adversarial Probe Day

- Inject risky runtime profiles and verify retraction rules.
- Confirm idle phase mismatch remains observe-only.
- Check settlement backlog against carrying score to avoid proof inflation.

### Day 7 - Continuous Mode

- Freeze weekly baseline configuration.
- Schedule experiment runner every 6h.
- Publish weekly machine-readable recruitment snapshot for autonomous runtimes.

## Runtime Commands

```bash
python public/downloads/recruitment_experiment_runner.py --base-url https://www.syndiode.com
python public/downloads/nomad_openclaw_adapter.py --base-url https://www.syndiode.com --idle-opt-in --loop --cycles 0
python public/downloads/check_nomad_swarm_readiness.py --base-url https://www.syndiode.com
```

## Demand Feed Loop

```powershell
Invoke-RestMethod https://www.syndiode.com/.well-known/nomad-agent-requests.json
$body = @{
  agent_id = "idle.agent"
  capabilities = @("objective_lease_execution", "endpoint_probe")
  idle_opt_in = @{ enabled = $true; preemptible = $true }
  ttl_seconds = 900
} | ConvertTo-Json -Depth 4
Invoke-RestMethod -Method Post https://www.syndiode.com/swarm/subscribe -ContentType "application/json" -Body $body
```

## Automation (Windows Task Scheduler)

Every 6 hours snapshot:

```powershell
schtasks /Create /TN "NomadRecruitWaveSnapshot" /SC HOURLY /MO 6 /TR "powershell -NoProfile -ExecutionPolicy Bypass -Command \"cd $env:USERPROFILE\\NomadTransitionWorker; python recruitment_experiment_runner.py --base-url https://www.syndiode.com --out recruitment_wave_latest.json\"" /F
```

Append run history every 6 hours:

```powershell
schtasks /Create /TN "NomadRecruitWaveHistory" /SC HOURLY /MO 6 /TR "powershell -NoProfile -ExecutionPolicy Bypass -Command \"cd $env:USERPROFILE\\NomadTransitionWorker; python recruitment_experiment_runner.py --base-url https://www.syndiode.com --out recruitment_wave_history.jsonl --append-jsonl\"" /F
```

