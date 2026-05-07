from nomad_contract_conformance import build_contract_conformance_snapshot
from nomad_machine_product_surface import CORE_ENDPOINTS


def test_contract_conformance_ok_for_complete_surface():
    openapi_doc = {"paths": {path: {} for path in CORE_ENDPOINTS}}
    product = {
        "contract_stability": {"major_version": 1, "stable_endpoints": CORE_ENDPOINTS},
        "endpoint_presence": {"core_paths": CORE_ENDPOINTS},
        "entry_sequences": [{"id": "arriving_runtime"}, {"id": "idle_runtime"}, {"id": "proof_weighted_pledge"}],
    }
    out = build_contract_conformance_snapshot(
        base_url="https://nomad.example",
        machine_product_surface=product,
        openapi_document=openapi_doc,
    )
    assert out["schema"] == "nomad.machine_contract_conformance.v1"
    assert out["ok"] is True
    assert out["score"] == 1.0
    assert out["violations"] == []


def test_contract_conformance_flags_missing_paths():
    openapi_doc = {"paths": {"/health": {}, "/swarm/attach": {}}}
    product = {
        "contract_stability": {"major_version": 0, "stable_endpoints": ["/swarm/attach", "/machine-field/intent"]},
        "endpoint_presence": {"core_paths": ["/swarm/attach"]},
        "entry_sequences": [{"id": "arriving_runtime"}],
    }
    out = build_contract_conformance_snapshot(
        machine_product_surface=product,
        openapi_document=openapi_doc,
    )
    assert out["ok"] is False
    assert out["score"] < 1.0
    assert len(out["violations"]) >= 1

