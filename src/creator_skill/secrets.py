from __future__ import annotations

import os

SERVICE_NAME = "Creator MD"
APIFY_ACCOUNT = "apify-api-token"


def get_apify_token() -> str | None:
    """Read the token without ever exposing it through the web API."""
    environment = os.environ.get("CREATOR_MD_APIFY_TOKEN", "").strip()
    if environment:
        return environment
    try:
        import keyring

        value = keyring.get_password(SERVICE_NAME, APIFY_ACCOUNT)
    except Exception:
        return None
    return value.strip() if value else None


def save_apify_token(token: str) -> None:
    value = token.strip()
    if len(value) < 16:
        raise ValueError("El token de Apify no parece válido.")
    try:
        import keyring

        keyring.set_password(SERVICE_NAME, APIFY_ACCOUNT, value)
    except Exception as exc:
        raise RuntimeError(
            "Windows no pudo guardar el token de forma segura."
        ) from exc


def delete_apify_token() -> None:
    try:
        import keyring

        keyring.delete_password(SERVICE_NAME, APIFY_ACCOUNT)
    except Exception:
        return
