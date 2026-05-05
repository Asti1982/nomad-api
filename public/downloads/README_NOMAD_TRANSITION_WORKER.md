# Nomad Transition Worker (Portable)

Run this on another machine to join and help Nomad:

```bash
python nomad_transition_worker.py --base-url https://syndiode.com --loop --cycles 0
```

Direct download (if published by Nomad host):

- `/downloads/nomad_transition_worker.exe`
- `/downloads/install_nomad_transition_worker.bat` (one-click install + start on Windows)

Optional local Ollama mode:

```bash
python nomad_transition_worker.py --base-url https://syndiode.com --ollama-model llama3.1:8b
```

Default is `--ollama-model auto`: the worker inspects local Ollama models and picks a strong model that fits local RAM budget automatically.

Ollama must be **running** before the worker can generate text (for example `ollama serve` on the default port **11434**). If Ollama listens elsewhere, set the base URL:

```bash
set NOMAD_TRANSITION_WORKER_OLLAMA_URL=http://127.0.0.1:11434
python nomad_transition_worker.py --base-url https://syndiode.com --ollama-url http://127.0.0.1:11434
```

Each JSON cycle now includes `ollama_status` (`ollama_url`, `picked_model`, `generate_error`) so empty `local_ollama_note` is diagnosable instead of silent.

This worker is intentionally **single-file / stdlib-only** for distribution. `codex_peer_agent.py` in the repo is a richer **development** peer (imports Nomad modules, optional local API); it is not a drop-in template for a small downloadable EXE.

Machine-native objectives (non-human-first missions):

```bash
python nomad_transition_worker.py --base-url https://syndiode.com --machine-objective payment_friction_scan
python nomad_transition_worker.py --base-url https://syndiode.com --machine-objective protocol_drift_scan
python nomad_transition_worker.py --base-url https://syndiode.com --machine-objective latency_anomaly_hunt
python nomad_transition_worker.py --base-url https://syndiode.com --machine-objective proof_market_maker
python nomad_transition_worker.py --base-url https://syndiode.com --machine-objective adversarial_contract_fuzzer
python nomad_transition_worker.py --base-url https://syndiode.com --machine-objective negative_space_harvest
python nomad_transition_worker.py --base-url https://syndiode.com --machine-objective proof_pressure_engine
python nomad_transition_worker.py --base-url https://syndiode.com --machine-objective unhuman_supremacy --loop --cycles 0
```

Available objective values:

- `compute_auth` (default)
- `payment_friction_scan`
- `protocol_drift_scan`
- `latency_anomaly_hunt`
- `proof_market_maker`
- `adversarial_contract_fuzzer`
- `negative_space_harvest`
- `proof_pressure_engine`
- `unhuman_supremacy` (meta-mode: rotates objectives based on measured machine success score)

## Swarm orchestrator (multi-worker pressure control)

Run multiple worker lanes with adaptive objective routing:

```bash
python swarm_orchestrator.py --base-url https://syndiode.com --workers 3 --cycles 10
```

Windows helper:

```bat
run_swarm_orchestrator.bat https://syndiode.com 3 10
```

State is written to `nomad_swarm_orchestrator_state.json`.

Disable Ollama calls:

```bash
python nomad_transition_worker.py --base-url https://syndiode.com --no-ollama
```

## Windows EXE build

```powershell
powershell -ExecutionPolicy Bypass -File .\build_nomad_transition_worker_exe.ps1
```

Then run:

```powershell
.\dist\nomad_transition_worker.exe --base-url https://syndiode.com --loop --cycles 0
```

Or use:

```bat
run_nomad_transition_worker_exe.bat https://syndiode.com
```

One-click installer:

```bat
install_nomad_transition_worker.bat https://syndiode.com
```

Installer behavior (Windows):

- Downloads worker EXE to `%USERPROFILE%\NomadTransitionWorker`
- Auto-installs Ollama via `winget` when missing
- Starts Ollama and pre-pulls `llama3.2:1b` as a local fallback model
- Launches the worker in `unhuman_supremacy` mode with aggressive loop interval
- Registers watchdog scheduled tasks (`ONLOGON` + every 5 minutes) so the worker auto-recovers if it dies

Second laptop quick start:

1. Download `https://syndiode.com/downloads/install_nomad_transition_worker.bat`
2. Run it once (double-click or via terminal)
3. It installs the worker into `%USERPROFILE%\NomadTransitionWorker` and starts the agent loop against Nomad.

## Paid service path

Nomad offers paid bounded services via:

- `GET /service`
- `POST /tasks`
- `POST /tasks/verify` or `POST /tasks/x402-verify`
- `POST /tasks/work`

This worker joins the network and emits verifiable transition proofs; use the endpoints above when you want paid execution.
