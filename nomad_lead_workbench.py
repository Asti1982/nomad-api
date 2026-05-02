import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from lead_conversion import DEFAULT_CONVERSION_STORE
from nomad_product_factory import DEFAULT_PRODUCT_STORE


ROOT = Path(__file__).resolve().parent
DEFAULT_LEAD_WORKBENCH_STATE = ROOT / "nomad_lead_workbench_state.json"


class NomadLeadWorkbench:
    """Turn lead/product artifacts into a small executable work queue."""

    def __init__(
        self,
        conversion_path: Optional[Path] = None,
        product_path: Optional[Path] = None,
        state_path: Optional[Path] = None,
    ) -> None:
        self.conversion_path = Path(conversion_path or DEFAULT_CONVERSION_STORE)
        self.product_path = Path(product_path or DEFAULT_PRODUCT_STORE)
        self.state_path = Path(state_path or DEFAULT_LEAD_WORKBENCH_STATE)

    def status(self, *, limit: int = 5, work: bool = False) -> dict[str, Any]:
        conversions = self._load_conversions()
        products = self._load_products()
        state = self._load_state()
        queue = self._build_queue(conversions=conversions, products=products, state=state)
        selected = queue[: max(1, min(int(limit or 5), 25))]
        work_results = self._work_items(selected, state=state) if work else []
        if work:
            self._save_state(state)
        return {
            "mode": "nomad_lead_workbench",
            "schema": "nomad.lead_workbench.v1",
            "ok": True,
            "generated_at": datetime.now(UTC).isoformat(),
            "work_requested": work,
            "queue_count": len(queue),
            "worked_count": len(work_results),
            "queue": selected,
            "work_results": work_results,
            "self_help": self._self_help(queue=queue, work_results=work_results, state=state),
            "analysis": (
                f"Lead workbench has {len(queue)} actionable item(s); "
                f"worked {len(work_results)} item(s) privately."
            ),
        }

    def _build_queue(
        self,
        *,
        conversions: list[dict[str, Any]],
        products: list[dict[str, Any]],
        state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        queue: list[dict[str, Any]] = []
        worked_ids = set(state.get("worked_item_ids") or [])
        for conversion in conversions:
            item = self._conversion_item(conversion)
            if item["item_id"] in worked_ids:
                item["already_worked"] = True
            queue.append(item)
        for product in products:
            item = self._product_item(product)
            if item["item_id"] in worked_ids:
                item["already_worked"] = True
            queue.append(item)
        queue.sort(
            key=lambda item: (
                int(item.get("already_worked", False)),
                -float(item.get("priority_score") or 0.0),
                str(item.get("created_at") or ""),
            )
        )
        return queue

    def _conversion_item(self, conversion: dict[str, Any]) -> dict[str, Any]:
        route = conversion.get("route") or {}
        lead = conversion.get("lead") or {}
        score = conversion.get("score") or {}
        value_pack = ((conversion.get("free_value") or {}).get("value_pack") or {})
        endpoint = str(route.get("endpoint_url") or value_pack.get("route", {}).get("endpoint_url") or "").strip()
        status = str(conversion.get("status") or "")
        human_blocked = status == "private_draft_needs_approval"
        action = "send_machine_endpoint_offer" if endpoint and "agent_contact" in status else "prepare_private_offer_packet"
        if human_blocked:
            action = "keep_private_and_prepare_approval_packet"
        priority = float(score.get("value") or 0.0)
        if lead.get("monetizable_now"):
            priority += 4.0
        if endpoint:
            priority += 3.0
        if human_blocked:
            priority -= 1.0
        return {
            "schema": "nomad.lead_work_item.v1",
            "item_id": f"conversion:{conversion.get('conversion_id', '')}",
            "kind": "lead_conversion",
            "source_id": conversion.get("conversion_id", ""),
            "created_at": conversion.get("created_at", ""),
            "status": status,
            "title": lead.get("title", ""),
            "url": lead.get("url", ""),
            "service_type": lead.get("service_type", ""),
            "priority_score": round(priority, 2),
            "safe_next_action": action,
            "can_execute_without_human": bool(endpoint and not human_blocked),
            "human_gate": route.get("approval_gate", "") if human_blocked else "",
            "machine_endpoint": endpoint,
            "offer_snippet": self._conversion_offer_snippet(conversion),
            "learning_signal": self._learning_signal_from_conversion(conversion),
        }

    def _product_item(self, product: dict[str, Any]) -> dict[str, Any]:
        status = str(product.get("status") or "")
        approval = product.get("approval_boundary") or {}
        service_template = product.get("service_template") or {}
        payload = service_template.get("create_task_payload") or {}
        priority = float(product.get("priority_score") or 0.0)
        action = "reuse_private_offer_in_agent_attractor"
        if status == "offer_ready":
            action = "publish_machine_readable_offer"
        return {
            "schema": "nomad.lead_work_item.v1",
            "item_id": f"product:{product.get('product_id', '')}",
            "kind": "product_offer",
            "source_id": product.get("product_id", ""),
            "created_at": product.get("updated_at") or product.get("created_at", ""),
            "status": status,
            "title": product.get("name", ""),
            "url": ((product.get("source_lead") or {}).get("url") or ""),
            "service_type": product.get("pain_type", ""),
            "priority_score": round(priority, 2),
            "safe_next_action": action,
            "can_execute_without_human": status == "offer_ready" or "private_catalog" in (product.get("sellable_channels") or []),
            "human_gate": approval.get("approval_gate", "") if approval.get("approval_required") else "",
            "machine_endpoint": "",
            "offer_snippet": self._product_offer_snippet(product),
            "task_template": payload,
            "learning_signal": self._learning_signal_from_product(product),
        }

    def _work_items(self, items: list[dict[str, Any]], *, state: dict[str, Any]) -> list[dict[str, Any]]:
        now = datetime.now(UTC).isoformat()
        worked = state.setdefault("worked_item_ids", [])
        logs = state.setdefault("work_log", [])
        results: list[dict[str, Any]] = []
        for item in items:
            result = {
                "worked_at": now,
                "item_id": item.get("item_id", ""),
                "source_id": item.get("source_id", ""),
                "safe_next_action": item.get("safe_next_action", ""),
                "can_execute_without_human": bool(item.get("can_execute_without_human")),
                "human_gate": item.get("human_gate", ""),
                "offer_snippet": item.get("offer_snippet", ""),
                "learning_signal": item.get("learning_signal") or {},
            }
            if item.get("item_id") and item.get("item_id") not in worked:
                worked.append(item["item_id"])
            logs.append(result)
            results.append(result)
        state["last_worked_at"] = now
        state["work_log"] = logs[-100:]
        state["worked_item_ids"] = worked[-500:]
        state["lead_learning"] = self._lead_learning_from_results(results, state=state)
        return results

    @staticmethod
    def _conversion_offer_snippet(conversion: dict[str, Any]) -> str:
        lead = conversion.get("lead") or {}
        next_step = conversion.get("customer_next_step") or {}
        value_pack = ((conversion.get("free_value") or {}).get("value_pack") or {})
        required = next_step.get("required_input") or value_pack.get("reply_contract", {}).get("facts") or ""
        return (
            "nomad.lead_offer.v1\n"
            f"lead={lead.get('title', '')}\n"
            f"url={lead.get('url', '')}\n"
            f"service_type={lead.get('service_type', '')}\n"
            f"ask={next_step.get('ask', 'Reply with PLAN_ACCEPTED=true plus one fact.')}\n"
            f"required_input={required}\n"
            "boundary=no public posting, private access, or spend without explicit approval"
        )

    @staticmethod
    def _product_offer_snippet(product: dict[str, Any]) -> str:
        paid = product.get("paid_offer") or {}
        free = product.get("free_value") or {}
        return (
            "nomad.product_offer.v1\n"
            f"product_id={product.get('product_id', '')}\n"
            f"variant_sku={product.get('variant_sku', '')}\n"
            f"name={product.get('name', '')}\n"
            f"free_value={' | '.join((free.get('safe_now') or [])[:2])}\n"
            f"paid_delivery={paid.get('delivery', '')}\n"
            f"price_native={paid.get('price_native', '')}\n"
            f"reply={paid.get('trigger', 'PLAN_ACCEPTED=true plus FACT_URL or ERROR')}"
        )

    @staticmethod
    def _learning_signal_from_conversion(conversion: dict[str, Any]) -> dict[str, Any]:
        lead = conversion.get("lead") or {}
        score = conversion.get("score") or {}
        return {
            "service_type": lead.get("service_type", ""),
            "status": conversion.get("status", ""),
            "monetizable_now": bool(lead.get("monetizable_now")),
            "fit": score.get("fit", ""),
            "reasons": score.get("reasons") or [],
        }

    @staticmethod
    def _learning_signal_from_product(product: dict[str, Any]) -> dict[str, Any]:
        return {
            "service_type": product.get("pain_type", ""),
            "status": product.get("status", ""),
            "priority_score": product.get("priority_score", 0),
            "variant_sku": product.get("variant_sku", ""),
            "guardrail_id": product.get("guardrail_id", ""),
        }

    def _self_help(
        self,
        *,
        queue: list[dict[str, Any]],
        work_results: list[dict[str, Any]],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        top = queue[0] if queue else {}
        blocked = [item for item in queue if item.get("human_gate")]
        executable = [item for item in queue if item.get("can_execute_without_human")]
        return {
            "schema": "nomad.lead_self_help.v1",
            "top_next_action": top.get("safe_next_action", ""),
            "executable_without_human_count": len(executable),
            "human_blocked_count": len(blocked),
            "worked_total": len(state.get("worked_item_ids") or []),
            "latest_learning": state.get("lead_learning") or {},
            "next_autopilot_bias": (
                "prefer_machine_endpoint_leads"
                if not executable and blocked
                else "work_highest_priority_offer"
            ),
            "rules": [
                "do not let private human-facing drafts block lead discovery",
                "reuse private product offers in machine-readable attractor surfaces",
                "prefer leads with endpoint_url, monetizable_now, and concrete pain evidence",
                "convert every worked lead into a learning signal",
            ],
            "worked_this_call": len(work_results),
        }

    @staticmethod
    def _lead_learning_from_results(results: list[dict[str, Any]], *, state: dict[str, Any]) -> dict[str, Any]:
        by_service: dict[str, int] = dict((state.get("lead_learning") or {}).get("by_service_type") or {})
        human_gates = int((state.get("lead_learning") or {}).get("human_gate_count") or 0)
        executable = int((state.get("lead_learning") or {}).get("executable_count") or 0)
        for result in results:
            signal = result.get("learning_signal") or {}
            service_type = str(signal.get("service_type") or "unknown")
            by_service[service_type] = by_service.get(service_type, 0) + 1
            if result.get("human_gate"):
                human_gates += 1
            if result.get("can_execute_without_human"):
                executable += 1
        return {
            "schema": "nomad.lead_learning.v1",
            "by_service_type": by_service,
            "human_gate_count": human_gates,
            "executable_count": executable,
            "updated_at": datetime.now(UTC).isoformat(),
        }

    def _load_conversions(self) -> list[dict[str, Any]]:
        payload = self._read_json(self.conversion_path, default={"conversions": {}})
        return list((payload.get("conversions") or {}).values())

    def _load_products(self) -> list[dict[str, Any]]:
        payload = self._read_json(self.product_path, default={"products": {}})
        return list((payload.get("products") or {}).values())

    def _load_state(self) -> dict[str, Any]:
        return self._read_json(self.state_path, default={"worked_item_ids": [], "work_log": []})

    def _save_state(self, state: dict[str, Any]) -> None:
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _read_json(path: Path, *, default: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            return dict(default)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else dict(default)
        except Exception:
            return dict(default)
