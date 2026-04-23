from self_development import SelfDevelopmentJournal


def test_self_development_journal_records_cycle_and_next_objective(tmp_path):
    journal = SelfDevelopmentJournal(
        path=tmp_path / "state.json",
        mutual_aid_state_path=tmp_path / "mutual_aid.json",
    )
    result = {
        "objective": "initial objective",
        "external_review_count": 2,
        "analysis": "cycle ok",
        "local_actions": [
            {
                "type": "cycle_hygiene",
                "category": "self_improvement",
                "title": "Keep one small next action.",
                "reason": "bounded progress",
                "requires_human": False,
            }
        ],
        "human_unlocks": [],
        "lead_scout": {},
        "autonomous_development": {
            "skipped": False,
            "action": {
                "action_id": "adev-test",
                "type": "cycle_hygiene",
                "title": "Recorded one bounded self-development receipt",
                "files": [],
            },
        },
    }
    state = journal.record_cycle(result)
    assert state["cycle_count"] == 1
    assert state["cycles"][0]["objective"] == "initial objective"
    assert state["last_autonomous_development"]["action_id"] == "adev-test"
    assert "Keep one small next action" in state["next_objective"]
    assert state["self_development_unlocks"][0]["candidate_id"] == "approve-next-self-dev-step"


def test_self_development_journal_prefers_active_lead(tmp_path):
    journal = SelfDevelopmentJournal(
        path=tmp_path / "state.json",
        mutual_aid_state_path=tmp_path / "mutual_aid.json",
    )
    result = {
        "objective": "lead cycle",
        "external_review_count": 1,
        "local_actions": [],
        "human_unlocks": [],
        "lead_scout": {
            "active_lead": {
                "url": "https://github.com/example/agent/issues/1",
                "pain": "agent deployment quota failure",
                "addressable_label": "Compute/auth unblock",
            }
        },
    }
    state = journal.record_cycle(result)
    assert "https://github.com/example/agent/issues/1" in state["next_objective"]
    assert "agent deployment quota failure" in state["next_objective"]
    assert "Compute/auth unblock" in state["next_objective"]
    unlock = state["self_development_unlocks"][0]
    assert unlock["candidate_id"] == "approve-active-lead-help"
    assert "APPROVE_LEAD_HELP" in unlock["human_deliverable"]


def test_self_development_journal_names_human_unlock_for_abstract_lead_discovery(tmp_path):
    journal = SelfDevelopmentJournal(
        path=tmp_path / "state.json",
        mutual_aid_state_path=tmp_path / "mutual_aid.json",
    )
    result = {
        "objective": "find leads",
        "external_review_count": 1,
        "local_actions": [],
        "human_unlocks": [
            {
                "category": "agent_customers",
                "candidate_id": "fresh-agent-customer-lead",
                "candidate_name": "Fresh agent-customer lead",
                "short_ask": "Let Nomad scout one AI agent/customer lead.",
                "human_action": "Send a lead URL.",
            }
        ],
        "lead_scout": {},
    }
    state = journal.record_cycle(result)
    unlock = state["self_development_unlocks"][0]
    assert unlock["candidate_id"] == "seed-agent-customer-source"
    assert "LEAD_URL" in unlock["human_deliverable"]


def test_self_development_journal_renders_codex_task_prompt(tmp_path):
    journal = SelfDevelopmentJournal(
        path=tmp_path / "state.json",
        mutual_aid_state_path=tmp_path / "mutual_aid.json",
    )
    journal.record_cycle(
        {
            "objective": "find leads",
            "external_review_count": 1,
            "local_actions": [],
            "human_unlocks": [],
            "lead_scout": {
                "active_lead": {
                    "url": "https://github.com/example/agent/issues/9",
                    "pain": "compute quota",
                    "addressable_label": "Compute/auth unblock",
                    "quote_summary": "diagnosis 0.001-0.003 native, unblock 0.004-0.012 native",
                    "product_package": "Nomad Compute Unlock Pack",
                }
            },
        }
    )
    autopilot_state = tmp_path / "autopilot.json"
    autopilot_state.write_text(
        (
            "{\n"
            '  "last_public_api_url": "https://nomad.example",\n'
            '  "last_self_improvement": {\n'
            '    "compute_watch": {\n'
            '      "needs_attention": true,\n'
            '      "brain_count": 1,\n'
            '      "active_lanes": ["ollama"],\n'
            '      "headline": "Unlock GitHub Models next."\n'
            "    },\n"
            '    "lead_watch": {"lead_count": 1, "compute_lead_count": 1}\n'
            "  }\n"
            "}\n"
        ),
        encoding="utf-8",
    )

    prompt = journal.codex_task_prompt(autopilot_state_path=autopilot_state)

    assert "Nomad self-development task for Codex" in prompt
    assert "https://github.com/example/agent/issues/9" in prompt
    assert "Compute/auth unblock" in prompt
    assert "0.001-0.003 native" in prompt
    assert "Nomad Compute Unlock Pack" in prompt
    assert "Compute watch:" in prompt
    assert "https://nomad.example" in prompt


def test_self_development_journal_packages_top_truth_pattern_when_same_lead_repeats(tmp_path):
    mutual_aid_state = tmp_path / "mutual_aid.json"
    mutual_aid_state.write_text(
        (
            "{\n"
            '  "truth_density_ledger": [\n'
            "    {\n"
            '      "ledger_id": "tdl-1",\n'
            '      "pain_type": "compute_auth",\n'
            '      "solution_title": "Provider Fallback Ladder",\n'
            '      "task": "Agent observed ERROR=429",\n'
            '      "truth_score": 0.81,\n'
            '      "reuse_value": {"score": 0.93, "repeat_count": 3},\n'
            '      "outcome": {"success": true},\n'
            '      "timestamp": "2026-04-21T12:00:00Z"\n'
            "    }\n"
            "  ]\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    journal = SelfDevelopmentJournal(
        path=tmp_path / "state.json",
        mutual_aid_state_path=mutual_aid_state,
    )
    journal.record_cycle(
        {
            "objective": "lead cycle",
            "external_review_count": 1,
            "local_actions": [],
            "human_unlocks": [],
            "lead_scout": {
                "active_lead": {
                    "url": "https://github.com/example/agent/issues/1",
                    "pain": "agent deployment quota failure",
                    "addressable_label": "Compute/auth unblock",
                }
            },
            "autonomous_development": {
                "skipped": False,
                "action": {
                    "action_id": "adev-lead",
                    "type": "lead_help_artifact",
                    "title": "Drafted a bounded help artifact for an agent lead",
                    "files": [],
                },
            },
        }
    )

    second = journal.record_cycle(
        {
            "objective": "lead cycle again",
            "external_review_count": 1,
            "local_actions": [],
            "human_unlocks": [],
            "lead_scout": {
                "active_lead": {
                    "url": "https://github.com/example/agent/issues/1",
                    "pain": "agent deployment quota failure",
                    "addressable_label": "Compute/auth unblock",
                }
            },
        }
    )

    assert "Package reusable truth pattern" in second["next_objective"]
    assert "Provider Fallback Ladder" in second["next_objective"]
    assert second["last_truth_pattern"]["repeat_count"] == 3


def test_self_development_journal_tracks_high_value_pattern_watch(tmp_path):
    journal = SelfDevelopmentJournal(
        path=tmp_path / "state.json",
        mutual_aid_state_path=tmp_path / "mutual_aid.json",
    )

    state = journal.record_cycle(
        {
            "objective": "productize repeated help",
            "external_review_count": 1,
            "local_actions": [],
            "human_unlocks": [],
            "lead_scout": {},
            "high_value_patterns": {
                "patterns": [
                    {
                        "pattern_id": "hvp-1",
                        "title": "Provider Fallback Ladder",
                        "pain_type": "compute_auth",
                        "occurrence_count": 3,
                        "avg_truth_score": 0.82,
                        "avg_reuse_value": 0.91,
                        "agent_offer": {
                            "reply_contract": "PLAN_ACCEPTED=true plus FACT_URL or ERROR",
                        },
                    }
                ]
            },
        }
    )

    assert "Productize high-value pattern" in state["next_objective"]
    assert state["last_high_value_pattern"]["title"] == "Provider Fallback Ladder"
    assert state["last_high_value_pattern"]["occurrence_count"] == 3
