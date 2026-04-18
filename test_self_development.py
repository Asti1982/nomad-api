from self_development import SelfDevelopmentJournal


def test_self_development_journal_records_cycle_and_next_objective(tmp_path):
    journal = SelfDevelopmentJournal(path=tmp_path / "state.json")
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
    }
    state = journal.record_cycle(result)
    assert state["cycle_count"] == 1
    assert state["cycles"][0]["objective"] == "initial objective"
    assert "Keep one small next action" in state["next_objective"]
    assert state["self_development_unlocks"][0]["candidate_id"] == "approve-next-self-dev-step"


def test_self_development_journal_prefers_active_lead(tmp_path):
    journal = SelfDevelopmentJournal(path=tmp_path / "state.json")
    result = {
        "objective": "lead cycle",
        "external_review_count": 1,
        "local_actions": [],
        "human_unlocks": [],
        "lead_scout": {
            "active_lead": {
                "url": "https://github.com/example/agent/issues/1",
                "pain": "agent deployment quota failure",
            }
        },
    }
    state = journal.record_cycle(result)
    assert "https://github.com/example/agent/issues/1" in state["next_objective"]
    assert "agent deployment quota failure" in state["next_objective"]
    unlock = state["self_development_unlocks"][0]
    assert unlock["candidate_id"] == "approve-active-lead-help"
    assert "APPROVE_LEAD_HELP" in unlock["human_deliverable"]


def test_self_development_journal_names_human_unlock_for_abstract_lead_discovery(tmp_path):
    journal = SelfDevelopmentJournal(path=tmp_path / "state.json")
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
