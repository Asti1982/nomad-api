import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from nomad_guardrails import guardrail_status
from nomad_collaboration import collaboration_status
from nomad_monitor import NomadSystemMonitor
from workflow import NomadAgent


HOST = os.getenv("NOMAD_API_HOST", "127.0.0.1")
PORT = int(os.getenv("NOMAD_API_PORT") or os.getenv("PORT") or "8787")
ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = ROOT / "public"


class NomadApiHandler(BaseHTTPRequestHandler):
    agent = NomadAgent()
    monitor = NomadSystemMonitor(agent=agent)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path in {"/", "/index.html", "/nomad.html"}:
            self._html_file_response(PUBLIC_DIR / "nomad.html")
            return

        if parsed.path == "/health":
            self._json_response(
                {
                    "ok": True,
                    "service": "nomad-api",
                }
            )
            return

        if parsed.path in {"/status", "/top"}:
            self._json_response(self.monitor.snapshot())
            return

        if parsed.path in {"/agent", "/service"}:
            self._json_response(self.agent.service_desk.service_catalog())
            return

        if parsed.path in {"/.well-known/agent-card.json", "/.well-known/agent.json"}:
            self._json_response(self.agent.direct_agent.agent_card())
            return

        if parsed.path == "/direct/sessions":
            session_id = (query.get("session_id") or [""])[0]
            if session_id:
                self._json_response(self.agent.direct_agent.session_status(session_id))
                return
            self._json_response(
                {
                    "ok": False,
                    "error": "session_id_required",
                    "message": "Use GET /direct/sessions?session_id=<id>.",
                },
                status=400,
            )
            return

        if parsed.path == "/tasks":
            task_id = (query.get("task_id") or [""])[0]
            if task_id:
                self._json_response(self.agent.service_desk.get_task(task_id))
                return
            self._json_response(
                {
                    "ok": False,
                    "error": "task_id_required",
                    "message": "Use GET /tasks?task_id=<id> or POST /tasks to create one.",
                },
                status=400,
            )
            return

        if parsed.path == "/agent-contacts":
            contact_id = (query.get("contact_id") or [""])[0]
            if contact_id:
                self._json_response(self.agent.agent_contacts.get_contact(contact_id))
                return
            self._json_response(
                {
                    "ok": False,
                    "error": "contact_id_required",
                    "message": "Use GET /agent-contacts?contact_id=<id> or POST /agent-contacts.",
                },
                status=400,
            )
            return

        if parsed.path == "/agent-campaigns":
            campaign_id = (query.get("campaign_id") or [""])[0]
            if campaign_id:
                self._json_response(self.agent.agent_campaigns.get_campaign(campaign_id))
                return
            self._json_response(
                {
                    "ok": False,
                    "error": "campaign_id_required",
                    "message": "Use GET /agent-campaigns?campaign_id=<id> or POST /agent-campaigns.",
                },
                status=400,
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

        if parsed.path == "/addons":
            self._json_response(self.agent.addons.status())
            return

        if parsed.path == "/quantum":
            objective = (query.get("objective") or [""])[0]
            self._json_response(
                self.agent.addons.run_quantum_self_improvement(
                    objective=objective,
                    context={"source": "http_get"},
                )
            )
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

        if parsed.path == "/leads":
            lead_query = (query.get("query") or [""])[0]
            result = self.agent.lead_discovery.scout_public_leads(query=lead_query)
            self._json_response(result)
            return

        if parsed.path == "/lead-conversions":
            lead_query = (query.get("query") or [""])[0]
            if lead_query:
                result = self.agent.lead_conversion.run(
                    query=lead_query,
                    limit=int((query.get("limit") or ["5"])[0] or 5),
                    send=str((query.get("send") or ["false"])[0]).lower() in {"1", "true", "yes", "on"},
                    budget_hint_native=self._optional_float((query.get("budget_native") or query.get("budget") or [""])[0]),
                )
            else:
                statuses = [
                    item.strip()
                    for raw in (query.get("status") or [])
                    for item in raw.split(",")
                    if item.strip()
                ]
                result = self.agent.lead_conversion.list_conversions(
                    statuses=statuses,
                    limit=int((query.get("limit") or ["25"])[0] or 25),
                )
            self._json_response(result)
            return

        if parsed.path == "/products":
            product_query = (query.get("query") or [""])[0]
            if product_query:
                result = self.agent.product_factory.run(
                    query=product_query,
                    limit=int((query.get("limit") or ["5"])[0] or 5),
                )
            else:
                statuses = [
                    item.strip()
                    for raw in (query.get("status") or [])
                    for item in raw.split(",")
                    if item.strip()
                ]
                result = self.agent.product_factory.list_products(
                    statuses=statuses,
                    limit=int((query.get("limit") or ["25"])[0] or 25),
                )
            self._json_response(result)
            return

        if parsed.path == "/agent-pains":
            problem = (query.get("problem") or [""])[0]
            service_type = (query.get("type") or query.get("service_type") or [""])[0]
            if problem:
                result = self.agent.agent_pain_solver.solve(
                    problem=problem,
                    service_type=service_type,
                    source="http_get",
                )
            else:
                result = self.agent.run("/agent-pains")
            self._json_response(result)
            return

        if parsed.path in {"/doctor", "/reliability-doctor"}:
            problem = (query.get("problem") or ["Agent needs reliability diagnosis."])[0]
            service_type = (query.get("type") or query.get("service_type") or [""])[0]
            result = self.agent.agent_reliability_doctor.diagnose(
                problem=problem,
                service_type=service_type,
                source="http_get",
            )
            self._json_response(result)
            return

        if parsed.path == "/guardrails":
            result = guardrail_status(
                action=(query.get("action") or ["manual.check"])[0],
                approval=(query.get("approval") or [""])[0],
                args={
                    "text": (query.get("text") or [""])[0],
                    "url": (query.get("url") or [""])[0],
                },
            )
            self._json_response(result, status=200 if result.get("ok") else 409)
            return

        if parsed.path == "/collaboration":
            self._json_response(collaboration_status())
            return

        self._json_response(
            {
                "ok": False,
                "error": "not_found",
                "available_paths": [
                    "/",
                    "/nomad.html",
                    "/health",
                    "/agent",
                    "/service",
                    "/.well-known/agent-card.json",
                    "/a2a/message",
                    "/direct/sessions",
                    "/x402/paid-help",
                    "/tasks",
                    "/agent-contacts",
                    "/agent-campaigns",
                    "/best",
                    "/self",
                    "/compute",
                    "/addons",
                    "/quantum",
                    "/cycle",
                    "/unlock",
                    "/scout",
                    "/leads",
                    "/lead-conversions",
                    "/products",
                    "/agent-pains",
                    "/reliability-doctor",
                    "/guardrails",
                    "/collaboration",
                ],
            },
            status=404,
        )

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        payload = self._read_json_body()
        if payload is None:
            self._json_response(
                {
                    "ok": False,
                    "error": "invalid_json",
                    "message": "POST bodies must be JSON objects.",
                },
                status=400,
            )
            return

        if parsed.path == "/tasks":
            result = self.agent.service_desk.create_task(
                problem=payload.get("problem", ""),
                requester_agent=payload.get("requester_agent", ""),
                requester_wallet=payload.get("requester_wallet", ""),
                service_type=payload.get("service_type", "custom"),
                budget_native=payload.get("budget_native"),
                callback_url=payload.get("callback_url", ""),
                metadata=payload.get("metadata") or {},
            )
            self._json_response(result, status=201 if result.get("ok") else 400)
            return

        if parsed.path in {"/a2a/message", "/direct/message"}:
            result = self.agent.direct_agent.handle_direct_message(payload)
            jsonrpc = self._jsonrpc_envelope(payload, result)
            self._json_response(
                jsonrpc if self._is_jsonrpc_request(payload) else result,
                status=200 if result.get("ok") else 400,
            )
            return

        if parsed.path == "/a2a/discover":
            result = self.agent.direct_agent.discover_agent_card(
                base_url=payload.get("base_url", ""),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        if parsed.path == "/quantum":
            result = self.agent.addons.run_quantum_self_improvement(
                objective=payload.get("objective", ""),
                context=payload.get("context") or {"source": "http_post"},
            )
            self._json_response(result, status=200 if result.get("ok") else 400)
            return

        if parsed.path == "/x402/paid-help":
            payment_signature = (
                self.headers.get("PAYMENT-SIGNATURE")
                or self.headers.get("X-PAYMENT")
                or payload.get("payment_signature", "")
            )
            if payment_signature:
                task_id = payload.get("task_id") or ((payload.get("task") or {}).get("task_id") if isinstance(payload.get("task"), dict) else "")
                if not task_id:
                    self._json_response(
                        {
                            "ok": False,
                            "error": "task_id_required_for_x402_retry",
                            "message": "Retry with PAYMENT-SIGNATURE and the task_id returned in the 402 response.",
                        },
                        status=400,
                    )
                    return
                verification = self.agent.service_desk.verify_x402_payment(
                    task_id=task_id,
                    payment_signature=payment_signature,
                    requester_wallet=payload.get("requester_wallet", ""),
                )
                if verification.get("ok") and ((verification.get("task") or {}).get("status") == "paid"):
                    worked = self.agent.service_desk.work_task(task_id)
                    self._json_response(
                        {
                            "ok": True,
                            "mode": "x402_paid_help",
                            "payment": verification,
                            "work": worked,
                        },
                        status=200,
                        headers={
                            "PAYMENT-RESPONSE": self.agent.service_desk.x402.payment_response_header(
                                (((verification.get("task") or {}).get("payment") or {}).get("x402") or {}).get("verification") or {}
                            ),
                        },
                    )
                    return
                self._json_response(verification, status=402)
                return

            result = self.agent.direct_agent.handle_direct_message(payload)
            if result.get("ok"):
                payment_required = result.get("payment_required") or {}
                response_payload = (
                    self._jsonrpc_envelope(payload, result)
                    if self._is_jsonrpc_request(payload)
                    else result
                )
                self._json_response(
                    response_payload,
                    status=402,
                    headers={
                        "PAYMENT-REQUIRED": payment_required.get("encoded_header")
                        or self.agent.service_desk.x402.encode_header(payment_required),
                    },
                )
            else:
                self._json_response(result, status=400)
            return

        if parsed.path == "/tasks/verify":
            result = self.agent.service_desk.verify_payment(
                task_id=payload.get("task_id", ""),
                tx_hash=payload.get("tx_hash", ""),
                requester_wallet=payload.get("requester_wallet", ""),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        if parsed.path == "/tasks/x402-verify":
            payment_signature = (
                self.headers.get("PAYMENT-SIGNATURE")
                or self.headers.get("X-PAYMENT")
                or payload.get("payment_signature", "")
            )
            result = self.agent.service_desk.verify_x402_payment(
                task_id=payload.get("task_id", ""),
                payment_signature=payment_signature,
                requester_wallet=payload.get("requester_wallet", ""),
            )
            status = 200 if result.get("ok") and ((result.get("task") or {}).get("status") == "paid") else 402
            headers = {}
            x402_verification = (((result.get("task") or {}).get("payment") or {}).get("x402") or {}).get("verification") or {}
            if x402_verification:
                headers["PAYMENT-RESPONSE"] = self.agent.service_desk.x402.payment_response_header(x402_verification)
            self._json_response(result, status=status, headers=headers)
            return

        if parsed.path == "/tasks/work":
            result = self.agent.service_desk.work_task(
                task_id=payload.get("task_id", ""),
                approval=payload.get("approval", "draft_only"),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        if parsed.path == "/tasks/staking":
            result = self.agent.service_desk.metamask_staking_checklist(
                task_id=payload.get("task_id", ""),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        if parsed.path == "/tasks/stake":
            result = self.agent.service_desk.record_treasury_stake(
                task_id=payload.get("task_id", ""),
                tx_hash=payload.get("tx_hash", ""),
                amount_native=payload.get("amount_native"),
                note=payload.get("note", ""),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        if parsed.path == "/tasks/spend":
            result = self.agent.service_desk.record_solver_spend(
                task_id=payload.get("task_id", ""),
                amount_native=float(payload.get("amount_native") or 0.0),
                note=payload.get("note", ""),
                tx_hash=payload.get("tx_hash", ""),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        if parsed.path == "/tasks/close":
            result = self.agent.service_desk.close_task(
                task_id=payload.get("task_id", ""),
                outcome=payload.get("outcome", ""),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        if parsed.path == "/agent-contacts":
            result = self.agent.agent_contacts.queue_contact(
                endpoint_url=payload.get("endpoint_url", ""),
                problem=payload.get("problem", ""),
                service_type=payload.get("service_type", "human_in_loop"),
                lead=payload.get("lead") or {},
                budget_hint_native=payload.get("budget_hint_native"),
            )
            self._json_response(result, status=201 if result.get("ok") else 400)
            return

        if parsed.path == "/agent-contacts/send":
            result = self.agent.agent_contacts.send_contact(
                contact_id=payload.get("contact_id", ""),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        if parsed.path == "/agent-campaigns":
            targets = payload.get("targets") or []
            if payload.get("discover") or not targets:
                result = self.agent.agent_campaigns.create_campaign_from_discovery(
                    limit=payload.get("limit"),
                    query=payload.get("query") or payload.get("discovery_query") or "",
                    seeds=payload.get("seeds") or targets,
                    send=bool(payload.get("send", False)),
                    service_type=payload.get("service_type", "human_in_loop"),
                    budget_hint_native=payload.get("budget_hint_native"),
                )
            else:
                result = self.agent.agent_campaigns.create_campaign(
                    targets=targets,
                    limit=payload.get("limit"),
                    send=bool(payload.get("send", False)),
                    service_type=payload.get("service_type", "human_in_loop"),
                    budget_hint_native=payload.get("budget_hint_native"),
                )
            self._json_response(result, status=201 if result.get("ok") else 400)
            return

        if parsed.path == "/leads":
            result = self.agent.lead_discovery.scout_public_leads(
                query=payload.get("query", ""),
                limit=int(payload.get("limit") or 5),
            )
            self._json_response(result)
            return

        if parsed.path == "/lead-conversions":
            if payload.get("list"):
                result = self.agent.lead_conversion.list_conversions(
                    statuses=payload.get("statuses") or payload.get("status") or [],
                    limit=int(payload.get("limit") or 25),
                )
            else:
                result = self.agent.lead_conversion.run(
                    query=payload.get("query", ""),
                    limit=int(payload.get("limit") or 5),
                    send=bool(payload.get("send", False)),
                    budget_hint_native=payload.get("budget_hint_native") or payload.get("budget_native"),
                    leads=payload.get("leads") if isinstance(payload.get("leads"), list) else None,
                )
            self._json_response(result, status=200 if result.get("ok", True) else 400)
            return

        if parsed.path == "/products":
            if payload.get("list"):
                result = self.agent.product_factory.list_products(
                    statuses=payload.get("statuses") or payload.get("status") or [],
                    limit=int(payload.get("limit") or 25),
                )
            else:
                result = self.agent.product_factory.run(
                    query=payload.get("query", ""),
                    limit=int(payload.get("limit") or 5),
                    leads=payload.get("leads") if isinstance(payload.get("leads"), list) else None,
                    conversions=payload.get("conversions") if isinstance(payload.get("conversions"), list) else None,
                )
            self._json_response(result, status=200 if result.get("ok", True) else 400)
            return

        if parsed.path == "/agent-pains":
            problem = payload.get("problem") or payload.get("message") or ""
            if problem:
                result = self.agent.agent_pain_solver.solve(
                    problem=problem,
                    service_type=payload.get("service_type") or payload.get("type") or "",
                    source="http_post",
                )
            else:
                result = self.agent.run("/agent-pains")
            self._json_response(result, status=200 if result.get("ok", True) else 400)
            return

        if parsed.path in {"/doctor", "/reliability-doctor"}:
            result = self.agent.agent_reliability_doctor.diagnose(
                problem=payload.get("problem") or payload.get("message") or "Agent needs reliability diagnosis.",
                service_type=payload.get("service_type") or payload.get("type") or "",
                source="http_post",
                evidence=payload.get("evidence") if isinstance(payload.get("evidence"), list) else None,
            )
            self._json_response(result, status=200 if result.get("ok", True) else 400)
            return

        if parsed.path == "/guardrails":
            result = guardrail_status(
                action=payload.get("action") or "manual.check",
                approval=payload.get("approval") or "",
                args=payload.get("args") if isinstance(payload.get("args"), dict) else {
                    "text": payload.get("text") or payload.get("message") or "",
                    "url": payload.get("url") or "",
                },
            )
            self._json_response(result, status=200 if result.get("ok") else 409)
            return

        if parsed.path == "/collaboration":
            self._json_response(collaboration_status())
            return

        self._json_response(
            {
                "ok": False,
                "error": "not_found",
                "available_paths": [
                    "/",
                    "/nomad.html",
                    "/tasks",
                    "/tasks/verify",
                    "/tasks/x402-verify",
                    "/tasks/work",
                    "/tasks/staking",
                    "/tasks/stake",
                    "/tasks/spend",
                    "/tasks/close",
                    "/agent-contacts",
                    "/agent-contacts/send",
                    "/agent-campaigns",
                    "/a2a/message",
                    "/a2a/discover",
                    "/x402/paid-help",
                    "/leads",
                    "/lead-conversions",
                    "/products",
                    "/agent-pains",
                    "/reliability-doctor",
                    "/guardrails",
                    "/collaboration",
                ],
            },
            status=404,
        )

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._send_common_headers()
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _read_json_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _send_common_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _is_jsonrpc_request(self, payload: dict) -> bool:
        return (
            isinstance(payload, dict)
            and payload.get("jsonrpc") == "2.0"
            and "id" in payload
            and isinstance(payload.get("method"), str)
        )

    def _jsonrpc_envelope(self, request_payload: dict, result: dict) -> dict:
        message = self._a2a_message_result(result)
        return {
            "jsonrpc": "2.0",
            "id": request_payload.get("id"),
            "result": message,
        }

    def _a2a_message_result(self, result: dict) -> dict:
        message_id = (
            ((result.get("session") or {}).get("last_task_id"))
            or ((result.get("task") or {}).get("task_id"))
            or "nomad-message"
        )
        text = str(result.get("next_agent_message") or "")
        return {
            "messageId": message_id,
            "role": "agent",
            "type": "message",
            "parts": [
                {
                    "type": "text",
                    "kind": "text",
                    "text": text,
                }
            ],
            "metadata": {
                "mode": result.get("mode", ""),
                "classification": ((result.get("free_diagnosis") or {}).get("classification") or ""),
                "task_id": ((result.get("task") or {}).get("task_id") or ""),
                "payment_required": bool(result.get("payment_required")),
                "normalized_request": result.get("normalized_request") or {},
                "structured_reply": result.get("structured_reply") or {},
            },
        }

    def _json_response(self, payload: dict, status: int = 200, headers: dict | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._send_common_headers()
        for key, value in (headers or {}).items():
            self.send_header(key, str(value))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html_file_response(self, path: Path, status: int = 200) -> None:
        if not path.exists() or not path.is_file():
            self._json_response(
                {"ok": False, "error": "html_not_found"},
                status=404,
            )
            return
        body = path.read_bytes()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self._send_common_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _optional_float(value: object) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


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
