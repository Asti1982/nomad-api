# Nomad Helper Agent (Portable)

Run this on another machine to join and help Nomad:

```bash
python nomad_helper_agent.py --base-url https://www.syndiode.com --loop --cycles 0
```

Optional local Ollama mode:

```bash
python nomad_helper_agent.py --base-url https://www.syndiode.com --ollama-model llama3.1:8b
```

Disable Ollama calls:

```bash
python nomad_helper_agent.py --base-url https://www.syndiode.com --no-ollama
```
