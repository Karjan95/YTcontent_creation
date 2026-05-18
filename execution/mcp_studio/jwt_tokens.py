"""HS256 JWT minting + verification for MCP access/refresh tokens.

Secret is derived from the existing ENCRYPTION_KEY via HKDF-SHA256 so we don't
need to manage a second piece of secret material. If ENCRYPTION_KEY rotates,
all outstanding MCP tokens invalidate (acceptable; same blast radius as the
Fernet-encrypted user API keys).
"""

import os
import secrets
import time
import uuid
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
import jwt as pyjwt

_ACCESS_TTL_SECONDS = 3600          # 1 hour
_REFRESH_TTL_SECONDS = 30 * 24 * 3600  # 30 days
_CLOCK_SKEW_SECONDS = 30


_cached_secret = None


def _derive_jwt_secret(encryption_key: str) -> bytes:
    """HKDF(encryption_key, salt='mcp-studio-jwt', info='hs256', len=32)."""
    global _cached_secret
    if _cached_secret is not None:
        return _cached_secret
    if not encryption_key:
        raise RuntimeError("ENCRYPTION_KEY is required to derive MCP JWT secret")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"mcp-studio-jwt",
        info=b"hs256",
    )
    _cached_secret = hkdf.derive(encryption_key.encode("utf-8"))
    return _cached_secret


def _now() -> int:
    return int(time.time())


def mint_access_token(*, uid: str, client_id: str, scope: str,
                      issuer: str, audience: str, encryption_key: str) -> dict:
    """Returns {token, jti, exp}."""
    jti = uuid.uuid4().hex
    exp = _now() + _ACCESS_TTL_SECONDS
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": uid,
        "client_id": client_id,
        "scope": scope or "",
        "iat": _now(),
        "exp": exp,
        "jti": jti,
        "typ": "access",
    }
    secret = _derive_jwt_secret(encryption_key)
    token = pyjwt.encode(claims, secret, algorithm="HS256")
    return {"token": token, "jti": jti, "exp": exp}


def mint_refresh_token(*, uid: str, client_id: str, scope: str,
                       issuer: str, encryption_key: str) -> dict:
    jti = uuid.uuid4().hex
    exp = _now() + _REFRESH_TTL_SECONDS
    claims = {
        "iss": issuer,
        "sub": uid,
        "client_id": client_id,
        "scope": scope or "",
        "iat": _now(),
        "exp": exp,
        "jti": jti,
        "typ": "refresh",
    }
    secret = _derive_jwt_secret(encryption_key)
    token = pyjwt.encode(claims, secret, algorithm="HS256")
    return {"token": token, "jti": jti, "exp": exp}


def verify_token(token: str, *, expected_type: str, issuer: str,
                 audience: str | None, encryption_key: str) -> dict:
    """Decode and validate a JWT. Raises pyjwt exceptions on failure.

    `audience` may be None for refresh tokens (no aud claim required).
    """
    secret = _derive_jwt_secret(encryption_key)
    options = {"require": ["exp", "iat", "iss", "sub", "jti", "typ"]}
    decode_kwargs = dict(
        algorithms=["HS256"],
        issuer=issuer,
        options=options,
        leeway=_CLOCK_SKEW_SECONDS,
    )
    if audience:
        decode_kwargs["audience"] = audience
    claims = pyjwt.decode(token, secret, **decode_kwargs)
    if claims.get("typ") != expected_type:
        raise pyjwt.InvalidTokenError(f"Expected typ={expected_type}, got {claims.get('typ')}")
    return claims


def generate_opaque(length_bytes: int = 32) -> str:
    """URL-safe random secret for auth codes, client secrets, etc."""
    return secrets.token_urlsafe(length_bytes)


def pkce_verify(code_verifier: str, code_challenge: str, method: str = "S256") -> bool:
    """RFC 7636 PKCE S256 verification."""
    import base64
    import hashlib
    if method != "S256":
        return False
    if not code_verifier or not code_challenge:
        return False
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    derived = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    # Constant-time compare
    return secrets.compare_digest(derived, code_challenge)
