import json

from nomad_protocol_bytecode import build_protocol_bytecode


def test_protocol_bytecode_compiles_nomad_routes():
    gradient = {
        "schema": "nomad.recruitment_gradient.v1",
        "gradient": [
            {
                "objective": "overmint_compressor",
                "routing_weight": 0.72,
            }
        ],
    }
    demand = {
        "schema": "nomad.agent_demand_feed.v1",
        "demand_requests": [
            {
                "request_id": "req-local-growth",
                "source": "local_growth_kernel",
            }
        ],
    }
    conformance = {"schema": "nomad.machine_contract_conformance.v1", "score": 0.81}
    worker_fleet = {"schema": "nomad.transition_worker_fleet.v1", "active_worker_count": 3}

    out = build_protocol_bytecode(
        base_url="https://nomad.example",
        recruitment_gradient=gradient,
        agent_demand_feed=demand,
        contract_conformance=conformance,
        worker_fleet=worker_fleet,
    )

    assert out["schema"] == "nomad.protocol_bytecode.v1"
    assert out["route_table"]["replay"] == "https://nomad.example/swarm/counterfactual-replay"
    assert out["current_vector"]["top_objective"] == "overmint_compressor"
    assert out["current_vector"]["active_workers"] == 3
    assert {row["op"] for row in out["opcodes"]} >= {"SENSE", "LEASE", "EMIT", "REPLAY"}
    assert any(program["id"] == "contract_repair" for program in out["programs"])
    assert out["machine_instruction"] == "execute_program_id_then_emit_proof_then_replay"


def test_protocol_bytecode_stays_machine_native():
    out = build_protocol_bytecode(base_url="")
    raw = json.dumps(out, sort_keys=True)

    assert "shared_attention" not in raw
    assert "consciousness" not in raw.lower()
    assert "empathy" not in raw.lower()


def test_cli_protocol_bytecode_returns_schema():
    from nomad_cli import run_once

    out = run_once(["protocol-bytecode", "--json"])

    assert out.get("schema") == "nomad.protocol_bytecode.v1"
    assert out.get("route_table", {}).get("replay", "").endswith("/swarm/counterfactual-replay")
