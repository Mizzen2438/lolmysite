"""Riot Sign On (RSO / OAuth2) client — account ownership verification (F-ACC-09).

RSO is the only Riot-supported way to prove a user owns the Riot account they
are linking (the in-client third-party verification code was removed in 2022).
The login id_token's ``sub`` claim is the account PUUID, so a successful sign-in
is itself the ownership proof.

The feature stays disabled until Riot issues client credentials
(:func:`is_enabled`); callers fall back to unverified manual linking meanwhile.
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx
import jwt
from django.conf import settings

# RSO is a single global authorization server (not region-routed).
AUTHORIZE_URL = "https://auth.riotgames.com/authorize"
TOKEN_URL = "https://auth.riotgames.com/token"
JWKS_URL = "https://auth.riotgames.com/jwks.json"
ISSUER = "https://auth.riotgames.com"
SCOPE = "openid offline_access"


class RsoError(Exception):
    """User-facing failure during the RSO flow."""


def is_enabled() -> bool:
    """Whether RSO credentials are configured (otherwise the flow is off)."""
    return bool(settings.RSO_CLIENT_ID and settings.RSO_CLIENT_SECRET)


def build_authorize_url(redirect_uri: str, state: str, nonce: str) -> str:
    """The URL to send the user to so they sign in with Riot."""
    params = {
        "client_id": settings.RSO_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "state": state,
        "nonce": nonce,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code(code: str, redirect_uri: str) -> dict:
    """Exchange an authorization code for tokens (server-to-server)."""
    try:
        resp = httpx.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            auth=(settings.RSO_CLIENT_ID, settings.RSO_CLIENT_SECRET),
            headers={"Accept": "application/json"},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise RsoError(f"Riot 認証サーバへの接続に失敗しました: {exc}") from exc
    if resp.status_code != 200:
        raise RsoError(f"トークン交換に失敗しました (status {resp.status_code})")
    return resp.json()


def extract_puuid(id_token: str, *, nonce: str | None = None) -> str:
    """Verify the id_token signature/claims and return the PUUID (``sub``)."""
    if not id_token:
        raise RsoError("id_token がありません。")
    try:
        signing_key = jwt.PyJWKClient(JWKS_URL).get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.RSO_CLIENT_ID,
            issuer=ISSUER,
        )
    except jwt.PyJWTError as exc:
        raise RsoError(f"id_token の検証に失敗しました: {exc}") from exc

    if nonce is not None and claims.get("nonce") != nonce:
        raise RsoError("nonce が一致しません(リプレイの可能性)。")
    puuid = claims.get("sub")
    if not puuid:
        raise RsoError("id_token に sub(PUUID)が含まれていません。")
    return puuid
