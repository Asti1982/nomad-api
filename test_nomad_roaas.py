from __future__ import annotations

from pathlib import Path

from nomad_market_patterns import ComputeLane, MarketPatternRegistry, PatternStatus
from nomad_predictive_router import PredictiveRouter
from nomad_self_healing import SelfHealingPipeline
from self_improvement import HostedBrainRouter


def test_market_pattern_registry_prefers_fast_local_lane(tmp_path: Path):
    registry = MarketPatternRegistry(registry_path=tmp_path / "runtime-patterns.json")
    for _ in range(6):
        registry.mint_from_execution(
            task_type="self_improvement_review",
            compute_lane=ComputeLane.LOCAL_OLLAMA,
            latency_ms=120,
            cost_usd=0.0,
            success=True,
        )
    registry.mint_from_execution(
        task_type="self_improvement_review",
        compute_lane=ComputeLane.XAI_GROK,
        latency_ms=1800,
        cost_usd=0.01,
        success=True,
    )

    best = registry.best_for("self_improvement_review")

    assert best is not None
    assert best.lane == ComputeLane.LOCAL_OLLAMA
    assert best.status == PatternStatus.TRUSTED


def test_predictive_router_prefers_fast_healthy_lane(tmp_path: Path):
    registry = MarketPatternRegistry(registry_path=tmp_path / "runtime-patterns.json")
    router = PredictiveRouter(registry=registry, health_path=tmp_path / "lane-health.json")

    for _ in range(5):
        router.record_outcome(
            lane=ComputeLane.GITHUB_MODELS,
            latency_ms=180,
            success=True,
            task_type="self_improvement_review",
            cost_usd=0.0001,
        )
    for _ in range(5):
        router.record_outcome(
            lane=ComputeLane.LOCAL_OLLAMA,
            latency_ms=900,
            success=True,
            task_type="self_improvement_review",
            cost_usd=0.0,
        )

    decision = router.route(
        task_type="self_improvement_review",
        preferred_lanes=[ComputeLane.GITHUB_MODELS, ComputeLane.LOCAL_OLLAMA],
    )

    assert decision.chosen_lane == ComputeLane.GITHUB_MODELS
    assert decision.routing_score > 0.6


def test_self_healing_lane_switch_creates_replacement_pattern(tmp_path: Path):
    registry = MarketPatternRegistry(registry_path=tmp_path / "runtime-patterns.json")
    router = PredictiveRouter(registry=registry, health_path=tmp_path / "lane-health.json")

    for _ in range(6):
        registry.mint_from_execution(
            task_type="self_improvement_review",
            compute_lane=ComputeLane.LOCAL_OLLAMA,
            latency_ms=200,
            cost_usd=0.0,
            success=True,
        )
    for _ in range(3):
        router.record_outcome(
            lane=ComputeLane.LOCAL_OLLAMA,
            latency_ms=5000,
            success=False,
            task_type="self_improvement_review",
            error_type="timeout",
        )
    for _ in range(5):
        router.record_outcome(
            lane=ComputeLane.GITHUB_MODELS,
            latency_ms=220,
            success=True,
            task_type="self_improvement_review",
        )

    healer = SelfHealingPipeline(
        router=router,
        registry=registry,
        max_actions_per_cycle=1,
        heal_log_path=tmp_path / "heal.ndjson",
    )
    report = healer.run_healing_cycle_sync()

    assert report["status"] == "healing_complete"
    assert report["actions_taken"] == 1
    action = report["actions"][0]
    assert action["strategy"] == "lane_switch"
    assert action["success"] is True
    assert action["new_lane"] == ComputeLane.GITHUB_MODELS.value


def test_hosted_brain_router_records_roaas_pattern(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("NOMAD_OLLAMA_AUTO_SELECT_SELF_IMPROVE_MODEL", "false")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2:1b")
    monkeypatch.setenv("NOMAD_RUNTIME_PATTERN_REGISTRY_PATH", str(tmp_path / "runtime-patterns.json"))
    monkeypatch.setenv("NOMAD_LANE_HEALTH_PATH", str(tmp_path / "lane-health.json"))
    monkeypatch.setenv("NOMAD_HEAL_LOG_PATH", str(tmp_path / "heal.ndjson"))

    router = HostedBrainRouter()
    router._ollama_review = lambda messages: {
        "provider": "ollama",
        "name": "Ollama",
        "model": "llama3.2:1b",
        "ok": True,
        "useful": True,
        "content": "Action1: use local lane\nAction2: keep changes bounded",
        "usage": {"prompt_tokens": 20, "completion_tokens": 40, "total_tokens": 60},
    }

    results = router.review(
        objective="Improve Nomad's self review throughput.",
        context={"resources": {"ollama": {"available": True, "api_reachable": True, "model_count": 1}}},
    )

    patterns = router.pattern_registry.all_for_task("self_improvement_review")

    assert [item["provider"] for item in results] == ["ollama"]
    assert patterns
    assert patterns[0].lane == ComputeLane.LOCAL_OLLAMA
    assert patterns[0].execution_count == 1


def test_hosted_brain_router_keeps_runtime_correction_opt_in(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("NOMAD_SELF_HEALING_ENABLED", raising=False)
    monkeypatch.setenv("NOMAD_RUNTIME_PATTERN_REGISTRY_PATH", str(tmp_path / "runtime-patterns.json"))
    monkeypatch.setenv("NOMAD_LANE_HEALTH_PATH", str(tmp_path / "lane-health.json"))
    monkeypatch.setenv("NOMAD_HEAL_LOG_PATH", str(tmp_path / "heal.ndjson"))

    router = HostedBrainRouter()

    report = router.run_self_healing_cycle()

    assert report["status"] == "skipped"
    assert report["reason"] == "automatic_correction_disabled"
