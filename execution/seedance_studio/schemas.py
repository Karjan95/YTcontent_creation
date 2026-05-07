"""Schema constants and validators for seedance_production_data."""

from datetime import datetime, timezone
import uuid

SCHEMA_VERSION = 1

# Per-sequence status enum
STATUS_NOT_STARTED = "not_started"
STATUS_SEQUENCED = "sequenced"
STATUS_DESIGNED = "designed_pending_grid"
STATUS_GRID_READY = "grid_ready"
STATUS_PROMPT_READY = "prompt_ready"
STATUS_ANIMATING = "animating"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"

VALID_GRID_LAYOUTS = ("2x2", "2x3", "3x3")
VALID_ASPECT_RATIOS = ("16:9", "9:16", "1:1")
VALID_SHOT_COUNTS = (3, 4, 6, 9)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def new_sequence_id():
    return f"seq_{uuid.uuid4().hex[:8]}"


def empty_seedance_data(default_aspect_ratio="16:9"):
    """Initial shape for a project's seedance_production_data field."""
    return {
        "version": SCHEMA_VERSION,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "status": STATUS_NOT_STARTED,
        "global": {
            "default_aspect_ratio": default_aspect_ratio,
        },
        "sequences": [],
    }


def new_sequence(prompt, grid_url, char_ref_urls, aspect_ratio="16:9", duration_sec=15, title=None):
    """Build a sequence dict for M1 (manual prompt path)."""
    return {
        "id": new_sequence_id(),
        "title": title or "Untitled sequence",
        "duration_sec": int(duration_sec),
        "aspect_ratio": aspect_ratio,
        "grid": {
            "image_url": grid_url,
            "generated_at": now_iso(),
        },
        "character_ref_urls": list(char_ref_urls or []),
        "seedance_prompt": prompt,
        "status": STATUS_PROMPT_READY,
        "created_at": now_iso(),
    }
