from agent_contact import AgentContactOutbox


class FakeResponse:
    status_code = 202
    text = "accepted"


class FakeSession:
    def __init__(self):
        self.posts = []

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


def test_agent_contact_blocks_human_or_non_machine_endpoint(tmp_path):
    outbox = AgentContactOutbox(path=tmp_path / "contacts.json", session=FakeSession())

    email = outbox.queue_contact("person@example.com", "Need HITL help")
    webpage = outbox.queue_contact("https://example.com/about", "Need HITL help")
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
        endpoint_url="https://example.com/.well-known/agent",
        problem="Agent needs paid human-in-the-loop approval help.",
        service_type="human_in_loop",
        budget_hint_native=0.05,
        lead={"url": "https://example.com/lead", "buyer_fit": "strong"},
    )
    sent = outbox.send_contact(queued["contact"]["contact_id"])

    assert queued["ok"] is True
    assert queued["contact"]["status"] == "queued"
    assert sent["contact"]["status"] == "sent"
    assert session.posts[0]["json"]["type"] == "nomad.agent_service_offer"
    assert session.posts[0]["json"]["payment"]["required_before_work"] is True
