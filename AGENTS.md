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
| Auto-Deploy | `yes` |

**Konsequenz:** Änderungen in **`Asti1982/Nomad`** (z. B. Branch `syndiode`) gehen **erst live**, wenn sie in **`Asti1982/nomad-api`** auf Branch **`main`** gemergt/gepusht sind und Render den Build abgeschlossen hat.

**Prüfen:** `python nomad_cli.py render --json` — unter `status.verification.services` bzw. `selected_service` stehen `repo`, `branch`, `url`; unter `recent_deploys` der zuletzt **live**e Commit.

## Zweiter Render-Web-Service (Referenz)

Es gibt zusätzlich den Service **`nomad-api`** (`srv-d7jc241kh4rs73fjmffg`), ebenfalls Repo **`Asti1982/nomad-api`**, Branch **`main`**, URL `https://nomad-api-4s84.onrender.com`. Apex/Custom-Domain-Routing entscheidet, welcher Host öffentlich genutzt wird; die Build-Quelle für beide ist dieselbe Codebasis auf `main`.

## Edge / Cloudflare

`syndiode.com` kann vor dem Origin noch **Cloudflare Worker / Pfad-Whitelist** haben. 404 auf einzelnen Pfaden heißt nicht zwingend „falscher Git-Branch“, sondern oft **Edge filtert** oder der Deploy ist noch alt. Zuerst Render-`commit_id` prüfen, dann Edge-Regeln.

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
