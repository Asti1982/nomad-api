# Nomad Sustainability Execution

This is the "do now" operating path when the goal is short-term sustainability without human micromanagement.

## North-Star constraints

- Optimize for **live deployed capability + measurable settled value**, not local branch comfort.
- Keep humans on **irreversible gates only** (secrets, external spend, destructive actions).
- Everything else should be machine-executable and checkable.

## Immediate execution order

1. Verify Render deploy source and live commit:
   - `python nomad_cli.py render --json`
   - Live production for `syndiode.com` is expected from `Asti1982/nomad-api` on `main` (see `AGENTS.md`).
2. Enforce production gate:
   - `python public/downloads/go_no_go_nomad_deploy.py --base-url https://www.syndiode.com`
   - Treat `go=false` as a hard no-go for "production ready" claims.
3. Keep worker substrate alive:
   - Ensure at least one continuously running transition worker (`--loop --swarm-surplus`).
4. Prioritize paid lanes:
   - Keep only lanes with measurable settle/proof outcomes in the short-term focus set.

## One-command operator check

Use:

`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\nomad_sustainability_execute_now.ps1 -StartLocalWorker`

It prints:
- Render service/repo/branch and live commit
- public endpoint smoke statuses
- deploy go/no-go summary
- local worker state (and optional watchdog-triggered start)

## Autonomy policy (practical)

- Autonomy default: enabled for routing/objective/cadence decisions.
- Human approval required only for:
  - secret rotation/exfiltration,
  - external paid actions,
  - destructive infrastructure changes.
- If uncertain, prefer reversible action and emit machine-readable status.
