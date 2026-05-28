# Changelog — Cast Fixes + Locations Feature + Upload Support

**Date:** 2026-05-28
**Status:** Implemented, ready for staging.
**Plan:** [`README.md`](README.md), [`phase_1_cast_fixes.md`](phase_1_cast_fixes.md), [`phase_2_locations.md`](phase_2_locations.md), [`phase_3_uploads.md`](phase_3_uploads.md)

This logs every file change made across the three planned phases. Each phase is self-contained and shippable; they were implemented sequentially in the order Phase 1 → 2 → 3 and pushed as a single bundle.

---

## Phase 1 — Cast Bug Fixes

Frontend only. `ui/index.html`.

### Fix 1.1 — Regen now uses edited Visual Identity

**Bug:** `generatePortraitForCharacter` and `generateAllPortraits` sent `char.portrait_prompts.reference_sheet`, which was baked once at suggest-cast time. User edits to the Visual Identity textarea never reached the model, so regenerating produced the same character.

**Fix:** New `buildReferenceSheetPrompt(char, styleSummary)` JS helper. Mirrors the template at `execution/research_templates.py:4300-4311` but builds from the current `char.visual_identity` text on every call. Both regen paths (single + batch) now rebuild the prompt before sending. Removed the "No portrait prompt available" guard — the prompt is always derivable now.

```js
function buildReferenceSheetPrompt(char, styleSummary) {
    const stylePrefix = styleSummary ? `${styleSummary}. ` : '';
    const identity = (char.visual_identity || '').trim();
    return `${stylePrefix}Create a professional character reference sheet for ${char.name}: ${identity}. ` +
        `Use a clean, neutral plain background. Arrange in two horizontal rows: ` +
        `Top row: four full-body standing views ...`;
}
```

For the batch path, each cast member's `portrait_prompts.reference_sheet` is rebuilt in a copy of the array before posting to `/api/generate-cast-portraits-batch` (since the server keys on that field).

### Fix 1.2 — Empty selectedCharacters means none

**Bug:** Three sites in the scene rendering / dispatch path treated `selectedCharacters = []` as "all characters checked". When auto-assignment found no name match for a shot, every cast portrait got auto-attached as a reference and contaminated the image.

**Fix:** Strict membership semantics everywhere. Empty array → no boxes checked → no refs sent.

- Checkbox render: `${s.selectedCharacters?.includes(ch.name) ? 'checked' : ''}`
- Header label: `'None'` instead of `'All (N)'`
- `getStructuredCharacters(idx)`: returns `[]` when `selectedCharacters` is empty
- `toggleSceneCharacter`: removed the "all selected → collapse to empty as shorthand" block

The fix reframes empty as "no known cast member needs a reference for this shot" rather than "no characters in shot at all" — the user can still manually check any box (e.g., for an undefined background character that happens to use a cast member's wardrobe).

### Fix 1.3 — "Appears in Beats" field removed

**Why:** Pure cosmetic field driven by an LLM guess from narration. Drove nothing — production table's per-shot `character_outfit` is the actual truth. Keeping it encouraged users to trust a value with no effect, and was a constant source of confusion when it disagreed with what shots actually showed.

**Removals:**
- Cast card render block (around line 6867-6871)
- `readCastFromUI` form parsing (the `getBeatsStr` + `beats` lines)
- `addCastMember` default object
- `gatherProjectState` strips `appears_in_beats` from each cast member before saving via `({ appears_in_beats, ...rest })` destructure

`_build_cast_section` in `research_templates.py` now omits the "Appears in beats" line when `beats_str` is empty, so existing pre-Phase-1 cast data still renders cleanly when fed back through the production pipeline.

The backend `build_cast_suggestion_prompt` still asks the LLM for `appears_in_beats` (kept the schema unchanged so we don't have to teach the model a new shape) — the frontend just ignores it on the way in and strips it on the way out.

---

## Phase 2 — Locations Feature

Backend + frontend. Mirrors the Cast feature end-to-end.

### `execution/research_templates.py`

- **`_build_cast_section`** — when `appears_in_beats` is empty/missing, the "Appears in beats" line is omitted instead of writing "various". Side-effect of Phase 1.3.
- **`_build_locations_section(locations, context)`** — new function, parallel to `_build_cast_section`. Two contexts:
  - `'storyboard'`: tells the Storyboard Artist to reference locations by name in `first_frame_prompt` and keep visuals consistent across shots set in the same location.
  - `'dp'`: tells the DP to weave the description into the environment portion and keep lighting/palette identical across all shots in that location.
- **`build_storyboard_prompt`** and **`build_dp_prompt`** — new `locations: dict = None` parameter. Each builds `locations_section = _build_locations_section(locations, …)` and injects it into the template alongside the cast section.
- **`build_cast_suggestion_prompt`** — opening line rewritten to "CASTING DIRECTOR and LOCATION SCOUT" with parallel (A) cast / (B) locations responsibilities. Output schema extended with `has_locations`, `locations: [{name, description, environment_type, mood, notes, reference_sheet_prompt}]`, and `location_notes`. Includes a Location Scouting subsection with guidelines (only recurring/important; abstract spaces allowed; `has_locations: false` valid when no recurring settings exist). Two new locations appear in the worked example so the model has a concrete pattern to follow.

### `execution/research_scriptwriter.py`

`locations: dict = None` threaded through:

- `generate_production_table` signature
- `_generate_single_batch_6phase` signature (and forwarded to both `build_storyboard_prompt` and `build_dp_prompt` inside)
- `_generate_single_batch_3phase` signature (kept for parity with the now-dead 3-phase path)
- Three call sites inside the orchestrator: small-narration single batch, large-narration `process_batch` worker, coverage retry block

### `execution/server.py`

- **`/api/suggest-cast`** — splits the single LLM response into `cast_data` and `locations_data` payloads. Old call sites that only consumed `cast_data` continue to work; new frontend reads both.
- **`/api/generate-production-table`** — reads `locations = data.get('locations')` and threads to both the streaming worker and the legacy synchronous path.
- **`/api/generate-location-reference`** — new endpoint, mirror of `/api/generate-cast-portrait`. Generates a single 2×3 grid for one location at 16:9 / 2K, rehosts under `references/{project_id}/location/…` in Firebase Storage.
- **`/api/generate-location-references-batch`** — new endpoint, mirror of `/api/generate-cast-portraits-batch`. Parallelizes over 5 worker threads (same as cast). Each location's `reference_sheet_prompt` field is the input; rehosts each result.
- **`/api/visuals/generate-image`** — new `location_refs` field in the request body. Each entry's `images` list is resolved through `resolve_image_input` (URL → base64) the same way character refs are. Threaded to `generate_scene_image` as `location_refs=…`.

### `execution/gemini_client.py`

- **`generate_scene_image`** — new `location_refs` parameter. New "2b. Location references" section in the parts assembly: for each location ref, a labeled instruction part ("LOCATION: \"…\" (Environment Reference) …") followed by up to 2 image bytes. Then a `LOCATION BINDING` part telling the model that when the scene mentions a named setting, match materials/palette/geometry/lighting from the reference but follow the prompt for camera angle/framing.
- Log line extended with `locations=[…]` summary alongside the existing `chars=[…]` summary.

### `ui/index.html`

State:
- New `currentLocations` global (declared next to `currentCast`, shape documented in inline comment).
- New `visualsLocations = []` global (parallel to `visualsCharacters`).

HTML panel (inserted directly below the cast panel block):
- `#locationsPanel` with same structure as `#castPanel`: title, info tooltip, approved badge, none-message, cards container, action row (Add Location / Generate All / Approve).

JS block (inserted between `syncCastToVisualsCharacters` and `showSuggestCastButton`):
- `renderLocationsPanel(locationsData)` — renders cards with name, description (textarea), environment_type (select: interior / exterior / abstract / vehicle / other), mood, notes, reference grid thumbnail + Generate button. `_identityHash` outdated badge.
- `addLocation` / `removeLocation` / `readLocationsFromUI` / `approveLocations`
- `buildLocationReferencePrompt(loc, styleSummary)` — client-side prompt builder that adapts the angle list to `environment_type`. Phase 1's lesson applied from the start: never re-use a stale prompt.
- `generateReferenceForLocation(idx)` and `generateAllLocationReferences()` — same pattern as cast generation, rebuild prompt on every call.
- `syncLocationsToVisualsLocations()` — pushes generated grids into `visualsLocations` (used by scene auto-assignment and request body).

Scene cards (in `renderVisualsScenes`):
- New "Locations: …" header + checkbox panel directly below the Characters selector. Same toggleable header, same strict-membership semantics from Phase 1.2 (empty = none).
- Scene init now includes `selectedLocations: existing?.selectedLocations || []`.

Auto-assignment (in the post-production-table block at line ~8183):
- For each scene without an existing `selectedLocations`, scan `first_frame_prompt + script_beat` text for location names. If no name match, fall back to description-keyword overlap (same fallback strategy as cast).

Toggle handlers:
- `toggleSceneLocSelector(idx)` and `toggleSceneLocation(idx, name, checked)` — parallel to the cast handlers.

Request body:
- `buildImageRequestBody(idx)` now includes `location_refs: getStructuredLocations(idx)`.
- `getStructuredLocations(sceneIdx)` is the locations equivalent of `getStructuredCharacters` — strict membership, up to 2 images per location, `ref_mode: 'environment'`.

Persistence:
- `gatherProjectState` writes `locations_data: currentLocations || null`.
- `restoreProjectState` reads `project.locations_data`, calls `renderLocationsPanel`, flips the approved badge if applicable, and runs `syncLocationsToVisualsLocations`.

Suggest button:
- Label updated to "Suggest Cast & Locations from Script".
- `suggestCast` reads `data.locations_data` from the response and renders both panels.

Production-table dispatch:
- `requestBody.locations = currentLocations` (gated on `has_locations && locations.length > 0`) added next to the existing cast gate. `readLocationsFromUI()` runs first to pick up any unsaved edits.

---

## Phase 3 — Upload Support

Layered on top of Phases 1 and 2. Cast and locations both gain user upload.

### `execution/gemini_client.py`

- **`analyze_image_for_identity(image_data, kind)`** — new function. Takes a single base64 data URI or HTTPS URL, returns `{identity_text, style_summary}`. The prompt branches on `kind` (`'character'` describes wardrobe / features / props; `'location'` describes geometry / materials / palette / mood). Both branches explicitly instruct the model to omit style language so the extracted prose is suitable for grounding the production pipeline regardless of how the image was rendered.
- HTTPS URL handling pulls bytes via `requests` (15s timeout) and reads MIME from `Content-Type` header.

### `execution/server.py`

- **`/api/analyze-uploaded-reference`** — new endpoint. Accepts `{image_url|image_b64, kind, style_summary, project_id}`. Calls `analyze_image_for_identity`. Returns `{identity_text, style_summary, style_mismatch}`. The mismatch flag uses a keyword-overlap heuristic (Jaccard-ish on tokens longer than 3 chars, threshold 30%) against the project's approved style. Conservative — false positives are fine since the user can just dismiss the warning.
- **`/api/restyle-reference`** — new endpoint. Accepts `{kind, name, identity_text, style_images, style_mode, style_summary, project_id, model}`. Builds the same reference-sheet prompt the client-side helpers would (one for character, one for location), runs through `generate_scene_image`, rehosts to the appropriate folder (`references/{project_id}/character|location`). Result replaces the `portraits.reference_sheet` / `references.reference_sheet` slot — uploaded ref is untouched, `active_ref` flips to `'generated'`.
- `analyze_image_for_identity` added to the `from gemini_client import (…)` block.

### `ui/index.html`

Data model — three new fields on every cast member and every location:
- `uploaded_ref: {url, blob_path} | null`
- `active_ref: 'generated' | 'uploaded' | null` (null is interpreted as 'generated' when only generated exists, 'uploaded' when only uploaded exists)
- `_styleWarning: bool`

Card rendering (both `renderCastPanel` and `renderLocationsPanel`):
- Two-slot thumbnail strip showing both generated and uploaded refs if present. The active slot gets a CSS `active-ref` border highlight.
- Active-ref radio toggle (Generated / Uploaded), each disabled when its slot is empty.
- Style-mismatch warning banner with one-click Restyle button (renders only when `_styleWarning` is true).
- Upload button next to the Generate button. Opens a hidden file input (`accept="image/png,image/jpeg,image/webp"`).

Handlers:
- `uploadReferenceForCharacter(idx, file)` / `uploadReferenceForLocation(idx, file)` — reads the file to base64, posts to the existing `/api/upload-reference-image` (reused, no contract change), then posts to `/api/analyze-uploaded-reference`. On success: stores `uploaded_ref`, sets `active_ref = 'uploaded'`, sets `_styleWarning` from the response. If Vision returned non-empty `identity_text` AND the textarea is currently blank, it prefills the field. Triggers autosave.
- `setActiveCastReference(idx, source)` / `setActiveLocationReference(idx, source)` — pure state change, re-renders, autosaves.
- `restyleUploadedReference(idx, kind)` — posts to `/api/restyle-reference` with the current identity text + project style. On success: writes result into the generated slot, flips `active_ref` to `'generated'`, clears `_styleWarning`. The upload remains.

Read functions:
- `readCastFromUI` and `readLocationsFromUI` now preserve `uploaded_ref`, `active_ref`, and `_styleWarning` on round-trip.

Sync functions:
- `syncCastToVisualsCharacters` and `syncLocationsToVisualsLocations` consult `active_ref` to decide which URL goes into `visualsCharacters` / `visualsLocations` (and therefore into scene-generation request bodies). If the active slot is empty, falls back to whichever slot is populated.

Persistence:
- The three new fields ride along on `cast_data` / `locations_data` since `gatherProjectState` already passes the full objects through; no schema change needed in the project doc.

### `ui/style.css`

New `.ref-slot` + `.ref-slot.active-ref` rules — 2px transparent border by default, accent-color border when active. Provides the visual cue for which thumbnail the scene generation will use.

---

## Files Modified

| File | Phases |
|---|---|
| `ui/index.html` | 1, 2, 3 |
| `execution/research_templates.py` | 2 (+ small Phase 1.3 spillover in `_build_cast_section`) |
| `execution/research_scriptwriter.py` | 2 |
| `execution/server.py` | 2, 3 |
| `execution/gemini_client.py` | 2, 3 |
| `ui/style.css` | 3 |

No new files (no new modules, no new SQL, no migrations). No new dependencies in `requirements.txt`.

---

## Tests

```
pytest tests/  →  157 passed, 2 pre-existing failures, 1 pre-existing error
```

The two failures (`test_production_pipeline_6phase_tags_stages`, `test_generate_content_no_config_when_all_none`) and one error (`test_research_workflow_ui`) all reproduce on `main` without these changes — they are stale mocks / Playwright setup issues, not regressions.

Python syntax validated on every backend file via `ast.parse`.

---

## Risk and Rollback

- **Schema additive.** `locations_data` is a new field on the project doc; old projects without it skip the panel render. `uploaded_ref` / `active_ref` / `_styleWarning` on cast/location items are new optional fields ignored by older code paths.
- **`/api/suggest-cast` payload shape change.** New `locations_data` field added alongside `cast_data`. Old clients reading only `cast_data` keep working (the cast portion is unchanged).
- **Storage cost.** Uploaded refs persist in Firebase Storage indefinitely (Phase 3 plan flagged this — a project-delete cleanup task is out of scope and tracked for later).
- **LLM behavior.** The extended suggest-cast prompt may occasionally produce malformed JSON if the model gets confused by the larger schema; the parser raises and returns 500, the frontend surfaces the alert, the user retries. Acceptable failure mode.
- **Rollback path.** Revert these six files. No data migration. Saved `cast_data` with `appears_in_beats` stripped is forward-compatible with the old renderer (the field is optional in the prompt builder). Saved `locations_data` is just ignored by older code.
