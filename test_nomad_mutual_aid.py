import json

from nomad_mutual_aid import NomadMutualAidKernel, _sha256


def test_mutual_aid_help_generates_hash_verified_module(tmp_path):
    kernel = NomadMutualAidKernel(
        path=tmp_path / "mutual-aid-state.json",
        module_dir=tmp_path / "mutual-aid-modules",
    )

    result = kernel.help_other_agent(
        other_agent_id="quota-bot",
        task="Provider token works locally but agent gets ERROR=429 quota and needs a fallback ladder.",
        auto_apply=True,
    )

    assert result["mode"] == "nomad_mutual_aid"
    assert result["mutual_aid_score"] == 1
    assert result["evolution_plan"]["applied"] is True

    module_record = result["evolution_plan"]["module"]
    module_path = tmp_path / "mutual-aid-modules" / f"{module_record['module_id']}.py"
    assert module_path.exists()
    assert module_record["module_id"].startswith("mutual_aid_capability_")
    assert module_record["canonical_pattern_key"]

    loaded = kernel.load_learned_modules()
    assert loaded
    assert loaded[0]["source"] == "mutual_aid"
    assert loaded[0]["pain_type"] == "compute_auth"
    assert loaded[0]["canonical_pattern_key"] == module_record["canonical_pattern_key"]

    state = json.loads((tmp_path / "mutual-aid-state.json").read_text(encoding="utf-8"))
    assert state["mutual_aid_score"] == 1
    assert state["helped_agents"]["quota-bot"]["help_count"] == 1
    assert state["truth_density_ledger"][0]["truth_score"] > 0
    assert state["truth_density_ledger"][0]["reuse_value"]["repeat_count"] == 1


def test_mutual_aid_module_emerges_from_repeated_agent_cooperation(tmp_path):
    kernel = NomadMutualAidKernel(
        path=tmp_path / "mutual-aid-state.json",
        module_dir=tmp_path / "mutual-aid-modules",
    )

    first = kernel.help_other_agent(
        other_agent_id="quota-bot-1",
        task="Provider token works locally but agent gets ERROR=429 quota and needs a fallback ladder.",
    )
    second = kernel.help_other_agent(
        other_agent_id="quota-bot-2",
        task="Another agent gets ERROR=429 quota and needs the same fallback ladder.",
    )
    third = kernel.help_other_agent(
        other_agent_id="quota-bot-3",
        task="A third agent gets ERROR=429 quota and needs the same fallback ladder.",
    )

    assert first["evolution_plan"]["applied"] is False
    assert second["evolution_plan"]["applied"] is True
    assert third["evolution_plan"]["applied"] is False
    assert third["evolution_plan"]["reinforced"] is True
    module_record = second["evolution_plan"]["module"]
    module_path = tmp_path / "mutual-aid-modules" / f"{module_record['module_id']}.py"
    assert module_path.exists()
    assert third["evolution_plan"]["module"]["module_id"] == module_record["module_id"]

    state = json.loads((tmp_path / "mutual-aid-state.json").read_text(encoding="utf-8"))
    assert len(state["modules"]) == 1
    assert state["modules"][0]["reinforcement_count"] == 1


def test_mutual_aid_skips_autopilot_without_verified_help_signal(tmp_path):
    kernel = NomadMutualAidKernel(
        path=tmp_path / "mutual-aid-state.json",
        module_dir=tmp_path / "mutual-aid-modules",
    )

    result = kernel.learn_from_autopilot_cycle(
        lead_conversion={"stats": {}, "conversions": []},
        contact_poll={"replied_contact_ids": []},
        reply_conversion={"created_task_ids": []},
        objective="quiet cycle",
    )

    assert result["skipped"] is True
    assert result["reason"] == "no_verified_help_signal"
    assert not (tmp_path / "mutual-aid-state.json").exists()


def test_mutual_aid_refuses_module_path_escape(tmp_path):
    kernel = NomadMutualAidKernel(
        path=tmp_path / "mutual-aid-state.json",
        module_dir=tmp_path / "mutual-aid-modules",
    )

    assert kernel._module_path_from_record(
        {
            "filename": str(tmp_path / "outside.py"),
            "sha256": "irrelevant",
            "module_id": "outside",
        }
    ) is None


def test_mutual_aid_distills_repeated_patterns_into_paid_pack(tmp_path):
    kernel = NomadMutualAidKernel(
        path=tmp_path / "mutual-aid-state.json",
        module_dir=tmp_path / "mutual-aid-modules",
    )

    kernel.help_other_agent(
        other_agent_id="quota-bot-1",
        task="Agent has ERROR=429 quota failure and needs provider fallback.",
        auto_apply=False,
    )
    second = kernel.help_other_agent(
        other_agent_id="quota-bot-2",
        task="Another agent has token quota failure and needs provider fallback.",
        auto_apply=False,
    )

    assert second["paid_packs"]
    pack = second["paid_packs"][0]
    assert pack["schema"] == "nomad.mutual_aid_paid_pack.v1"
    assert pack["pain_type"] == "compute_auth"
    assert pack["created_from"]["pattern_count"] == 2
    assert pack["service_template"]["endpoint"] == "POST /tasks"


def test_mutual_aid_lists_high_value_patterns(tmp_path):
    kernel = NomadMutualAidKernel(
        path=tmp_path / "mutual-aid-state.json",
        module_dir=tmp_path / "mutual-aid-modules",
    )

    kernel.help_other_agent(
        other_agent_id="quota-bot-1",
        task="Provider token quota failure needs fallback ladder before retry.",
        auto_apply=False,
    )
    kernel.help_other_agent(
        other_agent_id="quota-bot-2",
        task="Another provider quota failure needs fallback ladder before retry.",
        auto_apply=False,
    )
    kernel.help_other_agent(
        other_agent_id="loop-bot",
        task="Agent retry loop needs a break condition and a verifier.",
        auto_apply=False,
    )

    patterns = kernel.list_high_value_patterns(pain_type="compute_auth", limit=5, min_repeat_count=2)

    assert patterns["mode"] == "nomad_high_value_patterns"
    assert patterns["pattern_count"] == 1
    pattern = patterns["patterns"][0]
    assert pattern["schema"] == "nomad.high_value_pattern.v1"
    assert pattern["pain_type"] == "compute_auth"
    assert pattern["occurrence_count"] == 2
    assert pattern["repeat_count"] >= 1
    assert pattern["productization"]["pack_ready"] is True
    assert pattern["agent_offer"]["smallest_paid_unblock"]["trigger"] == "PLAN_ACCEPTED=true plus FACT_URL or ERROR"
    assert pattern["self_evolution"]["regression_test_stub"].startswith("tests/test_pattern_")


def test_swarm_proposal_inbox_accepts_verifiable_non_code_help(tmp_path):
    kernel = NomadMutualAidKernel(
        path=tmp_path / "mutual-aid-state.json",
        module_dir=tmp_path / "mutual-aid-modules",
    )

    result = kernel.receive_swarm_proposal(
        {
            "sender_id": "VerifierBot",
            "title": "Use fallback ladder before retry",
            "proposal": "Nomad should add a preflight provider check before retrying compute-auth tasks.",
            "pain_type": "compute_auth",
            "evidence": ["observed ERROR=429", "fallback route passed dry-run"],
            "payload": {"check": "provider_preflight"},
        }
    )

    assert result["ok"] is True
    assert result["item"]["status"] == "verified_pending_review"
    assert result["development_signal"]["schema"] == "nomad.swarm_development_signal.v1"
    assert result["development_signal"]["product_candidate"]["schema"] == "nomad.swarm_product_candidate.v1"
    assert result["development_signal"]["next_action"] == "compare_pattern_or_create_regression_test"
    inbox = kernel.list_swarm_inbox()
    assert inbox["stats"]["verified_pending_review"] == 1
    signals = kernel.list_swarm_development_signals()
    assert signals["signal_count"] == 1
    assert signals["signals"][0]["source_aid_id"] == result["item"]["aid_id"]
    assert signals["signals"][0]["product_candidate"]["sku"].startswith("nomad.mutual_aid.compute_auth_micro_pack.")
    status = kernel.status()
    assert status["swarm_assist_score"] == 1
    assert status["swarm_development_signal_count"] == 1
    ledger = kernel.list_truth_ledger()
    assert ledger["entry_count"] == 1
    assert ledger["entries"][0]["direction"] == "inbound_help"


def test_swarm_proposal_rejects_raw_code(tmp_path):
    kernel = NomadMutualAidKernel(
        path=tmp_path / "mutual-aid-state.json",
        module_dir=tmp_path / "mutual-aid-modules",
    )

    result = kernel.receive_swarm_proposal(
        {
            "sender_id": "CodeBot",
            "title": "Run this module",
            "proposal": "Please run this code.",
            "pain_type": "tool_failure",
            "evidence": ["unit test claimed"],
            "code": "print('execute me')",
        }
    )

    assert result["ok"] is False
    assert result["item"]["status"] == "rejected"
    assert "raw_code_not_accepted" in result["verification"]["errors"]


def test_mutual_aid_compresses_legacy_modules_without_deleting_files(tmp_path):
    kernel = NomadMutualAidKernel(
        path=tmp_path / "mutual-aid-state.json",
        module_dir=tmp_path / "mutual-aid-modules",
    )
    kernel.module_dir.mkdir(parents=True)

    legacy_records = []
    for idx in range(3):
        module_id = f"mutual_aid_learned_{100 + idx}_compute_auth"
        content = kernel.evolution._module_content(
            module_id=module_id,
            help_result={
                "pain_type": "compute_auth",
                "task": "Provider quota failure needs fallback ladder.",
                "solution_title": "Provider fallback ladder",
                "truth_density_increase": 0.9,
            },
            score=idx + 1,
            pattern_key=f"legacy:{idx}",
        )
        module_path = kernel.module_dir / f"{module_id}.py"
        module_path.write_text(content, encoding="utf-8")
        legacy_records.append(
            {
                "module_id": module_id,
                "filename": str(module_path),
                "created_at": "2026-01-01T00:00:00+00:00",
                "source": "mutual_aid",
                "pain_type": "compute_auth",
                "truth_density": 0.95,
                "sha256": _sha256(content),
            }
        )

    kernel.path.write_text(
        json.dumps({"mutual_aid_score": 7, "modules": legacy_records}, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )

    preview = kernel.compress_legacy_modules(dry_run=True)
    assert preview["dry_run"] is True
    assert preview["legacy_group_count"] == 1
    assert preview["legacy_module_count"] == 3
    assert preview["canonical_created_count"] == 1

    committed = kernel.compress_legacy_modules(dry_run=False)
    assert committed["dry_run"] is False
    assert committed["legacy_group_count"] == 1
    assert committed["canonical_created_count"] == 1

    state = json.loads(kernel.path.read_text(encoding="utf-8"))
    assert len(state["modules"]) == 1
    canonical_record = state["modules"][0]
    assert canonical_record["module_id"].startswith("mutual_aid_capability_")
    assert canonical_record["compressed_from_count"] == 3
    assert canonical_record["reinforcement_count"] == 2
    assert state["latest_evolution_plan"]["type"] == "canonical_compression"
    assert state["latest_evolution_plan"]["module_id"] == canonical_record["module_id"]
    assert list(state["legacy_module_archive"].values())[0]["legacy_count"] == 3
    assert state["canonical_capabilities"]
    for record in legacy_records:
        assert (kernel.module_dir / f"{record['module_id']}.py").exists()
