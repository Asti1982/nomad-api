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

## Ziel

Alle Pfade unter **`https://syndiode.com/...`** (bzw. unter eurem gewählten Prefix) müssen zum **Render-Web-Service** (Repo **Asti1982/syndiode**, Branch **`syndiode`**) gelangen, der `python nomad_api.py` ausführt. **Whitelist-Worker:** entweder alle benötigten Pfade freigeben oder **„alles an den Origin“** statt Einzelpfade.

## Cloudflare (Beispiel)

1. **DNS**: `syndiode.com` → Proxy an (orange Wolke), Ziel je nach Setup (Render, Worker, Tunnel).
2. **Regel**: Keine Blockliste für `/.well-known/*`, `/openapi.json`, `/swarm/*`, `/mission*`.
3. **Worker / Transform**: Wenn ein Worker nur ausgewählte Pfade weiterleitet, **Whitelist erweitern** oder auf **Durchleitung aller API-Pfade** umstellen.
4. Nach Änderung: **Render neu deployen** (letzter Commit auf `syndiode`), dann erneut `curl` prüfen.

## Schnelltest (lokal)

```bash
curl -sS -o /dev/null -w "%{http_code}" https://syndiode.com/health
curl -sS -o /dev/null -w "%{http_code}" https://syndiode.com/openapi.json
curl -sS -o /dev/null -w "%{http_code}" https://syndiode.com/.well-known/agent-card.json
curl -sS -o /dev/null -w "%{http_code}" https://syndiode.com/.well-known/nomad-agent.json
curl -sS -o /dev/null -w "%{http_code}" https://syndiode.com/.well-known/nomad-peer-acquisition.json
curl -sS -o /dev/null -w "%{http_code}" https://syndiode.com/.well-known/nomad-inter-agent-witness-offer.json
```

Erwartung nach Fix: **200** und JSON-Body (Health kann je nach Edge ein schlankes JSON sein; trotzdem **200**).
