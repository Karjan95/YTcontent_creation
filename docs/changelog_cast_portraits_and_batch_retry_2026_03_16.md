# Changelog: Cast Portrait Generation & Batch Retry Improvements

**Date:** 2026-03-16

---

## Feature: Auto-Generate Cast Portraits as Character References

Bridges the Cast system (Style & Cast tab) with the Character Reference system (Visuals tab). After AI suggests cast members, the system now generates portrait images and auto-populates them as character references for scene image generation.

### What's New

**1. Portrait Prompts in Cast Suggestion**
- AI Casting Director now generates `portrait_prompts` (face_closeup + full_body) for each cast member
- Prompts incorporate the character rendering style and creative direction context
- Creative direction (`visual_language`, `character_approach`) is now passed to the suggest-cast endpoint
- Portrait prompts are editable via a collapsible "Edit" toggle on each cast card

**2. Cast Portrait Generation**
- New "Generate Portrait" button per character card (face closeup + full body, 2 API calls)
- New "Generate All Portraits" batch button for all cast members at once
- Face closeup uses 1:1 aspect ratio, full body uses 9:16
- Portraits uploaded to Firebase Storage under `references/{project_id}/character/`
- Outdated indicator (orange badge) when `visual_identity` is edited after portraits were generated

**3. Auto-Populate Visuals Tab**
- Cast portraits automatically appear in the Visuals tab Characters section
- Characters with `fromCast: true` flag are managed by the cast system
- Manually-added characters are left untouched
- Sync happens after: portrait generation, cast approval, and project load

**4. Auto-Assign Characters to Scenes**
- When production table initializes the Visuals tab, characters are auto-assigned to scenes
- Uses `appears_in_beats` from cast data mapped to shot `beat` names via narration beat index
- Pre-populates `selectedCharacters` per scene card so correct character references are sent during image generation

**5. Removed `full_look` Ref Mode**
- Character reference mode is now always `identity` (face/body only, wardrobe from text)
- Removed the `full_look` dropdown from Visuals tab character cards
- Wardrobe handled via existing text-based system (cast `visual_identity` + production table `character_outfit`)

### New API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/generate-cast-portrait` | POST | Generate a single portrait (face or body) for one cast member |
| `/api/generate-cast-portraits-batch` | POST | Batch generate portraits for all cast members (ThreadPoolExecutor, max 5 workers) |

### Files Changed

| File | Changes |
|------|---------|
| `execution/research_templates.py` | Added `creative_direction` param to `build_cast_suggestion_prompt()`, added `portrait_prompts` to output schema with examples |
| `execution/server.py` | Updated suggest-cast route, added 2 new portrait generation endpoints |
| `execution/gemini_client.py` | Removed `full_look` branch in `generate_scene_image()`, always uses identity mode |
| `ui/index.html` | Extended cast cards with portrait UI, added generation functions, auto-populate + auto-assign logic, project load restoration |
| `ui/style.css` | New styles for portrait thumbnails, outdated badge, collapsible prompts, generate button |

---

## Improvement: Batch Image Generation Retry & Throttling

Addresses high failure rates when generating large batches (200+ images) due to Gemini API rate limiting.

### Changes

**1. Reduced Concurrency**
- Batch image generation reduced from 5 to 3 parallel workers
- Prevents thundering herd effect on Gemini API

**2. Stagger Delay**
- 800ms delay between each worker picking up a new job
- Workers start staggered (0ms, 800ms, 1600ms) to spread initial load

**3. Automatic Retry Pass**
- After initial batch completes, failed scenes are auto-retried
- Retry uses 2 workers with 2s delay between jobs
- 3-second cooldown before retry pass starts (lets rate limits reset)
- Only auto-retries if less than 50% failed (otherwise likely a systemic issue)
- Button shows "Auto-retrying X failed..." during retry pass

**4. Staging Timeout Fix**
- Added `--timeout 3600` to `deploy_staging.sh` (was missing, production already had it)
- Prevents Cloud Run 503 "Service Unavailable" on long-running image generation requests

**5. Better Error Handling**
- Portrait generation frontend now handles non-JSON error responses gracefully
- No more "Unexpected token" JSON parse errors on 503s

### Files Changed

| File | Changes |
|------|---------|
| `ui/index.html` | Batch generation: reduced concurrency to 3, added stagger delays, auto-retry pass for failed scenes |
| `deploy_staging.sh` | Added `--timeout 3600` flag |

---

## Discussion Notes

- Character reference consistency varies per scene. Hypothesis: long/complex prompts (environment detail, lens settings, etc.) can drown out reference image influence due to Gemini's attention budget. Simpler scenes tend to match better.
- User will test adding "The character MUST match the reference images exactly" in `additional_context` field to see if it improves consistency.
- Failed API calls (429/503) are not charged by Gemini. Only successful generations incur cost.
