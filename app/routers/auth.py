"""
Auth router  —  /api/v1/auth

Issues JWT access tokens so this service can be used standalone (e.g.
during development and testing).

In a full deployment, tokens are issued by **Service_Login** and simply
verified here; this endpoint is an optional convenience.
"""

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from app.core.config import settings
from app.utils.security import create_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class Token(BaseModel):
    access_token: str
    token_type: str


@router.post("/token", response_model=Token, summary="Issue a JWT access token")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """
    Issue a JWT access token for the given username.

    **Production**: token issuance is handled by Service_Login; this
    endpoint exists for development/testing convenience.

    ``client_id`` is reused to carry the caller's *company* name so that
    integration tests can set it without a custom field (OAuth2 form data
    does not include a company field by default).
    """
    if not settings.dev_auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Use Service Login to authenticate",
        )
    if not form_data.username or not form_data.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="username and password are required",
        )
    role = form_data.scopes[0] if form_data.scopes else "user"
    access_token = create_access_token(
        data={
            "sub": form_data.username,
            "username": form_data.username,
            "company": form_data.client_id or "",
            "role": role,
        },
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    logger.info("Token issued for user=%s", form_data.username)
    return Token(access_token=access_token, token_type="bearer")
