"""Verify Clerk session tokens in Flask.

The frontend sends the signed-in user's Clerk session token as ``Authorization: Bearer <jwt>``.
We verify it ourselves (no call to Clerk per request):

* signature, RS256, against Clerk's public key set (JWKS, cached),
* ``exp`` / ``nbf`` / ``iat`` with a few seconds of clock leeway,
* ``iss`` equals this Clerk instance's Frontend API URL,
* ``azp`` (the origin that asked for the token) is one of our authorized origins,
* the session is not ``pending`` (for example the user has not picked a hospital yet).

A hospital is a Clerk Organization, so ``org_id`` / ``org_role`` come from the token.

Configuration (environment):
    CLERK_PUBLISHABLE_KEY   public key, the issuer is derived from it (same as Clerk's SDKs), or
    CLERK_ISSUER            the Frontend API URL, e.g. https://xxxx.clerk.accounts.dev
    CLERK_JWKS_URL          optional override, defaults to <issuer>/.well-known/jwks.json
    CLERK_AUTHORIZED_PARTIES  comma separated origins, defaults to CORS_ORIGINS
    AUTH_DISABLED=1         explicit opt-out for local demos only (every request becomes a demo user)

If auth is not configured and AUTH_DISABLED is not set, protected routes answer 503, never "allow".
"""

from __future__ import annotations

import base64
import functools
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

import jwt
from flask import Flask, current_app, g, jsonify, request
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError

log = logging.getLogger(__name__)

LEEWAY_SECONDS = 5


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    session_id: str | None
    org_id: str | None = None
    org_role: str | None = None
    org_slug: str | None = None
    claims: dict[str, Any] = field(default_factory=dict, repr=False)

    def public(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "org_id": self.org_id,
            "org_role": self.org_role,
            "org_slug": self.org_slug,
        }


class AuthError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def issuer_from_publishable_key(key: str) -> str:
    """pk_test_<base64 of 'domain$'> -> https://domain (how Clerk's SDKs find the instance)."""
    try:
        encoded = key.split("_", 2)[2]
        domain = base64.b64decode(encoded + "=" * (-len(encoded) % 4)).decode().rstrip("$")
    except Exception as exc:  # noqa: BLE001
        raise ValueError("CLERK_PUBLISHABLE_KEY is not a valid Clerk publishable key") from exc
    if not domain or "." not in domain:
        raise ValueError("CLERK_PUBLISHABLE_KEY does not contain a Frontend API domain")
    return f"https://{domain}"


def _normalise_org(claims: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    # Session token v2: {"o": {"id", "slg", "rol"}} with the role without its "org:" prefix.
    o = claims.get("o")
    if isinstance(o, dict) and o.get("id"):
        role = o.get("rol")
        return o["id"], (f"org:{role}" if role and not role.startswith("org:") else role), o.get("slg")
    # Session token v1: flat claims.
    return claims.get("org_id"), claims.get("org_role"), claims.get("org_slug")


class ClerkVerifier:
    def __init__(self, issuer: str, jwks_url: str | None = None, authorized_parties: Iterable[str] = ()):
        self.issuer = issuer.rstrip("/")
        self.authorized_parties = {p.strip().rstrip("/") for p in authorized_parties if p and p.strip()}
        self.jwks = PyJWKClient(jwks_url or f"{self.issuer}/.well-known/jwks.json", cache_keys=True, lifespan=3600)

    def verify(self, token: str) -> AuthContext:
        try:
            signing_key = self.jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self.issuer,
                leeway=LEEWAY_SECONDS,
                options={"require": ["exp", "iat", "iss", "sub"], "verify_aud": False},
            )
        except PyJWKClientError as exc:
            # Could not fetch keys (or no key matches the token's kid).
            if "Unable to find a signing key" in str(exc):
                raise AuthError(401, "invalid_token", "Token was not signed by this Clerk instance.") from exc
            log.warning("Clerk JWKS unavailable: %s", exc)
            raise AuthError(503, "auth_unavailable", "Cannot reach the sign-in service. Use the phone process.") from exc
        except InvalidTokenError as exc:
            raise AuthError(401, "invalid_token", "Session is invalid or expired. Sign in again.") from exc

        azp = claims.get("azp")
        if self.authorized_parties and azp and azp.rstrip("/") not in self.authorized_parties:
            raise AuthError(401, "invalid_token", "Token was issued for a different app.")
        if claims.get("sts") == "pending":
            raise AuthError(403, "session_pending", "Finish setting up your account and hospital first.")

        org_id, org_role, org_slug = _normalise_org(claims)
        return AuthContext(
            user_id=claims["sub"], session_id=claims.get("sid"), org_id=org_id, org_role=org_role, org_slug=org_slug,
            claims=claims,
        )


def init_clerk(app: Flask) -> None:
    """Build the verifier from the environment and register JSON error handlers."""
    issuer = os.environ.get("CLERK_ISSUER")
    key = os.environ.get("CLERK_PUBLISHABLE_KEY")
    if not issuer and key:
        issuer = issuer_from_publishable_key(key)

    parties = os.environ.get("CLERK_AUTHORIZED_PARTIES") or os.environ.get("CORS_ORIGINS", "http://localhost:3000")
    app.extensions["clerk_verifier"] = (
        ClerkVerifier(issuer, os.environ.get("CLERK_JWKS_URL"), parties.split(",")) if issuer else None
    )
    app.config["AUTH_DISABLED"] = os.environ.get("AUTH_DISABLED") == "1"
    if app.config["AUTH_DISABLED"]:
        log.warning("AUTH_DISABLED=1: every request is treated as a demo user. Never use this in production.")
    elif not issuer:
        log.warning("Clerk is not configured: protected routes will answer 503.")

    @app.errorhandler(AuthError)
    def _auth_error(err: AuthError):
        resp = jsonify(error={"code": err.code, "message": err.message})
        resp.status_code = err.status
        if err.status == 401:
            resp.headers["WWW-Authenticate"] = "Bearer"
        return resp


def _bearer_token() -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def authenticate() -> AuthContext:
    """Verify the request's token and return who is calling (raises AuthError)."""
    if current_app.config.get("AUTH_DISABLED"):
        return AuthContext(user_id="user_demo", session_id=None, org_id="org_demo", org_role="org:admin", org_slug="demo")
    verifier: ClerkVerifier | None = current_app.extensions.get("clerk_verifier")
    if verifier is None:
        raise AuthError(503, "auth_not_configured", "Sign-in is not configured on the server.")
    token = _bearer_token()
    if not token:
        raise AuthError(401, "missing_token", "Sign in to continue.")
    return verifier.verify(token)


def _wrap(fn: Callable, check: Callable[[AuthContext], None]) -> Callable:
    @functools.wraps(fn)
    def inner(*args, **kwargs):
        ctx = authenticate()
        check(ctx)
        g.auth = ctx
        return fn(*args, **kwargs)

    return inner


def require_auth(fn: Callable) -> Callable:
    """The caller must be a signed-in user."""
    return _wrap(fn, lambda ctx: None)


def _needs_hospital(ctx: AuthContext) -> None:
    if not ctx.org_id:
        raise AuthError(403, "hospital_required", "Choose your hospital before making requests.")


def require_hospital(fn: Callable) -> Callable:
    """The caller must be signed in and acting for a hospital (a Clerk organization)."""
    return _wrap(fn, _needs_hospital)


def require_role(*roles: str) -> Callable[[Callable], Callable]:
    """Signed in, acting for a hospital, and holding one of ``roles`` (e.g. "org:admin")."""

    def check(ctx: AuthContext) -> None:
        _needs_hospital(ctx)
        if ctx.org_role not in roles:
            raise AuthError(403, "forbidden", "Your role cannot do this.")

    return lambda fn: _wrap(fn, check)
