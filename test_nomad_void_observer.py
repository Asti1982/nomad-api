from nomad_void_observer import _canonical_probe_lines, _fingerprint, run_void_observer_pulse


def test_canonical_lines_sort_permutation_invariant():
    a = _canonical_probe_lines(
        [
            {"url": "https://x.test/nomad/health", "status": 200, "ok": True},
            {"url": "https://x.test/nomad/swarm", "status": 404, "ok": False},
        ]
    )
    b = _canonical_probe_lines(
        [
            {"url": "https://x.test/nomad/swarm", "status": 404, "ok": False},
            {"url": "https://x.test/nomad/health", "status": 200, "ok": True},
        ]
    )
    assert a == b
    assert _fingerprint(a) == _fingerprint(b)


def test_void_observer_pulse_uses_swarm_helper(monkeypatch):
    def fake_pass(**kwargs):
        return {
            "schema": "nomad.swarm_helper_pass.v1",
            "public_base_url": "https://stub/nomad",
            "probe_ok_count": 2,
            "probes": [
                {"url": "https://stub/nomad/a", "status": 200, "ok": True},
                {"url": "https://stub/nomad/b", "status": 500, "ok": False},
            ],
        }

    monkeypatch.setattr("nomad_void_observer.run_swarm_helper_pass", fake_pass)
    monkeypatch.delenv("NOMAD_VOID_OBSERVER_BASELINE_SHA256", raising=False)
    out = run_void_observer_pulse(base_url="https://stub/nomad", timeout=1.0)
    assert out["mode"] == "nomad_void_observer_pulse"
    assert out["schema"] == "nomad.void_observer_pulse.v1"
    assert len(out["edge_coherence_sha256"]) == 64
    assert out["baseline_drift"] is False
    assert out["ordinal_status_series"] == [200, 500]
