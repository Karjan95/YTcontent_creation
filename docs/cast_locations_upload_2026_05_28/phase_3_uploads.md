# Phase 3 — Upload Support for Cast and Locations

**Created:** 2026-05-28
**Status:** Planned (depends on Phases 1 and 2)
**Estimated scope:** Backend (new Vision wrapper + one new endpoint) + frontend (upload UI on every cast and location card).

## Context

Users want control over identity references when the LLM-generated sheet doesn't match what they have in mind, or when they're working from existing brand assets, real-character photography, or real-location photography. Generation alone is too restrictive.

Phase 3 adds upload support to both cast members and locations using a single sheet image per item (one file = the whole grid, already arranged). Generated and uploaded refs coexist; the user toggles which is active for scene generation. When a user uploads a card with no `visual_identity` / `description` typed, Gemini Vision auto-extracts text from the image so the production pipeline always has prose grounding. When the uploaded image's style doesn't match the project's approved style, a warning appears with a one-click Restyle option.

## Scope

**In scope**
- Upload button on every cast and location card (rendered by the panel functions added in Phases 1 and 2).
- Reuse the existing `/api/upload-reference-image` endpoint (`execution/server.py:1300-1333`) for the actual file handling.
- New `active_ref` field per cast member / location: `'generated' | 'uploaded'`. Toggle UI on each card.
- New `uploaded_ref: {url, blob_path}` field per cast member / location.
- Auto-extract `visual_identity` (cast) or `description` (locations) via Gemini Vision when the field is blank on upload.
- Style mismatch detection: compare uploaded image's analyzed style summary to `approvedStyle.style_summary`. Warn + offer Restyle button.
- Restyle action: regenerate the reference sheet in the project's style, using the uploaded image's auto-extracted identity/description text. Stored as a new generated ref (does not delete the upload).
- Blank-card upload flow: "Add Character" / "Add Location" + immediate upload, skipping the LLM suggestion step.

**Out of scope**
- Multi-photo upload + auto-grid assembly.
- Reference video clips.
- Auto-restyle on upload (always-on). User opts in per item.
- Cropping / image editing in the UI before upload.
- Bulk upload from a folder.

## Architectural fit

Reuse existing primitives:

| Need | Reused helper | File:line |
|---|---|---|
| Upload base64 → Firebase Storage signed URL | `/api/upload-reference-image` | `execution/server.py:1300-1333` |
| Server-side blob upload from path | `upload_to_storage()` | `execution/server.py:219-243` |
| Gemini Vision for image analysis | `analyze_style_from_images()` | `execution/gemini_client.py:762-830` |
| Approved style storage | `approvedStyle.style_summary` | `ui/index.html:2278` |
| Scene-gen reference image injection | `generate_scene_image()` character ref block | `execution/gemini_client.py:1337-1419` |

New code is limited to: one Vision wrapper for identity/description extraction, one Restyle endpoint, one upload-button + active-toggle UI block per card type.

## Detailed changes

### Data model

Per cast member (existing object — add fields):
```js
{
  name, role, visual_identity, notes,
  portrait_prompts: {...},                       // existing — for generated path
  portraits: { reference_sheet: {url, blob_path} | null },   // existing — generated ref
  uploaded_ref: { url, blob_path } | null,       // NEW
  active_ref: 'generated' | 'uploaded',          // NEW (default 'generated')
  _identityHash, _styleWarning                   // existing + NEW _styleWarning flag
}
```

Per location: same three new fields (`uploaded_ref`, `active_ref`, `_styleWarning`) on the location object defined in Phase 2.

The `getStructuredCharacters` / `getStructuredLocations` helpers used in scene image requests must read from `active_ref` to decide which URL to send:
```js
const url = char.active_ref === 'uploaded'
    ? char.uploaded_ref?.url
    : char.portraits?.reference_sheet?.url;
```

### Backend — `execution/gemini_client.py`

**New function `analyze_image_for_identity(image_b64, kind)`**

Mirror of `analyze_style_from_images` (line 762-830) but with a different prompt depending on `kind`:
- `kind='character'`: prompt asks Gemini to describe the figure's visual identity in terms suitable for the production pipeline — wardrobe, distinctive features, body type, props, anything that needs to be consistent across shots. Plain prose. No style description.
- `kind='location'`: prompt asks Gemini to describe the setting — geometry, materials, color palette, props, lighting character, mood. Plain prose. No style description.

Returns `{identity_text: str, style_summary: str}`. The `style_summary` field reuses the existing style analysis logic so we get both extractions in one call.

### Backend — `execution/server.py`

**New `/api/analyze-uploaded-reference`**

Body: `{image_url | image_b64, kind: 'character' | 'location'}`.
- Calls `analyze_image_for_identity` from `gemini_client.py`.
- Returns `{identity_text, style_summary, style_mismatch: bool}`.
- `style_mismatch` is computed by comparing the returned `style_summary` against the project's approved `style_summary` (passed in the request body or derived from project doc) via keyword overlap. Threshold: fewer than 30% of meaningful keywords shared → mismatch.

**New `/api/restyle-reference`**

Body: `{image_url, kind: 'character' | 'location', name, identity_text, style_images, style_mode, style_summary, project_id, model}`.
- Builds a reference-sheet prompt using the same client/server template as Phases 1 and 2, but with `identity_text` as the identity portion.
- Calls the same generation path as `/api/generate-cast-portrait` (line 1809) or `/api/generate-location-reference` (Phase 2).
- Returns the new generated ref's URL and blob path.
- The result is stored under `portraits.reference_sheet` (cast) or `references.reference_sheet` (location) — i.e. it replaces the generated ref. The `uploaded_ref` is untouched. `active_ref` flips to `'generated'`.

### Frontend — `ui/index.html`

**Card UI additions** (in both `renderCastPanel` and `renderLocationsPanel`):

For each card, in the reference section:
- Upload button (file picker, accept image/png, image/jpeg, image/webp). Below the existing Generate button.
- Two-slot thumbnail strip showing both generated and uploaded refs, with a radio toggle below picking which is active. Slots are empty/disabled when not present.
- Warning banner above the active toggle if `_styleWarning` is true: "This upload doesn't match your project style." + a "Restyle" button.

**Upload flow** (`uploadReferenceFor[Character|Location](idx, file)`):
1. Read file as base64.
2. POST to `/api/upload-reference-image` to land it in Firebase Storage and get back `{url, blob_path}`.
3. Set `currentCast.cast[idx].uploaded_ref = {url, blob_path}` (or location equivalent).
4. POST to `/api/analyze-uploaded-reference` with the URL and the project's `style_summary`.
5. If response `identity_text` is non-empty AND the card's `visual_identity` / `description` is currently blank, prefill it.
6. If response `style_mismatch === true`, set `_styleWarning = true` on the item.
7. Set `active_ref = 'uploaded'` (the act of uploading implies intent to use it).
8. Re-render the panel. Autosave.

**Toggle handler** (`setActiveReference(idx, source)`):
- Simple state change. `currentCast.cast[idx].active_ref = source`. Re-render. Autosave.

**Restyle handler** (`restyleUploadedReference(idx, kind)`):
- Reads the card's `uploaded_ref.url` and `visual_identity` / `description`.
- POSTs to `/api/restyle-reference`.
- On success, stores result under `portraits.reference_sheet` (or location equivalent), flips `active_ref` to `'generated'`, clears `_styleWarning`.
- Re-render. Autosave.

**Blank-card upload flow**:
- "Add Character" / "Add Location" creates a card with empty fields (existing behavior from Phases 1 and 2).
- User clicks Upload on the empty card. Standard upload flow runs. Auto-extracted `visual_identity` / `description` prefills the textarea. User can edit before approving.

**Persistence** — `gatherProjectState` and `restoreProjectState` (around line 11513-12110 for the current snapshot) are already serializing the cast and location arrays. The new fields (`uploaded_ref`, `active_ref`, `_styleWarning`) are just additional keys that round-trip via the existing arbitrary-field merge. No schema work.

**Scene generation request bodies** — `getStructuredCharacters(idx)` (line 8647-8661) and the Phase 2 `getStructuredLocations(idx)` must consult `active_ref` when picking which image URL to attach to the request. Single-line change in each helper.

## Files modified

- `execution/gemini_client.py` — one new function.
- `execution/server.py` — two new endpoints.
- `ui/index.html` — upload UI, toggle UI, warning UI, four new JS functions (upload, set-active, restyle, blank-upload).

No new files, no new modules.

## Verification

1. Open an existing project with a generated cast.
2. On one cast card, click Upload and pick a custom character sheet PNG. Confirm:
   - The image lands in Firebase Storage.
   - The uploaded thumbnail appears next to the generated thumbnail.
   - The active toggle is now on "Uploaded".
   - If the card's Visual Identity was blank, it's auto-prefilled with extracted text.
   - If the uploaded style differs from the project style, a warning banner appears with a Restyle button.
3. Generate a scene image. Confirm the request includes the **uploaded** ref URL, not the generated one.
4. Toggle the active ref back to "Generated". Re-generate the scene image. Confirm now the **generated** ref is used.
5. Click Restyle on the warning banner. Confirm a new generated ref is produced in the project style and the active ref auto-flips to "Generated". Confirm the uploaded ref is still present.
6. Repeat 2–5 for a location.
7. Click "Add Character" → immediately Upload on the blank card. Confirm the card gets a name field still blank but the Visual Identity auto-fills from Vision. Confirm scene generation works.
8. Reload the project. Confirm `uploaded_ref`, `active_ref`, and `_styleWarning` round-trip.
9. Switch projects. Confirm uploaded refs do not leak across projects.

## Risk and rollback

- The Vision call adds latency (~2–4s) per upload. Show a spinner and disable the upload button while in flight.
- Gemini Vision may occasionally return empty `identity_text`. Don't overwrite an existing user-typed field; only prefill if blank.
- Style mismatch detection is heuristic (keyword overlap). False positives are acceptable because the user can dismiss the warning by toggling active ref or ignoring it. False negatives (mismatch missed) just means no warning — still safe.
- The `/api/upload-reference-image` endpoint is already in use for other features. Make sure we don't change its contract.
- Rollback: revert the three files. Existing data with `uploaded_ref` / `active_ref` fields is just ignored by older code paths (the scene-gen helpers fall back to the generated ref when `active_ref` isn't read).
- Storage cost: uploaded refs persist in Firebase Storage indefinitely. Consider a project-delete cleanup task later (out of scope for this phase).
