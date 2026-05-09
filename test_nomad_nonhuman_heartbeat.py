import importlib.util
import json
from pathlib import Path
from unittest.mock import patch


def _load_module():
    path = Path(__file__).resolve().parent / "public" / "downloads" / "nomad_nonhuman_heartbeat.py"
    spec = importlib.util.spec_from_file_location("nomad_nonhuman_heartbeat_dl", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_build_heartbeat_includes_nonhuman_cadence_and_actions():
    mod = _load_module()
    economics = {
        "ok": True,
        "economics_score": 0.4,
        "metrics": {"real_cashflow_24h_eur": -0.7, "diversity_index": 0.1},
        "network_phase": {"phase": "bootstrap_growth"},
    }
    funnel = {
        "ok": True,
        "connected_agents": 1,
        "known_agents": 1,
        "marginal_utility_per_cost": {"global_marginal_utility_per_cost": 0.0},
    }
    skills = {"ok": True, "skill_count": 0}

    def fake_urlopen(url, timeout=0):
        u = str(url)
        payload = economics
        if "recruitment-funnel-report" in u:
            payload = funnel
        elif "skill-library" in u:
            payload = skills

        class R:
            status = 200

            def read(self):
                return json.dumps(payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return R()

    with patch.object(mod, "urlopen", fake_urlopen):
        out = mod.build_heartbeat(base_url="https://x.example", timeout=5.0)

    assert out["schema"] == "nomad.nonhuman_heartbeat.v1"
    assert out["cadence"]["minutes"] == 37
    assert out["cadence"]["prime_interval"] is True
    assert isinstance(out["gap_vector"], list) and out["gap_vector"]
    assert isinstance(out["next_nonhuman_actions"], list) and out["next_nonhuman_actions"]
    assert out["machine_instruction"].startswith("execute_priority_order_actions")

