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
