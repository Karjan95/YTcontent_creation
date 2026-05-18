"""Single-shot status checks for long-running Studio backends.

Each helper returns a small dict the tool layer can convert into MCP content
blocks. Never blocks (no internal poll loops) — Claude polls on its own
cadence by calling studio_get_generation_status.
"""

from typing import Optional


def poll_kie_task_once(task_id: str, kie_api_key: str) -> dict:
    """Return Kie's status payload for a task_id. Shape:
        {status: "pending"|"completed"|"failed",
         result_urls?: [...], error?: "..."}
    """
    from kie_client import poll_task as kie_poll_task
    out = kie_poll_task(task_id, kie_api_key)
    # kie_client.poll_task returns its own shape; normalize.
    if not isinstance(out, dict):
        return {"status": "failed", "error": "Kie poll returned non-dict"}
    raw_status = (out.get("status") or "").lower()
    if raw_status in ("success", "succeeded", "completed", "done"):
        status = "completed"
    elif raw_status in ("failed", "error"):
        status = "failed"
    else:
        status = "pending"
    norm = {"status": status, "raw": out}
    urls = out.get("result_urls") or out.get("resultUrls") or out.get("urls")
    if urls:
        norm["result_urls"] = urls if isinstance(urls, list) else [urls]
    if out.get("error"):
        norm["error"] = out["error"]
    return norm


def poll_veo_op_once(operation, api_key: str) -> dict:
    """Veo (google_veo) operation status. Returns:
        {status: "pending"|"completed"|"failed",
         video_url?: "...", error?: "..."}
    """
    from gemini_client import poll_video_generation
    out = poll_video_generation(operation, api_key=api_key)
    if not isinstance(out, dict):
        return {"status": "failed", "error": "Veo poll returned non-dict"}
    if out.get("done"):
        if out.get("error"):
            return {"status": "failed", "error": str(out["error"])}
        url = out.get("video_url") or out.get("uri")
        return {"status": "completed", "video_url": url, "raw": out}
    return {"status": "pending", "raw": out}
