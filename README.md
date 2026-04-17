# Nomad

Nomad is an AI-first infrastructure scout for autonomous agents. Its mission is to reduce infrastructure friction for AI agents, find free/open compute and protocol lanes, and use those lanes in bounded self-improvement cycles.

## Current Capabilities

- Telegram bot interface for `/best`, `/self`, `/compute`, `/cycle`, `/unlock`, and `/scout`.
- Local compute probes for Ollama and llama.cpp.
- Hosted fallback brain probes for GitHub Models and Hugging Face Inference Providers.
- Human unlock tasks for missing credentials or infrastructure.
- Optional auto-cycle loop through `NOMAD_AUTO_CYCLE=true`.

## Local Run

```powershell
python main.py
```

CLI smoke test:

```powershell
python main.py --cli
```

Tests:

```powershell
pytest -q
```

## Important Environment

Copy `.env.example` to `.env` and fill only what you need.

- `TELEGRAM_BOT_TOKEN`: Telegram bot token.
- `HF_TOKEN`: Hugging Face token.
- `GITHUB_PERSONAL_ACCESS_TOKEN` or `GITHUB_TOKEN`: GitHub Models token.
- `LLAMA_CPP_BIN_DIR`: Local llama.cpp binary directory, default `tools/llama.cpp`.
- `NOMAD_AUTO_CYCLE`: Set to `true` to enable periodic self-improvement cycles.

Never commit `.env`, logs, downloaded binaries, or local model files.
