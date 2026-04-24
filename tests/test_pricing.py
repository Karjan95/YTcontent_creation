"""Unit tests for execution/pricing.py.

These exercise the pure-logic paths (default fallback, cache TTL) and
don't require a live Firestore. Firestore access is monkeypatched.
"""

import time
import importlib
import pytest


@pytest.fixture
def pricing_module():
    import pricing
    pricing.reset_cache_for_tests()
    return pricing


def test_get_rate_text_model_known(pricing_module, monkeypatch):
    """A known text model returns its exact rate dict, not fallback."""
    monkeypatch.setattr(pricing_module, "_fetch_from_firestore", lambda: None)
    rate, is_fallback = pricing_module.get_rate("text", "gemini-3-flash-preview")
    assert is_fallback is False
    assert rate["in_per_1m"] == 0.30
    assert rate["out_per_1m"] == 2.50
    assert rate["cached_in_per_1m"] == 0.075


def test_get_rate_fallback_on_unknown_model(pricing_module, monkeypatch):
    monkeypatch.setattr(pricing_module, "_fetch_from_firestore", lambda: None)
    rate, is_fallback = pricing_module.get_rate("text", "totally-made-up-model")
    assert is_fallback is True
    assert "in_per_1m" in rate and "out_per_1m" in rate


def test_get_rate_image_known(pricing_module, monkeypatch):
    monkeypatch.setattr(pricing_module, "_fetch_from_firestore", lambda: None)
    rate, is_fallback = pricing_module.get_rate("image", "gemini-3-pro-image-preview")
    assert is_fallback is False
    assert rate["per_image"] == 0.039


def test_get_rate_imagen_known(pricing_module, monkeypatch):
    monkeypatch.setattr(pricing_module, "_fetch_from_firestore", lambda: None)
    rate, is_fallback = pricing_module.get_rate("imagen", "imagen-4.0-generate-001")
    assert is_fallback is False
    assert rate["per_image"] == 0.04


def test_get_rate_tts_known(pricing_module, monkeypatch):
    monkeypatch.setattr(pricing_module, "_fetch_from_firestore", lambda: None)
    rate, is_fallback = pricing_module.get_rate("tts", "gemini-2.5-flash-preview-tts")
    assert is_fallback is False
    assert rate["per_1k_chars"] == 0.015


def test_get_rate_veo_known(pricing_module, monkeypatch):
    monkeypatch.setattr(pricing_module, "_fetch_from_firestore", lambda: None)
    rate, is_fallback = pricing_module.get_rate("veo", "veo-3.1-generate-preview")
    assert is_fallback is False
    assert rate["per_second"] == 0.40


def test_cache_ttl_only_fetches_once(pricing_module, monkeypatch):
    """Two back-to-back get_rate() calls must only hit Firestore once."""
    call_count = {"n": 0}

    def fake_fetch():
        call_count["n"] += 1
        return {
            "version": "v-cached",
            "text_models": {"m": {"in_per_1m": 1, "out_per_1m": 2, "cached_in_per_1m": 0.1}},
        }

    monkeypatch.setattr(pricing_module, "_fetch_from_firestore", fake_fetch)
    pricing_module.get_rate("text", "m")
    pricing_module.get_rate("text", "m")
    assert call_count["n"] == 1


def test_cache_force_refresh(pricing_module, monkeypatch):
    call_count = {"n": 0}

    def fake_fetch():
        call_count["n"] += 1
        return {
            "version": f"v-{call_count['n']}",
            "text_models": {"m": {"in_per_1m": 1, "out_per_1m": 2, "cached_in_per_1m": 0.1}},
        }

    monkeypatch.setattr(pricing_module, "_fetch_from_firestore", fake_fetch)
    pricing_module.load_pricing()
    pricing_module.load_pricing(force=True)
    assert call_count["n"] == 2


def test_pricing_version_stamp(pricing_module, monkeypatch):
    monkeypatch.setattr(
        pricing_module,
        "_fetch_from_firestore",
        lambda: {"version": "2026-04-24-v1", "text_models": {}},
    )
    assert pricing_module.get_pricing_version() == "2026-04-24-v1"
