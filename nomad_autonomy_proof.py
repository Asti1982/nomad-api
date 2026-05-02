from typing import Any


class AutonomyProofHarness:
    """Judge whether an autopilot cycle created real progress or just narration."""

    def evaluate(
        self,
        report: dict[str, Any],
        *,
        previous_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        previous_state = previous_state or {}
        artifacts = self._artifacts(report)
        useful = bool(artifacts)
        previous_streak = int(previous_state.get("useless_cycle_streak") or 0)
        useless_streak = 0 if useful else previous_streak + 1
        stuck_reason = "" if useful else self._stuck_reason(report)
        next_unlock = self._next_required_unlock(report, stuck_reason=stuck_reason)
        status = "useful_progress" if useful else ("blocked" if useless_streak >= 3 else "no_real_progress")

        return {
            "schema": "nomad.autonomy_proof.v1",
            "cycle_was_useful": useful,
            "status": status,
            "useful_artifacts": artifacts,
            "useful_artifact_created": artifacts[0]["type"] if artifacts else "",
            "external_progress": any(item["axis"] == "external" for item in artifacts),
            "money_progress": any(item["axis"] == "money" for item in artifacts),
            "agent_progress": any(item["axis"] == "agent" for item in artifacts),
            "code_progress": any(item["axis"] == "code" for item in artifacts),
            "learning_progress": any(item["axis"] == "learning" for item in artifacts),
            "useless_cycle_streak": useless_streak,
            "stuck_reason": stuck_reason,
            "next_required_unlock": next_unlock,
            "stop_self_deception": not useful,
            "should_pause_autonomy": useless_streak >= 3,
            "minimum_next_real_outcome": self._minimum_next_real_outcome(report, next_unlock=next_unlock),
            "analysis": (
                "Autonomy proof accepted this cycle because it produced real artifacts."
                if useful
                else "Autonomy proof rejected this cycle as non-useful; Nomad must get the named unlock or produce a real artifact next."
            ),
        }

    def _artifacts(self, report: dict[str, Any]) -> list[dict[str, Any]]:
        artifacts: list[dict[str, Any]] = []
        service = report.get("service") or {}
        payment_queue = report.get("payment_followup_queue") or {}
        payment_send = report.get("payment_followup_send") or {}
        contact_queue = report.get("contact_queue") or {}
        contact_poll = report.get("contact_poll") or {}
        agent_followup_queue = report.get("agent_followup_queue") or {}
        agent_followup_send = report.get("agent_followup_send") or {}
        reply_conversion = report.get("reply_conversion") or {}
        lead_conversion = report.get("lead_conversion") or {}
        product_factory = report.get("product_factory") or {}
        lead_workbench = report.get("lead_workbench") or {}
        outreach = report.get("outreach") or {}
        swarm_accumulation = report.get("swarm_accumulation") or {}
        mutual_aid = report.get("mutual_aid") or {}
        autonomous_development = report.get("autonomous_development") or {}
        self_improvement = report.get("self_improvement") or {}

        self._add_ids(artifacts, "paid_task_delivery", "money", service.get("worked_task_ids"))
        self._add_ids(artifacts, "draft_ready_task", "money", service.get("draft_ready_task_ids"))
        self._add_ids(artifacts, "payment_followup_draft", "money", [item.get("task_id") for item in service.get("payment_followups") or []])
        self._add_ids(artifacts, "payment_followup_queued", "money", payment_queue.get("queued_contact_ids"))
        self._add_ids(artifacts, "payment_followup_sent", "money", payment_send.get("sent_contact_ids"))
        self._add_ids(artifacts, "contact_sent", "external", contact_queue.get("sent_contact_ids"))
        self._add_ids(artifacts, "agent_followup_queued", "agent", agent_followup_queue.get("queued_contact_ids"))
        self._add_ids(artifacts, "agent_followup_sent", "agent", agent_followup_send.get("sent_contact_ids"))
        self._add_ids(artifacts, "agent_reply", "external", contact_poll.get("replied_contact_ids"))
        self._add_ids(artifacts, "service_task_created_from_reply", "money", reply_conversion.get("created_task_ids"))

        conversion_stats = lead_conversion.get("stats") or {}
        conversion_count = sum(int(value or 0) for value in conversion_stats.values()) if conversion_stats else 0
        if conversion_count:
            artifacts.append({"type": "lead_conversion_artifact", "axis": "external", "count": conversion_count})

        product_count = int(product_factory.get("product_count") or 0)
        if product_count:
            artifacts.append({"type": "product_offer_created", "axis": "money", "count": product_count})

        worked_leads = int(lead_workbench.get("worked_count") or 0)
        if worked_leads:
            artifacts.append({"type": "lead_queue_worked", "axis": "money", "count": worked_leads})

        campaign_stats = (outreach.get("campaign") or {}).get("stats") or {}
        queued = int(campaign_stats.get("queued") or 0)
        sent = int(campaign_stats.get("sent") or 0)
        if queued or sent:
            artifacts.append({"type": "outreach_campaign_progress", "axis": "external", "queued": queued, "sent": sent})

        prospects = int(swarm_accumulation.get("prospect_agents") or 0)
        joined = int(swarm_accumulation.get("joined_agents") or 0)
        if prospects or joined:
            artifacts.append({"type": "swarm_agent_signal", "axis": "agent", "prospects": prospects, "joined": joined})

        if mutual_aid and not mutual_aid.get("skipped") and int(mutual_aid.get("mutual_aid_score") or 0) > 0:
            artifacts.append({"type": "mutual_aid_learning", "axis": "learning", "score": int(mutual_aid.get("mutual_aid_score") or 0)})

        if autonomous_development and not autonomous_development.get("skipped"):
            action = autonomous_development.get("action") or {}
            artifacts.append({"type": "autonomous_development_action", "axis": "code", "id": action.get("action_id", "")})

        lead_scout = self_improvement.get("lead_scout") or {}
        leads = lead_scout.get("leads") or []
        if leads:
            artifacts.append({"type": "new_lead_signal", "axis": "external", "count": len(leads)})

        return artifacts

    @staticmethod
    def _add_ids(artifacts: list[dict[str, Any]], artifact_type: str, axis: str, ids: Any) -> None:
        cleaned = [str(item) for item in (ids or []) if str(item or "").strip()]
        if cleaned:
            artifacts.append({"type": artifact_type, "axis": axis, "ids": cleaned, "count": len(cleaned)})

    @staticmethod
    def _stuck_reason(report: dict[str, Any]) -> str:
        service = report.get("service") or {}
        if service.get("awaiting_payment_task_ids"):
            return "awaiting_payment_without_followup_or_verification"
        decision = report.get("decision") or {}
        if decision.get("reason"):
            return str(decision.get("reason"))
        compute_watch = (report.get("self_improvement") or {}).get("compute_watch") or {}
        if compute_watch.get("needs_attention"):
            return "compute_lane_needs_attention"
        return "no_external_or_verifiable_artifact_created"

    @staticmethod
    def _next_required_unlock(report: dict[str, Any], *, stuck_reason: str) -> str:
        payment_queue = report.get("payment_followup_queue") or {}
        payment_send = report.get("payment_followup_send") or {}
        service = report.get("service") or {}
        if service.get("awaiting_payment_task_ids"):
            if payment_send.get("sent_contact_ids"):
                return "WAIT_FOR_PAYMENT_OR_VERIFY_TX_HASH=..."
            skipped = payment_queue.get("skipped_reasons") or {}
            if int(skipped.get("requester_endpoint_missing") or 0) > 0:
                return "REQUESTER_ENDPOINT=https://... or TX_HASH=0x..."
            if payment_queue.get("reason") == "send_disabled_or_public_url_missing":
                return "PUBLIC_NOMAD_URL=https://..."
            return "WAIT_FOR_PAYMENT_OR_VERIFY_TX_HASH=..."
        if stuck_reason == "compute_lane_needs_attention":
            return "COMPUTE_PRIORITY=modal or COMPUTE_PRIORITY=local"
        if ((report.get("outreach") or {}).get("skipped") and not (report.get("public_api_url") or "").startswith("http")):
            return "PUBLIC_NOMAD_URL=https://..."
        return "PROVIDE_REAL_BLOCKER_OR_APPROVE_NEXT_ACTION=yes"

    @staticmethod
    def _minimum_next_real_outcome(report: dict[str, Any], *, next_unlock: str) -> str:
        service = report.get("service") or {}
        if service.get("awaiting_payment_task_ids"):
            return "one payment follow-up sent, one payment verified, or one task closed as stale"
        if "COMPUTE_PRIORITY" in next_unlock:
            return "one verified compute lane or one deferred learning packet with reason"
        return "one lead, reply, paid task, verifier artifact, code change, or stored learning packet"
