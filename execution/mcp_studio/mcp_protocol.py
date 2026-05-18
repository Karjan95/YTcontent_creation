"""JSON-RPC 2.0 dispatcher for the MCP endpoint.

Supports the surface needed by Claude.ai's custom connector:
- initialize (advertises tools + resources capabilities)
- ping
- tools/list, tools/call
- resources/list, resources/read  (MCP Apps — UI rendering in chat)
- notifications/initialized (accepted, no-op)
"""

import logging
import traceback

from flask import jsonify, request

from .errors import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    INTERNAL_ERROR,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    MCPError,
    jsonrpc_error_response,
)


logger = logging.getLogger(__name__)


MCP_PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "gemini-studio", "version": "0.2.0"}
SERVER_INSTRUCTIONS = (
    "Gemini Studio MCP. Generate images/videos/audio, manage the Studio "
    "asset library, and start Seedance sequences. Long-running operations "
    "(Veo, Kie, Seedance) return a task_id immediately — poll "
    "studio_get_generation_status until status='completed'. "
    "Generated media renders inline in chat via the MCP App viewer."
)

# Resource URI advertised to clients for inline rendering. Tools opt in by
# adding `_meta.ui.resourceUri` pointing at this URI; the client fetches the
# resource (HTML) and renders the tool result inside a sandboxed iframe.
MEDIA_VIEWER_URI = "ui://studio/media-viewer"
# MCP Apps standard MIME for embedded HTML/JS resources. If a host doesn't
# accept this, set MCP_VIEWER_MIME env to "text/html" to fall back.
MEDIA_VIEWER_MIME_DEFAULT = "text/html+skybridge"


def make_mcp_handler(*, tool_registry, resources):
    """Return a Flask view function for POST /mcp.

    `resources` is a dict[uri -> {name, mimeType, text, description?}] used to
    serve MCP Apps UI resources.
    """

    def handle_mcp():
        try:
            body = request.get_json(force=True, silent=False)
        except Exception:
            return jsonify(jsonrpc_error_response(None, PARSE_ERROR, "Invalid JSON")), 400

        if isinstance(body, list):
            results = [_dispatch_one(item, tool_registry, resources) for item in body]
            results = [r for r in results if r is not None]
            return jsonify(results)

        result = _dispatch_one(body, tool_registry, resources)
        if result is None:
            return ("", 204)
        return jsonify(result)

    return handle_mcp


def _dispatch_one(message, tool_registry, resources):
    if not isinstance(message, dict):
        return jsonrpc_error_response(None, INVALID_REQUEST, "Request must be an object")

    jsonrpc = message.get("jsonrpc")
    if jsonrpc != "2.0":
        return jsonrpc_error_response(message.get("id"), INVALID_REQUEST,
                                      "jsonrpc must be '2.0'")
    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params") or {}
    is_notification = "id" not in message

    try:
        if method == "initialize":
            result = _handle_initialize(params)
        elif method == "ping":
            result = {}
        elif method == "notifications/initialized":
            return None
        elif method == "tools/list":
            result = _handle_tools_list(tool_registry)
        elif method == "tools/call":
            result = _handle_tools_call(params, tool_registry)
        elif method == "resources/list":
            result = _handle_resources_list(resources)
        elif method == "resources/read":
            result = _handle_resources_read(params, resources)
        elif method == "resources/templates/list":
            result = {"resourceTemplates": []}
        else:
            if is_notification:
                return None
            return jsonrpc_error_response(msg_id, METHOD_NOT_FOUND,
                                          f"Method not found: {method}")
    except MCPError as e:
        if is_notification:
            return None
        return jsonrpc_error_response(msg_id, e.code, e.message, e.data)
    except Exception as e:
        logger.exception("MCP handler crashed")
        if is_notification:
            return None
        return jsonrpc_error_response(msg_id, INTERNAL_ERROR,
                                      "Internal server error",
                                      data={"detail": str(e)})

    if is_notification:
        return None
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _handle_initialize(params):
    return {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": {
            "tools": {"listChanged": False},
            "resources": {"listChanged": False, "subscribe": False},
        },
        "serverInfo": SERVER_INFO,
        "instructions": SERVER_INSTRUCTIONS,
    }


def _handle_tools_list(tool_registry):
    tools = []
    for name, spec in tool_registry.items():
        tool_def = {
            "name": name,
            "description": spec["description"],
            "inputSchema": spec["inputSchema"],
        }
        # Surface MCP Apps UI binding so Claude.ai renders the tool result
        # inside the linked iframe resource.
        meta = spec.get("_meta") or {}
        if meta:
            tool_def["_meta"] = meta
        tools.append(tool_def)
    return {"tools": tools}


def _handle_tools_call(params, tool_registry):
    import jsonschema

    name = (params.get("name") or "").strip()
    arguments = params.get("arguments") or {}
    if not name:
        raise MCPError(INVALID_PARAMS, "Missing tool name")
    spec = tool_registry.get(name)
    if not spec:
        raise MCPError(METHOD_NOT_FOUND, f"Unknown tool: {name}")

    try:
        jsonschema.validate(arguments, spec["inputSchema"])
    except jsonschema.ValidationError as e:
        return _error_result(f"Invalid arguments for {name}: {e.message}")

    try:
        content = spec["handler"](arguments)
    except MCPError:
        raise
    except Exception as e:
        logger.exception("Tool %s failed", name)
        return _error_result(f"{name} failed: {e}", detail=traceback.format_exc())

    if isinstance(content, dict) and "content" in content:
        return content
    if isinstance(content, list):
        return {"content": content, "isError": False}
    return {"content": [{"type": "text", "text": str(content)}], "isError": False}


def _handle_resources_list(resources):
    items = []
    for uri, r in resources.items():
        item = {"uri": uri, "name": r["name"], "mimeType": r["mimeType"]}
        if r.get("description"):
            item["description"] = r["description"]
        if r.get("_meta"):
            item["_meta"] = r["_meta"]
        items.append(item)
    return {"resources": items}


def _handle_resources_read(params, resources):
    uri = (params.get("uri") or "").strip()
    if not uri:
        raise MCPError(INVALID_PARAMS, "Missing resource uri")
    r = resources.get(uri)
    if not r:
        raise MCPError(METHOD_NOT_FOUND, f"Unknown resource: {uri}")
    content = {
        "uri": uri,
        "mimeType": r["mimeType"],
        "text": r["text"],
    }
    if r.get("_meta"):
        content["_meta"] = r["_meta"]
    return {"contents": [content]}


def _error_result(message: str, detail: str = None):
    blocks = [{"type": "text", "text": message}]
    if detail:
        blocks.append({"type": "text", "text": f"Detail:\n{detail[:2000]}"})
    return {"content": blocks, "isError": True}
