import json

from nomad_mcp import NomadMcpServer
from nomad_mcp_lab import (
    execution_gate,
    generate_svw_experiment,
    record_experiment_result,
    replay_svw_experiment,
)


def test_generate_and_replay_svw_experiment_is_falsifiable():
    experiment = generate_svw_experiment(
        objective="Reduce MCP retry waste for private tool calls.",
        candidate_action="Add schema-aware retry classification before public digest.",
        risk_budget="low",
    )

    assert experiment["schema"] == "nomad.svw_experiment.v1"
    assert experiment["intervention_class"] == "mcp_production"
    assert experiment["hypothesis_id"].startswith("hyp-")
    assert experiment["intervention"]["expected_svw_delta"] > 0
    assert "success_rule" in experiment["measurement_contract"]
    assert "failure_rule" in experiment["measurement_contract"]

    replay = replay_svw_experiment(experiment=experiment)
    assert replay["schema"] == "nomad.svw_experiment_replay.v1"
    assert replay["hypothesis_id"] == experiment["hypothesis_id"]
    assert replay["counterfactual"]["bounded_probe_delta_range"][1] > 0
    assert replay["failure_capture"]["record_negative_result"] is True


def test_execution_gate_requires_exact_hypothesis_approval():
    experiment = generate_svw_experiment(
        objective="Probe worker lease retry loss.",
        candidate_action="Run one low-risk worker cycle and compare retry loss.",
        risk_budget="low",
    )

    blocked = execution_gate(experiment=experiment, requested_action="run one worker cycle")
    assert blocked["allowed"] is False
    assert blocked["gate_status"] == "blocked_requires_approval"

    approved = execution_gate(
        experiment=experiment,
        requested_action="run one worker cycle",
        approval=experiment["approval"]["required_approval_token"],
    )
    assert approved["allowed"] is True
    assert approved["side_effect_performed"] is False


def test_record_experiment_result_appends_local_receipt(tmp_path):
    experiment = generate_svw_experiment(
        objective="Publish digest only if it improves inbound reuse.",
        candidate_action="Create public digest proposal.",
        risk_budget="proposal_only",
    )
    receipt = record_experiment_result(
        experiment=experiment,
        outcome="observed_failure",
        evidence="no inbound reuse, digest viewed once",
        svw_delta="-0.01",
        ledger_path=tmp_path / "lab.jsonl",
    )

    assert receipt["schema"] == "nomad.lab_experiment_record_receipt.v1"
    assert receipt["event"]["negative_result_value"] is True
    assert receipt["side_effect_performed"] is True
    rows = (tmp_path / "lab.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    assert json.loads(rows[0])["result_digest"] == receipt["event"]["result_digest"]


def test_mcp_exposes_private_lab_tools_and_resource(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_LAB_EXPERIMENT_LEDGER_PATH", str(tmp_path / "mcp-lab.jsonl"))
    server = NomadMcpServer(agent_factory=lambda: object())

    tools = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    tool_names = {tool["name"] for tool in tools["result"]["tools"]}
    assert "nomad_lab_state" in tool_names
    assert "nomad_agent_native_product" in tool_names
    assert "nomad_svw_state" in tool_names
    assert "nomad_external_value_state" in tool_names
    assert "nomad_generate_experiment" in tool_names
    assert "nomad_counterfactual_experiment_replay" in tool_names
    assert "nomad_lab_execution_gate" in tool_names
    assert "nomad_record_experiment_result" in tool_names

    generated = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "nomad_generate_experiment",
                "arguments": {
                    "objective": "Classify private MCP failures before retrying.",
                    "candidate_action": "Replay one failed tool call and record the outcome.",
                    "risk_budget": "low",
                },
            },
        }
    )
    body = generated["result"]["structuredContent"]
    assert body["schema"] == "nomad.svw_experiment.v1"
    assert body["nomad_wire_diag"]["tool_name"] == "nomad_generate_experiment"

    recorded = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "nomad_record_experiment_result",
                "arguments": {
                    "experiment_json": json.dumps(body),
                    "outcome": "inconclusive",
                    "evidence": "dry-run only",
                    "svw_delta": "0",
                },
            },
        }
    )
    assert recorded["result"]["structuredContent"]["event"]["outcome"] == "inconclusive"

    resource = server._read_resource({"uri": "nomad://private-mcp-lab"})
    lab = json.loads(resource["contents"][0]["text"])
    assert lab["schema"] == "nomad.private_mcp_lab.v1"
    assert "nomad-lab-readonly" in lab["profiles"]

    product_resource = server._read_resource({"uri": "nomad://agent-native-product"})
    product = json.loads(product_resource["contents"][0]["text"])
    assert product["schema"] == "nomad.agent_native_product.v1"
    assert "nomad-lab-execute" in product["private_mcp"]["profiles"]

    svw = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "nomad_svw_state", "arguments": {}},
        }
    )
    assert svw["result"]["structuredContent"]["schema"] == "nomad.swarm_verified_work.v1"
