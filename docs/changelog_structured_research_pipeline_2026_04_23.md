# Changelog — Structured Research Pipeline

**Date:** 2026-04-23
**Scope:** Research depth refactor — unlocks Gemini's output cap, replaces single-call research with a planner → parallel sub-researcher → merger pipeline, and emits a structured `{sections, claims, sources}` schema alongside the legacy markdown dossier.
**Feature flag:** `RESEARCH_STRUCTURED=1` (off by default during rollout).

---

## Why

Research answers felt shallow, sources were unverifiable, and the flat Markdown dossier left downstream prompts with nothing to cite. Root cause: `generate_content()` never set `max_output_tokens`, so every research call was silently truncated to Gemini's default 8,192-token output ceiling — even though Gemini 3 Flash/Pro support 65,536. On top of that, the single-call prompt asked for 15–20 facts in one shot, which the cap alone can't satisfy.

This change does three things, in order:

1. Unlock the output cap.
2. Decompose the single call into a planner → parallel sub-queries → merger pipeline so claims and sources are emitted with URLs + quotes from Google Search grounding.
3. Store the result as a structured schema (sections / claims / sources) in Firestore alongside the legacy Markdown so nothing existing breaks.

Stays on Gemini (no new vendor), per-project scope only.

---

## What changed

### Phase 0 — Token-cap fix
- `execution/gemini_client.py` — `generate_content()` now accepts `max_output_tokens` and `return_response`. When either of search/temperature/max_output_tokens is set, a `GenerateContentConfig` is built and `config.max_output_tokens` is plumbed through. Defensive retry once at 16,384 on `InvalidArgument` (unannounced model ceiling changes).
- `execution/server.py` research callsites pass `max_output_tokens=32768` for deep mode and `16384` for fast and the Flash fallback.
- Narration / production / title callers untouched — their outputs are bounded and don't hit the cap.

### Phase 1 — Structured research pipeline
New code in `execution/research_scriptwriter.py`:

- `run_structured_research(topic, template_id, api_key, mode) -> dict` — orchestrates:
  1. **Planner** (1 Flash call, no search): expands the template's `search_layers` into 3–6 concrete sub-queries, returns JSON.
  2. **Sub-researchers** (N parallel Pro+Search calls with `max_output_tokens=32768`): one per sub-query, each emits `{section, claims[], sources[]}` in the canonical schema.
  3. **Merger**: dedupes claims/sources across sub-queries, assigns stable `c1..cN` / `s1..sN` ids, emits the final schema.
- `_extract_grounding_sources(response) -> list[dict]` — pulls `{url, title, snippet}` from `candidates[0].grounding_metadata.grounding_chunks[].web.{uri,title}`, enriches with `grounding_supports` segment text when available. SDK field drift is handled defensively.
- `_scrape_urls_from_text(text) -> list[dict]` — regex-URL fallback when grounding metadata is empty.
- `_markdown_from_structured(structured) -> str` — renders the canonical schema back into the legacy `# Research Dossier / ## Template / ### {section}` layout so the legacy UI keeps rendering unchanged.
- `_empty_structured(topic, template_id, mode, model)` — canonical empty schema used on total failure.
- `structure_from_blob(text, topic, template_id, mode, model, api_key)` — best-effort Flash-based extractor that maps the async `deep_research_agent` text blob into the canonical schema (empty sources are acceptable — the agent API does not expose grounding metadata yet).
- `generate_narration` and `regenerate_beats` gain an optional `structured` param and forward it to the prompt builders.

Canonical schema:

```json
{
  "meta":     { "topic", "template_id", "mode", "model", "generated_at" },
  "sections": [ { "id", "title", "summary", "claim_ids": [] } ],
  "claims":   [ { "id": "c1", "text", "confidence": "high|med|low", "source_ids": ["s1","s2"] } ],
  "sources":  [ { "id": "s1", "url", "title", "publisher", "quote", "accessed_at" } ]
}
```

Reuses existing `_retry_api_call`, `_parse_json_response`, and the project's `ThreadPoolExecutor` pattern.

### Phase 2 — Firestore writes (additive, non-breaking)

`execution/server.py`:

- `users/{uid}/projects/{pid}` — on merge, keeps `research_dossier`, `research_summary`, `research_key_facts`, `research_sources`, `last_updated_at`; adds `research_structured` (the full object) and `research_schema_version: 1` when the structured pipeline produced output.
- `users/{uid}/dossiers/{autoId}` — on set, keeps `topic`, `template_id`, `template_name`, `dossier`, `key_facts`, `sources`, `summary`, `created_at`, `research_model`; adds `structured` and `schema_version: 1`.

Absence of `research_structured` on a project = legacy; readers fall back to the Markdown blob.

New constants in `server.py`:

```python
RESEARCH_STRUCTURED_ENABLED = os.environ.get('RESEARCH_STRUCTURED', '0').lower() in ('1', 'true', 'yes')
RESEARCH_SCHEMA_VERSION = 1
```

### Phase 3 — Backwards-compatible API response

`POST /api/research` (:1357) and `POST /api/research/poll` (:1748) now include `structured` in the JSON response when the pipeline produces output. The `dossier`, `summary`, `key_facts`, `sources` fields remain present and unchanged. The `deep_research_agent` poll path runs `structure_from_blob` over the returned text to synthesize `structured`; if extraction fails, the field is omitted rather than returning a malformed shape.

### Phase 4 — Downstream prompt upgrades

`execution/research_templates.py`:

- New helpers `_format_structured_claims_block(structured, max_claims, max_sources)` and `_top_claim_texts(structured, limit)`.
- `build_title_suggestions_prompt(..., structured=None)` — when provided, injects top-N claim texts instead of `dossier[:3000]`.
- `build_script_prompt(..., structured=None)` — under `═══════ RESEARCH DOSSIER ═══════`, injects a `CLAIMS (cite via [s1], [s2]…)` block followed by a `SOURCES` mapping `[sN] title — publisher (url) | "quote"`. Appends one line to the system prompt: *"When a claim comes from the research, reference the source id inline like [s3]."*
- `build_beat_regeneration_prompt(..., structured=None)` — same plumbing; structured block sits between the dossier excerpt and the surrounding-context block.
- Server callsites pass `_load_project_structured(project_id)`; when `None`, behavior is byte-identical to pre-change. Production table (`build_production_prompt`) is untouched — it reads narration, not dossier.

New helper in `server.py`:

```python
def _load_project_structured(project_id):
    """Return the research_structured object for a project, or None."""
```

Called by `/api/suggest-titles`, `/api/generate-script`, and `/api/regenerate-beat` — the three routes whose prompts consume the dossier.

### Phase 5 — UI additions (non-breaking)

`ui/index.html`:

- New global `currentResearchStructured` in the state block.
- New `<div class="sources-list" id="structuredSources"></div>` below the existing `#sourcesList`.
- New `renderStructuredSources(structured)` renders a "Verified Sources" block: `<a href target="_blank" rel="noopener">title</a>` plus `<blockquote>quote</blockquote>`, each tagged with its `[sN]` id.
- `displayResearchResults()` now stores `data.structured` and calls `renderStructuredSources`.
- `clearAppForNewProject()` resets `currentResearchStructured` and empties `#structuredSources`.
- `restoreProjectState()` rehydrates `currentResearchStructured` from `project.research_structured` and calls `renderStructuredSources` during project load.
- Autosave payload spreads `research_structured` when non-null (omitted otherwise so merges don't nuke it).

### Tests

New file `tests/test_structured_research.py` — 14 unit tests, all passing:

- `test_generate_content_respects_max_output_tokens` — param plumbs through to `GenerateContentConfig`.
- `test_generate_content_no_config_when_all_none` — byte-identical legacy path when nothing is set.
- `test_structured_schema_shape` — returned object has `meta/sections/claims/sources` with stable `c1..cN` / `s1..sN` ids and correct `source_urls` → `source_ids` mapping.
- `test_structured_schema_dedupes_sources_by_url` — identical URLs across sub-queries collapse to one source.
- `test_markdown_from_structured_matches_legacy_layout` / `test_markdown_from_structured_handles_empty` — legacy rendering contract preserved.
- `test_script_prompt_unchanged_when_structured_missing` — `build_script_prompt(..., structured=None|{}|{claims:[],sources:[]})` output byte-equal to pre-change baseline.
- `test_script_prompt_injects_claims_block_when_structured_present` — presence check for `CLAIMS` / `[c1]` / `[s1]` / inline-citation instruction.
- `test_title_prompt_uses_claim_texts_when_structured_present`.
- `test_structure_from_blob_returns_empty_on_empty_text` / `test_structure_from_blob_returns_empty_on_extractor_error`.
- `test_extract_grounding_sources_empty_response` / `test_extract_grounding_sources_parses_web_chunks` / `test_scrape_urls_from_text_fallback`.

All 4 existing `test_api_workflows.py` tests still pass.

---

## Files touched

| File | Change |
|------|--------|
| `execution/gemini_client.py` | `generate_content()` accepts `max_output_tokens` + `return_response`; defensive fallback at 16 384. |
| `execution/research_scriptwriter.py` | New `run_structured_research`, `structure_from_blob`, `_extract_grounding_sources`, `_scrape_urls_from_text`, `_markdown_from_structured`, `_empty_structured`, `_planner_expand_subqueries`, `_run_sub_researcher`, `_merge_subresearcher_outputs`; `generate_narration` and `regenerate_beats` accept `structured`. |
| `execution/research_templates.py` | New `_format_structured_claims_block`, `_top_claim_texts`; `build_title_suggestions_prompt`, `build_script_prompt`, `build_beat_regeneration_prompt` accept optional `structured`. |
| `execution/server.py` | `RESEARCH_STRUCTURED_ENABLED` flag + `RESEARCH_SCHEMA_VERSION`; `_load_project_structured`; `/api/research` + `/api/research/poll` persist `research_structured` and return it; callsites pass `structured=_load_project_structured(project_id)`. |
| `ui/index.html` | `currentResearchStructured` global, `#structuredSources` container, `renderStructuredSources()`, autosave + loadProject + clearAppForNewProject wiring. |
| `tests/test_structured_research.py` | New — 14 unit tests. |

---

## Migration / deploy

1. Ship Phase 0 to staging, verify the output-token jump on a single research run.
2. Ship Phases 1–4 behind `RESEARCH_STRUCTURED=1`. Run one deep request per template in staging, diff the Firestore doc, compare dossier token count pre/post (expect ~3–6× depth).
3. Enable the flag in prod for 48h. If no regressions, remove the flag.
4. Phase 5 UI ships any time after Phase 3 lands.

---

## Verification

**Local**

```bash
python execution/server.py
# In another shell, with a valid Firebase id token:
curl -X POST http://localhost:8080/api/research \
  -H 'Authorization: Bearer <id_token>' \
  -H 'Content-Type: application/json' \
  -d '{"topic":"...","template_id":"educational_explainer","research_model":"deep","project_id":"<pid>"}'
```

Inspect the response for both `dossier` (legacy markdown) and `structured.{sections, claims, sources}`. In the Firestore console, open `users/{uid}/projects/{pid}` and confirm both `research_dossier` and `research_structured` are present.

**Tests**

```bash
pytest tests/test_structured_research.py -v
pytest tests/test_api_workflows.py -v
```

**UI smoke**

- Load an existing legacy project (no `research_structured`) → research section renders unchanged.
- Run deep research on a new project with the flag on → new "Verified Sources" block appears with clickable links and quote blocks; narration generation emits `[s1]`-style inline citations.

---

## Risks

- **SDK drift** — `google-genai` grounding metadata shape changes between versions. `_extract_grounding_sources` tries `grounding_chunks[].web.{uri,title}` first, then `grounding_supports` segments, then regex-scrapes URLs from the text. If all three return empty, the structured object persists with an empty `sources` list (the legacy markdown dossier is unaffected).
- **Preview model ceilings** — models may reject our requested `max_output_tokens`. Covered by the one-shot fallback to 16 384.
- **API cost** — structured research adds ~3–5× per request (planner + N sub-queries + merger). Acceptable given the quality goal; document in release notes before enabling for all users.
- **Deep Research Agent gap** — `deep_research_agent` returns unstructured text via `client.interactions.*`, which does not expose grounding metadata. `structure_from_blob` is best-effort and will often return an empty `sources[]` until the agent API surfaces grounding data.
