# Visual Style System Overhaul — 2026-02-24

## Summary
Complete overhaul of how Style Reference Images, Additional Context, and Characters influence image generation. Fixed critical bugs where character references were ignored, added per-scene character selection, a debug preview panel, a Style Lock mode for controlling style vs prompt priority, and per-character Reference Mode (Identity Only vs Full Look).

---

## Problems Fixed

### 1. Character names stripped (Critical)
`getAllCharacterImages()` in `index.html` returned a flat array of base64 data, discarding all character names. The model received unlabeled images and had no way to tell which character was which.

### 2. No per-scene character selection
All characters were sent to every scene regardless of relevance. With 3-5 characters this confused the model.

### 3. Regeneration didn't refresh config
`regenerateSceneImage()` did not call `updateVisualsConfig()` first. Changing Additional Context text and hitting Regenerate on a single scene sent the old value.

### 4. Weak prompt instructions
Single-sentence instructions for character identity and style were insufficient. No separation between what style refs control vs what the scene prompt controls.

### 5. No debug visibility
Users couldn't see what prompt + images were actually being sent to the model.

### 6. Style refs overrode scene mood/lighting
Style references controlled everything including lighting and mood, preventing scene-specific atmosphere (e.g., dark horror scene with bright style refs).

### 7. No control over character reference behavior
All characters forced "identity only" mode — face/body preserved but clothing always came from scene prompt. No option for characters with signature outfits (animated mascots, branded looks).

---

## Changes Made

### Files Modified
- `execution/gemini_client.py`
- `execution/server.py`
- `ui/index.html`
- `ui/style.css`

---

### A. Character System Overhaul

**New function: `getStructuredCharacters(sceneIdx)`** — returns `[{name, images}]` grouped by character, filtered by per-scene selection. Replaces the flat `getAllCharacterImages()` for the generation pipeline.

**New field: `selectedCharacters: []`** on each scene object — empty means "all characters", otherwise an array of character names to include.

**Per-scene character selector UI** — collapsible section on each scene card with checkboxes and character thumbnails. Users can pick which characters appear in each scene.

**Backend: labeled character sections** — `generate_scene_image()` now receives `characters` param (list of `{name, images}` dicts). The Gemini prompt is built with labeled sections:
```
--- CHARACTER: "Detective Miller" ---
[reference images]

--- CHARACTER: "Sarah" ---
[reference images]

--- CHARACTER BINDING ---
Characters available in this scene: Detective Miller, Sarah.
```

### B. Prompt Engineering Overhaul

New 4-part multimodal prompt structure for Gemini:

1. **System instruction** — strict rules for identity/style separation
2. **Per-character labeled sections** — with binding instructions mapping names to scene subjects
3. **Style references** — mode-dependent instruction (see Style Lock below)
4. **Scene prompt + additional context + reinforcement** — placed last for recency bias

### C. Style Lock Mode (New Feature)

Dropdown with 3 modes controlling how much style references influence the output:

| Mode | Style refs control | Scene prompt controls |
|---|---|---|
| **Full Style** | Everything — art, palette, lighting, mood | Only composition/action |
| **Art Only** (default) | Medium, technique, palette, texture | Lighting, mood, atmosphere, time of day |
| **Loose** | General aesthetic inspiration only | Everything — refs are suggestions |

Each mode changes the prompt wording sent to Gemini. Applies per-generation so users can switch mid-project.

### D. Debug Preview Panel

Toggle button on each scene card showing:
- Character names + image counts (filtered by per-scene selection)
- Style image count
- Style mode
- Additional context
- Full scene prompt text
- Model, aspect ratio, resolution

### E. Per-Character Reference Mode (New Feature)

Each character now has a **Reference Mode** dropdown (set when creating, changeable inline on the card):

| Mode | What's preserved from reference | What comes from scene prompt |
|---|---|---|
| **Identity Only** (default) | Face, hair, skin tone, body build, age | Clothing, accessories, poses |
| **Full Look** | Everything: face, body, clothing, outfit, accessories, full aesthetic | Only action/pose/setting |

- Dropdown in character creation modal
- Inline dropdown on each character card (changeable anytime)
- Per-character `ref_mode` flows through to Gemini prompt as labeled instruction
- Debug panel shows mode per character

### F. Bug Fixes

- `regenerateSceneImage()` now calls `updateVisualsConfig()` first
- Server endpoints log character count, image count, style mode, and context preview
- `_decode_ref_image()` helper added to DRY up base64 decoding in gemini_client.py
- Both single and batch endpoints pass structured `characters` and `style_mode`
- Project save/load preserves `selectedCharacters` per scene, `styleMode` in config, and `refMode` per character

---

## Data Flow (After Changes)

```
UI: Style Lock dropdown → visualsConfig.styleMode
UI: Character checkboxes → scene.selectedCharacters
UI: Style images → visualsConfig.styleImages
                ↓
buildImageRequestBody(idx):
  characters: getStructuredCharacters(idx)  ← filtered by scene selection
  style_mode: visualsConfig.styleMode
  style_images: [base64...]
                ↓
Server: /api/visuals/generate-image
  → extracts characters, style_mode, style_images
  → passes all to generate_scene_image()
                ↓
gemini_client.py: generate_scene_image()
  → builds 4-part multimodal prompt
  → style instruction varies by style_mode (full/art_only/loose)
  → character sections labeled by name + ref_mode (identity/full_look)
  → sends to Gemini API
```

## User Controls Summary

| Control | Location | Options |
|---|---|---|
| **Style Lock** | Style section dropdown | Full Style / Art Only (default) / Loose |
| **Character Ref Mode** | Per-character (modal + card) | Identity Only (default) / Full Look |
| **Per-Scene Characters** | Each scene card (collapsible) | Checkboxes to select which characters appear |
| **Additional Context** | Style section text input | Free text style notes |
| **Debug Panel** | Each scene card (toggle) | Shows full prompt assembly before generation |

---

## Production Prompt Style Enforcement Fix — 2026-02-25

### Problem
Style extraction correctly identified stick-figure characters from uploaded reference images (e.g., "minimalist stick figure with large circular white head, thick black outlines"), but the generated production prompts completely ignored this and described realistic men in suits with cinematic photography (`SUBJECT CORE: Middle-aged man, weary Baron archetype`, `OUTPUT AESTHETIC: Photoreal`, `APERTURE: f/2.8`, etc.).

### Root Cause

**Bug 1: `SUBJECT CORE` field template contradicted the character description**
In `_FIELD_TO_PROMPT`, the subject field was hardcoded as:
```
SUBJECT CORE: [Age, gender, body type, and overall character archetype]
```
This literally instructed Gemini to fill in realistic human descriptors — directly contradicting the `CHARACTER RENDERING IDENTITY` section that said "don't use 'man', 'woman', 'person'." Gemini followed the field template, not the character section.

**Bug 2: Character description and style summary didn't reach field-level templates**
`_build_prompt_format_instructions()` had no access to `character_description` or `style_summary`. The field templates were always generic regardless of the extracted style.

### Changes Made

**File modified:** `execution/research_templates.py`

**`_build_prompt_format_instructions()`** — Added `character_description` and `style_summary` parameters. When provided:
- `SUBJECT CORE` bracket is overridden to embed the full character rendering description with explicit instruction to not use realistic human terms
- `OUTPUT AESTHETIC` bracket is overridden to embed the actual style (e.g., "Clean digital vector illustration") instead of letting Gemini default to "Photoreal"
- Veo video template embeds the character description and style in the subject hint and style line
- Field reference guide reflects the overridden descriptions

**`build_production_prompt()`** (fast mode) — Now extracts `character_description` from `style_intent` and passes it along with `style_summary` to the field template builder.

**`build_dp_prompt()`** (3-phase max quality mode) — Same fix applied.

### Before vs After

| Field | Before (broken) | After (fixed) |
|---|---|---|
| SUBJECT CORE template | `[Age, gender, body type, and overall character archetype]` | `[A minimalist stick figure with large white circular head... — differentiate by clothing/accessories ONLY]` |
| OUTPUT AESTHETIC template | `[Overall rendering pipeline (2D vector, Photoreal, 3D Render)]` | `[Clean digital vector illustration featuring minimalist stick-figure characters]` |
| Veo subject hint | `[subject]` | `[character described using: A minimalist stick figure...]` |
| Veo style line | `Style: [aesthetic reference].` | `Style: Clean digital vector illustration...` |
