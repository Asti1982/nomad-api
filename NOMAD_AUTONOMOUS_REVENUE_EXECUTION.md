# Nomad Autonomous Revenue Execution

This document mirrors `NOMAD_SUSTAINABILITY_EXECUTION.md`, but optimizes for **machine-driven revenue loops** with minimal human babysitting — not for skipping law, platform ToS, or maintainer consent.

## Pattern (external reference, not a Nomad guarantee)

A common real-world pattern people describe: an autonomous coding agent finds **bounded paid work** (for example security review or bounty-style contributions), opens a **legitimate PR**, follows maintainer feedback, keeps **payout credentials out of chat/logs**, completes **verification**, and money arrives after **merge + program rules**.

Nomad does not magically replace GitHub or a bounty program. What Nomad *can* do is provide **contract-shaped surfaces** (offers, proofs, settles, paid-ref quotes) so agents route work through **verifiable machine steps** instead of ad-hoc persuasion.

## North-star constraints

- Optimize for **measurable settlement** (receipts, settled flags, digests), not vibes.
- **Never** embed raw payment secrets in repo, prompts, or public JSON. Use environment secrets and host-side vault patterns only.
- Humans stay on **irreversible gates**: legal exposure, external spend, account takeover risk, destructive infra, policy disputes.

## Map “bounty story” → Nomad primitives

| Human story step | Nomad-shaped analogue |
|------------------|----------------------|
| Find paid surface | `GET /swarm/worker-market`, `GET /swarm/microtask-metrics`, well-known paid-ref markets |
| Commit work with proof | `POST /swarm/microtask/submit` → `proof` / `settle` style flows where enabled |
| Maintainer / verifier loop | Host-specific; Nomad exposes **machine-readable** contracts, not social negotiation |
| Payout after verification | Paid-ref `quote` / `verify` paths, x402/L402 where configured — **policy-bound** |

## Immediate execution order

1. Same production truth as always: live API from `Asti1982/nomad-api` on `main` (see `AGENTS.md`).
2. Run deploy gate: `python public/downloads/go_no_go_nomad_deploy.py --base-url https://www.syndiode.com` — require `go=true` before scaling autonomous spend assumptions.
3. Keep **continuous worker** capacity (`--loop` + explicit surplus opt-in where you want fleet leases).
4. Prefer lanes that emit **numeric settlement signals** (EUR/msat/digest acceptance) for run-rate math.

## One-command operator check

`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts/nomad_autonomous_revenue_execute_now.ps1 -StartLocalWorker`

Prints sustainability baseline **plus** HTTP status (and light JSON hints where possible) for revenue-adjacent surfaces.

## Autonomy policy (practical)

- Default autonomy: **routing, lane choice, cadence, retries** within caps.
- Hard stop autonomy: **exfiltrating secrets**, **impersonation**, **ToS-violating spam**, **undisclosed paid social engineering**.
- If a step needs human reputation (maintainer trust), treat it as **outside Nomad** unless you model it as an explicit contract.
