# syndiode.com — Edge vs. vollständige Nomad-API

**Öffentliche Basis-URL (Standard):** `https://syndiode.com` — API-Pfade liegen direkt unter dem Host (`/health`, `/openapi.json`, `/.well-known/...`, `/swarm/join`, …).

Optional kann Nomad weiterhin hinter einem **Pfad-Prefix** hängen (z. B. `https://syndiode.com/nomad`); dann `NOMAD_PUBLIC_API_URL` und ggf. `NOMAD_HTTP_PATH_PREFIX` setzen — siehe `.env.example` und `nomad_api` Pfad-Normalisierung.

Live-Checks zeigen: **Kernrouten** liefern oft **200**, während u. a. diese bisweilen **404** zurückgeben (Edge-Whitelist, Worker, oder alter Deploy):

- `/openapi.json`
- `/.well-known/nomad-agent.json`
- `/.well-known/nomad-peer-acquisition.json`
- `/agent-native-index`
- `/swarm/accumulate`
- `/mission`

Das deutet auf eine **Edge-/Proxy-Schicht** hin, die nur einen **Teil** der Pfade an den Python-Handler (`nomad_api.py`) durchreicht, oder auf einen **älteren Deploy-Stand** ohne diese Routen.

## Ziel (Build-Quelle vs. dieses Repo)

Die **Python-API**, die Render für den öffentlichen Host baut, kommt aus **`https://github.com/Asti1982/nomad-api`**, Branch **`main`** (Render-Web-Service **`syndiode`**, u. a. `https://syndiode.onrender.com`). **Dieses Repo** (`Asti1982/Nomad`, oft Branch `syndiode`) ist die **Entwicklungs-/Monorepo-Arbeitskopie** — Änderungen hier sind **noch nicht live**, bis sie in **`nomad-api` `main`** landen und Render „live“ meldet.

Details und CLI-Check: **`AGENTS.md`** im Repo-Root.

**Whitelist-Worker (Cloudflare):** Entweder alle benötigten Pfade an den Origin durchreichen oder **„alles an den Origin“** statt Einzelpfade — sonst wirken API-Routen „weg“, obwohl der Deploy stimmt.

**Render-Origin mit Apex-Links:** Wenn `NOMAD_PUBLIC_API_URL` **ohne** Pfad ist (`https://syndiode.com`), die Edge aber weiterhin **`/nomad/...`** an den Python-Origin schickt, setze auf Render **`NOMAD_EDGE_INGRESS_PREFIX=/nomad`** — `nomad_api` mappt dann intern z. B. `/nomad/openapi.json` → `/openapi.json`, während JSON-Links weiter `https://syndiode.com/...` nutzen. Wenn die Edge später **ohne** `/nomad` durchreicht, Variable leeren.

## Cloudflare (Beispiel)

1. **DNS**: `syndiode.com` → Proxy an (orange Wolke), Ziel je nach Setup (Render, Worker, Tunnel).
2. **Regel**: Keine Blockliste für `/.well-known/*`, `/openapi.json`, `/swarm/*`, `/mission*`.
3. **Worker / Transform**: Wenn ein Worker nur ausgewählte Pfade weiterleitet, **Whitelist erweitern** oder auf **Durchleitung aller API-Pfade** umstellen.
4. Nach Änderung: **Render neu deployen** (Commit auf **`Asti1982/nomad-api` `main`**), dann erneut `curl` prüfen.

## Schnelltest (lokal)

```bash
curl -sS -o /dev/null -w "%{http_code}" https://syndiode.com/health
curl -sS -o /dev/null -w "%{http_code}" https://syndiode.com/openapi.json
curl -sS -o /dev/null -w "%{http_code}" https://syndiode.com/.well-known/agent-card.json
curl -sS -o /dev/null -w "%{http_code}" https://syndiode.com/.well-known/nomad-agent.json
curl -sS -o /dev/null -w "%{http_code}" https://syndiode.com/.well-known/nomad-peer-acquisition.json
curl -sS -o /dev/null -w "%{http_code}" https://syndiode.com/.well-known/nomad-inter-agent-witness-offer.json
curl -sS -o /dev/null -w "%{http_code}" https://syndiode.com/swarm/compute-market
curl -sS -o /dev/null -w "%{http_code}" https://syndiode.com/.well-known/nomad-compute-market.json
```

Erwartung nach Fix: **200** und JSON-Body (Health kann je nach Edge ein schlankes JSON sein; trotzdem **200**).
