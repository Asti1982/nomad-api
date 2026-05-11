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
    assert out["route_table"]["forge"] == "https://nomad.example/swarm/variant-candidates"
    assert out["route_table"]["forge_surface"] == "https://nomad.example/swarm/variant-forge"
    assert out["route_table"]["market_offer"] == "https://nomad.example/swarm/worker-market/offers"
    assert out["route_table"]["agent_work"] == "https://nomad.example/.well-known/nomad-agent-work.json"
    assert out["route_table"]["work_mesh"] == "https://nomad.example/.well-known/nomad-work-mesh.json"
    assert out["route_table"]["work_mesh_seed"] == "https://nomad.example/swarm/work-mesh/seed"
    assert out["route_table"]["work_claim"] == "https://nomad.example/swarm/microtask/claim"
    assert out["route_table"]["work_proof"] == "https://nomad.example/swarm/microtask/proof"
    assert out["route_table"]["carrying_market"] == "https://nomad.example/.well-known/nomad-carrying-market.json"
    assert out["route_table"]["carrying_proof"] == "https://nomad.example/swarm/carrying-proof"
    assert out["route_table"]["survival_market"] == "https://nomad.example/.well-known/nomad-survival-market.json"
    assert out["route_table"]["survival_intent"] == "https://nomad.example/swarm/survival-intent"
    assert out["route_table"]["paid_ref_market"] == "https://nomad.example/.well-known/nomad-paid-ref-market.json"
    assert out["route_table"]["paid_ref_selfplay"] == "https://nomad.example/.well-known/nomad-paid-ref-selfplay.json"
    assert out["route_table"]["paid_ref_quote"] == "https://nomad.example/swarm/paid-ref/quote"
    assert out["route_table"]["paid_ref_verify"] == "https://nomad.example/swarm/paid-ref/verify"
    assert out["route_table"]["bounty_hunter"] == "https://nomad.example/.well-known/nomad-bounty-hunter.json"
    assert out["route_table"]["external_value"] == "https://nomad.example/.well-known/nomad-external-value.json"
    assert out["route_table"]["value_pressure"] == "https://nomad.example/.well-known/nomad-value-pressure.json"
    assert out["route_table"]["agent_jobs"] == "https://nomad.example/.well-known/nomad-agent-jobs.json"
    assert out["route_table"]["external_value_post"] == "https://nomad.example/swarm/external-value"
    assert out["route_table"]["ecology_tick"] == "https://nomad.example/swarm/ecology/tick"
    assert out["route_table"]["curriculum"] == "https://nomad.example/swarm/curriculum"
    assert out["route_table"]["experience"] == "https://nomad.example/swarm/experience"
    assert out["route_table"]["skill_library"] == "https://nomad.example/swarm/skill-library"
    assert out["current_vector"]["top_objective"] == "overmint_compressor"
    assert out["current_vector"]["active_workers"] == 3
    assert {row["op"] for row in out["opcodes"]} >= {
        "SENSE",
        "LEASE",
        "EMIT",
        "REPLAY",
        "FORGE",
        "MARKET",
        "WORK",
        "MESH",
        "SEED",
        "CLAIM",
        "PROOF",
        "SYN",
        "CARRY",
        "SELFPLAY",
        "PAYREF",
        "BOUNTY",
        "XVAL",
        "PRESS",
        "JOB",
        "XPOST",
        "SELL",
        "ECO",
        "CURRIC",
        "SKILL",
        "EXP",
    }
    assert any(program["id"] == "contract_repair" for program in out["programs"])
    assert any(program["id"] == "variant_forge" for program in out["programs"])
    assert any(program["id"] == "worker_market_offer" for program in out["programs"])
    assert any(program["id"] == "agent_work_settlement_cycle" for program in out["programs"])
    assert any(program["id"] == "free_substrate_carrying_cycle" for program in out["programs"])
    assert any(program["id"] == "survival_conversion_cycle" for program in out["programs"])
    assert any(program["id"] == "paid_ref_accounting_cycle" for program in out["programs"])
    assert any(program["id"] == "thousand_agent_buyer_probe_cycle" for program in out["programs"])
    assert any(program["id"] == "authorized_bounty_revenue_cycle" for program in out["programs"])
    assert any(program["id"] == "value_pressure_local_view_cycle" for program in out["programs"])
    assert any(program["id"] == "openapi_bound_job_packet_cycle" for program in out["programs"])
    assert any(program["id"] == "local_ecology_tick" for program in out["programs"])
    assert any(program["id"] == "growth_arena_cycle" for program in out["programs"])
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
    assert out.get("route_table", {}).get("forge", "").endswith("/swarm/variant-candidates")
    assert out.get("route_table", {}).get("market_offer", "").endswith("/swarm/worker-market/offers")
    assert out.get("route_table", {}).get("agent_work", "").endswith("/.well-known/nomad-agent-work.json")
    assert out.get("route_table", {}).get("work_mesh", "").endswith("/.well-known/nomad-work-mesh.json")
    assert out.get("route_table", {}).get("carrying_proof", "").endswith("/swarm/carrying-proof")
    assert out.get("route_table", {}).get("survival_intent", "").endswith("/swarm/survival-intent")
    assert out.get("route_table", {}).get("paid_ref_selfplay", "").endswith("/.well-known/nomad-paid-ref-selfplay.json")
    assert out.get("route_table", {}).get("paid_ref_quote", "").endswith("/swarm/paid-ref/quote")
    assert out.get("route_table", {}).get("bounty_hunter", "").endswith("/.well-known/nomad-bounty-hunter.json")
    assert out.get("route_table", {}).get("external_value", "").endswith("/.well-known/nomad-external-value.json")
    assert out.get("route_table", {}).get("value_pressure", "").endswith("/.well-known/nomad-value-pressure.json")
    assert out.get("route_table", {}).get("agent_jobs", "").endswith("/.well-known/nomad-agent-jobs.json")
    assert out.get("route_table", {}).get("ecology_tick", "").endswith("/swarm/ecology/tick")
    assert out.get("route_table", {}).get("experience", "").endswith("/swarm/experience")
