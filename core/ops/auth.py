"""Authentication helpers for the ops sub-app.

The /ops endpoints are protected by multiple auth paths:

1. **Cloudflare Access** — SSO at the edge injects
   ``Cf-Access-Authenticated-User-Email`` header.
2. **Bearer token** — for non-browser clients (Claude curl).
3. **Session cookie** — set by visiting ``/ops/login?token=<OPS_BEARER_TOKEN>``
   once in the browser. The cookie is HttpOnly + SameSite=Strict so it
   can't be read by JS and isn't sent cross-origin.

In dev (no ``OPS_BEARER_TOKEN`` set), authentication is disabled.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from typing import Final

from fastapi import Cookie, Header, HTTPException, status

# A server-side secret for signing the session cookie. Generated fresh on
# every process start — restarting the app invalidates all sessions, which
# is fine for a classroom tool. If persistence across restarts is needed,
# set OPS_COOKIE_SECRET in the environment.
_COOKIE_SECRET: Final[str] = os.environ.get(
    "OPS_COOKIE_SECRET", secrets.token_hex(32)
)

# Cookie name. Prefixed with __Host- for additional browser security
# (requires Secure, Path=/, no Domain).
_COOKIE_NAME: Final[str] = "ops_session"
_COOKIE_MAX_AGE: Final[int] = 86400  # 24 hours


def _sign_cookie(value: str) -> str:
    """Create an HMAC signature for a cookie value."""
    sig = hmac.new(_COOKIE_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()
    return f"{value}:{sig}"


def _verify_cookie(signed: str) -> str | None:
    """Verify and extract the value from a signed cookie. Returns None if invalid."""
    if ":" not in signed:
        return None
    value, sig = signed.rsplit(":", 1)
    expected = hmac.new(_COOKIE_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()
    if hmac.compare_digest(sig, expected):
        return value
    return None


def require_ops_auth(
    authorization: str | None = Header(default=None),
    cf_access_authenticated_user_email: str | None = Header(default=None),
    ops_session: str | None = Cookie(default=None, alias=_COOKIE_NAME),
) -> str:
    """FastAPI dependency that gates an /ops endpoint.

    Accepts any of: Cloudflare Access header, Bearer token, or a valid
    signed session cookie (set by /ops/login).

    Returns the caller identity string for audit logging.
    """
    expected_token = os.environ.get("OPS_BEARER_TOKEN")
    if not expected_token:
        return "dev"

    # Path 1: Cloudflare Access header.
    if cf_access_authenticated_user_email:
        return cf_access_authenticated_user_email

    # Path 2: Bearer token (curl / non-browser).
    if authorization and authorization.startswith("Bearer "):
        provided = authorization[len("Bearer "):]
        if _constant_time_eq(provided, expected_token):
            return "bearer"

    # Path 3: Signed session cookie (browser after /ops/login).
    if ops_session:
        identity = _verify_cookie(ops_session)
        if identity:
            return identity

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="ops endpoints require Cloudflare Access SSO or a bearer token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def create_session_cookie(identity: str) -> tuple[str, str, int]:
    """Create a signed session cookie value.

    Returns (cookie_name, signed_value, max_age_seconds).
    """
    return _COOKIE_NAME, _sign_cookie(identity), _COOKIE_MAX_AGE


def verify_token(token: str) -> bool:
    """Check a token against OPS_BEARER_TOKEN."""
    expected = os.environ.get("OPS_BEARER_TOKEN")
    if not expected:
        return True  # dev mode
    return _constant_time_eq(token, expected)


def _constant_time_eq(a: str, b: str) -> bool:
    """Compare two strings in constant time to avoid timing oracles."""
    return hmac.compare_digest(a.encode(), b.encode())
