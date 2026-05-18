"""Wires every MCP/OAuth route onto the host Flask app.

Called once from server.py:
    register_routes(app, limiter, require_auth, db=..., decrypt_api_key=...,
                    upload_to_storage=..., encryption_key=..., firestore_module=...,
                    encrypt_api_key=..., firebase_config=...)

Idempotent on import — does not register if MCP_DISABLED env is truthy.
"""

import logging
import os

from flask import jsonify, request

from .auth_decorator import make_require_mcp_auth
from .mcp_protocol import make_mcp_handler
from .oauth import register_oauth_routes
from .tools import build_registry


logger = logging.getLogger(__name__)


def _scoped_cors(app):
    """Install Flask-CORS scoped only to MCP/OAuth/.well-known paths.

    Never installs CORS on the host UI routes — those keep their same-origin
    posture.
    """
    try:
        from flask_cors import CORS
    except ImportError:
        logger.warning("flask-cors not installed; CORS preflight may fail for /mcp")
        return
    allowed = ["https://claude.ai", "https://*.anthropic.com",
               "http://localhost:*", "http://127.0.0.1:*"]
    CORS(app, resources={
        r"/mcp": {"origins": allowed},
        r"/oauth/*": {"origins": allowed},
        r"/.well-known/*": {"origins": "*"},
    }, supports_credentials=False,
       allow_headers=["Authorization", "Content-Type", "Mcp-Session-Id",
                      "MCP-Protocol-Version"],
       expose_headers=["WWW-Authenticate", "Mcp-Session-Id"])


def register_routes(app, limiter, require_auth, *, db, decrypt_api_key,
                    upload_to_storage, encryption_key,
                    firestore_module=None, encrypt_api_key=None,
                    firebase_config=None, create_signed_put_url=None):
    """Mount MCP, OAuth, and discovery endpoints on `app`.

    `firestore_module` should be the `firestore` module from firebase_admin
    (passed in to avoid circular imports). `encrypt_api_key` mirrors
    `decrypt_api_key` from server.py. `firebase_config` is the public JS SDK
    config that the consent page injects.
    """
    if os.environ.get("MCP_DISABLED", "").lower() in ("1", "true", "yes"):
        logger.info("[MCP] MCP_DISABLED set — skipping registration")
        return

    issuer_url = (os.environ.get("MCP_ISSUER_URL") or "").rstrip("/")
    audience = f"{issuer_url}/mcp" if issuer_url else None
    resource_metadata_url = (f"{issuer_url}/.well-known/oauth-protected-resource"
                              if issuer_url else "/.well-known/oauth-protected-resource")

    if not issuer_url:
        logger.warning(
            "[MCP] MCP_ISSUER_URL not set. OAuth discovery + JWT iss/aud will "
            "fail until you set it to the canonical public URL of this service "
            "(e.g. https://content-creation-app-xyz.run.app).")

    _scoped_cors(app)

    if firestore_module is None:
        from firebase_admin import firestore as _firestore_mod
        firestore_module = _firestore_mod

    if encrypt_api_key is None:
        from server import encrypt_api_key as _encrypt
        encrypt_api_key = _encrypt

    if firebase_config is None:
        firebase_config = _default_firebase_config()

    # OAuth + discovery endpoints
    register_oauth_routes(
        app, db=db, encryption_key=encryption_key,
        issuer_url=issuer_url or "", audience=audience or "",
        firebase_config=firebase_config, limiter=limiter,
        encrypt_api_key=encrypt_api_key, decrypt_api_key=decrypt_api_key,
    )

    # Build tool registry once with shared deps closure
    tool_registry = build_registry({
        "db": db,
        "firestore": firestore_module,
        "upload_to_storage": upload_to_storage,
        "create_signed_put_url": create_signed_put_url,
    })

    # Load MCP App UI resources (the media-viewer HTML served via
    # resources/read so Claude.ai renders tool media inline).
    resources = _load_ui_resources()

    # MCP endpoint with JWT-based auth
    require_mcp_auth = make_require_mcp_auth(
        issuer=issuer_url or "",
        audience=audience or "",
        encryption_key=encryption_key,
        db=db,
        decrypt_api_key=decrypt_api_key,
        resource_metadata_url=resource_metadata_url,
    )
    mcp_handler = make_mcp_handler(tool_registry=tool_registry, resources=resources)

    @app.route("/mcp", methods=["POST", "OPTIONS"])
    @limiter.limit("600/hour")
    @require_mcp_auth
    def mcp_endpoint():
        if request.method == "OPTIONS":
            return ("", 204)
        return mcp_handler()

    # Unauthenticated GET for connector discovery probing — returns 405 with
    # WWW-Authenticate so Claude.ai can find resource metadata.
    @app.route("/mcp", methods=["GET"])
    def mcp_get():
        resp = jsonify({"error": "method_not_allowed",
                        "error_description": "POST JSON-RPC required"})
        resp.status_code = 405
        resp.headers["WWW-Authenticate"] = (
            f'Bearer resource_metadata="{resource_metadata_url}"')
        return resp

    logger.info("[MCP] registered. issuer=%s tools=%d resources=%d",
                issuer_url or "(unset)", len(tool_registry), len(resources))
    print(f"[MCP] registered. issuer={issuer_url or '(unset)'} "
          f"tools={len(tool_registry)} resources={len(resources)}")


def _load_ui_resources():
    """Load MCP App resources (ui:// URIs) from execution/mcp_studio/ui_resources/.

    Currently one resource: ui://studio/media-viewer (the inline media viewer).
    Reads the HTML once at registration and keeps it in memory — cheap and
    Cloud Run instances stay warm long enough that the cost is negligible.
    """
    resources = {}
    here = os.path.dirname(os.path.abspath(__file__))
    viewer_path = os.path.join(here, "ui_resources", "media_viewer.html")
    # `text/html;profile=mcp-app` is the value exported as RESOURCE_MIME_TYPE
    # by @modelcontextprotocol/ext-apps — the MIME Claude.ai validates against.
    # The `text/html+skybridge` form is OpenAI's ChatGPT Apps protocol — not us.
    mime = os.environ.get("MCP_VIEWER_MIME") or "text/html;profile=mcp-app"
    # CSP + sandbox permissions per the MCP-Apps resource _meta schema. Without
    # these the host iframe is locked down and can't fetch images from Firebase
    # Storage or use the clipboard for the Copy URL / Recreate buttons.
    # Per the MCP-UI spec: `connectDomains: []` disables all network fetches.
    # We need fetch() to download videos and convert them to blob URLs (videos
    # can't be base64-inlined like images; we have to fetch them client-side
    # and use blob URLs to bypass media-src CSP).
    _MEDIA_DOMAINS = [
        "https://storage.googleapis.com",
        "https://*.googleapis.com",
        "https://*.firebasestorage.app",
        "https://firebasestorage.googleapis.com",
        "https://tempfile.aiquickdraw.com",
        "https://*.aiquickdraw.com",
        "data:",
        "blob:",
    ]
    viewer_meta = {
        "csp": {
            "connectDomains": _MEDIA_DOMAINS,
            "resourceDomains": _MEDIA_DOMAINS,
        },
        "permissions": {
            "clipboardWrite": {},
        },
    }
    try:
        with open(viewer_path, "r", encoding="utf-8") as f:
            html = f.read()
        resources["ui://studio/media-viewer"] = {
            "name": "Gemini Studio Media Viewer",
            "description": "Renders images, audio, and video returned by Studio tools.",
            "mimeType": mime,
            "text": html,
            "_meta": viewer_meta,
        }
    except Exception as e:
        logger.error("[MCP] Failed to load media_viewer.html: %s", e)
    return resources


def _default_firebase_config():
    """Fallback Firebase JS config — same public values as ui/index.html.

    Kept as a default so we don't need to thread a config dict through deploy.
    Override via the `firebase_config` kwarg if you ever rotate the web app.
    """
    return {
        "apiKey": "AIzaSyCjxbYKvgw66YAC-RzfylEmJC2cFnqW8b0",
        "authDomain": "gen-lang-client-0854991687.firebaseapp.com",
        "projectId": "gen-lang-client-0854991687",
        "storageBucket": "gen-lang-client-0854991687.firebasestorage.app",
        "messagingSenderId": "637532740810",
        "appId": "1:637532740810:web:c31e25a6f9c3f5a5a6a833",
    }
