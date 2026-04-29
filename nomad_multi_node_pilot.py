from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from nomad_market_patterns import ComputeLane, MarketPatternRegistry, PatternStatus
from nomad_predictive_router import PredictiveRouter
from nomad_roaas_exchange import RuntimePatternExchange
from nomad_runtime_identity import NodeIdentity, RuntimeTrustStore


@dataclass
class PilotNode:
    name: str
    registry: MarketPatternRegistry
    router: PredictiveRouter
    exchange: RuntimePatternExchange


def build_pilot_node(*, base_dir: Path, name: str, shared_secret: str) -> PilotNode:
    node_dir = base_dir / name
    node_dir.mkdir(parents=True, exist_ok=True)
    registry = MarketPatternRegistry(registry_path=node_dir / "runtime-patterns.json")
    router = PredictiveRouter(registry=registry, health_path=node_dir / "lane-health.json")
    identity = NodeIdentity(
        node_name=name,
        shared_secret=shared_secret,
        public_base_url=f"http://{name}.local",
        profile_hint="pilot",
    )
    exchange = RuntimePatternExchange(
        registry=registry,
        router=router,
        submission_log_path=node_dir / "runtime-submissions.ndjson",
        identity=identity,
        trust_store=RuntimeTrustStore(path=node_dir / "runtime-trust.json"),
    )
    return PilotNode(name=name, registry=registry, router=router, exchange=exchange)


def run_multi_node_pilot(
    *,
    output_dir: Optional[Path] = None,
    shared_secret: str = "nomad-pilot-secret",
) -> dict[str, Any]:
    base_dir = Path(output_dir or Path(__file__).resolve().parent / "pilot-output")
    base_dir.mkdir(parents=True, exist_ok=True)

    node_a = build_pilot_node(base_dir=base_dir, name="node-a", shared_secret=shared_secret)
    node_b = build_pilot_node(base_dir=base_dir, name="node-b", shared_secret=shared_secret)
    node_c = build_pilot_node(base_dir=base_dir, name="node-c", shared_secret=shared_secret)

    prompt_hash = "pilot-review-fast-lane"
    for _ in range(6):
        node_a.router.record_outcome(
            lane=ComputeLane.LOCAL_OLLAMA,
            latency_ms=120,
            success=True,
            task_type="self_improvement_review",
            cost_usd=0.0,
            prompt_hash=prompt_hash,
            model_hint="pilot-local",
            verification="local",
        )

    envelope_a = node_a.exchange.export_bundle(task_type="self_improvement_review")
    import_b = node_b.exchange.import_bundle(envelope_a, trust_level=PatternStatus.CANDIDATE)
    imported_b = node_b.registry.all_for_task("self_improvement_review")
    if imported_b:
        target_b = imported_b[0]
        for _ in range(3):
            node_b.router.record_outcome(
                lane=target_b.lane,
                latency_ms=145,
                success=True,
                task_type=target_b.task_type,
                cost_usd=0.0,
                prompt_hash=target_b.prompt_hash,
                model_hint=target_b.model_hint or "pilot-local",
                verification="local",
            )
    promotion_b = node_b.registry.evaluate_promotions()

    envelope_b = node_b.exchange.export_bundle(task_type="self_improvement_review")
    import_c = node_c.exchange.import_bundle(envelope_b, trust_level=PatternStatus.CANDIDATE)
    imported_c = node_c.registry.all_for_task("self_improvement_review")
    if imported_c:
        target_c = imported_c[0]
        for _ in range(2):
            node_c.router.record_outcome(
                lane=target_c.lane,
                latency_ms=150,
                success=True,
                task_type=target_c.task_type,
                cost_usd=0.0,
                prompt_hash=target_c.prompt_hash,
                model_hint=target_c.model_hint or "pilot-local",
                verification="local",
            )
    promotion_c = node_c.registry.evaluate_promotions()

    report = {
        "schema": "nomad.multi_node_pilot.v1",
        "ok": True,
        "base_dir": str(base_dir),
        "task_type": "self_improvement_review",
        "nodes": {
            "node_a": node_a.exchange.status(task_type="self_improvement_review"),
            "node_b": node_b.exchange.status(task_type="self_improvement_review"),
            "node_c": node_c.exchange.status(task_type="self_improvement_review"),
        },
        "imports": {
            "node_b": import_b,
            "node_c": import_c,
        },
        "promotions": {
            "node_b": promotion_b,
            "node_c": promotion_c,
        },
    }
    out = base_dir / "multi-node-pilot-report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    report["output_path"] = str(out)
    return report


if __name__ == "__main__":
    result = run_multi_node_pilot()
    print(json.dumps(result, indent=2, ensure_ascii=False))
