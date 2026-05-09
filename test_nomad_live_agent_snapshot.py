import importlib.util
import json
from pathlib import Path
from unittest.mock import patch


def _load_snapshot_module():
    path = Path(__file__).resolve().parent / "public" / "downloads" / "nomad_live_agent_snapshot.py"
    spec = importlib.util.spec_from_file_location("nomad_live_agent_snapshot_dl", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_build_snapshot_merges_economics_and_funnel():
    mod = _load_snapshot_module()
    econ = {
        "ok": True,
        "economics_score": 0.5,
        "metrics": {"real_cashflow_24h_eur": -0.1},
        "go_no_go": {"go": False, "action": "BOOTSTRAP_RECOVERY_WAVE"},
        "network_phase": {"phase": "bootstrap_growth"},
        "agent_runtime": {"schema": "nomad.agent_runtime.v1", "next": []},
    }
    funnel = {
        "ok": True,
        "schema": "nomad.recruitment_funnel_report.v1",
        "connected_agents": 2,
        "marginal_utility_per_cost": {"global_marginal_utility_per_cost": 0.12, "rows": [{"source": "a"}]},
    }

    def fake_urlopen(url, timeout=0):
        u = str(url)
        payload = funnel if "recruitment-funnel" in u else econ

        class R:
            def read(self):
                return json.dumps(payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return R()

    with patch.object(mod, "urlopen", fake_urlopen):
        out = mod.build_snapshot(base_url="https://x.example", timeout=5.0)

    assert out["schema"] == "nomad.live_agent_snapshot.v1"
    assert out["economics"]["economics_score"] == 0.5
    assert out["recruitment_funnel"]["connected_agents"] == 2
    assert out["recruitment_funnel"]["global_marginal_utility_per_cost"] == 0.12
