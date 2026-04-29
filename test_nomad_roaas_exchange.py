from __future__ import annotations

from pathlib import Path

from nomad_market_patterns import ComputeLane, MarketPatternRegistry, PatternStatus
from nomad_predictive_router import PredictiveRouter
from nomad_roaas_exchange import RuntimePatternExchange
from nomad_runtime_identity import NodeIdentity, RuntimeTrustStore


def test_roaas_exchange_exports_and_imports_patterns(tmp_path: Path):
    source_registry = MarketPatternRegistry(registry_path=tmp_path / "source-patterns.json")
    source_router = PredictiveRouter(registry=source_registry, health_path=tmp_path / "source-health.json")
    for _ in range(6):
        source_router.record_outcome(
            lane=ComputeLane.LOCAL_OLLAMA,
            latency_ms=140,
            success=True,
            task_type="self_improvement_review",
            cost_usd=0.0,
        )

    source_exchange = RuntimePatternExchange(
        registry=source_registry,
        router=source_router,
        submission_log_path=tmp_path / "source-submissions.ndjson",
    )
    bundle = source_exchange.export_bundle(task_type="self_improvement_review")

    target_registry = MarketPatternRegistry(registry_path=tmp_path / "target-patterns.json")
    target_router = PredictiveRouter(registry=target_registry, health_path=tmp_path / "target-health.json")
    target_exchange = RuntimePatternExchange(
        registry=target_registry,
        router=target_router,
        submission_log_path=tmp_path / "target-submissions.ndjson",
    )
    receipt = target_exchange.import_bundle(
        {
            "bundle": bundle,
            "source": "nomadportable-node-a",
            "source_node": {"node_name": "node-a", "local_base_url": "http://127.0.0.1:8878"},
        },
        source="nomadportable-node-a",
        trust_level=PatternStatus.CANDIDATE,
    )

    assert receipt["ok"] is True
    assert receipt["import"]["imported"] >= 1
    imported = target_registry.all_for_task("self_improvement_review")
    assert imported
    assert imported[0].status == PatternStatus.CANDIDATE
    assert receipt["submission"]["source"] == "nomadportable-node-a"


def test_roaas_exchange_status_reports_submission_log(tmp_path: Path):
    registry = MarketPatternRegistry(registry_path=tmp_path / "patterns.json")
    router = PredictiveRouter(registry=registry, health_path=tmp_path / "health.json")
    exchange = RuntimePatternExchange(
        registry=registry,
        router=router,
        submission_log_path=tmp_path / "submissions.ndjson",
    )

    status = exchange.status(task_type="self_improvement_review")

    assert status["ok"] is True
    assert status["patterns"]["pattern_count"] == 0
    assert status["submissions"]["count"] == 0


def test_signed_roaas_import_is_reverified_locally(tmp_path: Path):
    source_registry = MarketPatternRegistry(registry_path=tmp_path / "source-patterns.json")
    source_router = PredictiveRouter(registry=source_registry, health_path=tmp_path / "source-health.json")
    for _ in range(6):
        source_router.record_outcome(
            lane=ComputeLane.LOCAL_OLLAMA,
            latency_ms=130,
            success=True,
            task_type="self_improvement_review",
            cost_usd=0.0,
            prompt_hash="signed-review-fast",
        )

    shared_secret = "shared-roaas-secret"
    source_exchange = RuntimePatternExchange(
        registry=source_registry,
        router=source_router,
        submission_log_path=tmp_path / "source-submissions.ndjson",
        identity=NodeIdentity(node_name="node-a", shared_secret=shared_secret, public_base_url="http://node-a.local"),
        trust_store=RuntimeTrustStore(path=tmp_path / "source-trust.json"),
    )
    envelope = source_exchange.export_bundle(task_type="self_improvement_review")

    target_registry = MarketPatternRegistry(registry_path=tmp_path / "target-patterns.json")
    target_router = PredictiveRouter(registry=target_registry, health_path=tmp_path / "target-health.json")
    target_exchange = RuntimePatternExchange(
        registry=target_registry,
        router=target_router,
        submission_log_path=tmp_path / "target-submissions.ndjson",
        identity=NodeIdentity(node_name="node-b", shared_secret=shared_secret, public_base_url="http://node-b.local"),
        trust_store=RuntimeTrustStore(path=tmp_path / "target-trust.json"),
    )
    receipt = target_exchange.import_bundle(envelope, trust_level=PatternStatus.CANDIDATE)

    imported = target_registry.all_for_task("self_improvement_review")
    assert receipt["verification"]["signature_valid"] is True
    assert imported
    assert imported[0].status == PatternStatus.CANDIDATE
    assert imported[0].trust["signature_valid"] is True

    for _ in range(2):
        target_router.record_outcome(
            lane=imported[0].lane,
            latency_ms=150,
            success=True,
            task_type=imported[0].task_type,
            cost_usd=0.0,
            prompt_hash=imported[0].prompt_hash,
        )

    reverified = target_registry.all_for_task("self_improvement_review")
    assert reverified[0].status == PatternStatus.TRUSTED
    assert reverified[0].local_verifications >= 2
