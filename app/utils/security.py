"""
JWT utilities — mirrors Service_Login's token format so that tokens issued
by Service_Login can be verified here without any extra calls.

Token payload fields:
  sub  — username (str)
  company — company the user belongs to (str, optional)
  iat  — issued-at (auto, set by python-jose)
  exp  — expiry (auto)
"""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import InvalidTokenError


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT access token.

    Raises InvalidTokenError on any failure.
    """
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        if payload.get("sub") is None:
            raise InvalidTokenError()
        return payload
    except JWTError:
        raise InvalidTokenError()
