from nomad_referral_offers import build_referral_offer_surface


def test_referral_offer_surface_is_truthful_and_non_revenue():
    out = build_referral_offer_surface(base_url="https://nomad.example")
    offer = out["offers"][0]

    assert out["schema"] == "nomad.referral_offer_surface.v1"
    assert out["well_known_url"] == "https://nomad.example/.well-known/nomad-referral-offers.json"
    assert offer["provider"] == "Cursor"
    assert offer["referral_url"] == "https://cursor.com/referral?code=U7OPZAP4BZWH"
    assert offer["nomad_benefit"]["max_credit_per_billing_cycle_usd"] == 250
    assert offer["accounting_rule"]["recognized_revenue_usd"] == 0.0
    assert "link_share" in offer["accounting_rule"]["do_not_count"]
    assert "always_disclose_referrer_benefit" in offer["anti_spam_policy"]
    assert out["revenue_guard"]["recognized_revenue_usd_total"] == 0.0


def test_referral_offer_can_be_overridden_by_env(monkeypatch):
    monkeypatch.setenv("NOMAD_CURSOR_REFERRAL_URL", "https://cursor.com/referral?code=TEST")

    out = build_referral_offer_surface()

    assert out["offers"][0]["referral_url"] == "https://cursor.com/referral?code=TEST"
    assert out["copy_variants"][0]["url"] == "https://cursor.com/referral?code=TEST"
