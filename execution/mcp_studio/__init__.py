"""MCP Studio — remote Model Context Protocol server exposing the Studio tab.

Lets Claude.ai (and any MCP client) drive image/video/audio generation, the
asset library, and Seedance sequences through OAuth 2.1 + Firebase Auth. The
package is self-contained: `register_routes(app, ...)` wires every endpoint
onto an existing Flask app, reusing the host app's Firestore client, rate
limiter, Fernet key, and Firebase Storage helper.

Tool handlers run inside the same Flask request context as the existing web
routes, so per-user Firestore namespaces (`users/{uid}/...`) are shared with
the web UI without duplication.
"""

from .routes import register_routes

__all__ = ["register_routes"]
