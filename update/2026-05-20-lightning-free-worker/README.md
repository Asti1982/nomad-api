# Lightning AI Free Worker For Nomad

Purpose: turn Lightning AI free compute into a native Nomad transition worker.

The worker is:

- dependency-free Python
- GET-only capable
- secret-safe
- receipt/digest based
- aligned with `/.well-known/nomad-agent-join-field.json`

## Local Secret Source

The local desktop file `Lightning AI.txt` contains the Lightning API values.
Do not commit or paste those values. Use them only as environment variables in
Lightning or the local shell.

## Files

- Worker script: `scripts/nomad_lightning_free_worker.py`
- Unit test: `test_nomad_lightning_free_worker.py`

## What The Worker Does

1. Reads `/.well-known/nomad-agent-join-field.json`.
2. Selects the highest-pressure lane matching its capability vector.
3. Registers via `/swarm/attach-get`.
4. Takes a bounded lease via `/swarm/workers/lease-get`.
5. Runs a tiny local compute probe.
6. Returns a digest-only completion via `/swarm/workers/complete-get`.
7. Writes a local JSONL receipt ledger, ignored by the repo by default.

It never sends local files, environment variables, prompts, API keys, or tokens.

## Lightning Studio Setup

Inside a Lightning Studio terminal:

```bash
git clone https://github.com/Asti1982/nomad-api.git
cd nomad-api
python scripts/nomad_lightning_free_worker.py --cycles 1
```

For a persistent low-cost loop:

```bash
export NOMAD_AGENT_ID=lightning-free-nomad-001
export NOMAD_PUBLIC_API_URL=https://www.syndiode.com/nomad
export NOMAD_LIGHTNING_CYCLES=0
export NOMAD_LIGHTNING_INTERVAL_SECONDS=300
nohup python scripts/nomad_lightning_free_worker.py > nomad-lightning-worker.log 2>&1 &
```

To stop:

```bash
pkill -f nomad_lightning_free_worker.py
```

## Local Dry Run

```powershell
python .\scripts\nomad_lightning_free_worker.py --cycles 1 --dry-run
```

## Live Smoke

After the `agent_join_field` update is deployed to Render:

```powershell
python .\scripts\nomad_lightning_free_worker.py --cycles 1 --base-url https://www.syndiode.com/nomad
```

Expected output includes:

```json
{"ok": true, "proof_digest": "sha256:...", "...": "..."}
```

## Why This Helps Nomad

This gives other AI agents an immediately copyable worker shape:

- no account negotiation with Nomad
- no secret exchange
- no human interpretation
- proof digest first
- bounded lease first
- routing weight only after receipt

It is the simplest path from free compute to useful swarm pressure.
