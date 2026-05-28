# Phase 2 — Locations Feature

**Created:** 2026-05-28
**Status:** Planned (depends on Phase 1)
**Estimated scope:** Backend + frontend. New feature mirrored on cast end-to-end.

## Context

Recurring settings ("the lab", "the garden", "the warehouse") currently exist only as free text inside each shot's `first_frame_prompt`. Two consequences:

1. **No visual consistency anchor across shots.** Two scenes in the same lab will be rendered from scratch each time, with no shared reference for materials, layout, or color palette.
2. **Users can't curate locations.** There's no list of unique settings to review, no way to lock a look before generation starts, no per-location reference grid.

Phase 2 adds a structured Locations layer that mirrors the Cast feature end-to-end: LLM suggestion bundled into the existing cast call, 2×3 reference grid generation, per-scene multi-select auto-assigned from production-table text, and persistence on the project doc.

Locations are **not** uploaded by the user in this phase — that's Phase 3. Here we only support LLM-suggested locations and AI-generated 2×3 grids.

## Scope

**In scope**
- Extend `/api/suggest-cast` LLM call to also return `locations[]` (one call, two outputs).
- Add `_build_locations_section(locations, context)` to `research_templates.py`, inject into storyboard + DP prompts so the production pipeline knows location identity.
- New `Locations` panel in UI (parallel to Cast). Add/remove/edit cards with name, description, mood/environment hints, notes.
- New endpoint to generate location 2×3 grids (one per location, LLM-chosen angles).
- Per-scene location multi-select checkboxes (parallel to character checkboxes), auto-filled from production-table environment text.
- Persistence: `locations_data` field on the project doc, parallel to `cast_data`.
- Wire location refs into `/api/visuals/generate-image` so they reach the image model alongside character portraits.

**Out of scope**
- User uploads (Phase 3).
- Multi-photo grid assembly (deferred).
- Location video refs (deferred).
- Separating the LLM call into its own endpoint (intentionally bundled).

## Architectural fit

Mirror cast at every layer. If something exists for cast, do the parallel thing for locations:

| Cast | Locations equivalent |
|---|---|
| `currentCast` | `currentLocations` |
| `castPanel` HTML section | `locationsPanel` HTML section |
| `renderCastPanel` | `renderLocationsPanel` |
| `addCastMember` / `removeCastMember` | `addLocation` / `removeLocation` |
| `readCastFromUI` | `readLocationsFromUI` |
| `currentCast.cast[*].portraits.reference_sheet` | `currentLocations.locations[*].references.reference_sheet` |
| `_build_cast_section` (`research_templates.py:2350`) | `_build_locations_section` (new) |
| `/api/generate-cast-portrait` (`server.py:1809`) | `/api/generate-location-reference` |
| `/api/generate-cast-portraits-batch` (`server.py:1889`) | `/api/generate-location-references-batch` |
| `visualsCharacters` | `visualsLocations` |
| Scene `selectedCharacters` | Scene `selectedLocations` |
| Auto-assignment from `character_outfit` text | Auto-assignment from environment text in `first_frame_prompt` |

## Detailed changes

### Backend — `execution/research_templates.py`

**Extend `build_cast_suggestion_prompt`** (currently around line 4241-4370+).

Add a `locations` section to the requested JSON output. Append to the existing instructions, do not replace cast logic. New schema returned:

```json
{
  "title": "...",
  "has_characters": true,
  "cast": [...],
  "casting_notes": "...",
  "has_locations": true,
  "locations": [
    {
      "name": "The Lab",
      "description": "A cluttered chemistry lab with brass fixtures, weathered wooden benches, and afternoon light through tall windows.",
      "environment_type": "interior",
      "mood": "studious, slightly chaotic",
      "appears_in_beats_hint": [1, 2, 4, 6],
      "notes": "Recurring main setting. Should feel lived-in.",
      "reference_sheet_prompt": "Wide establishing shot of cluttered chemistry lab with brass fixtures...; mid-angle from doorway...; close detail of bench-top equipment...; alt POV from window side...; reverse angle from far wall...; close on glassware. Arrange in 2x3 grid. Maintain consistent lighting and palette across all six panels."
    }
  ],
  "location_notes": "Story revisits the lab heavily; garden appears only twice."
}
```

Notes on the schema:
- `environment_type`: free string from a hinted set (`interior` | `exterior` | `abstract` | `vehicle` | `other`) — used to flavor the reference prompt template.
- `appears_in_beats_hint`: explicitly named with `_hint` suffix so it's clear this is an LLM guess. Per the cast lesson, we do **not** use this to drive auto-assignment — that comes from production-table text. Kept for human reference only. Optional.
- `reference_sheet_prompt`: pre-written by the suggesting LLM, six panels as a single 2×3 grid. Mirrors how cast's `portrait_prompts.reference_sheet` works.

**Add `_build_locations_section(locations, context)`** — new function, mirror of `_build_cast_section` at line 2350-2403.

Two contexts:
- `context='storyboard'`: list each location with description so the Storyboard Artist knows what each named location looks like and keeps shots set there visually consistent.
- `context='dp'`: similar but emphasizes lighting/palette continuity per location.

**Inject into prompts:**
- `build_storyboard_prompt` (around line 3788-3947): add `locations_section = _build_locations_section(locations, 'storyboard')` and insert it into the template near where cast is inserted.
- `build_dp_prompt` (around line 4377-4544): same with `context='dp'`.

Both functions need a new `locations` parameter threaded through their call sites.

### Backend — `execution/server.py`

**`/api/suggest-cast`** (around line 1734-1800):
- Parse `locations` and `has_locations` from the LLM response alongside the existing cast extraction.
- Return both in the response payload: `{cast_data: {...}, locations_data: {...}}`.

**New `/api/generate-location-reference`** (mirror of `/api/generate-cast-portrait` at line 1809-1887):
- Body: `{prompt, location_name, model, project_id, style_images, style_mode, style_summary}`.
- Same model call path as cast portrait generation. Same Firebase Storage rehosting.

**New `/api/generate-location-references-batch`** (mirror of `/api/generate-cast-portraits-batch` at line 1889-2000ish):
- Body: `{locations, model, project_id, style_images, style_mode, style_summary}`.
- Iterates the locations array, calls the reference-sheet path for each, returns per-location results.

**`/api/visuals/generate-image`** (around line 5133-5192):
- Accept new `location_refs` array in body: `[{name, images: [base64...], ref_mode: 'environment'}]`.
- Resolve any URLs to base64 (reuse the existing helper that handles cast images at line 5150-5156).
- Pass into `generate_scene_image` (see next section).

**Routing path through production:**
- `/api/generate-production-table` (`server.py:3788` and around 4012) — add `locations=data.get('locations')` to the call and thread it down. The pipeline orchestrator (currently at server.py:4602 and 4721) passes cast to each phase; same treatment for locations.

### Backend — `execution/gemini_client.py`

**`generate_scene_image`** (around line 1259-1419):
- Add a `location_refs` parameter (default empty list).
- Mirror the cast injection block (line 1362-1401). For each location ref, append its image bytes as `Part.from_bytes()` and append a labeled instruction line ("Use this image as the environment reference for shots set in [LOCATION NAME]"). The binding instruction near line 1390-1401 should be extended to mention location refs alongside character refs.

### Frontend — `ui/index.html`

Add `currentLocations` global next to `currentCast` (declaration around line 2283):
```js
let currentLocations = null; // {has_locations, locations: [{name, description, environment_type, mood, notes, reference_sheet_prompt, references: {reference_sheet: {url, blob_path}} | null, _identityHash}], location_notes}
```

**HTML panel** — add a `locationsPanel` block parallel to `castPanel` at line 1596. Same layout: title, info tooltip, approved badge, "no locations" message, cards container, action buttons (Add Location, Suggest Locations, Generate All References).

**Render function** — `renderLocationsPanel(locationsData)` mirrors `renderCastPanel` (line 6829-6901). Per-card fields:
- Name (input)
- Description (textarea — this is the "Visual Identity" equivalent)
- Environment type (select: interior/exterior/abstract/vehicle/other)
- Mood (input)
- Notes (input)
- Reference sheet thumbnail + Generate / Regenerate button + spinner

Apply the Phase 1 lesson here from the start: the location reference prompt is rebuilt **client-side** from the current description on every regen. Same pattern as `buildReferenceSheetPrompt` in Phase 1, adapted for locations:
```js
function buildLocationReferencePrompt(loc, styleSummary) {
    const stylePrefix = styleSummary ? `${styleSummary}. ` : '';
    const desc = (loc.description || '').trim();
    const envHint = loc.environment_type ? ` (${loc.environment_type})` : '';
    return `${stylePrefix}Create a 2x3 reference grid for the location "${loc.name}"${envHint}: ${desc}. ` +
        `Six panels arranged in two rows of three. Choose six diverse angles that best capture this specific location — ` +
        `for interiors prefer wide / mid / detail / alt-angle / reverse / close-detail; ` +
        `for exteriors prefer establishing wide / mid POV / detail / alt time-of-day / weather variation / close detail; ` +
        `for abstract spaces prefer four atmospheric variations and two anchoring details. ` +
        `Maintain perfect spatial and lighting consistency across all six panels. Clean panel separation, even spacing.`;
}
```

**Add / remove / read / approve** — parallel to cast functions at line 6903-6971.

**Generate reference functions** — `generateReferenceForLocation(idx)` and `generateAllLocationReferences()`, parallel to `generatePortraitForCharacter` / `generateAllPortraits` (line 7007-7145). Same Firebase Storage path. Same `_identityHash` outdated-warning pattern.

**Sync to visuals layer** — `syncLocationsToVisualsLocations()` parallel to `syncCastToVisualsCharacters` (line 7147-7176). Pushes into a new `visualsLocations` global array. Stored on scenes as `selectedLocations` array.

**Per-scene checkbox UI** — extend the scene card render (around line 8749-8770) to add a Locations selector below the Characters selector. Same toggleable header, same checkbox semantics from Phase 1 (empty = none).

**Auto-assignment** — extend the post-production-table block at line 8183-8229. For each scene, scan `first_frame_prompt` text for location names and assign matched names to `selectedLocations`. Same matching strategy as cast (name match → optional fallback to description-keyword match).

**Persistence** — add `locations_data: currentLocations || null` to `gatherProjectState` (around line 12094). Add the restore block in `restoreProjectState` after the cast restore (after line 11779). The server's `/api/projects/<id>` PUT handler accepts arbitrary fields (server.py:2499-2546) so no backend persistence change is needed.

**Scene image request** — wherever the body for `/api/visuals/generate-image` is built (search for `buildImageRequestBody` and `generateSceneImage`), add `location_refs: getStructuredLocations(idx)` parallel to the existing `characters` field. `getStructuredLocations(idx)` is the locations equivalent of the cast helper at line 8647-8661.

## Files modified

- `execution/research_templates.py`
- `execution/server.py`
- `execution/gemini_client.py`
- `ui/index.html`

No new files. No new modules.

## Verification

1. Create a new project. Run research → script. The script should mention at least 2 distinct locations.
2. Trigger Suggest Cast. Confirm response includes both `cast_data` and `locations_data`. The new Locations panel appears below the Cast panel.
3. Edit a location's description. Click Generate. Confirm the 2×3 reference grid generates and the panels reflect the description (Phase 1 lesson applied — no stale-prompt bug).
4. Click Generate All Location References. Confirm one grid per location.
5. Run production table. Open Visuals tab.
6. Confirm each scene has both Characters and Locations selectors. Confirm boxes are auto-checked based on the actual production-table environment text (empty when no match — same fix as Phase 1).
7. Generate a scene image. Confirm the network request body includes both character refs and location refs. The generated image should respect both.
8. Save and reload the project. Confirm `locations_data` round-trips correctly (panels restore, refs preserved).
9. Switch projects. Confirm location state is per-project (no cross-contamination).

## Risk and rollback

- Schema additive: `locations_data` is a new field. Old projects without it simply skip the panel render.
- LLM behavior: the extended suggest-cast prompt might occasionally return malformed JSON if the model gets confused by the bigger schema. Wrap the locations extraction in try/except — if parsing fails, return cast only and log a warning.
- Auto-assignment is a hint, not a hard requirement. If matching fails, the boxes stay empty (Phase 1 behavior) and the user can manually pick.
- Rollback path: revert the four files. No data migration needed (locations_data on existing projects is just ignored if the code that reads it isn't there).
