import json

from agent_contact import AgentContactOutbox
from agent_service import AgentServiceDesk
from nomad_guardrails import NomadGuardrailEngine, guardrail_status


class FakeResponse:
    def __init__(self, payload=None, status_code=202, text="accepted"):
        self._payload = payload or {}
        self.status_code = status_code
        self.text = text
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.posts = []

    def post(self, url, json, headers, timeout):
        self.posts.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return FakeResponse()


def test_guardrails_deny_public_github_comment_without_approval():
    result = guardrail_status(
        action="github.comment",
        args={"url": "https://github.com/microsoft/autogen/issues/7405", "text": "comment"},
    )

    assert result["ok"] is False
    assert result["evaluation"]["decision"] == "deny"
    assert result["evaluation"]["results"][-1]["metadata"]["approval_required"].startswith("APPROVE_LEAD_HELP")


def test_guardrails_allow_public_github_comment_with_explicit_approval():
    result = guardrail_status(
        action="github.comment",
        approval="comment",
        args={"url": "https://github.com/microsoft/autogen/issues/7405", "text": "comment"},
    )

    assert result["ok"] is True
    assert result["evaluation"]["decision"] == "allow"


def test_guardrails_redact_secret_values_before_execution():
    token = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"
    evaluation = NomadGuardrailEngine().evaluate(
        action="service.create_task",
        args={
            "problem": f"GitHub fails with token={token}",
            "metadata": {"Authorization": f"Bearer {token}"},
        },
    )

    assert evaluation.decision.value == "modify"
    assert token not in evaluation.effective_args["problem"]
    assert evaluation.effective_args["metadata"]["Authorization"] == "[REDACTED_SECRET]"


def test_service_task_redacts_secret_before_persisting(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_REQUIRE_SERVICE_PAYMENT", "false")
    token = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"
    desk = AgentServiceDesk(path=tmp_path / "tasks.json")

    result = desk.create_task(
        problem=f"Provider broken, token={token}",
        service_type="compute_auth",
    )

    task = result["task"]
    assert result["ok"] is True
    assert token not in task["problem"]
    assert "[REDACTED_SECRET]" in task["problem"]
    assert task["guardrails"]["create_task"]["decision"] == "modify"


def test_agent_contact_redacts_secret_before_queue_and_send(tmp_path):
    token = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"
    session = FakeSession()
    outbox = AgentContactOutbox(path=tmp_path / "contacts.json", session=session)

    queued = outbox.queue_contact(
        endpoint_url="https://remote-agent.ai/a2a/message",
        problem=f"Need compute help with token={token}",
        service_type="compute_auth",
    )
    sent = outbox.send_contact(queued["contact"]["contact_id"])

    assert queued["ok"] is True
    assert token not in queued["contact"]["problem"]
    assert queued["contact"]["guardrails"]["queue"]["decision"] == "modify"
    assert sent["contact"]["guardrails"]["send"]["decision"] == "allow"
    assert token not in json.dumps(session.posts[0]["json"])
