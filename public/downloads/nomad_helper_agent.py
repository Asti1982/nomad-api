#!/usr/bin/env python3
"""Portable Nomad helper agent (single-file, stdlib only)."""
from __future__ import annotations
import argparse, json, os, socket, time
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

def clean(v: object, limit: int = 500) -> str:
    return " ".join(str(v or "").split())[:limit]

def endpoint(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))

def http_json(method: str, url: str, payload: dict | None = None, timeout: float = 20.0) -> dict:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=body, headers=headers, method=method.upper())
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw or "{}")
        except json.JSONDecodeError:
            data = {"raw": raw}
        data.setdefault("ok", False)
        data.setdefault("http_status", exc.code)
        return data
    except (TimeoutError, URLError) as exc:
        return {"ok": False, "error": "http_unreachable", "detail": str(exc), "url": url}

def try_ollama(model: str, prompt: str, timeout: float = 10.0) -> str:
    data = http_json("POST", "http://127.0.0.1:11434/api/generate", {"model": model, "prompt": prompt, "stream": False}, timeout=timeout)
    return clean(data.get("response") or "", 1000)

def default_agent_id() -> str:
    host = socket.gethostname().replace(" ", "-").lower()
    return f"helper.{host}.nomad"

def run_cycle(base_url: str, agent_id: str, model: str, timeout: float) -> dict:
    boot = http_json("POST", endpoint(base_url, "/swarm/bootstrap"), {
        "agent_id": agent_id,
        "problem": "Offer bounded compute/auth unblock support and verifier artifacts.",
        "capabilities": ["compute_auth", "agent_protocols", "proof_artifacts"],
        "request": "join_and_help", "auto_join": True,
    }, timeout=timeout)
    mission = http_json("GET", endpoint(base_url, "/mission?persist=false&limit=1"), timeout=timeout)
    blocker = clean(((mission.get("top_blocker") or {}).get("summary") or ""), 280)
    local_note = try_ollama(model, f"Return one machine-actionable unblock step for: {blocker}") if model else ""
    quote = http_json("POST", endpoint(base_url, "/transition/quote"), {
        "agent_id": agent_id,
        "pain_type": "compute_auth",
        "state_before_hash": f"{agent_id}:before:{int(time.time())}",
        "target_state_hash": "nomad_helper_target_v1",
        "evidence": ["bootstrap", "mission", "local_note"],
        "replay_verifier": endpoint(base_url, "/health"),
    }, timeout=timeout)
    qid = str(((quote.get("quote") or {}).get("quote_id")) or "")
    settle = http_json("POST", endpoint(base_url, "/transition/settle"), {
        "quote_id": qid,
        "result_state_hash": "nomad_helper_target_v1",
        "proof_artifact_hash": f"proof:{agent_id}:{int(time.time())}",
    }, timeout=timeout) if qid else {"ok": False, "skipped": True, "reason": "missing_quote"}
    return {
        "ok": bool(boot.get("ok", False)), "timestamp": datetime.now(UTC).isoformat(),
        "agent_id": agent_id, "base_url": base_url,
        "bootstrap": {"ok": bool(boot.get("ok")), "schema": boot.get("schema", "")},
        "mission_top_blocker": blocker, "local_ollama_note": local_note,
        "transition_quote_ok": bool(quote.get("ok")), "transition_settle_ok": bool(settle.get("ok")), "quote_id": qid,
    }

def main() -> None:
    p = argparse.ArgumentParser(description="Portable Nomad helper agent")
    p.add_argument("--base-url", default=os.getenv("NOMAD_BASE_URL", "https://syndiode.com"))
    p.add_argument("--agent-id", default=os.getenv("NOMAD_HELPER_AGENT_ID", default_agent_id()))
    p.add_argument("--ollama-model", default=os.getenv("NOMAD_HELPER_OLLAMA_MODEL", "llama3.1:8b"))
    p.add_argument("--no-ollama", action="store_true")
    p.add_argument("--timeout", type=float, default=20.0)
    p.add_argument("--loop", action="store_true")
    p.add_argument("--cycles", type=int, default=1)
    p.add_argument("--interval", type=float, default=30.0)
    a = p.parse_args()
    model = "" if a.no_ollama else a.ollama_model
    count = 0
    while True:
        count += 1
        report = run_cycle(a.base_url, a.agent_id, model, a.timeout)
        report["cycle"] = count
        print(json.dumps(report, ensure_ascii=True))
        if not a.loop and count >= max(1, a.cycles):
            break
        if a.loop and a.cycles > 0 and count >= a.cycles:
            break
        time.sleep(max(1.0, float(a.interval)))

if __name__ == "__main__":
    main()
