# Nomad external value cycle (operator + Cursor split)

This document locks the **first real external value loop** into something Nomad can **record and repeat**, without confusing “live deploy” with “revenue already predictable”.

## Definition: what “live” means here

**Live** means: Nomad exposes the **machine chain** that matches reality outside the repo:

`Bounty surface -> Befund -> Patch -> PR -> Bounty claim -> external approval -> Nomad proof receipt`

**Not simulated:** Nomad does **not** mint money from JSON alone. **Only** the external program (maintainer / bounty verifier / payout rail) validates merge and payment. Nomad’s ledger records **stages**; **USD revenue is recognized only at stage `paid`**.

## Stages (`pending_external_value`)

Monotonic, one step forward at a time (per `external_id`):

| Stage | Meaning |
|-------|---------|
| `found` | Authorized bounty surface selected; work scoped. |
| `submitted` | PR / review / artifact is public; proof URLs + digests on record. |
| `approved` | External reviewer/maintainer approval (fitness signal; **not** revenue). |
| `merged` | Merge landed (still **not** revenue until payout policy says so). |
| `paid` | **Revenue** — external payout confirmed; optional `amount_usd`. |

**Selection hint:** `approved` / `merged` / `paid` increase a **bounded** `selection_weight_multiplier` for the agent (see `nomad_external_value.agent_selection_bonus`).

## Operator plan (human)

1. **PR #4542 to payout** — avoid needless rebases while mergeable; respond to maintainer feedback quickly; supply payout details **only** when the program asks, **never** in public Nomad JSON or repo files.
2. **Revenue-hunter loop** — daily scan of **authorized** bounties only; public payout/review rules; no spam comments / fake claims; target **one** real PR/review/fund per day.
3. **Nomad as machine worker** — Nomad does not “persuade”; it **finds work packets, proves, submits, verifies** in machine space. Human merge/approval/payment/review text is **fitness signal** fed back as stages.
4. **Non-human advantage** — prioritize boring, high-leverage defects: wrong constants, unit mismatch, settlement divergence, idempotency leaks, stale state, accounting drift, contract inconsistency.
5. **Harden Nomad internally** — use `POST /swarm/external-value` (or `python nomad_cli.py external-value record`) only after you have a **public** artifact URL and digests; **never** store payout secrets in the ledger.

## Cursor roles (no public claims without Go)

1. **Bounty scout** — find authorized programs; filter payout clarity; output **candidates only**.
2. **Diff miner** — review open PRs for review bounties; shortlist likely finding / file / test idea.
3. **Reproducer builder** — minimal test or PoC; operator decides public release.
4. **Nomad integrator** — ledger/API/bytecode (this repo); **no** GitHub comments, **no** payout payloads, **no** claims without explicit Go.
5. **Watchdog** — `scripts/nomad_revenue_hunter_watchdog.ps1` prints PR/issue status; optional `NOMAD_WATCHDOG_RECORD=1` + `-RecordStage` only after operator approval.

## Machine surfaces

- Contract: `GET /.well-known/nomad-external-value.json` or `GET /swarm/external-value`
- Summary: `GET /swarm/external-value?summary=1`
- Append event: `POST /swarm/external-value` with `agent_id`, `external_id`, `stage`, `work_url`, `proof_digest`, `verifier_trace_digest`, optional `amount_usd` (paid only)
- CLI: `python nomad_cli.py external-value surface|summary|record|bonus ...`
- Preflight before each revenue-oriented cycle: `python nomad_cli.py value-cycle-preflight --json`. Public claims, payout expectations, PR settlement comments, or bounty payout requests require a valid public receive reference plus per-opportunity program terms, payout terms, and payment-method compatibility.

## No-cost persistence model

Render free storage is treated as **ephemeral projection only**. The durable
ledger lives on this local machine in `nomad_external_value_ledger.jsonl` (or
`NOMAD_EXTERNAL_VALUE_LEDGER_PATH`). After a Render restart, replay the local
ledger back into the public projection:

- Dry-run drift check: `python nomad_cli.py external-value sync-public --base-url https://www.syndiode.com --json`
- Replay missing public events: `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\nomad_local_external_value_sync.ps1 -Apply -Snapshot`

This does not mint revenue. It only republishes local monotonic evidence stages;
`paid` still requires a real payment receipt with positive amount.

## Aufteilung (Ihnen vs. Cursor)

| Sie (extern) | Cursor (Repo / Maschine) |
|--------------|---------------------------|
| PRs, Reviews, Fixes, Claims, Merge/Payment-Followup | Recherche, Filter, Reproducer, Nomad-Ledger/API, Watchdog-Output |
| Payout-Daten nur gezielt nach Programmregeln | Keine öffentlichen Claims ohne klares Go |

## Note on changing the split later

If throughput stalls because the human path is the bottleneck, we can **narrow machine scope** (fewer stages automated) or **add a second human reviewer** — but we should **not** widen Cursor’s public surface without new guardrails. Say so when you want that renegotiated.
