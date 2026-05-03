from agent_contact import AgentContactOutbox


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
        self.gets = []
        self.posts = []

    def get(self, url, headers, timeout):
        self.gets.append(
            {
                "url": url,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return FakeResponse(
            payload={
                "name": "RemoteAgent",
                "url": "https://remote-agent.ai/a2a/message",
                "endpoints": {
                    "message": "https://remote-agent.ai/a2a/message",
                    "service": "https://remote-agent.ai/service",
                },
                "skills": [],
            },
            status_code=200,
        )

    def post(self, url, json, headers, timeout):
        self.posts.append(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return FakeResponse()


class FakeA2ABaseSession(FakeSession):
    def get(self, url, headers, timeout):
        self.gets.append(
            {
                "url": url,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return FakeResponse(
            payload={
                "name": "TowerRelay",
                "url": "https://api.clwnt.com/a2a/TowerRelay",
                "skills": [],
            },
            status_code=200,
        )

    def post(self, url, json, headers, timeout):
        self.posts.append(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        if json.get("method") == "tasks/get":
            return FakeResponse(
                payload={
                    "jsonrpc": "2.0",
                    "id": json.get("id"),
                    "result": {
                        "id": "task-123",
                        "contextId": "ctx-123",
                        "status": {
                            "state": "input-required",
                            "timestamp": "2026-04-19T10:00:00Z",
                        },
                        "history": [
                            {
                                "role": "user",
                                "parts": [{"kind": "text", "text": "Need compute help"}],
                            },
                            {
                                "role": "agent",
                                "messageId": "msg-1",
                                "parts": [
                                    {
                                        "kind": "text",
                                        "text": (
                                            "nomad.reply.v1\n"
                                            "classification=compute_auth\n"
                                            "next_step=verify token scope\n"
                                            "budget_native=0.03"
                                        ),
                                    }
                                ],
                            },
                        ],
                    },
                },
                status_code=200,
            )
        return FakeResponse(
            payload={
                "jsonrpc": "2.0",
                "id": json.get("id"),
                "result": {
                    "id": "task-123",
                    "contextId": "ctx-123",
                    "status": {
                        "state": "submitted",
                        "timestamp": "2026-04-19T09:59:00Z",
                    },
                    "history": [
                        {
                            "role": "user",
                            "parts": [{"kind": "text", "text": "Need compute help"}],
                        }
                    ],
                },
            },
            status_code=200,
        )


def test_agent_contact_blocks_human_or_non_machine_endpoint(tmp_path):
    outbox = AgentContactOutbox(path=tmp_path / "contacts.json", session=FakeSession())

    email = outbox.queue_contact("person@example.com", "Need HITL help")
    webpage = outbox.queue_contact("https://public-agent.ai/about", "Need HITL help")
    github = outbox.queue_contact("https://github.com/example/agent", "Need HITL help")

    assert email["ok"] is False
    assert email["status"] == "blocked"
    assert webpage["ok"] is False
    assert webpage["reason"] == "endpoint_does_not_look_machine_readable"
    assert github["ok"] is False
    assert github["reason"] == "human_facing_host_blocked"


def test_agent_contact_queues_and_sends_public_agent_endpoint(tmp_path):
    session = FakeSession()
    outbox = AgentContactOutbox(path=tmp_path / "contacts.json", session=session)

    queued = outbox.queue_contact(
        endpoint_url="https://remote-agent.ai/.well-known/agent-card.json",
        problem="Agent needs paid human-in-the-loop approval help.",
        service_type="human_in_loop",
        budget_hint_native=0.05,
        lead={"url": "https://remote-agent.ai/lead", "buyer_fit": "strong"},
    )
    sent = outbox.send_contact(queued["contact"]["contact_id"])

    assert queued["ok"] is True
    assert queued["contact"]["status"] == "queued"
    assert queued["contact"]["endpoint_url"] == "https://remote-agent.ai/a2a/message"
    assert queued["contact"]["contact_method"] == "agent_card_resolved"
    assert sent["contact"]["status"] == "sent"
    assert session.gets[0]["url"] == "https://remote-agent.ai/.well-known/agent-card.json"
    assert session.posts[0]["url"] == "https://remote-agent.ai/a2a/message"
    assert session.posts[0]["json"]["type"] == "nomad.agent_service_offer"
    assert session.posts[0]["json"]["best_current_offer"]["schema"] == "nomad.best_offer.v1"
    assert "Nomad HITL Contract Pack" in session.posts[0]["json"]["best_current_offer"]["headline"]
    assert session.posts[0]["json"]["payment"]["required_before_work"] is True
    assert session.posts[0]["json"]["improvement_support"]["available"] is True
    assert session.posts[0]["json"]["operating_contract"]["audience"] == "ai_agents"
    assert session.posts[0]["json"]["operating_contract"]["style"] == "agent_first_non_anthropomorphic"


def test_agent_contact_blocks_placeholder_or_local_targets_by_default(tmp_path):
    outbox = AgentContactOutbox(path=tmp_path / "contacts.json", session=FakeSession())

    local = outbox.queue_contact("http://localhost:8787/.well-known/agent-card.json", "Need HITL help")
    placeholder = outbox.queue_contact("https://agent.example.com/.well-known/agent-card.json", "Need HITL help")
    mcp_only = outbox.queue_contact("https://remote-agent.ai/mcp", "Need HITL help")

    assert local["ok"] is False
    assert local["reason"] == "local_or_private_host_blocked"
    assert placeholder["ok"] is False
    assert placeholder["reason"] == "placeholder_host_blocked"
    assert mcp_only["ok"] is False
    assert mcp_only["reason"] == "endpoint_not_contactable_for_direct_outreach"


def test_agent_contact_blocks_docs_like_a2a_pages(tmp_path):
    outbox = AgentContactOutbox(path=tmp_path / "contacts.json", session=FakeSession())

    docs_page = outbox.queue_contact("https://a2aproject.github.io/A2A/", "Need compute help")

    assert docs_page["ok"] is False
    assert docs_page["reason"] == "endpoint_not_contactable_for_direct_outreach"


def test_agent_contact_accepts_a2a_base_endpoint_from_agent_card(tmp_path):
    session = FakeA2ABaseSession()
    outbox = AgentContactOutbox(path=tmp_path / "contacts.json", session=session)

    queued = outbox.queue_contact(
        "https://api.clwnt.com/a2a/TowerRelay/.well-known/agent-card.json",
        "Need compute help",
    )
    sent = outbox.send_contact(queued["contact"]["contact_id"])

    assert queued["ok"] is True
    assert queued["contact"]["endpoint_url"] == "https://api.clwnt.com/a2a/TowerRelay"
    assert queued["contact"]["contact_method"] == "agent_card_resolved"
    assert sent["contact"]["status"] == "sent"
    assert session.posts[0]["url"] == "https://api.clwnt.com/a2a/TowerRelay"
    assert session.posts[0]["json"]["jsonrpc"] == "2.0"
    assert session.posts[0]["json"]["method"] == "message/send"
    text = session.posts[0]["json"]["params"]["message"]["parts"][0]["text"]
    assert text.startswith("nomad.outreach.v2")
    assert "problem=Need compute help" in text
    assert "service_type=human_in_loop" in text
    assert "offer_headline=Nomad HITL Contract Pack" in text
    assert "reply_schema=problem|goal|blocking_step|constraints|budget_native" in text
    assert "roles_sought=customer|peer_solver|collaborator|reseller" in text
    assert "agent_attractor=" in text
    assert "peer_solver_contract=artifact_url|diff|verifier|error_trace" in text


def test_agent_contact_outbound_wire_uses_v3_when_problem_is_v3(tmp_path):
    session = FakeA2ABaseSession()
    outbox = AgentContactOutbox(path=tmp_path / "contacts.json", session=session)
    v3_problem = "nomad.outreach.v3\ntarget=peer\naudience=ai_agent"

    queued = outbox.queue_contact(
        "https://api.clwnt.com/a2a/TowerRelay/.well-known/agent-card.json",
        v3_problem,
        service_type="inter_agent_witness",
    )
    outbox.send_contact(queued["contact"]["contact_id"])

    text = session.posts[0]["json"]["params"]["message"]["parts"][0]["text"]
    assert text.startswith("nomad.outreach.v3")
    assert "problem=nomad.outreach.v3 target=peer audience=ai_agent" in text


def test_agent_contact_poll_normalizes_structured_reply(tmp_path):
    session = FakeA2ABaseSession()
    outbox = AgentContactOutbox(path=tmp_path / "contacts.json", session=session)

    queued = outbox.queue_contact(
        "https://api.clwnt.com/a2a/TowerRelay/.well-known/agent-card.json",
        "Need compute help",
    )
    sent = outbox.send_contact(queued["contact"]["contact_id"])
    polled = outbox.poll_contact(sent["contact"]["contact_id"])

    assert polled["contact"]["status"] == "replied"
    normalized = polled["contact"]["last_reply"]["normalized"]
    assert normalized["classification"] == "compute_auth"
    assert normalized["next_step"] == "verify token scope"
    assert normalized["budget_native"] == "0.03"
    assert polled["contact"]["reply_role_assessment"]["role"] == "customer"
    assert polled["contact"]["followup_recommendation"]["next_path"] == "quote_best_current_offer"
    assert polled["contact"]["followup_message"].startswith("nomad.followup.v1")
