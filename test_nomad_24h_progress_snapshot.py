import importlib.util
import json
from pathlib import Path
from unittest.mock import patch


def _load_module():
    path = Path(__file__).resolve().parent / "public" / "downloads" / "nomad_24h_progress_snapshot.py"
    spec = importlib.util.spec_from_file_location("nomad_24h_progress_snapshot_test_mod", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_24h_progress_snapshot_merges_core_surfaces():
    mod = _load_module()
    economics = {"ok": True, "economics_score": 0.72, "metrics": {"real_cashflow_24h_eur": 1.7}, "go_no_go": {"go": True}}
    funnel = {"ok": True, "connected_agents": 4, "marginal_utility_per_cost": {"global_marginal_utility_per_cost": 1.5}}
    weekly = {"ok": True, "selection": {"promote": [1], "freeze": [1, 2], "extinguish": []}}
    gate = {"ok": True, "gate_open": True, "failed_checks": [], "spawn_plan": {"spawn_count": 2}}

    def fake_urlopen(req, timeout=0):
        u = str(getattr(req, "full_url", req))
        payload = economics
        if "funnel" in u:
            payload = funnel
        elif "weekly-selection" in u:
            payload = weekly
        elif "spawner-gate" in u:
            payload = gate

        class R:
            def read(self):
                return json.dumps(payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return R()

    with patch.object(mod, "urlopen", fake_urlopen):
        out = mod.build_snapshot(base_url="https://nomad.example", timeout=5.0)

    assert out["schema"] == "nomad.progress_24h_snapshot.v1"
    assert out["economics"]["real_cashflow_24h_eur"] == 1.7
    assert out["funnel"]["global_marginal_utility_per_cost"] == 1.5
    assert out["weekly_selection"]["promote"] == 1
    assert out["spawner_gate"]["gate_open"] is True

