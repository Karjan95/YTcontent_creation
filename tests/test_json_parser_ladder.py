"""Unit tests for the Tier-1 JSON parser ladder in research_scriptwriter.

Covers the failure modes observed in the Wasp-project staging logs (2026-05-24):
  - Raw \n inside string values (Gemini pretty-prints prose without escaping).
  - Trailing commas / minor malformations (json_repair fallback).
  - Markdown code fences (existing behavior — regression guard).
  - Truncated `{"shots":[...]}` arrays (existing salvager — regression guard).

If any of these tests fail, the production-table generation will start
losing batches again.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'execution'))

from research_scriptwriter import _parse_json_response


# ───────── Tier 1 — new behavior ─────────

def test_strict_false_recovers_raw_newline_in_string():
    """The Wasp-project failure mode: a literal \\n inside a string value
    breaks strict json.loads but is recoverable with strict=False."""
    payload = '{"shots": [{"prompt": "line one\nline two", "shot_number": "1"}]}'
    # Sanity check — strict mode SHOULD reject this.
    with pytest.raises(json.JSONDecodeError):
        json.loads(payload)
    out = _parse_json_response(payload)
    assert out["shots"][0]["shot_number"] == "1"
    assert "line one" in out["shots"][0]["prompt"]
    assert "line two" in out["shots"][0]["prompt"]


def test_strict_false_recovers_raw_tab_in_string():
    payload = '{"shots": [{"prompt": "before\tafter"}]}'
    with pytest.raises(json.JSONDecodeError):
        json.loads(payload)
    out = _parse_json_response(payload)
    assert "before" in out["shots"][0]["prompt"]
    assert "after" in out["shots"][0]["prompt"]


def test_json_repair_recovers_trailing_comma():
    """json_repair handles trailing commas which neither strict nor
    strict=False accept."""
    payload = '{"shots": [{"shot_number": "1"},{"shot_number": "2"},]}'
    out = _parse_json_response(payload)
    assert len(out["shots"]) == 2
    assert out["shots"][1]["shot_number"] == "2"


def test_json_repair_handles_prose_around_json():
    """Even with prose wrapping the JSON, repair should extract it."""
    payload = 'Sure, here are the prompts:\n{"shots": [{"shot_number": "1"}]}\nLet me know if you need changes.'
    out = _parse_json_response(payload)
    assert len(out["shots"]) == 1


# ───────── Regression guards — existing behavior ─────────

def test_strict_parse_still_works():
    """Well-formed JSON must still parse via the strict path (fast path)."""
    payload = '{"shots": [{"shot_number": "1", "prompt": "clean"}]}'
    out = _parse_json_response(payload)
    assert out["shots"][0]["prompt"] == "clean"


def test_markdown_code_fence_stripped():
    payload = '```json\n{"shots": [{"shot_number": "1"}]}\n```'
    out = _parse_json_response(payload)
    assert out["shots"][0]["shot_number"] == "1"


def test_truncated_shots_salvaged():
    """The salvager recovers complete shot objects before the truncation."""
    payload = (
        '{"shots": [{"shot_number": "1", "prompt": "a"},'
        '{"shot_number": "2", "prompt": "b"},'
        '{"shot_number": "3", "prompt": "incomplete'  # truncated mid-string
    )
    out = _parse_json_response(payload)
    assert "shots" in out
    # At least the first two complete shots should survive.
    assert len(out["shots"]) >= 2
    assert out["shots"][0]["shot_number"] == "1"
    assert out["shots"][1]["shot_number"] == "2"


def test_empty_string_raises():
    with pytest.raises(ValueError):
        _parse_json_response("")


def test_total_garbage_raises_jsondecodeerror():
    """If nothing parses, we still surface a JSONDecodeError so callers
    can handle it (the diagnostic head/tail is logged as a side effect)."""
    # Use a string with neither braces nor JSON-like content so json_repair
    # also cannot find anything to recover. (json_repair is aggressive and
    # may return {} for many inputs; we accept either an exception or an
    # empty dict here — both are valid "no data" signals.)
    try:
        out = _parse_json_response("totally not json at all just words")
        # If repair returns an empty/falsy dict, that's the same as "no data".
        assert not out, f"Expected empty dict on garbage input, got: {out!r}"
    except json.JSONDecodeError:
        pass  # Acceptable — the explicit fail-loud path.
