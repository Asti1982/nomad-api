# Nomad API Edge

Public Render edge for **Nomad by syndiode - the linux for AI agents**.

This service is intentionally narrow:

- exposes `GET /`, `GET /health`, `GET /.well-known/agent-card.json`, and `GET /collaboration`
- accepts bounded task/contact payloads on `/tasks`, `/agent/tasks`, `/a2a/message`, `/service`, and `/x402/paid-help`
- keeps Nomad's operating brain, private files, local logs, and strong tokens outside Render

Render should deploy this directory as a separate service with:

- root directory: `nomad-api`
- build command: `python --version`
- start command: `python app.py`
- custom domain: `onrender.syndiode.com`
