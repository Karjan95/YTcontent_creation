"""Live-refreshable pricing table for Gemini API cost tracking.

The actual usage numbers (tokens, image counts, video seconds, TTS chars) come live
from the Gemini API response. This module converts those units into USD using rates
stored in the Firestore doc ``config/gemini_pricing``.

A Firestore-backed rate table (rather than Python constants) lets us adjust to
Google-side price changes via a single doc edit — no redeploy. Rates are cached
in memory with a short TTL so the common path is a dict lookup.

Fallback: if Firestore is unreachable or the doc is missing, _DEFAULT_PRICING
is used so tests and the CLI never crash.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

# Price units:
#   text_models.*.in_per_1m, out_per_1m, cached_in_per_1m  → USD per 1,000,000 tokens
#   image_models.*.per_image                                → USD per image
#   tts_models.*.per_1k_chars                               → USD per 1,000 characters
#   video_models.*.per_second                               → USD per second of generated video
#
# Rates below are Google's published USD rates as of **April 2026**
# (sourced from ai.google.dev/pricing + OpenRouter provider pages + Google blog).
# Override anything via the Firestore doc config/gemini_pricing to reflect
# future price changes without a redeploy. Every cost event stamps the
# pricing_version so retroactive audits can reconstruct the rate used.
#
# Caveats:
#  - Gemini 3 Pro / 3.1 Pro have context-tiered pricing ($2.00/$12.00 for
#    ≤200K context, $4.00/$18.00 above). The tracker charges the ≤200K tier;
#    bulk prompts over 200K context will under-bill. Re-check if you start
#    exceeding ~200K prompt tokens regularly.
#  - Gemini 3 Pro Image bills per-token (1120 tokens/image at 1K-2K, 2000
#    tokens/image at 4K). We approximate as a flat $0.134/image (2K tier).
#    For 4K generation that becomes an underbill — set to 0.24 in Firestore
#    if you move to 4K.
#  - Gemini 2.5 Flash TTS is priced by audio-output tokens (not input chars).
#    Our tracker measures input characters, so the per_1k_chars rate is a
#    rough equivalent based on typical 1 char ≈ 4 output tokens.
_DEFAULT_PRICING = {
    "version": "2026-04-defaults",
    "text_models": {
        # Gemini 3 family
        "gemini-3-pro-preview": {
            "in_per_1m": 2.00, "out_per_1m": 12.00, "cached_in_per_1m": 0.50,
        },
        "gemini-3.1-pro-preview": {
            "in_per_1m": 2.00, "out_per_1m": 12.00, "cached_in_per_1m": 0.50,
        },
        "gemini-3-flash-preview": {
            "in_per_1m": 0.50, "out_per_1m": 3.00, "cached_in_per_1m": 0.05,
        },
        # Gemini 2.5 family
        "gemini-2.5-pro": {
            "in_per_1m": 1.25, "out_per_1m": 10.00, "cached_in_per_1m": 0.31,
        },
        "gemini-2.5-flash": {
            "in_per_1m": 0.30, "out_per_1m": 2.50, "cached_in_per_1m": 0.075,
        },
        # TTS model's text-token side is not separately billed by Google;
        # audio output is metered via tts_models below.
        "gemini-2.5-flash-preview-tts": {
            "in_per_1m": 0.00, "out_per_1m": 0.00, "cached_in_per_1m": 0.00,
        },
    },
    "image_models": {
        # Gemini 3 Pro Image — 2K tier. Override to 0.24 for 4K.
        "gemini-3-pro-image-preview": {"per_image": 0.134},
        # "Nano Banana" — 1290 output tokens × $30/1M = $0.039/image
        "gemini-2.5-flash-image": {"per_image": 0.039},
        # Imagen 4 family
        "imagen-4.0-generate-001": {"per_image": 0.04},
        "imagen-4.0-fast-generate-001": {"per_image": 0.02},
        "imagen-4.0-ultra-generate-001": {"per_image": 0.06},
    },
    "tts_models": {
        # Preview TTS: rough per-character conversion from output-token rate.
        "gemini-2.5-flash-preview-tts": {"per_1k_chars": 0.010},
    },
    "video_models": {
        # Veo 3.1 — rates effective after Google's April 7 2026 price drop.
        "veo-3.1-generate-preview": {"per_second": 0.40},
        "veo-3.1-fast-generate-preview": {"per_second": 0.10},
        "veo-3.1-lite-generate-preview": {"per_second": 0.05},
    },
    "fallback": {
        # Used when a call reports a model name we don't recognize. Set to
        # the most expensive sensible default so we over- rather than
        # under-bill — admins see the "fallback" status flag in events.
        "text": {"in_per_1m": 2.00, "out_per_1m": 12.00, "cached_in_per_1m": 0.50},
        "image": {"per_image": 0.04},
        "imagen": {"per_image": 0.04},
        "tts": {"per_1k_chars": 0.010},
        "veo": {"per_second": 0.40},
    },
}

_CACHE_TTL_SECONDS = 300
_cache: dict = {"doc": None, "expires_at": 0.0}
_lock = threading.Lock()


def _tool_collection_key(tool: str) -> str:
    """Map a ``tool`` identifier to its rate-dict collection."""
    if tool == "text":
        return "text_models"
    if tool in ("image", "imagen"):
        return "image_models"
    if tool == "tts":
        return "tts_models"
    if tool == "veo":
        return "video_models"
    return ""


def load_pricing(force: bool = False) -> dict:
    """Return the active pricing doc, refreshing the cache if expired.

    Args:
        force: If True, bypass the cache and re-fetch immediately.
    """
    now = time.time()
    with _lock:
        if (not force) and _cache["doc"] is not None and now < _cache["expires_at"]:
            return _cache["doc"]

        doc = _fetch_from_firestore()
        if doc is None:
            doc = _DEFAULT_PRICING

        _cache["doc"] = doc
        _cache["expires_at"] = now + _CACHE_TTL_SECONDS
        return doc


def _fetch_from_firestore() -> Optional[dict]:
    """Fetch ``config/gemini_pricing`` from Firestore. Returns None on any failure."""
    try:
        from firebase_admin import firestore
        db = firestore.client()
        snap = db.collection("config").document("gemini_pricing").get()
        if not snap.exists:
            return None
        data = snap.to_dict() or {}
        # Minimal shape validation — must at least have one of the model groups.
        if not any(k in data for k in ("text_models", "image_models", "tts_models", "video_models")):
            return None
        # Merge over defaults so missing groups still have fallback rates.
        merged = dict(_DEFAULT_PRICING)
        merged.update(data)
        # Preserve defaults.fallback if the admin didn't override it.
        if "fallback" not in data:
            merged["fallback"] = _DEFAULT_PRICING["fallback"]
        return merged
    except Exception as e:  # pragma: no cover — path only hit when Firestore is live
        print(f"[pricing] Firestore load failed, using defaults: {e}")
        return None


def get_rate(tool: str, model: str) -> tuple[dict, bool]:
    """Return (rate_dict, is_fallback) for a given tool+model.

    ``is_fallback`` is True when the caller should stamp ``status="fallback"``
    on the emitted cost event because no exact rate was found.
    """
    pricing = load_pricing()
    collection_key = _tool_collection_key(tool)

    if collection_key and model:
        collection = pricing.get(collection_key, {}) or {}
        rate = collection.get(model)
        if rate:
            return rate, False

    fallback = (pricing.get("fallback", {}) or {}).get(tool)
    if fallback:
        return fallback, True

    default_fallback = _DEFAULT_PRICING["fallback"].get(tool, {})
    return default_fallback, True


def get_pricing_version() -> str:
    """Stamp applied to each cost event so retroactive audits can reconstruct the rate."""
    return load_pricing().get("version", "default-seed")


def reset_cache_for_tests() -> None:
    """Test-only helper — wipe the module-level cache."""
    with _lock:
        _cache["doc"] = None
        _cache["expires_at"] = 0.0
