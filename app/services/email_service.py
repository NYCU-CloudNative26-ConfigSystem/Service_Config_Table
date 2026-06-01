import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import aiosmtplib

from app.core.config import settings

logger = logging.getLogger(__name__)


async def send_update_notification(
    to_email: str,
    alias: str,
    config_relation_uuid: str,
) -> None:
    """Send an email notifying the user that a truth node value was updated."""
    if not settings.gmail_user or not settings.gmail_app_password:
        logger.warning("Gmail credentials not configured — skipping email to %s", to_email)
        return

    link = f"{settings.app_base_url.rstrip('/')}/config-snapshot/{config_relation_uuid}" \
        if settings.app_base_url else "(log in to the app to view your config)"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Config update available: {alias}"
    msg["From"] = settings.gmail_user
    msg["To"] = to_email

    body = (
        f"Hello,\n\n"
        f'The truth node "{alias}" has been updated to a new value.\n\n'
        f"You have a config entry that references this value. "
        f"If you would like to update your config to use the latest value, "
        f"please visit:\n\n"
        f"  {link}\n\n"
        f"No action is required if you want to keep your current value.\n\n"
        f"— Config System"
    )
    msg.attach(MIMEText(body, "plain"))

    try:
        await aiosmtplib.send(
            msg,
            hostname="smtp.gmail.com",
            port=587,
            start_tls=True,
            username=settings.gmail_user,
            password=settings.gmail_app_password,
        )
        logger.info("Notification sent to %s for alias '%s'", to_email, alias)
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc)
