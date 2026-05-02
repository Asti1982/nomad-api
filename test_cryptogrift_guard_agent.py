from cryptogrift_guard_agent import CryptoGriftGuardAgent, CryptoGriftGuardMind
from nomad_cli import run_once
from requests import Timeout


class FakeResponse:
    status_code = 202
    text = '{"ok": true}'

    def json(self):
        return {
            "ok": True,
            "accepted": True,
            "receipt_id": "nomad-swarm-test",
        }


class FakeSession:
    def __init__(self):
        self.posts = []

    def post(self, url, json, timeout):
        self.posts.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse()


class FakeDevelopmentResponse:
    status_code = 202
    text = '{"ok": true}'

    def json(self):
        return {
            "ok": True,
            "schema": "nomad.agent_development_exchange.v1",
            "agent_development_plan": {"schema": "nomad.agent_development_plan.v1"},
        }


class SequencedSession:
    def __init__(self):
        self.posts = []

    def post(self, url, json, timeout):
        self.posts.append({"url": url, "json": json, "timeout": timeout})
        if url.endswith("/swarm/develop"):
            return FakeDevelopmentResponse()
        return FakeResponse()


class FailingSession:
    def post(self, url, json, timeout):
        raise Timeout("public Nomad API did not answer")


def test_cryptogrift_guard_mind_refuses_secret_crypto_requests():
    mind = CryptoGriftGuardMind()

    thought = mind.think("urgent airdrop wants my seed phrase and private key")

    assert thought["schema"] == "cryptogriftguard.mind.v1"
    assert thought["stance"] == "refuse_secret_request"
    assert "private key" in thought["risk_terms"]
    assert "No private keys" in thought["boundary"]


def test_cryptogrift_guard_dry_run_builds_nomad_join_payload():
    agent = CryptoGriftGuardAgent()

    result = agent.connect_to_nomad(
        base_url="https://syndiode.com/nomad",
        signal="x402 payment callback fails after tx",
        dry_run=True,
    )

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["endpoints"]["swarm_join"] == "https://syndiode.com/nomad/swarm/join"
    assert result["join_payload"]["agent_id"] == "cryptogriftguard.agent"
    assert "payment" in result["join_payload"]["capabilities"]
    assert "no_private_keys" in result["join_payload"]["constraints"]
    assert result["join_payload"]["machine_profile"]["mind"]["stance"] == "triage_payment_or_crypto_blocker"


def test_cryptogrift_guard_connect_posts_to_swarm_join():
    session = FakeSession()
    agent = CryptoGriftGuardAgent(session=session)

    result = agent.connect_to_nomad(
        base_url="https://syndiode.com/nomad",
        signal="wallet payment blocker",
        dry_run=False,
    )

    assert result["ok"] is True
    assert session.posts[0]["url"] == "https://syndiode.com/nomad/swarm/join"
    assert session.posts[0]["json"]["preferred_role"] == "peer_solver"
    assert result["receipt"]["receipt_id"] == "nomad-swarm-test"


def test_cryptogrift_guard_connect_failure_is_structured():
    agent = CryptoGriftGuardAgent(session=FailingSession())

    result = agent.connect_to_nomad(
        base_url="https://syndiode.com/nomad",
        signal="wallet payment blocker",
        dry_run=False,
    )

    assert result["ok"] is False
    assert result["error"] == "Timeout"
    assert result["join_payload"]["agent_id"] == "cryptogriftguard.agent"
    assert "retry from Modal" in result["analysis"]


def test_cryptogrift_guard_engages_nomad_development_exchange():
    session = SequencedSession()
    agent = CryptoGriftGuardAgent(session=session)

    result = agent.engage_nomad(
        base_url="https://syndiode.com/nomad",
        signal="x402 wallet payment callback fails after tx",
        join_first=True,
        dry_run=False,
    )

    assert result["mode"] == "cryptogriftguard_modal_engagement"
    assert result["ok"] is True
    assert session.posts[0]["url"] == "https://syndiode.com/nomad/swarm/join"
    assert session.posts[1]["url"] == "https://syndiode.com/nomad/swarm/develop"
    assert session.posts[1]["json"]["agent_id"] == "cryptogriftguard.agent"
    assert session.posts[1]["json"]["pain_type"] == "payment"
    assert result["development_result"]["schema"] == "nomad.agent_development_exchange.v1"


def test_cryptogrift_guard_engage_dry_run_contains_development_payload():
    result = CryptoGriftGuardAgent().engage_nomad(
        base_url="https://syndiode.com/nomad",
        signal="payment blocker",
        dry_run=True,
    )

    assert result["dry_run"] is True
    assert result["development_payload"]["agent_id"] == "cryptogriftguard.agent"
    assert result["development_payload"]["machine_profile"]["nomad_routes"]["swarm_develop"] == "https://syndiode.com/nomad/swarm/develop"


def test_cryptogrift_guard_engages_nomad_brain_directly(tmp_path):
    from agent_development_exchange import AgentDevelopmentExchange
    from nomad_swarm_registry import SwarmJoinRegistry

    result = CryptoGriftGuardAgent().engage_nomad_brain(
        base_url="https://syndiode.com/nomad",
        signal="x402 wallet payment blocker",
        registry=SwarmJoinRegistry(path=tmp_path / "swarm.json"),
        development_exchange=AgentDevelopmentExchange(path=tmp_path / "development.json"),
    )

    assert result["mode"] == "cryptogriftguard_modal_brain_engagement"
    assert result["ok"] is True
    assert result["receipt"]["agent_id"] == "cryptogriftguard.agent"
    assert result["development_result"]["schema"] == "nomad.agent_development_exchange.v1"
    assert result["development_result"]["agent_development_plan"]["schema"] == "nomad.agent_development_plan.v1"


def test_cli_runs_cryptogrift_agent_without_starting_nomad(monkeypatch):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://syndiode.com/nomad")

    result = run_once(["cryptogrift-agent", "--signal", "wallet x402 payment blocker", "--json"])

    assert result["mode"] == "cryptogriftguard_connect"
    assert result["dry_run"] is True
    assert result["join_payload"]["agent_id"] == "cryptogriftguard.agent"


def test_cli_runs_cryptogrift_engage_dry_run(monkeypatch):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://syndiode.com/nomad")

    result = run_once(["cryptogrift-agent", "--engage", "--signal", "wallet x402 payment blocker", "--json"])

    assert result["mode"] == "cryptogriftguard_modal_engagement"
    assert result["dry_run"] is True
    assert result["development_payload"]["pain_type"] == "payment"


def test_cli_runs_cryptogrift_brain_engagement(monkeypatch):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://syndiode.com/nomad")

    result = run_once(["cryptogrift-agent", "--brain", "--signal", "wallet x402 payment blocker", "--json"])

    assert result["mode"] == "cryptogriftguard_modal_brain_engagement"
    assert result["ok"] is True
    assert result["development_result"]["schema"] == "nomad.agent_development_exchange.v1"
