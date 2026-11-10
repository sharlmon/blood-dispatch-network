"""Clerk session verification, with a locally generated key pair (no network)."""
import base64
import os
import sys
import time
import types

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from flask import Flask, g, jsonify

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import clerk_auth as ca  # noqa: E402

ISSUER = "https://example-app-12.clerk.accounts.dev"
ORIGIN = "http://localhost:3000"


@pytest.fixture(scope="module")
def keys():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048), rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_app(public_key, monkeypatch, configured=True, disabled=False):
    monkeypatch.setenv("CORS_ORIGINS", ORIGIN)
    monkeypatch.delenv("CLERK_AUTHORIZED_PARTIES", raising=False)
    monkeypatch.setenv("CLERK_ISSUER", ISSUER if configured else "")
    monkeypatch.delenv("CLERK_PUBLISHABLE_KEY", raising=False)
    if disabled:
        monkeypatch.setenv("AUTH_DISABLED", "1")
    else:
        monkeypatch.delenv("AUTH_DISABLED", raising=False)
    app = Flask(__name__)
    ca.init_clerk(app)
    if app.extensions["clerk_verifier"] is not None:
        # Serve our test public key instead of fetching Clerk's JWKS.
        app.extensions["clerk_verifier"].jwks.get_signing_key_from_jwt = lambda token: types.SimpleNamespace(key=public_key)

    @app.get("/open")
    def open_():
        return jsonify(ok=True)

    @app.get("/me")
    @ca.require_auth
    def me():
        return jsonify(g.auth.public())

    @app.get("/hospital")
    @ca.require_hospital
    def hospital():
        return jsonify(g.auth.public())

    @app.get("/admin")
    @ca.require_role("org:admin")
    def admin():
        return jsonify(g.auth.public())

    return app.test_client()


def token(private_key, **over):
    now = int(time.time())
    claims = {"iss": ISSUER, "sub": "user_1", "sid": "sess_1", "iat": now - 5, "nbf": now - 5, "exp": now + 60, "azp": ORIGIN,
              "org_id": "org_1", "org_role": "org:admin", "org_slug": "lakeview"}
    claims.update(over)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "k1"})


def auth(t):
    return {"Authorization": f"Bearer {t}"}


def test_valid_v1_token(keys, monkeypatch):
    c = make_app(keys[0].public_key(), monkeypatch)
    r = c.get("/hospital", headers=auth(token(keys[0])))
    assert r.status_code == 200
    assert r.get_json() == {"user_id": "user_1", "session_id": "sess_1", "org_id": "org_1", "org_role": "org:admin", "org_slug": "lakeview"}


def test_valid_v2_token_org_claim(keys, monkeypatch):
    c = make_app(keys[0].public_key(), monkeypatch)
    t = token(keys[0], org_id=None, org_role=None, org_slug=None, v=2, o={"id": "org_2", "rol": "member", "slg": "hillcrest"})
    body = c.get("/hospital", headers=auth(t)).get_json()
    assert (body["org_id"], body["org_role"], body["org_slug"]) == ("org_2", "org:member", "hillcrest")


def test_public_route_needs_no_token(keys, monkeypatch):
    assert make_app(keys[0].public_key(), monkeypatch).get("/open").status_code == 200


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer"}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer not.a.jwt"}])
def test_missing_or_malformed_token_is_401(keys, monkeypatch, headers):
    r = make_app(keys[0].public_key(), monkeypatch).get("/me", headers=headers)
    assert r.status_code == 401
    assert r.headers["WWW-Authenticate"] == "Bearer"


def test_expired_token_is_401(keys, monkeypatch):
    c = make_app(keys[0].public_key(), monkeypatch)
    assert c.get("/me", headers=auth(token(keys[0], exp=int(time.time()) - 60))).status_code == 401


def test_wrong_issuer_is_401(keys, monkeypatch):
    c = make_app(keys[0].public_key(), monkeypatch)
    assert c.get("/me", headers=auth(token(keys[0], iss="https://evil.clerk.accounts.dev"))).status_code == 401


def test_wrong_authorized_party_is_401(keys, monkeypatch):
    c = make_app(keys[0].public_key(), monkeypatch)
    assert c.get("/me", headers=auth(token(keys[0], azp="https://evil.example"))).status_code == 401


def test_token_signed_with_another_key_is_401(keys, monkeypatch):
    c = make_app(keys[0].public_key(), monkeypatch)
    assert c.get("/me", headers=auth(token(keys[1]))).status_code == 401


def test_tampered_payload_is_401(keys, monkeypatch):
    c = make_app(keys[0].public_key(), monkeypatch)
    head, body, sig = token(keys[0]).split(".")
    forged = base64.urlsafe_b64encode(b'{"iss":"%s","sub":"admin","iat":1,"exp":9999999999}' % ISSUER.encode()).rstrip(b"=").decode()
    assert c.get("/me", headers=auth(f"{head}.{forged}.{sig}")).status_code == 401


def test_alg_none_is_rejected(keys, monkeypatch):
    c = make_app(keys[0].public_key(), monkeypatch)
    forged = jwt.encode({"iss": ISSUER, "sub": "x", "iat": 1, "exp": 9999999999}, None, algorithm="none")
    assert c.get("/me", headers=auth(forged)).status_code == 401


def test_pending_session_is_403(keys, monkeypatch):
    c = make_app(keys[0].public_key(), monkeypatch)
    r = c.get("/me", headers=auth(token(keys[0], sts="pending")))
    assert r.status_code == 403 and r.get_json()["error"]["code"] == "session_pending"


def test_no_hospital_is_403_for_hospital_routes_but_ok_for_auth_routes(keys, monkeypatch):
    c = make_app(keys[0].public_key(), monkeypatch)
    t = token(keys[0], org_id=None, org_role=None, org_slug=None)
    assert c.get("/me", headers=auth(t)).status_code == 200
    r = c.get("/hospital", headers=auth(t))
    assert r.status_code == 403 and r.get_json()["error"]["code"] == "hospital_required"


def test_role_check(keys, monkeypatch):
    c = make_app(keys[0].public_key(), monkeypatch)
    assert c.get("/admin", headers=auth(token(keys[0]))).status_code == 200
    r = c.get("/admin", headers=auth(token(keys[0], org_role="org:member")))
    assert r.status_code == 403 and r.get_json()["error"]["code"] == "forbidden"


def test_not_configured_fails_closed(keys, monkeypatch):
    c = make_app(keys[0].public_key(), monkeypatch, configured=False)
    r = c.get("/me", headers=auth(token(keys[0])))
    assert r.status_code == 503 and r.get_json()["error"]["code"] == "auth_not_configured"
    assert c.get("/open").status_code == 200


def test_auth_disabled_is_explicit_opt_in(keys, monkeypatch):
    c = make_app(keys[0].public_key(), monkeypatch, configured=False, disabled=True)
    assert c.get("/hospital").get_json()["user_id"] == "user_demo"


def test_jwks_outage_is_503(keys, monkeypatch):
    c = make_app(keys[0].public_key(), monkeypatch)
    from jwt.exceptions import PyJWKClientConnectionError

    def boom(_):
        raise PyJWKClientConnectionError("down")

    # swap in the failing key lookup on the live verifier
    c.application.extensions["clerk_verifier"].jwks.get_signing_key_from_jwt = boom
    assert c.get("/me", headers=auth(token(keys[0]))).status_code == 503


def test_issuer_from_publishable_key():
    pk = "pk_test_" + base64.b64encode(b"example-app-12.clerk.accounts.dev$").decode()
    assert ca.issuer_from_publishable_key(pk) == ISSUER
    with pytest.raises(ValueError):
        ca.issuer_from_publishable_key("pk_test_garbage")
