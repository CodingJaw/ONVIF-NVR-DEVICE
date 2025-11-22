"""WS-Security authentication helpers for ONVIF-style services."""

from __future__ import annotations

import logging
import re
from typing import Iterable, Optional

from fastapi import Depends, Header, HTTPException, status

from src.users import AuthenticatedUser, UserStore, get_user_store


logger = logging.getLogger(__name__)


_TOKEN_PATTERN = re.compile(
    r"UsernameToken\s+username=\"(?P<username>[^\"]+)\"\s+password=\"(?P<password>[^\"]+)\"",
    re.IGNORECASE,
)


def _parse_username_token(username_token: str) -> tuple[str, str]:
    """Extract credentials from a UsernameToken header."""

    match = _TOKEN_PATTERN.search(username_token)
    if match:
        return match.group("username"), match.group("password")

    if ":" in username_token:
        username, password = username_token.split(":", 1)
        return username, password

    raise ValueError("Malformed UsernameToken header")


def verify_wsse(
    username_token: Optional[str] = Header(default=None, convert_underscores=False),
    store: UserStore = Depends(get_user_store),
) -> AuthenticatedUser:
    """Validate WS-Security UsernameToken credentials using the configured user store."""

    if not username_token:
        logger.debug("WS-Security UsernameToken header missing")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing WS-Security UsernameToken header",
        )

    try:
        username, password = _parse_username_token(username_token)
        logger.debug("Authenticating WS-Security user '%s'", username)
        user = store.authenticate(username, password)
    except ValueError as exc:
        logger.debug("Failed to parse UsernameToken: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc

    return AuthenticatedUser(username=user.username, roles=user.roles)


def require_roles(allowed_roles: Iterable[str]):
    """Dependency factory enforcing that the user has one of the allowed roles."""

    allowed = set(allowed_roles)

    def dependency(user: AuthenticatedUser = Depends(verify_wsse)) -> AuthenticatedUser:
        if not set(user.roles) & allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role permissions",
            )
        return user

    return dependency

