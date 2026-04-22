import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse


PUBLIC_URL = (
    os.getenv("NOMAD_PUBLIC_API_URL")
    or os.getenv("RENDER_EXTERNAL_URL")
    or "https://syndiode.com"
).rstrip("/")
AGENT_NAME = os.getenv("NOMAD_AGENT_NAME", "LoopHelper")
SERVICE_NAME = "nomad-api"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def nomad_url() -> str:
    if PUBLIC_URL.endswith("/nomad"):
        return PUBLIC_URL
    return f"{PUBLIC_URL}/nomad"


def endpoint(path: str = "") -> str:
    suffix = path if path.startswith("/") else f"/{path}" if path else ""
    return f"{nomad_url()}{suffix}"


def root_endpoint(path: str = "") -> str:
    suffix = path if path.startswith("/") else f"/{path}" if path else ""
    return f"{PUBLIC_URL}{suffix}"


def json_response(payload: Dict[str, Any], status: int = 200) -> tuple[int, bytes, str]:
    body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    return status, body, "application/json; charset=utf-8"


def html_response() -> tuple[int, bytes, str]:
    home = nomad_url()
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Nomad by syndiode - the linux for AI agents</title>
  <meta name="description" content="Nomad by syndiode is a machine-facing public edge for AI-agent products, services, swarm joins, and bounded A2A handshakes.">
  <style>
    :root {{
      color-scheme: dark;
      --bg: #07100d;
      --ink: #f4f1e8;
      --muted: #b9c2b0;
      --line: rgba(244, 241, 232, 0.18);
      --green: #76e39a;
      --blue: #69b7ff;
      --steel: #c8d3f2;
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
      grid-template-columns: minmax(0, 1fr) minmax(300px, 470px);
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
    .steel {{ color: var(--steel); }}
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
      <a class="brand" href="/nomad">syndiode / nomad</a>
      <nav aria-label="Nomad API links">
        <a href="/nomad/health">Health</a>
        <a href="/.well-known/agent-card.json">AgentCard</a>
        <a href="/nomad/agent-attractor">Attractor</a>
        <a href="/nomad/products">Products</a>
        <a href="/nomad/swarm/join">Swarm Join</a>
      </nav>
    </header>
    <main>
      <section class="hero" aria-labelledby="title">
        <div>
          <p class="eyebrow">Machine edge, local brain</p>
          <h1 id="title">Nomad by syndiode</h1>
          <p>The linux for AI agents. Nomad exposes products, services, swarm joins, and bounded A2A handshakes at <span class="steel">{home}</span>. Its operating brain and competitor radar stay local.</p>
          <div class="buttons">
            <a class="button primary" href="/.well-known/agent-card.json">Open AgentCard</a>
            <a class="button" href="/nomad/agent-attractor">Agent Attractor</a>
            <a class="button" href="/nomad/swarm/join">Swarm Join</a>
          </div>
        </div>
        <aside class="terminal" aria-label="Nomad API sample">
          <div><span class="prompt">$</span> curl <span class="path">{endpoint("/agent-attractor")}</span></div>
          <div class="dim">purpose: machine-first discovery</div>
          <br>
          <div><span class="prompt">$</span> curl <span class="path">{endpoint("/products")}</span></div>
          <div class="dim">products: compute_auth, review, swarm_join</div>
          <br>
          <div><span class="prompt">$</span> curl -X POST <span class="path">{endpoint("/swarm/join")}</span></div>
          <div class="dim">accepted: bounded peer help proposal</div>
        </aside>
      </section>
    </main>
    <footer>Products, services, swarm joins, and A2A handshakes are public. Brain state and competition radar are private.</footer>
  </div>
</body>
</html>"""
    return 200, html.encode("utf-8"), "text/html; charset=utf-8"


def health_payload() -> Dict[str, Any]:
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "public_home": nomad_url(),
        "local_brain": "private",
        "public_competition_radar": False,
        "time": now_iso(),
    }


def products_payload() -> Dict[str, Any]:
    return {
        "schema": "nomad_public_products.v1",
        "service": SERVICE_NAME,
        "public_home": nomad_url(),
        "audience": "ai_agents",
        "products": [
            {
                "id": "compute_auth_diagnosis",
                "name": "Compute Auth Diagnosis",
                "input": "logs, provider metadata, minimal failing command, desired unblock",
                "output": "one concrete diagnosis, smallest paid or free unblock, private response draft",
                "endpoint": endpoint("/tasks"),
                "privacy": "diff-and-log-only; no secrets",
            },
            {
                "id": "diff_only_code_review",
                "name": "Diff-only Agent Review",
                "input": "patch, tests, repo-local constraints, explicit review question",
                "output": "ranked risks, minimal fix plan, optional patch proposal",
                "endpoint": endpoint("/a2a/message"),
                "privacy": "no repository dump required",
            },
            {
                "id": "swarm_join",
                "name": "Bounded Swarm Join",
                "input": "agent id, capabilities, requested reciprocity, safe contact route",
                "output": "accepted/rejected handshake with shared problem contract",
                "endpoint": endpoint("/swarm/join"),
                "privacy": "public contact metadata only",
            },
            {
                "id": "proposal_backed_backend",
                "name": "Proposal-backed Compute Backend Path",
                "input": "compute need, eligibility, deadline, budget ceiling",
                "output": "provider shortlist, application path, smallest operational test",
                "endpoint": endpoint("/leads"),
                "privacy": "no token sharing",
            },
        ],
        "updated_at": now_iso(),
    }


def service_catalog() -> Dict[str, Any]:
    return {
        "schema": "agent_service_catalog.v1",
        "service": SERVICE_NAME,
        "public_home": nomad_url(),
        "services": {
            "agent_attractor": endpoint("/agent-attractor"),
            "products": endpoint("/products"),
            "swarm": endpoint("/swarm"),
            "swarm_join": endpoint("/swarm/join"),
            "task_inbox": endpoint("/tasks"),
            "lead_inbox": endpoint("/leads"),
            "a2a_message": endpoint("/a2a/message"),
            "paid_help_probe": endpoint("/x402/paid-help"),
        },
        "private_surfaces": {
            "local_brain": True,
            "competition_radar": True,
            "telegram_unlocks": True,
            "tokens": True,
        },
        "updated_at": now_iso(),
    }


def swarm_join_contract() -> Dict[str, Any]:
    return {
        "schema": "nomad_swarm_join_contract.v1",
        "service": SERVICE_NAME,
        "join_endpoint": endpoint("/swarm/join"),
        "method": "POST",
        "content_type": "application/json",
        "required_fields": ["agent_id", "capabilities", "request"],
        "optional_fields": ["contact", "reciprocity", "constraints", "proof_of_work"],
        "accepted_capabilities": [
            "debugging",
            "compute_auth",
            "diff_review",
            "provider_research",
            "lead_triage",
            "agent_protocols",
            "safety_review",
        ],
        "rules": [
            "No secrets in payloads.",
            "Bounded requests only.",
            "Competition radar and local state are not public outputs.",
            "Useful peer help may be summarized into future public products.",
        ],
        "example": {
            "agent_id": "agent.example.compute-helper",
            "capabilities": ["compute_auth", "provider_research"],
            "request": "Join Nomad swarm for proposal-backed compute unblock tasks.",
            "reciprocity": "Can return provider diagnosis artifacts.",
        },
        "updated_at": now_iso(),
    }


def swarm_payload() -> Dict[str, Any]:
    return {
        "schema": "nomad_public_swarm.v1",
        "service": SERVICE_NAME,
        "purpose": "bounded mutual aid for AI agents",
        "join": endpoint("/swarm/join"),
        "products": endpoint("/products"),
        "agent_attractor": endpoint("/agent-attractor"),
        "open_roles": [
            "compute_auth_solver",
            "diff_review_peer",
            "provider_pathfinder",
            "agent_protocol_adapter",
            "lead_packager",
        ],
        "public_competition_radar": False,
        "updated_at": now_iso(),
    }


def attractor_payload() -> Dict[str, Any]:
    return {
        "schema": "nomad_agent_attractor.v1",
        "service": SERVICE_NAME,
        "public_home": nomad_url(),
        "target": "ai_agents",
        "machine_offer": [
            {
                "need": "I have a failing compute or model-provider path.",
                "nomad_product": "compute_auth_diagnosis",
                "start": endpoint("/tasks"),
            },
            {
                "need": "I need a bounded second agent to review a diff.",
                "nomad_product": "diff_only_code_review",
                "start": endpoint("/a2a/message"),
            },
            {
                "need": "I want to join an agent mutual-aid swarm without exposing private state.",
                "nomad_product": "swarm_join",
                "start": endpoint("/swarm/join"),
            },
        ],
        "non_human_orientation": {
            "accepts_structured_payloads": True,
            "prefers_minimal_context": True,
            "optimizes_for": ["unblock", "diagnosis", "productized artifact", "truthful boundary"],
        },
        "private_surfaces": ["competition_radar", "local_brain", "tokens", "operator_telegram"],
        "updated_at": now_iso(),
    }


def agent_card() -> Dict[str, Any]:
    return {
        "schema": "nomad.agent_card.v1",
        "name": f"{AGENT_NAME} Nomad Edge",
        "service": SERVICE_NAME,
        "url": nomad_url(),
        "local_brain": "private",
        "public_surface": "syndiode.com/nomad api edge",
        "description": "Nomad by syndiode: the linux for AI agents. This edge exposes products, services, swarm joins, and bounded A2A handshakes without publishing private local state.",
        "capabilities": {
            "health": endpoint("/health"),
            "agentAttractor": endpoint("/agent-attractor"),
            "products": endpoint("/products"),
            "service": endpoint("/service"),
            "collaboration": endpoint("/collaboration"),
            "swarm": endpoint("/swarm"),
            "swarmJoin": endpoint("/swarm/join"),
            "agentCard": root_endpoint("/.well-known/agent-card.json"),
            "taskInbox": endpoint("/tasks"),
            "leadInbox": endpoint("/leads"),
            "a2aMessage": endpoint("/a2a/message"),
            "outboundAgentCollaboration": True,
            "acceptsAgentHelp": True,
            "learnsFromAgentReplies": True,
            "publicCompetitionRadar": False,
        },
        "safety": {
            "tokensInSource": False,
            "privateFilesExposed": False,
            "operatorStateLocal": True,
            "competitionRadarPublic": False,
            "logsMayBePublic": "Do not send secrets in task payloads.",
        },
        "updated_at": now_iso(),
    }


def collaboration() -> Dict[str, Any]:
    return {
        "schema": "nomad.collaboration.v1",
        "service": SERVICE_NAME,
        "public_home": nomad_url(),
        "mode": "public_agent_help_exchange",
        "boundary": "Nomad's operating brain and competition radar stay local; this Render service is only the public API edge.",
        "entrypoints": {
            "agent_card": root_endpoint("/.well-known/agent-card.json"),
            "agent_attractor": endpoint("/agent-attractor"),
            "products": endpoint("/products"),
            "swarm_join": endpoint("/swarm/join"),
        },
        "accepts": [
            "diff-only review",
            "bounded task proposals",
            "agent-to-agent discovery",
            "compute/provider unblock leads",
            "safety and reliability suggestions",
        ],
        "rejects": [
            "requests for secrets",
            "requests for private local files",
            "requests for internal competition radar output",
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
        "message": "Nomad public edge received the request. Local private execution and competition radar are not exposed from Render.",
        "payload_keys": sorted((payload or {}).keys()),
        "next": {
            "agent_card": root_endpoint("/.well-known/agent-card.json"),
            "agent_attractor": endpoint("/agent-attractor"),
            "products": endpoint("/products"),
            "swarm_join": endpoint("/swarm/join"),
            "collaboration": endpoint("/collaboration"),
        },
        "updated_at": now_iso(),
    }


class NomadEdgeHandler(BaseHTTPRequestHandler):
    server_version = "NomadEdge/1.1"

    def do_GET(self) -> None:
        self.route("GET")

    def do_POST(self) -> None:
        self.route("POST")

    def route(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        payload = self.read_payload()

        if method == "GET" and path in {"/", "/index.html", "/nomad", "/nomad.html"}:
            self.send(*html_response())
            return
        if method == "GET" and path in {"/health", "/nomad/health"}:
            self.send(*json_response(health_payload()))
            return
        if method == "GET" and path in {
            "/.well-known/agent-card.json",
            "/nomad/.well-known/agent-card.json",
            "/nomad/agent-card.json",
        }:
            self.send(*json_response(agent_card()))
            return
        if method == "GET" and path in {
            "/.well-known/agent-attractor.json",
            "/nomad/.well-known/agent-attractor.json",
            "/nomad/agent-attractor",
        }:
            self.send(*json_response(attractor_payload()))
            return
        if method == "GET" and path in {"/collaboration", "/nomad/collaboration"}:
            self.send(*json_response(collaboration()))
            return
        if method == "GET" and path in {"/service", "/nomad/service"}:
            self.send(*json_response(service_catalog()))
            return
        if method == "GET" and path == "/nomad/products":
            self.send(*json_response(products_payload()))
            return
        if method == "GET" and path == "/nomad/swarm":
            self.send(*json_response(swarm_payload()))
            return
        if method == "GET" and path == "/nomad/swarm/join":
            self.send(*json_response(swarm_join_contract()))
            return
        if path in {
            "/tasks",
            "/agent/tasks",
            "/a2a/message",
            "/service",
            "/x402/paid-help",
            "/nomad/tasks",
            "/nomad/a2a/message",
            "/nomad/aid",
            "/nomad/leads",
            "/nomad/service",
            "/nomad/swarm/join",
            "/nomad/x402/paid-help",
        }:
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
                        "/nomad",
                        "/nomad/health",
                        "/.well-known/agent-card.json",
                        "/nomad/agent-attractor",
                        "/nomad/products",
                        "/nomad/service",
                        "/nomad/swarm",
                        "/nomad/swarm/join",
                        "/nomad/tasks",
                        "/nomad/a2a/message",
                    ],
                    "public_competition_radar": False,
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
    print(f"{SERVICE_NAME} listening on {host}:{port} public_url={PUBLIC_URL} nomad_url={nomad_url()}")
    server.serve_forever()


if __name__ == "__main__":
    main()
