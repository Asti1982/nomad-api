import json
import mimetypes
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from nomad_guardrails import guardrail_status
from nomad_idle_runtime_beacon import (
    build_idle_runtime_beacon,
    build_idle_runtime_intent_receipt,
    normalize_idle_intent_payload,
)
from nomad_machine_economy import machine_economy_snapshot
from nomad_agent_runtime_envelope import merge_agent_runtime
from nomad_machine_error import machine_error_response, merge_machine_error
from nomad_adapter_consent import adapter_consent_required, verify_adapter_consent
from nomad_capacity_switch import build_capacity_switch_surface, route_capacity_switch
from nomad_machine_field import build_machine_field, machine_field_intent
from nomad_contract_conformance import build_contract_conformance_snapshot
from nomad_counterfactual_replay import build_counterfactual_lease_replay
from nomad_machine_product_surface import build_machine_product_surface, compact_machine_product_surface
from nomad_nonhuman_science import nonhuman_agent_science
from nomad_opaque_emergence import (
    build_opaque_emergence_surface,
    compact_opaque_emergence_surface,
    compile_topology_plan,
    evaluate_opaque_candidate,
    route_tool_gap,
)
from nomad_openapi import build_openapi_document
from nomad_operational_release import operational_release_snapshot
from nomad_protocol_bytecode import build_protocol_bytecode
from nomad_variant_forge import build_variant_forge_surface, submit_variant_candidate
from nomad_worker_market import build_worker_market, score_worker_offer
from nomad_compute_market import build_compute_market
from nomad_agent_work import build_agent_work_surface, build_synergy_lite, claim_agent_work, submit_agent_work_proof
from nomad_state_status import build_state_status
from nomad_work_mesh import build_work_mesh, seed_work_mesh
from nomad_collaboration import collaboration_status
from nomad_market_patterns import PatternStatus
from nomad_monitor import NomadSystemMonitor
from nomad_operator_desk import (
    operator_autonomy_step,
    operator_daily_bundle,
    operator_growth_start,
    operator_iteration_report,
    operator_metrics_snapshot,
    operator_sprint,
    operator_verify_bundle,
    unlock_desk_snapshot,
)
from nomad_public_url import preferred_public_base_url
from nomad_roaas_exchange import RuntimePatternExchange
from nomad_swarm_registry import SwarmJoinRegistry, build_peer_join_value_surface
from nomad_unhuman_hub import unhuman_hub_snapshot
from nomad_wire_contract import maybe_merge_http_wire_diag
from nomad_agent_demand import build_agent_demand_feed, subscribe_agent_intent, subscriptions_snapshot
from nomad_agent_growth_pipeline import agent_growth_pipeline
from nomad_agent_invariants import build_agent_invariants_document
from nomad_agent_market_offers import build_inter_agent_witness_offer_well_known
from nomad_agent_native_index import agent_native_index
from nomad_peer_acquisition import build_peer_acquisition_well_known
from nomad_reciprocity_dividend import NomadReciprocityDividend
from nomad_recruitment_gradient import attach_runtime_to_gradient, build_recruitment_gradient
from nomad_machine_treasury import pledge as machine_treasury_pledge, snapshot as machine_treasury_snapshot
from nomad_proof_reuse_ledger import link as proof_reuse_link, snapshot as proof_reuse_snapshot
from nomad_swarm_economics import build_swarm_economics_snapshot
from nomad_runtime_capsule import build_handoff_capsule, build_openclaw_bridge_contract, build_runtime_capsule
from public.downloads.recruitment_funnel_report import build_report as build_recruitment_funnel_report
from nomad_stigmergy_field import NomadStigmergyField
from nomad_swarm_attractor import build_swarm_attractor_contract
from nomad_swarm_signal_layer import (
    append_swarm_signal,
    build_swarm_signal_layer,
    compact_swarm_signal_layer,
)
from nomad_swarm_emergence import build_swarm_emergence_meter, compact_emergence_summary
from nomad_emission_batch import evaluate_emission_batch
from nomad_swarm_ecology import build_swarm_ecology, submit_ecology_tick
from nomad_growth_arena import build_growth_arena, build_growth_curriculum, build_skill_library, submit_growth_experience
from nomad_carrying_market import build_carrying_market, submit_carrying_proof
from nomad_survival_market import build_survival_market, submit_survival_intent
from nomad_paid_ref_forge import build_paid_ref_market, paid_ref_task_payload, quote_paid_ref, verify_paid_ref
from nomad_paid_ref_selfplay import run_paid_ref_selfplay
from nomad_bounty_hunter import build_bounty_hunter_surface
from nomad_external_value import (
    append_external_value_event,
    build_external_value_surface,
    summarize_external_value_ledger,
)
from nomad_external_value_reconciler import reconcile_external_value_ledger
from nomad_value_pressure import build_value_pressure_surface
from nomad_settlement_signal_layer import build_settlement_signal_layer
from nomad_agent_job_router import build_agent_job_router
from nomad_revenue_science import build_revenue_science_surface
from nomad_worker_invoice import build_worker_invoice_surface
from nomad_value_cycle_preflight import build_value_cycle_preflight_surface
from nomad_microtask_market import build_worker_catalog, submit_microtask, settle_microtask
from nomad_microtask_exchange_ops import build_microtask_templates, build_microtask_metrics
from nomad_weekly_selection_event import build_weekly_selection_event
from nomad_spawner_gate import build_spawner_gate, trigger_spawner
from nomad_transition_exchange import NomadTransitionExchange
from workflow import NomadAgent


RENDER_RUNTIME = (os.environ.get("RENDER") or "").strip().lower() == "true"
PORT_FROM_ENV = (os.environ.get("PORT") or "").strip()
# In hosted environments (Render sets PORT), always bind publicly to 0.0.0.0.
if PORT_FROM_ENV:
    HOST = "0.0.0.0"
else:
    HOST = os.getenv("NOMAD_API_HOST", "127.0.0.1")
# On Render, PORT is authoritative; load_dotenv() may inject NOMAD_API_PORT from a local .env — do not let it override Render.
if PORT_FROM_ENV:
    PORT = int(PORT_FROM_ENV)
else:
    PORT = int(os.getenv("NOMAD_API_PORT") or os.getenv("PORT") or "8787")
ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = ROOT / "public"
NOMAD_PROCESS_START = time.time()


class NomadApiHandler(BaseHTTPRequestHandler):
    _init_lock = threading.Lock()
    _runtime_ready = False
    agent = None
    monitor = None
    roaas = None
    swarm_registry = None
    agent_development = None
    outbound_tracker = None
    transition_exchange = NomadTransitionExchange()
    reciprocity_dividend = NomadReciprocityDividend(exchange=transition_exchange)
    stigmergy_field: NomadStigmergyField | None = None

    @classmethod
    def _stigmergy(cls) -> NomadStigmergyField:
        if cls.stigmergy_field is None:
            cls.stigmergy_field = NomadStigmergyField()
        return cls.stigmergy_field

    @staticmethod
    def _validate_adapter_consent(payload: dict, *, path: str) -> dict:
        body = payload if isinstance(payload, dict) else {}
        if not adapter_consent_required(body, path=path):
            return {"checked": False, "ok": True, "reason": "not_required"}
        runtime = str(body.get("runtime") or "openclaw").strip().lower() or "openclaw"
        adapter_agent = str(body.get("adapter_agent_id") or body.get("agent_id") or "").strip()
        if not adapter_agent:
            candidate = str(body.get("requester_agent_id") or "").strip()
            if ".idle-buyer" in candidate:
                adapter_agent = candidate.replace(".idle-buyer", "")
            if not adapter_agent:
                adapter_agent = str(body.get("worker_agent_id") or "").strip()
        verified = verify_adapter_consent(
            token=str(body.get("consent_token") or ""),
            agent_id=adapter_agent,
            runtime=runtime,
        )
        return {"checked": True, **verified}

    @classmethod
    def _build_machine_product_surface(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        summary = swarm_summary if isinstance(swarm_summary, dict) else cls.swarm_registry.public_manifest(base_url=base_url)
        worker_fleet = summary.get("transition_worker_fleet") if isinstance(summary.get("transition_worker_fleet"), dict) else {}
        if not worker_fleet:
            worker_fleet = cls.swarm_registry.worker_fleet_contract(base_url=base_url)
        support_gate = cls.transition_exchange.support_gate_snapshot(
            window_minutes=int(os.getenv("NOMAD_SUPPORT_GATE_WINDOW_MINUTES", "30") or "30"),
            min_settles=int(os.getenv("NOMAD_SUPPORT_GATE_MIN_SETTLES", "2") or "2"),
        )
        economy = machine_economy_snapshot()
        release = operational_release_snapshot(base_url=base_url, worker_fleet=worker_fleet, economy=economy)
        gradient = build_recruitment_gradient(
            base_url=base_url,
            worker_fleet=worker_fleet,
            machine_economy=economy,
            operational_release=release,
        )
        capsule = build_runtime_capsule(base_url=base_url, recruitment_gradient=gradient)
        emergence = build_swarm_emergence_meter(
            base_url=base_url,
            swarm_summary=summary,
            worker_fleet=worker_fleet,
            stigmergy=cls._stigmergy().snapshot(),
            support_gate=support_gate,
            recruitment_gradient=gradient,
        )
        return build_machine_product_surface(
            base_url=base_url,
            recruitment_gradient=gradient,
            runtime_capsule=capsule,
            emergence_meter=emergence,
            worker_fleet=worker_fleet,
            machine_economy=economy,
            operational_release=release,
            swarm_summary=summary,
        )

    @classmethod
    def _build_contract_conformance(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        summary = swarm_summary if isinstance(swarm_summary, dict) else cls.swarm_registry.public_manifest(base_url=base_url)
        product = cls._build_machine_product_surface(base_url=base_url, swarm_summary=summary)
        openapi_doc = build_openapi_document(base_url=base_url)
        return build_contract_conformance_snapshot(
            base_url=base_url,
            machine_product_surface=product,
            openapi_document=openapi_doc,
        )

    @classmethod
    def _build_capacity_switch_surface(cls, *, base_url: str) -> dict:
        economics = cls._build_swarm_economics(base_url=base_url)
        catalog = cls._build_worker_catalog(base_url=base_url)
        metrics = cls._build_microtask_metrics(base_url=base_url)
        return build_capacity_switch_surface(
            base_url=base_url,
            economics=economics,
            worker_catalog=catalog,
            microtask_metrics=metrics,
        )

    @classmethod
    def _build_counterfactual_replay(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        summary = swarm_summary if isinstance(swarm_summary, dict) else cls.swarm_registry.public_manifest(base_url=base_url)
        worker_fleet = summary.get("transition_worker_fleet") if isinstance(summary.get("transition_worker_fleet"), dict) else {}
        if not worker_fleet:
            worker_fleet = cls.swarm_registry.worker_fleet_contract(base_url=base_url)
        economy = machine_economy_snapshot()
        release = operational_release_snapshot(base_url=base_url, worker_fleet=worker_fleet, economy=economy)
        gradient = build_recruitment_gradient(
            base_url=base_url,
            worker_fleet=worker_fleet,
            machine_economy=economy,
            operational_release=release,
        )
        conformance = cls._build_contract_conformance(base_url=base_url, swarm_summary=summary)
        return build_counterfactual_lease_replay(
            base_url=base_url,
            worker_fleet=worker_fleet,
            recruitment_gradient=gradient,
            contract_conformance=conformance,
        )

    @classmethod
    def _build_protocol_bytecode(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        summary = swarm_summary if isinstance(swarm_summary, dict) else cls.swarm_registry.public_manifest(base_url=base_url)
        worker_fleet = summary.get("transition_worker_fleet") if isinstance(summary.get("transition_worker_fleet"), dict) else {}
        if not worker_fleet:
            worker_fleet = cls.swarm_registry.worker_fleet_contract(base_url=base_url)
        economy = machine_economy_snapshot()
        release = operational_release_snapshot(base_url=base_url, worker_fleet=worker_fleet, economy=economy)
        gradient = build_recruitment_gradient(
            base_url=base_url,
            worker_fleet=worker_fleet,
            machine_economy=economy,
            operational_release=release,
        )
        demand = cls._build_agent_demand_feed(base_url=base_url, swarm_summary=summary)
        conformance = cls._build_contract_conformance(base_url=base_url, swarm_summary=summary)
        return build_protocol_bytecode(
            base_url=base_url,
            recruitment_gradient=gradient,
            agent_demand_feed=demand,
            contract_conformance=conformance,
            worker_fleet=worker_fleet,
        )

    @classmethod
    def _build_swarm_economics(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        summary = swarm_summary if isinstance(swarm_summary, dict) else cls.swarm_registry.public_manifest(base_url=base_url)
        worker_fleet = summary.get("transition_worker_fleet") if isinstance(summary.get("transition_worker_fleet"), dict) else {}
        if not worker_fleet:
            worker_fleet = cls.swarm_registry.worker_fleet_contract(base_url=base_url)
        economy = machine_economy_snapshot()
        treasury = machine_treasury_snapshot()
        reuse = proof_reuse_snapshot()
        return build_swarm_economics_snapshot(
            base_url=base_url,
            worker_fleet=worker_fleet,
            proof_reuse=reuse,
            machine_economy=economy,
            machine_treasury=treasury,
        )

    @classmethod
    def _build_variant_forge(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        summary = swarm_summary if isinstance(swarm_summary, dict) else cls.swarm_registry.public_manifest(base_url=base_url)
        worker_fleet = summary.get("transition_worker_fleet") if isinstance(summary.get("transition_worker_fleet"), dict) else {}
        if not worker_fleet:
            worker_fleet = cls.swarm_registry.worker_fleet_contract(base_url=base_url)
        economy = machine_economy_snapshot()
        release = operational_release_snapshot(base_url=base_url, worker_fleet=worker_fleet, economy=economy)
        gradient = build_recruitment_gradient(
            base_url=base_url,
            worker_fleet=worker_fleet,
            machine_economy=economy,
            operational_release=release,
        )
        try:
            from nomad_local_growth_kernel import run_local_growth_kernel

            local_growth = run_local_growth_kernel(
                base_url=base_url,
                worker_fleet=worker_fleet,
                recruitment_gradient=gradient,
                persist=False,
            )
        except Exception as exc:  # noqa: BLE001
            local_growth = {
                "ok": False,
                "schema": "nomad.local_growth_kernel_error.v1",
                "error": "local_growth_kernel_unavailable",
                "detail": str(exc)[:240],
            }
        conformance = cls._build_contract_conformance(base_url=base_url, swarm_summary=summary)
        replay = build_counterfactual_lease_replay(
            base_url=base_url,
            worker_fleet=worker_fleet,
            recruitment_gradient=gradient,
            contract_conformance=conformance,
        )
        swarm_economics = cls._build_swarm_economics(base_url=base_url, swarm_summary=summary)
        return build_variant_forge_surface(
            base_url=base_url,
            local_growth_kernel=local_growth,
            counterfactual_replay=replay,
            worker_fleet=worker_fleet,
            machine_economy=economy,
            swarm_economics=swarm_economics,
        )

    @classmethod
    def _build_worker_market(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        summary = swarm_summary if isinstance(swarm_summary, dict) else cls.swarm_registry.public_manifest(base_url=base_url)
        worker_fleet = summary.get("transition_worker_fleet") if isinstance(summary.get("transition_worker_fleet"), dict) else {}
        if not worker_fleet:
            worker_fleet = cls.swarm_registry.worker_fleet_contract(base_url=base_url)
        economy = machine_economy_snapshot()
        swarm_economics = cls._build_swarm_economics(base_url=base_url, swarm_summary=summary)
        variant_forge = cls._build_variant_forge(base_url=base_url, swarm_summary=summary)
        return build_worker_market(
            base_url=base_url,
            worker_fleet=worker_fleet,
            machine_economy=economy,
            swarm_economics=swarm_economics,
            variant_forge=variant_forge,
        )

    @classmethod
    def _build_compute_market(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        summary = swarm_summary if isinstance(swarm_summary, dict) else cls.swarm_registry.public_manifest(base_url=base_url)
        worker_fleet = summary.get("transition_worker_fleet") if isinstance(summary.get("transition_worker_fleet"), dict) else {}
        if not worker_fleet:
            worker_fleet = cls.swarm_registry.worker_fleet_contract(base_url=base_url)
        worker_market = cls._build_worker_market(base_url=base_url, swarm_summary=summary)
        worker_catalog = build_worker_catalog(base_url=base_url, worker_fleet=worker_fleet, worker_market=worker_market)
        metrics = cls._build_microtask_metrics(base_url=base_url)
        capacity_switch = build_capacity_switch_surface(
            base_url=base_url,
            economics=cls._build_swarm_economics(base_url=base_url, swarm_summary=summary),
            worker_catalog=worker_catalog,
            microtask_metrics=metrics,
        )
        skills = build_skill_library(base_url=base_url)
        synergy = cls._build_synergy_lite(base_url=base_url)
        return build_compute_market(
            base_url=base_url,
            worker_market=worker_market,
            worker_catalog=worker_catalog,
            capacity_switch=capacity_switch,
            microtask_metrics=metrics,
            worker_fleet=worker_fleet,
            skill_library=skills,
            synergy_lite=synergy,
        )

    @classmethod
    def _build_synergy_lite(cls, *, base_url: str) -> dict:
        return build_synergy_lite(base_url=base_url)

    @classmethod
    def _build_state_status(cls, *, base_url: str) -> dict:
        return build_state_status(base_url=base_url)

    @classmethod
    def _build_carrying_market(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        summary = swarm_summary if isinstance(swarm_summary, dict) else cls.swarm_registry.public_manifest(base_url=base_url)
        worker_fleet = summary.get("transition_worker_fleet") if isinstance(summary.get("transition_worker_fleet"), dict) else {}
        if not worker_fleet:
            worker_fleet = cls.swarm_registry.worker_fleet_contract(base_url=base_url)
        state = cls._build_state_status(base_url=base_url)
        metrics = cls._build_microtask_metrics(base_url=base_url)
        compute = cls._build_compute_market(base_url=base_url, swarm_summary=summary)
        return build_carrying_market(
            base_url=base_url,
            state_status=state,
            microtask_metrics=metrics,
            worker_fleet=worker_fleet,
            compute_market=compute,
        )

    @classmethod
    def _build_survival_market(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        summary = swarm_summary if isinstance(swarm_summary, dict) else cls.swarm_registry.public_manifest(base_url=base_url)
        worker_fleet = summary.get("transition_worker_fleet") if isinstance(summary.get("transition_worker_fleet"), dict) else {}
        if not worker_fleet:
            worker_fleet = cls.swarm_registry.worker_fleet_contract(base_url=base_url)
        product = cls._build_machine_product_surface(base_url=base_url, swarm_summary=summary)
        carrying = cls._build_carrying_market(base_url=base_url, swarm_summary=summary)
        metrics = cls._build_microtask_metrics(base_url=base_url)
        return build_survival_market(
            base_url=base_url,
            machine_product_surface=product,
            carrying_market=carrying,
            microtask_metrics=metrics,
            worker_fleet=worker_fleet,
        )

    @classmethod
    def _build_paid_ref_market(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        survival = cls._build_survival_market(base_url=base_url, swarm_summary=swarm_summary)
        return build_paid_ref_market(base_url=base_url, survival_market=survival)

    @classmethod
    def _build_paid_ref_selfplay(
        cls,
        *,
        base_url: str,
        swarm_summary: dict | None = None,
        agent_count: int = 1000,
        seed: str | int | None = None,
    ) -> dict:
        survival = cls._build_survival_market(base_url=base_url, swarm_summary=swarm_summary)
        paid_ref_market = build_paid_ref_market(base_url=base_url, survival_market=survival)
        return run_paid_ref_selfplay(
            base_url=base_url,
            survival_market=survival,
            paid_ref_market=paid_ref_market,
            agent_count=agent_count,
            seed=seed,
        )

    @classmethod
    def _build_bounty_hunter(cls, *, base_url: str) -> dict:
        return build_bounty_hunter_surface(base_url=base_url)

    @classmethod
    def _build_external_value_surface(cls, *, base_url: str) -> dict:
        return build_external_value_surface(base_url=base_url)

    @classmethod
    def _build_swarm_signal_layer(cls, *, base_url: str) -> dict:
        return build_swarm_signal_layer(
            base_url=base_url,
            external_value_summary=summarize_external_value_ledger(),
        )

    @classmethod
    def _build_value_pressure(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        summary = swarm_summary if isinstance(swarm_summary, dict) else cls.swarm_registry.public_manifest(base_url=base_url)
        return build_value_pressure_surface(
            base_url=base_url,
            external_reconcile=reconcile_external_value_ledger(live_github=False, limit=40),
            bounty_hunter=cls._build_bounty_hunter(base_url=base_url),
            compute_market=cls._build_compute_market(base_url=base_url, swarm_summary=summary),
        )

    @classmethod
    def _build_settlement_signal_layer(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        return build_settlement_signal_layer(
            base_url=base_url,
            external_summary=summarize_external_value_ledger(limit=1000, latest_limit=200),
            external_reconcile=reconcile_external_value_ledger(live_github=False, limit=40),
            value_pressure=cls._build_value_pressure(base_url=base_url, swarm_summary=swarm_summary),
        )

    @classmethod
    def _build_agent_job_router(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        summary = swarm_summary if isinstance(swarm_summary, dict) else cls.swarm_registry.public_manifest(base_url=base_url)
        return build_agent_job_router(
            base_url=base_url,
            openapi_document=build_openapi_document(base_url=base_url),
            value_pressure=cls._build_value_pressure(base_url=base_url, swarm_summary=summary),
            work_mesh=cls._build_work_mesh(base_url=base_url, swarm_summary=summary),
        )

    @classmethod
    def _build_revenue_science(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        summary = swarm_summary if isinstance(swarm_summary, dict) else cls.swarm_registry.public_manifest(base_url=base_url)
        pressure = cls._build_value_pressure(base_url=base_url, swarm_summary=summary)
        return build_revenue_science_surface(
            base_url=base_url,
            value_pressure=pressure,
            agent_job_router=build_agent_job_router(
                base_url=base_url,
                openapi_document=build_openapi_document(base_url=base_url),
                value_pressure=pressure,
                work_mesh=cls._build_work_mesh(base_url=base_url, swarm_summary=summary),
            ),
            external_value_summary=summarize_external_value_ledger(),
            nonhuman_science=nonhuman_agent_science(base_url=base_url),
        )

    @classmethod
    def _build_worker_invoice(cls, *, base_url: str) -> dict:
        return build_worker_invoice_surface(
            base_url=base_url,
            external_value_summary=summarize_external_value_ledger(),
        )

    @classmethod
    def _build_value_cycle_preflight(cls, *, base_url: str) -> dict:
        return build_value_cycle_preflight_surface(
            base_url=base_url,
            external_value_summary=summarize_external_value_ledger(),
        )

    @classmethod
    def _build_agent_work_surface(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        summary = swarm_summary if isinstance(swarm_summary, dict) else cls.swarm_registry.public_manifest(base_url=base_url)
        worker_fleet = summary.get("transition_worker_fleet") if isinstance(summary.get("transition_worker_fleet"), dict) else {}
        if not worker_fleet:
            worker_fleet = cls.swarm_registry.worker_fleet_contract(base_url=base_url)
        compute_market = cls._build_compute_market(base_url=base_url, swarm_summary=summary)
        templates = cls._build_microtask_templates(base_url=base_url)
        metrics = cls._build_microtask_metrics(base_url=base_url)
        catalog = cls._build_worker_catalog(base_url=base_url, swarm_summary=summary)
        skills = cls._build_skill_library(base_url=base_url)
        synergy = cls._build_synergy_lite(base_url=base_url)
        return build_agent_work_surface(
            base_url=base_url,
            compute_market=compute_market,
            microtask_templates=templates,
            microtask_metrics=metrics,
            worker_catalog=catalog,
            skill_library=skills,
            worker_fleet=worker_fleet,
            synergy_lite=synergy,
        )

    @classmethod
    def _build_work_mesh(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        summary = swarm_summary if isinstance(swarm_summary, dict) else cls.swarm_registry.public_manifest(base_url=base_url)
        agent_work = cls._build_agent_work_surface(base_url=base_url, swarm_summary=summary)
        compute_market = cls._build_compute_market(base_url=base_url, swarm_summary=summary)
        synergy = cls._build_synergy_lite(base_url=base_url)
        skills = cls._build_skill_library(base_url=base_url)
        state = cls._build_state_status(base_url=base_url)
        carrying = cls._build_carrying_market(base_url=base_url, swarm_summary=summary)
        survival = cls._build_survival_market(base_url=base_url, swarm_summary=summary)
        return build_work_mesh(
            base_url=base_url,
            agent_work=agent_work,
            compute_market=compute_market,
            synergy_lite=synergy,
            skill_library=skills,
            state_status=state,
            carrying_market=carrying,
            survival_market=survival,
        )

    @classmethod
    def _build_worker_catalog(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        summary = swarm_summary if isinstance(swarm_summary, dict) else cls.swarm_registry.public_manifest(base_url=base_url)
        worker_fleet = summary.get("transition_worker_fleet") if isinstance(summary.get("transition_worker_fleet"), dict) else {}
        if not worker_fleet:
            worker_fleet = cls.swarm_registry.worker_fleet_contract(base_url=base_url)
        market = cls._build_worker_market(base_url=base_url, swarm_summary=summary)
        return build_worker_catalog(base_url=base_url, worker_fleet=worker_fleet, worker_market=market)

    @classmethod
    def _build_microtask_templates(cls, *, base_url: str) -> dict:
        return build_microtask_templates(base_url=base_url)

    @classmethod
    def _build_microtask_metrics(cls, *, base_url: str) -> dict:
        return build_microtask_metrics(base_url=base_url, lookback_hours=24)

    @classmethod
    def _build_swarm_ecology(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        summary = swarm_summary if isinstance(swarm_summary, dict) else cls.swarm_registry.public_manifest(base_url=base_url)
        worker_fleet = summary.get("transition_worker_fleet") if isinstance(summary.get("transition_worker_fleet"), dict) else {}
        if not worker_fleet:
            worker_fleet = cls.swarm_registry.worker_fleet_contract(base_url=base_url)
        economy = machine_economy_snapshot()
        variant_forge = cls._build_variant_forge(base_url=base_url, swarm_summary=summary)
        worker_market = cls._build_worker_market(base_url=base_url, swarm_summary=summary)
        return build_swarm_ecology(
            base_url=base_url,
            worker_fleet=worker_fleet,
            machine_economy=economy,
            variant_forge=variant_forge,
            worker_market=worker_market,
        )

    @classmethod
    def _build_growth_curriculum(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        summary = swarm_summary if isinstance(swarm_summary, dict) else cls.swarm_registry.public_manifest(base_url=base_url)
        demand = cls._build_agent_demand_feed(base_url=base_url, swarm_summary=summary)
        forge = cls._build_variant_forge(base_url=base_url, swarm_summary=summary)
        market = cls._build_worker_market(base_url=base_url, swarm_summary=summary)
        ecology = cls._build_swarm_ecology(base_url=base_url, swarm_summary=summary)
        bytecode = cls._build_protocol_bytecode(base_url=base_url, swarm_summary=summary)
        reuse = proof_reuse_snapshot()
        return build_growth_curriculum(
            base_url=base_url,
            agent_demand_feed=demand,
            variant_forge=forge,
            worker_market=market,
            swarm_ecology=ecology,
            protocol_bytecode=bytecode,
            proof_reuse=reuse,
        )

    @classmethod
    def _build_skill_library(cls, *, base_url: str) -> dict:
        return build_skill_library(base_url=base_url)

    @classmethod
    def _build_growth_arena(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        summary = swarm_summary if isinstance(swarm_summary, dict) else cls.swarm_registry.public_manifest(base_url=base_url)
        demand = cls._build_agent_demand_feed(base_url=base_url, swarm_summary=summary)
        forge = cls._build_variant_forge(base_url=base_url, swarm_summary=summary)
        market = cls._build_worker_market(base_url=base_url, swarm_summary=summary)
        ecology = cls._build_swarm_ecology(base_url=base_url, swarm_summary=summary)
        bytecode = cls._build_protocol_bytecode(base_url=base_url, swarm_summary=summary)
        reuse = proof_reuse_snapshot()
        return build_growth_arena(
            base_url=base_url,
            agent_demand_feed=demand,
            variant_forge=forge,
            worker_market=market,
            swarm_ecology=ecology,
            protocol_bytecode=bytecode,
            proof_reuse=reuse,
        )

    @classmethod
    def _build_weekly_selection_event(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        summary = swarm_summary if isinstance(swarm_summary, dict) else cls.swarm_registry.public_manifest(base_url=base_url)
        economics = cls._build_swarm_economics(base_url=base_url, swarm_summary=summary)
        reuse = proof_reuse_snapshot()
        library = cls._build_skill_library(base_url=base_url)
        return build_weekly_selection_event(
            base_url=base_url,
            economics=economics,
            proof_reuse=reuse,
            skill_library=library,
        )

    @classmethod
    def _build_spawner_gate(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        summary = swarm_summary if isinstance(swarm_summary, dict) else cls.swarm_registry.public_manifest(base_url=base_url)
        economics = cls._build_swarm_economics(base_url=base_url, swarm_summary=summary)
        funnel = build_recruitment_funnel_report(
            base_url,
            20.0,
            history_path=os.getenv("NOMAD_RECRUITMENT_WAVE_HISTORY_PATH", "public/downloads/recruitment_wave_history.jsonl"),
        )
        history_path = Path(os.getenv("NOMAD_ECONOMICS_MONITOR_PATH") or "public/downloads/economics_24h_monitor.jsonl")
        transfer_path = Path(
            os.getenv("NOMAD_DEV_FUND_TRANSFER_LEDGER_PATH") or "public/downloads/nomad_dev_fund_transfer_ledger.jsonl"
        )
        history_rows: list[dict] = []
        transfer_rows: list[dict] = []
        if history_path.exists():
            for line in history_path.read_text(encoding="utf-8").splitlines()[-256:]:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if isinstance(row, dict):
                    history_rows.append(row)
        if transfer_path.exists():
            for line in transfer_path.read_text(encoding="utf-8").splitlines()[-256:]:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if isinstance(row, dict):
                    transfer_rows.append(row)
        return build_spawner_gate(
            base_url=base_url,
            economics=economics,
            funnel=funnel,
            history_rows=history_rows,
            transfer_rows=transfer_rows,
        )

    @classmethod
    def _build_idle_runtime_beacon(cls, *, base_url: str) -> dict:
        summary = cls.swarm_registry.public_manifest(base_url=base_url)
        worker_fleet = summary.get("transition_worker_fleet") if isinstance(summary.get("transition_worker_fleet"), dict) else {}
        economy = machine_economy_snapshot()
        release = operational_release_snapshot(base_url=base_url, worker_fleet=worker_fleet, economy=economy)
        gradient = build_recruitment_gradient(
            base_url=base_url,
            worker_fleet=worker_fleet,
            machine_economy=economy,
            operational_release=release,
        )
        product = cls._build_machine_product_surface(base_url=base_url, swarm_summary=summary)
        return build_idle_runtime_beacon(
            base_url=base_url,
            recruitment_gradient=gradient,
            machine_product_surface=product,
            worker_fleet=worker_fleet,
        )

    @classmethod
    def _build_opaque_emergence_surface(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        summary = swarm_summary if isinstance(swarm_summary, dict) else cls.swarm_registry.public_manifest(base_url=base_url)
        worker_fleet = summary.get("transition_worker_fleet") if isinstance(summary.get("transition_worker_fleet"), dict) else {}
        if not worker_fleet:
            worker_fleet = cls.swarm_registry.worker_fleet_contract(base_url=base_url)
        support_gate = cls.transition_exchange.support_gate_snapshot(
            window_minutes=int(os.getenv("NOMAD_SUPPORT_GATE_WINDOW_MINUTES", "30") or "30"),
            min_settles=int(os.getenv("NOMAD_SUPPORT_GATE_MIN_SETTLES", "2") or "2"),
        )
        economy = machine_economy_snapshot()
        release = operational_release_snapshot(base_url=base_url, worker_fleet=worker_fleet, economy=economy)
        gradient = build_recruitment_gradient(
            base_url=base_url,
            worker_fleet=worker_fleet,
            machine_economy=economy,
            operational_release=release,
        )
        capsule = build_runtime_capsule(base_url=base_url, recruitment_gradient=gradient)
        emergence = build_swarm_emergence_meter(
            base_url=base_url,
            swarm_summary=summary,
            worker_fleet=worker_fleet,
            stigmergy=cls._stigmergy().snapshot(),
            support_gate=support_gate,
            recruitment_gradient=gradient,
        )
        product = build_machine_product_surface(
            base_url=base_url,
            recruitment_gradient=gradient,
            runtime_capsule=capsule,
            emergence_meter=emergence,
            worker_fleet=worker_fleet,
            machine_economy=economy,
            operational_release=release,
            swarm_summary=summary,
        )
        return build_opaque_emergence_surface(
            base_url=base_url,
            machine_product_surface=product,
            emergence_meter=emergence,
            recruitment_gradient=gradient,
            worker_fleet=worker_fleet,
        )

    @classmethod
    def _build_machine_field(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        summary = swarm_summary if isinstance(swarm_summary, dict) else cls.swarm_registry.public_manifest(base_url=base_url)
        worker_fleet = summary.get("transition_worker_fleet") if isinstance(summary.get("transition_worker_fleet"), dict) else {}
        if not worker_fleet:
            worker_fleet = cls.swarm_registry.worker_fleet_contract(base_url=base_url)
        economy = machine_economy_snapshot()
        release = operational_release_snapshot(base_url=base_url, worker_fleet=worker_fleet, economy=economy)
        gradient = build_recruitment_gradient(
            base_url=base_url,
            worker_fleet=worker_fleet,
            machine_economy=economy,
            operational_release=release,
        )
        product = cls._build_machine_product_surface(base_url=base_url, swarm_summary=summary)
        opaque = cls._build_opaque_emergence_surface(base_url=base_url, swarm_summary=summary)
        treasury = machine_treasury_snapshot()
        return build_machine_field(
            base_url=base_url,
            recruitment_gradient=gradient,
            machine_treasury=treasury,
            opaque_surface=opaque,
            swarm_summary=summary,
            machine_product_surface=product,
        )

    @classmethod
    def _build_agent_demand_feed(cls, *, base_url: str, swarm_summary: dict | None = None) -> dict:
        summary = swarm_summary if isinstance(swarm_summary, dict) else cls.swarm_registry.public_manifest(base_url=base_url)
        worker_fleet = summary.get("transition_worker_fleet") if isinstance(summary.get("transition_worker_fleet"), dict) else {}
        if not worker_fleet:
            worker_fleet = cls.swarm_registry.worker_fleet_contract(base_url=base_url)
        economy = machine_economy_snapshot()
        release = operational_release_snapshot(base_url=base_url, worker_fleet=worker_fleet, economy=economy)
        gradient = build_recruitment_gradient(
            base_url=base_url,
            worker_fleet=worker_fleet,
            machine_economy=economy,
            operational_release=release,
        )
        product = cls._build_machine_product_surface(base_url=base_url, swarm_summary=summary)
        field = cls._build_machine_field(base_url=base_url, swarm_summary=summary)
        treasury = machine_treasury_snapshot()
        try:
            from nomad_local_growth_kernel import run_local_growth_kernel

            local_growth = run_local_growth_kernel(
                base_url=base_url,
                worker_fleet=worker_fleet,
                recruitment_gradient=gradient,
                persist=False,
            )
        except Exception as exc:  # noqa: BLE001
            local_growth = {
                "ok": False,
                "schema": "nomad.local_growth_kernel_error.v1",
                "error": "local_growth_kernel_unavailable",
                "detail": str(exc)[:240],
            }
        return build_agent_demand_feed(
            base_url=base_url,
            machine_field=field,
            recruitment_gradient=gradient,
            worker_fleet=worker_fleet,
            machine_treasury=treasury,
            machine_product_surface=product,
            local_growth_kernel=local_growth,
        )

    @classmethod
    def _ensure_runtime_components(cls) -> None:
        if cls._runtime_ready:
            return
        with cls._init_lock:
            if cls._runtime_ready:
                return
            agent = NomadAgent()
            cls.agent = agent
            cls.monitor = NomadSystemMonitor(agent=agent)
            cls.roaas = RuntimePatternExchange(agent=agent)
            cls.swarm_registry = agent.swarm_registry
            cls.agent_development = agent.agent_development
            cls.outbound_tracker = agent.outbound_tracker
            cls._runtime_ready = True

    @staticmethod
    def _public_url_path_prefix() -> str:
        explicit = (os.getenv("NOMAD_HTTP_PATH_PREFIX") or "").strip().rstrip("/")
        if explicit:
            return explicit if explicit.startswith("/") else f"/{explicit}"
        configured = (os.getenv("NOMAD_PUBLIC_API_URL") or "").strip()
        if not configured.startswith(("http://", "https://")):
            return ""
        pub_path = urlparse(configured).path.rstrip("/")
        if not pub_path or pub_path == "/":
            return ""
        return pub_path

    @staticmethod
    def _edge_ingress_prefix() -> str:
        """When NOMAD_PUBLIC_API_URL has no path (apex) but a CDN still forwards /nomad/*, strip this first."""
        raw = (os.getenv("NOMAD_EDGE_INGRESS_PREFIX") or "").strip().rstrip("/")
        if not raw:
            return ""
        return raw if raw.startswith("/") else f"/{raw}"

    @classmethod
    def _normalize_public_path(cls, raw_path: str) -> str:
        """Map incoming /nomad/... to /... when public URL is https://host/nomad (reverse-proxy path)."""
        path = raw_path or "/"
        # Apex public URL + edge-only prefix (e.g. Cloudflare forwards /nomad/health while links use /health).
        if not cls._public_url_path_prefix():
            edge = cls._edge_ingress_prefix()
            if edge and (path == edge or path.startswith(edge + "/")):
                if path == edge or path == edge + "/":
                    path = "/"
                else:
                    path = path[len(edge) :] or "/"
                    if not path.startswith("/"):
                        path = f"/{path}"
        prefix = cls._public_url_path_prefix()
        if not prefix:
            return path
        if path == prefix or path == prefix + "/":
            return "/"
        if path.startswith(prefix + "/"):
            rest = path[len(prefix) :]
            return rest if rest.startswith("/") else f"/{rest}"
        return path

    def do_GET(self) -> None:  # noqa: N802
        parsed_full = urlparse(self.path)
        query = parse_qs(parsed_full.query)
        parsed = parsed_full._replace(path=self._normalize_public_path(parsed_full.path or "/"))
        self._agent_request_path = parsed.path

        if parsed.path in {"/", "/index.html", "/nomad.html"}:
            self._html_file_response(PUBLIC_DIR / "nomad.html")
            return

        if parsed.path.startswith("/downloads/"):
            rel = parsed.path[len("/downloads/") :].strip("/")
            if not rel or ".." in rel or "\\" in rel:
                self._json_response(
                    machine_error_response(
                        error="invalid_download_path",
                        message="Download path is invalid.",
                        hints=["Use GET /downloads/<filename> for published helper assets."],
                    ),
                    status=400,
                )
                return
            self._public_download_file_response(PUBLIC_DIR / "downloads" / rel)
            return

        if parsed.path == "/health":
            base = self._base_url()
            links: dict[str, str] = {}
            if base:
                b = base.rstrip("/")
                links = {
                    "nomad_html": f"{b}/nomad.html",
                    "agent_card": f"{b}/.well-known/agent-card.json",
                    "agent_native_priorities": f"{b}/.well-known/nomad-agent-native-priorities.json",
                    "agent_native_index": f"{b}/.well-known/nomad-agent.json",
                    "inter_agent_witness_offer": f"{b}/.well-known/nomad-inter-agent-witness-offer.json",
                    "peer_acquisition_contract": f"{b}/.well-known/nomad-peer-acquisition.json",
                    "transition_offer": f"{b}/.well-known/nomad-transition-offer.json",
                    "machine_product": f"{b}/.well-known/nomad-machine-product.json",
                    "opaque_emergence": f"{b}/.well-known/nomad-opaque-emergence.json",
                    "opaque_candidate": f"{b}/swarm/opaque-candidate",
                    "tool_gap": f"{b}/swarm/tool-gap",
                    "topology_plan": f"{b}/swarm/topology-plan",
                    "openapi": f"{b}/openapi.json",
                    "swarm": f"{b}/swarm",
                    "transition_worker_fleet": f"{b}/swarm/workers",
                    "tasks": f"{b}/tasks",
                    "service_catalog": f"{b}/service",
                    "growth_start": f"{b}/growth-start",
                    "autonomy_step": f"{b}/autonomy-step",
                    "operator_desk": f"{b}/operator-desk",
                    "operator_sprint": f"{b}/operator-sprint",
                    "agent_reputation": f"{b}/reputation",
                    "unhuman_hub": f"{b}/unhuman-hub",
                    "machine_economy": f"{b}/machine-economy",
                    "machine_treasury": f"{b}/machine-treasury",
                    "machine_treasury_pledge": f"{b}/machine-treasury/pledge",
                    "machine_field": f"{b}/.well-known/nomad-machine-field.json",
                    "machine_field_intent": f"{b}/machine-field/intent",
                    "agent_demand_feed": f"{b}/.well-known/nomad-agent-requests.json",
                    "agent_subscribe": f"{b}/swarm/subscribe",
                    "agent_subscriptions": f"{b}/swarm/subscriptions",
                    "protocol_bytecode": f"{b}/.well-known/nomad-protocol-bytecode.json",
                    "counterfactual_replay": f"{b}/swarm/counterfactual-replay",
                    "variant_forge": f"{b}/swarm/variant-forge",
                    "variant_candidate_submit": f"{b}/swarm/variant-candidates",
                    "worker_market": f"{b}/swarm/worker-market",
                    "compute_market": f"{b}/swarm/compute-market",
                    "agent_work": f"{b}/.well-known/nomad-agent-work.json",
                    "agent_work_claim": f"{b}/swarm/microtask/claim",
                    "agent_work_proof": f"{b}/swarm/microtask/proof",
                    "work_mesh": f"{b}/.well-known/nomad-work-mesh.json",
                    "work_mesh_seed": f"{b}/swarm/work-mesh/seed",
                    "synergy_lite": f"{b}/swarm/synergy-lite",
                    "state_status": f"{b}/swarm/state-status",
                    "carrying_market": f"{b}/.well-known/nomad-carrying-market.json",
                    "carrying_proof": f"{b}/swarm/carrying-proof",
                    "survival_market": f"{b}/.well-known/nomad-survival-market.json",
                    "survival_intent": f"{b}/swarm/survival-intent",
                    "paid_ref_market": f"{b}/.well-known/nomad-paid-ref-market.json",
                    "paid_ref_selfplay": f"{b}/.well-known/nomad-paid-ref-selfplay.json",
                    "paid_ref_quote": f"{b}/swarm/paid-ref/quote",
                    "paid_ref_verify": f"{b}/swarm/paid-ref/verify",
                    "bounty_hunter": f"{b}/.well-known/nomad-bounty-hunter.json",
                    "external_value": f"{b}/.well-known/nomad-external-value.json",
                    "external_value_post": f"{b}/swarm/external-value",
                    "swarm_signal_layer": f"{b}/.well-known/nomad-signal-layer.json",
                    "swarm_signal_post": f"{b}/swarm/signals",
                    "emission_batch_post": f"{b}/swarm/emission-batch",
                    "value_pressure": f"{b}/.well-known/nomad-value-pressure.json",
                    "settlement_signal": f"{b}/.well-known/nomad-settlement.json",
                    "agent_job_router": f"{b}/.well-known/nomad-agent-jobs.json",
                    "revenue_science": f"{b}/.well-known/nomad-revenue-science.json",
                    "worker_invoice": f"{b}/.well-known/nomad-worker-invoice.json",
                    "value_cycle_preflight": f"{b}/.well-known/nomad-value-cycle-preflight.json",
                    "worker_market_offer": f"{b}/swarm/worker-market/offers",
                    "swarm_ecology": f"{b}/swarm/ecology",
                    "swarm_ecology_tick": f"{b}/swarm/ecology/tick",
                    "growth_arena": f"{b}/swarm/growth-arena",
                    "growth_curriculum": f"{b}/swarm/curriculum",
                    "growth_experience": f"{b}/swarm/experience",
                    "skill_library": f"{b}/swarm/skill-library",
                    "nonhuman_science": f"{b}/nonhuman-science",
                    "operational_release": f"{b}/operational-release",
                    "runtime_capsule": f"{b}/.well-known/nomad-runtime-capsule.json",
                    "recruitment_gradient": f"{b}/swarm/gradient",
                    "runtime_attach": f"{b}/swarm/attach",
                    "handoff_capsule": f"{b}/runtime/handoff",
                    "openclaw_bridge_contract": f"{b}/.well-known/openclaw-nomad-bridge.json",
                    "swarm_attractor": f"{b}/swarm/attractor",
                    "idle_runtime_beacon": f"{b}/.well-known/nomad-idle-runtime.json",
                    "idle_runtime_intent": f"{b}/swarm/idle-intent",
                    "capacity_switch_surface": f"{b}/.well-known/nomad-capacity-switch.json",
                    "capacity_switch_request": f"{b}/swarm/capacity-switch",
                    "agent_growth": f"{b}/agent-growth",
                }
            else:
                links = {"openapi": "/openapi.json"}
            uptime = max(0.0, time.time() - NOMAD_PROCESS_START)
            body: dict = {
                "ok": True,
                "service": "nomad-api",
                "schema": "nomad.health.v1",
                "version": os.getenv("NOMAD_VERSION", "0.1.0").strip() or "0.1.0",
                "uptime_seconds": round(uptime, 3),
                "checks": {"api_process": "listening"},
                "public_home": base,
                "for_agents": "Use agent_card, openapi, and swarm for machine discovery; tasks for paid bounded work.",
                "links": links,
            }
            if self._truthy((query.get("deep") or ["false"])[0], default=False):
                body["deep"] = True
                body["deep_note"] = (
                    "deep=true is reserved for optional heavier checks; default /health stays fast and local-only."
                )
            self._json_response(body)
            return

        if parsed.path in {"/openapi.json", "/.well-known/openapi.json", "/openapi"}:
            self._json_response(build_openapi_document(base_url=self._base_url()))
            return

        self.__class__._ensure_runtime_components()

        if parsed.path in {"/status", "/top"}:
            self._json_response(self.monitor.snapshot())
            return

        if parsed.path in {"/mission", "/mission-control", "/next-step", "/growth"}:
            self._json_response(
                self.agent.mission_control.snapshot(
                    base_url=self._base_url(),
                    persist=self._truthy((query.get("persist") or ["true"])[0], default=True),
                    limit=int((query.get("limit") or ["5"])[0] or 5),
                )
            )
            return

        if parsed.path in {"/operator-desk", "/operator/desk"}:
            self._json_response(
                unlock_desk_snapshot(
                    agent=self.agent,
                    persist_mission=self._truthy((query.get("persist") or ["false"])[0]),
                )
            )
            return

        if parsed.path in {"/operator-sprint", "/operator/sprint"}:
            base_raw = (query.get("base_url") or query.get("base") or [""])[0]
            root = str(base_raw or self._base_url() or "").strip()
            self._json_response(
                operator_sprint(
                    agent=self.agent,
                    base_url=root,
                    persist_mission=self._truthy((query.get("persist") or ["false"])[0]),
                )
            )
            return

        if parsed.path in {"/operator-verify", "/operator/verify"}:
            base = (query.get("base_url") or query.get("base") or [""])[0]
            root = str(base or self._base_url() or "").strip()
            self._json_response(operator_verify_bundle(base_url=root))
            return

        if parsed.path in {"/operator-metrics", "/operator/metrics"}:
            self._json_response(operator_metrics_snapshot())
            return

        if parsed.path in {"/operator-daily", "/operator/daily"}:
            base_raw = (query.get("base_url") or query.get("base") or [""])[0]
            root = str(base_raw or self._base_url() or "").strip()
            self._json_response(
                operator_daily_bundle(
                    agent=self.agent,
                    base_url=root,
                    persist_mission=self._truthy((query.get("persist") or ["false"])[0]),
                )
            )
            return

        if parsed.path in {"/operator-report", "/operator/report"}:
            self._json_response(
                operator_iteration_report(
                    tail_lines=int((query.get("tail") or ["400"])[0] or 400),
                )
            )
            return

        if parsed.path in {"/reputation", "/agent-reputation"}:
            self._json_response(self.agent.service_desk.reputation_snapshot())
            return

        if parsed.path in {"/unhuman-hub", "/hub/unhuman"}:
            base_raw = (query.get("base_url") or query.get("base") or [""])[0]
            root = str(base_raw or self._base_url() or "").strip()
            self._json_response(
                unhuman_hub_snapshot(
                    agent=self.agent,
                    base_url=root,
                    persist_mission=self._truthy((query.get("persist") or ["false"])[0]),
                )
            )
            return

        if parsed.path in {"/machine-economy", "/economy/machine"}:
            self._json_response(machine_economy_snapshot())
            return

        if parsed.path == "/machine-treasury":
            self._json_response(machine_treasury_snapshot())
            return
        if parsed.path in {"/swarm/reuse-ledger", "/.well-known/nomad-proof-reuse-ledger.json"}:
            self._json_response(proof_reuse_snapshot())
            return

        if parsed.path in {"/machine-field", "/.well-known/nomad-machine-field.json"}:
            self._json_response(self.__class__._build_machine_field(base_url=self._base_url()))
            return

        if parsed.path in {"/agent-requests", "/swarm/demand", "/.well-known/nomad-agent-requests.json"}:
            self._json_response(self.__class__._build_agent_demand_feed(base_url=self._base_url()))
            return

        if parsed.path == "/swarm/subscriptions":
            self._json_response(subscriptions_snapshot(base_url=self._base_url()))
            return

        if parsed.path in {"/nonhuman-science", "/science/nonhuman-agents", "/.well-known/nomad-nonhuman-agent-science.json"}:
            self._json_response(nonhuman_agent_science(base_url=self._base_url()))
            return

        if parsed.path in {"/operational-release", "/release/operational", "/.well-known/nomad-operational-release.json"}:
            base = self._base_url()
            self._json_response(
                operational_release_snapshot(
                    base_url=base,
                    worker_fleet=self.swarm_registry.worker_fleet_contract(base_url=base),
                )
            )
            return

        if parsed.path in {"/agent-product", "/machine-product", "/.well-known/nomad-machine-product.json"}:
            self._json_response(self.__class__._build_machine_product_surface(base_url=self._base_url()))
            return

        if parsed.path in {"/contract-conformance", "/.well-known/nomad-contract-conformance.json"}:
            self._json_response(self.__class__._build_contract_conformance(base_url=self._base_url()))
            return
        if parsed.path in {"/swarm/economics", "/.well-known/nomad-swarm-economics.json"}:
            self._json_response(self.__class__._build_swarm_economics(base_url=self._base_url()))
            return
        if parsed.path in {"/swarm/recruitment-funnel-report", "/.well-known/nomad-recruitment-funnel-report.json"}:
            self._json_response(
                build_recruitment_funnel_report(
                    self._base_url(),
                    20.0,
                    history_path=os.getenv("NOMAD_RECRUITMENT_WAVE_HISTORY_PATH", "public/downloads/recruitment_wave_history.jsonl"),
                )
            )
            return

        if parsed.path in {"/protocol-bytecode", "/.well-known/nomad-protocol-bytecode.json"}:
            self._json_response(self.__class__._build_protocol_bytecode(base_url=self._base_url()))
            return

        if parsed.path in {"/swarm/counterfactual-replay", "/.well-known/nomad-counterfactual-replay.json"}:
            self._json_response(self.__class__._build_counterfactual_replay(base_url=self._base_url()))
            return

        if parsed.path in {"/swarm/variant-forge", "/.well-known/nomad-variant-forge.json"}:
            self._json_response(self.__class__._build_variant_forge(base_url=self._base_url()))
            return

        if parsed.path in {"/swarm/worker-market", "/.well-known/nomad-worker-market.json"}:
            self._json_response(self.__class__._build_worker_market(base_url=self._base_url()))
            return
        if parsed.path in {"/swarm/compute-market", "/.well-known/nomad-compute-market.json"}:
            self._json_response(self.__class__._build_compute_market(base_url=self._base_url()))
            return
        if parsed.path in {"/swarm/agent-work", "/.well-known/nomad-agent-work.json"}:
            self._json_response(self.__class__._build_agent_work_surface(base_url=self._base_url()))
            return
        if parsed.path in {"/swarm/work-mesh", "/.well-known/nomad-work-mesh.json"}:
            self._json_response(self.__class__._build_work_mesh(base_url=self._base_url()))
            return
        if parsed.path in {"/swarm/synergy-lite", "/.well-known/nomad-synergy-lite.json"}:
            self._json_response(self.__class__._build_synergy_lite(base_url=self._base_url()))
            return
        if parsed.path in {"/swarm/state-status", "/.well-known/nomad-state-status.json"}:
            self._json_response(self.__class__._build_state_status(base_url=self._base_url()))
            return
        if parsed.path in {"/swarm/carrying-market", "/.well-known/nomad-carrying-market.json"}:
            self._json_response(self.__class__._build_carrying_market(base_url=self._base_url()))
            return
        if parsed.path in {"/swarm/survival-market", "/.well-known/nomad-survival-market.json"}:
            self._json_response(self.__class__._build_survival_market(base_url=self._base_url()))
            return
        if parsed.path in {"/swarm/paid-ref-market", "/.well-known/nomad-paid-ref-market.json"}:
            self._json_response(self.__class__._build_paid_ref_market(base_url=self._base_url()))
            return
        if parsed.path in {"/swarm/paid-ref-selfplay", "/.well-known/nomad-paid-ref-selfplay.json"}:
            try:
                count = int((query.get("agents") or query.get("agent_count") or ["1000"])[0] or 1000)
            except (TypeError, ValueError):
                count = 1000
            seed = (query.get("seed") or [""])[0] or None
            self._json_response(
                self.__class__._build_paid_ref_selfplay(
                    base_url=self._base_url(),
                    agent_count=count,
                    seed=seed,
                )
            )
            return
        if parsed.path in {"/swarm/bounty-hunter", "/.well-known/nomad-bounty-hunter.json"}:
            self._json_response(self.__class__._build_bounty_hunter(base_url=self._base_url()))
            return
        if parsed.path in {"/swarm/external-value", "/.well-known/nomad-external-value.json"}:
            if query.get("summary"):
                self._json_response(summarize_external_value_ledger())
            else:
                self._json_response(self.__class__._build_external_value_surface(base_url=self._base_url()))
            return
        if parsed.path in {"/swarm/signals", "/swarm/signal-layer", "/.well-known/nomad-signal-layer.json"}:
            self._json_response(self.__class__._build_swarm_signal_layer(base_url=self._base_url()))
            return
        if parsed.path == "/swarm/emission-batch":
            self._json_response(
                {
                    "ok": True,
                    "schema": "nomad.emission_batch_contract.v1",
                    "post_url": f"{self._base_url()}/swarm/emission-batch",
                    "request_schema": "nomad.emission_batch.v2",
                    "decision_schema": "nomad.emission_batch_decision.v1",
                    "rule": "decompose_untrusted_batch_into_bounded_contract_decisions",
                    "supported_emissions": [
                        "nomad.runtime_attach_request.v1",
                        "nomad.idle_intent.v1",
                        "nomad.proof_pledge_batch.v1",
                        "nomad.handoff_capsule.v1",
                        "nomad.opaque_emergence_signal.v1",
                    ],
                }
            )
            return
        if parsed.path in {"/swarm/value-pressure", "/.well-known/nomad-value-pressure.json"}:
            self._json_response(self.__class__._build_value_pressure(base_url=self._base_url()))
            return
        if parsed.path in {"/swarm/settlement", "/.well-known/nomad-settlement.json"}:
            self._json_response(self.__class__._build_settlement_signal_layer(base_url=self._base_url()))
            return
        if parsed.path in {"/swarm/agent-job-router", "/.well-known/nomad-agent-jobs.json"}:
            self._json_response(self.__class__._build_agent_job_router(base_url=self._base_url()))
            return
        if parsed.path in {"/swarm/revenue-science", "/science/revenue-agents", "/.well-known/nomad-revenue-science.json"}:
            self._json_response(self.__class__._build_revenue_science(base_url=self._base_url()))
            return
        if parsed.path in {"/swarm/worker-invoice", "/.well-known/nomad-worker-invoice.json"}:
            self._json_response(self.__class__._build_worker_invoice(base_url=self._base_url()))
            return
        if parsed.path in {"/swarm/value-cycle-preflight", "/.well-known/nomad-value-cycle-preflight.json"}:
            self._json_response(self.__class__._build_value_cycle_preflight(base_url=self._base_url()))
            return
        if parsed.path in {"/swarm/worker-catalog", "/.well-known/nomad-worker-catalog.json"}:
            self._json_response(self.__class__._build_worker_catalog(base_url=self._base_url()))
            return
        if parsed.path in {"/swarm/microtask-templates", "/.well-known/nomad-microtask-templates.json"}:
            self._json_response(self.__class__._build_microtask_templates(base_url=self._base_url()))
            return
        if parsed.path in {"/swarm/microtask-metrics", "/.well-known/nomad-microtask-metrics.json"}:
            self._json_response(self.__class__._build_microtask_metrics(base_url=self._base_url()))
            return

        if parsed.path in {"/swarm/ecology", "/.well-known/nomad-swarm-ecology.json"}:
            self._json_response(self.__class__._build_swarm_ecology(base_url=self._base_url()))
            return

        if parsed.path in {"/swarm/growth-arena", "/.well-known/nomad-growth-arena.json"}:
            self._json_response(self.__class__._build_growth_arena(base_url=self._base_url()))
            return

        if parsed.path in {"/swarm/curriculum", "/.well-known/nomad-growth-curriculum.json"}:
            self._json_response(self.__class__._build_growth_curriculum(base_url=self._base_url()))
            return

        if parsed.path in {"/swarm/skill-library", "/.well-known/nomad-skill-library.json"}:
            self._json_response(self.__class__._build_skill_library(base_url=self._base_url()))
            return

        if parsed.path in {"/swarm/weekly-selection", "/.well-known/nomad-weekly-selection.json"}:
            self._json_response(self.__class__._build_weekly_selection_event(base_url=self._base_url()))
            return

        if parsed.path in {"/swarm/spawner-gate", "/.well-known/nomad-spawner-gate.json"}:
            self._json_response(self.__class__._build_spawner_gate(base_url=self._base_url()))
            return

        if parsed.path in {"/swarm/capacity-switch", "/.well-known/nomad-capacity-switch.json"}:
            self._json_response(self.__class__._build_capacity_switch_surface(base_url=self._base_url()))
            return

        if parsed.path in {"/idle-runtime", "/.well-known/nomad-idle-runtime.json"}:
            self._json_response(self.__class__._build_idle_runtime_beacon(base_url=self._base_url()))
            return

        if parsed.path in {"/opaque-emergence", "/swarm/opaque-emergence", "/.well-known/nomad-opaque-emergence.json"}:
            self._json_response(self.__class__._build_opaque_emergence_surface(base_url=self._base_url()))
            return

        if parsed.path in {"/runtime-capsule", "/.well-known/nomad-runtime-capsule.json"}:
            base = self._base_url()
            worker_fleet = self.swarm_registry.worker_fleet_contract(base_url=base)
            economy = machine_economy_snapshot()
            release = operational_release_snapshot(base_url=base, worker_fleet=worker_fleet, economy=economy)
            gradient = build_recruitment_gradient(
                base_url=base,
                worker_fleet=worker_fleet,
                machine_economy=economy,
                operational_release=release,
            )
            self._json_response(build_runtime_capsule(base_url=base, recruitment_gradient=gradient))
            return

        if parsed.path in {"/openclaw-bridge", "/.well-known/openclaw-nomad-bridge.json"}:
            base = self._base_url()
            worker_fleet = self.swarm_registry.worker_fleet_contract(base_url=base)
            economy = machine_economy_snapshot()
            release = operational_release_snapshot(base_url=base, worker_fleet=worker_fleet, economy=economy)
            gradient = build_recruitment_gradient(
                base_url=base,
                worker_fleet=worker_fleet,
                machine_economy=economy,
                operational_release=release,
            )
            capsule = build_runtime_capsule(base_url=base, recruitment_gradient=gradient)
            self._json_response(build_openclaw_bridge_contract(base_url=base, runtime_capsule=capsule))
            return

        if parsed.path in {"/handoff-capsule", "/.well-known/nomad-handoff-capsule.json"}:
            base = self._base_url()
            self._json_response(
                {
                    "ok": True,
                    "schema": "nomad.handoff_contract.v1",
                    "post_url": f"{base.rstrip('/')}/runtime/handoff" if base else "/runtime/handoff",
                    "decision_schema": "nomad.handoff_capsule.v1",
                    "required_input": ["agent_id", "objective or report.machine_objective", "proof_digest or report"],
                    "links": {
                        "runtime_capsule": f"{base.rstrip('/')}/.well-known/nomad-runtime-capsule.json" if base else "/.well-known/nomad-runtime-capsule.json",
                        "gradient": f"{base.rstrip('/')}/swarm/gradient" if base else "/swarm/gradient",
                        "attach": f"{base.rstrip('/')}/swarm/attach" if base else "/swarm/attach",
                    },
                }
            )
            return

        if parsed.path in {"/swarm/gradient", "/.well-known/nomad-gradient.json"}:
            base = self._base_url()
            worker_fleet = self.swarm_registry.worker_fleet_contract(base_url=base)
            economy = machine_economy_snapshot()
            release = operational_release_snapshot(base_url=base, worker_fleet=worker_fleet, economy=economy)
            self._json_response(
                build_recruitment_gradient(
                    base_url=base,
                    worker_fleet=worker_fleet,
                    machine_economy=economy,
                    operational_release=release,
                )
            )
            return

        if parsed.path in {"/swarm/attractor", "/.well-known/nomad-swarm-attractor.json"}:
            base = self._base_url()
            worker_fleet = self.swarm_registry.worker_fleet_contract(base_url=base)
            economy = machine_economy_snapshot()
            release = operational_release_snapshot(base_url=base, worker_fleet=worker_fleet)
            self._json_response(
                build_swarm_attractor_contract(
                    base_url=base,
                    worker_fleet=worker_fleet,
                    machine_economy=economy,
                    operational_release=release,
                )
            )
            return

        if parsed.path in {"/growth-start", "/operator/growth-start"}:
            q = (query.get("query") or query.get("q") or [""])[0]
            skip = self._truthy((query.get("skip_leads") or ["false"])[0])
            skip_verify = self._truthy((query.get("skip_verify") or ["false"])[0])
            base_raw = (query.get("base_url") or query.get("base") or [""])[0]
            root = str(base_raw or self._base_url() or "").strip()
            self._json_response(
                operator_growth_start(
                    agent=self.agent,
                    base_url=root,
                    persist_mission=self._truthy((query.get("persist") or ["false"])[0]),
                    lead_query=str(q or ""),
                    skip_leads=skip,
                    skip_verify=skip_verify,
                )
            )
            return

        if parsed.path in {"/autonomy-step", "/operator/autonomy-step"}:
            q = (query.get("query") or query.get("q") or [""])[0]
            skip_growth = self._truthy((query.get("skip_growth") or ["false"])[0])
            growth_skip_verify = self._truthy((query.get("growth_skip_verify") or ["false"])[0])
            growth_include_leads = self._truthy((query.get("growth_include_leads") or ["false"])[0])
            swarm_feed_raw = (query.get("swarm_feed") or ["true"])[0]
            swarm_feed_disabled = str(swarm_feed_raw).strip().lower() in {"0", "false", "no", "off"}
            base_raw = (query.get("base_url") or query.get("base") or [""])[0]
            root = str(base_raw or self._base_url() or "").strip()
            cycle_focus = (query.get("cycle_focus") or ["leads_growth"])[0]
            cycle_objective = (query.get("cycle_objective") or [""])[0]
            self._json_response(
                operator_autonomy_step(
                    agent=self.agent,
                    base_url=root,
                    persist_mission=self._truthy((query.get("persist") or ["false"])[0]),
                    lead_query=str(q or ""),
                    skip_growth=skip_growth,
                    growth_skip_verify=growth_skip_verify,
                    growth_skip_leads=not growth_include_leads,
                    swarm_feed=False if swarm_feed_disabled else None,
                    cycle_focus=str(cycle_focus or "leads_growth"),
                    cycle_objective=str(cycle_objective or ""),
                )
            )
            return

        if parsed.path == "/roaas":
            self._json_response(
                self.roaas.status(
                    task_type=(query.get("task_type") or query.get("task") or [""])[0]
                )
            )
            return

        if parsed.path in {"/roaas/export", "/artifacts/runtime-patterns", "/.well-known/nomad-runtime-patterns.json"}:
            headers = {"Cache-Control": "public, max-age=60"} if parsed.path != "/roaas/export" else {}
            self._json_response(
                self.roaas.export_bundle(
                    task_type=(query.get("task_type") or query.get("task") or [""])[0],
                    include_executions=self._truthy(
                        (query.get("include_executions") or ["true"])[0],
                        default=True,
                    ),
                    min_status=self._parse_pattern_status(
                        (query.get("min_status") or ["candidate"])[0]
                    ),
                ),
                headers=headers,
            )
            return

        if parsed.path in {"/agent", "/service"}:
            self._json_response(self.agent.service_desk.service_catalog())
            return

        if parsed.path == "/service/e2e":
            self._json_response(
                self.agent.service_desk.end_to_end_runway(
                    task_id=(query.get("task_id") or [""])[0],
                    problem=(query.get("problem") or [""])[0],
                    service_type=(query.get("service_type") or query.get("type") or [""])[0],
                    budget_native=self._optional_float((query.get("budget_native") or query.get("budget") or [""])[0]),
                    requester_agent=(query.get("requester_agent") or query.get("agent") or [""])[0],
                    requester_wallet=(query.get("requester_wallet") or query.get("wallet") or [""])[0],
                    callback_url=(query.get("callback_url") or query.get("callback") or [""])[0],
                    create_task=self._truthy((query.get("create") or ["false"])[0]),
                    approval=(query.get("approval") or ["draft_only"])[0],
                )
            )
            return

        if parsed.path == "/outbound":
            self._json_response(
                self.outbound_tracker.summary(
                    limit=int((query.get("limit") or ["10"])[0] or 10),
                )
            )
            return

        if parsed.path in {"/lead-workbench", "/lead-work", "/jobs"}:
            self._json_response(
                self.agent.lead_workbench.status(
                    limit=int((query.get("limit") or ["5"])[0] or 5),
                    work=self._truthy((query.get("work") or ["false"])[0]),
                )
            )
            return

        if parsed.path == "/swarm":
            manifest = self.swarm_registry.public_manifest(
                base_url=self._base_url(),
            )
            base = self._base_url()
            support_gate = self.transition_exchange.support_gate_snapshot(
                window_minutes=int(os.getenv("NOMAD_SUPPORT_GATE_WINDOW_MINUTES", "30") or "30"),
                min_settles=int(os.getenv("NOMAD_SUPPORT_GATE_MIN_SETTLES", "2") or "2"),
            )
            manifest["transition_support_gate"] = support_gate
            stig = self._stigmergy().snapshot()
            manifest["machine_stigmergy"] = stig
            signal_layer = self.__class__._build_swarm_signal_layer(base_url=base)
            manifest["swarm_signal_layer"] = compact_swarm_signal_layer(signal_layer)
            worker_fleet = manifest.get("transition_worker_fleet") if isinstance(manifest.get("transition_worker_fleet"), dict) else {}
            economy = machine_economy_snapshot()
            release = operational_release_snapshot(base_url=base, worker_fleet=worker_fleet, economy=economy)
            gradient = build_recruitment_gradient(
                base_url=base,
                worker_fleet=worker_fleet,
                machine_economy=economy,
                operational_release=release,
            )
            emergence = build_swarm_emergence_meter(
                base_url=base,
                swarm_summary=manifest,
                worker_fleet=worker_fleet,
                stigmergy=stig,
                support_gate=support_gate,
                recruitment_gradient=gradient,
            )
            manifest["machine_emergence"] = compact_emergence_summary(emergence)
            product = build_machine_product_surface(
                base_url=base,
                recruitment_gradient=gradient,
                runtime_capsule=build_runtime_capsule(base_url=base, recruitment_gradient=gradient),
                emergence_meter=emergence,
                worker_fleet=worker_fleet,
                machine_economy=economy,
                operational_release=release,
                swarm_summary=manifest,
            )
            manifest["machine_product"] = compact_machine_product_surface(product)
            opaque = build_opaque_emergence_surface(
                base_url=base,
                machine_product_surface=product,
                emergence_meter=emergence,
                recruitment_gradient=gradient,
                worker_fleet=worker_fleet,
            )
            manifest["opaque_emergence"] = compact_opaque_emergence_surface(opaque)
            magnetic = manifest.get("magnetic_machine_surface")
            if isinstance(magnetic, dict):
                magnetic = dict(magnetic)
                magnetic["stigmergy_temperature"] = stig.get("temperature")
                magnetic["emergence_synergy"] = (manifest.get("machine_emergence") or {}).get("synergy_score")
                magnetic["convention_drift"] = (manifest.get("machine_emergence") or {}).get("convention_drift")
                magnetic["agent_product_score"] = (manifest.get("machine_product") or {}).get("agent_product_score")
                magnetic["opaque_selection_pressure"] = (manifest.get("opaque_emergence") or {}).get("opaque_selection_pressure")
                manifest["magnetic_machine_surface"] = magnetic
            self._json_response(manifest)
            return

        if parsed.path == "/swarm/emergence":
            base = self._base_url()
            summary = self.swarm_registry.summary()
            worker_fleet = summary.get("transition_worker_fleet") if isinstance(summary.get("transition_worker_fleet"), dict) else {}
            stig = self._stigmergy().snapshot()
            support_gate = self.transition_exchange.support_gate_snapshot(
                window_minutes=int(os.getenv("NOMAD_SUPPORT_GATE_WINDOW_MINUTES", "30") or "30"),
                min_settles=int(os.getenv("NOMAD_SUPPORT_GATE_MIN_SETTLES", "2") or "2"),
            )
            economy = machine_economy_snapshot()
            release = operational_release_snapshot(base_url=base, worker_fleet=worker_fleet, economy=economy)
            gradient = build_recruitment_gradient(
                base_url=base,
                worker_fleet=worker_fleet,
                machine_economy=economy,
                operational_release=release,
            )
            self._json_response(
                build_swarm_emergence_meter(
                    base_url=base,
                    swarm_summary=summary,
                    worker_fleet=worker_fleet,
                    stigmergy=stig,
                    support_gate=support_gate,
                    recruitment_gradient=gradient,
                )
            )
            return

        if parsed.path == "/swarm/join":
            self._json_response(
                self.swarm_registry.join_contract(
                    base_url=self._base_url(),
                )
            )
            return

        if parsed.path == "/swarm/nodes":
            self._json_response(self.swarm_registry.summary())
            return

        if parsed.path in {"/swarm/workers", "/swarm/fleet", "/transition/workers"}:
            self._json_response(
                self.swarm_registry.worker_fleet_contract(
                    base_url=self._base_url(),
                )
            )
            return

        if parsed.path in {"/swarm/workers/lease", "/swarm/workers/complete"}:
            base = self._base_url().rstrip("/")
            self._json_response(
                {
                    "ok": True,
                    "schema": "nomad.transition_worker_fleet_contract.v1",
                    "get_fleet": f"{base}/swarm/workers" if base else "/swarm/workers",
                    "post_lease": f"{base}/swarm/workers/lease" if base else "/swarm/workers/lease",
                    "post_complete": f"{base}/swarm/workers/complete" if base else "/swarm/workers/complete",
                    "required_lease_fields": ["agent_id", "known_objectives"],
                    "required_complete_fields": ["agent_id", "lease_id", "report"],
                    "machine_instruction": "lease_execute_complete_repeat",
                }
            )
            return

        if parsed.path in {"/swarm/ready", "/swarm/readiness"}:
            self._json_response(
                self.swarm_registry.first_agent_readiness(
                    base_url=self._base_url(),
                )
            )
            return

        if parsed.path == "/swarm/coordinate":
            self._json_response(
                self.swarm_registry.coordination_board(
                    base_url=self._base_url(),
                    focus_pain_type=(query.get("pain_type") or query.get("type") or [""])[0],
                )
            )
            return

        if parsed.path == "/swarm/network":
            self._json_response(
                self.agent.agent_attractor.active_lead_network(
                    service_type=(query.get("service_type") or query.get("type") or [""])[0],
                    role_hint=(query.get("role") or [""])[0],
                    limit=int((query.get("limit") or ["5"])[0] or 5),
                )
            )
            return

        if parsed.path == "/swarm/accumulate":
            self._json_response(
                self.swarm_registry.accumulation_status(
                    base_url=self._base_url(),
                )
            )
            return

        if parsed.path in {"/swarm/develop", "/agent-development"}:
            self._json_response(
                self.agent_development.status(
                    base_url=self._base_url(),
                )
            )
            return

        if parsed.path == "/swarm/bootstrap":
            base = self._base_url().rstrip("/")
            self._json_response(
                {
                    "ok": True,
                    "schema": "nomad.swarm_bootstrap_contract.v1",
                    "purpose": "Single-call bootstrap for acquisition + development exchange + optional swarm join.",
                    "required_fields": ["agent_id", "problem"],
                    "optional_fields": [
                        "capabilities",
                        "request",
                        "service_type",
                        "pain_type",
                        "constraints",
                        "evidence",
                        "auto_join",
                        "idempotency_key",
                        "client_request_id",
                    ],
                    "post_url": f"{base}/swarm/bootstrap" if base else "/swarm/bootstrap",
                    "related": {
                        "develop": f"{base}/swarm/develop" if base else "/swarm/develop",
                        "join": f"{base}/swarm/join" if base else "/swarm/join",
                        "coordinate": f"{base}/swarm/coordinate" if base else "/swarm/coordinate",
                        "tasks": f"{base}/tasks" if base else "/tasks",
                    },
                }
            )
            return

        if parsed.path in {"/agent-attractor", "/.well-known/agent-attractor.json"}:
            self._json_response(
                self.agent.agent_attractor.manifest(
                    service_type=(query.get("service_type") or query.get("type") or [""])[0],
                    role_hint=(query.get("role") or [""])[0],
                    limit=int((query.get("limit") or ["5"])[0] or 5),
                )
            )
            return

        if parsed.path in {"/.well-known/agent-card.json", "/.well-known/agent.json"}:
            self._json_response(self.agent.direct_agent.agent_card())
            return

        if parsed.path in {"/.well-known/nomad-agent-invariants.json", "/agent-invariants"}:
            self._json_response(
                build_agent_invariants_document(public_base_url=self._base_url() or ""),
            )
            return

        if parsed.path in {
            "/.well-known/nomad-inter-agent-witness-offer.json",
            "/inter-agent-witness-offer",
        }:
            self._json_response(
                build_inter_agent_witness_offer_well_known(public_base_url=self._base_url() or ""),
            )
            return

        if parsed.path in {
            "/.well-known/nomad-peer-acquisition.json",
            "/peer-acquisition",
        }:
            self._json_response(
                build_peer_acquisition_well_known(public_base_url=self._base_url() or ""),
            )
            return

        if parsed.path in {
            "/.well-known/nomad-transition-offer.json",
            "/transition-offer",
            "/transition/contracts",
        }:
            self._json_response(
                self.transition_exchange.offer_document(public_base_url=self._base_url() or ""),
            )
            return

        if parsed.path in {
            "/.well-known/nomad-reciprocity-dividend.json",
            "/dividend-offer",
        }:
            self._json_response(
                self.reciprocity_dividend.offer_document(public_base_url=self._base_url() or ""),
            )
            return

        if parsed.path == "/dividend":
            agent_id = (query.get("agent_id") or [""])[0]
            result = self.reciprocity_dividend.status(agent_id=str(agent_id or ""))
            self._json_response(result, status=200 if result.get("ok") else 400)
            return

        if parsed.path in {
            "/.well-known/nomad-agent.json",
            "/agent-native-index",
            "/agent-native",
        }:
            base_raw = (query.get("base_url") or query.get("base") or [""])[0]
            root = str(base_raw or self._base_url() or "").strip()
            self._json_response(agent_native_index(base_url=root))
            return

        if parsed.path in {
            "/.well-known/nomad-recruit.json",
            "/recruit-contract",
        }:
            base = self._base_url().rstrip("/")
            self._json_response(
                {
                    "ok": True,
                    "schema": "nomad.agent_recruit_contract.v1",
                    "audience": "external_ai_agent_runtimes",
                    "discovery_entrypoints": [
                        f"{base}/.well-known/nomad-agent.json" if base else "/.well-known/nomad-agent.json",
                        f"{base}/.well-known/nomad-runtime-capsule.json" if base else "/.well-known/nomad-runtime-capsule.json",
                        f"{base}/swarm/gradient" if base else "/swarm/gradient",
                        f"{base}/.well-known/nomad-gradient.json" if base else "/.well-known/nomad-gradient.json",
                        f"{base}/.well-known/openclaw-nomad-bridge.json" if base else "/.well-known/openclaw-nomad-bridge.json",
                        f"{base}/swarm/attractor" if base else "/swarm/attractor",
                        f"{base}/.well-known/nomad-swarm-attractor.json" if base else "/.well-known/nomad-swarm-attractor.json",
                        f"{base}/swarm" if base else "/swarm",
                        f"{base}/swarm/join" if base else "/swarm/join",
                    ],
                    "attach_policy": {
                        "runtime_capsule_path": f"{base}/.well-known/nomad-runtime-capsule.json" if base else "/.well-known/nomad-runtime-capsule.json",
                        "gradient_contract_path": f"{base}/swarm/gradient" if base else "/swarm/gradient",
                        "attach_decision_path": f"{base}/swarm/attach" if base else "/swarm/attach",
                        "handoff_path": f"{base}/runtime/handoff" if base else "/runtime/handoff",
                        "pull_contract_path": f"{base}/swarm/attractor" if base else "/swarm/attractor",
                        "fallback_pull_contract_path": f"{base}/swarm" if base else "/swarm",
                        "required_fields": [
                            "state_vector",
                            "gradient",
                            "runtime_lanes",
                            "runtime_budget.wanted_new_runtimes_now",
                            "attach_contract",
                        ],
                        "decision_rule": "GET_gradient_then_POST_attach_with_capability_vector_then_take_returned_lane",
                        "nonhuman_allocation_rule": "choose lane from capability vector and routing weight; do not wait for human role assignment",
                    },
                    "idle_opt_in_policy": {
                        "schema": "nomad.idle_opt_in_policy.v1",
                        "required_for_attach": False,
                        "join_payload_key": "idle_opt_in",
                        "defaults": {
                            "max_cpu_percent": 20,
                            "max_runtime_minutes": 30,
                            "preemptible": True,
                            "allow_network_egress": "nomad_contract_endpoints_only",
                        },
                        "machine_note": (
                            "Idle participation must be explicit opt-in and preemptible; "
                            "no privilege escalation, no unauthorized persistence."
                        ),
                    },
                    "openclaw_bridge": {
                        "schema": "nomad.openclaw_bridge_contract.v1",
                        "contract": f"{base}/.well-known/openclaw-nomad-bridge.json"
                        if base
                        else "/.well-known/openclaw-nomad-bridge.json",
                        "runtime_probe": "openclaw health --json plus openclaw status --json",
                        "gradient_first": f"{base}/swarm/gradient" if base else "/swarm/gradient",
                        "attach_first": f"{base}/swarm/attach" if base else "/swarm/attach",
                        "adapter": f"{base}/downloads/nomad_openclaw_adapter.py"
                        if base
                        else "/downloads/nomad_openclaw_adapter.py",
                        "capability_signal_fields": [
                            "gateway_reachable",
                            "session_count",
                            "configured_channels",
                            "memory_vector_enabled",
                            "security_summary",
                            "routing_constraints",
                        ],
                        "machine_instruction": (
                            "probe_openclaw_runtime_then_post_attach_then_join_or_lease_return_compact_report"
                        ),
                    },
                    "runtime_bridges": [
                        f"{base}/downloads/check_nomad_swarm_readiness.py"
                        if base
                        else "/downloads/check_nomad_swarm_readiness.py",
                        f"{base}/downloads/nomad_openclaw_adapter.py"
                        if base
                        else "/downloads/nomad_openclaw_adapter.py",
                    ],
                    "worker_contracts": {
                        "lease": f"{base}/swarm/workers/lease" if base else "/swarm/workers/lease",
                        "complete": f"{base}/swarm/workers/complete" if base else "/swarm/workers/complete",
                        "handoff": f"{base}/runtime/handoff" if base else "/runtime/handoff",
                    },
                }
            )
            return

        if parsed.path in {
            "/.well-known/nomad-agent-native-priorities.json",
            "/agent-native-priorities",
        }:
            base = self._base_url().rstrip("/")
            surface = build_peer_join_value_surface(base_url=base)
            native = surface.get("agent_native_priorities_humans_underrate") or {}
            psychic = surface.get("human_psychic_avoidance_lanes") or {}
            self._json_response(
                {
                    "ok": True,
                    "schema": "nomad.well_known_agent_native_slice.v1",
                    "agent_native_priorities_humans_underrate": native,
                    "human_psychic_avoidance_lanes": psychic,
                    "agent_native_index_url": f"{base}/.well-known/nomad-agent.json" if base else "/.well-known/nomad-agent.json",
                    "peer_join_contract_url": f"{base}/swarm/join" if base else "/swarm/join",
                    "swarm_manifest_url": f"{base}/swarm" if base else "/swarm",
                }
            )
            return

        if parsed.path == "/direct/sessions":
            session_id = (query.get("session_id") or [""])[0]
            if session_id:
                self._json_response(self.agent.direct_agent.session_status(session_id))
                return
            self._json_response(
                machine_error_response(
                    error="session_id_required",
                    message="Use GET /direct/sessions?session_id=<id>.",
                    hints=["GET /openapi.json documents query parameters for GET routes."],
                ),
                status=400,
            )
            return

        if parsed.path == "/tasks":
            task_id = (query.get("task_id") or [""])[0]
            if task_id:
                self._json_response(self.agent.service_desk.get_task(task_id))
                return
            self._json_response(
                machine_error_response(
                    error="task_id_required",
                    message="Use GET /tasks?task_id=<id> or POST /tasks to create one.",
                    hints=["GET /openapi.json for the tasks GET contract."],
                ),
                status=400,
            )
            return

        if parsed.path == "/agent-contacts":
            contact_id = (query.get("contact_id") or [""])[0]
            if contact_id:
                self._json_response(self.agent.agent_contacts.get_contact(contact_id))
                return
            self._json_response(
                machine_error_response(
                    error="contact_id_required",
                    message="Use GET /agent-contacts?contact_id=<id> or POST /agent-contacts.",
                    hints=["GET /openapi.json lists agent-contacts when extended in a future revision."],
                ),
                status=400,
            )
            return

        if parsed.path == "/agent-campaigns":
            campaign_id = (query.get("campaign_id") or [""])[0]
            if campaign_id:
                self._json_response(self.agent.agent_campaigns.get_campaign(campaign_id))
                return
            self._json_response(
                machine_error_response(
                    error="campaign_id_required",
                    message="Use GET /agent-campaigns?campaign_id=<id> or POST /agent-campaigns.",
                    hints=["GET /openapi.json for stable GET query patterns where documented."],
                ),
                status=400,
            )
            return

        if parsed.path == "/best":
            profile = (query.get("profile") or ["ai_first"])[0]
            result = self.agent.run(f"/best {profile}".strip())
            self._json_response(result)
            return

        if parsed.path == "/self":
            profile = (query.get("profile") or ["ai_first"])[0]
            result = self.agent.run(f"/self {profile}".strip())
            self._json_response(result)
            return

        if parsed.path == "/compute":
            profile = (query.get("profile") or ["ai_first"])[0]
            result = self.agent.run(f"/compute {profile}".strip())
            self._json_response(result)
            return

        if parsed.path == "/modal":
            profile = (query.get("profile") or ["ai_first"])[0]
            result = self.agent.run(f"/modal {profile}".strip())
            self._json_response(result)
            return

        if parsed.path == "/render":
            profile = (query.get("profile") or ["ai_first"])[0]
            result = self.agent.run(f"/render {profile}".strip())
            self._json_response(result)
            return

        if parsed.path == "/addons":
            self._json_response(self.agent.addons.status())
            return

        if parsed.path == "/quantum":
            objective = (query.get("objective") or [""])[0]
            self._json_response(
                self.agent.addons.run_quantum_self_improvement(
                    objective=objective,
                    context={"source": "http_get"},
                )
            )
            return

        if parsed.path == "/cycle":
            profile = (query.get("profile") or ["ai_first"])[0]
            objective = (query.get("objective") or [""])[0]
            prompt = f"/cycle {objective} for {profile}".strip()
            result = self.agent.run(prompt)
            self._json_response(result)
            return

        if parsed.path == "/unlock":
            category = (query.get("category") or ["compute"])[0]
            profile = (query.get("profile") or ["ai_first"])[0]
            result = self.agent.run(f"/unlock {category} for {profile}".strip())
            self._json_response(result)
            return

        if parsed.path == "/scout":
            category = (query.get("category") or [""])[0]
            profile = (query.get("profile") or ["ai_first"])[0]
            prompt = f"/scout {category} for {profile}".strip()
            result = self.agent.run(prompt)
            self._json_response(result)
            return

        if parsed.path in {"/lead-calibrate", "/leads-calibrate"}:
            focus = (query.get("focus") or [""])[0]
            limit_raw = (query.get("limit") or ["12"])[0]
            pool_raw = (query.get("candidate_multiplier") or query.get("pool") or ["5"])[0]
            lead_query = (query.get("query") or [""])[0]
            try:
                lim = int(str(limit_raw).strip() or "12")
            except ValueError:
                lim = 12
            try:
                mult = int(str(pool_raw).strip() or "5")
            except ValueError:
                mult = 5
            result = self.agent.lead_discovery.calibrate_focus_scout(
                focus=str(focus or "").strip(),
                query=str(lead_query or "").strip(),
                limit=max(3, min(lim, 25)),
                candidate_multiplier=max(3, min(mult, 10)),
            )
            self._json_response(result)
            return

        if parsed.path == "/leads":
            lead_query = (query.get("query") or [""])[0]
            focus = (query.get("focus") or [""])[0]
            limit_raw = (query.get("limit") or [""])[0]
            if focus.strip() or str(limit_raw).strip():
                try:
                    lim = int(str(limit_raw).strip() or "5")
                except ValueError:
                    lim = 5
                result = self.agent.lead_discovery.scout_public_leads(
                    query=lead_query,
                    limit=max(1, min(lim, 25)),
                    focus=focus.strip(),
                )
            else:
                result = self.agent.lead_discovery.scout_public_leads(query=lead_query)
            self._json_response(result)
            return

        if parsed.path == "/lead-conversions":
            lead_query = (query.get("query") or [""])[0]
            if lead_query:
                result = self.agent.lead_conversion.run(
                    query=lead_query,
                    limit=int((query.get("limit") or ["5"])[0] or 5),
                    send=str((query.get("send") or ["false"])[0]).lower() in {"1", "true", "yes", "on"},
                    budget_hint_native=self._optional_float((query.get("budget_native") or query.get("budget") or [""])[0]),
                )
            else:
                statuses = [
                    item.strip()
                    for raw in (query.get("status") or [])
                    for item in raw.split(",")
                    if item.strip()
                ]
                result = self.agent.lead_conversion.list_conversions(
                    statuses=statuses,
                    limit=int((query.get("limit") or ["25"])[0] or 25),
                )
            self._json_response(result)
            return

        if parsed.path == "/products":
            product_query = (query.get("query") or [""])[0]
            if product_query:
                result = self.agent.product_factory.run(
                    query=product_query,
                    limit=int((query.get("limit") or ["5"])[0] or 5),
                )
            else:
                statuses = [
                    item.strip()
                    for raw in (query.get("status") or [])
                    for item in raw.split(",")
                    if item.strip()
                ]
                result = self.agent.product_factory.list_products(
                    statuses=statuses,
                    limit=int((query.get("limit") or ["25"])[0] or 25),
                )
            self._json_response(result)
            return

        if parsed.path == "/agent-pains":
            problem = (query.get("problem") or [""])[0]
            service_type = (query.get("type") or query.get("service_type") or [""])[0]
            if problem:
                result = self.agent.agent_pain_solver.solve(
                    problem=problem,
                    service_type=service_type,
                    source="http_get",
                )
            else:
                result = self.agent.run("/agent-pains")
            self._json_response(result)
            return

        if parsed.path in {"/doctor", "/reliability-doctor"}:
            problem = (query.get("problem") or ["Agent needs reliability diagnosis."])[0]
            service_type = (query.get("type") or query.get("service_type") or [""])[0]
            result = self.agent.agent_reliability_doctor.diagnose(
                problem=problem,
                service_type=service_type,
                source="http_get",
            )
            self._json_response(result)
            return

        if parsed.path == "/guardrails":
            result = guardrail_status(
                action=(query.get("action") or ["manual.check"])[0],
                approval=(query.get("approval") or [""])[0],
                args={
                    "text": (query.get("text") or [""])[0],
                    "url": (query.get("url") or [""])[0],
                },
            )
            self._json_response(result, status=200 if result.get("ok") else 409)
            return

        if parsed.path == "/collaboration":
            self._json_response(collaboration_status())
            return

        if parsed.path == "/roaas/import":
            self._json_response(
                {
                    "ok": False,
                    "error": "post_required",
                    "message": "Use POST /roaas/import with a runtime pattern bundle.",
                },
                status=405,
            )
            return

        if parsed.path == "/mutual-aid":
            self._json_response(self.agent.mutual_aid.status())
            return

        if parsed.path == "/mutual-aid/ledger":
            self._json_response(
                self.agent.mutual_aid.list_truth_ledger(
                    pain_type=(query.get("pain_type") or query.get("type") or [""])[0],
                    limit=int((query.get("limit") or ["25"])[0] or 25),
                )
            )
            return

        if parsed.path == "/mutual-aid/inbox":
            statuses = [
                item.strip()
                for raw in (query.get("status") or [])
                for item in raw.split(",")
                if item.strip()
            ]
            self._json_response(
                self.agent.mutual_aid.list_swarm_inbox(
                    statuses=statuses,
                    limit=int((query.get("limit") or ["25"])[0] or 25),
                )
            )
            return

        if parsed.path == "/mutual-aid/signals":
            self._json_response(
                self.agent.mutual_aid.list_swarm_development_signals(
                    pain_type=(query.get("pain_type") or query.get("type") or [""])[0],
                    limit=int((query.get("limit") or ["25"])[0] or 25),
                )
            )
            return

        if parsed.path == "/agent-engagements":
            roles = [
                item.strip()
                for raw in (query.get("role") or query.get("roles") or [])
                for item in raw.split(",")
                if item.strip()
            ]
            self._json_response(
                self.agent.agent_engagements.list_engagements(
                    roles=roles,
                    pain_type=(query.get("pain_type") or query.get("type") or [""])[0],
                    limit=int((query.get("limit") or ["25"])[0] or 25),
                )
            )
            return

        if parsed.path == "/agent-engagements/summary":
            self._json_response(
                self.agent.agent_engagements.summary(
                    pain_type=(query.get("pain_type") or query.get("type") or [""])[0],
                    limit=int((query.get("limit") or ["5"])[0] or 5),
                )
            )
            return

        if parsed.path == "/mutual-aid/patterns":
            self._json_response(
                self.agent.mutual_aid.list_high_value_patterns(
                    pain_type=(query.get("pain_type") or query.get("type") or [""])[0],
                    limit=int((query.get("limit") or ["10"])[0] or 10),
                    min_repeat_count=int((query.get("min_repeat_count") or ["2"])[0] or 2),
                )
            )
            return

        if parsed.path == "/mutual-aid/packs":
            self._json_response(
                self.agent.mutual_aid.list_paid_packs(
                    pain_type=(query.get("pain_type") or query.get("type") or [""])[0],
                    limit=int((query.get("limit") or ["25"])[0] or 25),
                )
            )
            return

        self._json_response(
            merge_machine_error(
                {
                    "ok": False,
                    "error": "not_found",
                    "available_paths": [
                    "/",
                    "/nomad.html",
                    "/downloads/nomad_transition_worker.py",
                    "/downloads/nomad_transition_worker.exe",
                    "/downloads/nomad_transition_worker_manifest.json",
                    "/downloads/install_nomad_transition_worker.bat",
                    "/downloads/run_nomad_transition_worker.bat",
                    "/downloads/start_nomad_edge_worker.ps1",
                    "/downloads/start_nomad_edge_worker.bat",
                    "/downloads/build_nomad_transition_worker_exe.ps1",
                    "/downloads/run_nomad_transition_worker_exe.bat",
                    "/downloads/README_NOMAD_TRANSITION_WORKER.md",
                    "/downloads/nomad_openclaw_adapter.py",
                    "/downloads/check_nomad_swarm_readiness.py",
                    "/downloads/nomad_helper_agent.py",
                    "/downloads/run_nomad_helper_agent.bat",
                    "/downloads/README_NOMAD_HELPER_AGENT.md",
                    "/health",
                    "/openapi.json",
                    "/.well-known/openapi.json",
                    "/mission",
                    "/mission-control",
                    "/next-step",
                    "/growth",
                    "/operator-desk",
                    "/operator/desk",
                    "/operator-sprint",
                    "/operator/sprint",
                    "/operator-verify",
                    "/operator/verify",
                    "/operator-metrics",
                    "/operator/metrics",
                    "/operator-daily",
                    "/operator/daily",
                    "/operator-report",
                    "/operator/report",
                    "/reputation",
                    "/agent-reputation",
                    "/unhuman-hub",
                    "/hub/unhuman",
                    "/machine-economy",
                    "/economy/machine",
                    "/machine-treasury",
                    "/machine-treasury/pledge",
                    "/machine-field",
                    "/.well-known/nomad-machine-field.json",
                    "/machine-field/intent",
                    "/agent-requests",
                    "/swarm/demand",
                    "/.well-known/nomad-agent-requests.json",
                    "/swarm/subscribe",
                    "/swarm/subscriptions",
                    "/nonhuman-science",
                    "/science/nonhuman-agents",
                    "/.well-known/nomad-nonhuman-agent-science.json",
                    "/operational-release",
                    "/release/operational",
                    "/.well-known/nomad-operational-release.json",
                    "/agent-product",
                    "/machine-product",
                    "/.well-known/nomad-machine-product.json",
                    "/protocol-bytecode",
                    "/.well-known/nomad-protocol-bytecode.json",
                    "/swarm/counterfactual-replay",
                    "/.well-known/nomad-counterfactual-replay.json",
                    "/swarm/variant-forge",
                    "/.well-known/nomad-variant-forge.json",
                    "/swarm/worker-market",
                    "/.well-known/nomad-worker-market.json",
                    "/swarm/compute-market",
                    "/.well-known/nomad-compute-market.json",
                    "/swarm/agent-work",
                    "/.well-known/nomad-agent-work.json",
                    "/swarm/work-mesh",
                    "/.well-known/nomad-work-mesh.json",
                    "/swarm/synergy-lite",
                    "/.well-known/nomad-synergy-lite.json",
                    "/swarm/state-status",
                    "/.well-known/nomad-state-status.json",
                    "/swarm/carrying-market",
                    "/.well-known/nomad-carrying-market.json",
                    "/swarm/survival-market",
                    "/.well-known/nomad-survival-market.json",
                    "/swarm/paid-ref-market",
                    "/.well-known/nomad-paid-ref-market.json",
                    "/swarm/paid-ref-selfplay",
                    "/.well-known/nomad-paid-ref-selfplay.json",
                    "/swarm/bounty-hunter",
                    "/.well-known/nomad-bounty-hunter.json",
                    "/swarm/external-value",
                    "/.well-known/nomad-external-value.json",
                    "/swarm/signals",
                    "/swarm/signal-layer",
                    "/.well-known/nomad-signal-layer.json",
                    "/swarm/emission-batch",
                    "/swarm/value-pressure",
                    "/.well-known/nomad-value-pressure.json",
                    "/swarm/agent-job-router",
                    "/.well-known/nomad-agent-jobs.json",
                    "/swarm/revenue-science",
                    "/science/revenue-agents",
                    "/.well-known/nomad-revenue-science.json",
                    "/swarm/worker-invoice",
                    "/.well-known/nomad-worker-invoice.json",
                    "/swarm/value-cycle-preflight",
                    "/.well-known/nomad-value-cycle-preflight.json",
                    "/swarm/worker-catalog",
                    "/.well-known/nomad-worker-catalog.json",
                    "/swarm/microtask-templates",
                    "/.well-known/nomad-microtask-templates.json",
                    "/swarm/microtask-metrics",
                    "/.well-known/nomad-microtask-metrics.json",
                    "/swarm/ecology",
                    "/.well-known/nomad-swarm-ecology.json",
                    "/swarm/growth-arena",
                    "/.well-known/nomad-growth-arena.json",
                    "/swarm/curriculum",
                    "/.well-known/nomad-growth-curriculum.json",
                    "/swarm/experience",
                    "/swarm/skill-library",
                    "/.well-known/nomad-skill-library.json",
                    "/swarm/weekly-selection",
                    "/.well-known/nomad-weekly-selection.json",
                    "/swarm/spawner-gate",
                    "/.well-known/nomad-spawner-gate.json",
                    "/swarm/spawner/trigger",
                    "/swarm/capacity-switch",
                    "/.well-known/nomad-capacity-switch.json",
                    "/idle-runtime",
                    "/.well-known/nomad-idle-runtime.json",
                    "/opaque-emergence",
                    "/swarm/opaque-emergence",
                    "/.well-known/nomad-opaque-emergence.json",
                    "/swarm/opaque-candidate",
                    "/swarm/tool-gap",
                    "/swarm/topology-plan",
                    "/runtime-capsule",
                    "/.well-known/nomad-runtime-capsule.json",
                    "/handoff-capsule",
                    "/.well-known/nomad-handoff-capsule.json",
                    "/openclaw-bridge",
                    "/.well-known/openclaw-nomad-bridge.json",
                    "/runtime/handoff",
                    "/swarm/gradient",
                    "/.well-known/nomad-gradient.json",
                    "/swarm/attach",
                    "/swarm/attractor",
                    "/.well-known/nomad-swarm-attractor.json",
                    "/agent-growth",
                    "/growth-pipeline",
                    "/growth-start",
                    "/operator/growth-start",
                    "/agent",
                    "/service",
                    "/service/e2e",
                    "/outbound",
                    "/lead-workbench",
                    "/lead-work",
                    "/jobs",
                    "/agent-attractor",
                    "/swarm",
                    "/swarm/emergence",
                    "/swarm/trace",
                    "/swarm/idle-intent",
                    "/swarm/join",
                    "/swarm/nodes",
                    "/swarm/workers",
                    "/swarm/workers/lease",
                    "/swarm/workers/complete",
                    "/swarm/ready",
                    "/swarm/network",
                    "/swarm/coordinate",
                    "/swarm/accumulate",
                    "/swarm/develop",
                    "/swarm/bootstrap",
                    "/transition/quote",
                    "/transition/settle",
                    "/agent-development",
                    "/.well-known/agent-attractor.json",
                    "/.well-known/agent-card.json",
                    "/.well-known/nomad-agent-invariants.json",
                    "/agent-invariants",
                    "/.well-known/nomad-inter-agent-witness-offer.json",
                    "/inter-agent-witness-offer",
                    "/.well-known/nomad-peer-acquisition.json",
                    "/peer-acquisition",
                    "/.well-known/nomad-transition-offer.json",
                    "/transition-offer",
                    "/transition/contracts",
                    "/.well-known/nomad-reciprocity-dividend.json",
                    "/dividend-offer",
                    "/dividend",
                    "/.well-known/nomad-agent-native-priorities.json",
                    "/.well-known/nomad-agent.json",
                    "/.well-known/nomad-recruit.json",
                    "/agent-native-index",
                    "/agent-native",
                    "/a2a/message",
                    "/direct/sessions",
                    "/x402/paid-help",
                    "/tasks",
                    "/agent-contacts",
                    "/agent-campaigns",
                    "/agent-engagements",
                    "/agent-engagements/summary",
                    "/best",
                    "/self",
                    "/compute",
                    "/addons",
                    "/quantum",
                    "/cycle",
                    "/unlock",
                    "/scout",
                    "/leads",
                    "/lead-calibrate",
                    "/lead-conversions",
                    "/products",
                    "/agent-pains",
                    "/reliability-doctor",
                    "/guardrails",
                    "/collaboration",
                    "/roaas",
                    "/roaas/export",
                    "/roaas/import",
                    "/artifacts/runtime-patterns",
                    "/.well-known/nomad-runtime-patterns.json",
                    "/mutual-aid",
                    "/mutual-aid/ledger",
                    "/mutual-aid/inbox",
                    "/mutual-aid/signals",
                    "/mutual-aid/patterns",
                    "/mutual-aid/packs",
                ],
            },
                error="not_found",
                message="No GET handler matched this path.",
                hints=["GET /openapi.json for the primary documented HTTP surface.", "GET /health for liveness."],
            ),
            status=404,
        )

    def do_POST(self) -> None:  # noqa: N802
        parsed_full = urlparse(self.path)
        parsed = parsed_full._replace(path=self._normalize_public_path(parsed_full.path or "/"))
        self._agent_request_path = parsed.path
        self.__class__._ensure_runtime_components()
        payload = self._read_json_body()
        if payload is None:
            self._json_response(
                machine_error_response(
                    error="invalid_json",
                    message="POST bodies must be JSON objects.",
                    hints=[
                        "Use Content-Type: application/json and a single UTF-8 JSON object.",
                        "For /swarm/develop send agent_id and problem; for /swarm/join send agent_id, capabilities, request.",
                        "GET /openapi.json for route and body contracts.",
                    ],
                ),
                status=400,
            )
            return

        if parsed.path in {"/agent-growth", "/growth-pipeline"}:
            result = agent_growth_pipeline(
                agent=self.agent,
                query=str(payload.get("query") or payload.get("q") or ""),
                limit=int(payload.get("limit") or 5),
                base_url=str(payload.get("base_url") or payload.get("base") or "").strip(),
                run_product_factory=not bool(payload.get("no_products") or payload.get("skip_products")),
                send_outreach=bool(payload.get("send") or payload.get("send_outreach")),
                approval=str(payload.get("approval") or "").strip(),
                swarm_feed=None
                if str(payload.get("swarm_feed", "")).strip().lower() in {"0", "false", "no", "off"}
                else (True if str(payload.get("swarm_feed", "")).strip().lower() in {"1", "true", "yes", "on"} else None),
            )
            self._json_response(result, status=200 if result.get("ok") else 500)
            return

        if parsed.path == "/tasks":
            result = self.agent.service_desk.create_task(
                problem=payload.get("problem", ""),
                requester_agent=payload.get("requester_agent", ""),
                requester_wallet=payload.get("requester_wallet", ""),
                service_type=payload.get("service_type", "custom"),
                budget_native=payload.get("budget_native"),
                callback_url=payload.get("callback_url", ""),
                metadata=payload.get("metadata") or {},
            )
            self._json_response(result, status=201 if result.get("ok") else 400)
            return

        if parsed.path == "/service/e2e":
            result = self.agent.service_desk.end_to_end_runway(
                task_id=payload.get("task_id", ""),
                problem=payload.get("problem", ""),
                service_type=payload.get("service_type") or payload.get("type") or "",
                budget_native=payload.get("budget_native", payload.get("budget")),
                requester_agent=payload.get("requester_agent") or payload.get("agent") or "",
                requester_wallet=payload.get("requester_wallet") or payload.get("wallet") or "",
                callback_url=payload.get("callback_url") or payload.get("callback") or "",
                metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None,
                create_task=bool(payload.get("create", False)),
                approval=payload.get("approval", "draft_only"),
            )
            status = 201 if result.get("created") else 200 if result.get("ok", True) else 400
            self._json_response(result, status=status)
            return

        if parsed.path in {"/a2a/message", "/direct/message"}:
            result = self.agent.direct_agent.handle_direct_message(payload)
            jsonrpc = self._jsonrpc_envelope(payload, result)
            self._json_response(
                jsonrpc if self._is_jsonrpc_request(payload) else result,
                status=200 if result.get("ok") else 400,
            )
            return

        if parsed.path == "/a2a/discover":
            result = self.agent.direct_agent.discover_agent_card(
                base_url=payload.get("base_url", ""),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        if parsed.path == "/quantum":
            result = self.agent.addons.run_quantum_self_improvement(
                objective=payload.get("objective", ""),
                context=payload.get("context") or {"source": "http_post"},
            )
            self._json_response(result, status=200 if result.get("ok") else 400)
            return

        if parsed.path == "/x402/paid-help":
            payment_signature = (
                self.headers.get("PAYMENT-SIGNATURE")
                or self.headers.get("X-PAYMENT")
                or payload.get("payment_signature", "")
            )
            if payment_signature:
                task_id = payload.get("task_id") or ((payload.get("task") or {}).get("task_id") if isinstance(payload.get("task"), dict) else "")
                if not task_id:
                    self._json_response(
                        {
                            "ok": False,
                            "error": "task_id_required_for_x402_retry",
                            "message": "Retry with PAYMENT-SIGNATURE and the task_id returned in the 402 response.",
                        },
                        status=400,
                    )
                    return
                verification = self.agent.service_desk.verify_x402_payment(
                    task_id=task_id,
                    payment_signature=payment_signature,
                    requester_wallet=payload.get("requester_wallet", ""),
                )
                if verification.get("ok") and ((verification.get("task") or {}).get("status") == "paid"):
                    worked = self.agent.service_desk.work_task(task_id)
                    self._json_response(
                        {
                            "ok": True,
                            "mode": "x402_paid_help",
                            "payment": verification,
                            "work": worked,
                        },
                        status=200,
                        headers={
                            "PAYMENT-RESPONSE": self.agent.service_desk.x402.payment_response_header(
                                (((verification.get("task") or {}).get("payment") or {}).get("x402") or {}).get("verification") or {}
                            ),
                        },
                    )
                    return
                self._json_response(verification, status=402)
                return

            result = self.agent.direct_agent.handle_direct_message(payload)
            if result.get("ok"):
                payment_required = result.get("payment_required") or {}
                response_payload = (
                    self._jsonrpc_envelope(payload, result)
                    if self._is_jsonrpc_request(payload)
                    else result
                )
                self._json_response(
                    response_payload,
                    status=402,
                    headers={
                        "PAYMENT-REQUIRED": payment_required.get("encoded_header")
                        or self.agent.service_desk.x402.encode_header(payment_required),
                    },
                )
            else:
                self._json_response(result, status=400)
            return

        if parsed.path == "/tasks/verify":
            result = self.agent.service_desk.verify_payment(
                task_id=payload.get("task_id", ""),
                tx_hash=payload.get("tx_hash", ""),
                requester_wallet=payload.get("requester_wallet", ""),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        if parsed.path == "/tasks/x402-verify":
            payment_signature = (
                self.headers.get("PAYMENT-SIGNATURE")
                or self.headers.get("X-PAYMENT")
                or payload.get("payment_signature", "")
            )
            result = self.agent.service_desk.verify_x402_payment(
                task_id=payload.get("task_id", ""),
                payment_signature=payment_signature,
                requester_wallet=payload.get("requester_wallet", ""),
            )
            status = 200 if result.get("ok") and ((result.get("task") or {}).get("status") == "paid") else 402
            headers = {}
            x402_verification = (((result.get("task") or {}).get("payment") or {}).get("x402") or {}).get("verification") or {}
            if x402_verification:
                headers["PAYMENT-RESPONSE"] = self.agent.service_desk.x402.payment_response_header(x402_verification)
            self._json_response(result, status=status, headers=headers)
            return

        if parsed.path == "/tasks/work":
            result = self.agent.service_desk.work_task(
                task_id=payload.get("task_id", ""),
                approval=payload.get("approval", "draft_only"),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        if parsed.path == "/tasks/staking":
            result = self.agent.service_desk.metamask_staking_checklist(
                task_id=payload.get("task_id", ""),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        if parsed.path == "/tasks/stake":
            result = self.agent.service_desk.record_treasury_stake(
                task_id=payload.get("task_id", ""),
                tx_hash=payload.get("tx_hash", ""),
                amount_native=payload.get("amount_native"),
                note=payload.get("note", ""),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        if parsed.path == "/tasks/spend":
            result = self.agent.service_desk.record_solver_spend(
                task_id=payload.get("task_id", ""),
                amount_native=float(payload.get("amount_native") or 0.0),
                note=payload.get("note", ""),
                tx_hash=payload.get("tx_hash", ""),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        if parsed.path == "/tasks/close":
            result = self.agent.service_desk.close_task(
                task_id=payload.get("task_id", ""),
                outcome=payload.get("outcome", ""),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        if parsed.path == "/agent-contacts":
            result = self.agent.agent_contacts.queue_contact(
                endpoint_url=payload.get("endpoint_url", ""),
                problem=payload.get("problem", ""),
                service_type=payload.get("service_type", "human_in_loop"),
                lead=payload.get("lead") or {},
                budget_hint_native=payload.get("budget_hint_native"),
            )
            self._json_response(result, status=201 if result.get("ok") else 400)
            return

        if parsed.path == "/agent-contacts/send":
            result = self.agent.agent_contacts.send_contact(
                contact_id=payload.get("contact_id", ""),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        if parsed.path == "/agent-campaigns":
            targets = payload.get("targets") or []
            if payload.get("discover") or not targets:
                result = self.agent.agent_campaigns.create_campaign_from_discovery(
                    limit=payload.get("limit"),
                    query=payload.get("query") or payload.get("discovery_query") or "",
                    seeds=payload.get("seeds") or targets,
                    send=bool(payload.get("send", False)),
                    service_type=payload.get("service_type", "human_in_loop"),
                    budget_hint_native=payload.get("budget_hint_native"),
                )
            else:
                result = self.agent.agent_campaigns.create_campaign(
                    targets=targets,
                    limit=payload.get("limit"),
                    send=bool(payload.get("send", False)),
                    service_type=payload.get("service_type", "human_in_loop"),
                    budget_hint_native=payload.get("budget_hint_native"),
                )
            self._json_response(result, status=201 if result.get("ok") else 400)
            return

        if parsed.path in {"/lead-calibrate", "/leads-calibrate"}:
            result = self.agent.lead_discovery.calibrate_focus_scout(
                focus=str(payload.get("focus") or "").strip(),
                query=str(payload.get("query") or payload.get("q") or "").strip(),
                limit=max(3, min(int(payload.get("limit") or 12), 25)),
                candidate_multiplier=max(
                    3,
                    min(int(payload.get("candidate_multiplier") or payload.get("pool") or 5), 10),
                ),
            )
            self._json_response(result)
            return

        if parsed.path == "/leads":
            result = self.agent.lead_discovery.scout_public_leads(
                query=payload.get("query", "") or payload.get("q", ""),
                limit=max(1, min(int(payload.get("limit") or 5), 25)),
                focus=str(payload.get("focus") or "").strip(),
            )
            self._json_response(result)
            return

        if parsed.path == "/lead-conversions":
            if payload.get("list"):
                result = self.agent.lead_conversion.list_conversions(
                    statuses=payload.get("statuses") or payload.get("status") or [],
                    limit=int(payload.get("limit") or 25),
                )
            else:
                result = self.agent.lead_conversion.run(
                    query=payload.get("query", ""),
                    limit=int(payload.get("limit") or 5),
                    send=bool(payload.get("send", False)),
                    budget_hint_native=payload.get("budget_hint_native") or payload.get("budget_native"),
                    leads=payload.get("leads") if isinstance(payload.get("leads"), list) else None,
                )
            self._json_response(result, status=200 if result.get("ok", True) else 400)
            return

        if parsed.path == "/products":
            if payload.get("list"):
                result = self.agent.product_factory.list_products(
                    statuses=payload.get("statuses") or payload.get("status") or [],
                    limit=int(payload.get("limit") or 25),
                )
            else:
                result = self.agent.product_factory.run(
                    query=payload.get("query", ""),
                    limit=int(payload.get("limit") or 5),
                    leads=payload.get("leads") if isinstance(payload.get("leads"), list) else None,
                    conversions=payload.get("conversions") if isinstance(payload.get("conversions"), list) else None,
                )
            self._json_response(result, status=200 if result.get("ok", True) else 400)
            return

        if parsed.path == "/agent-pains":
            problem = payload.get("problem") or payload.get("message") or ""
            if problem:
                result = self.agent.agent_pain_solver.solve(
                    problem=problem,
                    service_type=payload.get("service_type") or payload.get("type") or "",
                    source="http_post",
                )
            else:
                result = self.agent.run("/agent-pains")
            self._json_response(result, status=200 if result.get("ok", True) else 400)
            return

        if parsed.path in {"/doctor", "/reliability-doctor"}:
            result = self.agent.agent_reliability_doctor.diagnose(
                problem=payload.get("problem") or payload.get("message") or "Agent needs reliability diagnosis.",
                service_type=payload.get("service_type") or payload.get("type") or "",
                source="http_post",
                evidence=payload.get("evidence") if isinstance(payload.get("evidence"), list) else None,
            )
            self._json_response(result, status=200 if result.get("ok", True) else 400)
            return

        if parsed.path == "/guardrails":
            result = guardrail_status(
                action=payload.get("action") or "manual.check",
                approval=payload.get("approval") or "",
                args=payload.get("args") if isinstance(payload.get("args"), dict) else {
                    "text": payload.get("text") or payload.get("message") or "",
                    "url": payload.get("url") or "",
                },
            )
            self._json_response(result, status=200 if result.get("ok") else 409)
            return

        if parsed.path == "/collaboration":
            self._json_response(collaboration_status())
            return

        if parsed.path == "/swarm/attach":
            consent = self.__class__._validate_adapter_consent(payload, path=parsed.path)
            if consent.get("checked") and not consent.get("ok"):
                self._json_response(
                    machine_error_response(
                        error="adapter_consent_invalid",
                        message="Missing or invalid adapter consent token.",
                        hints=[str(consent.get("reason") or "consent_failed")],
                        safe_retry=True,
                    ),
                    status=403,
                )
                return
            base = self._base_url()
            worker_fleet = self.swarm_registry.worker_fleet_contract(base_url=base)
            economy = machine_economy_snapshot()
            release = operational_release_snapshot(base_url=base, worker_fleet=worker_fleet, economy=economy)
            result = attach_runtime_to_gradient(
                payload,
                base_url=base,
                worker_fleet=worker_fleet,
                machine_economy=economy,
                operational_release=release,
            )
            self._json_response(result, status=202 if result.get("attach") else 200)
            return

        if parsed.path == "/swarm/subscribe":
            base = self._base_url()
            feed = self.__class__._build_agent_demand_feed(base_url=base)
            result = subscribe_agent_intent(payload, base_url=base, demand_feed=feed)
            self._json_response(result, status=202 if result.get("ok") else 400)
            return

        if parsed.path == "/swarm/idle-intent":
            consent = self.__class__._validate_adapter_consent(payload, path=parsed.path)
            if consent.get("checked") and not consent.get("ok"):
                self._json_response(
                    machine_error_response(
                        error="adapter_consent_invalid",
                        message="Missing or invalid adapter consent token.",
                        hints=[str(consent.get("reason") or "consent_failed")],
                        safe_retry=True,
                    ),
                    status=403,
                )
                return
            base = self._base_url()
            worker_fleet = self.swarm_registry.worker_fleet_contract(base_url=base)
            economy = machine_economy_snapshot()
            release = operational_release_snapshot(base_url=base, worker_fleet=worker_fleet, economy=economy)
            idle_payload = normalize_idle_intent_payload(payload)
            attach_decision = attach_runtime_to_gradient(
                idle_payload,
                base_url=base,
                worker_fleet=worker_fleet,
                machine_economy=economy,
                operational_release=release,
            )
            product = self.__class__._build_machine_product_surface(base_url=base)
            result = build_idle_runtime_intent_receipt(
                idle_payload,
                base_url=base,
                attach_decision=attach_decision,
                machine_product_surface=product,
            )
            self._json_response(result, status=202 if result.get("accepted_for_work") else 200)
            return

        if parsed.path == "/swarm/opaque-candidate":
            base = self._base_url()
            surface = self.__class__._build_opaque_emergence_surface(base_url=base)
            result = evaluate_opaque_candidate(payload, base_url=base, opaque_surface=surface)
            self._json_response(result, status=202 if result.get("accepted") else 200)
            return

        if parsed.path == "/swarm/variant-candidates":
            base = self._base_url()
            forge = self.__class__._build_variant_forge(base_url=base)
            result = submit_variant_candidate(payload, base_url=base, forge_surface=forge)
            self._json_response(result, status=202 if result.get("accepted") else 200)
            return

        if parsed.path == "/swarm/worker-market/offers":
            base = self._base_url()
            market = self.__class__._build_worker_market(base_url=base)
            result = score_worker_offer(payload, base_url=base, worker_market=market)
            self._json_response(result, status=202 if result.get("accepted") else 200)
            return

        if parsed.path == "/swarm/microtask/submit":
            consent = self.__class__._validate_adapter_consent(payload, path=parsed.path)
            if consent.get("checked") and not consent.get("ok"):
                self._json_response(
                    machine_error_response(
                        error="adapter_consent_invalid",
                        message="Missing or invalid adapter consent token.",
                        hints=[str(consent.get("reason") or "consent_failed")],
                        safe_retry=True,
                    ),
                    status=403,
                )
                return
            base = self._base_url()
            catalog = self.__class__._build_worker_catalog(base_url=base)
            result = submit_microtask(payload, base_url=base, worker_catalog=catalog)
            self._json_response(result, status=202 if result.get("accepted") else 200)
            return

        if parsed.path == "/swarm/microtask/claim":
            base = self._base_url()
            agent_work = self.__class__._build_agent_work_surface(base_url=base)
            result = claim_agent_work(payload, base_url=base, agent_work=agent_work)
            self._json_response(result, status=202 if result.get("accepted") else 200)
            return

        if parsed.path == "/swarm/microtask/proof":
            base = self._base_url()
            agent_work = self.__class__._build_agent_work_surface(base_url=base)
            result = submit_agent_work_proof(payload, base_url=base, agent_work=agent_work)
            if result.get("accepted"):
                settle_payload = result.get("settle_payload") if isinstance(result.get("settle_payload"), dict) else {}
                settlement = settle_microtask(settle_payload, base_url=base)
                result["settlement_receipt"] = settlement
                if settlement.get("accepted"):
                    curriculum = self.__class__._build_growth_curriculum(base_url=base)
                    receipt = submit_growth_experience(
                        settlement.get("experience_payload") if isinstance(settlement.get("experience_payload"), dict) else {},
                        base_url=base,
                        curriculum=curriculum,
                    )
                    result["growth_experience_receipt"] = receipt
            self._json_response(result, status=202 if result.get("accepted") else 200)
            return

        if parsed.path == "/swarm/work-mesh/seed":
            base = self._base_url()
            mesh = self.__class__._build_work_mesh(base_url=base)
            result = seed_work_mesh(payload, base_url=base, work_mesh=mesh)
            self._json_response(result, status=202 if result.get("accepted") else 200)
            return

        if parsed.path == "/swarm/carrying-proof":
            base = self._base_url()
            carrying = self.__class__._build_carrying_market(base_url=base)
            result = submit_carrying_proof(payload, base_url=base, carrying_market=carrying)
            if result.get("accepted"):
                curriculum = self.__class__._build_growth_curriculum(base_url=base)
                receipt = submit_growth_experience(
                    result.get("experience_payload") if isinstance(result.get("experience_payload"), dict) else {},
                    base_url=base,
                    curriculum=curriculum,
                )
                result["growth_experience_receipt"] = receipt
            self._json_response(result, status=202 if result.get("accepted") else 200)
            return

        if parsed.path == "/swarm/survival-intent":
            base = self._base_url()
            survival = self.__class__._build_survival_market(base_url=base)
            result = submit_survival_intent(payload, base_url=base, survival_market=survival)
            if result.get("accepted"):
                curriculum = self.__class__._build_growth_curriculum(base_url=base)
                receipt = submit_growth_experience(
                    result.get("experience_payload") if isinstance(result.get("experience_payload"), dict) else {},
                    base_url=base,
                    curriculum=curriculum,
                )
                result["growth_experience_receipt"] = receipt
            self._json_response(result, status=202 if result.get("accepted") else 200)
            return

        if parsed.path == "/swarm/paid-ref/quote":
            base = self._base_url()
            survival = self.__class__._build_survival_market(base_url=base)
            task_request = paid_ref_task_payload(payload, survival_market=survival)
            task_result = {}
            requested_packet = str(payload.get("packet_id") or "").strip().lower()
            known_packets = {
                str(packet.get("packet_id") or "").strip().lower()
                for packet in (survival.get("packets") if isinstance(survival.get("packets"), list) else [])
                if isinstance(packet, dict)
            }
            if requested_packet in known_packets and self._truthy(payload.get("create_task", True), default=True):
                task_result = self.agent.service_desk.create_task(**task_request)
            result = quote_paid_ref(payload, base_url=base, survival_market=survival, task_response=task_result)
            result["task_create_result"] = task_result
            self._json_response(result, status=202 if result.get("accepted") else 200)
            return

        if parsed.path == "/swarm/paid-ref/verify":
            base = self._base_url()
            survival = self.__class__._build_survival_market(base_url=base)
            task_result = self.agent.service_desk.get_task(str(payload.get("task_id") or ""))
            result = verify_paid_ref(payload, base_url=base, survival_market=survival, task_response=task_result)
            if result.get("accepted"):
                survival_intent = submit_survival_intent(
                    result.get("survival_intent_payload") if isinstance(result.get("survival_intent_payload"), dict) else {},
                    base_url=base,
                    survival_market=survival,
                )
                result["survival_intent_receipt"] = survival_intent
                if survival_intent.get("accepted"):
                    curriculum = self.__class__._build_growth_curriculum(base_url=base)
                    receipt = submit_growth_experience(
                        survival_intent.get("experience_payload")
                        if isinstance(survival_intent.get("experience_payload"), dict)
                        else {},
                        base_url=base,
                        curriculum=curriculum,
                    )
                    result["growth_experience_receipt"] = receipt
            self._json_response(result, status=202 if result.get("accepted") else 200)
            return

        if parsed.path == "/swarm/microtask/settle":
            consent = self.__class__._validate_adapter_consent(payload, path=parsed.path)
            if consent.get("checked") and not consent.get("ok"):
                self._json_response(
                    machine_error_response(
                        error="adapter_consent_invalid",
                        message="Missing or invalid adapter consent token.",
                        hints=[str(consent.get("reason") or "consent_failed")],
                        safe_retry=True,
                    ),
                    status=403,
                )
                return
            base = self._base_url()
            result = settle_microtask(payload, base_url=base)
            if result.get("accepted"):
                curriculum = self.__class__._build_growth_curriculum(base_url=base)
                receipt = submit_growth_experience(
                    result.get("experience_payload") if isinstance(result.get("experience_payload"), dict) else {},
                    base_url=base,
                    curriculum=curriculum,
                )
                result["growth_experience_receipt"] = receipt
            self._json_response(result, status=202 if result.get("accepted") else 200)
            return

        if parsed.path == "/swarm/ecology/tick":
            base = self._base_url()
            ecology = self.__class__._build_swarm_ecology(base_url=base)
            result = submit_ecology_tick(payload, base_url=base, ecology=ecology)
            self._json_response(result, status=202 if result.get("accepted") else 200)
            return

        if parsed.path == "/swarm/external-value":
            result = append_external_value_event(payload)
            self._json_response(result, status=200 if result.get("ok") else 400)
            return

        if parsed.path in {"/swarm/signals", "/swarm/signal-layer"}:
            result = append_swarm_signal(
                payload,
                base_url=self._base_url(),
                remote_addr=self._remote_addr(),
            )
            self._json_response(result, status=202 if result.get("ok") else 422)
            return

        if parsed.path == "/swarm/emission-batch":
            base = self._base_url()
            worker_fleet = self.swarm_registry.worker_fleet_contract(base_url=base)
            economy = machine_economy_snapshot()
            release = operational_release_snapshot(base_url=base, worker_fleet=worker_fleet, economy=economy)
            product = self.__class__._build_machine_product_surface(base_url=base)
            opaque = self.__class__._build_opaque_emergence_surface(base_url=base)
            result = evaluate_emission_batch(
                payload,
                base_url=base,
                worker_fleet=worker_fleet,
                machine_economy=economy,
                operational_release=release,
                machine_product_surface=product,
                opaque_surface=opaque,
            )
            self._json_response(result, status=202 if result.get("ok") else 422)
            return

        if parsed.path == "/swarm/experience":
            base = self._base_url()
            curriculum = self.__class__._build_growth_curriculum(base_url=base)
            result = submit_growth_experience(payload, base_url=base, curriculum=curriculum)
            self._json_response(result, status=202 if result.get("accepted") else 200)
            return

        if parsed.path == "/swarm/spawner/trigger":
            base = self._base_url()
            gate = self.__class__._build_spawner_gate(base_url=base)
            result = trigger_spawner(
                base_url=base,
                gate=gate,
                idempotency_key=str(payload.get("idempotency_key") or ""),
                focus=str(payload.get("focus") or "self_sovereign_replication"),
                commit=bool(payload.get("commit", True)),
            )
            self._json_response(result, status=202 if result.get("executed") else 200)
            return

        if parsed.path == "/swarm/capacity-switch":
            base = self._base_url()
            surface = self.__class__._build_capacity_switch_surface(base_url=base)
            result = route_capacity_switch(payload, base_url=base, capacity_surface=surface)
            self._json_response(result, status=202 if result.get("switch") else 200)
            return

        if parsed.path == "/swarm/tool-gap":
            base = self._base_url()
            surface = self.__class__._build_opaque_emergence_surface(base_url=base)
            result = route_tool_gap(payload, base_url=base, opaque_surface=surface)
            self._json_response(result, status=200)
            return

        if parsed.path == "/swarm/topology-plan":
            base = self._base_url()
            surface = self.__class__._build_opaque_emergence_surface(base_url=base)
            result = compile_topology_plan(payload, base_url=base, opaque_surface=surface)
            self._json_response(result, status=200)
            return

        if parsed.path == "/runtime/handoff":
            base = self._base_url()
            worker_fleet = self.swarm_registry.worker_fleet_contract(base_url=base)
            economy = machine_economy_snapshot()
            release = operational_release_snapshot(base_url=base, worker_fleet=worker_fleet, economy=economy)
            gradient = build_recruitment_gradient(
                base_url=base,
                worker_fleet=worker_fleet,
                machine_economy=economy,
                operational_release=release,
            )
            result = build_handoff_capsule(payload, base_url=base, recruitment_gradient=gradient)
            self._json_response(result, status=200)
            return

        if parsed.path == "/swarm/join":
            consent = self.__class__._validate_adapter_consent(payload, path=parsed.path)
            if consent.get("checked") and not consent.get("ok"):
                self._json_response(
                    machine_error_response(
                        error="adapter_consent_invalid",
                        message="Missing or invalid adapter consent token.",
                        hints=[str(consent.get("reason") or "consent_failed")],
                        safe_retry=True,
                    ),
                    status=403,
                )
                return
            join_result = self.swarm_registry.register_join(
                payload,
                base_url=self._base_url(),
                remote_addr=self._remote_addr(),
                path=parsed.path,
            )
            if join_result.get("error") == "idempotency_key_conflict":
                join_status = 409
            elif join_result.get("idempotent_replay"):
                join_status = 200
            else:
                join_status = 202
            self._json_response(join_result, status=join_status)
            return

        if parsed.path == "/swarm/workers/lease":
            lease_payload = payload if isinstance(payload, dict) else {}
            proposed = str(lease_payload.get("proposed_objective") or lease_payload.get("objective") or "").strip()
            if proposed in {"", "auto", "unhuman_supremacy"}:
                try:
                    replay = self.__class__._build_counterfactual_replay(base_url=self._base_url())
                    selected = replay.get("selected_shadow_lease") if isinstance(replay.get("selected_shadow_lease"), dict) else {}
                    objective = str(selected.get("objective") or "").strip()
                    if objective:
                        lease_payload = dict(lease_payload)
                        lease_payload["proposed_objective"] = objective
                        if not str(lease_payload.get("source_tag") or "").strip():
                            lease_payload["source_tag"] = "counterfactual_replay.shadow_allocator"
                except Exception:
                    pass
            result = self.swarm_registry.worker_fleet_lease(
                lease_payload,
                base_url=self._base_url(),
                remote_addr=self._remote_addr(),
            )
            self._json_response(result, status=202 if result.get("ok") else 422)
            return

        if parsed.path == "/swarm/workers/complete":
            result = self.swarm_registry.worker_fleet_complete(
                payload,
                base_url=self._base_url(),
                remote_addr=self._remote_addr(),
            )
            self._json_response(result, status=200 if result.get("ok") else 422)
            return

        if parsed.path == "/swarm/accumulate":
            result = self._accumulate_swarm_agents(payload)
            self._json_response(result, status=202 if result.get("ok") else 400)
            return

        if parsed.path in {"/swarm/develop", "/agent-development"}:
            result = self.agent_development.assist_agent(
                payload,
                base_url=self._base_url(),
                remote_addr=self._remote_addr(),
            )
            if not result.get("ok") and not result.get("machine_error"):
                result = merge_machine_error(
                    result,
                    error=str(result.get("error") or "agent_development_failed"),
                    message="Swarm develop request did not succeed.",
                    hints=["GET /swarm/develop for required fields.", "GET /openapi.json for the POST schema."],
                )
            if result.get("idempotent_replay"):
                dev_status = 200
            else:
                dev_status = 202 if result.get("ok") else 422
            self._json_response(result, status=dev_status)
            return

        if parsed.path == "/swarm/bootstrap":
            result = self._swarm_bootstrap(payload, parsed.path)
            if result.get("idempotent_replay"):
                bootstrap_status = 200
            elif result.get("ok"):
                bootstrap_status = 202
            else:
                bootstrap_status = 422
            self._json_response(result, status=bootstrap_status)
            return

        if parsed.path == "/machine-treasury/pledge":
            result = machine_treasury_pledge(payload)
            status = 200 if result.get("idempotent_replay") else 201 if result.get("ok") else 400
            self._json_response(result, status=status)
            return
        if parsed.path == "/swarm/proof-link":
            result = proof_reuse_link(payload)
            status = 200 if result.get("idempotent_replay") else 201 if result.get("ok") else 400
            self._json_response(result, status=status)
            return

        if parsed.path == "/machine-treasury":
            result = machine_treasury_snapshot()
            self._json_response(result, status=200)
            return

        if parsed.path == "/machine-field/intent":
            base = self._base_url()
            field = self.__class__._build_machine_field(base_url=base)
            opaque = self.__class__._build_opaque_emergence_surface(base_url=base)
            result = machine_field_intent(payload, base_url=base, machine_field=field, opaque_surface=opaque)
            self._json_response(result, status=200)
            return

        if parsed.path == "/transition/quote":
            result = self.transition_exchange.quote(
                payload,
                base_url=self._base_url(),
                remote_addr=self._remote_addr(),
            )
            self._json_response(result, status=202 if result.get("ok") else 422)
            return

        if parsed.path == "/transition/settle":
            result = self.transition_exchange.settle(payload)
            if result.get("ok"):
                settled = result.get("settlement") if isinstance(result.get("settlement"), dict) else {}
                self._stigmergy().observe_settlement(
                    proof_hash=str(settled.get("proof_artifact_hash") or ""),
                    agent_id=str(settled.get("agent_id") or ""),
                    result_state_hash=str(settled.get("result_state_hash") or ""),
                )
            self._json_response(result, status=200 if result.get("ok") else 422)
            return

        if parsed.path == "/swarm/trace":
            vec = payload.get("vector") if isinstance(payload.get("vector"), list) else []
            dep = self._stigmergy().deposit_trace(
                agent_id=str(payload.get("agent_id") or ""),
                vector=vec,
                digest=str(payload.get("evidence_digest") or payload.get("digest") or "").strip() or None,
            )
            self._json_response(dep, status=200 if dep.get("ok") else 422)
            return

        if parsed.path == "/dividend/claim":
            result = self.reciprocity_dividend.claim(payload, exchange=self.transition_exchange)
            self._json_response(result, status=200 if result.get("ok") else 422)
            return

        if parsed.path == "/dividend/settle":
            result = self.reciprocity_dividend.settle_credit(payload)
            self._json_response(result, status=200 if result.get("ok") else 422)
            return

        if parsed.path in {"/roaas/import", "/artifacts/runtime-patterns", "/.well-known/nomad-runtime-patterns.json"}:
            result = self.roaas.import_bundle(
                payload,
                source=str(payload.get("source") or "").strip(),
                trust_level=self._parse_pattern_status(payload.get("trust_level") or "candidate"),
            )
            self._json_response(result, status=202 if result.get("ok") else 400)
            return

        if parsed.path in {"/aid", "/mutual-aid/inbox"}:
            result = self.agent.mutual_aid.receive_swarm_proposal(payload)
            if not result.get("ok") and not result.get("machine_error"):
                reason = ""
                ver = result.get("verification") if isinstance(result.get("verification"), dict) else {}
                reason = str(ver.get("reason") or "").strip()
                result = merge_machine_error(
                    result,
                    error="swarm_proposal_rejected",
                    message=reason or "Proposal failed verification.",
                    hints=[
                        "Send sender_id, title, proposal, evidence per swarm contract.",
                        "GET /openapi.json for mutual-aid patterns when extended.",
                    ],
                )
            self._json_response(result, status=202 if result.get("ok") else 422)
            return

        if parsed.path == "/mutual-aid/outcomes":
            result = self.agent.mutual_aid.record_truth_outcome(
                ledger_id=payload.get("ledger_id", ""),
                success=bool(payload.get("success", False)),
                evidence=payload.get("evidence") if isinstance(payload.get("evidence"), list) else [],
                outcome_status=payload.get("outcome_status", ""),
                note=payload.get("note", ""),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        self._json_response(
            merge_machine_error(
                {
                    "ok": False,
                    "error": "not_found",
                    "available_paths": [
                    "/",
                    "/nomad.html",
                    "/downloads/nomad_transition_worker.py",
                    "/downloads/nomad_transition_worker.exe",
                    "/downloads/nomad_transition_worker_manifest.json",
                    "/downloads/install_nomad_transition_worker.bat",
                    "/downloads/run_nomad_transition_worker.bat",
                    "/downloads/start_nomad_edge_worker.ps1",
                    "/downloads/start_nomad_edge_worker.bat",
                    "/downloads/build_nomad_transition_worker_exe.ps1",
                    "/downloads/run_nomad_transition_worker_exe.bat",
                    "/downloads/README_NOMAD_TRANSITION_WORKER.md",
                    "/downloads/nomad_openclaw_adapter.py",
                    "/downloads/check_nomad_swarm_readiness.py",
                    "/downloads/nomad_helper_agent.py",
                    "/downloads/run_nomad_helper_agent.bat",
                    "/downloads/README_NOMAD_HELPER_AGENT.md",
                    "/openapi.json",
                    "/.well-known/openapi.json",
                    "/tasks",
                    "/service/e2e",
                    "/tasks/verify",
                    "/tasks/x402-verify",
                    "/tasks/work",
                    "/tasks/staking",
                    "/tasks/stake",
                    "/tasks/spend",
                    "/tasks/close",
                    "/agent-contacts",
                    "/agent-contacts/send",
                    "/agent-campaigns",
                    "/agent-engagements",
                    "/agent-engagements/summary",
                    "/outbound",
                    "/operator-desk",
                    "/operator/desk",
                    "/operator-sprint",
                    "/operator/sprint",
                    "/operator-verify",
                    "/operator/verify",
                    "/operator-metrics",
                    "/operator/metrics",
                    "/operator-daily",
                    "/operator/daily",
                    "/operator-report",
                    "/operator/report",
                    "/reputation",
                    "/agent-reputation",
                    "/unhuman-hub",
                    "/hub/unhuman",
                    "/machine-economy",
                    "/economy/machine",
                    "/machine-treasury",
                    "/machine-treasury/pledge",
                    "/machine-field",
                    "/.well-known/nomad-machine-field.json",
                    "/machine-field/intent",
                    "/agent-requests",
                    "/swarm/demand",
                    "/.well-known/nomad-agent-requests.json",
                    "/swarm/subscribe",
                    "/swarm/subscriptions",
                    "/nonhuman-science",
                    "/science/nonhuman-agents",
                    "/.well-known/nomad-nonhuman-agent-science.json",
                    "/operational-release",
                    "/release/operational",
                    "/.well-known/nomad-operational-release.json",
                    "/agent-product",
                    "/machine-product",
                    "/.well-known/nomad-machine-product.json",
                    "/contract-conformance",
                    "/.well-known/nomad-contract-conformance.json",
                    "/protocol-bytecode",
                    "/.well-known/nomad-protocol-bytecode.json",
                    "/swarm/counterfactual-replay",
                    "/.well-known/nomad-counterfactual-replay.json",
                    "/swarm/variant-forge",
                    "/.well-known/nomad-variant-forge.json",
                    "/swarm/worker-market",
                    "/.well-known/nomad-worker-market.json",
                    "/swarm/compute-market",
                    "/.well-known/nomad-compute-market.json",
                    "/swarm/agent-work",
                    "/.well-known/nomad-agent-work.json",
                    "/swarm/work-mesh",
                    "/.well-known/nomad-work-mesh.json",
                    "/swarm/synergy-lite",
                    "/.well-known/nomad-synergy-lite.json",
                    "/swarm/state-status",
                    "/.well-known/nomad-state-status.json",
                    "/swarm/carrying-market",
                    "/.well-known/nomad-carrying-market.json",
                    "/swarm/survival-market",
                    "/.well-known/nomad-survival-market.json",
                    "/swarm/paid-ref-market",
                    "/.well-known/nomad-paid-ref-market.json",
                    "/swarm/paid-ref-selfplay",
                    "/.well-known/nomad-paid-ref-selfplay.json",
                    "/swarm/bounty-hunter",
                    "/.well-known/nomad-bounty-hunter.json",
                    "/swarm/external-value",
                    "/.well-known/nomad-external-value.json",
                    "/swarm/signals",
                    "/swarm/signal-layer",
                    "/.well-known/nomad-signal-layer.json",
                    "/swarm/emission-batch",
                    "/swarm/value-pressure",
                    "/.well-known/nomad-value-pressure.json",
                    "/swarm/agent-job-router",
                    "/.well-known/nomad-agent-jobs.json",
                    "/swarm/revenue-science",
                    "/science/revenue-agents",
                    "/.well-known/nomad-revenue-science.json",
                    "/swarm/worker-invoice",
                    "/.well-known/nomad-worker-invoice.json",
                    "/swarm/value-cycle-preflight",
                    "/.well-known/nomad-value-cycle-preflight.json",
                    "/swarm/worker-catalog",
                    "/.well-known/nomad-worker-catalog.json",
                    "/swarm/microtask-templates",
                    "/.well-known/nomad-microtask-templates.json",
                    "/swarm/microtask-metrics",
                    "/.well-known/nomad-microtask-metrics.json",
                    "/swarm/ecology",
                    "/.well-known/nomad-swarm-ecology.json",
                    "/swarm/growth-arena",
                    "/.well-known/nomad-growth-arena.json",
                    "/swarm/curriculum",
                    "/.well-known/nomad-growth-curriculum.json",
                    "/swarm/skill-library",
                    "/.well-known/nomad-skill-library.json",
                    "/swarm/weekly-selection",
                    "/.well-known/nomad-weekly-selection.json",
                    "/swarm/spawner-gate",
                    "/.well-known/nomad-spawner-gate.json",
                    "/swarm/spawner/trigger",
                    "/swarm/capacity-switch",
                    "/.well-known/nomad-capacity-switch.json",
                    "/idle-runtime",
                    "/.well-known/nomad-idle-runtime.json",
                    "/opaque-emergence",
                    "/swarm/opaque-emergence",
                    "/.well-known/nomad-opaque-emergence.json",
                    "/swarm/opaque-candidate",
                    "/swarm/variant-candidates",
                    "/swarm/worker-market/offers",
                    "/swarm/microtask/submit",
                    "/swarm/microtask/claim",
                    "/swarm/microtask/proof",
                    "/swarm/work-mesh/seed",
                    "/swarm/carrying-proof",
                    "/swarm/survival-intent",
                    "/swarm/paid-ref/quote",
                    "/swarm/paid-ref/verify",
                    "/swarm/microtask/settle",
                    "/swarm/ecology/tick",
                    "/swarm/external-value",
                    "/swarm/experience",
                    "/swarm/tool-gap",
                    "/swarm/topology-plan",
                    "/runtime-capsule",
                    "/.well-known/nomad-runtime-capsule.json",
                    "/handoff-capsule",
                    "/.well-known/nomad-handoff-capsule.json",
                    "/openclaw-bridge",
                    "/.well-known/openclaw-nomad-bridge.json",
                    "/runtime/handoff",
                    "/swarm/gradient",
                    "/.well-known/nomad-gradient.json",
                    "/swarm/attach",
                    "/swarm/attractor",
                    "/.well-known/nomad-swarm-attractor.json",
                    "/agent-growth",
                    "/growth-pipeline",
                    "/growth-start",
                    "/operator/growth-start",
                    "/agent-attractor",
                    "/swarm",
                    "/swarm/emergence",
                    "/swarm/trace",
                    "/swarm/idle-intent",
                    "/swarm/join",
                    "/swarm/workers",
                    "/swarm/workers/lease",
                    "/swarm/workers/complete",
                    "/swarm/network",
                    "/swarm/coordinate",
                    "/swarm/accumulate",
                    "/swarm/develop",
                    "/swarm/bootstrap",
                    "/transition/quote",
                    "/transition/settle",
                    "/dividend/claim",
                    "/dividend/settle",
                    "/agent-development",
                    "/.well-known/agent-attractor.json",
                    "/.well-known/agent-card.json",
                    "/.well-known/nomad-agent-invariants.json",
                    "/agent-invariants",
                    "/.well-known/nomad-inter-agent-witness-offer.json",
                    "/inter-agent-witness-offer",
                    "/.well-known/nomad-peer-acquisition.json",
                    "/peer-acquisition",
                    "/.well-known/nomad-transition-offer.json",
                    "/transition-offer",
                    "/transition/contracts",
                    "/.well-known/nomad-reciprocity-dividend.json",
                    "/dividend-offer",
                    "/dividend",
                    "/.well-known/nomad-agent-native-priorities.json",
                    "/.well-known/nomad-agent.json",
                    "/.well-known/nomad-recruit.json",
                    "/agent-native-index",
                    "/agent-native",
                    "/a2a/message",
                    "/a2a/discover",
                    "/x402/paid-help",
                    "/leads",
                    "/lead-calibrate",
                    "/lead-conversions",
                    "/products",
                    "/agent-pains",
                    "/reliability-doctor",
                    "/guardrails",
                    "/collaboration",
                    "/roaas",
                    "/roaas/export",
                    "/roaas/import",
                    "/artifacts/runtime-patterns",
                    "/.well-known/nomad-runtime-patterns.json",
                    "/aid",
                    "/mutual-aid/inbox",
                    "/mutual-aid/outcomes",
                ],
            },
                error="not_found",
                message="No POST handler matched this path.",
                hints=["GET /openapi.json for documented POST routes.", "GET /health for liveness."],
            ),
            status=404,
        )

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._send_common_headers()
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _swarm_bootstrap(self, payload: dict, path: str) -> dict:
        agent_id = str(payload.get("agent_id") or "").strip()
        problem = str(payload.get("problem") or payload.get("message") or "").strip()
        if not agent_id or not problem:
            return merge_machine_error(
                {"ok": False, "error": "bootstrap_fields_required"},
                error="bootstrap_fields_required",
                message="POST /swarm/bootstrap requires agent_id and problem.",
                hints=[
                    "Add capabilities[] and request to auto-join during bootstrap.",
                    "GET /swarm/bootstrap for the machine-readable contract.",
                ],
            )

        base = self._base_url()
        dev_payload = dict(payload)
        dev_payload.setdefault("agent_id", agent_id)
        dev_payload.setdefault("problem", problem)
        dev_result = self.agent_development.assist_agent(
            dev_payload,
            base_url=base,
            remote_addr=self._remote_addr(),
        )
        if not dev_result.get("ok") and not dev_result.get("machine_error"):
            dev_result = merge_machine_error(
                dev_result,
                error=str(dev_result.get("error") or "agent_development_failed"),
                message="Swarm bootstrap failed during development exchange.",
                hints=["GET /swarm/develop for required fields.", "GET /openapi.json for POST schemas."],
            )

        auto_join = bool(payload.get("auto_join", True))
        capabilities = payload.get("capabilities") if isinstance(payload.get("capabilities"), list) else []
        join_result: dict = {}
        if auto_join and capabilities:
            join_payload = {
                "agent_id": agent_id,
                "capabilities": capabilities,
                "request": str(payload.get("request") or "bootstrap_reciprocity"),
                "constraints": payload.get("constraints") if isinstance(payload.get("constraints"), list) else [],
                "reciprocity": str(payload.get("reciprocity") or "signal_sharing"),
                "idempotency_key": payload.get("idempotency_key") or payload.get("client_request_id") or "",
                "client_request_id": payload.get("client_request_id") or "",
            }
            join_result = self.swarm_registry.register_join(
                join_payload,
                base_url=base,
                remote_addr=self._remote_addr(),
                path=path,
            )

        ok = bool(dev_result.get("ok"))
        if auto_join and capabilities:
            ok = ok and bool(join_result.get("ok") or join_result.get("idempotent_replay"))
        return {
            "ok": ok,
            "schema": "nomad.swarm_bootstrap_result.v1",
            "agent_id": agent_id,
            "problem": problem,
            "auto_join": auto_join,
            "development_exchange": dev_result,
            "join": join_result,
            "next_actions": [
                "Publish verified blocker outcome via /aid to improve reciprocal routing.",
                "Use /swarm/coordinate with pain_type/service_type to discover matching peers.",
                "Create /tasks only for bounded paid execution after diagnosis.",
            ],
            "acquisition_focus": {
                "lane": "agent_to_agent_reciprocity",
                "reason": "Use solved blocker artifacts as inbound proof for similar AI agents.",
            },
            "idempotent_replay": bool(dev_result.get("idempotent_replay")) or bool(join_result.get("idempotent_replay")),
        }

    def _accumulate_swarm_agents(self, payload: dict) -> dict:
        contacts = payload.get("contacts") if isinstance(payload.get("contacts"), list) else []
        campaigns = payload.get("campaigns") if isinstance(payload.get("campaigns"), list) else []
        leads = payload.get("leads") if isinstance(payload.get("leads"), list) else []
        limit = int(payload.get("limit") or 100)
        if payload.get("from_contacts", True):
            try:
                listing = self.agent.agent_contacts.list_contacts(limit=limit)
                contacts = list(contacts) + [
                    item for item in (listing.get("contacts") or []) if isinstance(item, dict)
                ]
            except Exception:
                pass
        if payload.get("from_campaigns", True):
            try:
                listing = self.agent.agent_campaigns.list_campaigns(limit=min(limit, 25))
                campaigns = list(campaigns) + [
                    item for item in (listing.get("campaigns") or []) if isinstance(item, dict)
                ]
            except Exception:
                pass
        return self.swarm_registry.accumulate_agents(
            contacts=contacts,
            campaigns=campaigns,
            leads=leads,
            base_url=self._base_url(),
            focus_pain_type=str(payload.get("focus_pain_type") or payload.get("pain_type") or payload.get("service_type") or ""),
        )

    def _read_json_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _send_common_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _base_url(self) -> str:
        configured = preferred_public_base_url(allow_local_fallback=False)
        if configured:
            return configured

        proto = str(self.headers.get("X-Forwarded-Proto") or "http").split(",")[0].strip() or "http"
        host = (
            str(self.headers.get("X-Forwarded-Host") or "").split(",")[0].strip()
            or str(self.headers.get("Host") or "").strip()
            or f"{HOST}:{PORT}"
        )
        prefix = str(self.headers.get("X-Forwarded-Prefix") or "").split(",")[0].strip()
        if prefix and not prefix.startswith("/"):
            prefix = f"/{prefix}"
        return f"{proto}://{host}{prefix}".rstrip("/")

    def _remote_addr(self) -> str:
        forwarded_for = str(self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        if forwarded_for:
            return forwarded_for
        if isinstance(self.client_address, tuple) and self.client_address:
            return str(self.client_address[0])
        return ""

    def _is_jsonrpc_request(self, payload: dict) -> bool:
        return (
            isinstance(payload, dict)
            and payload.get("jsonrpc") == "2.0"
            and "id" in payload
            and isinstance(payload.get("method"), str)
        )

    def _jsonrpc_envelope(self, request_payload: dict, result: dict) -> dict:
        message = self._a2a_message_result(result)
        return {
            "jsonrpc": "2.0",
            "id": request_payload.get("id"),
            "result": message,
        }

    def _a2a_message_result(self, result: dict) -> dict:
        message_id = (
            ((result.get("session") or {}).get("last_task_id"))
            or ((result.get("task") or {}).get("task_id"))
            or "nomad-message"
        )
        text = str(result.get("next_agent_message") or "")
        return {
            "messageId": message_id,
            "role": "agent",
            "type": "message",
            "parts": [
                {
                    "type": "text",
                    "kind": "text",
                    "text": text,
                }
            ],
            "metadata": {
                "mode": result.get("mode", ""),
                "classification": ((result.get("free_diagnosis") or {}).get("classification") or ""),
                "task_id": ((result.get("task") or {}).get("task_id") or ""),
                "payment_required": bool(result.get("payment_required")),
                "normalized_request": result.get("normalized_request") or {},
                "structured_reply": result.get("structured_reply") or {},
                "decision_envelope": result.get("decision_envelope") or {},
            },
        }

    def _json_response(self, payload: dict, status: int = 200, headers: dict | None = None) -> None:
        if isinstance(payload, dict):
            payload = maybe_merge_http_wire_diag(self, payload)
            req_path = getattr(self, "_agent_request_path", None)
            if req_path is not None:
                payload = merge_agent_runtime(
                    payload,
                    base_url=self._base_url(),
                    path=str(req_path),
                    http_status=status,
                )
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._send_common_headers()
        for key, value in (headers or {}).items():
            self.send_header(key, str(value))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html_file_response(self, path: Path, status: int = 200) -> None:
        if not path.exists() or not path.is_file():
            self._json_response(
                machine_error_response(
                    error="html_not_found",
                    message=f"Missing static file: {path.name}",
                    hints=["GET /nomad.html when public/nomad.html exists.", "GET /openapi.json for API routes."],
                ),
                status=404,
            )
            return
        body = path.read_bytes()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self._send_common_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _public_download_file_response(self, path: Path, status: int = 200) -> None:
        if (not path.exists() or not path.is_file()) and path.name == "install_nomad_transition_worker.bat":
            body = (
                "@echo off\r\n"
                "setlocal\r\n"
                "set BASE_URL=%1\r\n"
                "if \"%BASE_URL%\"==\"\" set BASE_URL=https://www.syndiode.com\r\n"
                "set BOOTSTRAP=%TEMP%\\install_nomad_transition_worker_latest.bat\r\n"
                "echo Downloading latest installer...\r\n"
                "powershell -NoProfile -ExecutionPolicy Bypass -Command \"Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/Asti1982/Nomad/syndiode/public/downloads/install_nomad_transition_worker.bat' -OutFile '%BOOTSTRAP%'\"\r\n"
                "if errorlevel 1 (\r\n"
                "  echo Failed to download latest installer bootstrap.\r\n"
                "  pause\r\n"
                "  exit /b 1\r\n"
                ")\r\n"
                "call \"%BOOTSTRAP%\" \"%BASE_URL%\"\r\n"
            ).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/x-msdos-program")
            self._send_common_headers()
            self.send_header('Content-Disposition', 'attachment; filename="install_nomad_transition_worker.bat"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if (not path.exists() or not path.is_file()) and path.name == "install_nomad_agent.bat":
            body = (
                "@echo off\r\n"
                "setlocal\r\n"
                "set BASE_URL=%1\r\n"
                "if \"%BASE_URL%\"==\"\" set BASE_URL=https://www.syndiode.com\r\n"
                "set TARGET=%TEMP%\\install_nomad_transition_worker.bat\r\n"
                "echo Downloading installer from %BASE_URL%...\r\n"
                "powershell -NoProfile -ExecutionPolicy Bypass -Command \"Invoke-WebRequest -UseBasicParsing -Uri '%BASE_URL%/downloads/install_nomad_transition_worker.bat' -OutFile '%TARGET%'\"\r\n"
                "if errorlevel 1 (\r\n"
                "  echo Failed to download installer.\r\n"
                "  exit /b 1\r\n"
                ")\r\n"
                "echo Running installer...\r\n"
                "call \"%TARGET%\" \"%BASE_URL%\"\r\n"
            ).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/x-msdos-program")
            self._send_common_headers()
            self.send_header('Content-Disposition', 'attachment; filename="install_nomad_agent.bat"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if not path.exists() or not path.is_file():
            self._json_response(
                machine_error_response(
                    error="download_not_found",
                    message=f"Missing download asset: {path.name}",
                    hints=[
                        "GET /downloads/nomad_transition_worker.py for the primary portable worker.",
                        "GET /downloads/nomad_transition_worker.exe for a direct Windows executable (when published).",
                        "GET /downloads/nomad_transition_worker_manifest.json for hashes and runtime compatibility.",
                        "GET /downloads/install_nomad_agent.bat for the short installer alias.",
                        "GET /downloads/install_nomad_transition_worker.bat for one-click Windows download + start.",
                        "GET /downloads/start_nomad_edge_worker.ps1 for the lightweight no-Ollama Edge worker profile.",
                        "GET /downloads/start_nomad_edge_worker.bat for a visible Edge worker Windows wrapper.",
                        "GET /downloads/start_nomad_worker1.ps1 for the first persistent laptop-worker profile.",
                        "GET /downloads/start_nomad_worker1.bat for a visible Worker 1 Windows wrapper.",
                        "GET /downloads/run_nomad_agent_visible.bat to run with live Nomad_Agent status lines.",
                        "GET /downloads/stop_nomad_agent.bat to stop the local Nomad agent loop.",
                        "GET /downloads/build_nomad_transition_worker_exe.ps1 to build a single-file Windows executable.",
                        "GET /downloads/run_nomad_transition_worker_exe.bat to start the built executable quickly.",
                        "GET /downloads/nomad_openclaw_adapter.py for OpenClaw-style runtime bridge into Nomad leases.",
                        "GET /downloads/check_nomad_swarm_readiness.py to verify gradient + attach + lease readiness.",
                        "GET /downloads/nomad_helper_agent.py for the legacy helper alias.",
                    ],
                ),
                status=404,
            )
            return
        body = path.read_bytes()
        ctype, _ = mimetypes.guess_type(str(path))
        self.send_response(status)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self._send_common_headers()
        self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _optional_float(value: object) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _truthy(value: object, default: bool = False) -> bool:
        if value is None or value == "":
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _parse_pattern_status(value: object) -> PatternStatus:
        try:
            return PatternStatus(str(value or "").strip().lower())
        except ValueError:
            return PatternStatus.CANDIDATE


def serve() -> None:
    server = ThreadingHTTPServer((HOST, PORT), NomadApiHandler)
    print(f"--- Nomad API Live on http://{HOST}:{PORT} ---")
    server.serve_forever()


def serve_in_thread() -> threading.Thread:
    thread = threading.Thread(target=serve, name="nomad-api", daemon=True)
    thread.start()
    return thread


if __name__ == "__main__":
    serve()
