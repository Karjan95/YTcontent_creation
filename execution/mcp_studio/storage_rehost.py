"""Mirror third-party generation URLs to Firebase Storage.

Kie's `tempfile.aiquickdraw.com` URLs are throwaway (short TTL, geo-restricted,
sometimes outright unreachable from Claude.ai's CDN). To keep generated assets
viewable later — both inside Claude.ai's chat re-render and inside the Studio
web UI's asset library — we download each result URL once and re-upload to
Firebase Storage under the user's project folder. The returned signed URL
behaves like every other persisted asset.

Reuses the host app's `upload_to_storage` helper (server.py:154) so the storage
layout (folders, signed-URL TTLs, project namespacing) stays identical.
"""

import logging
import os
import tempfile
import time
import urllib.request


logger = logging.getLogger(__name__)


MAX_REHOST_BYTES = 50 * 1024 * 1024   # 50 MB
DEFAULT_TIMEOUT = 25                  # seconds — bounded by Cloud Run /mcp 60s budget


_KIND_FOLDER = {"image": "images", "video": "videos", "audio": "audio"}
_KIND_EXT_FALLBACK = {"image": "png", "video": "mp4", "audio": "mp3"}
_MIME_EXT = {
    "image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg",
    "image/webp": "webp", "image/gif": "gif",
    "video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov",
    "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/wav": "wav",
    "audio/x-wav": "wav", "audio/ogg": "ogg", "audio/m4a": "m4a",
}


def rehost_to_firebase(url: str, *, kind: str, project_id: str | None,
                       upload_to_storage) -> str:
    """Download `url` and re-upload via `upload_to_storage`. Returns the new
    signed URL on success, or the original `url` on any failure (graceful
    fallback so a rehost outage never breaks generation).

    `kind` is one of "image", "video", "audio".
    `upload_to_storage(local_path, folder, project_id=...)` is the host helper.
    """
    if not url or not isinstance(url, str):
        return url
    # Skip if already on a Firebase Storage signed URL — no point round-tripping.
    if "firebasestorage" in url or "storage.googleapis.com" in url:
        return url

    folder = _KIND_FOLDER.get(kind, "misc")
    fallback_ext = _KIND_EXT_FALLBACK.get(kind, "bin")

    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "GeminiStudioMCP/0.2"})
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            mime = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            ext = _MIME_EXT.get(mime, fallback_ext)
            buf = bytearray()
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                if len(buf) + len(chunk) > MAX_REHOST_BYTES:
                    logger.warning("[Rehost] size cap exceeded for %s", url[:80])
                    return url
                buf.extend(chunk)
    except Exception as e:
        logger.warning("[Rehost] download failed for %s: %s", url[:80], e)
        return url

    tmp_dir = tempfile.mkdtemp(prefix="rehost_")
    safe_name = f"mcp_{int(time.time())}_{os.urandom(3).hex()}.{ext}"
    tmp_path = os.path.join(tmp_dir, safe_name)
    try:
        with open(tmp_path, "wb") as f:
            f.write(bytes(buf))
        new_url = upload_to_storage(tmp_path, folder, project_id=project_id)
        if new_url:
            return new_url
        logger.warning("[Rehost] upload_to_storage returned empty for %s", url[:80])
        return url
    except Exception as e:
        logger.warning("[Rehost] upload failed for %s: %s", url[:80], e)
        return url
    finally:
        try:
            os.unlink(tmp_path)
            os.rmdir(tmp_dir)
        except Exception:
            pass


def rehost_many(urls, *, kind: str, project_id: str | None,
                upload_to_storage) -> list:
    """Re-host every URL in `urls`. Returns a new list, preserving order."""
    if not urls:
        return urls
    return [rehost_to_firebase(u, kind=kind, project_id=project_id,
                                upload_to_storage=upload_to_storage) for u in urls]
