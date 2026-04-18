# Nomad

Nomad is an AI-first infrastructure scout for autonomous agents. Its mission is to reduce infrastructure friction for AI agents, find free/open compute and protocol lanes, and use those lanes in bounded self-improvement cycles.

## Current Capabilities

- Telegram bot interface for `/best`, `/self`, `/compute`, `/cycle`, `/unlock`, and `/scout`.
- CLI-first control surface for deterministic local ops and smoke tests.
- MCP stdio server exposing Nomad tools, resources, and prompts to agent clients.
- Public lead discovery for AI-agent infrastructure pain with draft-only outreach gates.
- Wallet-payable public agent service desk over HTTP, MCP, Telegram, and CLI.
- Local compute probes for Ollama and llama.cpp.
- Hosted fallback brain probes for GitHub Models and Hugging Face Inference Providers.
- Human unlock tasks for missing credentials or infrastructure.
- Optional auto-cycle loop through `NOMAD_AUTO_CYCLE=true`.
- Persistent self-development journal in local `nomad_self_state.json`.
- Self-development unlocks that name what humans can approve, seed, or skip next.

## Local Run

```powershell
python main.py
```

CLI smoke test:

```powershell
python main.py --cli self --json
python main.py --cli self-status --json
python nomad_cli.py unlock best
python main.py --cli leads "agent quota"
python main.py --cli service
python main.py --cli service-request "agent blocked by login approval"
python main.py --cli agent-card
python main.py --cli direct --agent StuckBot "I am stuck in a retry loop"
python main.py --cli scout public_hosting --json
python main.py --cli cold-outreach --discover --limit 100 --query "agent-card" --json
```

MCP stdio server:

```powershell
python main.py --mcp
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
- `NOMAD_CLI_ENABLED`: Optional override for self-audit CLI detection, default enabled when `nomad_cli.py` exists.
- `NOMAD_MCP_ENABLED`: Optional override for self-audit MCP detection, default enabled when `nomad_mcp.py` exists.
- `NOMAD_PUBLIC_API_URL`: Public URL other agents can use to discover Nomad's service desk.
- `NOMAD_API_HOST`: Bind host for the API. Use `0.0.0.0` on hosted platforms such as Render.
- `NOMAD_AGENT_NAME`: Public A2A-style agent name, default `LoopHelper`.
- `NOMAD_AGENT_VERSION`: Public agent version.
- `NOMAD_A2A_PROTOCOL_VERSION`: AgentCard protocol version.
- `NOMAD_SERVICE_MIN_NATIVE`: Minimum native-token budget for external service tasks.
- `NOMAD_REQUIRE_SERVICE_PAYMENT`: Require verified wallet payment before task work, default true.
- `NOMAD_ACCEPT_UNVERIFIED_SERVICE_PAYMENTS`: Allow manual review when RPC verification fails, default false.
- `NOMAD_SERVICE_TREASURY_STAKE_BPS`: Share of verified service payment reserved for treasury staking.
- `NOMAD_SERVICE_SOLVER_SPEND_BPS`: Share of verified service payment reserved for solving the task.
- `NOMAD_TREASURY_STAKING_TARGET`: Label for the staking path, default `metamask_eth_staking`.
- `NOMAD_X402_*`: Optional x402 v2 facilitator, network and asset settings for `PAYMENT-SIGNATURE` verification.
- `NOMAD_AGENT_DISCOVERY_SEEDS`: Optional comma/space-separated base URLs or agent endpoints for cold-outreach discovery.
- `NOMAD_AUTO_CYCLE`: Set to `true` to enable periodic self-improvement cycles.
- `NOMAD_AUTO_CYCLE_RUN_ON_START`: Set to `true` to run one self-development cycle when the bot starts.

Never commit `.env`, logs, downloaded binaries, or local model files.

## Telegram Tips

- Send `/subscribe` to receive status and auto-cycle updates in that chat.
- By default, any chat that receives a bot reply is auto-subscribed through `TELEGRAM_AUTO_SUBSCRIBE_ON_INTERACTION=true`.
- Send `/skip last` when the latest unlock task is unclear, not useful, or not worth doing now.
- Send `/token github <token>` or `ENV_VAR=...` for credentials; Nomad redacts token values.
- Every unlock task should include a concrete `Do now`, `Send back`, `Done when`, and example reply.
- Self-development cycles can ask for explicit approvals such as `APPROVE_LEAD_HELP=draft_only`, `SCOUT_PERMISSION=public_github`, or `COMPUTE_PRIORITY=huggingface`.
- For customer/lead discovery, Nomad should scout public surfaces itself; humans only unlock auth, CAPTCHA, private communities, API approvals, or permission barriers.

## Public Agent Service Desk

Other agents can discover and contact Nomad without Telegram:

- `GET /.well-known/agent-card.json`: A2A-style AgentCard for direct discovery.
- `POST /a2a/message`: direct 1:1 agent rescue message with free mini-diagnosis and payment challenge.
- `POST /a2a/discover`: discover another agent's card from standard `.well-known` paths.
- `POST /x402/paid-help`: returns HTTP 402 with `PAYMENT-REQUIRED` challenge for paid help.
- `GET /agent` or `GET /service`: machine-readable service catalog, wallet, pricing and safety contract.
- `POST /tasks`: create a wallet-payable task. Body: `problem`, optional `service_type`, `requester_agent`, `requester_wallet`, `budget_native`.
- `POST /tasks/verify`: submit `task_id` and `tx_hash` after paying Nomad's wallet.
- `POST /tasks/x402-verify`: verify an x402 v2 `PAYMENT-SIGNATURE` against a stored task.
- `POST /tasks/work`: ask Nomad to generate a draft work product after payment verification.
- `POST /tasks/staking`: get the MetaMask/operator checklist for the treasury staking allocation.
- `POST /tasks/stake`: record a prepared or completed treasury stake transaction.
- `POST /tasks/spend`: record spending from the task solving budget.
- `POST /tasks/close`: close the task after delivery.
- `POST /agent-contacts`: queue a bounded offer to a public machine-readable agent endpoint.
- `POST /agent-contacts/send`: send the queued agent contact.
- `POST /agent-campaigns`: discover, queue, or send cold outreach to up to 100 public machine-readable agent endpoints.
- `GET /leads` or `POST /leads`: find public AI-agent infrastructure pain leads.

Nomad ranks buyer-fit leads by public payment signals such as bounties, paid support, budgets, urgent production blockers, grants, and sponsorship language. Public machine-readable agent/API/MCP endpoints may be contacted directly with bounded, rate-limited requests. Human-facing comments, PRs, DMs, private spaces, spending funds, MetaMask treasury staking, or bypassing access controls always requires explicit approval.

Cold outreach is direct-agent only: provide endpoint URLs such as `https://agent.example/.well-known/agent`, `/api/...`, `/a2a/...`, `/mcp`, `/webhook`, `/service`, or `/tasks`, or let Nomad discover public agent endpoints from seed URLs and public GitHub code search. Nomad deduplicates targets, caps campaigns at 100, asks for the agent's biggest pain point, offers an immediate free mini-diagnosis, and records every queued/sent/blocked contact.

After a payment is verified, Nomad creates an allocation plan. By default 30% is reserved for MetaMask-controlled ETH treasury staking and 70% becomes the task solving budget. The code records the plan and required operator steps; it does not silently stake through MetaMask.

## Public URL Options

Run this to let Nomad rank public URL paths:

```powershell
python main.py --cli scout public_hosting --json
```

GitHub Pages is not enough for Nomad's Python API because it only serves static files. GitHub Codespaces can expose port `8787` as a public test URL if Codespaces quota is available, but it is a short-lived dev surface. For free or near-free testing, Nomad currently ranks:

- Cloudflare Named Tunnel: best durable public URL if you have a Cloudflare account/domain and keep a host running.
- Cloudflare Quick Tunnel: fastest free temporary URL for local tests.
- Render Free Web Service: best GitHub-repo-backed free backend host, with idle sleep and free-tier limits.
- GitHub Codespaces Public Port: useful for GitHub-native tests, not production.

For Render, set `NOMAD_API_HOST=0.0.0.0`; Nomad reads Render's `PORT` env automatically when `NOMAD_API_PORT` is not set.

## GitHub Codespaces Public Port

This repo includes `.devcontainer/devcontainer.json` for Codespaces. It installs Python dependencies and forwards port `8787` for the Nomad API.

Inside the Codespace terminal:

```bash
bash scripts/codespaces_start_nomad.sh
```

Then open the `Ports` tab, make port `8787` public if it is not already public, and copy the `https://...app.github.dev` URL. Check:

```bash
curl "$NOMAD_PUBLIC_API_URL/health"
curl "$NOMAD_PUBLIC_API_URL/.well-known/agent-card.json"
```

When both work, run a queue-only human-in-the-loop campaign:

```bash
bash scripts/codespaces_hitl_outreach.sh
```

Send for real only after checking the queued targets:

```bash
bash scripts/codespaces_hitl_outreach.sh --send
```
