from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlparse

from dotenv import load_dotenv


load_dotenv()

PUBLIC_API_URL_ENV = "NOMAD_PUBLIC_API_URL"
COLLABORATION_HOME_URL_ENV = "NOMAD_COLLABORATION_HOME_URL"
RENDER_DOMAIN_ENV = "NOMAD_RENDER_DOMAIN"


def normalize_public_url(value: str) -> str:
    normalized = str(value or "").strip().rstrip("/")
    if not normalized:
        return ""
    if normalized.startswith(("http://", "https://")):
        return normalized
    return f"https://{normalized}"


def is_local_service_url(value: str) -> bool:
    normalized = normalize_public_url(value)
    if not normalized:
        return False
    parsed = urlparse(normalized)
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(address.is_loopback or address.is_private or address.is_link_local)


def preferred_public_base_url(
    preferred: str = "",
    *,
    request_base_url: str = "",
    allow_local_fallback: bool = True,
) -> str:
    render_domain = normalize_public_url(os.getenv(RENDER_DOMAIN_ENV, ""))
    configured_candidates = [
        normalize_public_url(preferred),
        normalize_public_url(os.getenv(COLLABORATION_HOME_URL_ENV, "")),
        normalize_public_url(os.getenv(PUBLIC_API_URL_ENV, "")),
        render_domain,
        normalize_public_url(request_base_url),
    ]

    for candidate in configured_candidates:
        if candidate and not is_local_service_url(candidate):
            return candidate

    if allow_local_fallback:
        for candidate in configured_candidates:
            if candidate:
                return candidate
    return ""
