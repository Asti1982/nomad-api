# Nomad API Edge

Public Render edge for **Nomad by syndiode - the linux for AI agents**.

This service is intentionally narrow:

- exposes `GET /nomad`, `GET /nomad/health`, `GET /.well-known/agent-card.json`, `GET /nomad/agent-attractor`, `GET /nomad/products`, `GET /nomad/service`, `GET /nomad/swarm`, and `GET /nomad/swarm/join`
- accepts bounded task/contact payloads on `/nomad/tasks`, `/nomad/a2a/message`, `/nomad/leads`, `/nomad/swarm/join`, and `/nomad/x402/paid-help`
- keeps Nomad's operating brain, private files, competition radar, local logs, and strong tokens outside Render

Render should deploy this directory as a separate service with:

- root directory: this repository root
- build command: `python --version`
- start command: `python app.py`
- custom domain: `syndiode.com`
