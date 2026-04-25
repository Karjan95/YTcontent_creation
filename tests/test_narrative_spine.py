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


# ── Step 2: build_script_prompt consumes spine ──────────────────────────────

def test_script_prompt_unchanged_when_spine_missing():
    """Without a spine, the script prompt must produce its legacy shape."""
    from research_templates import build_script_prompt
    prompt = build_script_prompt(
        template_id="educational_explainer",
        topic="Test topic",
        research_dossier="Some dossier",
    )
    assert "NARRATIVE SPINE" not in prompt
    assert '"sources_used"' in prompt
    assert '"claim_ids"' not in prompt


def test_script_prompt_injects_spine_block_when_spine_present():
    """With a spine, the prompt must inject the spine block and bind beats to claim_ids."""
    from research_templates import build_script_prompt
    spine = json.loads(VALID_SPINE_JSON)
    prompt = build_script_prompt(
        template_id="educational_explainer",
        topic="Test topic",
        research_dossier="Some dossier",
        spine=spine,
    )
    assert "NARRATIVE SPINE" in prompt
    assert "Logical flow: k1 → k2 → k3" in prompt
    assert '"claim_ids"' in prompt
    assert '"claim_ids_used"' in prompt
    assert '"sources_used"' not in prompt


# ── Step 2: claim_ids sanitization on returned narration ────────────────────

def test_sanitize_narration_drops_unknown_claim_ids():
    import research_scriptwriter as rsw
    spine = json.loads(VALID_SPINE_JSON)
    narration = {
        "narration": [
            {"act": "ACT 1", "beat": "Hook", "text": "...", "claim_ids": ["k1", "k_ghost"]},
            {"act": "ACT 1", "beat": "Stakes", "text": "...", "claim_ids": ["k2"]},
            {"act": "ACT 2", "beat": "Twist", "text": "...", "claim_ids": []},
        ]
    }
    rsw._sanitize_narration_claim_ids(narration, spine)
    assert narration["narration"][0]["claim_ids"] == ["k1"]
    assert narration["narration"][1]["claim_ids"] == ["k2"]
    assert narration["narration"][2]["claim_ids"] == []
    assert narration["claim_ids_used"] == ["k1", "k2"]


def test_generate_narration_passes_spine_into_prompt():
    """End-to-end: spine flows from generate_narration through build_script_prompt to Gemini."""
    import research_scriptwriter as rsw
    spine = json.loads(VALID_SPINE_JSON)
    fake_response = json.dumps({
        "title": "T",
        "narration": [
            {"act": "ACT 1", "beat": "Hook", "text": "x", "claim_ids": ["k1"]},
        ],
        "claim_ids_used": ["k1"],
    })
    captured = {}

    def fake_gen(prompt, **kwargs):
        captured["prompt"] = prompt
        return fake_response

    with patch.object(rsw, 'generate_content', side_effect=fake_gen):
        result = rsw.generate_narration(
            topic="T", template_id="educational_explainer",
            research_dossier="dossier", spine=spine, api_key="fake",
        )
    assert result.get("success")
    assert "NARRATIVE SPINE" in captured["prompt"]
    assert result["narration"]["narration"][0]["claim_ids"] == ["k1"]


# ── Step 3: beat regeneration is spine-aware ────────────────────────────────

def test_regen_prompt_drops_dossier_excerpt_when_spine_present():
    """With a spine, the regen prompt must NOT include the legacy 4000-char dossier excerpt."""
    from research_templates import build_beat_regeneration_prompt
    spine = json.loads(VALID_SPINE_JSON)
    long_dossier = "DOSSIER_MARKER " * 500  # > 4000 chars
    full_narration = {
        "narration": [
            {"act": "ACT 1", "beat": "Hook", "text": "...", "claim_ids": ["k1"]},
            {"act": "ACT 1", "beat": "Stakes", "text": "...", "claim_ids": ["k2"]},
        ]
    }
    prompt = build_beat_regeneration_prompt(
        template_id="educational_explainer",
        topic="T", research_dossier=long_dossier,
        full_narration=full_narration,
        target_beat_indices=[0],
        spine=spine,
    )
    assert "DOSSIER_MARKER" not in prompt
    assert "RESEARCH DOSSIER" not in prompt
    assert "NARRATIVE SPINE" in prompt
    assert "CLAIM ANCHOR" in prompt
    assert "Claims: [k1]" in prompt


def test_regen_prompt_keeps_dossier_excerpt_when_spine_missing():
    """Legacy path: without spine, the 4000-char dossier truncation must still apply."""
    from research_templates import build_beat_regeneration_prompt
    long_dossier = "DOSSIER_MARKER " * 500
    full_narration = {"narration": [{"act": "A", "beat": "B", "text": "..."}]}
    prompt = build_beat_regeneration_prompt(
        template_id="educational_explainer",
        topic="T", research_dossier=long_dossier,
        full_narration=full_narration,
        target_beat_indices=[0],
    )
    assert "RESEARCH DOSSIER" in prompt
    assert "DOSSIER_MARKER" in prompt
    assert "NARRATIVE SPINE" not in prompt


def test_regenerate_beats_restyle_preserves_claim_ids():
    """Restyle mode: regenerated beat returning the same claim_ids passes through unchanged."""
    import research_scriptwriter as rsw
    spine = json.loads(VALID_SPINE_JSON)
    full_narration = {
        "narration": [
            {"act": "ACT 1", "beat": "Hook", "text": "old", "claim_ids": ["k1", "k2"]},
        ]
    }
    fake = json.dumps([
        {"act": "ACT 1", "beat": "Hook", "text": "new phrasing", "claim_ids": ["k1", "k2"]},
    ])
    with patch.object(rsw, 'generate_content', return_value=fake) as mock_gc:
        result = rsw.regenerate_beats(
            topic="T", template_id="educational_explainer",
            research_dossier="dossier", full_narration=full_narration,
            target_beat_indices=[0], mode="restyle",
            spine=spine, api_key="fake",
        )
    assert result.get("success")
    assert result["beats"][0]["claim_ids"] == ["k1", "k2"]
    assert mock_gc.call_count == 1  # no retry needed


def test_regenerate_beats_restyle_drift_triggers_retry():
    """Restyle drift (different claim_ids) triggers one tighter retry."""
    import research_scriptwriter as rsw
    spine = json.loads(VALID_SPINE_JSON)
    full_narration = {
        "narration": [
            {"act": "ACT 1", "beat": "Hook", "text": "old", "claim_ids": ["k1"]},
        ]
    }
    drifted = json.dumps([
        {"act": "ACT 1", "beat": "Hook", "text": "new", "claim_ids": ["k3"]},
    ])
    corrected = json.dumps([
        {"act": "ACT 1", "beat": "Hook", "text": "newer", "claim_ids": ["k1"]},
    ])
    with patch.object(rsw, 'generate_content', side_effect=[drifted, corrected]) as mock_gc:
        result = rsw.regenerate_beats(
            topic="T", template_id="educational_explainer",
            research_dossier="dossier", full_narration=full_narration,
            target_beat_indices=[0], mode="restyle",
            spine=spine, api_key="fake",
        )
    assert result.get("success")
    assert result["beats"][0]["claim_ids"] == ["k1"]
    assert mock_gc.call_count == 2  # original + retry


def test_regenerate_beats_sanitizes_unknown_claim_ids():
    """Unknown ids (k_ghost) must be stripped from regenerated beats."""
    import research_scriptwriter as rsw
    spine = json.loads(VALID_SPINE_JSON)
    full_narration = {
        "narration": [
            {"act": "ACT 1", "beat": "Hook", "text": "old", "claim_ids": ["k1"]},
        ]
    }
    # Reimagine path: no equality check, but sanitization still runs
    drifted = json.dumps([
        {"act": "ACT 1", "beat": "Hook", "text": "new", "claim_ids": ["k1", "k_ghost"]},
    ])
    with patch.object(rsw, 'generate_content', return_value=drifted):
        result = rsw.regenerate_beats(
            topic="T", template_id="educational_explainer",
            research_dossier="dossier", full_narration=full_narration,
            target_beat_indices=[0], mode="reimagine",
            spine=spine, api_key="fake",
        )
    assert result.get("success")
    assert result["beats"][0]["claim_ids"] == ["k1"]


# ── Step 4: production + director consume spine ─────────────────────────────

NARRATION_WITH_CLAIMS = {
    "title": "T",
    "narration": [
        {"act": "ACT 1", "beat": "Hook", "text": "Open with a question.", "claim_ids": ["k1"]},
        {"act": "ACT 2", "beat": "Stakes", "text": "Raise the stakes here.", "claim_ids": ["k2", "k3"]},
    ],
}


def test_production_prompt_unchanged_when_spine_missing():
    """build_production_prompt without spine must NOT emit a claim_id field or SPINE block."""
    from research_templates import build_production_prompt
    prompt = build_production_prompt(narration_json=NARRATION_WITH_CLAIMS, duration_minutes=2)
    assert "NARRATIVE SPINE" not in prompt
    assert '"claim_id"' not in prompt


def test_production_prompt_injects_spine_and_claim_id_field():
    """With spine, build_production_prompt must inject SPINE block, beat claim tags, and claim_id schema."""
    from research_templates import build_production_prompt
    spine = json.loads(VALID_SPINE_JSON)
    prompt = build_production_prompt(
        narration_json=NARRATION_WITH_CLAIMS, duration_minutes=2,
        spine=spine,
    )
    assert "NARRATIVE SPINE" in prompt
    assert "Claims: [k1]" in prompt
    assert "Claims: [k2, k3]" in prompt
    assert '"claim_id"' in prompt
    assert "CLAIM PROPAGATION" in prompt


def test_director_prompt_unchanged_when_spine_missing():
    """build_director_prompt without spine must NOT emit a claim_id field."""
    from research_templates import build_director_prompt
    prompt = build_director_prompt(narration_json=NARRATION_WITH_CLAIMS, duration_minutes=2)
    assert "NARRATIVE SPINE" not in prompt
    assert '"claim_id"' not in prompt


def test_director_prompt_injects_spine_and_claim_id_field():
    """With spine, build_director_prompt must inject SPINE block + per-shot claim_id schema."""
    from research_templates import build_director_prompt
    spine = json.loads(VALID_SPINE_JSON)
    prompt = build_director_prompt(
        narration_json=NARRATION_WITH_CLAIMS, duration_minutes=2,
        spine=spine,
    )
    assert "NARRATIVE SPINE" in prompt
    assert "Claims: [k1]" in prompt
    assert "Claims: [k2, k3]" in prompt
    assert '"claim_id"' in prompt
    assert "CLAIM PROPAGATION" in prompt


# ── Step 7: end-to-end claim-id propagation ────────────────────────────────

def test_e2e_claim_id_survives_research_to_production():
    """A claim id (k3) must survive: spine → narration → beat regen → director phase.

    This is the headline guarantee of the Narrative Spine feature: source citations
    propagate end-to-end without being lost at any handoff. We mock generate_content
    at each phase boundary and verify k3 is present in the final shot.
    """
    import research_scriptwriter as rsw
    spine = json.loads(VALID_SPINE_JSON)

    # ── Phase 1: spine → narration (script gen) ───────────────────────────
    narration_response = json.dumps({
        "title": "T",
        "narration": [
            {"act": "ACT 1", "beat": "Hook", "text": "Open with a question.", "claim_ids": ["k1"]},
            {"act": "ACT 2", "beat": "Stakes", "text": "Raise the stakes.", "claim_ids": ["k2"]},
            {"act": "ACT 3", "beat": "Payoff", "text": "Deliver the conclusion.", "claim_ids": ["k3"]},
        ],
        "claim_ids_used": ["k1", "k2", "k3"],
    })
    with patch.object(rsw, 'generate_content', return_value=narration_response):
        result = rsw.generate_narration(
            topic="T", template_id="educational_explainer",
            research_dossier="dossier with k3 fact", spine=spine, api_key="fake",
        )
    assert result.get("success")
    narration = result["narration"]
    payoff_beat = next(b for b in narration["narration"] if b["beat"] == "Payoff")
    assert payoff_beat["claim_ids"] == ["k3"], "k3 lost at script gen"

    # ── Phase 2: narration → beat regen (restyle preserves k3) ────────────
    regen_response = json.dumps([
        {"act": "ACT 3", "beat": "Payoff", "text": "Deliver the conclusion (restyled).", "claim_ids": ["k3"]},
    ])
    with patch.object(rsw, 'generate_content', return_value=regen_response):
        regen_result = rsw.regenerate_beats(
            topic="T", template_id="educational_explainer",
            research_dossier="dossier",
            full_narration=narration,
            target_beat_indices=[2], mode="restyle",
            spine=spine, api_key="fake",
        )
    assert regen_result.get("success")
    assert regen_result["beats"][0]["claim_ids"] == ["k3"], "k3 lost in regen"

    # Apply regen back into the narration (mirrors what the route does)
    narration["narration"][2] = {
        **narration["narration"][2],
        "text": regen_result["beats"][0]["text"],
        "claim_ids": regen_result["beats"][0]["claim_ids"],
    }
    assert narration["narration"][2]["claim_ids"] == ["k3"]

    # ── Phase 3: narration → production (Director carries k3 to a shot) ───
    # Verify that the Director prompt contains [Claims: k3] for the Payoff beat.
    from research_templates import build_director_prompt
    director_prompt = build_director_prompt(
        narration_json=narration, duration_minutes=2, spine=spine,
    )
    # The Payoff beat (3rd beat) line must carry the [Claims: k3] tag.
    assert "Claims: [k3]" in director_prompt, "k3 lost when Director prompt was built"
    # And the SPINE REFERENCE block must include the k3 claim entry.
    assert "[k3]" in director_prompt
    assert "Steam spins turbines." in director_prompt  # k3's text from VALID_SPINE_JSON
