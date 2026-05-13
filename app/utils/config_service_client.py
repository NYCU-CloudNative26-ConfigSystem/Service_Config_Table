"""
Config Service client.

Validates that Key IDs and Value IDs exist in the Config Service before
a new config table entry is created or updated.

Because the Config Service may not yet be deployed, the client **fails
open** (returns True) when the service is unreachable, logging a warning.
When the service explicitly returns 404 the ID is treated as invalid.
"""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


async def validate_key_id(key_id: str) -> bool:
    """Return True if the Key ID is valid (or if Config Service is unreachable)."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{settings.config_service_url}/api/v1/keys/{key_id}"
            )
        if response.status_code == 200:
            return True
        if response.status_code == 404:
            return False
        logger.warning(
            "Config Service returned unexpected status %d for key_id=%s",
            response.status_code,
            key_id,
        )
        return True
    except httpx.RequestError as exc:
        logger.warning(
            "Config Service unreachable while validating key_id=%s: %s",
            key_id,
            exc,
        )
        return True  # fail-open during development / degraded mode


async def validate_value_id(value_id: str) -> bool:
    """Return True if the Value ID is valid (or if Config Service is unreachable)."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{settings.config_service_url}/api/v1/values/{value_id}"
            )
        if response.status_code == 200:
            return True
        if response.status_code == 404:
            return False
        logger.warning(
            "Config Service returned unexpected status %d for value_id=%s",
            response.status_code,
            value_id,
        )
        return True
    except httpx.RequestError as exc:
        logger.warning(
            "Config Service unreachable while validating value_id=%s: %s",
            value_id,
            exc,
        )
        return True  # fail-open
