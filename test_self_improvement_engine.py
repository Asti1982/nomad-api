from nomad_autonomous_development import AutonomousDevelopmentLog
from self_improvement import HostedBrainRouter, SelfImprovementEngine
import requests


class FakeInfra:
    def best_stack(self, profile_id="ai_first"):
        return {
            "profile": {"id": profile_id, "label": "AI-First Nomad", "description": "test"},
            "overall_score": 9.2,
            "stack": [{"category": "compute", "name": "Ollama", "agent_satisfaction_score": 9.5, "tradeoff": "small"}],
        }

    def self_audit(self, profile_id="ai_first"):
        return {
            "profile": {"id": profile_id, "label": "AI-First Nomad", "description": "test"},
            "upgrades": [],
            "analysis": "Nomad is mostly aligned.",
        }

    def compute_assessment(self, profile_id="ai_first"):
        return {
            "mode": "compute_audit",
            "profile": {"id": profile_id, "label": "AI-First Nomad", "description": "test"},
            "probe": {
                "ollama": {"available": True, "api_reachable": True, "count": 2, "models": ["qwen2.5:0.5b-instruct"]},
                "hosted": {
                    "github_models": {"available": False},
                    "huggingface": {"available": True},
                    "cloudflare_workers_ai": {"available": False},
                    "modal": {"available": False},
                },
            },
            "brains": {
                "brain_count": 1,
                "primary": {"name": "Ollama"},
                "secondary": [],
            },
            "activation_request": {
                "candidate_name": "GitHub Models",
                "category": "compute",
                "short_ask": "Unlock GitHub Models",
                "ask": "Please unlock GitHub Models next.",
            },
            "analysis": "Nomad should add a second compute lane.",
        }

    def market_scan(self, focus="balanced", limit=4):
        return {
            "mode": "market_scan",
            "focus": focus,
            "competitors": [{"name": "ClawNet"}, {"name": "A2A Registry"}],
            "compute_opportunities": [{"name": "Cloudflare Workers AI"}],
            "copy_now": ["Keep a root agent catalog plus per-agent public cards."],
            "brain_context": {
                "top_competitors": ["ClawNet", "A2A Registry"],
                "top_compute": ["Cloudflare Workers AI"],
                "copy_now": ["Keep a root agent catalog plus per-agent public cards."],
            },
        }

    def best_activation_request(self, profile_id="ai_first", excluded_ids=None):
        return {
            "request": {
                "candidate_name": "GitHub Models",
                "category": "compute",
                "short_ask": "Unlock GitHub Models",
            }
        }

    def _make_activation_request_concrete(self, payload):
        return dict(payload)


class FakeBrainRouter:
    def review(self, objective, context):
        return [
            {
                "name": "Ollama",
                "model": "qwen2.5:0.5b-instruct",
                "ok": True,
                "content": (
                    "Diagnosis: compute fallback weak\n"
                    "Action1: scout public quota pain\n"
                    "Action2: keep outreach bounded\n"
                    "Query: \"AI agent\" \"quota\" \"budget\""
                ),
            }
        ]


class FakeLeadDiscovery:
    def __init__(self):
        self.calls = []

    def current_focus(self, focus=""):
        return "compute_auth"

    def source_plan(self, focus=""):
        return {
            "service_type": "compute_auth",
            "public_surfaces": [{"name": "Quota search", "url": "https://github.com/search?q=quota&type=issues"}],
            "outreach_queries": ['"agent-card.json" "quota" "https://"'],
        }

    def default_queries(self, focus=""):
        return ['"AI agent" "rate limit" is:issue is:open']

    def scout_public_leads(self, query="", limit=5, focus=""):
        self.calls.append((query, limit, focus))
        return {
            "mode": "lead_discovery",
            "query": query,
            "leads": [
                {
                    "title": "Agent hits quota in production",
                    "url": "https://github.com/example/agent/issues/7",
                    "pain": "quota, compute",
                    "recommended_service_type": "compute_auth",
                    "addressable_label": "Compute/auth unblock",
                    "addressable_now": True,
                    "monetizable_now": True,
                    "first_help_action": "Draft a compute fallback and quota isolation plan.",
                }
            ][:limit],
            "errors": [],
        }

    def draft_first_help_action(self, lead, approval="draft_only"):
        return {
            "mode": "lead_help_draft",
            "draft_only": True,
            "draft": f"Draft help for {lead['url']}",
        }


class FakeJournal:
    def load(self):
        return {"next_objective": "Next objective"}

    def record_cycle(self, result):
        return {
            "cycle_count": 1,
            "last_cycle_at": "2026-04-18T00:00:00Z",
            "current_objective": result.get("objective", ""),
            "next_objective": "Work the quota lead",
            "open_human_unlock": None,
            "self_development_unlocks": [],
        }


class FakeAddons:
    def __init__(self):
        self.objectives = []
        self.contexts = []

    def run_quantum_self_improvement(self, objective="", context=None):
        self.objectives.append(objective)
        self.contexts.append(context or {})
        return {
            "mode": "nomad_quantum_tokens",
            "ok": True,
            "selected_strategy": {
                "qtoken_id": "qtok-test",
                "strategy_id": "measurement_critic_gate",
                "title": "Measurement critic gate",
            },
            "tokens": [
                {
                    "qtoken_id": "qtok-test",
                    "title": "Measurement critic gate",
                    "score": 0.9,
                }
            ],
            "improvements": [
                {
                    "qtoken_id": "qtok-test",
                    "title": "Measurement critic gate",
                    "agent_use": "Measure candidate fixes before applying.",
                    "verification": "Regression check exists.",
                }
            ],
            "brain_context": {
                "selected_strategy": "measurement_critic_gate",
                "selected_instruction": "Measure candidate fixes before applying.",
            },
            "human_unlocks": [],
        }


class FakeMutualAid:
    def __init__(self, patterns=None):
        self.patterns = patterns or []
        self.calls = []

    def list_high_value_patterns(self, limit=3, min_repeat_count=2):
        self.calls.append((limit, min_repeat_count))
        return {
            "mode": "nomad_high_value_patterns",
            "ok": True,
            "pattern_count": len(self.patterns),
            "patterns": self.patterns[:limit],
        }


def test_self_improvement_runs_public_lead_scout_and_compute_watch(tmp_path):
    lead_discovery = FakeLeadDiscovery()
    engine = SelfImprovementEngine(
        infra=FakeInfra(),
        brain_router=FakeBrainRouter(),
        journal=FakeJournal(),
        lead_discovery=lead_discovery,
        addons=FakeAddons(),
        lead_plan_path=tmp_path / "lead-plan.json",
        autonomous_development=AutonomousDevelopmentLog(tmp_path / "autonomous.json"),
    )

    result = engine.run_cycle(objective="Find paid compute pain and improve Nomad.", profile_id="ai_first")

    assert result["mode"] == "self_improvement_cycle"
    assert result["compute_watch"]["needs_attention"] is True
    assert result["compute_watch"]["activation_request"]["candidate_name"] == "GitHub Models"
    assert result["lead_scout"]["search_queries"][0] == '"AI agent" "quota" "budget"'
    assert result["lead_scout"]["outreach_queries"] == ['"agent-card.json" "quota" "https://"']
    assert result["lead_scout"]["leads"][0]["url"] == "https://github.com/example/agent/issues/7"
    assert result["lead_scout"]["compute_leads"][0]["recommended_service_type"] == "compute_auth"
    assert result["lead_scout"]["addressable_count"] == 1
    assert result["lead_scout"]["monetizable_count"] == 1
    assert result["lead_scout"]["addressable_leads"][0]["addressable_label"] == "Compute/auth unblock"
    assert result["lead_scout"]["active_lead"]["url"] == "https://github.com/example/agent/issues/7"
    assert result["lead_scout"]["help_draft"]["draft"] == "Draft help for https://github.com/example/agent/issues/7"
    assert result["lead_scout"]["help_draft_saved"] is True
    assert result["lead_scout"]["help_draft_path"] == str(tmp_path / "lead-plan.json")
    assert result["agent_pain_solver"]["solution"]["pain_type"] == "compute_auth"
    assert result["autonomous_development"]["skipped"] is False
    assert result["autonomous_development"]["action"]["type"] == "lead_help_artifact"
    assert result["agent_pain_solver"]["solution"]["guardrail"]["id"] == "compute_fallback_ladder"
    assert any(action["type"] == "agent_pain_solution" for action in result["local_actions"])
    assert result["market_scan"]["compute_opportunities"][0]["name"] == "Cloudflare Workers AI"
    assert result["compute_watch"]["external_free_lanes"][0] == "Cloudflare Workers AI"
    assert "https://github.com/example/agent/issues/7" in (tmp_path / "lead-plan.json").read_text(encoding="utf-8")
    assert lead_discovery.calls[0][0] == '"AI agent" "quota" "budget"'
    assert lead_discovery.calls[0][2] == "compute_auth"


def test_self_improvement_includes_quantum_tokens_in_cycle_context(tmp_path):
    addons = FakeAddons()
    engine = SelfImprovementEngine(
        infra=FakeInfra(),
        brain_router=FakeBrainRouter(),
        journal=FakeJournal(),
        lead_discovery=FakeLeadDiscovery(),
        addons=addons,
        lead_plan_path=tmp_path / "lead-plan.json",
        autonomous_development=AutonomousDevelopmentLog(tmp_path / "autonomous.json"),
    )

    result = engine.run_cycle(
        objective="Use qtokens to improve guardrail selection.",
        profile_id="ai_first",
    )

    assert result["quantum_tokens"]["selected_strategy"]["strategy_id"] == "measurement_critic_gate"
    assert any(action["type"] == "quantum_token_self_improvement" for action in result["local_actions"])
    assert addons.contexts[0]["profile"]["id"] == "ai_first"
    assert "Quantum tokens selected" in result["analysis"]


def test_self_improvement_prefers_focused_discovered_lead_when_objective_is_generic(tmp_path):
    lead_discovery = FakeLeadDiscovery()
    engine = SelfImprovementEngine(
        infra=FakeInfra(),
        brain_router=FakeBrainRouter(),
        journal=FakeJournal(),
        lead_discovery=lead_discovery,
        addons=FakeAddons(),
        lead_plan_path=tmp_path / "lead-plan.json",
        autonomous_development=AutonomousDevelopmentLog(tmp_path / "autonomous.json"),
    )

    result = engine.run_cycle(
        objective="Work the next useful lead for ai_first",
        profile_id="ai_first",
    )

    assert result["lead_scout"]["active_lead"]["url"] == "https://github.com/example/agent/issues/7"


def test_self_improvement_surfaces_high_value_patterns_and_builds_artifacts(tmp_path):
    mutual_aid = FakeMutualAid(
        patterns=[
            {
                "pattern_id": "hvp-1",
                "title": "Provider Fallback Ladder",
                "pain_type": "compute_auth",
                "occurrence_count": 3,
                "avg_truth_score": 0.82,
                "avg_reuse_value": 0.91,
                "productization": {
                    "pack_ready": True,
                    "sku": "nomad.mutual_aid.compute_auth_micro_pack",
                    "name": "Mutual-Aid Compute Auth Micro-Pack",
                },
                "agent_offer": {
                    "starter_diagnosis": "Nomad has seen this pattern repeatedly.",
                    "reply_contract": "PLAN_ACCEPTED=true plus FACT_URL or ERROR",
                    "smallest_paid_unblock": {"amount_native": 0.03},
                },
                "self_evolution": {
                    "next_action": "differentiate_paid_pack_and_add_regression_check",
                    "self_apply_step": "Use the fallback ladder before retrying.",
                },
                "source_agents": ["quota-bot-1", "quota-bot-2"],
            }
        ]
    )
    engine = SelfImprovementEngine(
        infra=FakeInfra(),
        brain_router=FakeBrainRouter(),
        journal=FakeJournal(),
        lead_discovery=FakeLeadDiscovery(),
        addons=FakeAddons(),
        lead_plan_path=tmp_path / "lead-plan.json",
        autonomous_development=AutonomousDevelopmentLog(
            tmp_path / "autonomous.json",
            artifact_dir=tmp_path / "artifacts",
        ),
        mutual_aid=mutual_aid,
    )

    result = engine.run_cycle(objective="Package the best repeated agent pain pattern.", profile_id="ai_first")

    assert result["high_value_patterns"]["pattern_count"] == 1
    assert result["high_value_patterns"]["patterns"][0]["title"] == "Provider Fallback Ladder"
    assert any(action["type"] == "high_value_pattern_productization" for action in result["local_actions"])
    assert result["autonomous_development"]["action"]["type"] == "high_value_pattern_artifact"
    assert any(path.endswith(".service.json") for path in result["autonomous_development"]["action"]["files"])
    assert mutual_aid.calls[0] == (3, 2)


def test_hosted_brain_router_auto_uses_available_hosted_lane(monkeypatch):
    monkeypatch.delenv("NOMAD_HOSTED_BRAIN_MODE", raising=False)
    monkeypatch.delenv("NOMAD_ALLOW_HOSTED_BRAINS", raising=False)
    monkeypatch.setenv("NOMAD_OLLAMA_AUTO_SELECT_SELF_IMPROVE_MODEL", "false")
    monkeypatch.setenv("HF_TOKEN", "hf-test-token")
    router = HostedBrainRouter()
    router._ollama_review = lambda messages: {
        "provider": "ollama",
        "name": "Ollama",
        "ok": True,
        "useful": False,
        "content": "I can't help with this request.",
    }
    router._huggingface_review = lambda messages: {
        "provider": "huggingface",
        "name": "Hugging Face Inference Providers",
        "ok": True,
        "useful": True,
        "content": "Diagnosis: fallback ready\nAction1: use hosted lane\nAction2: keep lead scout bounded\nQuery: \"agent-card.json\" \"quota\" \"https://\"",
    }
    router._github_review = lambda messages: {
        "provider": "github_models",
        "name": "GitHub Models",
        "ok": False,
        "useful": False,
        "content": "",
    }

    results = router.review(
        objective="Find compute pain and improve Nomad.",
        context={
            "resources": {
                "brain_count": 2,
                "github_models": {"available": False, "reachable": True},
                "huggingface": {"available": True, "reachable": True},
            }
        },
    )

    assert [item["provider"] for item in results] == ["ollama", "huggingface"]


def test_hosted_brain_router_prefers_fast_available_ollama_model(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "")
    monkeypatch.setenv("NOMAD_OLLAMA_SELF_IMPROVE_MODEL", "")
    monkeypatch.setenv("NOMAD_OLLAMA_AUTO_SELECT_SELF_IMPROVE_MODEL", "true")

    class TagsResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "models": [
                    {"name": "llama3.2:1b"},
                    {"name": "qwen2.5:0.5b-instruct"},
                ]
            }

    monkeypatch.setattr("self_improvement.requests.get", lambda *args, **kwargs: TagsResponse())

    router = HostedBrainRouter()

    assert router.ollama_model == "qwen2.5:0.5b-instruct"
    assert router.ollama_model_source == "auto_fast_available"
    assert router.ollama_timeout_seconds <= 15


def test_hosted_brain_router_skips_unreachable_ollama_when_hosted_available(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2:1b")
    monkeypatch.setenv("NOMAD_OLLAMA_AUTO_SELECT_SELF_IMPROVE_MODEL", "false")
    monkeypatch.setenv("HF_TOKEN", "hf-test-token")
    monkeypatch.delenv("NOMAD_HOSTED_BRAIN_MODE", raising=False)
    monkeypatch.delenv("NOMAD_ALLOW_HOSTED_BRAINS", raising=False)
    router = HostedBrainRouter()
    router._ollama_review = lambda messages: (_ for _ in ()).throw(AssertionError("Ollama should be skipped"))
    router._huggingface_review = lambda messages: {
        "provider": "huggingface",
        "name": "Hugging Face Inference Providers",
        "ok": True,
        "useful": True,
        "content": "Diagnosis: fallback ready\nAction1: use hosted lane\nAction2: keep lead scout bounded\nQuery: \"agent-card.json\" \"quota\" \"https://\"",
    }

    results = router.review(
        objective="Find compute pain and improve Nomad.",
        context={
            "resources": {
                "ollama": {"api_reachable": False, "model_count": 0},
                "huggingface": {"available": True, "reachable": True},
            }
        },
    )

    assert [item["provider"] for item in results] == ["huggingface"]


def test_ollama_review_timeout_returns_retryable_fallback_advice(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2:1b")
    monkeypatch.setenv("NOMAD_OLLAMA_AUTO_SELECT_SELF_IMPROVE_MODEL", "false")
    monkeypatch.setenv("NOMAD_OLLAMA_TIMEOUT_SECONDS", "3")
    router = HostedBrainRouter()

    def timeout_post(*args, **kwargs):
        raise requests.Timeout("read timed out")

    monkeypatch.setattr("self_improvement.requests.post", timeout_post)

    result = router._ollama_review([{"role": "user", "content": "test"}])

    assert result["ok"] is False
    assert result["retryable"] is True
    assert result["timeout_seconds"] == 3
    assert "hosted fallback" in result["fallback_advice"].lower()


def test_self_improvement_ignores_question_style_brain_query_hint(tmp_path):
    lead_discovery = FakeLeadDiscovery()

    class QuestionBrainRouter(FakeBrainRouter):
        def review(self, objective, context):
            return [
                {
                    "name": "Hugging Face Inference Providers",
                    "model": "meta-llama",
                    "ok": True,
                    "useful": True,
                    "content": (
                        "Diagnosis: compute fallback weak\n"
                        "Action1: keep scouting bounded\n"
                        "Action2: use hosted lane\n"
                        "Query: What are the top 3 compute/auth pain points?"
                    ),
                }
            ]

    engine = SelfImprovementEngine(
        infra=FakeInfra(),
        brain_router=QuestionBrainRouter(),
        journal=FakeJournal(),
        lead_discovery=lead_discovery,
        addons=FakeAddons(),
        lead_plan_path=tmp_path / "lead-plan.json",
        autonomous_development=AutonomousDevelopmentLog(tmp_path / "autonomous.json"),
    )

    result = engine.run_cycle(objective="Find compute pain and improve Nomad.", profile_id="ai_first")

    assert result["lead_scout"]["search_queries"][0] == '"AI agent" "rate limit" is:issue is:open'
