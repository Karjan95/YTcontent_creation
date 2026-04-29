"""Unit tests for execution/cost_tracker.py.

Firestore is mocked. We verify:
- cost math per tool
- fallback flagging
- event+rollup batch writes
- no-op when uid is None
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def tracker(monkeypatch):
    import pricing
    import cost_tracker

    pricing.reset_cache_for_tests()
    monkeypatch.setattr(
        pricing,
        "_fetch_from_firestore",
        lambda: {
            "version": "test-v1",
            "text_models": {
                "gemini-3-flash-preview": {
                    "in_per_1m": 0.30, "out_per_1m": 2.50, "cached_in_per_1m": 0.075,
                },
            },
            "image_models": {
                "gemini-3-pro-image-preview": {"per_image": 0.04},
            },
            "tts_models": {
                "gemini-2.5-flash-preview-tts": {"per_1k_chars": 0.015},
            },
            "video_models": {
                "veo-3.1-generate-preview": {
                    "per_second": 0.40,
                    "by_resolution": {"720p": 0.40, "1080p": 0.40, "4k": 0.60},
                },
                "veo-3.1-lite-generate-preview": {
                    "per_second": 0.05,
                    "by_resolution": {"720p": 0.05, "1080p": 0.08},  # no 4k
                },
            },
            "fallback": {
                "text": {"in_per_1m": 1.25, "out_per_1m": 10.00, "cached_in_per_1m": 0.31},
                "image": {"per_image": 0.04},
                "imagen": {"per_image": 0.04},
                "tts": {"per_1k_chars": 0.015},
                "veo": {"per_second": 0.40},
            },
        },
    )
    return cost_tracker


# ── Cost math ───────────────────────────────────────────────────────────────

def test_get_cost_text_exact_math(tracker):
    cost, version, is_fallback = tracker.get_cost(
        "text", "gemini-3-flash-preview",
        {"in_tokens": 1000, "out_tokens": 500, "cached_tokens": 200},
    )
    # billable_in = 1000-200 = 800 at 0.30/1M = 0.00024
    # cached       = 200 at 0.075/1M          = 0.000015
    # out          = 500 at 2.50/1M           = 0.00125
    # total        = 0.001505
    assert is_fallback is False
    assert version == "test-v1"
    assert cost == pytest.approx(0.001505, rel=1e-4)


def test_get_cost_veo(tracker):
    cost, _v, _f = tracker.get_cost("veo", "veo-3.1-generate-preview", {"video_seconds": 6})
    assert cost == pytest.approx(2.40)


def test_get_cost_veo_resolution_aware(tracker):
    # 4k bills at the higher per-second rate
    cost_4k, _, _ = tracker.get_cost(
        "veo", "veo-3.1-generate-preview",
        {"video_seconds": 6, "resolution": "4k"},
    )
    assert cost_4k == pytest.approx(0.60 * 6)

    # case-insensitive
    cost_4k_upper, _, _ = tracker.get_cost(
        "veo", "veo-3.1-generate-preview",
        {"video_seconds": 6, "resolution": "4K"},
    )
    assert cost_4k_upper == pytest.approx(0.60 * 6)

    # 1080p on Lite (different rate from 720p baseline)
    cost_lite_1080, _, _ = tracker.get_cost(
        "veo", "veo-3.1-lite-generate-preview",
        {"video_seconds": 6, "resolution": "1080p"},
    )
    assert cost_lite_1080 == pytest.approx(0.08 * 6)

    # Unknown resolution falls back to per_second baseline
    cost_unknown, _, _ = tracker.get_cost(
        "veo", "veo-3.1-generate-preview",
        {"video_seconds": 6, "resolution": "8k"},
    )
    assert cost_unknown == pytest.approx(0.40 * 6)

    # 4k on Lite (not in by_resolution) falls back to per_second baseline
    cost_lite_4k, _, _ = tracker.get_cost(
        "veo", "veo-3.1-lite-generate-preview",
        {"video_seconds": 6, "resolution": "4k"},
    )
    assert cost_lite_4k == pytest.approx(0.05 * 6)


def test_get_cost_image(tracker):
    cost, _v, _f = tracker.get_cost("image", "gemini-3-pro-image-preview", {"images": 2})
    assert cost == pytest.approx(0.08)


def test_get_cost_tts(tracker):
    cost, _v, _f = tracker.get_cost("tts", "gemini-2.5-flash-preview-tts",
                                    {"tts_chars": 2000})
    # 2000 chars at 0.015 / 1000 = 0.03
    assert cost == pytest.approx(0.03)


def test_fallback_flags_status(tracker):
    cost, _v, is_fallback = tracker.get_cost(
        "text", "totally-unknown-model",
        {"in_tokens": 1000, "out_tokens": 0, "cached_tokens": 0},
    )
    assert is_fallback is True
    # falls back to 1.25/1M for input
    assert cost == pytest.approx(0.00125, rel=1e-4)


# ── record_usage path ───────────────────────────────────────────────────────

def test_record_usage_writes_event_and_rollup(tracker, monkeypatch):
    fake_db = MagicMock()
    fake_batch = MagicMock()
    fake_db.batch.return_value = fake_batch
    # Simulate the .collection().document()... chain that record_usage uses.
    fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value = "events_ref"
    fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value = "rollup_ref"
    # The two distinct refs are built with separate chains — use side_effect to distinguish.
    events_ref = MagicMock(name="events_ref")
    rollup_ref = MagicMock(name="rollup_ref")

    def _collection_side(name):
        assert name == "users"
        user_coll = MagicMock()

        def _doc_side(uid):
            assert uid == "u1"
            user_doc = MagicMock()

            def _sub_side(subname):
                sub = MagicMock()
                if subname == "cost_events":
                    sub.document.return_value = events_ref
                elif subname == "cost_rollups":
                    sub.document.return_value = rollup_ref
                return sub

            user_doc.collection.side_effect = _sub_side
            return user_doc

        user_coll.document.side_effect = _doc_side
        return user_coll

    fake_db.collection.side_effect = _collection_side

    monkeypatch.setattr(tracker, "_get_db", lambda: fake_db)
    # Run synchronously so assertions are simple.
    monkeypatch.setattr(tracker._executor, "submit",
                        lambda fn, *args, **kwargs: fn(*args, **kwargs) or MagicMock())

    tracker.record_usage(
        uid="u1", project_id="p1", tool="text",
        model="gemini-3-flash-preview",
        usage={"in_tokens": 1000, "out_tokens": 500, "cached_tokens": 0},
        retries=1, status="ok", description="unit-test",
    )

    assert fake_batch.set.call_count == 2
    # First set is the event
    first_call_args, first_call_kwargs = fake_batch.set.call_args_list[0]
    assert first_call_args[0] is events_ref
    event_payload = first_call_args[1]
    assert event_payload["tool"] == "text"
    assert event_payload["retries"] == 1
    assert event_payload["description"] == "unit-test"
    assert event_payload["usage"] == {"in_tokens": 1000, "out_tokens": 500, "cached_tokens": 0}

    # Second set is the rollup (with merge=True)
    second_call_args, second_call_kwargs = fake_batch.set.call_args_list[1]
    assert second_call_args[0] is rollup_ref
    assert second_call_kwargs.get("merge") is True
    rollup_updates = second_call_args[1]
    # Increments contain a .value — we just check the dot-paths are there.
    assert "total_usd" in rollup_updates
    assert "by_tool.text.calls" in rollup_updates
    assert "by_tool.text.cost_usd" in rollup_updates
    assert "by_project.p1.calls" in rollup_updates
    fake_batch.commit.assert_called_once()


def test_record_usage_noop_when_uid_none(tracker, monkeypatch):
    fake_db = MagicMock()
    monkeypatch.setattr(tracker, "_get_db", lambda: fake_db)
    submitted = []
    monkeypatch.setattr(tracker._executor, "submit",
                        lambda fn, *args, **kwargs: submitted.append((fn, args)) or MagicMock())

    tracker.record_usage(
        uid=None, project_id="p1", tool="text",
        model="gemini-3-flash-preview",
        usage={"in_tokens": 10, "out_tokens": 0, "cached_tokens": 0},
    )

    assert submitted == []
    fake_db.batch.assert_not_called()


# ── helpers (_extract_token_usage, _count_images_in_response) ───────────────

def test_extract_token_usage_from_response(tracker):
    resp = SimpleNamespace(
        usage_metadata=SimpleNamespace(
            prompt_token_count=500,
            candidates_token_count=200,
            cached_content_token_count=50,
        ),
    )
    usage = tracker._extract_token_usage(resp)
    assert usage == {"in_tokens": 500, "out_tokens": 200, "cached_tokens": 50}


def test_extract_token_usage_missing(tracker):
    resp = SimpleNamespace(usage_metadata=None)
    usage = tracker._extract_token_usage(resp)
    assert usage == {"in_tokens": 0, "out_tokens": 0, "cached_tokens": 0}


def test_count_images_in_response(tracker):
    parts = [
        SimpleNamespace(inline_data=SimpleNamespace(mime_type="image/png")),
        SimpleNamespace(inline_data=SimpleNamespace(mime_type="text/plain")),
        SimpleNamespace(inline_data=SimpleNamespace(mime_type="image/jpeg")),
    ]
    resp = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=parts))])
    assert tracker._count_images_in_response(resp) == 2


# ── Veo refund ──────────────────────────────────────────────────────────────

def test_veo_refund_writes_negative_cost(tracker, monkeypatch):
    submitted = []

    def fake_submit(fn, uid, event):
        submitted.append((uid, event))

    monkeypatch.setattr(tracker._executor, "submit",
                        lambda fn, *args, **kwargs: fake_submit(fn, *args) or MagicMock())

    tracker.track_veo_refund(
        uid="u1", project_id="p1", model="veo-3.1-generate-preview",
        duration_seconds=6, description="veo-failed", op_name="op-abc",
    )

    assert len(submitted) == 1
    _uid, event = submitted[0]
    assert event["status"] == "refund"
    assert event["cost_usd"] == pytest.approx(-2.40)  # 6s * 0.40 negated
    assert event["op_name"] == "op-abc"


def test_veo_refund_resolution_aware(tracker, monkeypatch):
    submitted = []

    def fake_submit(fn, uid, event):
        submitted.append((uid, event))

    monkeypatch.setattr(tracker._executor, "submit",
                        lambda fn, *args, **kwargs: fake_submit(fn, *args) or MagicMock())

    tracker.track_veo_refund(
        uid="u1", project_id="p1", model="veo-3.1-generate-preview",
        duration_seconds=6, description="veo-failed-4k", op_name="op-xyz",
        resolution="4k",
    )

    assert len(submitted) == 1
    _uid, event = submitted[0]
    assert event["cost_usd"] == pytest.approx(-3.60)  # 6s * 0.60 (4k rate) negated
    assert event["usage"]["resolution"] == "4k"
    assert event["usage"]["video_seconds"] == pytest.approx(-6.0)
