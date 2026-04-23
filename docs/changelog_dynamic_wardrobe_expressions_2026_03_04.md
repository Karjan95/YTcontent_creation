# Dynamic Character Wardrobe & Expressions

**Date:** 2026-03-04
**Type:** Feature — Phase 2/3 Pipeline Enhancement

---

## Problem

The 3-phase production pipeline hardcoded character wardrobe and facial expressions from the master Character Description. The AI had no room to adapt outfits when locations changed (e.g., a character entering a lab should wear a lab coat) or to map emotions from the Director's beats into specific facial expressions per shot. This produced visually flat, static characters across narrative videos.

## Solution

Added two new user-controlled modes (**Wardrobe Mode** and **Expression Mode**) to the Character Rendering panel, and upgraded the Phase 2 (Storyboard Artist) to explicitly output per-shot `character_outfit` and `character_expression` decisions that Phase 3 (DP) consumes mechanically.

---

## Changes

### UI (ui/index.html)

**New dropdowns in Character Rendering sub-panel:**

- **Wardrobe Mode** (`#reviewWardrobeMode`)
  - `Locked to description` — Character wears the exact same outfit from the master description in every shot
  - `Story-driven (AI adapts per scene)` — Storyboard Artist chooses contextually appropriate outfits per scene, maintaining continuity within the same location

- **Expression Mode** (`#reviewExpressionMode`)
  - `Dynamic (matches script emotion)` — Storyboard Artist translates each shot's emotion into specific facial features (eyes, mouth, brows)
  - `Neutral / Locked` — All expressions set to neutral throughout

**Info tooltips (i) on hover:** Both new fields have detailed (i) tooltips explaining what each mode does, following the existing tooltip pattern.

**State management updates:**
- `captureCurrentStyleFields()` — captures `wardrobe_mode` and `expression_mode`
- `approveStyle()` — includes both modes in `style_intent`
- `showStyleReviewPanel()` — restores both modes from saved state
- `initStaleDetection()` — tracks both fields for stale detection
- `applyCreativeDirection()` fieldMap — includes both fields for creative direction merge

### Backend — Phase 2: Storyboard Artist (execution/research_templates.py)

**`build_storyboard_prompt()` changes:**

- Reads `wardrobe_mode` and `expression_mode` from `style_intent`
- Injects mode-dependent instruction blocks:
  - **Wardrobe Locked**: Copy clothing from Character Description verbatim. If no clothing described, invent a simple default in Shot 1 and lock it.
  - **Wardrobe Story-driven**: Choose outfits based on environment/setting. Maintain consistency within the same scene. Change only when location demands it.
  - **Expression Dynamic**: Translate Director's `emotion` field into specific facial details (eyes, mouth, brows, energy). Track emotional arc across the video.
  - **Expression Locked**: Set neutral expression for all shots.

- **Two new output fields per shot:**
  - `character_outfit` — Specific clothing description for this shot
  - `character_expression` — Specific facial expression description for this shot

- Updated JSON output schema from 3 new fields to 5 new fields (added `character_outfit` and `character_expression`)

- Enhanced FULL STORY CONTEXT section to emphasize reading the entire script before making wardrobe/expression decisions

- **Holistic Story Analysis (planning pass):** Phase 2 now outputs a `story_analysis` object BEFORE the per-shot array. This forces the AI to map all locations, characters, emotional arc, and wardrobe transition points holistically before processing any individual shot. Per-shot decisions must then be consistent with this pre-built plan. This prevents the AI from processing beats in isolation and "forgetting" earlier decisions.

### Backend — Phase 3: DP (execution/research_templates.py)

**`build_dp_prompt()` changes:**

- Added explicit instructions telling the DP to use Phase 2's `character_outfit` for the WARDROBE & FIT prompt field and `character_expression` for the FACIAL EXPRESSION prompt field
- DP is instructed NOT to invent its own — it faithfully copies the Storyboard Artist's decisions
- Updated output JSON schema to carry forward `character_outfit` and `character_expression` fields

---

## Data Flow

```
UI (Style Review Panel)
  wardrobe_mode: "locked" | "story_driven"
  expression_mode: "dynamic" | "locked"
    ↓ approveStyle()
  style_intent.wardrobe_mode
  style_intent.expression_mode
    ↓ POST /api/generate-production-table
  style_analysis.style_intent.wardrobe_mode
  style_analysis.style_intent.expression_mode
    ↓ _generate_single_batch_3phase()
  Phase 2: build_storyboard_prompt(style_intent=...)
    → Reads wardrobe_mode/expression_mode
    → Injects conditional instruction blocks
    → Outputs: character_outfit, character_expression per shot
    ↓
  Phase 3: build_dp_prompt(storyboard_shots=...)
    → Reads character_outfit → WARDROBE & FIT field
    → Reads character_expression → FACIAL EXPRESSION field
    → Writes final prompts with storyboard's decisions
```

## Defaults

- **Wardrobe Mode default:** `locked` (backward compatible — existing behavior)
- **Expression Mode default:** `dynamic` (expressions were already somewhat dynamic; this makes it explicit and reliable)

## Edge Cases Handled

| Scenario | Behavior |
|----------|----------|
| Wardrobe locked + no clothing in description | Phase 2 invents a default outfit in Shot 1 and locks it for all shots |
| Wardrobe story-driven + no clothing in description | Phase 2 invents contextually appropriate outfits per scene |
| Expression locked | All shots get "Neutral expression" |
| Expression dynamic + emotion field empty | Phase 2 infers from `directors_intent` and `script_beat` |
| Saved project restore | `wardrobe_mode` and `expression_mode` are persisted via `captureStyleReviewState()` and restored via `showStyleReviewPanel()` |
| **No characters in shot** (drone, landscape, equipment) | Phase 2 writes "N/A — no characters in shot" for both outfit and expression; Phase 3 omits WARDROBE & FACIAL EXPRESSION fields from that shot's prompt |
| **Multiple characters in shot** | Phase 2 describes all visible characters' outfits in one string: "Officer: dress whites; Sailors: NWU camo". Expressions describe primary subject or all distinct states |
| **Different subjects across shots** (documentary) | Each shot treated independently — continuity only applies when the SAME character reappears |

---

## Feature 2: Cast Definition

**Date:** 2026-03-04
**Type:** Feature — Pre-production Character Management

### Problem

The system had no way to define individual characters. A single "Character Description" text box described the rendering STYLE (e.g., "stick figure with round head") but couldn't differentiate between multiple characters in the same story. The Storyboard Artist had to improvise how to tell characters apart, leading to inconsistent visual identity across shots.

### Solution

Added a **Cast Definition** step between script finalization and production table generation. The AI reads the finalized script, identifies all recurring characters, and suggests visual identities. The user reviews and edits the cast before production.

### How It Works

```
Script finalized → [Suggest Cast from Script] button
    ↓
AI reads full script, identifies characters
    ↓
Cast Review Panel (editable cards per character)
    ↓
User reviews: edit names, visual identity, add/remove characters
    ↓
Approved cast stored in project state
    ↓
Phase 2 (Storyboard): receives cast → references characters by name,
    uses visual_identity for outfit decisions
    ↓
Phase 3 (DP): receives cast → uses visual_identity in SUBJECT CORE field
```

### Changes

**New prompt builder** (`execution/research_templates.py`):
- `build_cast_suggestion_prompt()` — Reads the full narration, identifies all characters/subjects, suggests visual identities within the rendering style
- `_build_cast_section()` — Helper that formats cast data for injection into Phase 2 and Phase 3 prompts

**New API endpoint** (`execution/server.py`):
- `POST /api/suggest-cast` — Accepts narration JSON + character description, returns structured cast data

**UI** (`ui/index.html`):
- Cast Review Panel with editable character cards (name, role, visual identity, beat appearances, notes)
- "Suggest Cast from Script" button (appears after script is available)
- "Approve Cast" button with badge
- Add/remove character functionality
- Full Firestore persistence and restore

**Pipeline integration:**
- `generate_production_table()` accepts `cast` parameter
- `_generate_single_batch_3phase()` passes cast to Phase 2 and Phase 3
- `build_storyboard_prompt()` receives cast — injects character list with storyboard-specific instructions
- `build_dp_prompt()` receives cast — injects character list with DP-specific instructions

**CSS** (`ui/style.css`):
- Cast panel, card, field, and button styles

### Cast Data Structure

```json
{
  "has_characters": true,
  "cast": [
    {
      "name": "The Scientist",
      "role": "Protagonist — drives the discovery",
      "visual_identity": "Blue lab coat, round glasses on head, clipboard under arm",
      "appears_in_beats": [1, 2, 3, 5, 7],
      "notes": "Outfit changes in beach flashback"
    }
  ],
  "casting_notes": "Characters differentiated by clothing color and accessories"
}
```

### Interaction with Wardrobe/Expression Modes

| Mode | Without Cast | With Cast |
|------|-------------|-----------|
| Wardrobe Locked | One outfit for all shots | Each cast member keeps THEIR visual_identity outfit |
| Wardrobe Story-driven | AI invents from scratch | Each cast member's visual_identity is the baseline; AI can deviate when story demands |
| Expression Dynamic | Generic emotion mapping | Expressions mapped to identified characters by name |
| Expression Locked | Neutral everywhere | All cast members neutral |

### Non-Character Videos

If the script has no recurring characters (geography, nature, architecture), the AI returns `has_characters: false` with an empty cast array. The panel shows a message confirming no cast is needed. The user can still manually add characters if desired.

## Files Modified

| File | Changes |
|------|---------|
| `ui/index.html` | Wardrobe/Expression dropdowns, tooltips, Cast panel with editable cards, state management, production request wiring |
| `ui/style.css` | Cast panel styles (cards, fields, buttons) |
| `execution/research_templates.py` | `build_storyboard_prompt()`, `build_dp_prompt()`, new `build_cast_suggestion_prompt()`, new `_build_cast_section()` |
| `execution/research_scriptwriter.py` | `generate_production_table()`, `_generate_single_batch_3phase()`, `_generate_single_batch()` — all accept `cast` parameter |
| `execution/server.py` | New `/api/suggest-cast` endpoint, `cast` passthrough in production table route |
