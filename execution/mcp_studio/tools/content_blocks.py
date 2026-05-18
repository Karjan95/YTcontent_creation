"""Helpers that produce MCP content blocks from URLs/bytes.

MCP block shapes (current spec):
  text          {"type":"text","text":"..."}
  image         {"type":"image","mimeType":"image/png","data":"<base64>"}
  audio         {"type":"audio","mimeType":"audio/mpeg","data":"<base64>"}
  resource_link {"type":"resource_link","uri":"...","name":"...","mimeType":"..."}

Hard 8 MB inline cap on image/audio bytes — beyond that, we fall back to a
resource_link so Cloud Run doesn't hit its 32 MB response cap when the same
response contains tool envelopes + multiple blocks.
"""

import base64
import logging
import urllib.request


MAX_INLINE_BYTES = 8 * 1024 * 1024  # 8 MB
DEFAULT_FETCH_TIMEOUT = 25  # seconds — Cloud Run has 60s on /mcp endpoint

logger = logging.getLogger(__name__)


# MCP content blocks default to assistant-only consumption. To make Claude.ai
# (and other clients) render media inline to the user, every media block needs
# `annotations.audience` to include "user". See MCP spec §Tool Result.
_USER_ANNOTATIONS = {"audience": ["user", "assistant"], "priority": 1.0}
# audience=["assistant"] keeps the block in the tool result for the model and
# the MCP App widget (the iframe receives the full content array regardless)
# but hides it from the chat surface so Claude.ai doesn't render it natively
# next to the widget.
_ASSISTANT_ONLY_ANNOTATIONS = {"audience": ["assistant"], "priority": 0.1}


def _annotations(user_visible: bool) -> dict:
    return _USER_ANNOTATIONS if user_visible else _ASSISTANT_ONLY_ANNOTATIONS


def text_block(text: str, *, user_visible: bool = True) -> dict:
    block = {"type": "text", "text": text}
    block["annotations"] = _annotations(user_visible)
    return block


def image_block_from_bytes(data: bytes, mime_type: str = "image/png",
                           *, user_visible: bool = True) -> dict:
    return {
        "type": "image",
        "mimeType": mime_type,
        "data": base64.b64encode(data).decode("ascii"),
        "annotations": _annotations(user_visible),
    }


def audio_block_from_bytes(data: bytes, mime_type: str = "audio/mpeg",
                           *, user_visible: bool = True) -> dict:
    return {
        "type": "audio",
        "mimeType": mime_type,
        "data": base64.b64encode(data).decode("ascii"),
        "annotations": _annotations(user_visible),
    }


def resource_link(uri: str, *, name: str, mime_type: str, description: str = None,
                  user_visible: bool = True) -> dict:
    out = {
        "type": "resource_link",
        "uri": uri,
        "name": name,
        "mimeType": mime_type,
        "annotations": _annotations(user_visible),
    }
    if description:
        out["description"] = description
    return out


def fetch_bytes(url: str, max_bytes: int = MAX_INLINE_BYTES,
                timeout: int = DEFAULT_FETCH_TIMEOUT) -> tuple:
    """Returns (bytes, mime_type) or (None, mime_type) if the URL exceeds the cap.

    The mime_type comes from the response Content-Type header (best-effort).
    Returns (None, None) on fetch error.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GeminiStudioMCP/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            mime_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
            buf = bytearray()
            chunk_size = 256 * 1024
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                if len(buf) + len(chunk) > max_bytes:
                    return (None, mime_type)
                buf.extend(chunk)
            return (bytes(buf), mime_type)
    except Exception as e:
        logger.warning("fetch_bytes failed for %s: %s", url[:80], e)
        return (None, None)


def image_block_from_url(url: str, *, fallback_name: str = "image",
                         description: str = None, user_visible: bool = True) -> dict:
    """Returns inline image block if under cap, else resource_link."""
    data, mime = fetch_bytes(url)
    if data is None:
        # Either too large or fetch failed — fall back to a link.
        return resource_link(url, name=fallback_name, mime_type=mime or "image/png",
                             description=description or "Image (inline cap exceeded)",
                             user_visible=user_visible)
    return image_block_from_bytes(data, mime_type=mime or "image/png",
                                   user_visible=user_visible)


def audio_block_from_url(url: str, *, fallback_name: str = "audio",
                         description: str = None, user_visible: bool = True) -> dict:
    data, mime = fetch_bytes(url)
    if data is None:
        return resource_link(url, name=fallback_name, mime_type=mime or "audio/mpeg",
                             description=description or "Audio (inline cap exceeded)",
                             user_visible=user_visible)
    return audio_block_from_bytes(data, mime_type=mime or "audio/mpeg",
                                   user_visible=user_visible)


def video_link(url: str, *, name: str = "video.mp4", description: str = None) -> dict:
    """Videos are never inlined — MCP image/audio block types don't cover video."""
    return resource_link(url, name=name, mime_type="video/mp4", description=description)
