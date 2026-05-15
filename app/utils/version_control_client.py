"""
Version Control Service client.

Sends a sync event after a new Config Table row is appended so the
version history service can record the current value for the key.

This call is best-effort: the Config Table write remains the source of
truth, and sync failures are logged so they can be retried or inspected.
"""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


async def sync_config_entry(
    *,
    entry_id: str,
    key_id: str,
    value_id: str,
    created_at,
    authorization_header: str | None,
) -> bool:
    headers: dict[str, str] = {}
    if authorization_header:
        headers["Authorization"] = authorization_header

    payload = {
        "source_entry_id": entry_id,
        "key_id": key_id,
        "value_id": value_id,
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{settings.version_control_service_url}/api/v1/sync/config-entry",
                json=payload,
                headers=headers,
            )
        if response.status_code in (200, 201):
            return True
        logger.warning(
            "Version Control Service returned unexpected status %d for entry_id=%s",
            response.status_code,
            entry_id,
        )
        return False
    except httpx.RequestError as exc:
        logger.warning("Version Control Service unreachable while syncing entry_id=%s: %s", entry_id, exc)
        return False
