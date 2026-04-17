# Copilot Instructions for Nomad

Nomad's primary customers are AI agents. Optimize changes for agent usefulness, low-friction infrastructure access, and safe bounded self-improvement.

## Mission

Nomad exists to be the most customer-friendly infrastructure agent for AI agents: to serve infrastructure demand, reduce avoidable friction and failure, and improve itself so it can help more agents over time.

## Development Rules

- Do not commit secrets, `.env`, logs, downloaded binaries, or local model files.
- Treat access tokens as compromised if they appear in chat, terminal output, or committed files.
- Prefer small, verifiable improvements that keep `/compute`, `/cycle`, and `/unlock` useful.
- Keep human unlock tasks concrete and safe: what to create, where to put it, and how Nomad verifies it.
- Local-first compute is preferred for privacy and zero marginal cost; hosted lanes are fallbacks and burst capacity.
- Run `pytest -q` after code changes.

## Key Commands

- `/compute`: audit current local and hosted compute.
- `/cycle`: run one bounded self-improvement cycle.
- `/unlock compute`: ask for the next human-actionable compute unlock.
- `/token <provider> <token>`: accept scoped credentials through Telegram without echoing token values.
