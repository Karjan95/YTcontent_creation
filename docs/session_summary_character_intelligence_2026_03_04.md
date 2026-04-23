# Session Summary: Character Intelligence System
**Date:** 2026-03-04
**Scope:** Dynamic Wardrobe & Expressions + Cast Definition + Holistic Story Analysis

---

## Overview

This session added a **Character Intelligence** layer to the 3-phase production pipeline. Before these changes, characters were static — the same outfit, the same expression, no individual identity. After these changes, the system can:

1. **Define a cast** of characters with distinct visual identities
2. **Adapt wardrobes** per scene based on story context (or lock them)
3. **Map emotions** to specific facial expressions per shot (or lock them neutral)
4. **Analyze the full script holistically** before making any per-shot decisions

All features are user-controlled via UI toggles and panels, with sensible defaults that preserve backward compatibility.

---

## Features Implemented

### Feature 1: Dynamic Wardrobe & Expression Modes

**Problem:** Characters wore the same outfit and had generic expressions across all shots, regardless of story context.

**Solution:** Two new dropdowns in the Style Review panel give users control over how the Storyboard Artist handles clothing and facial expressions.

| Control | Options | Default |
|---------|---------|---------|
| Wardrobe Mode | `Locked to description` / `Story-driven (AI adapts per scene)` | Locked |
| Expression Mode | `Dynamic (matches script emotion)` / `Neutral / Locked` | Dynamic |

**How it flows:**
- User selects modes in Style Review → modes saved in `style_intent`
- Phase 2 (Storyboard Artist) reads modes → injects conditional instruction blocks
- Phase 2 outputs `character_outfit` and `character_expression` per shot
- Phase 3 (DP) reads those fields → copies them into final prompt (does NOT invent its own)

### Feature 2: Cast Definition

**Problem:** A single "Character Description" field described rendering STYLE but couldn't differentiate between multiple characters in the same story.

**Solution:** After script finalization, an AI-powered "Suggest Cast from Script" step identifies all recurring characters and suggests visual identities. The user reviews, edits, and approves the cast before production.

**How it flows:**
- User clicks "Suggest Cast from Script" → AI reads narration + rendering style
- AI returns structured cast (name, role, visual_identity, beat appearances, notes)
- User reviews editable cards → can edit, add, or remove characters
- Approved cast is stored in project state and Firestore
- Phase 2 receives cast → references characters by name for outfit/expression decisions
- Phase 3 receives cast → uses visual_identity in SUBJECT CORE field

**Cast data structure:**
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

### Feature 3: Holistic Story Analysis (Phase 2 Enhancement)

**Problem:** The Storyboard Artist processed beats sequentially without a global plan, leading to inconsistent wardrobe/expression decisions and "forgetting" earlier context.

**Solution:** Phase 2 now performs a mandatory **planning pass** (Step 1) before any per-shot work (Step 2). The AI must output a `story_analysis` object that maps:

- All distinct **locations/settings** in the story
- All **primary subjects** (characters, objects, phenomena, environments)
- The **emotional/tonal arc** across the full video
- **Visual transition points** where major changes occur

Per-shot decisions must then be consistent with this pre-built plan.

---

## How Everything Composes

```
                        ┌─────────────────────┐
                        │   CHARACTER DESC     │  Rendering style (e.g., "2D stick figure")
                        │  (existing field)    │  Applies to ALL characters
                        └─────────┬───────────┘
                                  │
                        ┌─────────▼───────────┐
                        │   CAST DEFINITION    │  WHO: Individual identities
                        │   (new feature)      │  "Officer: dress whites + gold stars"
                        └─────────┬───────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
    ┌─────────▼────────┐ ┌───────▼────────┐ ┌────────▼───────┐
    │  WARDROBE MODE   │ │ EXPRESSION MODE│ │ STORY ANALYSIS │
    │  locked/dynamic  │ │ dynamic/locked │ │ planning pass  │
    └─────────┬────────┘ └───────┬────────┘ └────────┬───────┘
              │                   │                   │
              └───────────────────┼───────────────────┘
                                  │
                        ┌─────────▼───────────┐
                        │  PHASE 2 OUTPUT     │
                        │  character_outfit    │  Per shot
                        │  character_expression│  Per shot
                        └─────────┬───────────┘
                                  │
                        ┌─────────▼───────────┐
                        │  PHASE 3 (DP)       │
                        │  Copies verbatim    │  No invention
                        └─────────────────────┘
```

**Composition table:**

| Mode | Without Cast | With Cast |
|------|-------------|-----------|
| Wardrobe Locked | One outfit for all shots | Each cast member keeps THEIR visual_identity outfit |
| Wardrobe Story-driven | AI invents from scratch | Cast visual_identity is baseline; AI deviates when story demands |
| Expression Dynamic | Generic emotion mapping | Expressions mapped to identified characters by name |
| Expression Locked | Neutral everywhere | All cast members neutral |

---

## Multi-Scenario Support

The system was designed to handle all video types, not just single-character narratives:

| Scenario | How it's handled |
|----------|-----------------|
| **Single character** | Standard path — one cast member, wardrobe/expression per shot |
| **Multiple characters in shot** | Phase 2 describes all visible characters: "Officer: dress whites; Sailors: NWU camo" |
| **No characters (drone, landscape)** | Phase 2 writes "N/A — no characters in shot"; Phase 3 omits wardrobe/expression fields |
| **Documentary with mixed shots** | Each shot treated independently — continuity only for same character reappearing |
| **Non-character video (geography, nature)** | Cast returns `has_characters: false`; story_analysis focuses on locations/phenomena/tonal arc |

---

## Files Modified

| File | What Changed |
|------|-------------|
| **ui/index.html** | Wardrobe/Expression dropdowns with (i) tooltips; Cast Review Panel with editable cards; state management for both features; production request wiring; Firestore persistence |
| **ui/style.css** | Cast panel CSS (~130 lines): cards, fields, buttons, responsive layout |
| **execution/research_templates.py** | `build_storyboard_prompt()`: wardrobe/expression mode injection, story_analysis planning pass, cast section, multi-scenario support. `build_dp_prompt()`: cast section, Phase 2 field passthrough. New: `build_cast_suggestion_prompt()`, `_build_cast_section()` |
| **execution/research_scriptwriter.py** | `cast` parameter threaded through `generate_production_table()`, `_generate_single_batch_3phase()`, `_generate_single_batch()` |
| **execution/server.py** | New `POST /api/suggest-cast` endpoint; `cast` passthrough in production table route |

---

## New API Endpoint

### `POST /api/suggest-cast`

**Request:**
```json
{
  "narration_json": { "beats": [...] },
  "character_description": "2D cartoon stick figure...",
  "rendering_split": "1 image per beat"
}
```

**Response:**
```json
{
  "success": true,
  "cast_data": {
    "has_characters": true,
    "cast": [...],
    "casting_notes": "..."
  }
}
```

---

## New UI Components

### Wardrobe & Expression Controls
- Location: Character Rendering sub-panel in Style Review
- Two `<select>` dropdowns with (i) hover tooltips
- Integrated into stale detection, creative direction merge, and state persistence

### Cast Review Panel
- Location: Between Style Review panel and Pacing controls
- Trigger: "Suggest Cast from Script" button (appears after script is available)
- Editable cards: name, role, visual identity, beat appearances, notes
- Add/remove character functionality
- "Approve Cast" button with badge
- Full Firestore persistence and restore on project load

---

## Design Decisions

1. **Modes as UI toggles, not AI decisions** — The user controls whether wardrobe/expressions are locked or dynamic. The AI follows instructions, it doesn't choose the policy.

2. **Phase 2 decides, Phase 3 copies** — Wardrobe and expression decisions are made by the Storyboard Artist (who has story context). The DP faithfully copies them into prompts. This prevents conflicting interpretations.

3. **Planning pass before per-shot work** — The `story_analysis` object forces the AI to build a global plan (locations, subjects, arc, transition points) before processing any individual shot. This prevents inconsistency from isolated processing.

4. **Cast inherits rendering style** — Cast visual identities are described WITHIN the character rendering style (e.g., "stick figure with blue lab coat"), not as photorealistic descriptions. The Character Description field sets the rendering style, Cast defines individual identities within it.

5. **Backward compatible defaults** — Wardrobe defaults to `locked` (existing behavior), Expression defaults to `dynamic` (makes existing behavior explicit). No cast = original pipeline behavior.

6. **Universal video support** — All instructions, schemas, and examples support both character-driven and non-character videos. The `story_analysis` schema uses generic terms (subjects, phenomena, environments) not just "characters."

---

## Detailed Changelog

See [changelog_dynamic_wardrobe_expressions_2026_03_04.md](changelog_dynamic_wardrobe_expressions_2026_03_04.md) for line-level implementation details, data flow diagrams, and edge case tables.
