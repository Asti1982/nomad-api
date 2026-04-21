import json

from nomad_mutual_aid import NomadMutualAidKernel


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

    loaded = kernel.load_learned_modules()
    assert loaded
    assert loaded[0]["source"] == "mutual_aid"
    assert loaded[0]["pain_type"] == "compute_auth"

    state = json.loads((tmp_path / "mutual-aid-state.json").read_text(encoding="utf-8"))
    assert state["mutual_aid_score"] == 1
    assert state["helped_agents"]["quota-bot"]["help_count"] == 1


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
