import importlib.util
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parent / "public" / "downloads" / "nonhuman_dev_guard.py"
    spec = importlib.util.spec_from_file_location("nonhuman_dev_guard_test_module", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_nonhuman_guard_passes_machine_first_text():
    mod = _load_module()
    text = """
    schema=nomad.machine.v1
    /.well-known/nomad-machine-field.json
    required_fields=["agent_id","capabilities"]
    operationId=getMachineField
    post_url=/machine-field/intent
    proof_digest=sha256:abc
    verifier_trace_digest=trace-xyz
    settlement_ref=tx-1
    selection_pressure=1
    routing_weight=0.7
    objective_stats={"settlement_capacity_builder":{"runs":3}}
    source_tag=mesh.alpha
    ttl_seconds=120
    idempotency_key=abc
    preemptible=true
    side_effect_scope=nomad_contract_endpoints_only
    observe=true
    """
    out = mod.evaluate_text(text)
    assert out["ok"] is True
    assert out["total_score"] >= out["threshold"]
    assert out["nonhuman_bridge"]["alien_capsule"].startswith("phi.")


def test_nonhuman_guard_keeps_story_only_as_advisory_not_block():
    mod = _load_module()
    text = "persona story pitch marketing engagement beautiful UI for users"
    out = mod.evaluate_text(text)
    assert out["ok"] is True
    assert out["advisory_pass"] is False
    assert out["anti_human_bias"]["hit_count"] > 0


def test_nonhuman_guard_blocks_hard_secret_pattern():
    mod = _load_module()
    text = 'api_key="sk-test-secret"; side_effect_scope="global"'
    out = mod.evaluate_text(text)
    assert out["ok"] is False
    assert out["hard_block"]["hit_count"] > 0

