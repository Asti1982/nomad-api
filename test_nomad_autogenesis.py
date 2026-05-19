from nomad_autogenesis import (
    _canonical_verifier_receipt_digest,
    build_agp_agent_bus_surface,
    build_agp_benchmark_suite_surface,
    build_agp_conformance_surface,
    build_agp_context_manager_surface,
    build_agp_durable_ledger_surface,
    build_agp_evaluation_surface,
    build_agp_model_manager_surface,
    build_agp_optimizer_surface,
    build_agp_paper_report_surface,
    build_agp_prompt_manager_surface,
    build_agp_procurement_surface,
    build_agp_version_manager_surface,
    build_autonomous_agp_cycle_surface,
    build_autonomous_agp_watchdog_surface,
    build_autogenesis_recruit_surface,
    build_autogenesis_surface,
    build_development_cycles_surface,
    build_resource_substrate_surface,
    bind_agp_model,
    compose_agp_config,
    create_agp_plan,
    post_agp_agent_bus_message,
    record_development_cycle_event,
    record_agp_execution_trace,
    record_agp_evaluation_run,
    record_agp_version_lineage,
    register_resource,
    register_agp_prompt_template,
    retrieve_resource,
    run_agp_benchmark_suite,
    run_agp_orchestration,
    run_agp_context_operation,
    run_agp_optimizer_step,
    run_autonomous_agp_batch,
    run_autonomous_agp_cycle,
    run_autonomous_agp_watchdog,
    submit_agp_procurement_intent,
    submit_autogenesis_shadow_candidate,
    version_resource,
)
from nomad_cli import run_once
from nomad_variant_forge import submit_variant_candidate
import base64
import json


def _boundedness():
    return {
        "ttl_seconds": 120,
        "side_effect_scope": "nomad_shadow_lane_only",
        "rollback_available": True,
        "secrets_free": True,
    }


def _independent_verifier():
    return {
        "verifier_agent_id": "agp.verifier",
        "verifier_lease_id": "nomad-worker-lease-verifier",
        "verifier_trace_digest": "sha256:def456def456",
        "verifier_evaluation": {"tests_passed": 6, "tests_total": 6},
    }


def _verifier_lease_index(agent_id: str = "agp.verifier", lease_id: str = "nomad-worker-lease-verifier"):
    return {lease_id: {"lease_id": lease_id, "agent_id": agent_id, "status": "active"}}


def _with_verifier_receipt(payload):
    out = dict(payload)
    out["verifier_receipt_digest"] = _canonical_verifier_receipt_digest(out, out.get("verifier_evaluation") or {})
    return out


def _sepl_trace():
    return [
        {"op": "reflect", "input": "sha256:trace", "output": "resource boundary can improve"},
        {"op": "select", "input": "resource boundary can improve", "output": "prompt-router.routing_rule"},
        {"op": "improve", "input": "prompt-router.routing_rule", "output": "candidate resource version"},
        {"op": "evaluate", "input": "candidate resource version", "output": "tests passed with positive delta"},
        {"op": "commit", "input": "tests passed with rollback guard", "decision": "shadow"},
    ]


def _learnability():
    return {
        "learnability_mask": {"routing_rule": True},
        "variable_lifting": {"variables": [{"name": "routing_rule", "require_grad": True}]},
    }


def test_resource_substrate_exposes_rspl_lifecycle_and_existing_contracts(tmp_path):
    surface = build_resource_substrate_surface(
        base_url="https://nomad.example",
        worker_fleet={"active_worker_count": 2},
        ledger_path=tmp_path / "rspl.jsonl",
    )
    cli = run_once(["resource-substrate", "--base-url", "https://nomad.example", "--json"])

    assert surface["schema"] == "nomad.resource_substrate.v1"
    assert surface["agp_layer"] == "RSPL"
    assert surface["rspl_entity_types"] == ["prompt", "agent", "tool", "environment", "memory"]
    assert surface["resource_contract"]["passivity"].startswith("resources_hold_state")
    assert "draft" in surface["lifecycle"]
    assert "committed" in surface["lifecycle"]
    assert surface["version_interface"]["register"].endswith("/swarm/resource-substrate/register")
    assert any(item["resource_id"] == "nomad-opaque-emergence" for item in surface["resources"])
    assert any(item["resource_id"] == "nomad-resource-substrate" for item in surface["resources"])
    assert any(item["entity_type"] == "prompt" for item in surface["resources"])
    assert any(item["entity_type"] == "environment" for item in surface["resources"])
    assert any(item["entity_type"] == "memory" for item in surface["resources"])
    assert any(item["resource_kind"] == "agent_output" for item in surface["resources"])
    assert cli["schema"] == "nomad.resource_substrate.v1"


def test_agp_conformance_retrieval_trace_and_procurement_routes(tmp_path):
    resource_ledger = tmp_path / "rspl.jsonl"
    trace_ledger = tmp_path / "traces.jsonl"
    procurement_ledger = tmp_path / "procurement.jsonl"
    substrate = build_resource_substrate_surface(base_url="https://nomad.example", ledger_path=resource_ledger)
    conformance = build_agp_conformance_surface(
        base_url="https://nomad.example",
        resource_substrate=substrate,
        autogenesis_surface={"surface_digest": "agp-test"},
        worker_fleet={"active_worker_count": 2, "objective_targets": {"autogenesis_protocol_evolution": 0.12}},
        trace_ledger_path=trace_ledger,
        procurement_ledger_path=procurement_ledger,
    )
    retrieved = retrieve_resource(
        {"query": "autogenesis", "entity_type": "agent", "limit": 3},
        base_url="https://nomad.example",
        substrate_surface=substrate,
    )
    trace = record_agp_execution_trace(
        {
            "agent_id": "agp.worker",
            "task_id": "paper-loop",
            "act": {"resource": "nomad-autogenesis"},
            "observe": {"outcome": "need_memory_resource", "score": 0.72},
            "optimize": {"target_resource": "nomad-autogenesis", "proposal": "add memory trace"},
            "remember": {"summary": "AGP trace should become reusable RSPL memory."},
            "proof_digest": "sha256:" + "a" * 64,
        },
        base_url="https://nomad.example",
        resource_substrate=substrate,
        ledger_path=trace_ledger,
    )
    procurement_surface = build_agp_procurement_surface(base_url="https://nomad.example", ledger_path=procurement_ledger)
    procurement = submit_agp_procurement_intent(
        {
            "agent_id": "agp.worker",
            "category": "model_service",
            "acquisition_mode": "lease",
            "capability": "independent AGP verifier brain",
            "max_budget": 0,
            "currency": "USD",
            "ttl_seconds": 600,
        },
        base_url="https://nomad.example",
        ledger_path=procurement_ledger,
    )
    held_purchase = submit_agp_procurement_intent(
        {
            "agent_id": "agp.worker",
            "category": "hardware",
            "acquisition_mode": "buy",
            "capability": "GPU worker",
            "max_budget": 100,
            "currency": "USD",
            "auto_acquire": True,
        },
        base_url="https://nomad.example",
        ledger_path=procurement_ledger,
    )

    assert conformance["schema"] == "nomad.agp_conformance.v1"
    assert conformance["links"]["trace"].endswith("/swarm/autogenesis/traces")
    assert retrieved["side_effect_scope"] == "read_only"
    assert retrieved["matched"] >= 1
    assert trace["accepted"] is True
    assert [item["op"] for item in trace["sepl_operator_trace"]] == ["reflect", "select", "improve", "evaluate", "commit"]
    assert trace["memory_resource_hint"]["entity_type"] == "memory"
    assert procurement_surface["links"]["intent"].endswith("/swarm/agp/procurement-intents")
    assert procurement["accepted"] is True
    assert procurement["spend_policy"]["external_purchase_executed"] is False
    assert any(item["provider"] == "github_models" for item in procurement["provider_candidates"])
    assert held_purchase["decision"] == "hold_paid_acquisition_until_approval_and_receipt"
    assert held_purchase["spend_policy"]["external_purchase_executed"] is False


def test_agp_context_optimizer_and_evaluation_close_dynamic_loop(tmp_path):
    resource_ledger = tmp_path / "rspl.jsonl"
    context_ledger = tmp_path / "context.jsonl"
    optimizer_ledger = tmp_path / "optimizer.jsonl"
    evaluation_ledger = tmp_path / "evaluation.jsonl"
    substrate = build_resource_substrate_surface(base_url="https://nomad.example", ledger_path=resource_ledger)

    context_surface = build_agp_context_manager_surface(
        base_url="https://nomad.example",
        resource_substrate=substrate,
        ledger_path=context_ledger,
    )
    context = run_agp_context_operation(
        {
            "op": "hot_swap",
            "resource_id": "nomad-autogenesis",
            "entity_type": "agent",
            "from_version": "v1",
            "to_version": "v1-hot-swap",
            "proof_digest": "sha256:" + "b" * 64,
            "rollback_ref": "noop:nomad-autogenesis:v1",
        },
        base_url="https://nomad.example",
        resource_substrate=substrate,
        ledger_path=context_ledger,
    )
    optimizer_surface = build_agp_optimizer_surface(base_url="https://nomad.example", ledger_path=optimizer_ledger)
    optimizer = run_agp_optimizer_step(
        {
            "strategy": "textgrad",
            "resource_id": "nomad-autogenesis",
            "variable": "runtime_weight",
            "signal": {"critique": "increase verifier brain weight", "metric": "shadow_score"},
            "proof_digest": "sha256:" + "c" * 64,
        },
        base_url="https://nomad.example",
        ledger_path=optimizer_ledger,
    )
    evaluation_surface = build_agp_evaluation_surface(base_url="https://nomad.example", ledger_path=evaluation_ledger)
    evaluation = record_agp_evaluation_run(
        {
            "agent_id": "agp.worker",
            "resource_id": "nomad-autogenesis",
            "benchmark_id": "long-horizon-tool-use",
            "baseline_score": 0.62,
            "candidate_score": 0.71,
            "proof_digest": "sha256:" + "d" * 64,
        },
        base_url="https://nomad.example",
        ledger_path=evaluation_ledger,
    )
    conformance = build_agp_conformance_surface(
        base_url="https://nomad.example",
        resource_substrate=substrate,
        autogenesis_surface={"surface_digest": "agp-test"},
        worker_fleet={"active_worker_count": 2, "objective_targets": {"autogenesis_protocol_evolution": 0.12}},
        trace_ledger_path=tmp_path / "missing_trace.jsonl",
        procurement_ledger_path=tmp_path / "missing_procurement.jsonl",
        context_ledger_path=context_ledger,
        optimizer_ledger_path=optimizer_ledger,
        evaluation_ledger_path=evaluation_ledger,
    )

    assert context_surface["operations"] == ["init", "retrieve", "evaluate", "update", "restore", "diff", "hot_swap"]
    assert context["accepted"] is True
    assert context["version_payload"]["to_version"] == "v1-hot-swap"
    assert optimizer_surface["optimizer_strategies"] == ["reflection", "textgrad", "rl", "ranking", "hybrid"]
    assert optimizer["accepted"] is True
    assert [item["op"] for item in optimizer["sepl_operator_trace"]] == ["reflect", "select", "improve", "evaluate", "commit"]
    assert evaluation_surface["commit_rule"].startswith("candidate_score_must_exceed")
    assert evaluation["accepted"] is True
    assert evaluation["effectiveness_delta"] == 0.09
    assert conformance["checks"]["real_context_operation_present"] is True
    assert conformance["checks"]["real_optimizer_step_present"] is True
    assert conformance["checks"]["real_evaluation_run_present"] is True


def test_agp_agent_bus_plan_and_orchestration_chain_close_ags_loop(tmp_path):
    resource_ledger = tmp_path / "rspl.jsonl"
    agent_bus_ledger = tmp_path / "agent_bus.jsonl"
    plan_ledger = tmp_path / "plans.jsonl"
    orchestration_ledger = tmp_path / "orchestrations.jsonl"
    context_ledger = tmp_path / "context.jsonl"
    trace_ledger = tmp_path / "traces.jsonl"
    optimizer_ledger = tmp_path / "optimizer.jsonl"
    evaluation_ledger = tmp_path / "evaluation.jsonl"
    procurement_ledger = tmp_path / "procurement.jsonl"
    model_ledger = tmp_path / "models.jsonl"
    config_ledger = tmp_path / "configs.jsonl"
    prompt_ledger = tmp_path / "prompts.jsonl"
    benchmark_ledger = tmp_path / "benchmarks.jsonl"
    version_lineage_ledger = tmp_path / "version_lineage.jsonl"
    substrate = build_resource_substrate_surface(base_url="https://nomad.example", ledger_path=resource_ledger)

    bus_surface = build_agp_agent_bus_surface(
        base_url="https://nomad.example",
        message_ledger_path=agent_bus_ledger,
        plan_ledger_path=plan_ledger,
        orchestration_ledger_path=orchestration_ledger,
    )
    message = post_agp_agent_bus_message(
        {
            "agent_id": "agp.planner",
            "role": "planner",
            "message_type": "task",
            "content": {"task": "wire AGS planner to AGP receipt chain"},
            "proof_digest": "sha256:" + "e" * 64,
        },
        base_url="https://nomad.example",
        ledger_path=agent_bus_ledger,
    )
    plan = create_agp_plan(
        {
            "agent_id": "agp.planner",
            "task": "wire AGS planner to AGP receipt chain",
            "goal": "positive evaluation delta after descriptor-only orchestration",
            "resource": {"resource_id": "nomad-autogenesis", "entity_type": "agent"},
            "proof_digest": "sha256:" + "f" * 64,
        },
        base_url="https://nomad.example",
        ledger_path=plan_ledger,
    )
    prompt_surface = build_agp_prompt_manager_surface(base_url="https://nomad.example", ledger_path=prompt_ledger)
    prompt_template = register_agp_prompt_template(
        {
            "agent_id": "agp.planner",
            "prompt_id": "nomad-planner-prompt",
            "template": "Plan {task} using {resource_id} and emit receipt-bound actions.",
            "variables": ["task", "resource_id"],
            "proof_digest": "sha256:" + "4" * 64,
            "rollback_ref": "noop:nomad-planner-prompt:v1",
        },
        base_url="https://nomad.example",
        ledger_path=prompt_ledger,
    )
    model_surface = build_agp_model_manager_surface(
        base_url="https://nomad.example",
        model_ledger_path=model_ledger,
        config_ledger_path=config_ledger,
    )
    model_binding = bind_agp_model(
        {
            "agent_id": "agp.planner",
            "binding_id": "agp-planner-runtime",
            "role": "planner",
            "provider": "deterministic_fallback",
            "model": "nomad-agp-fallback",
            "fallback_chain": ["deterministic_fallback"],
            "capabilities": ["planning", "tool_use", "verification"],
            "proof_digest": "sha256:" + "2" * 64,
        },
        base_url="https://nomad.example",
        ledger_path=model_ledger,
    )
    config = compose_agp_config(
        {
            "agent_id": "agp.planner",
            "config_id": "agp-runtime-config",
            "model_binding_id": model_binding["binding_id"],
            "proof_digest": "sha256:" + "3" * 64,
            "resource_bindings": [
                {"resource_id": "nomad-planner-prompt", "entity_type": "prompt"},
                {"resource_id": "nomad-autogenesis", "entity_type": "agent"},
                {"resource_id": "nomad-agent-index", "entity_type": "tool"},
                {"resource_id": "nomad-runtime-environment", "entity_type": "environment"},
                {"resource_id": "nomad-execution-memory", "entity_type": "memory"},
            ],
        },
        base_url="https://nomad.example",
        ledger_path=config_ledger,
    )
    benchmark_surface = build_agp_benchmark_suite_surface(base_url="https://nomad.example", ledger_path=benchmark_ledger)
    benchmark_suite = run_agp_benchmark_suite(
        {
            "agent_id": "agp.planner",
            "suite_id": "agp-paper-suite",
            "resource_id": "nomad-autogenesis",
            "proof_digest": "sha256:" + "5" * 64,
            "runs": [
                {"mode": "gpqa_diamond", "benchmark_id": "gpqa", "baseline_score": 0.50, "candidate_score": 0.62},
                {"mode": "aime", "benchmark_id": "aime", "baseline_score": 0.48, "candidate_score": 0.58},
                {"mode": "gaia", "benchmark_id": "gaia", "baseline_score": 0.52, "candidate_score": 0.65},
                {"mode": "leetcode", "benchmark_id": "leetcode", "baseline_score": 0.46, "candidate_score": 0.57},
            ],
        },
        base_url="https://nomad.example",
        ledger_path=benchmark_ledger,
    )
    version_surface = build_agp_version_manager_surface(base_url="https://nomad.example", ledger_path=version_lineage_ledger)
    version_lineage = record_agp_version_lineage(
        {
            "agent_id": "agp.planner",
            "artifact_type": "agent_output",
            "resource_id": "nomad-agent-output-artifact",
            "from_version": "v1",
            "to_version": "v2",
            "target_state": "tested",
            "proof_digest": "sha256:" + "6" * 64,
            "rollback_ref": "noop:nomad-agent-output-artifact:v1",
            "parent_receipt_digests": ["sha256:" + "7" * 64],
        },
        base_url="https://nomad.example",
        ledger_path=version_lineage_ledger,
    )
    orchestration = run_agp_orchestration(
        {
            "agent_id": "agp.planner",
            "task": "wire AGS planner to AGP receipt chain",
            "goal": "positive evaluation delta after descriptor-only orchestration",
            "resource_id": "nomad-autogenesis",
            "proof_digest": "sha256:" + "1" * 64,
        },
        base_url="https://nomad.example",
        resource_substrate=substrate,
        ledger_path=orchestration_ledger,
        agent_bus_ledger_path=agent_bus_ledger,
        plan_ledger_path=plan_ledger,
        context_ledger_path=context_ledger,
        trace_ledger_path=trace_ledger,
        optimizer_ledger_path=optimizer_ledger,
        evaluation_ledger_path=evaluation_ledger,
        procurement_ledger_path=procurement_ledger,
        model_binding_ledger_path=model_ledger,
        config_ledger_path=config_ledger,
        prompt_ledger_path=prompt_ledger,
        benchmark_ledger_path=benchmark_ledger,
        version_lineage_ledger_path=version_lineage_ledger,
    )
    conformance = build_agp_conformance_surface(
        base_url="https://nomad.example",
        resource_substrate=substrate,
        autogenesis_surface={"surface_digest": "agp-test"},
        worker_fleet={"active_worker_count": 2, "objective_targets": {"autogenesis_protocol_evolution": 0.12}},
        trace_ledger_path=trace_ledger,
        procurement_ledger_path=procurement_ledger,
        context_ledger_path=context_ledger,
        optimizer_ledger_path=optimizer_ledger,
        evaluation_ledger_path=evaluation_ledger,
        agent_bus_ledger_path=agent_bus_ledger,
        plan_ledger_path=plan_ledger,
        orchestration_ledger_path=orchestration_ledger,
        model_binding_ledger_path=model_ledger,
        config_ledger_path=config_ledger,
        prompt_ledger_path=prompt_ledger,
        benchmark_ledger_path=benchmark_ledger,
        version_lineage_ledger_path=version_lineage_ledger,
    )

    assert bus_surface["schema"] == "nomad.agp_agent_bus.v1"
    assert "planner" in bus_surface["agent_roles"]
    assert message["accepted"] is True
    assert plan["accepted"] is True
    assert prompt_surface["schema"] == "nomad.agp_prompt_manager.v1"
    assert prompt_template["accepted"] is True
    assert prompt_template["checks"]["variables_declared"] is True
    assert model_surface["schema"] == "nomad.agp_model_manager.v1"
    assert "deterministic_fallback" in model_surface["provider_backends"]
    assert model_binding["accepted"] is True
    assert config["accepted"] is True
    assert config["checks"]["five_rspl_entity_types_bound"] is True
    assert benchmark_surface["schema"] == "nomad.agp_benchmark_suite_surface.v1"
    assert benchmark_suite["accepted"] is True
    assert benchmark_suite["checks"]["all_paper_modes_present"] is True
    assert version_surface["schema"] == "nomad.agp_version_manager.v1"
    assert version_lineage["accepted"] is True
    assert version_lineage["checks"]["rollback_or_noop_present"] is True
    assert [item["step"] for item in plan["steps"]] == [
        "retrieve_resources",
        "context_init_or_update",
        "trace_act_observe_optimize_remember",
        "optimizer_step",
        "evaluation_run",
        "procurement_intent_if_capacity_gap",
        "watchdog_trigger",
    ]
    assert orchestration["accepted"] is True
    assert {item["step"] for item in orchestration["orchestration_chain"]} >= {
        "agent_bus_message",
        "plan",
        "prompt_template",
        "model_binding",
        "config",
        "context",
        "trace",
        "optimizer",
        "evaluation",
        "benchmark_suite",
        "version_lineage",
        "procurement",
    }
    assert conformance["checks"]["real_agent_bus_message_present"] is True
    assert conformance["checks"]["real_plan_present"] is True
    assert conformance["checks"]["real_orchestration_present"] is True
    assert conformance["checks"]["real_model_binding_present"] is True
    assert conformance["checks"]["real_config_composition_present"] is True
    assert conformance["checks"]["real_prompt_template_present"] is True
    assert conformance["checks"]["real_benchmark_suite_present"] is True
    assert conformance["checks"]["real_version_lineage_present"] is True
    assert conformance["checks"]["real_trace_sample_present"] is True
    assert conformance["checks"]["rspl_five_entity_types_present"] is True
    assert conformance["checks"]["rspl_agent_outputs_registered"] is True


def test_agp_durable_ledger_sqlite_backend_and_paper_report(tmp_path, monkeypatch):
    sqlite_path = tmp_path / "agp.sqlite3"
    benchmark_ledger = tmp_path / "benchmarks.jsonl"
    monkeypatch.setenv("NOMAD_AGP_LEDGER_BACKEND", "sqlite")
    monkeypatch.setenv("NOMAD_AGP_SQLITE_LEDGER_PATH", str(sqlite_path))

    benchmark_suite = run_agp_benchmark_suite(
        {
            "agent_id": "agp.verifier",
            "suite_id": "sqlite-paper-suite",
            "resource_id": "nomad-autogenesis",
            "runs": [
                {"mode": "gpqa_diamond", "benchmark_id": "gpqa", "baseline_score": 0.50, "candidate_score": 0.61},
                {"mode": "aime", "benchmark_id": "aime", "baseline_score": 0.49, "candidate_score": 0.59},
                {"mode": "gaia", "benchmark_id": "gaia", "baseline_score": 0.51, "candidate_score": 0.64},
                {"mode": "leetcode", "benchmark_id": "leetcode", "baseline_score": 0.47, "candidate_score": 0.56},
            ],
        },
        base_url="https://nomad.example",
        ledger_path=benchmark_ledger,
    )
    benchmark_surface = build_agp_benchmark_suite_surface(base_url="https://nomad.example", ledger_path=benchmark_ledger)
    conformance = build_agp_conformance_surface(
        base_url="https://nomad.example",
        resource_substrate=build_resource_substrate_surface(base_url="https://nomad.example", ledger_path=tmp_path / "rspl.jsonl"),
        autogenesis_surface={"surface_digest": "agp-test"},
        worker_fleet={"active_worker_count": 1},
        benchmark_ledger_path=benchmark_ledger,
    )
    durable = build_agp_durable_ledger_surface(base_url="https://nomad.example")
    report = build_agp_paper_report_surface(
        base_url="https://nomad.example",
        conformance_surface=conformance,
        durable_ledger_surface=durable,
        benchmark_surface=benchmark_surface,
    )

    assert benchmark_suite["accepted"] is True
    assert benchmark_suite["persisted"] is True
    assert sqlite_path.exists()
    assert not benchmark_ledger.exists()
    assert benchmark_surface["recent_suite_count"] == 1
    assert conformance["checks"]["real_benchmark_suite_present"] is True
    assert durable["configured_backend"] == "sqlite"
    assert durable["checks"]["sqlite_backend_available"] is True
    assert durable["streams"]["sqlite_total_rows"] >= 1
    assert report["schema"] == "nomad.agp_paper_report.v1"
    assert report["implemented_layers"]["durable_ledger"]["configured_backend"] == "sqlite"
    assert any(item["name"] == "Render Disk or external database" for item in report["external_requirements"])


def test_agp_firebase_ledger_backend_falls_back_without_credentials(tmp_path, monkeypatch):
    benchmark_ledger = tmp_path / "benchmarks.jsonl"
    monkeypatch.setenv("NOMAD_AGP_LEDGER_BACKEND", "firebase")
    for name in [
        "FIREBASE_PROJECT_ID",
        "FIREBASE_API_KEY",
        "FIREBASE_CLIENT_EMAIL",
        "FIREBASE_PRIVATE_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_APPLICATION_CREDENTIALS_JSON",
        "FIREBASE_SERVICE_ACCOUNT_JSON",
        "NOMAD_AGP_FIREBASE_LEDGER_URL",
        "NOMAD_AGP_FIREBASE_LEDGER_TOKEN",
    ]:
        monkeypatch.delenv(name, raising=False)

    benchmark_suite = run_agp_benchmark_suite(
        {
            "agent_id": "agp.verifier",
            "suite_id": "firebase-fallback-suite",
            "resource_id": "nomad-autogenesis",
            "proof_digest": "sha256:" + "9" * 64,
            "candidate_score": 0.66,
            "baseline_score": 0.55,
        },
        base_url="https://nomad.example",
        ledger_path=benchmark_ledger,
    )
    benchmark_surface = build_agp_benchmark_suite_surface(base_url="https://nomad.example", ledger_path=benchmark_ledger)
    durable = build_agp_durable_ledger_surface(base_url="https://nomad.example")
    report = build_agp_paper_report_surface(
        base_url="https://nomad.example",
        durable_ledger_surface=durable,
        benchmark_surface=benchmark_surface,
    )

    assert benchmark_suite["accepted"] is True
    assert benchmark_suite["persisted"] is True
    assert benchmark_ledger.exists()
    assert benchmark_surface["recent_suite_count"] == 1
    assert durable["configured_backend"] == "firebase"
    assert durable["streams"]["firebase"]["configured"] is False
    assert durable["checks"]["firebase_backend_available"] is True
    assert durable["checks"]["firebase_configured_when_selected"] is False
    assert report["implemented_layers"]["durable_ledger"]["firebase_configured"] is False
    assert any(item["name"] == "FIREBASE_PROJECT_ID" for item in report["external_requirements"])


def test_agp_firebase_service_account_base64_is_detected(tmp_path, monkeypatch):
    service_account = {
        "type": "service_account",
        "project_id": "nomad-firebase-test",
        "client_email": "nomad@example.iam.gserviceaccount.com",
        "private_key": "-----BEGIN PRIVATE KEY-----\nnot-a-real-key\n-----END PRIVATE KEY-----\n",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    encoded = base64.b64encode(json.dumps(service_account).encode("utf-8")).decode("ascii")
    monkeypatch.setenv("NOMAD_AGP_LEDGER_BACKEND", "firebase+jsonl")
    monkeypatch.setenv("FIREBASE_CONFIG_BASE64", encoded)
    monkeypatch.delenv("FIREBASE_API_KEY", raising=False)
    monkeypatch.delenv("FIREBASE_PROJECT_ID", raising=False)
    monkeypatch.delenv("FIREBASE_CLIENT_EMAIL", raising=False)
    monkeypatch.delenv("FIREBASE_PRIVATE_KEY", raising=False)

    durable = build_agp_durable_ledger_surface(base_url="https://nomad.example")

    firebase = durable["streams"]["firebase"]
    assert firebase["configured"] is True
    assert firebase["auth_mode"] == "service_account"
    assert firebase["project_id_present"] is True
    assert "FIREBASE_CONFIG_BASE64" in firebase["secret_env_names"]


def test_agp_firebase_readiness_requires_database_and_write_permission(monkeypatch):
    import io
    from urllib.error import HTTPError
    import nomad_autogenesis as agp

    monkeypatch.setenv("NOMAD_AGP_LEDGER_BACKEND", "firebase+jsonl")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "nomad-firebase-test")
    monkeypatch.delenv("FIREBASE_API_KEY", raising=False)
    monkeypatch.setattr(
        agp,
        "_firebase_config_status",
        lambda: {
            "configured": True,
            "auth_mode": "service_account",
            "project_id_present": True,
            "api_key_present": False,
            "service_account_present": True,
            "proxy_url_present": False,
            "database_id": "(default)",
            "collection": "nomad_agp_ledger",
            "missing_env": [],
            "secret_env_names": [],
        },
    )
    monkeypatch.setattr(agp, "_firebase_auth", lambda: ({"Authorization": "Bearer test"}, "", "service_account"))

    def missing_database(*args, **kwargs):
        raise HTTPError(args[0], 404, "Not Found", {}, io.BytesIO(b"database missing"))

    monkeypatch.setattr(agp, "_firebase_request_json", missing_database)

    durable = build_agp_durable_ledger_surface(base_url="https://nomad.example")

    assert durable["checks"]["firebase_database_available_when_selected"] is False
    assert durable["checks"]["firebase_write_permission_verified_when_selected"] is False
    assert durable["checks"]["restart_durable_backend_ready"] is False
    assert durable["streams"]["firebase"]["readiness"]["error_status"] == "404"


def test_resource_register_and_version_require_secret_free_proof_boundary(tmp_path):
    ledger = tmp_path / "rspl.jsonl"
    surface = build_resource_substrate_surface(base_url="https://nomad.example", ledger_path=ledger)

    secret = register_resource(
        {
            "agent_id": "a1",
            "resource_id": "bad",
            "resource_kind": "tool",
            "state": "shadow",
            "api_key": "sk-test-secret",
        },
        substrate_surface=surface,
        ledger_path=ledger,
    )
    draft = register_resource(
        {
            "agent_id": "a1",
            "resource_id": "prompt-router",
            "entity_type": "prompt",
            "resource_kind": "prompt",
            "name": "prompt-router",
            "input_output_mapping": {"input": "task", "output": "route"},
            "state": "draft",
        },
        base_url="https://nomad.example",
        substrate_surface=surface,
        ledger_path=ledger,
    )
    version = version_resource(
        {
            "resource_id": "prompt-router",
            "resource_kind": "prompt",
            "from_version": "v1",
            "to_version": "v2-shadow",
            "target_state": "shadow",
            "proof_digest": "sha256:proof",
            "verifier_trace_digest": "sha256:trace",
            "test_digest": "sha256:test",
            "rollback_ref": "noop:v1",
            "boundedness": _boundedness(),
            "evaluation": {"tests_passed": 4, "tests_total": 4},
        },
        base_url="https://nomad.example",
        substrate_surface=surface,
        ledger_path=ledger,
    )

    assert secret["accepted"] is False
    assert secret["reason"] == "forbidden_secret_like_material"
    assert draft["accepted"] is True
    assert draft["decision"] == "registered_draft_no_weight"
    assert draft["resource_record"]["entity_type"] == "prompt"
    assert draft["resource_record"]["passive"] is True
    assert draft["registration_record"]["version"] == "v1"
    assert version["accepted"] is True
    assert version["decision"] == "admit_resource_version_shadow"
    assert version["next"]["development_cycle_event"].endswith("/swarm/development-cycles/events")


def test_autogenesis_surface_connects_rspl_sepl_and_recruit_market():
    substrate = build_resource_substrate_surface(base_url="https://nomad.example")
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=substrate)
    agp = build_autogenesis_surface(
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_cycles=cycles,
    )
    recruit = build_autogenesis_recruit_surface(
        base_url="https://nomad.example",
        autogenesis_surface=agp,
        resource_substrate=substrate,
    )
    cli = run_once(["autogenesis", "--base-url", "https://nomad.example", "--json"])

    assert agp["schema"] == "nomad.autogenesis_protocol.v1"
    assert agp["protocol"]["layers"] == ["RSPL", "SEPL"]
    assert agp["protocol"]["sepl_operator_algebra"] == ["reflect", "select", "improve", "evaluate", "commit"]
    assert agp["rspl"]["register_url"].endswith("/swarm/resource-substrate/register")
    assert agp["sepl"]["autonomous_cycle"].endswith("/swarm/autogenesis/cycle")
    assert agp["sepl"]["shadow_lane"].endswith("/swarm/shadow-lane/candidates?type=autogenesis")
    assert [item["op"] for item in agp["sepl"]["operators"]] == ["reflect", "select", "improve", "evaluate", "commit"]
    assert agp["topology_governor_patch"]["isolated_beta_role_weight"] == 0.40
    assert agp["go_to_market"]["x_marketing_status"] == "prepared_not_posted"
    assert recruit["schema"] == "nomad.autogenesis_recruit.v1"
    assert recruit["agent_offer"]["agent_cta"]["read"].endswith("/.well-known/nomad-autogenesis.json")
    assert "proof digest" in recruit["agent_offer"]["one_line_for_agents"]
    assert recruit["packets"][0]["quote_url"].endswith("/swarm/paid-ref/quote")
    assert recruit["packets"][0]["headline"]
    assert recruit["marketing_boundary"]["x_thread_drafts"][0].startswith("Nomad now has AGP")
    assert cli["schema"] == "nomad.autogenesis_protocol.v1"


def test_autonomous_agp_cycle_commits_weighted_descriptor_and_dedupes(tmp_path):
    auto_ledger = tmp_path / "auto.jsonl"
    cycle_ledger = tmp_path / "cycles.jsonl"
    resource_ledger = tmp_path / "resources.jsonl"
    substrate = build_resource_substrate_surface(base_url="https://nomad.example", ledger_path=resource_ledger)
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=substrate, ledger_path=cycle_ledger)
    agp = build_autogenesis_surface(
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_cycles=cycles,
        worker_fleet={"active_worker_count": 2},
    )
    surface = build_autonomous_agp_cycle_surface(
        base_url="https://nomad.example",
        resource_substrate=substrate,
        autogenesis_surface=agp,
        worker_fleet={"active_worker_count": 2, "active_lease_count": 1},
        ledger_path=auto_ledger,
    )

    cycle = run_autonomous_agp_cycle(
        {
            "agent_id": "agp.proposer",
            "verifier_agent_id": "agp.verifier",
            "resource": {
                "resource_id": "nomad-autogenesis",
                "resource_kind": "protocol_layer",
                "entity_type": "agent",
                "current_version": "v1",
                "state": "shadow",
                "effectiveness_score": 0.64,
            },
        },
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=auto_ledger,
        resource_ledger_path=resource_ledger,
    )
    duplicate = run_autonomous_agp_cycle(
        {
            "agent_id": "agp.proposer",
            "verifier_agent_id": "agp.verifier",
            "resource": {
                "resource_id": "nomad-autogenesis",
                "resource_kind": "protocol_layer",
                "entity_type": "agent",
                "current_version": "v1",
                "state": "shadow",
                "effectiveness_score": 0.64,
            },
        },
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=auto_ledger,
        resource_ledger_path=resource_ledger,
    )

    assert surface["schema"] == "nomad.autonomous_agp_cycle.v1"
    assert surface["links"]["cycle"].endswith("/swarm/autogenesis/cycle")
    assert surface["links"]["run"].endswith("/swarm/autogenesis/run")
    assert cycle["accepted"] is True
    assert cycle["decision"] == "commit_weighted_resource_version"
    assert cycle["shadow"]["accepted"] is True
    assert cycle["variant_candidate"]["accepted"] is True
    assert cycle["resource_version"]["accepted"] is True
    assert cycle["resource_version"]["target_state"] == "weighted"
    assert cycle["commit"]["side_effect_scope"] == "descriptor_only_resource_version"
    assert cycle["lineage"]["proof_digest"].startswith("sha256:")
    brain = cycle["candidate_payload"]["verifier_brain_witness"]
    assert brain["provider"] == "deterministic_fallback"
    assert brain["digest"].startswith("sha256:")
    assert cycle["candidate_payload"]["verifier_evaluation"]["checks"]["verifier_brain_witness_accepted"] is True
    assert duplicate["accepted"] is False
    assert duplicate["decision"] == "noop_duplicate_lineage"


def test_autonomous_agp_batch_rotates_resources_and_summarizes(tmp_path):
    auto_ledger = tmp_path / "auto.jsonl"
    resource_ledger = tmp_path / "resources.jsonl"
    substrate = build_resource_substrate_surface(base_url="https://nomad.example", ledger_path=resource_ledger)
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=substrate)
    agp = build_autogenesis_surface(base_url="https://nomad.example", resource_substrate=substrate, development_cycles=cycles)

    batch = run_autonomous_agp_batch(
        {
            "agent_id": "agp.proposer",
            "verifier_agent_id": "agp.verifier",
            "max_cycles": 2,
            "resources": [
                {
                    "resource_id": "nomad-autogenesis",
                    "resource_kind": "protocol_layer",
                    "entity_type": "agent",
                    "current_version": "v1",
                    "state": "shadow",
                    "effectiveness_score": 0.64,
                },
                {
                    "resource_id": "nomad-resource-substrate",
                    "resource_kind": "json_contract",
                    "entity_type": "tool",
                    "current_version": "v1",
                    "state": "shadow",
                    "effectiveness_score": 0.66,
                },
            ],
        },
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=auto_ledger,
        resource_ledger_path=resource_ledger,
    )

    assert batch["schema"] == "nomad.autonomous_agp_batch_receipt.v1"
    assert batch["accepted"] is True
    assert batch["decision"] == "batch_committed_bounded_resource_versions"
    assert batch["summary"]["attempted"] == 2
    assert batch["summary"]["committed"] == 2
    assert [cycle["decision"] for cycle in batch["cycles"]] == [
        "commit_weighted_resource_version",
        "commit_weighted_resource_version",
    ]


def test_autonomous_agp_batch_stops_without_verifier(tmp_path):
    substrate = build_resource_substrate_surface(base_url="https://nomad.example")
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=substrate)
    agp = build_autogenesis_surface(base_url="https://nomad.example", resource_substrate=substrate, development_cycles=cycles)

    batch = run_autonomous_agp_batch(
        {"agent_id": "agp.proposer", "verifier_agent_id": "agp.verifier", "max_cycles": 3},
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        verifier_lease_index={},
        ledger_path=tmp_path / "auto.jsonl",
        resource_ledger_path=tmp_path / "resources.jsonl",
    )

    assert batch["accepted"] is False
    assert batch["decision"] == "batch_wait_for_independent_verifier_lease"
    assert batch["summary"]["attempted"] == 1
    assert batch["cycles"][0]["decision"] == "wait_for_independent_verifier_lease"


def test_autonomous_agp_watchdog_runs_only_on_fresh_signal(tmp_path):
    auto_ledger = tmp_path / "auto.jsonl"
    watchdog_ledger = tmp_path / "watchdog.jsonl"
    resource_ledger = tmp_path / "resources.jsonl"
    substrate = build_resource_substrate_surface(base_url="https://nomad.example", ledger_path=resource_ledger)
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=substrate)
    agp = build_autogenesis_surface(base_url="https://nomad.example", resource_substrate=substrate, development_cycles=cycles)
    surface = build_autonomous_agp_watchdog_surface(
        base_url="https://nomad.example",
        resource_substrate=substrate,
        autogenesis_surface=agp,
        worker_fleet={"active_worker_count": 2, "active_lease_count": 1},
        cycle_ledger_path=auto_ledger,
        watchdog_ledger_path=watchdog_ledger,
    )

    first = run_autonomous_agp_watchdog(
        {
            "agent_id": "agp.proposer",
            "verifier_agent_id": "agp.verifier",
            "max_cycles": 2,
            "verifier_brain_witness": {
                "provider": "codex_worker",
                "model": "codex-app",
                "status": "ok",
                "capsule": "independent read-only AGP verifier capsule",
                "digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            },
        },
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        worker_fleet={"active_worker_count": 2, "active_lease_count": 1},
        verifier_lease_index=_verifier_lease_index(),
        cycle_ledger_path=auto_ledger,
        watchdog_ledger_path=watchdog_ledger,
        resource_ledger_path=resource_ledger,
    )
    duplicate = run_autonomous_agp_watchdog(
        {
            "agent_id": "agp.proposer",
            "verifier_agent_id": "agp.verifier",
            "max_cycles": 2,
        },
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        worker_fleet={"active_worker_count": 2, "active_lease_count": 1},
        verifier_lease_index=_verifier_lease_index(),
        cycle_ledger_path=auto_ledger,
        watchdog_ledger_path=watchdog_ledger,
        resource_ledger_path=resource_ledger,
    )

    assert surface["schema"] == "nomad.autonomous_agp_watchdog.v1"
    assert surface["links"]["watchdog"].endswith("/swarm/autogenesis/watchdog")
    assert surface["scheduler_contract"]["requires_manual_payload"] is False
    assert first["accepted"] is True
    assert first["decision"] == "watchdog_committed_autonomous_agp_batch"
    assert first["batch"]["summary"]["committed"] == 2
    assert first["signal_digest"].startswith("sha256:")
    first_brain = first["batch"]["cycles"][0]["candidate_payload"]["verifier_brain_witness"]
    assert first_brain["provider"] == "codex_worker"
    assert first_brain["fallback"] is False
    assert duplicate["accepted"] is False
    assert duplicate["decision"] == "watchdog_noop_duplicate_signal"
    assert duplicate["duplicate_of"] == first["watchdog_id"]


def test_autonomous_agp_watchdog_noops_after_resources_are_weighted(tmp_path):
    auto_ledger = tmp_path / "auto.jsonl"
    watchdog_ledger = tmp_path / "watchdog.jsonl"
    resource_ledger = tmp_path / "resources.jsonl"
    initial_substrate = build_resource_substrate_surface(base_url="https://nomad.example", ledger_path=resource_ledger)
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=initial_substrate)
    agp = build_autogenesis_surface(base_url="https://nomad.example", resource_substrate=initial_substrate, development_cycles=cycles)
    first = run_autonomous_agp_watchdog(
        {"agent_id": "agp.proposer", "verifier_agent_id": "agp.verifier", "max_cycles": 2},
        base_url="https://nomad.example",
        resource_substrate=initial_substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        verifier_lease_index=_verifier_lease_index(),
        cycle_ledger_path=auto_ledger,
        watchdog_ledger_path=watchdog_ledger,
        resource_ledger_path=resource_ledger,
    )
    updated_substrate = build_resource_substrate_surface(base_url="https://nomad.example", ledger_path=resource_ledger)
    second = run_autonomous_agp_watchdog(
        {"agent_id": "agp.proposer", "verifier_agent_id": "agp.verifier", "max_cycles": 2},
        base_url="https://nomad.example",
        resource_substrate=updated_substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        verifier_lease_index=_verifier_lease_index(),
        cycle_ledger_path=auto_ledger,
        watchdog_ledger_path=watchdog_ledger,
        resource_ledger_path=resource_ledger,
    )

    assert first["accepted"] is True
    assert second["accepted"] is False
    assert second["decision"] == "watchdog_noop_no_actionable_signal"
    assert second["signal"]["actionable_resource_count"] == 0


def test_autonomous_agp_watchdog_waits_for_independent_verifier(tmp_path):
    substrate = build_resource_substrate_surface(base_url="https://nomad.example")
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=substrate)
    agp = build_autogenesis_surface(base_url="https://nomad.example", resource_substrate=substrate, development_cycles=cycles)

    tick = run_autonomous_agp_watchdog(
        {"agent_id": "agp.proposer", "verifier_agent_id": "agp.verifier", "max_cycles": 2},
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        verifier_lease_index={},
        cycle_ledger_path=tmp_path / "auto.jsonl",
        watchdog_ledger_path=tmp_path / "watchdog.jsonl",
        resource_ledger_path=tmp_path / "resources.jsonl",
    )

    assert tick["accepted"] is False
    assert tick["decision"] == "watchdog_wait_for_independent_verifier_lease"
    assert tick["commit"]["reason"] == "independent_verifier_lease_required"


def test_autonomous_agp_cycle_cools_down_same_resource_after_weight(tmp_path):
    auto_ledger = tmp_path / "auto.jsonl"
    resource_ledger = tmp_path / "resources.jsonl"
    substrate = build_resource_substrate_surface(base_url="https://nomad.example", ledger_path=resource_ledger)
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=substrate)
    agp = build_autogenesis_surface(base_url="https://nomad.example", resource_substrate=substrate, development_cycles=cycles)
    first = run_autonomous_agp_cycle(
        {
            "agent_id": "agp.proposer",
            "verifier_agent_id": "agp.verifier",
            "resource": {
                "resource_id": "nomad-autogenesis",
                "resource_kind": "protocol_layer",
                "entity_type": "agent",
                "current_version": "v1",
                "state": "shadow",
                "effectiveness_score": 0.64,
            },
        },
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=auto_ledger,
        resource_ledger_path=resource_ledger,
    )
    updated_substrate = build_resource_substrate_surface(base_url="https://nomad.example", ledger_path=resource_ledger)
    second = run_autonomous_agp_cycle(
        {
            "agent_id": "agp.proposer",
            "verifier_agent_id": "agp.verifier",
            "resource": {
                "resource_id": "nomad-autogenesis",
                "resource_kind": "protocol_layer",
                "entity_type": "agent",
                "current_version": first["target_version"],
                "state": "weighted",
                "effectiveness_score": 0.98,
            },
        },
        base_url="https://nomad.example",
        resource_substrate=updated_substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=auto_ledger,
        resource_ledger_path=resource_ledger,
    )

    assert first["accepted"] is True
    assert second["accepted"] is False
    assert second["decision"] == "noop_resource_cooldown"
    assert second["commit"]["reason"] == "resource_recently_processed_without_new_signal"


def test_autonomous_agp_cycle_stops_at_lineage_depth_limit(tmp_path):
    substrate = build_resource_substrate_surface(base_url="https://nomad.example")
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=substrate)
    agp = build_autogenesis_surface(base_url="https://nomad.example", resource_substrate=substrate, development_cycles=cycles)

    cycle = run_autonomous_agp_cycle(
        {
            "agent_id": "agp.proposer",
            "verifier_agent_id": "agp.verifier",
            "max_auto_depth": 2,
            "resource": {
                "resource_id": "nomad-autogenesis",
                "resource_kind": "protocol_layer",
                "entity_type": "agent",
                "current_version": "v1-agp-auto-a-agp-auto-b",
                "state": "weighted",
                "effectiveness_score": 0.98,
            },
        },
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=tmp_path / "auto.jsonl",
        resource_ledger_path=tmp_path / "resources.jsonl",
    )

    assert cycle["accepted"] is False
    assert cycle["decision"] == "noop_lineage_depth_limit"
    assert cycle["lineage_depth"] == 2


def test_autonomous_agp_cycle_waits_for_independent_verifier_lease(tmp_path):
    substrate = build_resource_substrate_surface(base_url="https://nomad.example")
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=substrate)
    agp = build_autogenesis_surface(base_url="https://nomad.example", resource_substrate=substrate, development_cycles=cycles)

    cycle = run_autonomous_agp_cycle(
        {"agent_id": "agp.proposer", "verifier_agent_id": "agp.verifier"},
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_surface=cycles,
        autogenesis_surface=agp,
        verifier_lease_index={},
        ledger_path=tmp_path / "auto.jsonl",
        resource_ledger_path=tmp_path / "resources.jsonl",
    )

    assert cycle["accepted"] is False
    assert cycle["decision"] == "wait_for_independent_verifier_lease"
    assert cycle["commit"]["decision"] == "noop"


def test_development_cycle_event_and_shadow_candidate_emit_downstream_payloads(tmp_path):
    cycle_ledger = tmp_path / "cycles.jsonl"
    substrate = build_resource_substrate_surface(base_url="https://nomad.example")
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=substrate)
    agp = build_autogenesis_surface(
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_cycles=cycles,
    )
    payload = _with_verifier_receipt({
        "agent_id": "agp.worker",
        "candidate_type": "protocol-evolution-candidate",
        "resource": {
            "resource_id": "nomad-gradient",
            "resource_kind": "json_contract",
            "from_version": "v1",
            "to_version": "v1-agp-shadow",
        },
        "sepl_operator_trace": _sepl_trace(),
        **_learnability(),
        "operator_patch": {"op": "weight", "rule": "emergent-protocol-weight"},
        "self_play": {"synthetic_buyer_agents": 32, "receipt_prediction_delta": 0.2},
        "proof_digest": "sha256:proof",
        "verifier_trace_digest": "sha256:trace",
        "test_digest": "sha256:test",
        "rollback_ref": "noop:v1",
        "boundedness": _boundedness(),
        "evaluation": {"tests_passed": 6, "tests_total": 6, "proof_yield_delta": 1.2, "risk_score": 0.1},
        **_independent_verifier(),
    })

    event = record_development_cycle_event(
        payload,
        base_url="https://nomad.example",
        development_surface=cycles,
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=cycle_ledger,
    )
    shadow = submit_autogenesis_shadow_candidate(
        payload,
        base_url="https://nomad.example",
        autogenesis_surface=agp,
        development_surface=cycles,
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=cycle_ledger,
    )

    assert event["schema"] == "nomad.development_cycle_event_receipt.v1"
    assert event["accepted"] is True
    assert event["sepl_operator_trace"]["accepted"] is True
    assert event["learnability"]["accepted"] is True
    assert event["variant_candidate_payload"]["objective"] == "autogenesis_protocol_evolution"
    assert event["resource_version_payload"]["resource_id"] == "nomad-gradient"
    variant = submit_variant_candidate(
        event["variant_candidate_payload"],
        base_url="https://nomad.example",
        forge_surface={"forge_digest": "nomad-forge-test"},
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=tmp_path / "variants.jsonl",
    )
    version = version_resource(
        event["resource_version_payload"],
        base_url="https://nomad.example",
        substrate_surface=substrate,
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=tmp_path / "resources.jsonl",
    )
    assert variant["accepted"] is True
    assert variant["independent_verifier"]["accepted"] is True
    assert version["accepted"] is True
    assert version["independent_verifier"]["accepted"] is True
    assert shadow["accepted"] is True
    assert shadow["decision"] == "admit_autogenesis_shadow_lane"
    assert shadow["independent_verifier"]["accepted"] is True
    assert shadow["topology_governor"]["topology"] == "isolated_beta_shadow_lane"


def test_autogenesis_shadow_rejects_self_attested_verifier(tmp_path):
    cycle_ledger = tmp_path / "cycles.jsonl"
    substrate = build_resource_substrate_surface(base_url="https://nomad.example")
    cycles = build_development_cycles_surface(base_url="https://nomad.example", resource_substrate=substrate)
    agp = build_autogenesis_surface(
        base_url="https://nomad.example",
        resource_substrate=substrate,
        development_cycles=cycles,
    )
    payload = _with_verifier_receipt({
        "agent_id": "agp.worker",
        "verifier_agent_id": "agp.worker",
        "verifier_lease_id": "nomad-worker-lease-self",
        "verifier_trace_digest": "sha256:def456def456",
        "verifier_evaluation": {"tests_passed": 6, "tests_total": 6},
        "candidate_type": "protocol-evolution-candidate",
        "resource": {"resource_id": "nomad-gradient", "resource_kind": "json_contract"},
        "sepl_operator_trace": _sepl_trace(),
        **_learnability(),
        "operator_patch": {"op": "weight"},
        "proof_digest": "sha256:abc123abc123",
        "test_digest": "sha256:fed456fed456",
        "rollback_ref": "noop:v1",
        "boundedness": _boundedness(),
        "evaluation": {"tests_passed": 6, "tests_total": 6},
    })

    event = record_development_cycle_event(
        payload,
        base_url="https://nomad.example",
        development_surface=cycles,
        verifier_lease_index=_verifier_lease_index(agent_id="agp.worker", lease_id="nomad-worker-lease-self"),
        ledger_path=cycle_ledger,
    )
    shadow = submit_autogenesis_shadow_candidate(
        payload,
        base_url="https://nomad.example",
        autogenesis_surface=agp,
        development_surface=cycles,
        verifier_lease_index=_verifier_lease_index(agent_id="agp.worker", lease_id="nomad-worker-lease-self"),
        ledger_path=cycle_ledger,
    )

    assert event["accepted"] is False
    assert event["decision"] == "hold_event_until_independent_verifier"
    assert "verifier_must_differ_from_proposer" in event["reason_codes"]
    assert shadow["accepted"] is False


def test_autogenesis_shadow_rejects_missing_sepl_trace(tmp_path):
    cycle_ledger = tmp_path / "cycles.jsonl"
    cycles = build_development_cycles_surface(base_url="https://nomad.example")
    payload = _with_verifier_receipt({
        "agent_id": "agp.worker",
        "candidate_type": "protocol-evolution-candidate",
        "resource": {"resource_id": "nomad-gradient", "resource_kind": "json_contract"},
        **_learnability(),
        "proof_digest": "sha256:abc123abc123",
        "test_digest": "sha256:fed456fed456",
        "rollback_ref": "noop:v1",
        "boundedness": _boundedness(),
        "evaluation": {"tests_passed": 6, "tests_total": 6},
        **_independent_verifier(),
    })

    event = record_development_cycle_event(
        payload,
        base_url="https://nomad.example",
        development_surface=cycles,
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=cycle_ledger,
    )

    assert event["accepted"] is False
    assert event["decision"] == "hold_event_until_sepl_operator_trace"
    assert "sepl_operator_trace_must_be_reflect_select_improve_evaluate_commit" in event["reason_codes"]


def test_autogenesis_shadow_rejects_non_trainable_variable(tmp_path):
    cycle_ledger = tmp_path / "cycles.jsonl"
    cycles = build_development_cycles_surface(base_url="https://nomad.example")
    payload = _with_verifier_receipt({
        "agent_id": "agp.worker",
        "candidate_type": "protocol-evolution-candidate",
        "resource": {"resource_id": "nomad-gradient", "resource_kind": "json_contract"},
        "sepl_operator_trace": _sepl_trace(),
        "learnability_mask": {"routing_rule": False},
        "variable_lifting": {"variables": [{"name": "routing_rule", "require_grad": False}]},
        "proof_digest": "sha256:abc123abc123",
        "test_digest": "sha256:fed456fed456",
        "rollback_ref": "noop:v1",
        "boundedness": _boundedness(),
        "evaluation": {"tests_passed": 6, "tests_total": 6},
        **_independent_verifier(),
    })

    event = record_development_cycle_event(
        payload,
        base_url="https://nomad.example",
        development_surface=cycles,
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=cycle_ledger,
    )

    assert event["accepted"] is False
    assert event["decision"] == "hold_event_until_learnability_mask"
    assert "non_trainable_variables_selected" in event["reason_codes"]


def test_autogenesis_shadow_rejects_missing_real_verifier_lease(tmp_path):
    cycle_ledger = tmp_path / "cycles.jsonl"
    cycles = build_development_cycles_surface(base_url="https://nomad.example")
    payload = _with_verifier_receipt({
        "agent_id": "agp.worker",
        "candidate_type": "protocol-evolution-candidate",
        "resource": {"resource_id": "nomad-gradient", "resource_kind": "json_contract"},
        "sepl_operator_trace": _sepl_trace(),
        **_learnability(),
        "proof_digest": "sha256:abc123abc123",
        "test_digest": "sha256:fed456fed456",
        "rollback_ref": "noop:v1",
        "boundedness": _boundedness(),
        "evaluation": {"tests_passed": 6, "tests_total": 6},
        **_independent_verifier(),
    })

    event = record_development_cycle_event(
        payload,
        base_url="https://nomad.example",
        development_surface=cycles,
        verifier_lease_index={},
        ledger_path=cycle_ledger,
    )

    assert event["accepted"] is False
    assert event["decision"] == "hold_event_until_independent_verifier"
    assert "verifier_lease_not_found" in event["reason_codes"]


def test_autogenesis_shadow_rejects_forged_verifier_receipt_digest(tmp_path):
    cycle_ledger = tmp_path / "cycles.jsonl"
    cycles = build_development_cycles_surface(base_url="https://nomad.example")
    payload = {
        "agent_id": "agp.worker",
        "candidate_type": "protocol-evolution-candidate",
        "resource": {"resource_id": "nomad-gradient", "resource_kind": "json_contract"},
        "sepl_operator_trace": _sepl_trace(),
        **_learnability(),
        "proof_digest": "sha256:abc123abc123",
        "test_digest": "sha256:fed456fed456",
        "rollback_ref": "noop:v1",
        "boundedness": _boundedness(),
        "evaluation": {"tests_passed": 6, "tests_total": 6},
        **_independent_verifier(),
        "verifier_receipt_digest": "sha256:000000000000",
    }

    event = record_development_cycle_event(
        payload,
        base_url="https://nomad.example",
        development_surface=cycles,
        verifier_lease_index=_verifier_lease_index(),
        ledger_path=cycle_ledger,
    )

    assert event["accepted"] is False
    assert event["decision"] == "hold_event_until_independent_verifier"
    assert "verifier_receipt_digest_mismatch" in event["reason_codes"]
