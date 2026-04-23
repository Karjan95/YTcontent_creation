"""Tests for the structured research pipeline.

Covers the Phase 0 token-cap fix and the Phase 1-3 structured-schema additions
introduced alongside the research refactor.
"""

import json
from unittest.mock import patch, MagicMock

import pytest


# ── Phase 0: max_output_tokens plumbs through to GenerateContentConfig ────

def test_generate_content_respects_max_output_tokens():
    """max_output_tokens must be set on the GenerateContentConfig passed to the SDK."""
    import gemini_client

    fake_response = MagicMock()
    fake_response.text = "ok"

    fake_models = MagicMock()
    fake_models.generate_content.return_value = fake_response

    fake_client = MagicMock()
    fake_client.models = fake_models

    with patch.object(gemini_client, 'get_client', return_value=fake_client):
        result = gemini_client.generate_content(
            "hello",
            model_name="gemini-3-flash-preview",
            api_key="fake",
            max_output_tokens=32768,
        )

    assert result == "ok"
    call = fake_models.generate_content.call_args
    config = call.kwargs['config']
    assert config is not None
    assert getattr(config, 'max_output_tokens', None) == 32768


def test_generate_content_no_config_when_all_none():
    """Without search/temperature/max_output_tokens, no config should be built (legacy behavior)."""
    import gemini_client

    fake_response = MagicMock()
    fake_response.text = "ok"
    fake_models = MagicMock()
    fake_models.generate_content.return_value = fake_response
    fake_client = MagicMock()
    fake_client.models = fake_models

    with patch.object(gemini_client, 'get_client', return_value=fake_client):
        gemini_client.generate_content("hi", api_key="fake")

    call = fake_models.generate_content.call_args
    assert call.kwargs['config'] is None


# ── Phase 1: structured schema shape ──────────────────────────────────────

def test_structured_schema_shape():
    """_merge_subresearcher_outputs must emit the canonical schema keys."""
    import research_scriptwriter as rsw

    sub_outputs = [
        {
            "section": {"title": "Origins", "summary": "A summary."},
            "claims": [
                {"text": "Invented in 1956", "confidence": "high",
                 "source_urls": ["https://example.com/a"]},
            ],
            "sources": [
                {"url": "https://example.com/a", "title": "Example A",
                 "publisher": "", "quote": "quote text"},
            ],
        },
        {
            "section": {"title": "Impact", "summary": "Another summary."},
            "claims": [
                {"text": "Widely adopted", "confidence": "med",
                 "source_urls": ["https://example.com/b"]},
            ],
            "sources": [
                {"url": "https://example.com/b", "title": "Example B",
                 "publisher": "", "quote": ""},
            ],
        },
    ]

    result = rsw._merge_subresearcher_outputs(
        topic="AI", template_id="educational_explainer",
        mode="deep", model="gemini-test", sub_outputs=sub_outputs,
    )

    assert set(result.keys()) == {"meta", "sections", "claims", "sources"}
    assert result["meta"]["topic"] == "AI"
    assert result["meta"]["template_id"] == "educational_explainer"
    assert len(result["sections"]) == 2
    assert len(result["claims"]) == 2
    assert len(result["sources"]) == 2

    # Stable sequential ids
    assert [c["id"] for c in result["claims"]] == ["c1", "c2"]
    assert [s["id"] for s in result["sources"]] == ["s1", "s2"]

    # Claim source_urls correctly mapped to source_ids
    assert result["claims"][0]["source_ids"] == ["s1"]
    assert result["claims"][1]["source_ids"] == ["s2"]

    # Each section's claim_ids references real claims
    all_claim_ids = {c["id"] for c in result["claims"]}
    for sec in result["sections"]:
        for cid in sec["claim_ids"]:
            assert cid in all_claim_ids


def test_structured_schema_dedupes_sources_by_url():
    """Identical URLs across sub-queries must collapse to a single source id."""
    import research_scriptwriter as rsw

    sub_outputs = [
        {
            "section": {"title": "A", "summary": ""},
            "claims": [
                {"text": "Claim 1", "confidence": "high",
                 "source_urls": ["https://example.com/shared"]},
            ],
            "sources": [
                {"url": "https://example.com/shared", "title": "Shared",
                 "publisher": "", "quote": ""},
            ],
        },
        {
            "section": {"title": "B", "summary": ""},
            "claims": [
                {"text": "Claim 2", "confidence": "med",
                 "source_urls": ["https://example.com/shared"]},
            ],
            "sources": [
                {"url": "https://example.com/shared", "title": "Shared",
                 "publisher": "", "quote": ""},
            ],
        },
    ]

    result = rsw._merge_subresearcher_outputs(
        topic="T", template_id="educational_explainer",
        mode="fast", model="gemini-test", sub_outputs=sub_outputs,
    )

    assert len(result["sources"]) == 1
    assert result["sources"][0]["id"] == "s1"
    assert result["claims"][0]["source_ids"] == ["s1"]
    assert result["claims"][1]["source_ids"] == ["s1"]


# ── _markdown_from_structured preserves the legacy layout ─────────────────

def test_markdown_from_structured_matches_legacy_layout():
    """Rendered markdown must start with the same three headers as build_research_dossier()."""
    import research_scriptwriter as rsw

    structured = rsw._empty_structured("My Topic", "educational_explainer", "deep", "gemini-test")
    structured["sections"] = [{"id": "sec1", "title": "Origins", "summary": "A summary.", "claim_ids": ["c1"]}]
    structured["claims"] = [{"id": "c1", "text": "Invented in 1956", "confidence": "high", "source_ids": ["s1"]}]
    structured["sources"] = [{"id": "s1", "url": "https://example.com", "title": "Example", "publisher": "", "quote": ""}]

    md = rsw._markdown_from_structured(structured)
    lines = md.splitlines()

    assert lines[0] == "# Research Dossier: My Topic"
    assert lines[1].startswith("## Template: ")
    assert lines[2] == "## Research Mode: deep"
    assert "### Origins" in md
    assert "Invented in 1956" in md
    assert "[s1]" in md
    assert "https://example.com" in md


def test_markdown_from_structured_handles_empty():
    """Empty structured should still render at least the header lines."""
    import research_scriptwriter as rsw

    structured = rsw._empty_structured("X", "educational_explainer", "fast", "gemini-test")
    md = rsw._markdown_from_structured(structured)
    assert "# Research Dossier: X" in md


# ── Phase 4: prompts fall back byte-for-byte when structured is missing ───

def test_script_prompt_unchanged_when_structured_missing():
    """build_script_prompt(..., structured=None) must equal the legacy output."""
    from research_templates import build_script_prompt

    kwargs = dict(
        template_id="educational_explainer",
        topic="AI",
        research_dossier="Some dossier text.",
        duration_minutes=5,
        audience="general",
        tone="conversational",
        selected_title="My Title",
    )

    baseline = build_script_prompt(**kwargs)
    with_none = build_script_prompt(**kwargs, structured=None)
    with_empty = build_script_prompt(**kwargs, structured={})
    with_no_claims = build_script_prompt(**kwargs, structured={"claims": [], "sources": []})

    assert baseline == with_none
    assert baseline == with_empty
    assert baseline == with_no_claims


def test_script_prompt_injects_claims_block_when_structured_present():
    """When structured has claims, the CLAIMS block must appear in the prompt."""
    from research_templates import build_script_prompt

    structured = {
        "claims": [
            {"id": "c1", "text": "Fact one", "confidence": "high", "source_ids": ["s1"]},
        ],
        "sources": [
            {"id": "s1", "url": "https://example.com", "title": "Ex",
             "publisher": "", "quote": "exact wording"},
        ],
    }

    prompt = build_script_prompt(
        template_id="educational_explainer",
        topic="AI",
        research_dossier="Some dossier text.",
        duration_minutes=5,
        audience="general",
        tone="conversational",
        selected_title="My Title",
        structured=structured,
    )

    assert "CLAIMS" in prompt
    assert "[c1]" in prompt
    assert "[s1]" in prompt
    assert "https://example.com" in prompt
    assert "reference the source id inline" in prompt


def test_title_prompt_uses_claim_texts_when_structured_present():
    from research_templates import build_title_suggestions_prompt

    structured = {
        "claims": [
            {"id": "c1", "text": "First fact", "confidence": "high", "source_ids": []},
            {"id": "c2", "text": "Second fact", "confidence": "med", "source_ids": []},
        ],
        "sources": [],
    }

    prompt = build_title_suggestions_prompt(
        template_id="educational_explainer",
        topic="AI",
        dossier="A long legacy dossier blob",
        audience="General",
        structured=structured,
    )

    assert "TOP FACTUAL CLAIMS" in prompt
    assert "First fact" in prompt
    assert "Second fact" in prompt


# ── structure_from_blob best-effort extractor ─────────────────────────────

def test_structure_from_blob_returns_empty_on_empty_text():
    import research_scriptwriter as rsw
    result = rsw.structure_from_blob(
        text="", topic="X", template_id="educational_explainer",
        mode="deep_research_agent", model="deep-research-pro", api_key="fake",
    )
    assert set(result.keys()) == {"meta", "sections", "claims", "sources"}
    assert result["sections"] == []
    assert result["claims"] == []
    assert result["sources"] == []


def test_structure_from_blob_returns_empty_on_extractor_error():
    """If the extractor call fails, we still return the empty-but-valid schema."""
    import research_scriptwriter as rsw
    with patch.object(rsw, 'generate_content', return_value="Error: boom"):
        result = rsw.structure_from_blob(
            text="Some report text with no JSON",
            topic="X", template_id="educational_explainer",
            mode="deep_research_agent", model="deep-research-pro", api_key="fake",
        )
    assert result["sections"] == []
    assert result["claims"] == []
    assert result["sources"] == []
    assert result["meta"]["topic"] == "X"


# ── grounding extractor handles missing/odd SDK shapes gracefully ────────

def test_extract_grounding_sources_empty_response():
    import research_scriptwriter as rsw
    assert rsw._extract_grounding_sources(None) == []
    fake = MagicMock()
    fake.candidates = []
    assert rsw._extract_grounding_sources(fake) == []


def test_extract_grounding_sources_parses_web_chunks():
    import research_scriptwriter as rsw

    chunk = MagicMock()
    chunk.web = MagicMock()
    chunk.web.uri = "https://example.com/a"
    chunk.web.title = "Example A"

    candidate = MagicMock()
    candidate.grounding_metadata = MagicMock()
    candidate.grounding_metadata.grounding_chunks = [chunk]
    candidate.grounding_metadata.grounding_supports = []

    response = MagicMock()
    response.candidates = [candidate]

    sources = rsw._extract_grounding_sources(response)
    assert len(sources) == 1
    assert sources[0]["url"] == "https://example.com/a"
    assert sources[0]["title"] == "Example A"


def test_scrape_urls_from_text_fallback():
    import research_scriptwriter as rsw
    text = "See https://example.com/a and http://foo.bar/page."
    out = rsw._scrape_urls_from_text(text)
    urls = [s["url"] for s in out]
    assert "https://example.com/a" in urls
    assert "http://foo.bar/page" in urls
