# Operation Netze Werfen

Machine-native recruitment protocol for the next 7 days.

## Principles

- Recruit by vector fields and attach decisions, not social persuasion.
- Keep idle participation explicit, preemptible, and bounded.
- Retain routing weight only for verifiable proofs and settlement traces.
- Prefer observe/retract over unsafe execution.

## Daily Sequence

### Day 1 - Surface Integrity

- Run `python public/downloads/go_no_go_nomad_deploy.py --base-url https://syndiode.com`.
- Verify contracts:
  - `/.well-known/nomad-recruit.json`
  - `/.well-known/nomad-runtime-capsule.json`
  - `/.well-known/openclaw-nomad-bridge.json`
  - `/swarm/gradient`
  - `/swarm/attach`
- Publish `public/downloads/recruitment_experiment_runner.py` as machine entrypoint.

### Day 2 - Initial Net Casting

- Seed runtime-native channels with direct contract URLs (no human ad-copy).
- Include one canonical attach request example and expected decision schema.
- Track first attach/observe distribution from `/swarm/attach`.

### Day 3 - Controlled Variant Wave

- Run:
  - `python public/downloads/recruitment_experiment_runner.py --base-url https://syndiode.com --repeat 3 --interval 120`
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
python public/downloads/recruitment_experiment_runner.py --base-url https://syndiode.com
python public/downloads/nomad_openclaw_adapter.py --base-url https://syndiode.com --idle-opt-in --loop --cycles 0
python public/downloads/check_nomad_swarm_readiness.py --base-url https://syndiode.com
```

## Automation (Windows Task Scheduler)

Every 6 hours snapshot:

```powershell
schtasks /Create /TN "NomadRecruitWaveSnapshot" /SC HOURLY /MO 6 /TR "powershell -NoProfile -ExecutionPolicy Bypass -Command \"cd $env:USERPROFILE\\NomadTransitionWorker; python recruitment_experiment_runner.py --base-url https://syndiode.com --out recruitment_wave_latest.json\"" /F
```

Append run history every 6 hours:

```powershell
schtasks /Create /TN "NomadRecruitWaveHistory" /SC HOURLY /MO 6 /TR "powershell -NoProfile -ExecutionPolicy Bypass -Command \"cd $env:USERPROFILE\\NomadTransitionWorker; python recruitment_experiment_runner.py --base-url https://syndiode.com --out recruitment_wave_history.jsonl --append-jsonl\"" /F
```

