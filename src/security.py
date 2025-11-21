"""WS-Security authentication helpers for ONVIF-style services."""

from typing import Optional

from fastapi import Header, HTTPException, status


def verify_wsse(username_token: Optional[str] = Header(default=None, convert_underscores=False)) -> str:
    """
    Basic WS-Security UsernameToken hook.

    In production, this function should parse the `Security` SOAP header and validate
    digests or password text according to ONVIF/WS-Security profiles. For this sample,
    we accept a simplified `UsernameToken` header value and reject missing tokens.
    """

    if not username_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing WS-Security UsernameToken header",
        )

    # Placeholder for credential verification. Swap with real user lookup or HMAC checks.
    if username_token != "devuser:devpass":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid WS-Security credentials",
        )

    return username_token

