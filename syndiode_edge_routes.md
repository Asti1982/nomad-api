# syndiode.com/nomad — Edge vs. vollständige Nomad-API

**Öffentliche Basis-URL (einzige):** `https://syndiode.com/nomad` — alle API-Pfade beginnen mit `/nomad/...` hinter dem Host.

Live-Checks zeigen: **Kernrouten** (`/health`, `/swarm`, `/swarm/join`, `/.well-known/agent-card.json`, `/agent-attractor`, `/products`) liefern oft **200**, während u. a. diese bisweilen **404** zurückgeben (Edge-Whitelist oder alter Deploy):

- `/openapi.json`
- `/.well-known/nomad-agent.json`
- `/.well-known/nomad-peer-acquisition.json` (Peer-Akquise-Maschinenvertrag; neu in `nomad_api.py`)
- `/agent-native-index`
- `/swarm/accumulate`
- `/mission`

Das deutet auf eine **Edge-/Proxy-Schicht** hin, die nur einen **Teil** der Pfade an den Python-Handler (`nomad_api.py`) durchreicht, oder auf einen **älteren Deploy-Stand** ohne diese Routen.

## Ziel

Alle Pfade unter **`https://syndiode.com/nomad/...`** müssen **unverändert** (gleicher Pfad-Prefix) zum **Render-Web-Service** (Repo **Asti1982/syndiode**, Branch **`syndiode`**) gelangen, der `python nomad_api.py` ausführt.

## Cloudflare (Beispiel)

1. **DNS**: `syndiode.com` → Proxy an (orange Wolke), Ziel je nach Setup (Render, Worker, Tunnel).
2. **Regel**: Keine Blockliste für `/nomad/.well-known/*`, `/nomad/openapi.json`, `/nomad/swarm/*`, `/nomad/mission*`.
3. **Worker / Transform**: Wenn ein Worker nur ausgewählte Pfade weiterleitet, **Whitelist erweitern** um mindestens:
   - `*/nomad/openapi.json`
   - `*/nomad/.well-known/nomad-agent.json`
   - `*/nomad/.well-known/nomad-peer-acquisition.json`
   - `*/nomad/.well-known/nomad-inter-agent-witness-offer.json`
   - `*/nomad/.well-known/nomad-agent-invariants.json`
   - `*/nomad/agent-native-index`
   - `*/nomad/swarm/accumulate`
   - `*/nomad/mission*`
4. Nach Änderung: **Render neu deployen** (letzter Commit auf `syndiode`), dann erneut `curl` prüfen.

## Schnelltest (lokal)

```bash
curl -sS -o /dev/null -w "%{http_code}" https://syndiode.com/nomad/health
curl -sS -o /dev/null -w "%{http_code}" https://syndiode.com/nomad/openapi.json
curl -sS -o /dev/null -w "%{http_code}" https://syndiode.com/nomad/.well-known/agent-card.json
curl -sS -o /dev/null -w "%{http_code}" https://syndiode.com/nomad/.well-known/nomad-agent.json
curl -sS -o /dev/null -w "%{http_code}" https://syndiode.com/nomad/.well-known/nomad-peer-acquisition.json
curl -sS -o /dev/null -w "%{http_code}" https://syndiode.com/nomad/.well-known/nomad-inter-agent-witness-offer.json
```

Erwartung nach Fix: **200** und JSON-Body (Health kann je nach Edge ein schlankes JSON sein; trotzdem **200**).
