import json
from pathlib import Path

from nomad_lead_product_blind_spots import run_lead_product_blind_spot_pass


def _write(p: Path, data: dict) -> None:
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_lead_product_blind_spots_human_host_and_collisions(tmp_path):
    conv = tmp_path / "conv.json"
    prod = tmp_path / "prod.json"
    st = tmp_path / "state.json"
    old = "2020-01-01T00:00:00+00:00"
    _write(
        conv,
        {
            "conversions": {
                "a": {
                    "conversion_id": "a",
                    "created_at": old,
                    "status": "private_draft_needs_approval",
                    "lead": {
                        "title": "Same Title",
                        "url": "https://github.com/x/y",
                        "service_type": "compute_auth",
                    },
                    "route": {},
                    "free_value": {"value_pack": {}},
                },
                "b": {
                    "conversion_id": "b",
                    "created_at": old,
                    "status": "ready",
                    "lead": {
                        "title": "Same Title",
                        "url": "https://gitlab.com/z",
                        "service_type": "compute_auth",
                    },
                    "route": {},
                    "free_value": {"value_pack": {}},
                },
            }
        },
    )
    _write(prod, {"products": {}})
    gates = [{"human_gate": "needs_wallet", "can_execute_without_human": False}] * 4
    _write(st, {"worked_item_ids": [], "work_log": gates})

    out = run_lead_product_blind_spot_pass(
        conversion_path=conv,
        product_path=prod,
        state_path=st,
        stale_days=10,
        append_log=False,
    )
    assert out["schema"] == "nomad.lead_product_blind_spots_pass.v1"
    assert len(out["human_facing_lead_hits"]) >= 1
    assert len(out["duplicate_title_collisions"]) >= 1
    assert len(out["stale_unproductized_conversions"]) >= 1
    assert out["recurring_human_gates"]


def test_append_lead_log(tmp_path):
    conv = tmp_path / "c.json"
    prod = tmp_path / "p.json"
    st = tmp_path / "s.json"
    _write(conv, {"conversions": {}})
    _write(prod, {"products": {}})
    _write(st, {"worked_item_ids": [], "work_log": []})
    logf = tmp_path / "lc.jsonl"
    out = run_lead_product_blind_spot_pass(
        conversion_path=conv,
        product_path=prod,
        state_path=st,
        append_log=True,
        log_path=str(logf),
    )
    assert json.loads(logf.read_text(encoding="utf-8").strip())["schema"] == "nomad.lead_product_blind_spots_pass.v1"
