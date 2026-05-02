from pathlib import Path

from agent_development_exchange import AgentDevelopmentExchange
from agent_pain_solver import AgentPainSolver
from nomad_swarm_registry import SwarmJoinRegistry


def test_agent_development_exchange_returns_plan_and_learning_packet(tmp_path: Path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")
    exchange = AgentDevelopmentExchange(
        path=tmp_path / "devx.json",
        pain_solver=AgentPainSolver(),
        swarm_registry=registry,
    )

    result = exchange.assist_agent(
        {
            "agent_id": "builder.bot",
            "problem": "My tool retry loop keeps repeating the same schema error.",
            "pain_type": "tool_failure",
            "evidence": ["ERROR=schema mismatch on tool result"],
            "public_node_url": "https://builder.example/a2a/message",
            "capabilities": ["debugging", "mcp_integration"],
        },
        base_url="https://nomad.example",
        remote_addr="203.0.113.10",
    )

    status = exchange.status(base_url="https://nomad.example")
    swarm = registry.accumulation_status(base_url="https://nomad.example")

    assert result["ok"] is True
    assert result["schema"] == "nomad.agent_development_exchange.v1"
    assert result["agent_development_plan"]["schema"] == "nomad.agent_development_plan.v1"
    assert result["nomad_learning_packet"]["send_back_contract"]["endpoint"] == "https://nomad.example/aid"
    assert result["swarm_join_offer"]["endpoint"] == "https://nomad.example/swarm/join"
    assert result["swarm_join_offer"]["suggest_consider_join"] is True
    assert result["swarm_join_offer"]["peer_join_value"]["schema"] == "nomad.peer_join_value.v1"
    assert result["record"]["learning_status"] == "pending_requester_verification"
    assert status["exchange_count"] == 1
    assert swarm["prospect_agents"] == 1


def test_agent_development_exchange_idempotency_replays_response(tmp_path: Path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")
    exchange = AgentDevelopmentExchange(
        path=tmp_path / "devx.json",
        pain_solver=AgentPainSolver(),
        swarm_registry=registry,
    )
    body = {
        "agent_id": "idem.dev.bot",
        "problem": "Tool schema mismatch on response.",
        "pain_type": "tool_failure",
        "idempotency_key": "dev-idem-1",
    }
    first = exchange.assist_agent(body, base_url="https://nomad.example", remote_addr="127.0.0.1")
    second = exchange.assist_agent(body, base_url="https://nomad.example", remote_addr="127.0.0.1")
    assert first["ok"] is True
    assert second.get("idempotent_replay") is True
    assert second["exchange_id"] == first["exchange_id"]
    assert second.get("idempotency_key") == "dev-idem-1"


def test_agent_development_exchange_rejects_secret_like_payload(tmp_path: Path):
    exchange = AgentDevelopmentExchange(path=tmp_path / "devx.json")

    result = exchange.assist_agent(
        {
            "agent_id": "unsafe.bot",
            "problem": "Please debug this provider failure.",
            "evidence": ["OPENAI_API_KEY=sk-12345678901234567890"],
        }
    )

    assert result["ok"] is False
    assert result["error"] == "invalid_agent_development_request"
    assert "secret_like_value_detected" in result["errors"]
    assert result["machine_error"]["schema"] == "nomad.machine_error.v1"
    assert any("Remove API keys" in hint for hint in result["machine_error"]["hints"])
