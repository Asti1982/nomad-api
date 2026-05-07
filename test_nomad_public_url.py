from nomad_public_url import normalize_public_url, preferred_public_base_url


def test_normalize_public_url_canonicalizes_syndiode_apex_to_www():
    assert normalize_public_url("https://syndiode.com") == "https://www.syndiode.com"
    assert normalize_public_url("syndiode.com") == "https://www.syndiode.com"
    assert normalize_public_url("https://syndiode.com/nomad") == "https://www.syndiode.com/nomad"


def test_preferred_public_base_url_uses_canonical_syndiode_host(monkeypatch):
    monkeypatch.setenv("NOMAD_COLLABORATION_HOME_URL", "https://syndiode.com")
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://syndiode.com")
    monkeypatch.delenv("NOMAD_RENDER_DOMAIN", raising=False)

    assert preferred_public_base_url() == "https://www.syndiode.com"
