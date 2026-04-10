"""Authentication helpers for the ops sub-app.

The /ops endpoints are protected by two layers in production:

1. **Cloudflare Access** sits in front of the tunnel and only lets the
   instructor's email through. Successful Access requests carry a
   ``Cf-Access-Authenticated-User-Email`` header.

2. **Bearer token** as a fallback path for non-browser clients (notably
   the Claude Code session that ``curl``s ``/ops/events.json`` to
   co-monitor). The token comes from the ``OPS_BEARER_TOKEN`` env var.

In dev (no ``OPS_BEARER_TOKEN`` set), authentication is disabled — useful
for local development without setting up Cloudflare Access.
"""

from __future__ import annotations

import os

from fastapi import Header, HTTPException, status

# Cloudflare Access injects the authenticated user's email in the
# `Cf-Access-Authenticated-User-Email` header on every request that passes
# its SSO check. FastAPI's Header() converts the snake_case parameter name
# `cf_access_authenticated_user_email` into that header name automatically.


def require_ops_auth(
    authorization: str | None = Header(default=None),
    cf_access_authenticated_user_email: str | None = Header(default=None),
) -> str:
    """FastAPI dependency that gates an /ops endpoint.

    Returns the identity of the caller as a string — either an email
    (from Cloudflare Access) or ``"bearer"`` (when the bearer token path
    was used) or ``"dev"`` (when authentication is disabled).

    Args:
        authorization: The ``Authorization`` request header. FastAPI
            populates this from the request automatically.
        cf_access_authenticated_user_email: The
            ``Cf-Access-Authenticated-User-Email`` header injected by
            Cloudflare Access on successful SSO.

    Returns:
        The caller identity string for audit logging.

    Raises:
        HTTPException: 401 if no valid auth was provided in production.
    """
    expected_token = os.environ.get("OPS_BEARER_TOKEN")
    if not expected_token:
        return "dev"

    # Cloudflare Access path — trust the header injected at the edge.
    if cf_access_authenticated_user_email:
        return cf_access_authenticated_user_email

    # Bearer token path — used by Claude curl and any other non-browser client.
    if authorization and authorization.startswith("Bearer "):
        provided = authorization[len("Bearer "):]
        if _constant_time_eq(provided, expected_token):
            return "bearer"

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="ops endpoints require Cloudflare Access SSO or a bearer token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _constant_time_eq(a: str, b: str) -> bool:
    """Compare two strings in constant time to avoid timing oracles.

    Standard Python ``==`` short-circuits on the first differing byte, which
    leaks token length and prefix to a remote attacker. ``hmac.compare_digest``
    avoids this; we wrap it for explicit intent at the call site.
    """
    import hmac  # noqa: PLC0415

    return hmac.compare_digest(a.encode(), b.encode())
