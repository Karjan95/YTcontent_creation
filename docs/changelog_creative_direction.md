# Creative Direction Feature

**Date:** 2026-02-26

## Problem

The 3 production agents (Director, Storyboard Artist, DP) knew **how things should look** (via style analysis) but NOT **what kind of video it is**. A script about the Royal Family could be a stick figure explainer, a 3D documentary, or a POV story — the agents had no way to know. Style covers rendering (lighting, texture, camera), but not the conceptual/structural direction of the video.

## Solution

Added a new "Creative Direction" section in Phase 3 (Production Table), placed **before** Style Review. Users describe the video concept in free-form text, AI expands it into structured guidance, and it flows through the entire production pipeline to all 3 agents.

## User Flow

1. User types a creative direction (e.g., "stick figure explainer with POV style, each level of the hierarchy gets its own visual segment with different outfits")
2. Clicks **"Expand with AI"** — AI reads the script context + user input and returns structured guidance across 7 fields (video format, visual language, narrative approach, pacing philosophy, world building, character approach, tone & feel) plus auto-suggested style defaults
3. User reviews the expanded direction, can **"Re-refine"** with adjustment prompts (e.g., "make it more playful")
4. Clicks **"Apply Direction & Auto-Suggest Style"** — style review panel auto-populates with AI-suggested defaults matching the creative direction
5. User can optionally upload style reference images to further refine the auto-suggested style
6. User approves style and generates production table — all 3 agents receive tailored creative direction guidance

## Files Modified

### `execution/gemini_client.py`
- Added `_get_creative_direction_prompt()` — shared prompt template for expanding/refining creative direction
- Added `expand_creative_direction(user_direction, narration_context, api_key)` — expands free-form text into structured guidance + auto-suggested style defaults
- Added `refine_creative_direction(current_direction, user_feedback, narration_context, api_key)` — refines existing direction based on user feedback

### `execution/server.py`
- Added `POST /api/expand-creative-direction` endpoint — accepts `{direction, narration_context?}`, returns structured creative direction
- Added `POST /api/refine-creative-direction` endpoint — accepts `{current_direction, feedback, narration_context?}`, returns updated direction
- Updated `POST /api/generate-production-table` — extracts `creative_direction` from request body and passes it through the pipeline

### `execution/research_scriptwriter.py`
- Added `creative_direction` parameter to `generate_production_table()`, `_generate_single_batch()`, `_generate_single_batch_3phase()`
- Threaded parameter through all batch calls (single batch, multi-batch, and 3-phase pipeline)

### `execution/research_templates.py`
- Added `_build_creative_direction_section(creative_direction, agent_role)` — generates role-tailored prompt sections:
  - **Director** receives: narrative approach, pacing philosophy, video format, tone — influences cutting decisions
  - **Storyboard Artist** receives: visual language, world building, character approach, video format — influences visual composition
  - **DP** receives: visual language, world building, character approach, tone — influences prompt writing
- Added `creative_direction` parameter to `build_production_prompt()` (fast mode), `build_director_prompt()`, `build_storyboard_prompt()`, `build_dp_prompt()`

### `ui/index.html`
- Added Creative Direction HTML section between Input Mode Toggle and Style Reference Images
- Added global state variables: `currentCreativeDirection`, `lastAutoSuggestedStyle`
- Added JavaScript functions: `expandCreativeDirection()`, `refineCreativeDirection()`, `showCreativeDirectionResult()`, `captureCurrentStyleFields()`, `applyCreativeDirection()`, `clearCreativeDirection()`
- Updated `generateProductionTable()` to include `creative_direction` in the request body
- State preservation logic: user's manual style edits are preserved when creative direction is re-applied

### `ui/style.css`
- Added CSS for `.creative-direction-section`, `.creative-direction-result`, `.direction-header`, `.direction-approved-badge`, `.direction-summary`, `.direction-details`, `.direction-detail-item`

## Data Structure

```json
{
    "direction_summary": "2-3 sentence elevator pitch of the creative vision",
    "video_format": "explainer / documentary / essay / tutorial / etc.",
    "visual_language": "literal depiction / visual metaphors / abstract / symbolic",
    "narrative_approach": "direct address / observational / dramatic / POV / educational",
    "pacing_philosophy": "contemplative / rapid-fire / building crescendo / steady",
    "world_building": "minimalist void / rich environments / real-world / stylized",
    "character_approach": "stick figures / 3D humans / silhouettes / no characters",
    "tone_and_feel": "playful / serious / warm / dramatic",
    "suggested_style_defaults": {
        "style_summary": "...",
        "style_intent": { "character_description, detail_level, ..." },
        "prompt_schema": { "always_include, include, exclude" }
    }
}
```

## Edge Cases Handled

| Case | Behavior |
|------|----------|
| No narration yet (Phase 2 not done) | AI expands based on user text alone, without script context |
| Direction changed after style approved | `applyCreativeDirection()` clears approved style, forces re-approval. Manual style edits are preserved |
| Style images uploaded after auto-suggest | Image analysis overrides auto-suggested style defaults. Creative direction still passes separately to agents |
| Fast mode vs Max Quality mode | Fast mode gets combined direction section; Max Quality mode gets role-specific sections for each of the 3 agents |
| No creative direction provided | Backward-compatible — all functions default to `None`, existing behavior unchanged |
