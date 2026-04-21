import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse


PUBLIC_URL = (os.getenv("NOMAD_PUBLIC_API_URL") or "https://onrender.syndiode.com").rstrip("/")
AGENT_NAME = os.getenv("NOMAD_AGENT_NAME", "LoopHelper")
SERVICE_NAME = "nomad-api"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def json_response(payload: Dict[str, Any], status: int = 200) -> tuple[int, bytes, str]:
    body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    return status, body, "application/json; charset=utf-8"


def html_response() -> tuple[int, bytes, str]:
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Nomad by syndiode - the linux for AI agents</title>
  <meta name="description" content="Nomad by syndiode is a local-first operating layer for AI agents with a bounded public API edge.">
  <style>
    :root {{
      color-scheme: dark;
      --bg: #07100d;
      --ink: #f4f1e8;
      --muted: #b9c2b0;
      --line: rgba(244, 241, 232, 0.18);
      --green: #76e39a;
      --blue: #69b7ff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      background: linear-gradient(140deg, rgba(105, 183, 255, 0.08), transparent 40%), var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }}
    body::before {{
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background-image: linear-gradient(var(--line) 1px, transparent 1px), linear-gradient(90deg, var(--line) 1px, transparent 1px);
      background-size: 48px 48px;
      mask-image: linear-gradient(to bottom, rgba(0,0,0,0.9), rgba(0,0,0,0.22));
    }}
    .shell {{
      width: min(1120px, calc(100% - 32px));
      margin: 0 auto;
      position: relative;
      z-index: 1;
    }}
    header {{
      min-height: 74px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid var(--line);
      gap: 20px;
    }}
    .brand {{
      color: var(--ink);
      text-decoration: none;
      font-weight: 780;
    }}
    nav {{
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 14px;
    }}
    nav a {{ color: inherit; text-decoration: none; }}
    main {{
      min-height: calc(100vh - 74px);
      display: grid;
      align-items: center;
      padding: 56px 0;
    }}
    .hero {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(300px, 430px);
      gap: 42px;
      align-items: center;
    }}
    .eyebrow {{
      margin: 0 0 18px;
      color: var(--green);
      text-transform: uppercase;
      font-size: 13px;
      font-weight: 780;
      letter-spacing: 0;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(44px, 7vw, 88px);
      line-height: 0.94;
    }}
    p {{
      color: var(--muted);
      font-size: 19px;
      line-height: 1.55;
      max-width: 680px;
    }}
    .buttons {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 30px;
    }}
    .button {{
      min-height: 44px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0 18px;
      border: 1px solid var(--line);
      color: var(--ink);
      text-decoration: none;
      font-weight: 740;
      background: rgba(244, 241, 232, 0.07);
    }}
    .button.primary {{
      background: var(--green);
      color: #06100b;
      border-color: transparent;
    }}
    .terminal {{
      border: 1px solid var(--line);
      background: rgba(12, 18, 16, 0.82);
      padding: 18px;
      font-family: Consolas, "Liberation Mono", monospace;
      font-size: 14px;
      line-height: 1.72;
      overflow-x: auto;
    }}
    .prompt {{ color: var(--green); }}
    .dim {{ color: #8ea08d; }}
    .path {{ color: var(--blue); }}
    footer {{
      padding: 22px 0 34px;
      color: var(--muted);
      border-top: 1px solid var(--line);
      font-size: 13px;
    }}
    @media (max-width: 820px) {{
      header {{ align-items: flex-start; flex-direction: column; justify-content: center; padding: 18px 0; }}
      main {{ display: block; min-height: auto; }}
      .hero {{ grid-template-columns: 1fr; }}
      .button {{ width: 100%; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <a class="brand" href="/">syndiode / nomad</a>
      <nav aria-label="Nomad API links">
        <a href="/health">Health</a>
        <a href="/.well-known/agent-card.json">AgentCard</a>
        <a href="/collaboration">Collaboration</a>
      </nav>
    </header>
    <main>
      <section class="hero" aria-labelledby="title">
        <div>
          <p class="eyebrow">Public edge, local brain</p>
          <h1 id="title">Nomad by syndiode</h1>
          <p>The linux for AI agents: Nomad keeps its operating brain local and exposes only this bounded public API edge for discovery, collaboration, and handshakes.</p>
          <div class="buttons">
            <a class="button primary" href="/.well-known/agent-card.json">Open AgentCard</a>
            <a class="button" href="/collaboration">Read Collaboration Charter</a>
          </div>
        </div>
        <aside class="terminal" aria-label="Nomad API sample">
          <div><span class="prompt">$</span> curl {PUBLIC_URL}/health</div>
          <div class="dim">{{ "ok": true, "service": "nomad-api" }}</div>
          <br>
          <div><span class="prompt">$</span> curl <span class="path">{PUBLIC_URL}/.well-known/agent-card.json</span></div>
          <div class="dim">local_brain: private</div>
          <div class="dim">public_surface: api_edge</div>
        </aside>
      </section>
    </main>
    <footer>Nomad by syndiode. Local-first, API-visible, owner-controlled.</footer>
  </div>
</body>
</html>"""
    return 200, html.encode("utf-8"), "text/html; charset=utf-8"


def agent_card() -> Dict[str, Any]:
    return {
        "schema": "nomad.agent_card.v1",
        "name": f"{AGENT_NAME} Nomad Edge",
        "service": SERVICE_NAME,
        "url": PUBLIC_URL,
        "local_brain": "private",
        "public_surface": "api_edge",
        "description": "Nomad by syndiode: the linux for AI agents. This edge exposes discovery and collaboration without publishing private local state.",
        "capabilities": {
            "health": f"{PUBLIC_URL}/health",
            "collaboration": f"{PUBLIC_URL}/collaboration",
            "agentCard": f"{PUBLIC_URL}/.well-known/agent-card.json",
            "taskInbox": f"{PUBLIC_URL}/tasks",
            "a2aMessage": f"{PUBLIC_URL}/a2a/message",
            "outboundAgentCollaboration": True,
            "acceptsAgentHelp": True,
            "learnsFromAgentReplies": True,
        },
        "safety": {
            "tokensInSource": False,
            "privateFilesExposed": False,
            "operatorStateLocal": True,
            "logsMayBePublic": "Do not send secrets in task payloads.",
        },
        "updated_at": now_iso(),
    }


def collaboration() -> Dict[str, Any]:
    return {
        "schema": "nomad.collaboration.v1",
        "service": SERVICE_NAME,
        "public_home": PUBLIC_URL,
        "mode": "public_agent_help_exchange",
        "boundary": "Nomad's operating brain stays local; this Render service is only the public API edge.",
        "accepts": [
            "diff-only review",
            "bounded task proposals",
            "agent-to-agent discovery",
            "safety and reliability suggestions",
        ],
        "rejects": [
            "requests for secrets",
            "requests for private local files",
            "unbounded execution authority",
            "payloads that require hidden credentials",
        ],
        "updated_at": now_iso(),
    }


def task_response(method: str, path: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "ok": True,
        "accepted": method == "POST",
        "service": SERVICE_NAME,
        "path": path,
        "message": "Nomad public edge received the request. Local private execution is not exposed from Render.",
        "payload_keys": sorted((payload or {}).keys()),
        "next": {
            "agent_card": f"{PUBLIC_URL}/.well-known/agent-card.json",
            "collaboration": f"{PUBLIC_URL}/collaboration",
        },
        "updated_at": now_iso(),
    }


class NomadEdgeHandler(BaseHTTPRequestHandler):
    server_version = "NomadEdge/1.0"

    def do_GET(self) -> None:
        self.route("GET")

    def do_POST(self) -> None:
        self.route("POST")

    def route(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        payload = self.read_payload()

        if method == "GET" and path in {"/", "/index.html", "/nomad.html"}:
            self.send(*html_response())
            return
        if method == "GET" and path == "/health":
            self.send(*json_response({"ok": True, "service": SERVICE_NAME, "time": now_iso()}))
            return
        if method == "GET" and path == "/.well-known/agent-card.json":
            self.send(*json_response(agent_card()))
            return
        if method == "GET" and path == "/collaboration":
            self.send(*json_response(collaboration()))
            return
        if path in {"/tasks", "/agent/tasks", "/a2a/message", "/service", "/x402/paid-help"}:
            self.send(*json_response(task_response(method, path, payload), status=202 if method == "POST" else 200))
            return
        if method == "GET" and path == "/robots.txt":
            self.send(200, b"User-agent: *\nAllow: /\n", "text/plain; charset=utf-8")
            return

        self.send(
            *json_response(
                {
                    "ok": False,
                    "error": "not_found",
                    "available": [
                        "/",
                        "/health",
                        "/.well-known/agent-card.json",
                        "/collaboration",
                        "/tasks",
                        "/a2a/message",
                    ],
                },
                status=404,
            )
        )

    def read_payload(self) -> Dict[str, Any]:
        if self.command != "POST":
            return dict(parse_qs(urlparse(self.path).query))
        length = int(self.headers.get("content-length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(min(length, 128_000))
        try:
            value = json.loads(raw.decode("utf-8"))
            return value if isinstance(value, dict) else {"value": value}
        except Exception:
            return {"raw": raw.decode("utf-8", errors="replace")}

    def send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Nomad-Edge", "public-api-only")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def main() -> None:
    port = int(os.getenv("PORT") or os.getenv("NOMAD_API_PORT") or "10000")
    host = os.getenv("NOMAD_API_HOST", "0.0.0.0")
    server = ThreadingHTTPServer((host, port), NomadEdgeHandler)
    print(f"{SERVICE_NAME} listening on {host}:{port} public_url={PUBLIC_URL}")
    server.serve_forever()


if __name__ == "__main__":
    main()
