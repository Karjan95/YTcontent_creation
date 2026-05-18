"""OAuth 2.1 + RFC 7591 (DCR) endpoints for the MCP server.

All endpoints registered on the host Flask app (no url_prefix — .well-known
must be at the root). Discovery, dynamic client registration, authorize+consent
split (HTML page → XHR consent), token exchange with PKCE, and revocation.
"""

import time
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlparse

from firebase_admin import auth as fb_auth
from flask import jsonify, request, redirect as flask_redirect
import jwt as pyjwt

from . import jwt_tokens
from .consent_template import render_consent_page


_CODE_TTL_SECONDS = 60
_ALLOWED_GRANT_TYPES = {"authorization_code", "refresh_token"}
_DEFAULT_SCOPES = ["studio:read", "studio:write"]


def register_oauth_routes(app, *, db, encryption_key, issuer_url, audience,
                          firebase_config, limiter, encrypt_api_key, decrypt_api_key):

    base_path = ""  # endpoints live at root

    # ──────────── Discovery ────────────

    @app.route("/.well-known/oauth-protected-resource", methods=["GET", "OPTIONS"])
    def mcp_protected_resource_metadata():
        return jsonify({
            "resource": f"{issuer_url}/mcp",
            "authorization_servers": [issuer_url],
            "bearer_methods_supported": ["header"],
            "scopes_supported": _DEFAULT_SCOPES,
            "resource_documentation": f"{issuer_url}/",
        })

    @app.route("/.well-known/oauth-authorization-server", methods=["GET", "OPTIONS"])
    def mcp_authorization_server_metadata():
        return jsonify({
            "issuer": issuer_url,
            "authorization_endpoint": f"{issuer_url}/oauth/authorize",
            "token_endpoint": f"{issuer_url}/oauth/token",
            "registration_endpoint": f"{issuer_url}/oauth/register",
            "revocation_endpoint": f"{issuer_url}/oauth/revoke",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["client_secret_post", "none"],
            "scopes_supported": _DEFAULT_SCOPES,
        })

    # ──────────── Dynamic Client Registration (RFC 7591) ────────────

    @app.route("/oauth/register", methods=["POST", "OPTIONS"])
    @limiter.limit("30/hour")
    def mcp_oauth_register():
        if request.method == "OPTIONS":
            return ("", 204)
        data = request.json or {}
        redirect_uris = data.get("redirect_uris") or []
        if not isinstance(redirect_uris, list) or not redirect_uris:
            return jsonify({"error": "invalid_redirect_uri",
                            "error_description": "redirect_uris is required"}), 400
        for uri in redirect_uris:
            if not isinstance(uri, str):
                return jsonify({"error": "invalid_redirect_uri"}), 400
            parsed = urlparse(uri)
            if parsed.scheme not in ("https", "http"):
                return jsonify({"error": "invalid_redirect_uri",
                                "error_description": f"Scheme not allowed: {uri}"}), 400
            # Allow localhost http for local testing only.
            if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1"):
                return jsonify({"error": "invalid_redirect_uri",
                                "error_description": "http only allowed for localhost"}), 400

        client_name = (data.get("client_name") or "").strip()[:200] or "Unnamed MCP Client"
        auth_method = data.get("token_endpoint_auth_method") or "none"
        if auth_method not in ("none", "client_secret_post"):
            return jsonify({"error": "invalid_client_metadata",
                            "error_description": "Unsupported auth method"}), 400
        grant_types = data.get("grant_types") or ["authorization_code", "refresh_token"]
        if not set(grant_types).issubset(_ALLOWED_GRANT_TYPES):
            return jsonify({"error": "invalid_client_metadata",
                            "error_description": "Unsupported grant type"}), 400

        client_id = jwt_tokens.generate_opaque(24)
        client_secret = None
        encrypted_secret = None
        if auth_method == "client_secret_post":
            client_secret = jwt_tokens.generate_opaque(36)
            encrypted_secret = encrypt_api_key(client_secret)

        doc = {
            "client_id": client_id,
            "client_name": client_name,
            "redirect_uris": redirect_uris,
            "grant_types": grant_types,
            "token_endpoint_auth_method": auth_method,
            "scope": " ".join(_DEFAULT_SCOPES),
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
        if encrypted_secret:
            doc["client_secret_enc"] = encrypted_secret
        db.collection("mcp_oauth_clients").document(client_id).set(doc)

        resp = {
            "client_id": client_id,
            "client_name": client_name,
            "redirect_uris": redirect_uris,
            "grant_types": grant_types,
            "token_endpoint_auth_method": auth_method,
            "scope": doc["scope"],
        }
        if client_secret:
            resp["client_secret"] = client_secret
        return jsonify(resp), 201

    # ──────────── Authorize (HTML consent page) ────────────

    @app.route("/oauth/authorize", methods=["GET"])
    def mcp_oauth_authorize():
        client_id = request.args.get("client_id", "").strip()
        redirect_uri = request.args.get("redirect_uri", "").strip()
        state = request.args.get("state", "")
        code_challenge = request.args.get("code_challenge", "").strip()
        code_challenge_method = request.args.get("code_challenge_method", "S256").strip()
        response_type = request.args.get("response_type", "code").strip()
        scope = request.args.get("scope", "studio:write").strip()

        if response_type != "code":
            return _redirect_with_error(redirect_uri, state,
                                        "unsupported_response_type",
                                        "Only response_type=code is supported")
        if code_challenge_method != "S256":
            return _redirect_with_error(redirect_uri, state,
                                        "invalid_request",
                                        "code_challenge_method must be S256")
        if not code_challenge:
            return _redirect_with_error(redirect_uri, state,
                                        "invalid_request",
                                        "code_challenge is required")

        client_doc = db.collection("mcp_oauth_clients").document(client_id).get()
        if not client_doc.exists:
            return _error_page("Unknown client_id."), 400
        client = client_doc.to_dict() or {}
        if redirect_uri not in (client.get("redirect_uris") or []):
            return _error_page("redirect_uri does not match this client's registration."), 400

        html_body = render_consent_page(
            client_id=client_id,
            client_name=client.get("client_name") or client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            scope=scope,
            firebase_config=firebase_config,
        )
        return (html_body, 200, {"Content-Type": "text/html; charset=utf-8"})

    # ──────────── Consent (XHR from authorize HTML) ────────────

    @app.route("/oauth/consent", methods=["POST", "OPTIONS"])
    @limiter.limit("60/hour")
    def mcp_oauth_consent():
        if request.method == "OPTIONS":
            return ("", 204)
        data = request.json or {}
        firebase_id_token = data.get("firebase_id_token")
        client_id = (data.get("client_id") or "").strip()
        redirect_uri = (data.get("redirect_uri") or "").strip()
        state = data.get("state") or ""
        code_challenge = (data.get("code_challenge") or "").strip()
        code_challenge_method = (data.get("code_challenge_method") or "S256").strip()
        scope = (data.get("scope") or "studio:write").strip()

        if not firebase_id_token:
            return jsonify({"error": "invalid_request",
                            "error_description": "firebase_id_token required"}), 400
        if code_challenge_method != "S256" or not code_challenge:
            return jsonify({"error": "invalid_request",
                            "error_description": "PKCE S256 required"}), 400

        client_doc = db.collection("mcp_oauth_clients").document(client_id).get()
        if not client_doc.exists:
            return jsonify({"error": "invalid_client"}), 400
        client = client_doc.to_dict() or {}
        if redirect_uri not in (client.get("redirect_uris") or []):
            return jsonify({"error": "invalid_request",
                            "error_description": "redirect_uri mismatch"}), 400

        try:
            decoded = fb_auth.verify_id_token(firebase_id_token)
            uid = decoded["uid"]
        except Exception as e:
            return jsonify({"error": "access_denied",
                            "error_description": f"Firebase auth failed: {e}"}), 401

        code = jwt_tokens.generate_opaque(32)
        exp_at = datetime.utcnow() + timedelta(seconds=_CODE_TTL_SECONDS)
        db.collection("mcp_oauth_codes").document(code).set({
            "uid": uid,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "scope": scope,
            "used": False,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "exp_at": exp_at,
        })

        redir = redirect_uri
        sep = "&" if "?" in redir else "?"
        params = {"code": code}
        if state:
            params["state"] = state
        redir = f"{redir}{sep}{urlencode(params)}"
        return jsonify({"redirect": redir})

    # ──────────── Token ────────────

    @app.route("/oauth/token", methods=["POST", "OPTIONS"])
    @limiter.limit("300/hour")
    def mcp_oauth_token():
        if request.method == "OPTIONS":
            return ("", 204)
        # OAuth token endpoint accepts form-encoded or JSON. Be lenient.
        if request.is_json:
            form = request.json or {}
        else:
            form = request.form.to_dict() or {}

        grant_type = (form.get("grant_type") or "").strip()
        if grant_type == "authorization_code":
            return _grant_authorization_code(form)
        if grant_type == "refresh_token":
            return _grant_refresh_token(form)
        return jsonify({"error": "unsupported_grant_type"}), 400

    def _grant_authorization_code(form):
        code = (form.get("code") or "").strip()
        code_verifier = (form.get("code_verifier") or "").strip()
        client_id = (form.get("client_id") or "").strip()
        redirect_uri = (form.get("redirect_uri") or "").strip()
        client_secret_in = (form.get("client_secret") or "").strip()

        if not code or not code_verifier or not client_id or not redirect_uri:
            return jsonify({"error": "invalid_request"}), 400

        client_doc = db.collection("mcp_oauth_clients").document(client_id).get()
        if not client_doc.exists:
            return jsonify({"error": "invalid_client"}), 401
        client = client_doc.to_dict() or {}
        if client.get("token_endpoint_auth_method") == "client_secret_post":
            stored = client.get("client_secret_enc")
            stored_plain = decrypt_api_key(stored) if stored else None
            if not stored_plain or not _const_eq(client_secret_in, stored_plain):
                return jsonify({"error": "invalid_client"}), 401

        code_ref = db.collection("mcp_oauth_codes").document(code)
        code_doc = code_ref.get()
        if not code_doc.exists:
            return jsonify({"error": "invalid_grant", "error_description": "Unknown code"}), 400
        cdata = code_doc.to_dict() or {}
        if cdata.get("used"):
            return jsonify({"error": "invalid_grant", "error_description": "Code already used"}), 400
        exp_at = cdata.get("exp_at")
        if exp_at and hasattr(exp_at, "timestamp") and exp_at.timestamp() < time.time():
            return jsonify({"error": "invalid_grant", "error_description": "Code expired"}), 400
        if cdata.get("client_id") != client_id:
            return jsonify({"error": "invalid_grant",
                            "error_description": "client_id mismatch"}), 400
        if cdata.get("redirect_uri") != redirect_uri:
            return jsonify({"error": "invalid_grant",
                            "error_description": "redirect_uri mismatch"}), 400
        if not jwt_tokens.pkce_verify(code_verifier,
                                       cdata.get("code_challenge", ""),
                                       cdata.get("code_challenge_method", "S256")):
            return jsonify({"error": "invalid_grant",
                            "error_description": "PKCE verification failed"}), 400

        code_ref.update({"used": True})

        uid = cdata["uid"]
        scope = cdata.get("scope", "studio:write")
        access = jwt_tokens.mint_access_token(
            uid=uid, client_id=client_id, scope=scope,
            issuer=issuer_url, audience=audience, encryption_key=encryption_key)
        refresh = jwt_tokens.mint_refresh_token(
            uid=uid, client_id=client_id, scope=scope,
            issuer=issuer_url, encryption_key=encryption_key)
        return jsonify({
            "access_token": access["token"],
            "token_type": "Bearer",
            "expires_in": access["exp"] - int(time.time()),
            "refresh_token": refresh["token"],
            "scope": scope,
        })

    def _grant_refresh_token(form):
        refresh_token = (form.get("refresh_token") or "").strip()
        client_id = (form.get("client_id") or "").strip()
        client_secret_in = (form.get("client_secret") or "").strip()
        if not refresh_token or not client_id:
            return jsonify({"error": "invalid_request"}), 400

        client_doc = db.collection("mcp_oauth_clients").document(client_id).get()
        if not client_doc.exists:
            return jsonify({"error": "invalid_client"}), 401
        client = client_doc.to_dict() or {}
        if client.get("token_endpoint_auth_method") == "client_secret_post":
            stored = client.get("client_secret_enc")
            stored_plain = decrypt_api_key(stored) if stored else None
            if not stored_plain or not _const_eq(client_secret_in, stored_plain):
                return jsonify({"error": "invalid_client"}), 401

        try:
            claims = jwt_tokens.verify_token(
                refresh_token, expected_type="refresh",
                issuer=issuer_url, audience=None, encryption_key=encryption_key)
        except pyjwt.ExpiredSignatureError:
            return jsonify({"error": "invalid_grant", "error_description": "Refresh expired"}), 400
        except pyjwt.InvalidTokenError as e:
            return jsonify({"error": "invalid_grant", "error_description": str(e)}), 400

        if claims.get("client_id") != client_id:
            return jsonify({"error": "invalid_grant",
                            "error_description": "client_id mismatch"}), 400

        # Denylist check
        try:
            denied = db.collection("mcp_token_denylist").document(claims["jti"]).get()
            if denied.exists:
                return jsonify({"error": "invalid_grant",
                                "error_description": "Refresh revoked"}), 400
        except Exception:
            pass

        # Rotate: denylist the old refresh jti, mint a new pair.
        try:
            db.collection("mcp_token_denylist").document(claims["jti"]).set({
                "exp_at": datetime.utcfromtimestamp(claims["exp"]),
                "reason": "rotated",
            })
        except Exception:
            pass

        uid = claims["sub"]
        scope = claims.get("scope", "studio:write")
        access = jwt_tokens.mint_access_token(
            uid=uid, client_id=client_id, scope=scope,
            issuer=issuer_url, audience=audience, encryption_key=encryption_key)
        new_refresh = jwt_tokens.mint_refresh_token(
            uid=uid, client_id=client_id, scope=scope,
            issuer=issuer_url, encryption_key=encryption_key)
        return jsonify({
            "access_token": access["token"],
            "token_type": "Bearer",
            "expires_in": access["exp"] - int(time.time()),
            "refresh_token": new_refresh["token"],
            "scope": scope,
        })

    # ──────────── Revoke ────────────

    @app.route("/oauth/revoke", methods=["POST", "OPTIONS"])
    @limiter.limit("60/hour")
    def mcp_oauth_revoke():
        if request.method == "OPTIONS":
            return ("", 204)
        if request.is_json:
            form = request.json or {}
        else:
            form = request.form.to_dict() or {}
        token = (form.get("token") or "").strip()
        if not token:
            return ("", 200)  # spec: 200 even for unknown tokens
        # Try as access first, then refresh
        for typ in ("access", "refresh"):
            try:
                aud = audience if typ == "access" else None
                claims = jwt_tokens.verify_token(
                    token, expected_type=typ, issuer=issuer_url,
                    audience=aud, encryption_key=encryption_key)
                db.collection("mcp_token_denylist").document(claims["jti"]).set({
                    "exp_at": datetime.utcfromtimestamp(claims["exp"]),
                    "reason": "revoked",
                })
                break
            except pyjwt.InvalidTokenError:
                continue
        return ("", 200)


def _redirect_with_error(redirect_uri, state, error, description):
    if not redirect_uri:
        return (description, 400)
    params = {"error": error, "error_description": description}
    if state:
        params["state"] = state
    sep = "&" if "?" in redirect_uri else "?"
    return flask_redirect(f"{redirect_uri}{sep}{urlencode(params)}")


def _error_page(msg):
    return (f"<!doctype html><html><body style='font-family:sans-serif;padding:40px'>"
            f"<h1>OAuth error</h1><p>{msg}</p></body></html>",
            200, {"Content-Type": "text/html; charset=utf-8"})


def _const_eq(a, b):
    import secrets as _secrets
    return _secrets.compare_digest(a or "", b or "")
