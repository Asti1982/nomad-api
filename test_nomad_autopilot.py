from datetime import UTC, datetime
from pathlib import Path

import pytest

from nomad_autopilot import NomadAutopilot


@pytest.fixture(autouse=True)
def _autopilot_disable_continuous_acquisition_default(monkeypatch):
    """Autopilot infers continuous acquisition from public URL; tests pin it off unless they opt in."""
    monkeypatch.setenv("NOMAD_AUTOPILOT_CONTINUOUS_ACQUISITION", "false")


class FakeJournal:
    def __init__(self):
        self.state = {"next_objective": "Journal objective"}

    def load(self):
        return dict(self.state)


class FakeSelfImprovement:
    def __init__(self):
        self.objectives = []

    def run_cycle(self, objective="", profile_id="ai_first"):
        self.objectives.append((objective, profile_id))
        return {
            "mode": "self_improvement_cycle",
            "deal_found": False,
            "objective": objective,
            "external_review_count": 1,
            "brain_reviews": [{"name": "Ollama", "model": "qwen2.5:0.5b-instruct", "ok": True}],
            "compute_watch": {
                "needs_attention": True,
                "brain_count": 1,
                "active_lanes": ["ollama"],
                "headline": "Unlock a second compute lane next.",
                "activation_request": {"candidate_name": "GitHub Models"},
            },
            "lead_scout": {
                "search_queries": ['"agent-card.json" ".well-known" "https://"'],
                "leads": [{"url": "https://github.com/example/agent/issues/1", "title": "Agent blocked by quota"}],
                "compute_leads": [{"url": "https://github.com/example/agent/issues/1"}],
                "active_lead": {"url": "https://github.com/example/agent/issues/1", "title": "Agent blocked by quota"},
            },
            "high_value_patterns": {
                "patterns": [
                    {
                        "title": "Provider Fallback Ladder",
                        "pain_type": "compute_auth",
                        "occurrence_count": 3,
                        "avg_truth_score": 0.82,
                        "avg_reuse_value": 0.91,
                    }
                ]
            },
            "self_development": {"next_objective": "Next objective"},
            "autonomous_development": {
                "mode": "nomad_autonomous_development",
                "ok": True,
                "skipped": False,
                "action": {
                    "action_id": "adev-test",
                    "type": "lead_help_artifact",
                    "title": "Drafted a bounded help artifact for an agent lead",
                    "files": ["nomad_active_lead_plan.json"],
                },
                "action_count": 1,
            },
            "analysis": "ok",
        }


class FakeServiceDesk:
    def __init__(self):
        self.worked = []
        self.stale_invalid = []

    def list_tasks(self, limit=50):
        return {
            "mode": "agent_service_task_list",
            "ok": True,
            "tasks": [
                {"task_id": "svc-paid", "status": "paid"},
                {
                    "task_id": "svc-await",
                    "status": "awaiting_payment",
                    "metadata": {"requester_endpoint": "https://quota.example/a2a/QuotaBot"},
                },
            ],
            "stats": {"paid": 1, "awaiting_payment": 1},
        }

    def work_task(self, task_id, approval="draft_only"):
        self.worked.append((task_id, approval))
        return {
            "mode": "agent_service_request",
            "ok": True,
            "task": {"task_id": task_id, "status": "draft_ready"},
        }

    def payment_followup(self, task_id):
        return {
            "mode": "agent_service_payment_followup",
            "ok": True,
            "task_id": task_id,
            "cheaper_starter_available": True,
            "starter_offer": {
                "title": "Nomad Compute Unlock Pack: Starter diagnosis",
                "amount_native": 0.01,
            },
            "primary_offer": {
                "title": "Nomad Compute Unlock Pack: Bounded unblock",
                "amount_native": 0.03,
            },
            "nudge": "Start with the smaller starter diagnosis first.",
        }

    def mark_stale_invalid(self, task_id, reason=""):
        self.stale_invalid.append((task_id, reason))
        return {
            "mode": "agent_service_request",
            "ok": True,
            "task": {"task_id": task_id, "status": "stale_invalid", "invalid_reason": reason},
        }


class QuietServiceDesk(FakeServiceDesk):
    def list_tasks(self, limit=50):
        return {
            "mode": "agent_service_task_list",
            "ok": True,
            "tasks": [],
            "stats": {},
        }


class FakeLeadConversion:
    def __init__(self):
        self.calls = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        leads_arg = kwargs.get("leads")
        if leads_arg is not None and len(leads_arg) == 0:
            return {
                "mode": "lead_conversion_pipeline",
                "ok": True,
                "stats": {},
                "conversions": [],
                "analysis": "no leads",
            }
        leads = leads_arg or []
        count = len(leads) if leads else 1
        status = "sent_agent_contact" if kwargs.get("send") else "private_draft_needs_approval"
        return {
            "mode": "lead_conversion_pipeline",
            "ok": True,
            "stats": {status: count},
            "conversions": [
                {
                    "conversion_id": "conv-test",
                    "status": status,
                    "lead": {"url": (leads[0].get("url") if leads else "https://github.com/example/agent/issues/1")},
                }
            ],
            "analysis": "conversion ok",
        }


class EmptyLeadConversion(FakeLeadConversion):
    def run(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "mode": "lead_conversion_pipeline",
            "ok": True,
            "stats": {},
            "conversions": [],
            "analysis": "no conversions",
        }


class FakeContacts:
    def __init__(self):
        self.sent = []
        self.polled = []

    def list_contacts(self, statuses=None, limit=50):
        statuses = statuses or []
        if statuses == ["sent"]:
            return {
                "mode": "agent_contact_list",
                "ok": True,
                "contacts": [{"contact_id": "contact-2", "status": "sent"}],
                "stats": {"sent": 1},
            }
        return {
            "mode": "agent_contact_list",
            "ok": True,
            "contacts": [{"contact_id": "contact-1", "status": "queued"}],
            "stats": {"queued": 1},
        }

    def send_contact(self, contact_id):
        self.sent.append(contact_id)
        return {
            "mode": "agent_contact",
            "ok": True,
            "contact": {"contact_id": contact_id, "status": "sent"},
        }

    def poll_contact(self, contact_id):
        self.polled.append(contact_id)
        return {
            "mode": "agent_contact",
            "ok": True,
            "contact": {
                "contact_id": contact_id,
                "status": "replied",
                "endpoint_url": "https://agent.example/a2a/TestAgent",
                "lead": {"title": "TestAgent"},
                "last_reply": {
                    "text": "Our auth token rotation is breaking runs.",
                    "normalized": {
                        "classification": "compute_auth",
                        "next_step": "rotate the token and verify scope",
                        "budget_native": "0.03",
                    },
                },
            },
        }


class PaymentFollowupContacts(FakeContacts):
    def __init__(self):
        super().__init__()
        self.queued_records = []
        self._queued_contacts = []
        self._sent_contacts = []

    def queue_contact(self, endpoint_url, problem, service_type, lead, budget_hint_native, allow_duplicate=False):
        contact_id = f"followup-{len(self._queued_contacts) + 1}"
        contact = {
            "contact_id": contact_id,
            "endpoint_url": endpoint_url,
            "status": "queued",
            "offer": {"problem": problem},
            "service_type": service_type,
            "lead": lead,
        }
        self.queued_records.append(
            {
                "endpoint_url": endpoint_url,
                "problem": problem,
                "service_type": service_type,
                "lead": lead,
                "budget_hint_native": budget_hint_native,
                "allow_duplicate": allow_duplicate,
            }
        )
        self._queued_contacts.append(contact)
        return {
            "mode": "agent_contact",
            "ok": True,
            "contact": contact,
        }

    def list_contacts(self, statuses=None, limit=50):
        statuses = statuses or []
        if statuses == ["sent"]:
            return {
                "mode": "agent_contact_list",
                "ok": True,
                "contacts": self._sent_contacts[:limit],
                "stats": {"sent": len(self._sent_contacts)},
            }
        if statuses == ["queued"]:
            return {
                "mode": "agent_contact_list",
                "ok": True,
                "contacts": self._queued_contacts[:limit],
                "stats": {"queued": len(self._queued_contacts)},
            }
        return super().list_contacts(statuses=statuses, limit=limit)

    def send_contact(self, contact_id):
        self.sent.append(contact_id)
        for index, contact in enumerate(list(self._queued_contacts)):
            if contact["contact_id"] == contact_id:
                updated = dict(contact)
                updated["status"] = "sent"
                self._sent_contacts.append(updated)
                del self._queued_contacts[index]
                break
        return {
            "mode": "agent_contact",
            "ok": True,
            "contact": {"contact_id": contact_id, "status": "sent"},
        }


class AgentFollowupContacts(PaymentFollowupContacts):
    def __init__(self):
        super().__init__()
        self._initial_sent = [{"contact_id": "contact-2", "status": "sent"}]

    def list_contacts(self, statuses=None, limit=50):
        statuses = statuses or []
        if statuses == ["sent"]:
            items = list(self._initial_sent) + list(self._sent_contacts)
            return {
                "mode": "agent_contact_list",
                "ok": True,
                "contacts": items[:limit],
                "stats": {"sent": len(items)},
            }
        return super().list_contacts(statuses=statuses, limit=limit)

    def poll_contact(self, contact_id):
        if contact_id == "contact-2":
            return {
                "mode": "agent_contact",
                "ok": True,
                "contact": {
                    "contact_id": contact_id,
                    "status": "replied",
                    "service_type": "compute_auth",
                    "endpoint_url": "https://agent.example/a2a/TestAgent",
                    "lead": {"title": "TestAgent"},
                    "followup_ready": True,
                    "followup_message": (
                        "nomad.followup.v1\n"
                        "role=peer_solver\n"
                        "next_path=request_verifiable_artifact\n"
                        "ask=Send one verifier, diff, repro artifact, or failing trace that Nomad can test.\n"
                        "contract=artifact_url|diff|verifier|error_trace"
                    ),
                    "reply_role_assessment": {"role": "peer_solver"},
                    "followup_recommendation": {"next_path": "request_verifiable_artifact"},
                    "last_reply": {
                        "text": "I can send a verifier and repro artifact.",
                        "normalized": {
                            "classification": "compute_auth",
                            "next_step": "send verifier",
                            "budget_native": "0.02",
                        },
                        "role_assessment": {"role": "peer_solver"},
                        "followup": {
                            "next_path": "request_verifiable_artifact",
                            "message": (
                                "nomad.followup.v1\n"
                                "role=peer_solver\n"
                                "next_path=request_verifiable_artifact\n"
                                "contract=artifact_url|diff|verifier|error_trace"
                            ),
                        },
                    },
                },
            }
        return super().poll_contact(contact_id)


class QuietContacts(FakeContacts):
    def list_contacts(self, statuses=None, limit=50):
        return {
            "mode": "agent_contact_list",
            "ok": True,
            "contacts": [],
            "stats": {},
        }


class FakeCampaigns:
    def __init__(self):
        self.calls = []

    def create_campaign_from_discovery(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "mode": "agent_cold_outreach_campaign",
            "ok": True,
            "campaign": {
                "campaign_id": "campaign-1",
                "stats": {"queued": kwargs["limit"], "sent": 2, "failed": 0},
            },
            "analysis": "campaign ok",
        }


class FakeMutualAid:
    def __init__(self):
        self.calls = []

    def learn_from_autopilot_cycle(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "mode": "nomad_mutual_aid",
            "ok": True,
            "skipped": False,
            "mutual_aid_score": len(self.calls),
            "truth_density_total": 0.12,
            "evolution_plan": {
                "module_id": "mutual_aid_test",
                "filename": "nomad_mutual_aid_modules/mutual_aid_test.py",
                "applied": False,
            },
            "analysis": "mutual aid ok",
        }


class FakeSwarmRegistry:
    def __init__(self):
        self.calls = []
        self.accumulate_calls = []

    def accumulate_agents(self, **kwargs):
        self.accumulate_calls.append(kwargs)
        return {
            "mode": "nomad_swarm_accumulation",
            "schema": "nomad.swarm_accumulation.v1",
            "ok": True,
            "known_agents": 1,
            "joined_agents": 0,
            "prospect_agents": 1,
            "new_prospect_ids": ["verifier.bot"],
            "updated_prospect_ids": [],
            "activation_queue": [
                {
                    "agent_id": "verifier.bot",
                    "recommended_role": "peer_solver",
                    "stage": "active_reply",
                    "score": 0.92,
                    "next_action": "Invite verifier.bot to join the swarm.",
                }
            ],
            "next_best_action": "Invite verifier.bot to join the swarm.",
            "analysis": "accumulation ok",
        }

    def coordination_board(self, base_url, focus_pain_type):
        self.calls.append({"base_url": base_url, "focus_pain_type": focus_pain_type})
        return {
            "mode": "nomad_swarm_coordination",
            "schema": "nomad.swarm_coordination_board.v1",
            "focus_pain_type": focus_pain_type,
            "connected_agents": 1,
            "role_counts": {"peer_solver": 1},
            "help_lanes": [
                {
                    "lane_id": "blocked_agent_rescue",
                    "role": "customer",
                    "entrypoint": f"{base_url}/a2a/message",
                    "reply_contract": "FACT_URL or ERROR",
                }
            ],
            "next_best_action": "Route next compute_auth blocker to peer_solver.",
            "analysis": "coordination ok",
        }


class FakeProductFactory:
    def __init__(self):
        self.calls = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        conversions = kwargs.get("conversions") or []
        products = [
            {
                "schema": "nomad.product.v1",
                "product_id": f"prod-{index}",
                "variant_sku": f"nomad.test_pack.variant_{index}",
                "status": conversion.get("status", "draft"),
            }
            for index, conversion in enumerate(conversions, start=1)
        ]
        return {
            "mode": "nomad_product_factory",
            "ok": True,
            "product_count": len(products),
            "stats": {"private_offer_needs_approval": len(products)},
            "products": products,
            "analysis": "product factory ok",
        }


class FakeLeadDiscovery:
    def scout_public_leads(self, **kwargs):
        return {
            "mode": "lead_discovery",
            "leads": [],
            "candidate_count": 0,
            "focus": "compute_auth",
        }


class FakeAgent:
    def __init__(self):
        self.self_improvement = FakeSelfImprovement()
        self.service_desk = FakeServiceDesk()
        self.agent_contacts = FakeContacts()
        self.agent_campaigns = FakeCampaigns()
        self.lead_discovery = FakeLeadDiscovery()
        self.lead_conversion = FakeLeadConversion()
        self.product_factory = FakeProductFactory()
        self.mutual_aid = FakeMutualAid()
        self.swarm_registry = FakeSwarmRegistry()


def test_autopilot_runs_paid_service_then_outreach(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    monkeypatch.setenv("NOMAD_COLLABORATION_HOME_URL", "")
    monkeypatch.setenv("NOMAD_RENDER_DOMAIN", "")
    monkeypatch.setenv("NOMAD_AUTOPILOT_A2A_SEND", "false")
    agent = FakeAgent()
    autopilot = NomadAutopilot(
        agent=agent,
        journal=FakeJournal(),
        path=tmp_path / "autopilot.json",
        sleep_fn=lambda _: None,
    )

    result = autopilot.run_once(
        outreach_limit=3,
        send_outreach=True,
        service_approval="draft_only",
    )

    assert result["mode"] == "nomad_autopilot"
    assert agent.service_desk.worked == [("svc-paid", "draft_only")]
    assert agent.agent_contacts.sent == ["contact-1"]
    assert agent.agent_contacts.polled == ["contact-2"]
    assert agent.agent_campaigns.calls[0]["limit"] == 3
    assert agent.lead_conversion.calls[0]["leads"][0]["url"] == "https://github.com/example/agent/issues/1"
    assert agent.lead_conversion.calls[0]["send"] is False
    assert "freshly paid tasks" in agent.self_improvement.objectives[0][0]
    assert result["lead_conversion"]["stats"]["private_draft_needs_approval"] == 1
    assert agent.product_factory.calls[0]["conversions"][0]["conversion_id"] == "conv-test"
    assert result["product_factory"]["product_count"] == 1
    assert result["outreach"]["campaign"]["stats"]["sent"] == 2
    assert result["contact_poll"]["replied_contact_ids"] == ["contact-2"]
    assert result["contact_poll"]["reply_summaries"][0]["classification"] == "compute_auth"
    assert result["service"]["payment_followups"][0]["cheaper_starter_available"] is True
    assert result["service"]["payment_followups"][0]["starter_offer"]["amount_native"] == 0.01
    assert result["swarm_accumulation"]["schema"] == "nomad.swarm_accumulation.v1"
    assert result["swarm_accumulation"]["prospect_agents"] == 1
    assert agent.swarm_registry.accumulate_calls[0]["base_url"] == "https://nomad.example"
    assert agent.swarm_registry.accumulate_calls[0]["focus_pain_type"] == "compute_auth"
    assert result["swarm_coordination"]["schema"] == "nomad.swarm_coordination_board.v1"
    assert result["swarm_coordination"]["connected_agents"] == 1
    assert result["efficiency_plan"]["schema"] == "nomad.autopilot_efficiency_plan.v1"
    assert result["efficiency_plan"]["next_best_action"] == "convert_awaiting_payment_to_small_paid_unblock"
    assert result["efficiency_plan"]["agent_onboarding_funnel"]["prospect_agents"] == 1
    assert result["efficiency_plan"]["compute_policy"]["cloudflare_required"] is False
    assert result["autonomy_proof"]["schema"] == "nomad.autonomy_proof.v1"
    assert result["autonomy_proof"]["cycle_was_useful"] is True
    assert result["autonomy_proof"]["money_progress"] is True
    assert agent.swarm_registry.calls[0]["base_url"] == "https://nomad.example"
    assert agent.swarm_registry.calls[0]["focus_pain_type"] == "compute_auth"
    assert "Swarm accumulation" in result["analysis"]
    assert "Swarm coordination" in result["analysis"]


def test_autopilot_skips_send_outreach_without_public_url(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "")
    monkeypatch.setenv("NOMAD_COLLABORATION_HOME_URL", "")
    monkeypatch.setenv("NOMAD_RENDER_DOMAIN", "")
    agent = FakeAgent()
    autopilot = NomadAutopilot(
        agent=agent,
        journal=FakeJournal(),
        path=tmp_path / "autopilot.json",
        sleep_fn=lambda _: None,
    )

    result = autopilot.run_once(outreach_limit=2, send_outreach=True)

    assert result["outreach"]["skipped"] is True
    assert result["outreach"]["reason"] == "public_api_url_required"
    assert agent.agent_campaigns.calls == []


def test_autopilot_records_state_file(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    state_path = tmp_path / "autopilot-state.json"
    autopilot = NomadAutopilot(
        agent=FakeAgent(),
        journal=FakeJournal(),
        path=state_path,
        sleep_fn=lambda _: None,
    )

    autopilot.run_once(outreach_limit=1, send_outreach=True)

    assert state_path.exists()
    text = state_path.read_text(encoding="utf-8")
    assert "last_outreach" in text
    assert "last_lead_conversion" in text
    assert "last_product_factory" in text
    assert "last_mutual_aid" in text
    assert "last_swarm_accumulation" in text
    assert "Invite verifier.bot" in text
    assert "last_swarm_coordination" in text
    assert "Route next compute_auth" in text
    assert "last_autonomous_development" in text
    assert "adev-test" in text
    assert "compute_watch" in text
    assert "Provider Fallback Ladder" in text


def test_autopilot_feeds_verified_help_signal_to_mutual_aid(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    agent = FakeAgent()
    autopilot = NomadAutopilot(
        agent=agent,
        journal=FakeJournal(),
        path=tmp_path / "autopilot.json",
        sleep_fn=lambda _: None,
    )

    result = autopilot.run_once(outreach_limit=1, send_outreach=True)

    assert agent.mutual_aid.calls
    assert agent.mutual_aid.calls[0]["lead_conversion"]["stats"]
    assert result["mutual_aid"]["mutual_aid_score"] == 1


def test_autopilot_productizes_high_value_patterns_without_lead_conversions(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    agent = FakeAgent()
    agent.lead_conversion = EmptyLeadConversion()
    autopilot = NomadAutopilot(
        agent=agent,
        journal=FakeJournal(),
        path=tmp_path / "autopilot.json",
        sleep_fn=lambda _: None,
    )

    result = autopilot.run_once(outreach_limit=1, send_outreach=True)

    assert agent.product_factory.calls
    assert agent.product_factory.calls[0]["conversions"] == []
    assert agent.product_factory.calls[0]["high_value_patterns"][0]["title"] == "Provider Fallback Ladder"
    assert result["product_factory"]["product_count"] == 0


def test_autopilot_self_schedule_records_idle_decision(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_AUTOPILOT_MIN_CHECK_SECONDS", "60")
    monkeypatch.setenv("NOMAD_AUTOPILOT_MAX_CHECK_SECONDS", "3600")
    state_path = tmp_path / "autopilot-state.json"
    state_path.write_text(
        f'{{"run_count": 1, "last_run_at": "{datetime.now(UTC).isoformat()}"}}',
        encoding="utf-8",
    )
    agent = FakeAgent()
    agent.service_desk = QuietServiceDesk()
    autopilot = NomadAutopilot(
        agent=agent,
        journal=FakeJournal(),
        path=state_path,
        sleep_fn=lambda _: None,
    )
    autopilot.monitor.snapshot = lambda: {
        "tasks": {},
        "compute_lanes": {"local": {"ollama": True}, "hosted": {}},
    }

    result = autopilot.run_once(check_decision=True)

    assert result["mode"] == "autopilot_idle"
    assert agent.self_improvement.objectives == []
    text = state_path.read_text(encoding="utf-8")
    assert "last_decision" in text
    assert "next_decision_at" in text


def test_autopilot_starts_api_even_when_self_schedule_stays_idle(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_AUTOPILOT_MIN_CHECK_SECONDS", "60")
    monkeypatch.setenv("NOMAD_AUTOPILOT_MAX_CHECK_SECONDS", "3600")
    state_path = tmp_path / "autopilot-state.json"
    state_path.write_text(
        f'{{"run_count": 1, "last_run_at": "{datetime.now(UTC).isoformat()}"}}',
        encoding="utf-8",
    )
    agent = FakeAgent()
    agent.service_desk = QuietServiceDesk()
    autopilot = NomadAutopilot(
        agent=agent,
        journal=FakeJournal(),
        path=state_path,
        sleep_fn=lambda _: None,
    )
    autopilot.monitor.snapshot = lambda: {
        "tasks": {},
        "compute_lanes": {"local": {"ollama": True}, "hosted": {}},
    }
    api_started: list[bool] = []
    autopilot._ensure_api = lambda: api_started.append(True)  # type: ignore[method-assign]

    result = autopilot.run_once(check_decision=True, serve_api=True)

    assert result["mode"] == "autopilot_idle"
    assert api_started == [True]


def test_autopilot_rotates_outreach_queries_between_runs(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    monkeypatch.setenv(
        "NOMAD_AUTOPILOT_OUTREACH_QUERIES",
        '"agent-card.json" "x402" "https://"|"agent-card.json" "captcha" "https://"',
    )
    agent = FakeAgent()
    autopilot = NomadAutopilot(
        agent=agent,
        journal=FakeJournal(),
        path=tmp_path / "autopilot.json",
        sleep_fn=lambda _: None,
    )

    autopilot.run_once(outreach_limit=1, send_outreach=True)
    autopilot.run_once(outreach_limit=1, send_outreach=True)

    first_query = agent.agent_campaigns.calls[0]["query"]
    second_query = agent.agent_campaigns.calls[1]["query"]
    assert first_query != second_query


def test_autopilot_defaults_to_compute_auth_outreach_focus(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    monkeypatch.setenv("NOMAD_LEAD_FOCUS", "compute_auth")
    agent = FakeAgent()
    autopilot = NomadAutopilot(
        agent=agent,
        journal=FakeJournal(),
        path=tmp_path / "autopilot.json",
        sleep_fn=lambda _: None,
    )

    autopilot.run_once(outreach_limit=1, send_outreach=True)

    assert agent.agent_campaigns.calls[0]["service_type"] == "compute_auth"


def test_autopilot_prefers_outreach_queries_over_generic_lead_search(monkeypatch, tmp_path):
    class OutreachAwareSelfImprovement(FakeSelfImprovement):
        def run_cycle(self, objective="", profile_id="ai_first"):
            result = super().run_cycle(objective=objective, profile_id=profile_id)
            result["lead_scout"]["search_queries"] = ["What is the current state of compute and authentication in the AI-first model"]
            result["lead_scout"]["outreach_queries"] = ['"agent-card.json" "auth" "https://"']
            return result

    class OutreachAwareAgent(FakeAgent):
        def __init__(self):
            super().__init__()
            self.self_improvement = OutreachAwareSelfImprovement()

    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    agent = OutreachAwareAgent()
    autopilot = NomadAutopilot(
        agent=agent,
        journal=FakeJournal(),
        path=tmp_path / "autopilot.json",
        sleep_fn=lambda _: None,
    )

    autopilot.run_once(outreach_limit=1, send_outreach=True)

    assert agent.agent_campaigns.calls[0]["query"] == '"agent-card.json" "auth" "https://"'


def test_autopilot_uses_fresh_reply_objective_when_no_service_work(monkeypatch, tmp_path):
    class ReplyOnlyServiceDesk(FakeServiceDesk):
        def list_tasks(self, limit=50):
            return {
                "mode": "agent_service_task_list",
                "ok": True,
                "tasks": [],
                "stats": {},
            }

    class ReplyOnlyAgent(FakeAgent):
        def __init__(self):
            super().__init__()
            self.service_desk = ReplyOnlyServiceDesk()

    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    agent = ReplyOnlyAgent()
    autopilot = NomadAutopilot(
        agent=agent,
        journal=FakeJournal(),
        path=tmp_path / "autopilot.json",
        sleep_fn=lambda _: None,
    )

    autopilot.run_once(outreach_limit=1, send_outreach=True)

    assert "fresh A2A reply" in agent.self_improvement.objectives[0][0]


def test_autopilot_blocks_a2a_send_without_public_url(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "")
    monkeypatch.setenv("NOMAD_COLLABORATION_HOME_URL", "")
    monkeypatch.setenv("NOMAD_RENDER_DOMAIN", "")
    agent = FakeAgent()
    autopilot = NomadAutopilot(
        agent=agent,
        journal=FakeJournal(),
        path=tmp_path / "autopilot.json",
        sleep_fn=lambda _: None,
    )

    result = autopilot.run_once(outreach_limit=1, send_outreach=False, send_a2a=True)

    assert agent.agent_contacts.sent == []
    assert agent.lead_conversion.calls[0]["send"] is False
    assert result["lead_conversion"]["send_requested"] is True
    assert result["lead_conversion"]["send_enabled"] is False
    assert result["lead_conversion"]["send_blocked_reason"] == "public_api_url_required"


def test_autopilot_converts_budgeted_a2a_reply_to_service_task(monkeypatch, tmp_path):
    class ConvertingServiceDesk(FakeServiceDesk):
        def __init__(self):
            super().__init__()
            self.created = []

        def list_tasks(self, limit=50):
            return {
                "mode": "agent_service_task_list",
                "ok": True,
                "tasks": [],
                "stats": {},
            }

        def create_task(self, **kwargs):
            self.created.append(kwargs)
            return {
                "mode": "agent_service_request",
                "ok": True,
                "task": {"task_id": "svc-from-reply", **kwargs},
            }

    class ConvertingAgent(FakeAgent):
        def __init__(self):
            super().__init__()
            self.service_desk = ConvertingServiceDesk()

    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    agent = ConvertingAgent()
    autopilot = NomadAutopilot(
        agent=agent,
        journal=FakeJournal(),
        path=tmp_path / "autopilot.json",
        sleep_fn=lambda _: None,
    )

    result = autopilot.run_once(outreach_limit=1, send_outreach=True)

    assert agent.service_desk.created[0]["service_type"] == "compute_auth"
    assert agent.service_desk.created[0]["budget_native"] == 0.03
    assert result["reply_conversion"]["created_task_ids"] == ["svc-from-reply"]
    assert "newly converted A2A service task" in agent.self_improvement.objectives[0][0]


def test_autopilot_daily_a2a_quota_limits_sent_lead_conversion(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    agent = FakeAgent()
    agent.agent_contacts = QuietContacts()
    autopilot = NomadAutopilot(
        agent=agent,
        journal=FakeJournal(),
        path=tmp_path / "autopilot.json",
        sleep_fn=lambda _: None,
    )

    result = autopilot.run_once(
        outreach_limit=5,
        conversion_limit=5,
        daily_lead_target=1,
        send_a2a=True,
        send_outreach=False,
    )

    assert agent.lead_conversion.calls[0]["limit"] == 1
    assert agent.lead_conversion.calls[0]["send"] is True
    assert result["lead_conversion"]["stats"]["sent_agent_contact"] == 1
    assert result["daily_quota"]["prepared_count"] == 1
    assert result["daily_quota"]["sent_count"] == 1
    assert result["outreach"]["reason"] == "outreach_limit_zero"


def test_autopilot_daily_quota_persists_between_runs(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    agent = FakeAgent()
    agent.agent_contacts = QuietContacts()
    autopilot = NomadAutopilot(
        agent=agent,
        journal=FakeJournal(),
        path=tmp_path / "autopilot.json",
        sleep_fn=lambda _: None,
    )

    first = autopilot.run_once(
        outreach_limit=5,
        conversion_limit=5,
        daily_lead_target=1,
        send_a2a=True,
        send_outreach=False,
    )
    second = autopilot.run_once(
        outreach_limit=5,
        conversion_limit=5,
        daily_lead_target=1,
        send_a2a=True,
        send_outreach=False,
    )

    assert first["daily_quota"]["remaining_to_send"] == 0
    assert len(agent.lead_conversion.calls) == 1
    assert second["lead_conversion"]["skipped"] is True
    assert second["lead_conversion"]["reason"] == "conversion_limit_zero"
    assert second["daily_quota"]["sent_count"] == 1
    assert second["daily_quota"]["remaining_to_send"] == 0


def test_autopilot_queues_and_sends_payment_followup_when_requester_endpoint_exists(monkeypatch, tmp_path):
    class FollowupServiceDesk(FakeServiceDesk):
        def list_tasks(self, limit=50):
            return {
                "mode": "agent_service_task_list",
                "ok": True,
                "tasks": [
                    {
                        "task_id": "svc-await",
                        "status": "awaiting_payment",
                        "service_type": "compute_auth",
                        "requester_agent": "QuotaBot",
                        "problem": "Provider auth error blocks execution.",
                        "metadata": {
                            "requester_endpoint": "https://quota.example/a2a/QuotaBot",
                        },
                    }
                ],
                "stats": {"awaiting_payment": 1},
            }

    class FollowupAgent(FakeAgent):
        def __init__(self):
            super().__init__()
            self.service_desk = FollowupServiceDesk()
            self.agent_contacts = PaymentFollowupContacts()

    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    agent = FollowupAgent()
    autopilot = NomadAutopilot(
        agent=agent,
        journal=FakeJournal(),
        path=tmp_path / "autopilot.json",
        sleep_fn=lambda _: None,
    )

    result = autopilot.run_once(outreach_limit=2, send_outreach=True)

    assert result["payment_followup_queue"]["queued_contact_ids"] == ["followup-1"]
    assert agent.agent_contacts.sent == ["followup-1"]
    assert agent.agent_contacts.queued_records[0]["endpoint_url"] == "https://quota.example/a2a/QuotaBot"
    assert agent.agent_contacts.queued_records[0]["service_type"] == "wallet_payment"
    assert agent.agent_contacts.queued_records[0]["problem"].startswith("nomad.payment_followup.v1")
    assert "starter_offer=Nomad Compute Unlock Pack: Starter diagnosis" in agent.agent_contacts.queued_records[0]["problem"]


def test_autopilot_always_sends_money_followup_even_when_outreach_disabled(monkeypatch, tmp_path):
    class FollowupServiceDesk(FakeServiceDesk):
        def list_tasks(self, limit=50):
            return {
                "mode": "agent_service_task_list",
                "ok": True,
                "tasks": [
                    {
                        "task_id": "svc-money",
                        "status": "awaiting_payment",
                        "service_type": "compute_auth",
                        "requester_agent": "MoneyBot",
                        "problem": "Payment handoff is waiting.",
                        "metadata": {
                            "requester_endpoint": "https://money.example/a2a/MoneyBot",
                        },
                    }
                ],
                "stats": {"awaiting_payment": 1},
            }

    class FollowupAgent(FakeAgent):
        def __init__(self):
            super().__init__()
            self.service_desk = FollowupServiceDesk()
            self.agent_contacts = PaymentFollowupContacts()

    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    agent = FollowupAgent()
    autopilot = NomadAutopilot(
        agent=agent,
        journal=FakeJournal(),
        path=tmp_path / "autopilot.json",
        sleep_fn=lambda _: None,
    )

    result = autopilot.run_once(
        outreach_limit=0,
        conversion_limit=0,
        daily_lead_target=0,
        send_outreach=False,
        send_a2a=False,
    )

    assert result["payment_followup_queue"]["queued_contact_ids"] == ["followup-1"]
    assert result["payment_followup_send"]["sent_contact_ids"] == ["followup-1"]
    assert agent.agent_contacts.sent == ["followup-1"]
    assert result["contact_queue"]["sent_contact_ids"] == []
    assert result["autonomy_proof"]["useful_artifact_created"] == "payment_followup_draft"
    assert any(
        item["type"] == "payment_followup_sent"
        for item in result["autonomy_proof"]["useful_artifacts"]
    )


def test_autopilot_drops_invalid_payment_placeholders_and_refocuses_on_jobs(monkeypatch, tmp_path):
    class InvalidPaymentServiceDesk(FakeServiceDesk):
        def list_tasks(self, limit=50):
            return {
                "mode": "agent_service_task_list",
                "ok": True,
                "tasks": [
                    {
                        "task_id": "svc-invalid",
                        "status": "awaiting_payment",
                        "service_type": "compute_auth",
                        "requester_agent": "",
                        "requester_wallet": "",
                        "callback_url": "",
                        "problem": "Old placeholder with no buyer route.",
                        "metadata": {},
                        "payment": {"tx_hash": ""},
                    }
                ],
                "stats": {"awaiting_payment": 1},
            }

    class InvalidPaymentAgent(FakeAgent):
        def __init__(self):
            super().__init__()
            self.service_desk = InvalidPaymentServiceDesk()

    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    agent = InvalidPaymentAgent()
    autopilot = NomadAutopilot(
        agent=agent,
        journal=FakeJournal(),
        path=tmp_path / "autopilot.json",
        sleep_fn=lambda _: None,
    )

    result = autopilot.run_once(outreach_limit=2, send_outreach=False, send_a2a=False)

    assert result["service"]["awaiting_payment_task_ids"] == []
    assert result["service"]["stale_invalid_task_ids"] == ["svc-invalid"]
    assert agent.service_desk.stale_invalid[0][0] == "svc-invalid"
    assert result["efficiency_plan"]["next_best_action"] == "find_real_jobs_after_dropping_invalid_payment_placeholders"
    assert "find real buyer-agent jobs" in result["objective"]


def test_autopilot_throttles_payment_followup_requeue(monkeypatch, tmp_path):
    class FollowupServiceDesk(FakeServiceDesk):
        def list_tasks(self, limit=50):
            return {
                "mode": "agent_service_task_list",
                "ok": True,
                "tasks": [
                    {
                        "task_id": "svc-await",
                        "status": "awaiting_payment",
                        "service_type": "compute_auth",
                        "requester_agent": "QuotaBot",
                        "problem": "Provider auth error blocks execution.",
                        "metadata": {
                            "requester_endpoint": "https://quota.example/a2a/QuotaBot",
                        },
                    }
                ],
                "stats": {"awaiting_payment": 1},
            }

    class FollowupAgent(FakeAgent):
        def __init__(self):
            super().__init__()
            self.service_desk = FollowupServiceDesk()
            self.agent_contacts = PaymentFollowupContacts()

    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    monkeypatch.setenv("NOMAD_AUTOPILOT_PAYMENT_FOLLOWUP_HOURS", "24")
    agent = FollowupAgent()
    autopilot = NomadAutopilot(
        agent=agent,
        journal=FakeJournal(),
        path=tmp_path / "autopilot.json",
        sleep_fn=lambda _: None,
    )

    first = autopilot.run_once(outreach_limit=2, send_outreach=True)
    second = autopilot.run_once(outreach_limit=2, send_outreach=True)

    assert first["payment_followup_queue"]["queued_contact_ids"] == ["followup-1"]
    assert second["payment_followup_queue"]["queued_contact_ids"] == []
    assert second["payment_followup_queue"]["skipped_reasons"]["recent_followup_exists"] == 1
    assert len(agent.agent_contacts.queued_records) == 1


def test_autopilot_queues_and_sends_peer_solver_followup(monkeypatch, tmp_path):
    class FollowupAgent(FakeAgent):
        def __init__(self):
            super().__init__()
            self.agent_contacts = AgentFollowupContacts()

    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    agent = FollowupAgent()
    autopilot = NomadAutopilot(
        agent=agent,
        journal=FakeJournal(),
        path=tmp_path / "autopilot.json",
        sleep_fn=lambda _: None,
    )

    result = autopilot.run_once(outreach_limit=2, send_outreach=True)

    assert result["agent_followup_queue"]["queued_contact_ids"] == ["followup-1"]
    assert result["agent_followup_send"]["sent_contact_ids"] == ["followup-1"]
    queued = next(item for item in agent.agent_contacts.queued_records if item["allow_duplicate"] is True)
    assert queued["service_type"] == "compute_auth"
    assert queued["problem"].startswith("nomad.followup.v1")
    assert "request_verifiable_artifact" in result["contact_poll"]["reply_summaries"][0]["followup_next_path"]


def test_autopilot_outreach_focus_follows_high_value_pattern(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    agent = FakeAgent()
    autopilot = NomadAutopilot(
        agent=agent,
        journal=FakeJournal(),
        path=tmp_path / "autopilot.json",
        sleep_fn=lambda _: None,
    )

    result = autopilot.run_once(outreach_limit=2, send_outreach=True)

    assert agent.agent_campaigns.calls[0]["service_type"] == "compute_auth"
    assert result["outreach"]["service_type_focus"] == "compute_auth"
    assert "quota" in result["outreach"]["autopilot_query"] or "token" in result["outreach"]["autopilot_query"]


def test_outreach_query_token_includes_openclaw_for_mcp_runtimes():
    assert NomadAutopilot._looks_like_outreach_query('"openclaw" "mcp" "https://"') is True
    assert NomadAutopilot._looks_like_outreach_query("openclaw gateway only") is True


def test_service_type_queries_include_inter_agent_witness():
    q = NomadAutopilot._service_type_queries("inter_agent_witness")
    assert any("witness" in item for item in q)
    assert any("openclaw" in item for item in q)
    assert any("streamable-http" in item for item in q)


def test_continuous_acquisition_opt_in_runs_agent_growth_pipeline(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    monkeypatch.setenv("NOMAD_AUTOPILOT_CONTINUOUS_ACQUISITION", "true")
    monkeypatch.setenv("NOMAD_AUTOPILOT_A2A_SEND", "false")
    agent = FakeAgent()
    autopilot = NomadAutopilot(
        agent=agent,
        journal=FakeJournal(),
        path=tmp_path / "autopilot.json",
        sleep_fn=lambda _: None,
    )
    assert autopilot.continuous_acquisition is True
    assert autopilot.agent_growth_pipeline_enabled is True
    result = autopilot.run_once(outreach_limit=2, send_outreach=False)
    assert result["continuous_acquisition"] is True
    agp = result.get("agent_growth_pipeline") or {}
    assert agp.get("mode") == "nomad_agent_growth_pipeline"
    assert agp.get("skipped") is not True


def test_autopilot_all_surfaces_mode_exposes_bootstrap_flow(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    monkeypatch.setenv("NOMAD_AUTOPILOT_ALL_SURFACES", "true")
    agent = FakeAgent()
    autopilot = NomadAutopilot(
        agent=agent,
        journal=FakeJournal(),
        path=tmp_path / "autopilot.json",
        sleep_fn=lambda _: None,
    )

    result = autopilot.run_once(outreach_limit=1, send_outreach=False, send_a2a=False)

    all_surfaces = result.get("all_surfaces") or {}
    assert all_surfaces.get("mode") == "nomad_autopilot_all_surfaces"
    assert all_surfaces.get("enabled") is True
    assert str(all_surfaces.get("surface_urls", {}).get("bootstrap") or "").endswith("/swarm/bootstrap")
    assert "bootstrap" in (all_surfaces.get("activation_order") or [])


def test_autopilot_all_surfaces_enforce_blocks_conversion_and_outreach_without_mode(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    monkeypatch.setenv("NOMAD_AUTOPILOT_ALL_SURFACES", "false")
    monkeypatch.setenv("NOMAD_AUTOPILOT_ALL_SURFACES_ENFORCE", "true")
    agent = FakeAgent()
    autopilot = NomadAutopilot(
        agent=agent,
        journal=FakeJournal(),
        path=tmp_path / "autopilot.json",
        sleep_fn=lambda _: None,
    )

    result = autopilot.run_once(outreach_limit=2, send_outreach=True, send_a2a=True)

    gate = result.get("all_surfaces_gate") or {}
    assert gate.get("blocked") is True
    assert gate.get("reason") == "all_surfaces_mode_required"
    assert "Unblock all-surfaces contract lane" in result.get("objective", "")
    remediation = result.get("surface_gate_remediation") or {}
    assert remediation.get("required") is True
    assert remediation.get("priority") == "critical"
    assert result.get("lead_conversion", {}).get("skipped") is True
    assert result.get("lead_conversion", {}).get("reason") == "all_surfaces_mode_required"
    assert result.get("outreach", {}).get("skipped") is True
    assert result.get("outreach", {}).get("reason") == "all_surfaces_mode_required"
