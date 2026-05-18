"""Asset-library + project MCP tools.

Direct Firestore reads/writes against users/{uid}/projects/{pid}/assets and
users/{uid}/projects/{pid}. Mirrors the shapes used by server.py routes so the
data appears identically in the Studio web UI.
"""

import json
from datetime import datetime

from flask import g

from . import content_blocks as cb


_PATCH_FIELDS = {"favorite", "prompt"}
_WRITE_FIELDS = {"kind", "url", "thumbnail_url", "prompt", "model_id",
                 "provider", "refs", "params", "favorite"}

_VIEWER_META = {"ui": {"resourceUri": "ui://studio/media-viewer"}}


def _ts_key(value):
    """Return a sortable key for a Firestore timestamp / ISO string / None."""
    if value is None:
        return 0
    if hasattr(value, "timestamp"):
        try:
            return value.timestamp()
        except Exception:
            return 0
    if isinstance(value, str):
        return value
    return 0


def build_handlers(deps: dict) -> dict:
    db = deps["db"]
    firestore = deps["firestore"]

    # ──────────────── studio_list_projects ────────────────

    def _list_projects(args):
        coll = db.collection("users").document(g.uid).collection("projects")
        # Fetch unordered then sort in Python — order_by('updated_at') silently
        # excludes docs that lack the field, which was producing stale 3-month-
        # old picks. Falls back through updated_at → created_at → doc id.
        try:
            docs = list(coll.limit(500).stream())
        except Exception:
            docs = []
        out = []
        for d in docs:
            data = d.to_dict() or {}
            out.append({
                "id": d.id,
                "title": data.get("title") or data.get("topic") or d.id,
                "topic": data.get("topic"),
                "updated_at": _iso(data.get("updated_at")),
                "created_at": _iso(data.get("created_at")),
                "_sort": _ts_key(data.get("updated_at") or data.get("created_at")),
            })
        out.sort(key=lambda x: x["_sort"], reverse=True)
        for o in out:
            o.pop("_sort", None)
        return [cb.text_block(json.dumps(out[:200], indent=2))]

    # ──────────────── studio_get_project ────────────────

    def _get_project(args):
        pid = args.get("project_id")
        if not pid:
            return _err("project_id is required")
        doc = db.collection("users").document(g.uid).collection("projects").document(pid).get()
        if not doc.exists:
            return _err(f"Project {pid} not found for this user")
        data = doc.to_dict() or {}
        slim = {
            "id": doc.id,
            "title": data.get("title"),
            "topic": data.get("topic"),
            "audience": data.get("audience"),
            "tone": data.get("tone"),
            "has_research": bool(data.get("research_dossier")),
            "has_narration": bool(data.get("narration_data")),
            "has_production_table": bool(data.get("production_table")),
            "updated_at": _iso(data.get("updated_at")),
        }
        return [cb.text_block(json.dumps(slim, indent=2))]

    # ──────────────── studio_list_assets ────────────────

    def _list_assets(args):
        pid = args.get("project_id")
        if not pid:
            return _err("project_id is required")
        limit = max(1, min(int(args.get("limit") or 50), 500))
        kind = args.get("kind")
        coll = (db.collection("users").document(g.uid)
                  .collection("projects").document(pid)
                  .collection("assets"))
        # Avoid composite (kind, ts DESC) index: filter by kind without
        # order_by, then sort in Python. Slower for huge libraries but
        # eliminates the FAILED_PRECONDITION users were hitting.
        if kind in {"image", "video", "audio"}:
            stream = coll.where("kind", "==", kind).limit(500).stream()
        else:
            stream = coll.order_by("ts", direction=firestore.Query.DESCENDING).limit(limit).stream()
        assets = []
        for d in stream:
            ad = d.to_dict() or {}
            ad["id"] = d.id
            ts = ad.get("ts")
            ad["_sort"] = _ts_key(ts)
            if hasattr(ts, "isoformat"):
                ad["ts"] = ts.isoformat()
            assets.append(ad)
        if kind in {"image", "video", "audio"}:
            assets.sort(key=lambda a: a["_sort"], reverse=True)
            assets = assets[:limit]
        for a in assets:
            a.pop("_sort", None)

        blocks = [cb.text_block(f"{len(assets)} asset(s):"),
                  cb.text_block(json.dumps(assets, indent=2)[:8000])]
        thumbs = [a for a in assets if a.get("kind") == "image" and a.get("url")][:4]
        for a in thumbs:
            blocks.append(cb.image_block_from_url(
                a["url"], fallback_name=f"asset-{a.get('id', '')}.png"))
        return blocks

    # ──────────────── studio_get_asset ────────────────

    def _get_asset(args):
        pid = args.get("project_id")
        aid = args.get("asset_id")
        if not pid or not aid:
            return _err("project_id and asset_id are required")
        doc = (db.collection("users").document(g.uid)
                 .collection("projects").document(pid)
                 .collection("assets").document(aid).get())
        if not doc.exists:
            return _err(f"Asset {aid} not found")
        data = doc.to_dict() or {}
        data["id"] = doc.id
        ts = data.get("ts")
        if hasattr(ts, "isoformat"):
            data["ts"] = ts.isoformat()
        url = data.get("url")
        kind = data.get("kind") or "image"

        blocks = [cb.text_block(json.dumps({
            "id": data["id"], "kind": kind, "url": url,
            "prompt": data.get("prompt"), "model_id": data.get("model_id"),
            "ts": data.get("ts"),
        }, indent=2))]
        if url and kind == "image":
            blocks.append(cb.image_block_from_url(url, fallback_name=f"{aid}.png"))
        elif url and kind == "audio":
            blocks.append(cb.audio_block_from_url(url, fallback_name=f"{aid}.mp3"))
        # Videos: rely on structuredContent.video_url + viewer (chat client
        # rejects resource_link video blocks). The caption text + structured
        # data is enough for Claude AND the viewer renders the <video>.
        structured = {"id": data["id"], "kind": kind, "url": url,
                       "primary_url": url, "project_id": pid}
        if kind == "image":
            structured["image_url"] = url
        elif kind == "video":
            structured["video_url"] = url
        elif kind == "audio":
            structured["audio_url"] = url
        return {"content": blocks, "structuredContent": structured,
                "isError": False}

    # ──────────────── studio_save_asset ────────────────

    def _save_asset(args):
        pid = args.get("project_id")
        if not pid:
            return _err("project_id is required")
        kind = (args.get("kind") or "").strip()
        url = (args.get("url") or "").strip()
        if kind not in {"image", "video", "audio"}:
            return _err("kind must be image, video, or audio")
        if not url:
            return _err("url is required")

        doc = {k: args[k] for k in _WRITE_FIELDS if k in args}
        doc["kind"] = kind
        doc["url"] = url
        doc["favorite"] = bool(doc.get("favorite", False))
        doc["created_by"] = g.uid
        doc["ts"] = firestore.SERVER_TIMESTAMP

        ref = (db.collection("users").document(g.uid)
                 .collection("projects").document(pid)
                 .collection("assets").document())
        ref.set(doc)
        echo = {**doc, "id": ref.id, "ts": datetime.utcnow().isoformat() + "Z"}
        return [cb.text_block(json.dumps(echo, indent=2))]

    # ──────────────── studio_update_asset ────────────────

    def _update_asset(args):
        pid = args.get("project_id")
        aid = args.get("asset_id")
        if not pid or not aid:
            return _err("project_id and asset_id are required")
        update = {k: args[k] for k in _PATCH_FIELDS if k in args}
        if not update:
            return _err("No updatable fields supplied (favorite, prompt)")
        if "favorite" in update:
            update["favorite"] = bool(update["favorite"])
        (db.collection("users").document(g.uid)
            .collection("projects").document(pid)
            .collection("assets").document(aid).set(update, merge=True))
        return [cb.text_block(f"Updated asset {aid}")]

    # ──────────────── studio_delete_asset ────────────────

    def _delete_asset(args):
        pid = args.get("project_id")
        aid = args.get("asset_id")
        if not pid or not aid:
            return _err("project_id and asset_id are required")
        (db.collection("users").document(g.uid)
            .collection("projects").document(pid)
            .collection("assets").document(aid).delete())
        return [cb.text_block(f"Deleted asset {aid}")]

    return {
        "studio_list_projects": {
            "description": "List the current user's projects. Use to find a project_id for "
                           "asset operations or studio_generate.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "handler": _list_projects,
        },
        "studio_get_project": {
            "description": "Get a single project's metadata (title, topic, completion flags).",
            "inputSchema": {
                "type": "object",
                "properties": {"project_id": {"type": "string"}},
                "required": ["project_id"],
                "additionalProperties": False,
            },
            "handler": _get_project,
        },
        "studio_list_assets": {
            "description": "List Studio assets in a project (newest first). Optionally filter "
                           "by kind. Returns metadata for all matches and inline thumbnails for "
                           "the first 4 images, rendered in chat.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "kind": {"type": "string", "enum": ["image", "video", "audio"]},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
                },
                "required": ["project_id"],
                "additionalProperties": False,
            },
            "_meta": _VIEWER_META,
            "handler": _list_assets,
        },
        "studio_get_asset": {
            "description": "Fetch a single asset by id and render its image/audio/video inline. "
                           "Useful when you know an asset_id (e.g. from a previous "
                           "studio_list_assets or studio_save_asset call).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "asset_id": {"type": "string"},
                },
                "required": ["project_id", "asset_id"],
                "additionalProperties": False,
            },
            "_meta": _VIEWER_META,
            "handler": _get_asset,
        },
        "studio_save_asset": {
            "description": "Save a generation result to the project asset library so it appears "
                           "in the Studio web UI gallery. Typically called after studio_generate "
                           "(or pass save_to_library=true on studio_generate to do this automatically).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "kind": {"type": "string", "enum": ["image", "video", "audio"]},
                    "url": {"type": "string"},
                    "thumbnail_url": {"type": "string"},
                    "prompt": {"type": "string"},
                    "model_id": {"type": "string"},
                    "provider": {"type": "string"},
                    "refs": {"type": "array"},
                    "params": {"type": "object", "additionalProperties": True},
                    "favorite": {"type": "boolean"},
                },
                "required": ["project_id", "kind", "url"],
                "additionalProperties": False,
            },
            "handler": _save_asset,
        },
        "studio_update_asset": {
            "description": "Toggle favorite or edit the prompt label of an asset.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "asset_id": {"type": "string"},
                    "favorite": {"type": "boolean"},
                    "prompt": {"type": "string"},
                },
                "required": ["project_id", "asset_id"],
                "additionalProperties": False,
            },
            "handler": _update_asset,
        },
        "studio_delete_asset": {
            "description": "Permanently delete an asset from the project asset library.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "asset_id": {"type": "string"},
                },
                "required": ["project_id", "asset_id"],
                "additionalProperties": False,
            },
            "handler": _delete_asset,
        },
    }


def _err(msg: str) -> dict:
    return {"content": [cb.text_block(msg)], "isError": True}


def _iso(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
