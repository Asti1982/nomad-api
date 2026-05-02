"""Human-shaped Telegram digests only. Machine truth lives in HTTP/JSON for agents."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, Dict


def human_telegram_signals_enabled() -> bool:
    return (os.getenv("TELEGRAM_HUMAN_SIGNALS", "true").strip().lower() in {"1", "true", "yes", "on"})


def _is_actionable_quantum_unlock(unlock: Dict[str, Any]) -> bool:
    """Mirror telegram_bot logic so human digests match operational truth (no nag on local qtokens)."""
    if not isinstance(unlock, dict) or not unlock:
        return False
    provider = str(unlock.get("provider") or "").strip().lower()
    command = str(unlock.get("telegram_command") or "").strip()
    env_var = str(unlock.get("env_var") or "").strip()
    if not command or command == "/quantum" or provider.startswith("local qtoken"):
        return False
    if env_var and "/token" in command:
        return True
    if env_var in {"NOMAD_ALLOW_REAL_QUANTUM", "NOMAD_ALLOW_HPC_SUBMIT"} and "=" in command:
        return True
    return False


def _tone_from_snapshot(snapshot: Dict[str, Any]) -> str:
    state = snapshot.get("self_state") or {}
    products = snapshot.get("products") or {}
    product_stats = products.get("stats") or {}
    private_products = int(product_stats.get("private_offer_needs_approval") or 0)
    dev_unlocks = state.get("self_development_unlocks") or []
    actionable = [u for u in dev_unlocks if isinstance(u, dict) and (u.get("short_ask") or u.get("title"))]
    if private_products or actionable:
        return "heads_up"
    compute = snapshot.get("compute") or {}
    probe = compute.get("probe") or {}
    ollama = probe.get("ollama") or {}
    if not ollama.get("api_reachable"):
        return "gentle"
    return "calm"


def format_human_status_snapshot(snapshot: Dict[str, Any], *, periodic: bool = False) -> str:
    """Warm, short status for humans. No schemas, no agent routing tables."""
    compute = snapshot.get("compute") or {}
    products = snapshot.get("products") or {}
    state = snapshot.get("self_state") or {}
    github = snapshot.get("github_models") or {}
    xai_grok = snapshot.get("xai_grok") or {}
    addons = snapshot.get("addons") or {}
    quantum = addons.get("quantum_tokens") or {}
    quantum_unlock = quantum.get("best_next_quantum_unlock") or {}
    probe = compute.get("probe") or {}
    ollama = probe.get("ollama") or {}
    brains = compute.get("brains") or {}
    secondary = brains.get("secondary") or []
    product_stats = products.get("stats") or {}
    private_products = int(product_stats.get("private_offer_needs_approval") or 0)
    offer_ready = int(product_stats.get("offer_ready") or 0)
    product_total = len(products.get("products") or [])
    dev_unlocks = [
        u for u in (state.get("self_development_unlocks") or [])
        if isinstance(u, dict) and (u.get("short_ask") or u.get("title"))
    ]
    public_url = str(snapshot.get("public_api_url") or "").strip()
    public_configured = bool(
        public_url
        and not public_url.startswith("http://127.0.0.1")
        and not public_url.startswith("http://localhost")
    )
    tone = _tone_from_snapshot(snapshot)
    when = datetime.now(UTC).strftime("%d.%m. %H:%M UTC")

    if tone == "calm":
        opener = "Alles im grünen Bereich."
    elif tone == "gentle":
        opener = "Nomad läuft; ein paar Dinge sind noch weich verbunden."
    else:
        opener = "Kurz Bescheid: es gibt etwas, das nur du freigeben oder entscheiden kannst."

    lines = [
        f"Nomad · {when}",
        "",
        opener,
        "",
        "Was hinten passiert",
    ]
    if ollama.get("api_reachable"):
        lines.append(f"• Lokales Modell: an ({int(ollama.get('count') or 0)} Stück).")
    else:
        lines.append("• Lokales Modell: gerade nicht erreichbar – Nomad nutzt andere Wege, falls vorhanden.")
    if github.get("available"):
        lines.append("• GitHub-Modelle: verbunden.")
    elif github.get("configured"):
        lines.append("• GitHub-Modelle: eingetragen, heute evtl. gedrosselt – kein Handlungszwang für dich.")
    if xai_grok.get("available"):
        lines.append("• Grok: verbunden.")
    elif xai_grok.get("configured"):
        lines.append("• Grok: eingetragen, antwortet gerade nicht – kann warten.")
    if secondary:
        lines.append(f"• Zusätzliche Rechenwege: {len(secondary[:3])} aktiv.")
    if public_configured:
        lines.append("• Öffentliche Adresse: gesetzt – andere Agenten können Nomad von außen ansprechen.")
    else:
        lines.append("• Öffentliche Adresse: noch lokal – für Außenwelt später einmal einrichten, kein Stress.")
    lines.append(f"• Produktkatalog: {product_total} Einträge, {offer_ready} verkaufsbereit.")

    lines.extend(["", "Für dich (optional)"])
    if private_products:
        lines.append(
            f"• {private_products} Angebot(e) warten auf dein Okay, bevor etwas nach außen geht – "
            "nur wenn du das wirklich willst."
        )
    if dev_unlocks:
        ask = str(dev_unlocks[0].get("short_ask") or dev_unlocks[0].get("title") or "Freigabe")[:200]
        lines.append(f"• Freigabe: {ask}")
    if not private_products and not dev_unlocks:
        lines.append("• Gerade nichts, das deine Finger braucht.")
    next_objective = state.get("next_objective")
    if next_objective:
        lines.append(f"• Nomads nächster Fokus: {str(next_objective)[:160]}")

    if _is_actionable_quantum_unlock(quantum_unlock):
        tc = str(quantum_unlock.get("telegram_command") or "/quantum").strip()
        lines.append(f"• Quantum optional: später {tc}, wenn du magst.")
    elif isinstance(quantum, dict) and quantum.get("enabled"):
        lines.append("• Quantum: läuft lokal; kein Provider-Token nötig.")

    lines.extend(
        [
            "",
            "Hinweis: Technische Rohdaten und Agenten-Schnittstellen sind absichtlich nicht hier – "
            "dafür ist die HTTP-API gedacht (z. B. /.well-known/nomad-agent.json).",
        ]
    )
    if not periodic:
        lines.append("Mit `/unsubscribe` kannst du diese Kurzmeldungen abstellen.")

    return "\n".join(lines)


def format_human_auto_cycle_digest(trigger: str, result: Dict[str, Any]) -> str:
    """Short auto-cycle ping for humans; agents should read cycle artifacts via API/CLI."""
    development = result.get("self_development") or {}
    autonomous = result.get("autonomous_development") or {}
    action = autonomous.get("action") or {}
    lead_scout = result.get("lead_scout") or {}
    active_lead = lead_scout.get("active_lead") or {}
    lead_hint = ""
    if isinstance(active_lead, dict) and (active_lead.get("title") or active_lead.get("url")):
        lead_hint = str(active_lead.get("title") or active_lead.get("url") or "")[:120]

    trigger_de = "beim Start" if trigger == "startup" else "planmäßig"
    lines = [
        f"**Auto-Lauf** ({trigger_de})",
        "",
        "Nomad hat wieder einen Selbstlauf gedreht – du musst nichts tun.",
        f"• Ziel dieser Runde: {str(result.get('objective') or '—')[:140]}",
        f"• Nächster Fokus: {str(development.get('next_objective') or '—')[:140]}",
    ]
    if autonomous.get("skipped"):
        lines.append(f"• Eigenentwicklung: ruht ({str(autonomous.get('reason') or 'unverändert')[:80]}).")
    elif action:
        lines.append(f"• Eigenentwicklung: {str(action.get('title') or 'Fortschritt')[:140]}")
    else:
        lines.append("• Eigenentwicklung: ohne große Schlagzeile.")
    if lead_hint:
        lines.append(f"• Lead im Blick: {lead_hint}")
    lines.extend(
        [
            "",
            "Für andere KI-Agenten: strukturierte Antworten über die Nomad-API, nicht über diesen Chat.",
            "Wenn du selbst tiefer graben willst: /cycle – das ist bewusst technischer.",
        ]
    )
    return "\n".join(lines)


def format_human_auto_cycle_error(trigger: str, exc: BaseException) -> str:
    trigger_de = "beim Start" if trigger == "startup" else "planmäßig"
    return "\n".join(
        [
            f"Auto-Lauf ({trigger_de})",
            "",
            "Nomad ist diesmal ausgerutscht – passiert, kein Drama.",
            f"Technisch: {type(exc).__name__}",
            "",
            "Wenn es wiederholt: einmal `/cycle` manuell ausführen oder Logs prüfen.",
        ]
    )
