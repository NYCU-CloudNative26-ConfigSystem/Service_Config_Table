"""
Auth dependency — validates JWT tokens issued by Service_Login.

The token format is identical to the one produced by Service_Login
(HS256, payload contains ``sub`` = username and optionally ``company``).
"""

import logging

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from app.core.exceptions import InvalidTokenError
from app.utils.security import decode_access_token

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


class CurrentUser:
    """Lightweight representation of the authenticated caller."""

    def __init__(self, username: str, company: str, role: str = "user", token: str = "") -> None:
        self.username = username
        self.company = company
        self.role = role
        self.token = token


async def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    payload = decode_access_token(token)
    username: str | None = payload.get("username") or payload.get("sub")
    if not username:
        raise InvalidTokenError()
    company: str = payload.get("company", "")
    role: str = payload.get("role", "user")
    return CurrentUser(username=username, company=company, role=role, token=token)
