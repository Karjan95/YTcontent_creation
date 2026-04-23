Here is Claude's plan:                                                                             
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 Research Pipeline Refactor — Plan                                                                  
                                                                                                    
 Context                                                

 Research answers in Gemini Studio feel shallow, sources are unverifiable, and the dossier is
 stored as a flat Markdown blob that downstream prompts can't cite. Investigation surfaced the root
  cause: generate_content() at execution/gemini_client.py:60 never sets max_output_tokens, so every
  research call is silently truncated to Gemini's default of 8,192 tokens — even though Gemini 3
 Flash/Pro support 65,536. The current single-call prompt also asks for 15-20 facts in one shot,
 which the cap alone can't satisfy.

 This change does three things, in order: (1) unlock the output cap, (2) decompose the single call
 into a small planner → parallel sub-queries → merge pipeline so claims and sources are emitted
 with URLs + quotes from Google Search grounding, (3) store the result as a structured schema
 (sections / claims / sources) in Firestore alongside the legacy Markdown so nothing existing
 breaks. Stays on Gemini (no new vendor), per-project scope only.

 Phase 0 — Token-cap fix (fast win, ship independently)

 File: execution/gemini_client.py:60-86

 - Add max_output_tokens: int | None = None param to generate_content().
 - In the config block (lines 66-72), always construct types.GenerateContentConfig() when any of
 search/temperature/max_output_tokens is provided, and set config.max_output_tokens =
 max_output_tokens when given.
 - Callsites to pass the new param:
   - execution/server.py:1477, 1483 (research fast/deep sync path): pass max_output_tokens=32768
 for deep, 16384 for fast.
   - execution/research_scriptwriter.py inside start_deep_research (:848) and poll_deep_research
 (:904): pass 32768.
   - Leave narration/production/title callers alone — their outputs are bounded and don't hit the
 cap.
 - Wrap the new call path in try/except for InvalidArgument; on failure, retry once with 16384
 (defensive against unannounced model ceiling changes).

 Phase 0.5 — Introspect grounding metadata (prerequisite for Phase 1)

 Before coding the source extractor, run python -c "from google import genai; …" against a live
 deep-mode response and print response.candidates[0].grounding_metadata. The google-genai SDK field
  names drift between versions (grounding_chunks, grounding_supports, web_search_queries). Record
 the exact shape in the session log; the extractor in Phase 1 depends on it.

 Phase 1 — Structured research pipeline

 Files: execution/research_scriptwriter.py, execution/research_templates.py

 Define the canonical schema (Gemini returns it, we store it verbatim):

 {
   "meta":     { "topic", "template_id", "mode", "model", "generated_at" },
   "sections": [ { "id", "title", "summary", "claim_ids": [] } ],
   "claims":   [ { "id": "c1", "text", "confidence": "high|med|low", "source_ids": ["s1","s2"] } ],
   "sources":  [ { "id": "s1", "url", "title", "publisher", "quote", "accessed_at" } ]
 }

 Pipeline (3-5 Gemini calls total, parallelized with the existing ThreadPoolExecutor pattern
 already in research_scriptwriter.py):

 1. Planner (1 Flash call): expands the template's search_layers (from research_templates.py
 build_research_queries()) into 3-6 concrete sub-queries, returns JSON.
 2. Sub-researchers (N parallel Pro+Search calls with max_output_tokens=32768): one per sub-query,
 each emits {section, claims[], sources[]} in the schema above.
 3. Merger (1 Flash call): dedupes claims/sources across sub-queries, assigns stable c1..cN /
 s1..sN ids, emits final schema.

 New helpers (all in execution/research_scriptwriter.py):
 - run_structured_research(topic, template_id, api_key, mode) -> dict — orchestrates 1→2→3.
 - _extract_grounding_sources(response) -> list[dict] — pulls URLs + titles + snippets from the SDK
  shape recorded in Phase 0.5; falls back to regex-scraping URLs from the text.
 - _markdown_from_structured(structured) -> str — renders the same # Research Dossier / ## Template
  / ### {question}\n{answer} shape that build_research_dossier() currently emits at :37-68, so the
 legacy UI renders unchanged.

 Reuse: existing _retry_api_call (gemini_client.py:29), existing _parse_json_response
 (research_scriptwriter.py:71), existing ThreadPoolExecutor usage already in
 research_scriptwriter.py.

 Phase 2 — Firestore writes (additive, non-breaking)

 File: execution/server.py

 Keep every existing field. Add new ones:

 - Project doc (server.py:1525 and :1818) users/{uid}/projects/{pid} merge:
   - Keep: research_dossier, research_summary, research_key_facts, research_sources,
 last_updated_at.
   - Add: research_structured (the full object above), research_schema_version: 1.
 - Dossier collection (server.py:1538 and :1787) users/{uid}/dossiers/{autoId} set:
   - Keep: topic, template_id, template_name, dossier, key_facts, sources, summary, created_at,
 research_model.
   - Add: structured, schema_version: 1.

 Absence of research_structured on a project = legacy; readers fall back to the Markdown blob.

 Phase 3 — Backwards-compatible API response

 File: execution/server.py

 POST /api/research (:1357) and POST /api/research/poll (:1748) return:
 - dossier (string, from _markdown_from_structured(structured))
 - summary, key_facts[], sources[] (derived from structured for parity with current UI)
 - structured (new full object)

 deep_research_agent path: after the token fix produces a longer text blob, run the merge step
 (Phase 1 step 3) over the blob to synthesize a structured object. If extraction fails, emit
 structured = {sections:[], claims:[], sources:[], meta:{…}} so the field is always present but
 empty.

 Phase 4 — Downstream prompt upgrades

 File: execution/research_templates.py

 Add optional structured: dict | None = None param to:
 - build_title_suggestions_prompt() (:1377) — when provided, inject top-N claim texts instead of
 dossier[:3000].
 - build_script_prompt() (:1458, dossier-embed site at :1664) — under ═══════ RESEARCH DOSSIER
 ═══════, inject a CLAIMS (cite via [s1], [s2]…): block followed by SOURCES: mapping s1 -> url |
 quote. Append one line to system prompt: "When a claim comes from research, reference the source
 id inline like [s3]."
 - build_beat_regeneration_prompt() — same optional plumbing.

 Server callsites must pass project_doc.get('research_structured'); when None, behavior is
 byte-identical to today. Production table (build_production_prompt) is untouched — it reads
 narration, not dossier.

 Phase 5 — UI additions (optional, non-breaking)

 File: ui/index.html:~2745-2760

 After the existing #sourcesList render, if data.structured?.sources?.length > 0, render a new
 #structuredSources block with clickable <a href="s.url" target="_blank"
 rel="noopener">{s.title}</a> plus <blockquote>{s.quote}</blockquote>. Existing
 summary/key_facts/sources blocks unchanged.

 Autosave (~line 7969): add research_structured to the saved payload alongside research_dossier +
 research_summary. Keep the existing guard that omits research_key_facts / research_sources (those
 are written only by the research endpoint).

 Migration / deploy

 1. Ship Phase 0 to staging, verify token count jump on a single research run.
 2. Ship Phases 1-4 behind env flag RESEARCH_STRUCTURED=1. Run one deep request per template in
 staging, diff the Firestore doc, compare dossier token count pre/post (expect ~3-6× depth).
 3. Enable flag in prod for 48h. If no regressions, remove flag.
 4. Phase 5 UI ships any time after Phase 3 lands.

 Verification

 Local
 python execution/server.py
 curl -X POST http://localhost:8080/api/research \
   -H 'Authorization: Bearer <id_token>' \
   -d
 '{"topic":"…","template_id":"educational_explainer","research_model":"deep","project_id":"<pid>"}'
 Inspect response for both dossier (legacy) and structured.{sections,claims,sources}. In Firestore
 console, open users/{uid}/projects/{pid} and confirm both research_dossier and research_structured
  present.

 Tests (tests/test_research.py, new cases):
 - test_generate_content_respects_max_output_tokens — asserts param plumbs through to
 GenerateContentConfig.
 - test_structured_schema_shape — asserts the returned object has sections[]/claims[]/sources[]
 with the right keys.
 - test_markdown_from_structured_matches_legacy — snapshot test against a fixture.
 - test_prompt_falls_back_when_structured_missing — build_script_prompt(..., structured=None)
 output byte-equal to pre-change fixture.
 - test_poll_returns_structured — /api/research/poll returns structured even for
 deep_research_agent.

 UI smoke
 - Load an existing legacy project (no research_structured): research section renders unchanged.
 - Run deep research on a new project: new clickable sources block appears below the legacy list;
 narration generation cites [s1]-style refs.

 Files touched

 - execution/gemini_client.py:60-86 — max_output_tokens param.
 - execution/research_scriptwriter.py:37-68, 848, 904 + new run_structured_research,
 _extract_grounding_sources, _markdown_from_structured.
 - execution/research_templates.py:1377, 1458, 1664 + build_beat_regeneration_prompt — optional
 structured param.
 - execution/server.py:1357, 1477, 1483, 1525, 1538, 1748, 1787, 1818 — response shape + Firestore
 writes.
 - ui/index.html:~2745-2760, ~7969 — clickable sources block + autosave field.
 - tests/test_research.py — new coverage above.

 Risks

 - google-genai grounding metadata shape drifts by SDK version → Phase 0.5 introspection gates
 Phase 1.
 - Model token ceilings may be lower than advertised on some preview models → try/except fallback
 to 16384.
 - API cost rises ~3-5× per research (planner + N sub-queries + merger). Acceptable given quality
 goal; document in release notes.
 - deep_research_agent returns unstructured text; its structured extraction is best-effort and may
 yield empty sources[] until the agent API exposes grounding metadata.