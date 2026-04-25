"""Tests for the Narrative Spine extractor and formatter.

The spine is an additive ranked outline derived from a research dossier.
Downstream prompts (script gen, beat regen, production) consume it via
[k1], [k2]… ids. These tests cover Step 1 of the rollout — extractor + storage.
"""

import json
from unittest.mock import patch

import pytest


VALID_SPINE_JSON = json.dumps({
    "version": 1,
    "topic": "How nuclear reactors work",
    "key_claims": [
        {"id": "k1", "text": "Fission splits heavy nuclei.", "importance": "primary", "source_ids": ["s1"]},
        {"id": "k2", "text": "Heat boils water into steam.", "importance": "supporting", "source_ids": ["s1", "s2"]},
        {"id": "k3", "text": "Steam spins turbines.", "importance": "primary", "source_ids": ["s2"]},
    ],
    "logical_flow": ["k1", "k2", "k3"],
    "source_map": {
        "s1": {"url": "https://example.com/fission", "title": "Fission 101", "publisher": "", "quote": ""},
        "s2": {"url": "https://example.com/turbines", "title": "Turbines", "publisher": "", "quote": ""},
    },
})


# ── extract_narrative_spine ────────────────────────────────────────────────

def test_extract_narrative_spine_happy_path():
    import research_scriptwriter as rsw
    with patch.object(rsw, 'generate_content', return_value=VALID_SPINE_JSON):
        result = rsw.extract_narrative_spine(
            topic="How nuclear reactors work",
            research_dossier="# Dossier\nFission, steam, turbines.",
            api_key="fake",
        )
    assert result.get("success") is True
    spine = result["spine"]
    assert len(spine["key_claims"]) == 3
    # logical_flow ⊆ key_claim ids
    claim_ids = {c["id"] for c in spine["key_claims"]}
    assert all(k in claim_ids for k in spine["logical_flow"])
    # source_map keys ⊆ union of source_ids actually referenced
    used = {s for c in spine["key_claims"] for s in c["source_ids"]}
    assert set(spine["source_map"].keys()) == used


def test_extract_narrative_spine_invalid_json_returns_error():
    import research_scriptwriter as rsw
    with patch.object(rsw, 'generate_content', return_value="this is not json at all"):
        result = rsw.extract_narrative_spine(
            topic="X",
            research_dossier="some dossier",
            api_key="fake",
        )
    assert "error" in result
    assert result["spine"] is None


def test_extract_narrative_spine_extractor_failure_returns_error():
    import research_scriptwriter as rsw
    with patch.object(rsw, 'generate_content', return_value="Error: boom"):
        result = rsw.extract_narrative_spine(
            topic="X", research_dossier="dossier", api_key="fake",
        )
    assert "error" in result
    assert result["spine"] is None


def test_extract_narrative_spine_empty_dossier_short_circuits():
    import research_scriptwriter as rsw
    # generate_content must NOT be called when dossier is empty
    with patch.object(rsw, 'generate_content') as mock_gc:
        result = rsw.extract_narrative_spine(
            topic="X", research_dossier="   ", api_key="fake",
        )
    assert result["spine"] is None
    assert "error" in result
    mock_gc.assert_not_called()


def test_extract_narrative_spine_dangling_source_id_dropped():
    import research_scriptwriter as rsw
    bad_json = json.dumps({
        "version": 1,
        "key_claims": [
            {"id": "k1", "text": "Real claim", "importance": "primary", "source_ids": ["s1", "s99"]},
        ],
        "logical_flow": ["k1"],
        "source_map": {
            "s1": {"url": "https://example.com", "title": "Real", "publisher": "", "quote": ""},
        },
    })
    with patch.object(rsw, 'generate_content', return_value=bad_json):
        result = rsw.extract_narrative_spine(
            topic="X", research_dossier="dossier", api_key="fake",
        )
    assert result.get("success") is True
    spine = result["spine"]
    # The dangling s99 must be stripped
    assert spine["key_claims"][0]["source_ids"] == ["s1"]
    assert "s99" not in spine["source_map"]


def test_extract_narrative_spine_dangling_flow_id_dropped():
    import research_scriptwriter as rsw
    bad_json = json.dumps({
        "version": 1,
        "key_claims": [
            {"id": "k1", "text": "Claim one", "importance": "primary", "source_ids": []},
        ],
        # flow references a claim that doesn't exist
        "logical_flow": ["k1", "k99"],
        "source_map": {},
    })
    with patch.object(rsw, 'generate_content', return_value=bad_json):
        result = rsw.extract_narrative_spine(
            topic="X", research_dossier="dossier", api_key="fake",
        )
    assert result.get("success") is True
    assert result["spine"]["logical_flow"] == ["k1"]


def test_extract_narrative_spine_uses_structured_source_ids():
    """When `structured` is supplied, its sources should bootstrap the spine source_map."""
    import research_scriptwriter as rsw
    structured = {
        "claims": [{"id": "c1", "text": "x", "source_ids": ["s1"]}],
        "sources": [
            {"id": "s1", "url": "https://structured.example", "title": "From structured", "publisher": "Pub", "quote": ""},
        ],
    }
    # The model returns claims that cite s1 but DOESN'T include the source_map
    # (so the bootstrap path must populate it from `structured`).
    json_without_source_map = json.dumps({
        "version": 1,
        "key_claims": [
            {"id": "k1", "text": "Spine claim", "importance": "primary", "source_ids": ["s1"]},
        ],
        "logical_flow": ["k1"],
        "source_map": {},
    })
    with patch.object(rsw, 'generate_content', return_value=json_without_source_map):
        result = rsw.extract_narrative_spine(
            topic="X", research_dossier="dossier",
            structured=structured, api_key="fake",
        )
    assert result.get("success") is True
    spine = result["spine"]
    assert "s1" in spine["source_map"]
    assert spine["source_map"]["s1"]["url"] == "https://structured.example"


# ── _format_spine_block ────────────────────────────────────────────────────

def test_format_spine_block_empty_returns_empty_string():
    from research_templates import _format_spine_block
    assert _format_spine_block(None) == ""
    assert _format_spine_block({}) == ""
    assert _format_spine_block({"key_claims": []}) == ""


def test_format_spine_block_renders_claims_and_flow():
    from research_templates import _format_spine_block
    spine = json.loads(VALID_SPINE_JSON)
    block = _format_spine_block(spine)
    assert "NARRATIVE SPINE" in block
    assert "Logical flow: k1 → k2 → k3" in block
    assert "[k1] (primary) Fission" in block
    assert "[s1]" in block and "[s2]" in block
    assert "https://example.com/fission" in block


# ── build_spine_extraction_prompt ─────────────────────────────────────────

def test_build_spine_extraction_prompt_contains_dossier_and_schema():
    from research_templates import build_spine_extraction_prompt
    prompt = build_spine_extraction_prompt(
        topic="Quantum computing",
        research_dossier="### Q1\nQuantum bits use superposition.",
    )
    assert "Quantum computing" in prompt
    assert "Quantum bits use superposition." in prompt
    assert '"key_claims"' in prompt
    assert '"logical_flow"' in prompt
    assert '"source_map"' in prompt


def test_build_spine_extraction_prompt_includes_structured_block():
    from research_templates import build_spine_extraction_prompt
    structured = {
        "claims": [{"id": "c1", "text": "Existing claim", "source_ids": ["s1"]}],
        "sources": [{"id": "s1", "url": "https://x", "title": "S1", "publisher": "", "quote": ""}],
    }
    prompt = build_spine_extraction_prompt(
        topic="X", research_dossier="dossier text", structured=structured,
    )
    # The shared CLAIMS/SOURCES helper must inject existing s1 so the model reuses it.
    assert "[c1]" in prompt
    assert "[s1]" in prompt


# ── _validate_spine_edit (server-side PUT validator) ──────────────────────

def test_validate_spine_edit_accepts_clean_spine():
    from server import _validate_spine_edit
    spine = json.loads(VALID_SPINE_JSON)
    cleaned, err = _validate_spine_edit(spine)
    assert err is None
    assert cleaned["edited_by_user"] is True


def test_validate_spine_edit_rejects_duplicate_ids():
    from server import _validate_spine_edit
    spine = {
        "key_claims": [
            {"id": "k1", "text": "a", "importance": "primary", "source_ids": []},
            {"id": "k1", "text": "b", "importance": "primary", "source_ids": []},
        ],
        "logical_flow": ["k1"],
        "source_map": {},
    }
    cleaned, err = _validate_spine_edit(spine)
    assert cleaned is None
    assert "duplicate" in err.lower()


def test_validate_spine_edit_rejects_dangling_flow():
    from server import _validate_spine_edit
    spine = {
        "key_claims": [{"id": "k1", "text": "a", "importance": "primary", "source_ids": []}],
        "logical_flow": ["k1", "k_ghost"],
        "source_map": {},
    }
    cleaned, err = _validate_spine_edit(spine)
    assert cleaned is None
    assert "logical_flow" in err


def test_validate_spine_edit_rejects_dangling_source():
    from server import _validate_spine_edit
    spine = {
        "key_claims": [
            {"id": "k1", "text": "a", "importance": "primary", "source_ids": ["s_ghost"]},
        ],
        "logical_flow": ["k1"],
        "source_map": {},
    }
    cleaned, err = _validate_spine_edit(spine)
    assert cleaned is None
    assert "unknown source" in err
