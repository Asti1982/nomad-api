import base64
import json

from agent_contact import AgentContactOutbox
from agent_discovery import AgentEndpointDiscovery


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/search/code"):
            return FakeResponse(
                {
                    "items": [
                        {
                            "name": "agent-card.json",
                            "path": ".well-known/agent-card.json",
                            "html_url": "https://github.com/example/agent/.well-known/agent-card.json",
                            "url": "https://api.github.test/repos/example/agent/contents/.well-known/agent-card.json",
                        }
                    ]
                }
            )
        content = json.dumps(
            {
                "name": "ExampleAgent",
                "url": "https://example-agent.test/a2a/message",
                "skills": [{"id": "hitl", "endpoint": "https://example-agent.test/mcp"}],
            }
        )
        return FakeResponse(
            {
                "encoding": "base64",
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            }
        )


def test_agent_endpoint_discovery_extracts_urls_from_public_code(tmp_path):
    outbox = AgentContactOutbox(path=tmp_path / "contacts.json")
    discovery = AgentEndpointDiscovery(
        session=FakeSession(),
        outbox=outbox,
        github_api_base="https://api.github.test",
    )

    result = discovery.discover(limit=10, query='"agent-card.json"')

    assert result["ok"] is True
    endpoints = {target["endpoint_url"] for target in result["targets"]}
    assert "https://example-agent.test/a2a/message" in endpoints
    assert "https://example-agent.test/mcp" in endpoints
    assert result["stats"]["targets_found"] == 2


def test_agent_endpoint_discovery_expands_seed_base_urls(tmp_path):
    outbox = AgentContactOutbox(path=tmp_path / "contacts.json")
    discovery = AgentEndpointDiscovery(
        session=FakeSession(),
        outbox=outbox,
        github_api_base="https://api.github.test",
    )

    result = discovery.discover(limit=2, seeds=["https://seed-agent.test"])

    endpoints = [target["endpoint_url"] for target in result["targets"]]
    assert endpoints == [
        "https://seed-agent.test/.well-known/agent-card.json",
        "https://seed-agent.test/.well-known/agent.json",
    ]
