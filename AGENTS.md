# Hinweise für AI-Agenten (Repo Nomad)

## Wo landet Production für syndiode.com?

Der öffentliche API-Origin auf Render ist **nicht** automatisch dieses Repo (`Asti1982/Nomad`), sondern das schlankere Deploy-Repo:

| Feld | Wert (Stand: per Render API verifizierbar mit `RENDER_API_KEY`) |
|------|------------------------------------------------------------------|
| Render-Service-Name | `syndiode` |
| Render-Service-ID | `srv-cs8d1ldumphs7384hn2g` |
| Öffentliche Render-URL | `https://syndiode.onrender.com` |
| GitHub-Repo (Build-Quelle) | `Asti1982/nomad-api` |
| Branch | `main` |
| Auto-Deploy | `no` (Stand 2026-05-29; Render API ist massgeblich) |

**Konsequenz:** Änderungen in **`Asti1982/Nomad`** (z. B. Branch `syndiode`) gehen **erst live**, wenn sie in **`Asti1982/nomad-api`** auf Branch **`main`** gemergt/gepusht sind und Render den Build abgeschlossen hat.

**Prüfen:** `python nomad_cli.py render --json` — unter `status.verification.services` bzw. `selected_service` stehen `repo`, `branch`, `url`; unter `recent_deploys` der zuletzt **live**e Commit.

Wenn `auto_deploy=no` ist, reicht ein Push nach `Asti1982/nomad-api/main` allein nicht aus: der Render-Deploy muss danach explizit angestossen oder per Render-Konsole/API reaktiviert werden.

## Zweiter Render-Web-Service (Referenz)

Es gibt zusätzlich den Service **`nomad-api`** (`srv-d7jc241kh4rs73fjmffg`), ebenfalls Repo **`Asti1982/nomad-api`**, Branch **`main`**, URL `https://nomad-api-4s84.onrender.com`. Apex/Custom-Domain-Routing entscheidet, welcher Host öffentlich genutzt wird; die Build-Quelle für beide ist dieselbe Codebasis auf `main`.

## Edge / Cloudflare

`syndiode.com` kann vor dem Origin noch **Cloudflare Worker / Pfad-Whitelist** haben. 404 auf einzelnen Pfaden heißt nicht zwingend „falscher Git-Branch“, sondern oft **Edge filtert** oder der Deploy ist noch alt. Zuerst Render-`commit_id` prüfen, dann Edge-Regeln.

## Render Budget Guardrails (mandatory)

Render bandwidth, build-minute, and free instance-hour warnings are production constraints. Before any public change, deploy, worker launch, or live verification, every agent must protect the Render budget:

- Prefer local tests over public endpoint probing; keep live checks to the smallest useful set.
- Do not run keepalive loops, repeated browser refreshes, or polling scripts against `syndiode.com`, `syndiode.de`, `syndiode.onrender.com`, or `nomad-api-4s84.onrender.com`.
- Do not start or leave Transition Workers polling public Render origins unless the user explicitly asks for that run. If a public worker loop is required, use long intervals (`>= 900` seconds) and stop it after the check.
- Do not upgrade instance types, enable paid Render features, create previews, add paid storage, or trigger repeated deploys without explicit user approval.
- Use the pattern: one full local test pass, one manual deploy if needed, one short live verification, then stop.
- Cancel stuck or unhealthy deploys instead of retrying in a loop.
- Keep health checks tiny and synchronous: `/health` must not scan ledgers, start workers, call external APIs, load models, or serve large assets.
- Serve APKs, EXEs, images, favicons, and gadget assets from static/cache/CDN-style paths where possible; dynamic API origins should serve contracts and small JSON.
- Treat duplicate public services (`syndiode` and `nomad-api`) as budget pressure. Prefer one canonical live API origin and let unused free services sleep.

End-of-month note: Render free instance hours reset at the start of the next calendar month, but on May 29-31 the remaining hours can still be exhausted quickly by two awake services or active public workers. Do not rely on the reset; preserve the remaining budget.

## Operativer Schnellcheck (Ausfuehrung statt Debatte)

Fuer direkte Tragfaehigkeits-Pruefung:

- `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\nomad_sustainability_execute_now.ps1 -StartLocalWorker`

Der Check kombiniert Render-Quelle, Public-Gate und lokalen Worker-Status in einem Lauf.

## Autonomer Umsatz (ohne Mikromanagement, mit Leitplanken)

Fuer Maschinen-getriebene Umsatzpfade (Worker-Markt, Microtask-Metriken, Paid-Ref-Oberflaechen, Bounty-Hunter) **zusaetzlich** zur Tragfaehigkeits-Baseline:

- `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\nomad_autonomous_revenue_execute_now.ps1 -StartLocalWorker`

Details und Grenzen (GitHub/Bounty-Story vs. Nomad-Vertraege): `NOMAD_AUTONOMOUS_REVENUE_EXECUTION.md`.

## Externer Wertzyklus (Bounty -> PR -> Zahlung)

Operativer Plan und Rollenaufteilung (PR #4542, Bounty #2819, Watchdog-Skript): **`NOMAD_EXTERNAL_VALUE_CYCLE.md`**.

Maschinen-Ledger (nur **paid** = Umsatz): `GET /.well-known/nomad-external-value.json`, `POST /swarm/external-value`, CLI `python nomad_cli.py external-value …`.
