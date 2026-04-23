# Changelog: 3-Phase Production Pipeline, Style Enforcement & UI Enhancements

## Overview

This session implemented three major features:
1. **Three-Phase Production Pipeline** (Max Quality mode) — splits the single Gemini call into Director → Storyboard Artist → DP for higher quality prompts
2. **Character Rendering Identity** — fixes the core problem where prompts used "man"/"woman" instead of the actual character style (e.g., stick figures)
3. **Style Review Panel UX** — info tooltips, stale field detection, quality mode toggle

Plus one bug fix.

---

## Bug Fix

### `renderNarration()` null innerHTML error
- **File:** `ui/index.html`
- **Problem:** `document.getElementById('narrationList')` returned `null` because the element `narrationList` was removed from the HTML but still referenced in JavaScript. This caused "Cannot set properties of null (setting 'innerHTML')" when generating narration with "Analyze Transcript Style" mode.
- **Fix:** Replaced the dead reference with `container.innerHTML = ''` using the existing `narrationDisplay` element.

---

## Feature 1: Three-Phase Production Pipeline

### Concept

Previously, one Gemini call did everything: split narration into shots, design visuals, AND write first_frame/last_frame/veo prompts — all while juggling 3 roles (Director, Storyboard Artist, DP). This caused attention dilution and inconsistent quality.

The new "Max Quality" mode runs 3 sequential, focused Gemini calls within each batch:

```
Phase 1: DIRECTOR (Editorial Pass)
   Only decides: where to cut, duration, emotion, rationale
   NO visuals, NO prompts
         ↓
Phase 2: STORYBOARD ARTIST (Visual Composition)
   Receives: Director's shots + full original narration (story arc context)
   Adds: visual description, shot_size, visual_continuity_notes
   NO final prompts
         ↓
Phase 3: DIRECTOR OF PHOTOGRAPHY (Prompt Writer)
   Receives: storyboarded shots + full style_analysis + prompt schema
   Writes: first_frame_prompt, last_frame_prompt, veo_prompt
```

The existing "Fast" single-call mode is completely untouched. Users choose via a UI toggle.

### Files Changed

#### `execution/research_templates.py`

**Extracted pacing constants to module level:**
- `WORDS_PER_SECOND = 2.5`
- `PACING_INSTRUCTIONS` dict (5 tiers: Meditative → Frenetic)
- `WORDS_PER_SHOT_TARGETS` dict
- `build_production_prompt()` updated to reference module-level constants instead of local ones

**Added 3 new prompt builder functions (appended after `build_production_prompt()`):**

1. `build_director_prompt(narration_json, duration_minutes, shot_start_number, pacing_tier)`
   - Purely editorial — no style, no schema, no visuals
   - Prompt: "You are THE DIRECTOR. You do NOT design visuals. You do NOT write image prompts."
   - Output: `{"shots": [{shot_number, script_beat, duration, act, beat, emotion, directors_intent, cutting_rationale}]}`

2. `build_storyboard_prompt(director_shots, narration_json, style_intent)`
   - Receives Director's shots + full original narration for story arc context
   - Also receives character_description via `_build_character_section()` so visual descriptions use the correct character style
   - Prompt: "You are THE STORYBOARD ARTIST. You do NOT change cuts. You do NOT write final prompts."
   - Output: same shots enriched with `{visual, shot_size, visual_continuity_notes}`

3. `build_dp_prompt(storyboard_shots, style_analysis, aspect_ratio, title)`
   - Receives storyboarded shots + full style_analysis + prompt_schema
   - Reuses `_build_prompt_format_instructions()` for schema-based templates
   - Reuses the same visual style section + character identity injection as `build_production_prompt()`
   - Prompt: "You are THE DIRECTOR OF PHOTOGRAPHY. Your job is to write the final generation prompts."
   - Output: full production table with first_frame_prompt, last_frame_prompt, veo_prompt, continuity_notes, production_notes

#### `execution/research_scriptwriter.py`

**Updated imports** to include `build_director_prompt`, `build_storyboard_prompt`, `build_dp_prompt`.

**Added `_generate_single_batch_3phase()`** — same signature as `_generate_single_batch()` for drop-in compatibility:
- Phase 1: calls `build_director_prompt()` → `generate_content()` → parses shots
- Phase 2: calls `build_storyboard_prompt()` with director shots + original narration → parses enriched shots
- Phase 3: calls `build_dp_prompt()` with storyboard shots → parses final production table
- All 3 phases use `gemini-3.1-pro-preview` at temperature 0.1
- If any phase fails, returns `{"error": "Phase N (Role) failed: ..."}`

**Added `quality_mode` parameter to `generate_production_table()`:**
- Default: `"fast"` (existing single-call behavior)
- `"max_quality"`: routes to `_generate_single_batch_3phase()` instead
- Both small narration path and large narration batch path use `batch_fn` variable for routing
- Existing batching, merging, and renumbering logic unchanged

#### `execution/server.py`

- Reads `quality_mode = data.get('quality_mode', 'fast')` from request body
- Passes `quality_mode=quality_mode` to `generate_production_table()`

#### `ui/index.html`

- Added Quality Mode `<select>` dropdown (Fast / Max Quality) before the Generate button
- Added `updateQualityModeHint()` — updates hint text and cost badge dynamically
- Added `quality_mode` to the `generateProductionTable()` request body
- Status message shows "(3-Phase Max Quality)" or "(Fast)" during generation

---

## Feature 2: Character Rendering Identity

### Problem

When users uploaded stick figure style images, the style analysis correctly described the aesthetic ("2D vector-style, thick outlines, flat colors") but prompts still used "young man", "elderly male", "man" — because:

1. The style analysis prompt said "extract transferable aesthetic rules" but never asked what characters look like as rendered objects
2. No `character_description` field existed in the style_intent schema
3. The SUBJECT CORE template said `[Age, gender, body type]` which pushes toward real humans
4. No enforcement rule told Gemini to avoid generic human terms

### Fix

#### `execution/gemini_client.py`

Updated `_get_style_analysis_prompt()` — added **Part 2: Extract Character Rendering Identity**:
- Explicitly asks: "What do characters LOOK LIKE as rendered objects?"
- Asks for body proportions, facial features, wardrobe rendering style
- Requests a `character_description` paragraph that can replace "man"/"woman" in every prompt
- Provides examples for stick figure and photorealistic styles
- Added `character_description` field to the `style_intent` output JSON schema

#### `execution/research_templates.py`

**Added `_build_character_section(intent)` helper function:**
- Returns empty string if no `character_description` exists (backward compatible)
- Otherwise returns a mandatory block with the character template and strict rules:
  - "Do NOT use generic human terms like 'man', 'woman', 'person'"
  - "EVERY time a character appears, describe them using the character rendering style"
  - "Differentiate characters by clothing color, accessories, or size — NOT by realistic facial features"

**Injected character section into ALL production prompts:**
- `build_production_prompt()` (single-call / Fast mode)
- `build_storyboard_prompt()` (Phase 2 / Max Quality)
- `build_dp_prompt()` (Phase 3 / Max Quality)

#### `ui/index.html`

- Added **Character Description** textarea to Style Review panel (between Style Summary and the review grid)
- `showStyleReviewPanel()` populates it from `intent.character_description`
- `approveStyle()` reads it into the approved style object
- Added info tooltip: "Defines how ALL characters are rendered in every prompt. Replaces generic terms like 'man' or 'woman'."
- Included in stale field detection (gets orange border when Style Summary changes)

---

## Feature 3: Style Review Panel UX Enhancements

### Info Icons with Tooltips

#### `ui/index.html`

**Added `STYLE_FIELD_TOOLTIPS` constant** — maps each field ID to `{desc, good, bad}`:
- `reviewStyleSummary` → "The master style identity..."
- `reviewCharacterDescription` → "Defines how ALL characters are rendered..."
- `reviewDetailLevel` → "Controls how verbose/detailed each prompt will be..."
- `reviewSceneComplexity` → "Controls how rich backgrounds and environments are..."
- `reviewCameraLanguage` → "Defines camera techniques Gemini uses..."
- `reviewLighting` → "How light is described in each prompt..."
- `reviewSubjectFraming` → "How characters are positioned and composed..."
- `reviewWritingStyle` → "The language style used when writing prompts..."
- `reviewColorPalette` → "What colors Gemini uses in visual descriptions..."
- `reviewTexture` → "Surface quality and rendering finish..."
- `reviewMoodDefault` → "Emotional baseline for all prompts..."
- `schemaFieldsChecklist` → "Check which technical fields appear in prompts..."

**Added `injectInfoTooltips()` function:**
- Creates SVG info circle icons (i) next to each field label
- Hover triggers a tooltip with description + Good/Bad examples
- Tooltips styled with green (good) and red (bad) borders

### Stale Field Highlighting

#### `ui/index.html`

**Added `originalStyleSummary` global variable** — stores the Style Summary text when fields are populated.

**Added `initStaleDetection()` function:**
- `oninput` listener on Style Summary textarea → compares to `originalStyleSummary`
- If different, adds `stale-field` CSS class to all 10 intent fields (including Character Description)
- Per-field `oninput` listeners → remove `stale-field` from that specific field when manually edited
- Uses `data-staleInit` to prevent duplicate listener registration

**`showStyleReviewPanel()` updated:**
- Stores `originalStyleSummary` when panel opens
- Clears all `stale-field` classes on fresh data
- Calls `injectInfoTooltips()` and `initStaleDetection()`

#### `ui/style.css`

**Added tooltip styles:**
- `.info-tooltip-trigger` — relative positioning, cursor:help
- `.info-icon` — color #666, hover → primary purple
- `.info-tooltip` — absolute positioned above trigger, 320px wide, dark background (#1e1e2e), purple border, z-index 1000, hidden by default, shown on hover
- `.tooltip-example.good` — green left border (#10b981), green-tinted background
- `.tooltip-example.bad` — red left border (#ef4444), red-tinted background
- `.tooltip-label` — bold weight

**Added stale field style:**
- `.review-input.stale-field` — 3px solid orange left border (#f59e0b), subtle orange background tint

---

## Compatibility Notes

- **Visual tab ("Load Latest Production Table")** is fully compatible — the 3-phase output has the identical `shots` array structure with all 9 fields the visuals tab uses. Extra fields (`visual`, `shot_size`, `visual_continuity_notes`) are safely ignored.
- **Existing "Fast" mode** is completely untouched — no code paths changed.
- **Backward compatible** — if `character_description` is absent from style_intent (old projects), the character section is simply empty. No errors.
- **Batching** works with 3-phase — each batch runs all 3 phases internally, then the existing merge/renumber logic combines them.
