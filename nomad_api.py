import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from workflow import NomadAgent


HOST = os.getenv("NOMAD_API_HOST", "127.0.0.1")
PORT = int(os.getenv("NOMAD_API_PORT", "8787"))


class NomadApiHandler(BaseHTTPRequestHandler):
    agent = NomadAgent()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == "/health":
            self._json_response(
                {
                    "ok": True,
                    "service": "nomad-api",
                }
            )
            return

        if parsed.path == "/best":
            profile = (query.get("profile") or ["ai_first"])[0]
            result = self.agent.run(f"/best {profile}".strip())
            self._json_response(result)
            return

        if parsed.path == "/self":
            profile = (query.get("profile") or ["ai_first"])[0]
            result = self.agent.run(f"/self {profile}".strip())
            self._json_response(result)
            return

        if parsed.path == "/compute":
            profile = (query.get("profile") or ["ai_first"])[0]
            result = self.agent.run(f"/compute {profile}".strip())
            self._json_response(result)
            return

        if parsed.path == "/cycle":
            profile = (query.get("profile") or ["ai_first"])[0]
            objective = (query.get("objective") or [""])[0]
            prompt = f"/cycle {objective} for {profile}".strip()
            result = self.agent.run(prompt)
            self._json_response(result)
            return

        if parsed.path == "/unlock":
            category = (query.get("category") or ["compute"])[0]
            profile = (query.get("profile") or ["ai_first"])[0]
            result = self.agent.run(f"/unlock {category} for {profile}".strip())
            self._json_response(result)
            return

        if parsed.path == "/scout":
            category = (query.get("category") or [""])[0]
            profile = (query.get("profile") or ["ai_first"])[0]
            prompt = f"/scout {category} for {profile}".strip()
            result = self.agent.run(prompt)
            self._json_response(result)
            return

        self._json_response(
            {
                "ok": False,
                "error": "not_found",
                "available_paths": ["/health", "/best", "/self", "/compute", "/cycle", "/unlock", "/scout"],
            },
            status=404,
        )

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _json_response(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve() -> None:
    server = ThreadingHTTPServer((HOST, PORT), NomadApiHandler)
    print(f"--- Nomad API Live on http://{HOST}:{PORT} ---")
    server.serve_forever()


def serve_in_thread() -> threading.Thread:
    thread = threading.Thread(target=serve, name="nomad-api", daemon=True)
    thread.start()
    return thread


if __name__ == "__main__":
    serve()
