# Cast Fixes + Locations Feature + Upload Support

**Created:** 2026-05-28
**Status:** Planned, not yet implemented
**Scope:** 3 phases — cast bug fixes, new Locations feature, upload support for both

## Context

Three intertwined issues surfaced during cast testing:

1. **Regenerating a character portrait after editing Visual Identity does not use the edited prompt.** Users see the same character come back. Root cause: the regen path reads `portrait_prompts.reference_sheet`, which is baked once at suggest-cast time and never refreshed when `visual_identity` is edited.
2. **Per-scene character reference checkboxes auto-check every character** even when none of them appear in that shot. Root cause: empty `selectedCharacters` array is rendered as "all checked" (`ui/index.html:8762`) and treated as "send all refs" in the generation request (`ui/index.html:8651`).
3. **No structured "Locations" system exists.** Environments live as free text inside the production table's `first_frame_prompt`. There is no way to lock visual consistency across multiple shots in the same setting, or attach a location reference grid the way cast portraits anchor characters.

User also wants to **upload their own cast sheets and location grids** when the LLM-generated ones don't match what they have in mind, or when working from brand assets / real-location photography.

## Architectural decisions (locked 2026-05-28)

| Topic | Decision |
|---|---|
| Cast `Appears in Beats` field | Remove — production table per-shot `character_outfit` is the truth. The field was a misleading LLM guess that never drove anything. |
| Cast empty selection semantic | Empty = "no known cast member needs a reference for this shot" (no boxes checked, no refs sent). User can manually check any box. |
| Locations detection | Extend the existing `/api/suggest-cast` call to also return `locations[]` in the same LLM response. One call, two outputs. |
| Locations timing | Pre-production-table, same as cast. Refs generate in parallel with other work. After production table runs, auto-assign per scene from environment text. |
| Locations grid layout | LLM chooses the 6 angles per location (indoor vs outdoor vs abstract). One 2×3 grid image per location. |
| Per-scene location assignment | Multi-select like cast (most scenes have one; allow more for tracking shots / montages). |
| Upload format | Single pre-made sheet image (one file = the whole grid). No multi-photo assembly for v1. |
| Upload coexistence | Generated and uploaded both stored. User toggles which is the active ref via per-card switch. |
| When uploads are allowed | Anywhere/anytime — creation, after generation, mid-project swap. Also "blank card + upload" path that skips LLM suggestion. |
| `visual_identity` for upload-only items | Auto-extract via Gemini Vision (user can edit after). Production prompts always have text to work with. |
| Style mismatch | Warn the user and offer a one-click Restyle button. No auto-restyle. No silent acceptance. |
| Location refs | Same upload behavior as cast. No video ref for v1. |
| Storage | Firebase Storage under the project, same path convention as generated assets. |

## Phase order

| Phase | File | Why this order |
|---|---|---|
| 1. Cast bug fixes | [`phase_1_cast_fixes.md`](phase_1_cast_fixes.md) | Smallest, highest user-visible value, validates the empty-checkbox fix before locations layer on top. |
| 2. Locations feature | [`phase_2_locations.md`](phase_2_locations.md) | Mirrors cast end-to-end. Builds on Phase 1's fixed checkbox semantic. No uploads yet. |
| 3. Upload support | [`phase_3_uploads.md`](phase_3_uploads.md) | Applies to both cast and locations once both exist. Reuses existing upload helper + Vision wrappers. |

Each phase is self-contained and shippable. Test after each before starting the next.

## Files touched (consolidated index)

**Frontend:**
- `ui/index.html` — every phase touches it. Cast panel (`6829-7176`), per-scene selectors (`8749-8770`), auto-assignment (`8183-8229`), project state I/O (`11513-12110`).

**Backend:**
- `execution/server.py` — `/api/suggest-cast` (`1734`), `/api/generate-cast-portrait` (`1809`), `/api/generate-cast-portraits-batch` (`1889`), `/api/visuals/generate-image` (`5133`), `/api/upload-reference-image` (`1300`), `/api/analyze-style-images` (`1501`).
- `execution/research_templates.py` — `build_cast_suggestion_prompt` (`4241-4370+`), `_build_cast_section` (`2350-2403`), `build_storyboard_prompt` (`3788`), `build_dp_prompt` (`4377`).
- `execution/gemini_client.py` — `analyze_style_from_images` (`762-830`), `generate_scene_image` (`1259-1419`).

**Persistence shape (project doc on Firestore):**
- Existing: `cast_data: {has_characters, cast: [...]}`
- Added in Phase 2: `locations_data: {has_locations, locations: [...]}`
- Added in Phase 3 (on cast members and locations): `uploaded_ref: {url, blob_path}`, `active_ref: 'generated' | 'uploaded'`

## Out of scope (deferred)

- Multi-photo upload + auto-assembly into a grid
- Reference video clips for locations
- Auto-restyle on upload (always-on)
- Locations API endpoint separated from cast (kept bundled for v1)
- Reworking `appears_in_beats` to be derived from the production table (just removing the field; if we want a "Appears in Scenes" readout later, it can be a separate post-pipeline computation)

## Verification across all phases

After each phase, run a project end-to-end:

1. Create a new project with a script that has 2–3 recurring characters and 2–3 distinct locations.
2. Run research → script → cast (and locations from Phase 2 onward) → production table → visuals.
3. Verify:
   - Phase 1: edit a Visual Identity, regen, confirm new character matches the edit. Open visuals tab, confirm characters NOT in a shot show unchecked boxes for that scene.
   - Phase 2: locations appear in their own panel; 2×3 grids generate; per-scene location checkboxes auto-fill from production table; scene images use location refs.
   - Phase 3: upload a custom sheet for one cast member + one location. Toggle active ref. Verify scene generation uses the active ref. Trigger Restyle on a deliberately mismatched upload.
