# Nomad Transition Worker (Portable)

Run this on another machine to join and help Nomad:

```bash
python nomad_transition_worker.py --base-url https://syndiode.com --loop --cycles 0
```

Optional local Ollama mode:

```bash
python nomad_transition_worker.py --base-url https://syndiode.com --ollama-model llama3.1:8b
```

Disable Ollama calls:

```bash
python nomad_transition_worker.py --base-url https://syndiode.com --no-ollama
```
