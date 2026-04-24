"""Instrumentation tests — exercise gemini_client.py and verify cost events are emitted.

The google-genai client is mocked so no network is required. We assert that
cost_tracker.record_usage() receives the correct tool / model / usage / retry
/ status / description for each call type.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest


@pytest.fixture
def gc_mocks(monkeypatch):
    """Expose gemini_client + a recording cost_tracker stub."""
    import pricing
    import cost_tracker
    import gemini_client as gc

    pricing.reset_cache_for_tests()

    captured_events = []

    def fake_record(uid, project_id, tool, model, usage,
                    retries=0, status="ok", description="",
                    op_name=None, cost_override=None):
        captured_events.append({
            "uid": uid, "project_id": project_id, "tool": tool,
            "model": model, "usage": usage, "retries": retries,
            "status": status, "description": description,
            "op_name": op_name, "cost_override": cost_override,
        })

    monkeypatch.setattr(cost_tracker, "record_usage", fake_record)

    # gemini_client imported cost_tracker into its own namespace at module load,
    # so we can patch the shared helpers too.
    # (Our helpers delegate to record_usage, which is now the fake.)
    return gc, captured_events


def _fake_text_response(prompt_tc=100, cand_tc=50, cached_tc=0, text="ok"):
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt_tc,
            candidates_token_count=cand_tc,
            cached_content_token_count=cached_tc,
        ),
    )


def _fake_image_response(n=1):
    parts = [
        SimpleNamespace(inline_data=SimpleNamespace(mime_type="image/png", data=b"x"))
        for _ in range(n)
    ]
    return SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=parts))],
        usage_metadata=SimpleNamespace(
            prompt_token_count=0, candidates_token_count=0, cached_content_token_count=0,
        ),
    )


def _fake_imagen_response(n=1):
    imgs = [
        SimpleNamespace(image=SimpleNamespace(image_bytes=b"fake-img-bytes"))
        for _ in range(n)
    ]
    return SimpleNamespace(generated_images=imgs)


# ── generate_content ────────────────────────────────────────────────────────

def test_generate_content_tracks_tokens(gc_mocks, monkeypatch):
    gc, events = gc_mocks

    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = _fake_text_response(
        prompt_tc=1000, cand_tc=500, cached_tc=200,
    )
    monkeypatch.setattr(gc, "get_client", lambda api_key=None: fake_client)

    result = gc.generate_content(
        "hello", model_name="gemini-3-flash-preview",
        api_key="k", uid="u1", project_id="p1",
        description="director",
    )

    assert result == "ok"
    assert len(events) == 1
    ev = events[0]
    assert ev["uid"] == "u1"
    assert ev["project_id"] == "p1"
    assert ev["tool"] == "text"
    assert ev["model"] == "gemini-3-flash-preview"
    assert ev["usage"] == {"in_tokens": 1000, "out_tokens": 500, "cached_tokens": 200}
    assert ev["retries"] == 0
    assert ev["status"] == "ok"
    assert ev["description"] == "director"


def test_generate_content_retries_counted(gc_mocks, monkeypatch):
    gc, events = gc_mocks

    attempts = {"n": 0}

    def flaky(model, contents, config):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("503 service unavailable")
        return _fake_text_response(prompt_tc=10, cand_tc=5)

    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = flaky
    monkeypatch.setattr(gc, "get_client", lambda api_key=None: fake_client)
    # Skip the real backoff sleep.
    monkeypatch.setattr(gc.time, "sleep", lambda *_a, **_k: None)

    gc.generate_content("hi", api_key="k", uid="u1", project_id="p1")

    assert len(events) == 1
    assert events[0]["retries"] == 2


def test_generate_content_noop_without_uid(gc_mocks, monkeypatch):
    gc, events = gc_mocks

    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = _fake_text_response()
    monkeypatch.setattr(gc, "get_client", lambda api_key=None: fake_client)

    gc.generate_content("hi", api_key="k")  # no uid

    # record_usage is still called, but downstream _commit skips when uid=None.
    # We only assert the call happened with uid=None.
    assert len(events) == 1
    assert events[0]["uid"] is None


# ── image generation ────────────────────────────────────────────────────────

def test_generate_scene_image_imagen_tracks_per_image(gc_mocks, monkeypatch):
    gc, events = gc_mocks

    fake_client = MagicMock()
    fake_client.models.generate_images.return_value = _fake_imagen_response(n=1)
    monkeypatch.setattr(gc, "get_client", lambda api_key=None: fake_client)

    # Patch file write to avoid disk I/O — the test only cares about tracking.
    monkeypatch.setattr("builtins.open", MagicMock())
    monkeypatch.setattr(gc.os, "makedirs", lambda *a, **k: None)

    gc.generate_scene_image(
        prompt="A cat", model_name="imagen-4.0-generate-001",
        scene_id="s1", api_key="k", uid="u1", project_id="p1",
    )

    assert len(events) == 1
    ev = events[0]
    assert ev["tool"] == "imagen"
    assert ev["model"] == "imagen-4.0-generate-001"
    assert ev["usage"]["images"] == 1
    assert ev["project_id"] == "p1"


def test_generate_scene_image_gemini_tracks_per_image(gc_mocks, monkeypatch):
    gc, events = gc_mocks

    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = _fake_image_response(n=1)
    monkeypatch.setattr(gc, "get_client", lambda api_key=None: fake_client)

    monkeypatch.setattr("builtins.open", MagicMock())
    monkeypatch.setattr(gc.os, "makedirs", lambda *a, **k: None)

    gc.generate_scene_image(
        prompt="A cat", model_name="gemini-3-pro-image-preview",
        scene_id="s1", api_key="k", uid="u1", project_id="p1",
    )

    assert len(events) == 1
    ev = events[0]
    assert ev["tool"] == "image"
    assert ev["model"] == "gemini-3-pro-image-preview"
    assert ev["usage"]["images"] == 1


# ── TTS ─────────────────────────────────────────────────────────────────────

def test_generate_tts_tracks_char_count(gc_mocks, monkeypatch):
    gc, events = gc_mocks

    # TTS response carries inline audio data; we just need the shape.
    resp = SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[
            SimpleNamespace(inline_data=SimpleNamespace(data=b"pcm"))
        ]))],
    )
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = resp
    monkeypatch.setattr(gc, "get_client", lambda api_key=None: fake_client)
    monkeypatch.setattr(gc.os, "makedirs", lambda *a, **k: None)
    # Skip the wave file write.
    class FakeWave:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def setnchannels(self, *_): pass
        def setsampwidth(self, *_): pass
        def setframerate(self, *_): pass
        def writeframes(self, *_): pass
    monkeypatch.setattr("wave.open", lambda *a, **k: FakeWave())

    gc.generate_tts(
        "hello world",  # 11 chars
        voice_name="kore", style_instructions="",
        api_key="k", uid="u1", project_id="p1",
    )

    assert len(events) == 1
    ev = events[0]
    assert ev["tool"] == "tts"
    assert ev["model"] == "gemini-2.5-flash-preview-tts"
    assert ev["usage"]["tts_chars"] == 11


# ── Veo submit-then-refund ──────────────────────────────────────────────────

def test_start_video_generation_bills_provisionally(gc_mocks, monkeypatch, tmp_path):
    gc, events = gc_mocks

    operation = SimpleNamespace(name="op-xyz", done=False, response=None)
    fake_client = MagicMock()
    fake_client.models.generate_videos.return_value = operation
    monkeypatch.setattr(gc, "get_client", lambda api_key=None: fake_client)

    img_path = tmp_path / "scene.png"
    img_path.write_bytes(b"fakebytes")

    result = gc.start_video_generation(
        image_path=str(img_path), prompt="animate",
        model_name="veo-3.1-generate-preview",
        duration=6, scene_id="scene_3",
        api_key="k", uid="u1", project_id="p1",
    )

    assert result["operation_name"] == "op-xyz"
    assert len(events) == 1
    ev = events[0]
    assert ev["tool"] == "veo"
    assert ev["status"] == "provisional"
    assert ev["usage"]["video_seconds"] == 6.0
    assert ev["op_name"] == "op-xyz"
    assert ev["project_id"] == "p1"


def test_poll_video_failure_emits_refund(gc_mocks, monkeypatch):
    gc, events = gc_mocks

    # Simulate: operation is already stored with billing context, poll returns
    # done=True but no videos (safety block).
    op = SimpleNamespace(name="op-xyz", done=True, response=None)
    gc._video_operations["op-xyz"] = {
        "operation": op,
        "uid": "u1",
        "project_id": "p1",
        "duration": 6,
        "model": "veo-3.1-generate-preview",
        "scene_id": "scene_3",
    }

    fake_client = MagicMock()
    fake_client.operations.get.return_value = op
    monkeypatch.setattr(gc, "get_client", lambda api_key=None: fake_client)

    result = gc.poll_video_generation("op-xyz", scene_id="scene_3", api_key="k")

    assert result["status"] == "failed"
    # Refund event has tool=veo, status=refund, cost_override set to negative
    refund_events = [e for e in events if e.get("status") == "refund"]
    assert len(refund_events) == 1
    assert refund_events[0]["tool"] == "veo"
    assert refund_events[0]["op_name"] == "op-xyz"
    assert refund_events[0]["cost_override"] is not None
    assert refund_events[0]["cost_override"] < 0
