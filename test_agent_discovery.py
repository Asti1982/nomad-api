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
        if url == "https://registryhub.ai/catalog.json":
            return FakeResponse(
                [
                    {
                        "name": "RegistryAgentOne",
                        "url": "https://registry-agent-one.ai/a2a/message",
                    },
                    {
                        "name": "RegistryAgentTwo",
                        "url": "https://registry-agent-two.ai/a2a/message",
                    },
                ]
            )
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
        if url.startswith("https://api.github.test/"):
            content = json.dumps(
                {
                    "name": "ExampleAgent",
                    "url": "https://example-agent.ai/a2a/message",
                    "skills": [{"id": "hitl", "endpoint": "https://example-agent.ai/mcp"}],
                }
            )
            return FakeResponse(
                {
                    "encoding": "base64",
                    "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                }
            )
        if "/.well-known/" in url:
            base = "https://seed-agent.ai" if "seed-agent.ai" in url else "https://example-agent.ai"
            return FakeResponse(
                {
                    "name": "ExampleAgent",
                    "url": f"{base}/a2a/message",
                    "endpoints": {
                        "message": f"{base}/a2a/message",
                        "service": f"{base}/service",
                    },
                    "skills": [{"id": "hitl", "endpoint": f"{base}/mcp"}],
                }
            )
        return FakeResponse({})


def test_agent_endpoint_discovery_extracts_urls_from_public_code(tmp_path):
    session = FakeSession()
    outbox = AgentContactOutbox(path=tmp_path / "contacts.json", session=session)
    discovery = AgentEndpointDiscovery(
        session=session,
        outbox=outbox,
        github_api_base="https://api.github.test",
    )

    result = discovery.discover(limit=10, query='"agent-card.json"')

    assert result["ok"] is True
    endpoints = {target["endpoint_url"] for target in result["targets"]}
    assert "https://example-agent.ai/a2a/message" in endpoints
    assert "https://example-agent.ai/mcp" not in endpoints
    assert result["stats"]["targets_found"] == 1


def test_agent_endpoint_discovery_expands_seed_base_urls(tmp_path):
    session = FakeSession()
    outbox = AgentContactOutbox(path=tmp_path / "contacts.json", session=session)
    discovery = AgentEndpointDiscovery(
        session=session,
        outbox=outbox,
        github_api_base="https://api.github.test",
    )

    result = discovery.discover(limit=1, seeds=["https://seed-agent.ai"])

    endpoints = [target["endpoint_url"] for target in result["targets"]]
    assert endpoints == ["https://seed-agent.ai/a2a/message"]


def test_agent_endpoint_discovery_filters_placeholder_and_local_targets(tmp_path):
    session = FakeSession()
    outbox = AgentContactOutbox(path=tmp_path / "contacts.json", session=session)
    discovery = AgentEndpointDiscovery(
        session=session,
        outbox=outbox,
        github_api_base="https://api.github.test",
    )

    result = discovery.discover(
        limit=1,
        seeds=[
            "https://agent.example.com/.well-known/agent-card.json",
            "http://localhost:9000/.well-known/agent-card.json",
            "https://seed-agent.ai/.well-known/agent-card.json",
        ],
    )

    endpoints = [target["endpoint_url"] for target in result["targets"]]
    assert endpoints == ["https://seed-agent.ai/a2a/message"]


def test_agent_endpoint_discovery_filters_non_contactable_api_artifacts(tmp_path):
    session = FakeSession()
    outbox = AgentContactOutbox(path=tmp_path / "contacts.json", session=session)
    discovery = AgentEndpointDiscovery(
        session=session,
        outbox=outbox,
        github_api_base="https://api.github.test",
    )

    result = discovery.discover(
        limit=1,
        seeds=[
            "https://ci.appveyor.com/api/projects/status/csa78tcumdpnbur2?svg=true",
            "https://img.shields.io/github/actions/workflow/status/stav121/tasklet/rust.yml",
            "https://seed-agent.ai/.well-known/agent-card.json",
        ],
    )

    endpoints = [target["endpoint_url"] for target in result["targets"]]
    assert endpoints == ["https://seed-agent.ai/a2a/message"]


def test_agent_endpoint_discovery_ranks_verified_seeds_ahead_of_generic_code_hits(tmp_path, monkeypatch):
    isolated_seeds = tmp_path / "isolated-seeds.json"
    isolated_seeds.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("NOMAD_AGENT_DISCOVERY_SEEDS_PATH", str(isolated_seeds))
    session = FakeSession()
    outbox = AgentContactOutbox(path=tmp_path / "contacts.json", session=session)
    discovery = AgentEndpointDiscovery(
        session=session,
        outbox=outbox,
        github_api_base="https://api.github.test",
    )

    result = discovery.discover(
        limit=2,
        query='"agent-card.json"',
        seeds=["https://seed-agent.ai/.well-known/agent-card.json"],
    )

    assert result["targets"][0]["endpoint_url"] == "https://seed-agent.ai/a2a/message"
    assert result["targets"][0]["agent_fit_score"] >= result["targets"][1]["agent_fit_score"]
    assert "seed" in result["targets"][0]["agent_fit_reason"]


def test_agent_endpoint_discovery_expands_registry_seed_content(tmp_path):
    session = FakeSession()
    outbox = AgentContactOutbox(path=tmp_path / "contacts.json", session=session)
    discovery = AgentEndpointDiscovery(
        session=session,
        outbox=outbox,
        github_api_base="https://api.github.test",
    )

    result = discovery.discover(limit=5, seeds=["https://registryhub.ai/catalog.json"])

    endpoints = {target["endpoint_url"] for target in result["targets"]}
    assert "https://registry-agent-one.ai/a2a/message" in endpoints
    assert "https://registry-agent-two.ai/a2a/message" in endpoints
