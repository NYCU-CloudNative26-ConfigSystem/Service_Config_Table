import asyncio
import json
import logging

import httpx
from redis.asyncio import Redis
from sqlalchemy import select, distinct

from app.core.config import settings
from app.database.connection import AsyncSessionLocal
from app.models.config_table import CT, ConfigRelationUser
from app.services.email_service import send_update_notification

logger = logging.getLogger(__name__)

_LOGIN_SERVICE_URL = "http://service-login:8000"


async def _fetch_emails(user_ids: list[str]) -> dict[str, str]:
    """Call Service Login internal endpoint to get emails for a list of usernames."""
    if not user_ids:
        return {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{_LOGIN_SERVICE_URL}/internal/users/emails",
                json={"user_ids": user_ids},
                headers={"x-internal-key": settings.internal_api_key},
            )
            resp.raise_for_status()
            return {item["user_id"]: item["email"] for item in resp.json()}
    except Exception as exc:
        logger.error("Failed to fetch user emails from login service: %s", exc)
        return {}


async def _handle_truth_updated(data: dict) -> None:
    name_id = data.get("nameId")
    alias = data.get("alias", name_id)

    if not name_id:
        return

    async with AsyncSessionLocal() as db:
        # Find config relations that have a CT row referencing this NameNode
        cr_uuids_result = await db.execute(
            select(distinct(CT.config_relation_uuid)).where(CT.key == name_id)
        )
        cr_uuids = [r for (r,) in cr_uuids_result.all()]

        if not cr_uuids:
            logger.debug("No configs reference nameId %s — no notifications sent", name_id)
            return

        # Find all users linked to those config relations
        users_result = await db.execute(
            select(ConfigRelationUser.user_id, ConfigRelationUser.config_relation_uuid)
            .where(ConfigRelationUser.config_relation_uuid.in_(cr_uuids))
        )
        rows = users_result.all()

    if not rows:
        return

    unique_user_ids = list({r.user_id for r in rows})
    email_map = await _fetch_emails(unique_user_ids)

    # Send one email per (user, config_relation) pair so the link is specific
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row.user_id, row.config_relation_uuid)
        if key in seen:
            continue
        seen.add(key)
        email = email_map.get(row.user_id)
        if not email:
            logger.debug("No email found for user_id %s — skipping", row.user_id)
            continue
        await send_update_notification(email, alias, row.config_relation_uuid)


async def start_subscriber() -> None:
    """Background task: subscribe to Redis truth:updated channel and dispatch notifications."""
    redis_url = settings.redis_url
    while True:
        try:
            redis: Redis = Redis.from_url(redis_url, decode_responses=True)
            pubsub = redis.pubsub()
            await pubsub.subscribe("truth:updated")
            logger.info("Subscribed to Redis channel 'truth:updated'")
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    await _handle_truth_updated(data)
                except Exception as exc:
                    logger.error("Error handling truth:updated message: %s", exc)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Redis subscriber error, reconnecting in 5s: %s", exc)
            await asyncio.sleep(5)
