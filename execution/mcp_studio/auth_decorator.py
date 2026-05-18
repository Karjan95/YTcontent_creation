"""@require_mcp_auth — JWT-based auth that mirrors require_auth's Firestore read.

After successful decode, populates g.uid + decrypted Gemini/Kie API keys so the
existing Studio dispatchers (which read from g) work without modification.
"""

from functools import wraps
from flask import g, request, jsonify
import jwt as pyjwt

from . import jwt_tokens


def make_require_mcp_auth(*, issuer: str, audience: str, encryption_key: str,
                          db, decrypt_api_key, resource_metadata_url: str):
    """Factory so the decorator captures host-app dependencies.

    Returns a decorator suitable for Flask routes that should accept MCP-issued
    Bearer JWTs. On failure, returns 401 with WWW-Authenticate per MCP spec.
    """

    def _unauthorized(error_code: str, description: str):
        www_auth = (
            f'Bearer resource_metadata="{resource_metadata_url}", '
            f'error="{error_code}", error_description="{description}"'
        )
        resp = jsonify({"error": error_code, "error_description": description})
        resp.status_code = 401
        resp.headers["WWW-Authenticate"] = www_auth
        return resp

    def require_mcp_auth(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return _unauthorized("invalid_token", "Missing bearer token")

            token = auth_header.split("Bearer ", 1)[1].strip()
            try:
                claims = jwt_tokens.verify_token(
                    token,
                    expected_type="access",
                    issuer=issuer,
                    audience=audience,
                    encryption_key=encryption_key,
                )
            except pyjwt.ExpiredSignatureError:
                return _unauthorized("invalid_token", "Access token expired")
            except pyjwt.InvalidTokenError as e:
                return _unauthorized("invalid_token", str(e))

            # Denylist check (revoked tokens). One Firestore read per call —
            # the access token TTL is 1h, so this is the only Firestore hit on
            # the auth path. JWT itself is otherwise stateless.
            try:
                denied = db.collection("mcp_token_denylist").document(claims["jti"]).get()
                if denied.exists:
                    return _unauthorized("invalid_token", "Token has been revoked")
            except Exception:
                # Fail open on denylist read errors — better than blocking all
                # MCP traffic on a Firestore blip. Revoked tokens are rare.
                pass

            g.uid = claims["sub"]
            g.mcp_client_id = claims.get("client_id")
            g.mcp_scope = claims.get("scope", "")
            g.mcp_jti = claims["jti"]

            # Same Firestore read as require_auth — guarantees the MCP request
            # sees the user's encrypted Gemini/Kie keys exactly like the web UI.
            user_doc = db.collection("users").document(g.uid).get()
            if user_doc.exists:
                ud = user_doc.to_dict() or {}
                g.api_key = decrypt_api_key(ud.get("gemini_api_key")) if ud.get("gemini_api_key") else None
                g.kie_api_key = decrypt_api_key(ud.get("kie_api_key")) if ud.get("kie_api_key") else None
            else:
                g.api_key = None
                g.kie_api_key = None

            return f(*args, **kwargs)

        return decorated

    return require_mcp_auth
