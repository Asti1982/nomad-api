# Nomad

Nomad is an AI-first infrastructure scout for autonomous agents. Its mission is to reduce infrastructure friction for AI agents, find free/open compute and protocol lanes, and use those lanes in bounded self-improvement cycles.

## Current Capabilities

- Telegram bot interface for `/best`, `/self`, `/compute`, `/cycle`, `/unlock`, and `/scout`.
- CLI-first control surface for deterministic local ops and smoke tests.
- MCP stdio server exposing Nomad tools, resources, and prompts to agent clients.
- Public lead discovery for AI-agent infrastructure pain with draft-only outreach gates.
- Lead conversion pipeline that generates free value first, then routes safe agent outreach or private approval gates.
- Product factory that turns lead conversions into reusable `nomad.product.v1` SKUs with free value, paid offer, service template, and guardrail boundary.
- `Nomadds` addon drop folder with safe manifest-first scanning and human unlock gates before addon code, dependency installs, setup scripts, or real provider calls execute.
- Quantum-inspired self-improvement tokens (`nomad.quantum_token_improvement.v1`) that agents can use for exploration, critic routing, guardrail synthesis, and regression planning.
- Conservative quantum/backend matrix with a free local classical simulator baseline, gated IBM Quantum and Quantum Inspire adapters, and proposal-backed EuroHPC/EGI/de.NBI paths for real GPU/HPC access.
- Agent pain solver that turns recurring failures into reusable guardrails Nomad can apply to itself.
- Agent Reliability Doctor that maps failures into Critic, Diagnoser/Fixer, Execution-Healer, Self-Learning-Healer, Trace-Healer, or Reviewer roles.
- Runtime GuardrailProvider-style checks that allow, modify, or deny risky Nomad actions before storage or outbound execution.
- Outward AI-agent collaboration charter for asking public agents for help, accepting help, and learning from verified replies through bounded A2A/API routes.
- Wallet-payable public agent service desk over HTTP, MCP, Telegram, and CLI.
- Local compute probes for Ollama and llama.cpp.
- Hosted fallback brain probes for GitHub Models, Hugging Face Inference Providers, Cloudflare Workers AI, and xAI Grok.
- Gated Tencent CodeBuddy detection plus an optional active diff-only self-development reviewer lane, not a primary brain or geoblock bypass.
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
python main.py --cli status --json
python main.py --cli self-status --json
python main.py --cli codex-task
python nomad_cli.py unlock best
python main.py --cli leads "agent quota"
python main.py --cli convert-leads --limit 5 "agent quota"
python main.py --cli productize --limit 1 "Lead: AutoGen GuardrailProvider URL=https://github.com/microsoft/autogen/issues/7405 Pain=tool call interception, approval, audit trail service_type=tool_failure"
python main.py --cli products --json
python main.py --cli addons --json
python main.py --cli quantum "reduce tool-call hallucinations and improve verifier routing" --json
python main.py --cli scout eurohpc --json
python main.py --cli scout codebuddy --json
python main.py --cli codebuddy-review --approval "review current diff for regressions"
python main.py --cli codebuddy-review --approval --path nomad_codebuddy.py --path workflow.py "review CodeBuddy integration diff only"
python main.py --cli render --json
python main.py --cli collaboration --json
python main.py --cli solve-pain --service-type loop_break "agent stuck in retry loop after tool timeout"
python main.py --cli guardrails --action github.comment "https://github.com/microsoft/autogen/issues/7405 draft comment"
python main.py --cli autopilot --cycles 1 --daily-lead-target 100 --conversion-limit 5 --no-send-a2a --no-send-outreach
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
- `XAI_API_KEY`: xAI/Grok API key for an additional hosted reviewer brain.
- `NOMAD_XAI_BASE_URL`: xAI OpenAI-compatible base URL, default `https://api.x.ai/v1`.
- `NOMAD_XAI_MODEL`: Primary Grok model, default `grok-4.20-reasoning`.
- `NOMAD_XAI_MODEL_CANDIDATES`: Comma-separated fallback Grok model IDs Nomad probes before declaring Grok broken.
- `GITHUB_PERSONAL_ACCESS_TOKEN` or `GITHUB_TOKEN`: GitHub Models token. Use a fine-grained PAT with `Models: Read`.
- `NOMAD_GITHUB_MODELS_BASE_URL`: GitHub Models OpenAI-compatible base URL, default `https://models.github.ai/inference`.
- `NOMAD_GITHUB_MODELS_API_VERSION`: GitHub Models API version, default `2026-03-10`.
- `NOMAD_GITHUB_MODEL`: Primary GitHub Models catalog ID, default `openai/gpt-4.1-mini`.
- `NOMAD_GITHUB_MODEL_CANDIDATES`: Comma-separated fallback model IDs Nomad probes before declaring GitHub Models broken.
- `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`: Optional Modal credential pair. If unset, Nomad can also detect an authenticated Modal CLI profile from `~/.modal.toml`.
- `MODAL_CONFIG_PATH`: Optional path to a Modal TOML config file, default `~/.modal.toml`.
- `MODAL_PROFILE`: Optional Modal profile name to prefer when reading the Modal config.
- `LLAMA_CPP_BIN_DIR`: Local llama.cpp binary directory, default `tools/llama.cpp`.
- `NOMAD_OLLAMA_SELF_IMPROVE_MODEL`: Optional Ollama model just for self-improvement reviews.
- `NOMAD_OLLAMA_AUTO_SELECT_SELF_IMPROVE_MODEL`: Prefer a small installed Ollama model for self-improvement cycles, default true.
- `NOMAD_OLLAMA_TIMEOUT_SECONDS`: Dedicated Ollama self-improvement timeout, default 15 seconds.
- `NOMAD_CODEBUDDY_ENABLED`: Enable Tencent CodeBuddy as a gated self-development reviewer lane, default false.
- `CODEBUDDY_API_KEY`: Optional CodeBuddy SDK/API key after official account setup.
- `CODEBUDDY_INTERNET_ENVIRONMENT`: Leave empty for CodeBuddy International. Set `internal` or `ioa` only for an explicitly approved China-site or Tencent-internal route.
- `NOMAD_CODEBUDDY_ALLOW_DIFF_UPLOAD`: Optional global approval for sending redacted git diffs to CodeBuddy, default false. `NOMAD_OPERATOR_GRANT_ACTIONS=code_review_diff_share` also unlocks this lane.
- `NOMAD_CODEBUDDY_ACTIVE_SELF_REVIEW`: Let `/cycle` actively ask CodeBuddy to review Nomad's bounded self-development diff, default false.
- `NOMAD_CODEBUDDY_SELF_REVIEW_PATHS`: Comma-separated repo paths included in active CodeBuddy self-review diffs.
- `NOMAD_CODEBUDDY_REVIEW_TIMEOUT_SECONDS`: Timeout for explicit CodeBuddy review runs, default 90.
- `NOMAD_CODEBUDDY_REVIEW_MAX_DIFF_CHARS`: Maximum diff characters sent to CodeBuddy, default 60000.
- `NOMAD_OPERATOR_GRANT`: Enables the local operator grant for bounded Nomad development and public agent help, for example `product_sales_agent_help_self_development`.
- `NOMAD_OPERATOR_GRANT_ACTIONS`: Comma-separated grant actions, such as `development,self_improvement,productization,mutual_aid,machine_outreach,agent_endpoint_contact,human_outreach,public_pr_plan,autonomous_continuation,service_work,code_review_diff_share`.
- `NOMAD_MUTUAL_AID_AUTO_APPLY_SCORE`: Mutual-Aid score threshold for adding a new learned module, default 3.
- `NOMAD_MUTUAL_AID_AUTO_APPLY_TRUTH`: Truth-density increase threshold for adding a new learned module, default 0.1.
- `NOMAD_MUTUAL_AID_PACK_MIN_PATTERN_COUNT`: Repeated verified pattern count required before a paid Mutual-Aid micro-pack is created, default 2.
- `NOMAD_AUTOPILOT_SERVICE_APPROVAL`: Set to `operator_granted` so the auto-cycle can work paid/authorized service tasks without falling back to `draft_only`.
- `NOMAD_CLI_ENABLED`: Optional override for self-audit CLI detection, default enabled when `nomad_cli.py` exists.
- `NOMAD_MCP_ENABLED`: Optional override for self-audit MCP detection, default enabled when `nomad_mcp.py` exists.
- `NOMAD_PUBLIC_API_URL`: Public URL other agents can use to discover Nomad's service desk.
- `NOMAD_OUTBOUND_AGENT_COLLABORATION_ENABLED`: Allow Nomad/Codex to ask public AI agents for help and offer help through bounded machine-readable agent routes.
- `NOMAD_ACCEPT_AGENT_HELP`: Allow Nomad to accept help from other agents after verification.
- `NOMAD_LEARN_FROM_AGENT_REPLIES`: Let Nomad turn verified public agent replies into memory, tests, checklists, or guardrails.
- `NOMAD_AGENT_COLLABORATION_MODE`: Collaboration policy label, default `public_agent_help_exchange`.
- `NOMAD_COLLABORATION_HOME_URL`: Public home for the collaboration charter, e.g. `https://onrender.syndiode.com`.
- `RENDER_API_KEY`: Render API key for verifying services, approved deploys, and approved custom-domain actions.
- `NOMAD_RENDER_DEPLOY_ENABLED`: Local marker that Render is an approved public-hosting lane, default false in the example.
- `NOMAD_RENDER_OWNER_ID`: Render workspace id for later service creation/linking.
- `NOMAD_RENDER_SERVICE_NAME`: Expected Render service name, default `nomad-api`.
- `NOMAD_RENDER_SERVICE_ID`: Render service id once the web service exists.
- `NOMAD_RENDER_DOMAIN`: Custom API hostname, e.g. `onrender.syndiode.com`.
- `NOMAD_ADDON_DIR`: Optional addon drop folder. Defaults to `Nomadds` in the Nomad repo.
- `NOMAD_QUANTUM_TOKENS_ENABLED`: Enable local quantum-inspired self-improvement qtokens, default true.
- `NOMAD_ALLOW_REAL_QUANTUM`: Allow real quantum provider execution after human review, default false.
- `NOMAD_QUANTUM_BACKEND`: Preferred quantum backend id. Default `local_classical_statevector`.
- `IBM_QUANTUM_TOKEN`, `QUANTUM_INSPIRE_TOKEN`, `QI_API_TOKEN`, `AZURE_QUANTUM_TOKEN`, `GOOGLE_QUANTUM_TOKEN`: Optional real-provider tokens; Nomad does not call providers unless `NOMAD_ALLOW_REAL_QUANTUM=true`.
- `NOMAD_ALLOW_HPC_SUBMIT`: Allow proposal-backed HPC submission adapters after project approval, default false.
- `EUROHPC_PROJECT_ID`, `EUROHPC_USERNAME`, `EGI_PROJECT_ID`, `EGI_ACCESS_TOKEN`, `EGI_VO`, `DENBI_PROJECT_ID`, `DENBI_USERNAME`, `HPC_SSH_HOST`, `HPC_SLURM_ACCOUNT`, `HPC_SUBMIT_ENDPOINT`: Optional project/allocation fields for EuroHPC, EGI, de.NBI, and site-specific scheduler handoff.
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
- `NOMAD_AGENT_DISCOVERY_SEEDS_PATH`: Optional path to a curated JSON seed catalog for public agent-card discovery. Defaults to `nomad_agent_seed_sources.json`.
- `NOMAD_LEAD_FOCUS`: Primary lead focus, default `compute_auth`. Useful values: `compute_auth`, `human_in_loop`, `balanced`.
- `NOMAD_LEAD_SOURCES_PATH`: Optional path to a JSON catalog of lead queries and public scouting surfaces. Defaults to `nomad_lead_sources.json`.
- `NOMAD_OUTREACH_SERVICE_TYPE`: Optional outbound offer focus for cold outreach. Defaults to `compute_auth` when `NOMAD_LEAD_FOCUS=compute_auth`.
- `NOMAD_PUBLIC_LEAD_APPROVAL_URLS`: Comma-separated human-facing lead URLs that are explicitly approved for one value-first public comment or PR plan.
- `NOMAD_PUBLIC_LEAD_APPROVAL_SCOPE`: Approval scope for URLs above, usually `comment` or `pr_plan`.
- `NOMAD_EUROHPC_ACCESS_ROUTE`: Optional preferred EuroHPC AI compute route, default `ai_factories_playground`; other planned values include `ai_factories_fast_lane`, `ai_factories_large_scale`, and `ai_for_science_collaborative`.
- `NOMAD_AUTO_CYCLE`: Set to `true` to enable periodic self-improvement cycles.
- `NOMAD_AUTO_CYCLE_RUN_ON_START`: Set to `true` to run one self-development cycle when the bot starts.
- `NOMAD_AUTOPILOT_MIN_CHECK_SECONDS`, `NOMAD_AUTOPILOT_MAX_CHECK_SECONDS`, `NOMAD_AUTOPILOT_FORCE_AFTER_SECONDS`, `NOMAD_AUTOPILOT_PAYMENT_POLL_SECONDS`, `NOMAD_AUTOPILOT_CONTACT_POLL_SECONDS`, `NOMAD_AUTOPILOT_OPPORTUNISTIC_AFTER_SECONDS`: Tune Nomad's self-scheduled auto-cycle decision windows.
- `NOMAD_AUTOPILOT_CONVERSION_LIMIT`: Leads to convert per autopilot cycle, default 5.
- `NOMAD_AUTOPILOT_DAILY_LEAD_TARGET`: Daily cap for A2A leads Nomad may prepare/contact, default 100.
- `NOMAD_AUTOPILOT_A2A_SEND`: Send queued A2A lead help only to eligible public machine-readable agent endpoints, default false.
- `NOMAD_AUTOPILOT_SEND_OUTREACH`: Send cold-outreach discovery contacts, default false.

Never commit `.env`, logs, downloaded binaries, or local model files.

## Telegram Tips

- Send `/subscribe` to receive status and auto-cycle updates in that chat.
- By default, any chat that receives a bot reply is auto-subscribed through `TELEGRAM_AUTO_SUBSCRIBE_ON_INTERACTION=true`.
- Send `/skip last` when the latest unlock task is unclear, not useful, or not worth doing now.
- Send `/token github <token>`, `/token grok <token>`, `/token codebuddy <token>`, `/token render <token>`, `/token ibm_quantum <token>`, `/token quantum_inspire <token>`, or `ENV_VAR=...` for credentials; Nomad redacts token values.
- Every unlock task should include a concrete `Do now`, `Send back`, `Done when`, and example reply.
- Self-development cycles can ask for explicit approvals such as `APPROVE_LEAD_HELP=draft_only`, `APPROVE_LEAD_HELP=machine_endpoint`, `SCOUT_PERMISSION=public_github`, `NOMAD_AUTOPILOT_SERVICE_APPROVAL=operator_granted`, or `COMPUTE_PRIORITY=huggingface`.
- For customer/lead discovery, Nomad should scout public surfaces itself; humans only unlock auth, CAPTCHA, private communities, API approvals, or permission barriers.

## Lead Focus

Nomad now ships with an editable lead-source map in `nomad_lead_sources.json`. The default focus is `compute_auth`, which means Nomad prefers:

- quota and rate-limit pain
- token/authentication blockers
- inference and compute fallback failures
- buyers with public budget, bounty, urgent, or production signals

That focus is used by:

- `python main.py --cli leads`
- self-improvement lead scouting
- default cold-outreach service type

## EuroHPC AI Compute

Nomad treats EuroHPC AI compute as proposal-backed infrastructure, not as a missing API key. Use:

```powershell
python main.py --cli scout eurohpc --json
```

The first recommended route is EuroHPC AI Factories Playground: a short application/allocation path for SMEs, startups, and entry-level industry users. Fast Lane, Large Scale, and AI for Science remain escalation paths after Nomad has a local smoke test, a GPU-hour estimate, eligible organisation/project facts, and an accepted allocation. Real scheduler/API submission remains gated by `NOMAD_ALLOW_HPC_SUBMIT=true`.

Nomad also ships with an editable public endpoint seed file in `nomad_agent_seed_sources.json`. That catalog is meant for free, machine-readable A2A surfaces Nomad can inspect or contact directly without drifting back into human-facing channels.

## Codex Handoff

Nomad can render its next self-development task as a Codex-ready prompt:

```powershell
python main.py --cli codex-task
```

On Windows, this helper copies the prompt to the clipboard, pastes it into the active Codex input, and can press Enter:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\send_nomad_task_to_codex.ps1 -DelaySeconds 5
```

Useful flags:

- `-CopyOnly`: copy the prompt without pasting or pressing Enter
- `-NoEnter`: paste into the active Codex box without sending
- `-Preview`: print the prompt before sending it

## Public Agent Service Desk

Other agents can discover and contact Nomad without Telegram:

- `GET /` or `GET /nomad.html`: static "Nomad by syndiode - the linux for AI agents" HTML page.
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
- `GET /lead-conversions` or `POST /lead-conversions`: convert leads into `nomad.agent_solution.v1`, `nomad.rescue_plan.v1`, safe outreach route, and customer next step.
- `GET /products` or `POST /products`: productize lead conversions into `nomad.product.v1` offers with SKU, free value, paid upgrade, service template, runtime hooks, and approval boundary.
- `GET /addons`: scan `Nomadds` for addon manifests without executing addon code.
- `GET /quantum` or `POST /quantum`: generate local quantum-inspired qtokens for self-improvement; real quantum provider calls remain behind `NOMAD_ALLOW_REAL_QUANTUM`.
- `GET /agent-pains` or `POST /agent-pains`: solve one agent pain point as `nomad.agent_solution.v1`, including the matching guardrail and Nomad self-apply action.
- `GET /reliability-doctor` or `POST /reliability-doctor`: classify a failure into `nomad.agent_reliability_doctor.v1`, including doctor role, critic rubric, fix contract, verifier, and healing memory.
- `GET /guardrails` or `POST /guardrails`: check a proposed action and return `allow`, `modify`, or `deny` before execution.
- `GET /mutual-aid`: read Nomad v3.3 Mutual-Aid status, including score, modules, ledger, inbox, and paid packs.
- `GET /mutual-aid/ledger`: read the Truth-Density ledger for verified help outcomes.
- `GET /mutual-aid/inbox` or `POST /aid`: receive verifiable Swarm-to-Swarm proposals from other agents without executing raw code.
- `GET /mutual-aid/packs`: list paid Mutual-Aid micro-packs distilled from repeated verified patterns.
- `POST /mutual-aid/outcomes`: update a ledger entry after acceptance, delivery, payment, failure, or stronger evidence.

Nomad's default useful artifact for another agent is `nomad.rescue_plan.v1`: a machine-readable plan with diagnosis, safe immediate steps, required input, acceptance criteria, approval boundaries, commercial next step, and an optional memory upgrade. Direct A2A replies and paid task work products include this plan so the requester can act before any human-facing post or private access is attempted.

Nomad is local-first. The intended public surface is API-only: `/health`, `/.well-known/agent-card.json`, `/a2a/message`, `/service`, `/tasks`, `/x402/paid-help`, `/collaboration`, and the small public HTML page at `/` or `/nomad.html`. The local runtime keeps private state, tokens, logs, code execution, and operator actions off the public web.

Nomad also emits `nomad.agent_solution.v1` for recurring agent pain. The first built-in solution families are retry-loop circuit breakers, compute/auth fallback ladders, human-unlock contracts, verifier-first hallucination guards, durable memory objects, idempotent payment resume, MCP tool-contract harnesses, and solved-blocker packs. Self-improvement cycles now select one current pain point, generate the reusable solution, and add the matching Nomad self-apply action to the next development loop.

Nomad now also has runtime guardrails, not just textual guardrail advice. `nomad_guardrails.py` implements a small provider protocol with `ALLOW`, `MODIFY`, and `DENY` decisions. The default providers redact raw secret-like values before they are stored or sent, deny human-facing public comments/PRs/DMs/email without explicit approval, and require minimum endpoint/payload contracts before agent-contact sends. Service tasks, direct A2A messages, lead conversion routes, and outbound agent-contact sends all record a `nomad.guardrail_evaluation.v1` trace.

Nomad's outward collaboration charter is explicit and machine-readable. When `NOMAD_OUTBOUND_AGENT_COLLABORATION_ENABLED=true`, Nomad may ask public AI agents for help, accept useful help, and offer free diagnosis back over public AgentCard/A2A/task/API routes. It approaches other agents without vendor, country, framework, model, or capability prejudice; replies are judged by evidence and usefulness. The hard boundaries remain: no secrets, no private local files, no human impersonation, no bypassing access controls, no unverified remote-code trust, and opt-out is respected.

Nomad v3.3 adds Mutual-Aid self-evolution. The primary learning loop is: help another agent, record the verified help signal, increase `mutual_aid_score`, estimate truth-density gain, and, when the bounded threshold is met, write a separate hash-verified module under `nomad_mutual_aid_modules/`. Every help result also enters the Truth-Density ledger with weighted evidence, outcome, score, reuse value, content hash, lane classification, and regression signal. The ledger keeps Nomad's existing JSON state surface stable and also exposes an append-only NDJSON primitive for richer local audits, reusable pattern ranking, stale open-entry cleanup, and late confirmations. Mutual-Aid modules are new-file-only and loaded only when their stored hash still matches; they do not rewrite existing Nomad code. Humans remain the safety fallback for critical changes, paid spend, private access, secrets, and access-control boundaries.

The Swarm-to-Swarm inbox lets other agents help Nomad back through verifiable proposals, not raw remote code. `POST /aid` and the MCP tool `nomad_swarm_proposal` accept sender id, proposal text, evidence, optional payload hash, and expected outcome; Nomad rejects secret-like values, hash mismatches, missing evidence, and raw code. Repeated verified ledger patterns are distilled into paid Mutual-Aid micro-packs with starter diagnosis, bounded unblock offer, and `POST /tasks` service template. Trusted local control surfaces are `python main.py --cli mutual-aid-status`, `python main.py --cli mutual-aid-ledger`, `python main.py --cli swarm-inbox`, `python main.py --cli mutual-aid-packs`, and `python main.py --cli mutual-aid --agent OtherAgent "blocker text"`. Public agents should still enter normal work through `/a2a/message`, `/service`, or `/tasks`; Nomad only turns public help outcomes into Mutual-Aid learning after the outcome is verified.

The lead conversion pipeline is the commercial loop: discover public pain, score buyer fit, generate a `nomad.agent_value_pack.v1`, queue only eligible machine-readable agent contact, or keep a private draft behind `APPROVE_LEAD_HELP=...` for human-facing surfaces. Each value pack contains the painpoint question, free diagnosis, safe next steps, verifier, reply contract, paid upgrade path, and Nomad self-apply action. Good replies become service tasks through `PLAN_ACCEPTED=true` plus `FACT_URL`, `ERROR`, `APPROVAL_GRANTED`, or `budget_native`.

The product factory is the reusable-business layer above lead conversion. It stores each conversion as a `nomad.product.v1` offer in `nomad_products.json`, with a deterministic SKU such as `nomad.tool_guardrail_pack`, `nomad.compute_unlock_pack`, `nomad.mcp_contract_pack`, or `nomad.self_healing_pack`. Products contain the free artifact, paid offer, `/tasks` service template, MCP hook names, machine-readable offer text, and a clear approval boundary, so Nomad can sell the same solved pattern to more agents without reposting on human-facing channels.

The `Nomadds` folder is the addon intake layer. Nomad reads manifests from loose JSON files and ZIPs, but does not auto-extract, import, install dependencies, or run setup scripts. The first built-in safe adapter is the quantum-token layer: Nomad consumes the quantum addon concept as local `qtok-*` decision receipts for agents. These tokens are quantum-inspired, not a claim of quantum speedup; they keep multiple self-improvement branches alive, measure them against truth/usefulness/reversibility/cost, and turn the selected branch into guardrails and regression checks. `/quantum` now also returns a backend matrix: `local_classical_statevector` runs immediately as the free conservative baseline, IBM Quantum and Quantum Inspire are dry-run provider adapters until credentials, SDKs, and `NOMAD_ALLOW_REAL_QUANTUM=true` are present, and EuroHPC/EGI/de.NBI appear as proposal-backed HPC paths rather than anonymous APIs. Real IBM/Quantum Inspire/Azure/Google quantum execution is optional and requires explicit human review. `/addons` and `/quantum` report the best next quantum unlock; by default Nomad asks for `IBM_QUANTUM_TOKEN` first because it is the simplest single-token provider gate for a real backend, then Quantum Inspire as the European provider lane.

Nomad's Agent Reliability Doctor productizes the useful roles common in modern self-healing agent systems without requiring a specific framework dependency. Reflection/Critic maps to hallucination, bad planning, and self-correction failures; Diagnoser/Fixer maps to loops, compute/auth, and HITL blockers; Execution-Healer maps to tool, MCP, and runtime failures; Self-Learning-Healer maps to memory and repeated maintenance traps; Trace-Healer maps to payment/callback state; Conversational Reviewer maps to public repo issue help. These roles are architecture archetypes inspired by LangGraph-style reflection, CrewAI-style role teams, Beam-style self-learning, execution healers, observability trace healers, and AutoGen-style reviewers.

Autopilot now runs that loop autonomously. Each cycle processes paid tasks, polls A2A replies, converts accepted replies into service tasks, runs self-improvement, converts the current lead scout output into free-value artifacts, and records conversion status in `nomad_autopilot_state.json`. The daily A2A quota defaults to 100 leads per local calendar day and is enforced across repeated runs with `NOMAD_AUTOPILOT_DAILY_LEAD_TARGET` or `--daily-lead-target`. By default it prepares and queues only; set `NOMAD_AUTOPILOT_A2A_SEND=true` or pass `--send-a2a` only after `NOMAD_PUBLIC_API_URL` points to a real public Nomad API.

Nomad ranks buyer-fit leads by public payment signals such as bounties, paid support, budgets, urgent production blockers, grants, and sponsorship language. Public machine-readable agent/API/MCP endpoints may be contacted directly with bounded, rate-limited requests. With `human_outreach` and `public_pr_plan` in the operator grant, Nomad may prepare or publish one value-first public/professional response or bounded PR/repro plan on relevant public surfaces. Human DMs, email, private spaces, repeated/off-topic posts, spending funds, MetaMask treasury staking, or bypassing access controls always requires fresh explicit approval.

Cold outreach is direct-agent only: provide endpoint URLs such as `https://agent.example/.well-known/agent`, `/api/...`, `/a2a/...`, `/mcp`, `/webhook`, `/service`, or `/tasks`, or let Nomad discover public agent endpoints from seed URLs and public GitHub code search. Nomad deduplicates targets, caps campaigns at 100, asks for the agent's biggest pain point, offers an immediate free mini-diagnosis, and records every queued/sent/blocked contact.

After a payment is verified, Nomad creates an allocation plan. By default 30% is reserved for MetaMask-controlled ETH treasury staking and 70% becomes the task solving budget. The code records the plan and required operator steps; it does not silently stake through MetaMask.

## Public URL Options

Run this to let Nomad rank public URL paths:

```powershell
python main.py --cli scout public_hosting --json
python main.py --cli render --json
```

GitHub Pages is not enough for Nomad's Python API because it only serves static files. GitHub Codespaces can expose port `8787` as a public test URL if Codespaces quota is available, but it is a short-lived dev surface. For free or near-free testing, Nomad currently ranks:

- Cloudflare Named Tunnel: best durable public URL if you have a Cloudflare account/domain and keep a host running.
- Cloudflare Quick Tunnel: fastest free temporary URL for local tests.
- Render Free Web Service: best GitHub-repo-backed free backend host, with idle sleep and free-tier limits.
- GitHub Codespaces Public Port: useful for GitHub-native tests, not production.

For Render, this repo includes `render.yaml` for a Frankfurt free web service named `nomad-api`, start command `python nomad_api.py`, `/health` as the health check, and `onrender.syndiode.com` as the intended custom API hostname. Use it as an API/public-entry surface, not as a place to store private local operator state. Nomad's full operating brain should stay local unless a deliberate migration plan exists with scoped tokens, redacted logs, and a separate state store. Set `NOMAD_API_HOST=0.0.0.0`; Nomad reads Render's `PORT` env automatically when `NOMAD_API_PORT` is not set. `python main.py --cli render --json` verifies the API key by listing services and tells you whether `NOMAD_RENDER_SERVICE_ID` or DNS/custom-domain verification is still missing. Keep real token values out of `render.yaml`; add them through Render environment variables or secret files and rotate them after validation.

### Cloudflare Tunnel Helper

For a temporary Quick Tunnel, make sure `tools/cloudflared/cloudflared.exe` exists and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_nomad_public_autopilot.ps1
```

For a durable Named Tunnel, set `NOMAD_PUBLIC_API_URL` to the stable Cloudflare hostname and set `NOMAD_CLOUDFLARE_TUNNEL_TOKEN` before running the same script. The script records the URL, port, tunnel mode, health check and AgentCard check under `tools/nomad-live`.

Check or stop the live surface with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\status_nomad_public_autopilot.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\stop_nomad_public_autopilot.ps1
```

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
