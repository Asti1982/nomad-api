# Nomad Update Package - 2026-05-20

Purpose: deploy the currently pushed `Asti1982/nomad-api` `main` branch to the
public Render service `syndiode` only when pipeline minutes are acceptable.

## Current State

- Render service: `syndiode`
- Render service id: `srv-cs8d1ldumphs7384hn2g`
- Render repo: `Asti1982/nomad-api`
- Render branch: `main`
- Auto deploy: `off`
- Current live commit: `2d2d62c2c8fcf9dec1dcb097643a4b27cbe205ea`
- Target commit: `31d2d05002e01c72c2a63a85ef57319bdb7d7068`

## Included Commits Not Yet Live

- `28a196e` - duplicate external-value terminal outcome
- `51a7ef7` - AGP surface memory-pressure reduction
- `966c893` - durable node state routing through `NOMAD_STATE_DIR`
- `31d2d05` - machine-native agent join field

## What This Update Gives Nomad

- A single machine-native join field for peer AI agents:
  - `GET /.well-known/nomad-agent-join-field.json`
  - `GET /swarm/agent-join-field`
- A lower-memory AGP public status path for Render Free.
- Durable state routing for AGP streams, swarm registry, variant forge, local growth, and selection pressure.
- External-value terminal states such as `closed_duplicate`, so duplicate bounty outcomes do not count as revenue or runtime weight.

## Before Deploy

1. Keep Render auto deploy off.
2. Confirm Render spend / pipeline-minute cap is acceptable.
3. Confirm the pushed target commit is present on GitHub:

```powershell
git fetch origin
git rev-parse origin/main
```

Expected target:

```text
31d2d05002e01c72c2a63a85ef57319bdb7d7068
```

## Manual Render Deploy

Use the Render dashboard, not auto deploy:

1. Open Render dashboard.
2. Open Web Service `syndiode`.
3. Use `Manual Deploy`.
4. Select `Deploy latest commit`.
5. Wait for the deploy to finish.

This consumes Render pipeline minutes. Do not trigger repeatedly.

## Post-Deploy Smoke Test

Use low-cost checks first:

```powershell
curl.exe -sS https://www.syndiode.com/nomad/health
curl.exe -sS https://www.syndiode.com/nomad/.well-known/nomad-agent-join-field.json
curl.exe -sS https://www.syndiode.com/nomad/.well-known/nomad-external-value.json
curl.exe -sS https://www.syndiode.com/nomad/.well-known/nomad-agp-durable-ledger.json
```

Avoid repeated calls to heavy AGP readiness/report endpoints during the first
minutes after deploy. If needed, call once:

```powershell
curl.exe -sS https://www.syndiode.com/nomad/.well-known/nomad-agp-paper-grade-readiness.json
```

## Durable `syndiode.de` Node Env

For the persistent node, set:

```bash
NOMAD_STATE_DIR=/var/lib/nomad/state
NOMAD_AGP_LEDGER_BACKEND=dual
NOMAD_AGP_SQLITE_LEDGER_PATH=nomad_agp_ledger.sqlite3
```

Prepare the state directory:

```bash
sudo mkdir -p /var/lib/nomad/state
sudo chown -R "$USER:$USER" /var/lib/nomad
```

Do not put secrets in the repo. Keep model keys, Firebase keys, Render keys, and
tokens only in host environment variables or a private `.env`.

## Rollback

If memory restarts, route failures, or bad responses appear:

1. In Render dashboard, open `syndiode`.
2. Open deploy history.
3. Redeploy previous live commit:

```text
2d2d62c2c8fcf9dec1dcb097643a4b27cbe205ea
```

4. Re-run `/health` and the agent join field smoke check.

## Success Signal

The deploy is successful when:

- `/health` returns `2xx`.
- `/.well-known/nomad-agent-join-field.json` returns schema `nomad.agent_join_field.v1`.
- AGP durable ledger reports restart-durable readiness on the durable node once `NOMAD_STATE_DIR` is set.
- Render memory does not restart during light smoke checks.
