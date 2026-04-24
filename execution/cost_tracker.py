"""Cost event + daily rollup writer for the usage dashboard.

Every billable Gemini call funnels through ``record_usage()``. This writes two
docs in a single Firestore batch:

    users/{uid}/cost_events/{autoId}       (append-only per-call log)
    users/{uid}/cost_rollups/{YYYY-MM-DD}  (aggregated totals via Increment)

Writes are dispatched to a small thread pool so request latency is unchanged —
a dropped event never blocks the caller. ``uid=None`` is a no-op (CLI path).

Pricing is resolved via ``pricing.get_rate`` so Google-side changes need only a
Firestore doc edit, not a redeploy.
"""

from __future__ import annotations

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional

import pricing

# Fire-and-forget executor — 4 workers is plenty for the 100–250 calls-per-video
# workload. The GIL isn't a bottleneck here; the threads spend all their time
# waiting on Firestore HTTP.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cost-tracker")
_executor_lock = threading.Lock()


# ── Firestore client acquisition ────────────────────────────────────────────

def _get_db():
    """Return the live Firestore client, or None if firebase hasn't initialised."""
    try:
        from firebase_admin import firestore
        return firestore.client()
    except Exception:
        return None


# ── Cost math ───────────────────────────────────────────────────────────────

def get_cost(tool: str, model: str, usage: dict) -> tuple[float, str, bool]:
    """Return (cost_usd, pricing_version, is_fallback) for a call.

    ``usage`` keys by tool:
        text:   {"in_tokens", "out_tokens", "cached_tokens"}
        image / imagen: {"images"}
        tts:    {"tts_chars"}
        veo:    {"video_seconds"}
    """
    rate, is_fallback = pricing.get_rate(tool, model)
    version = pricing.get_pricing_version()

    if tool == "text":
        in_tokens = int(usage.get("in_tokens", 0) or 0)
        out_tokens = int(usage.get("out_tokens", 0) or 0)
        cached_tokens = int(usage.get("cached_tokens", 0) or 0)
        # Gemini's usage_metadata.prompt_token_count already INCLUDES cached_tokens,
        # so we subtract to avoid double-billing the cached portion at the full rate.
        billable_in = max(in_tokens - cached_tokens, 0)
        cost = (
            billable_in / 1_000_000.0 * float(rate.get("in_per_1m", 0))
            + cached_tokens / 1_000_000.0 * float(rate.get("cached_in_per_1m", 0))
            + out_tokens / 1_000_000.0 * float(rate.get("out_per_1m", 0))
        )
    elif tool in ("image", "imagen"):
        cost = int(usage.get("images", 0) or 0) * float(rate.get("per_image", 0))
    elif tool == "tts":
        cost = int(usage.get("tts_chars", 0) or 0) / 1000.0 * float(rate.get("per_1k_chars", 0))
    elif tool == "veo":
        cost = float(usage.get("video_seconds", 0) or 0) * float(rate.get("per_second", 0))
    else:
        cost = 0.0

    return round(cost, 6), version, is_fallback


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── Rollup update builder ───────────────────────────────────────────────────

def _rollup_updates(day: str, tool: str, model: str, project_id: Optional[str],
                    usage: dict, cost: float) -> dict:
    """Dot-path Increment updates for the day's rollup doc.

    All keys are dot-paths so Firestore merges nested fields correctly without
    us having to read-modify-write.
    """
    from firebase_admin import firestore as _fs
    Inc = _fs.Increment

    updates = {
        "day": day,
        "updated_at": _fs.SERVER_TIMESTAMP,
        "total_usd": Inc(cost),
        f"by_tool.{tool}.calls": Inc(1),
        f"by_tool.{tool}.cost_usd": Inc(cost),
        f"by_model.{model}.calls": Inc(1),
        f"by_model.{model}.cost_usd": Inc(cost),
    }

    # Per-project bucket (or "_account" when no project context)
    project_key = project_id or "_account"
    # Firestore rejects dots in field-path segments; sanitize just in case.
    safe_project_key = project_key.replace(".", "_").replace("/", "_")
    updates[f"by_project.{safe_project_key}.calls"] = Inc(1)
    updates[f"by_project.{safe_project_key}.cost_usd"] = Inc(cost)

    # Tool-specific usage counters (useful for dashboards to show e.g. total tokens)
    if tool == "text":
        updates[f"by_tool.{tool}.in_tokens"] = Inc(int(usage.get("in_tokens", 0) or 0))
        updates[f"by_tool.{tool}.out_tokens"] = Inc(int(usage.get("out_tokens", 0) or 0))
        updates[f"by_tool.{tool}.cached_tokens"] = Inc(int(usage.get("cached_tokens", 0) or 0))
    elif tool in ("image", "imagen"):
        updates[f"by_tool.{tool}.images"] = Inc(int(usage.get("images", 0) or 0))
    elif tool == "tts":
        updates[f"by_tool.{tool}.tts_chars"] = Inc(int(usage.get("tts_chars", 0) or 0))
    elif tool == "veo":
        updates[f"by_tool.{tool}.video_seconds"] = Inc(float(usage.get("video_seconds", 0) or 0))

    return updates


# ── Main entry point ────────────────────────────────────────────────────────

def record_usage(uid: Optional[str], project_id: Optional[str], tool: str,
                 model: str, usage: dict, retries: int = 0,
                 status: str = "ok", description: str = "",
                 op_name: Optional[str] = None,
                 cost_override: Optional[float] = None) -> None:
    """Log one billable call to Firestore. Fire-and-forget — never raises to caller.

    ``cost_override`` is used by Veo refund events to write a negative cost
    without re-running the pricing math.
    """
    if not uid:
        # CLI / unauthenticated path — skip tracking so we don't pollute prod data.
        return

    cost, version, is_fallback = (None, None, False)
    if cost_override is not None:
        cost, version = float(cost_override), pricing.get_pricing_version()
    else:
        try:
            cost, version, is_fallback = get_cost(tool, model, usage or {})
        except Exception as e:
            print(f"[cost_tracker] get_cost failed ({tool}/{model}): {e}")
            return

    effective_status = status
    if is_fallback and status == "ok":
        effective_status = "fallback"

    event = {
        "day": _today_utc(),
        "project_id": project_id,
        "tool": tool,
        "model": model,
        "status": effective_status,
        "retries": int(retries or 0),
        "usage": {k: v for k, v in (usage or {}).items() if v is not None},
        "cost_usd": cost,
        "pricing_version": version,
        "description": description or "",
        "op_name": op_name,
    }

    # Submit async so we don't add Firestore latency to the request path.
    try:
        with _executor_lock:
            _executor.submit(_commit_event, uid, event)
    except Exception as e:
        print(f"[cost_tracker] submit failed: {e}")


def _commit_event(uid: str, event: dict) -> None:
    """Background worker: actually writes the event + rollup to Firestore."""
    db = _get_db()
    if db is None:
        return
    try:
        from firebase_admin import firestore as _fs

        # Add server timestamp now (inside the worker) so clock drift on the
        # submit thread doesn't matter.
        event_to_write = dict(event)
        event_to_write["ts"] = _fs.SERVER_TIMESTAMP

        day = event["day"]
        events_ref = db.collection("users").document(uid).collection("cost_events").document()
        rollup_ref = db.collection("users").document(uid).collection("cost_rollups").document(day)

        updates = _rollup_updates(
            day=day,
            tool=event["tool"],
            model=event["model"],
            project_id=event.get("project_id"),
            usage=event.get("usage", {}),
            cost=event.get("cost_usd", 0.0),
        )

        batch = db.batch()
        batch.set(events_ref, event_to_write)
        batch.set(rollup_ref, updates, merge=True)
        batch.commit()
    except Exception as e:
        # Never raise into the caller — we'd rather lose one event than break
        # the user-facing generation flow.
        print(f"[cost_tracker] commit failed for uid={uid}: {e}")
        traceback.print_exc()


# ── Helpers for each call-site type ─────────────────────────────────────────

def _extract_token_usage(response) -> dict:
    """Pull token counts off a google-genai response's usage_metadata, if present."""
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return {"in_tokens": 0, "out_tokens": 0, "cached_tokens": 0}
    return {
        "in_tokens": int(getattr(meta, "prompt_token_count", 0) or 0),
        "out_tokens": int(getattr(meta, "candidates_token_count", 0) or 0),
        "cached_tokens": int(getattr(meta, "cached_content_token_count", 0) or 0),
    }


def _count_images_in_response(response) -> int:
    """Count image parts in a gemini-native image-generation response."""
    try:
        parts = response.candidates[0].content.parts or []
    except Exception:
        return 0
    count = 0
    for part in parts:
        inline = getattr(part, "inline_data", None)
        if inline and getattr(inline, "mime_type", "").startswith("image/"):
            count += 1
    return count


def track_text(uid, project_id, model, response, retries=0,
               description="", status="ok") -> None:
    """Emit a cost event from a text/multimodal Gemini response."""
    usage = _extract_token_usage(response)
    record_usage(
        uid=uid, project_id=project_id, tool="text", model=model,
        usage=usage, retries=retries, status=status, description=description,
    )


def track_image(uid, project_id, model, response, retries=0,
                description="", status="ok") -> None:
    """Emit an event for a Gemini-native image generation (per-image billing)."""
    images = _count_images_in_response(response)
    if images == 0 and status == "ok":
        # Model returned no image — don't bill the user for a failed call.
        return
    record_usage(
        uid=uid, project_id=project_id, tool="image", model=model,
        usage={"images": images}, retries=retries, status=status,
        description=description,
    )


def track_imagen(uid, project_id, model, response, retries=0,
                 description="", status="ok") -> None:
    """Emit an event for an Imagen generate_images() call."""
    try:
        images = len(response.generated_images or [])
    except Exception:
        images = 0
    if images == 0 and status == "ok":
        return
    record_usage(
        uid=uid, project_id=project_id, tool="imagen", model=model,
        usage={"images": images}, retries=retries, status=status,
        description=description,
    )


def track_tts(uid, project_id, model, char_count, retries=0,
              description="", status="ok") -> None:
    record_usage(
        uid=uid, project_id=project_id, tool="tts", model=model,
        usage={"tts_chars": int(char_count or 0)}, retries=retries,
        status=status, description=description,
    )


def track_veo(uid, project_id, model, duration_seconds, retries=0,
              description="", status="provisional", op_name=None) -> None:
    """Bill a Veo video at submit time. Status defaults to 'provisional' so we
    can later emit a refund if the operation fails."""
    record_usage(
        uid=uid, project_id=project_id, tool="veo", model=model,
        usage={"video_seconds": float(duration_seconds or 0)},
        retries=retries, status=status, description=description,
        op_name=op_name,
    )


def track_veo_refund(uid, project_id, model, duration_seconds,
                     description="", op_name=None) -> None:
    """Emit a negative-cost event when a Veo operation fails after being billed."""
    cost, _version, _is_fallback = get_cost("veo", model,
                                            {"video_seconds": duration_seconds})
    record_usage(
        uid=uid, project_id=project_id, tool="veo", model=model,
        usage={"video_seconds": -float(duration_seconds or 0)},
        retries=0, status="refund", description=description,
        op_name=op_name,
        cost_override=-abs(cost),
    )


def _shutdown_executor_for_tests() -> None:
    """Test-only: drain the thread pool so assertions see completed writes."""
    global _executor
    with _executor_lock:
        _executor.shutdown(wait=True)
        _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cost-tracker")
