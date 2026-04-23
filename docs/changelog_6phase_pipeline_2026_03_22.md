# Changelog: 6-Phase Visual Production Pipeline

**Date:** 2026-03-22

---

## Overview

Replaced the existing 3-phase production pipeline (Director → Storyboard → DP) and Fast mode with a new 6-phase pipeline that adds three new specialist agents and upgrades all three existing ones. Fast mode has been removed entirely — all production table generation now uses the 6-phase pipeline.

**Why:** The previous pipeline produced flat, generic shots with no cinematographic intelligence. The audit identified: no camera language vocabulary, no visual metaphor thinking, no shot sequencing logic, repetitive compositions, and mechanical prompt writing. Each agent was either too restricted (Director forbidden from visual thinking) or too vague (Storyboard writing "a man stands in a forest").

---

## New Architecture

```
Phase 0: SCRIPT DOCTOR (NEW)         → Visual Brief (metaphors, mood, color, symbols)
Phase 1: DIRECTOR (UPGRADED)         → Cuts + emotional arc + camera INTENT
Phase 2: CINEMATOGRAPHER (NEW)       → Camera technique from 62-technique library
Phase 3: STORYBOARD ARTIST (UPGRADED)→ Layered compositions informed by camera decisions
Phase 4: CONTINUITY SUPERVISOR (NEW) → Review + auto-fix variety/flow/consistency
Phase 5: DP (UPGRADED)               → Final prompts with lighting vocabulary + creative authority
```

The Visual Brief from Phase 0 is passed as shared context to ALL downstream phases, ensuring every agent works from the same creative vision.

---

## Phase 0: Script Doctor (NEW)

**Role:** Reads the complete narration and distills a per-beat Visual Brief — a compact creative compass for all downstream agents.

**What it produces per beat (50-80 words):**
- `metaphors` — concrete visual analogies ("Time as erosion — sand wearing stone smooth")
- `mood_atmosphere` — 2-4 evocative tags (["suffocating", "amber-lit", "ancient"])
- `color_palette_shift` — how color evolves ("Deep indigo fading to amber")
- `symbolic_imagery` — 1-2 visual symbols ("Hourglass with sand flowing upward; cracked sundial")
- `suggested_pov` — ideal perspective ("Aerial pulling back to reveal scale")
- `tone_keywords` — 3-5 tone descriptors (["haunting", "reverent", "questioning"])

**Global motifs:** Recurring symbols, color arc across the full piece, emotional throughline.

**Key design decisions:**
- Uses mood board language, NOT film references (no "like Blade Runner")
- Runs ONCE before batching — shared across all batches for consistency
- Temperature: 0.3 (creative — metaphors benefit from higher temperature)

**File:** `execution/research_templates.py` — `build_script_doctor_prompt()`

---

## Phase 1: Director (UPGRADED)

**Previous:** Only made cutting decisions (where to split, duration, emotion). Explicitly forbidden from visual thinking.

**Now:** Makes cutting decisions AND expresses camera INTENT per shot — the storytelling goal, not specific technique.

### What Changed

**1. New role definition**
No longer forbidden from visual thinking. Expresses intent like "this needs a slow reveal," "claustrophobic intimacy," "pull back to show the enormity." The Cinematographer translates intent into specific technique.

**2. Chain-of-thought: Emotional Arc Mapping**
Before making ANY cuts, the Director now maps the full emotional arc:
- Tension peaks (moments of highest intensity)
- Breathing points (moments of release)
- Transitions (shifts between topics/moods)
- Overall shape (building? wavelike? U-shaped?)

This analysis is output as `emotional_arc_analysis` and cutting decisions must serve the arc.

**3. New output fields per shot:**
- `camera_intent` — storytelling goal ("Slow reveal — start tight, then expand to show context")
- `emotional_arc_position` — where in the arc ("Rising tension", "Peak", "Release")

**4. Richer examples**
Multi-act pacing examples showing how duration/rhythm varies across acts (fast cuts at peaks, held shots at breathing points).

**5. Visual Brief context**
Receives the Script Doctor's mood tags and POV suggestions to inform pacing decisions.

**File:** `execution/research_templates.py` — `build_director_prompt()`

---

## Phase 2: Cinematographer (NEW)

**Role:** Translates the Director's camera intent into specific executable camera language from a 62-technique library.

### Technique Library (62 techniques, 7 categories)

| Category | Count | Examples |
|----------|-------|---------|
| Camera Movement | 14 | Static, Dolly-in, Dolly-out, Tracking, Crane up/down, Steadicam float, Handheld, Whip pan, Slow push-in, Orbit/arc, Zoom, Tilt, Boom |
| Camera Angle | 9 | Eye level, Low angle, High angle, Bird's eye, Worm's eye, Dutch angle, Over-the-shoulder, POV, Profile |
| Lens Feel | 7 | Wide-angle, Standard, Telephoto, Macro, Fisheye, Anamorphic, Tilt-shift |
| Composition | 9 | Rule of thirds, Center/symmetry, Golden ratio, Leading lines, Frame-within-frame, Negative space, Foreground framing, Diagonal, Layered depth |
| Lighting Mood | 10 | High-key, Low-key, Rembrandt, Split, Silhouette, Rim/backlight, Practical, Chiaroscuro, Golden hour, Motivated |
| Visual Storytelling | 7 | Contrast cut, Match cut, Visual callback, Reveal, Conceal, Juxtaposition, Visual metaphor |
| Depth & Focus | 6 | Deep focus, Shallow DOF, Rack focus, Split diopter, Bokeh, Pull focus through layers |

Each technique includes name, when-to-use context, and effect on viewer. The library is universal (not template-specific) — the Cinematographer selects based on mood/tone from the Visual Brief.

### Output per shot (7 new fields)
- `camera_movement` — with justification ("Slow push-in — building toward revelation")
- `camera_angle` — with justification ("Eye level — honest, direct connection")
- `lens_feel` — with justification ("Telephoto compression — isolating subject")
- `composition` — with justification ("Center frame — subject commands attention")
- `lighting_mood` — with justification ("Low-key — truth lives in shadow")
- `depth_focus` — with justification ("Shallow DOF — world falls away")
- `visual_storytelling_technique` — from library or "none" (used sparingly, 20-30% of shots)

### Enforced Variety Rules
- No more than 2 consecutive shots with same camera_movement
- No more than 3 consecutive shots with same camera_angle
- No more than 2 consecutive shots with same lighting_mood
- Full shot list must use at least 4 different movements, 3 angles, 3 lighting moods

**Temperature:** 0.2 (slight creativity for technique selection)

**File:** `execution/research_templates.py` — `build_cinematographer_prompt()`

---

## Phase 3: Storyboard Artist (UPGRADED)

**Previous:** Wrote 1-2 sentence generic visual descriptions ("A man stands in a forest"). Only picked `shot_size` for camera decisions.

**Now:** Creates layered 3-4 sentence compositions informed by the Cinematographer's camera decisions. Thinks in terms of visual storytelling: foreground/midground/background, visual metaphor execution, environmental storytelling.

### What Changed

**1. Upgraded "visual" field**
From 1-2 generic sentences to 3-4 layered sentences:
- Sentence 1: Primary subject and action
- Sentence 2: Environment and atmospheric context
- Sentence 3: Composition detail — foreground vs background, visual metaphor, symbolic elements
- Sentence 4 (optional): Dynamic element — movement, change, interaction

WEAK: "A man stands in a forest."
STRONG: "A weathered explorer pauses mid-stride on a root-tangled trail, machete lowered to his side. Dense canopy filters jade-green light onto his sweat-streaked face. In the foreground, a spider's web stretches between two branches — a natural gate he must break through. Behind him, the path disappears into shadow."

**2. New field: `fg_mg_bg_layers`**
Explicit foreground/midground/background content per shot:
```json
{"fg": "out-of-focus candle flame", "mg": "scientist hunched over microscope", "bg": "shelves of specimen jars"}
```

**3. New field: `visual_metaphor_execution`**
How the Script Doctor's symbolic suggestions manifest in this shot's composition:
"The Script Doctor suggested 'time as erosion.' Executed by placing a crumbling stone wall behind the subject, with sand visibly trickling from its cracks."

**4. Cinematographer-informed compositions**
The Storyboard Artist now receives and works WITH the Cinematographer's camera_movement, camera_angle, lens_feel, composition, lighting_mood, and depth_focus decisions. If the Cinematographer chose "foreground framing" as composition, the Storyboard Artist ensures there's a foreground element in `fg_mg_bg_layers`.

**5. Visual Brief context**
Mood tags and symbolic imagery suggestions inform scene composition and metaphor execution.

**File:** `execution/research_templates.py` — `build_storyboard_prompt()`

---

## Phase 4: Continuity Supervisor (NEW)

**Role:** Final quality check before the DP writes generation prompts. Reviews the COMPLETE shot list and flags + auto-fixes issues.

### 5-Step Review Process

1. **Shot Size Variety** — No 3+ consecutive shots at same size. Auto-fixes by changing middle shot to contrasting size.
2. **Camera Variety** — No 2+ consecutive same movement, no 3+ consecutive same angle. Suggests alternatives serving the Director's intent.
3. **Visual Flow** — Checks spatial logic, transition gaps, emotional intensity matching shot language.
4. **Color Consistency** — Validates against Visual Brief's color_palette_shift and global color_arc.
5. **Continuity** — Character/environment consistency across shots (outfit, visual description, time-of-day).

### Output per shot
- `continuity_fix` — what was changed and why (or "No issues — approved as-is")
- `continuity_grade` — A (clean), B (minor fix), C (significant fix), F (flagged for review)
- `review_summary` — counts of total shots, modifications, by category

**Non-critical fallthrough:** If the Continuity Supervisor fails (API error, parse error), the pipeline continues with uncorrected shots rather than failing entirely.

**Temperature:** 0.05 (rule-checking, minimal creativity)

**File:** `execution/research_templates.py` — `build_continuity_supervisor_prompt()`

---

## Phase 5: DP (UPGRADED)

**Previous:** Mechanical transcriber converting storyboard fields into bracket-format prompts. No creative authority.

**Now:** Brings creative authority over lighting design, atmosphere, and texture.

### What Changed

**1. Lighting Vocabulary**
Embedded reference covering:
- Light Source (sun, candle, neon, moonlight, bioluminescence...)
- Light Quality (hard, soft, dappled, specular, diffused)
- Light Direction (front-lit, side-lit, back-lit, top-lit, rim-lit)
- Color Temperature (warm candlelight, neutral daylight, cool overcast, mixed)
- Shadow Quality (crisp-edged, soft gradient, deep black, none)
- Atmosphere (haze, fog, dust motes, rain, steam, heat shimmer, morning mist)

**2. Creative authority**
No longer just transcribing — the DP now makes lighting design decisions informed by the Visual Brief's mood_atmosphere and color_palette_shift. Adds atmospheric details (dust motes, moisture, lens artifacts) that make images feel real.

**3. Visual Brief context**
Per-beat color and mood guidance drives lighting and atmosphere choices.

**4. Cinematographer decisions as input**
Reads camera_movement, camera_angle, lens_feel from previous phases to write technically accurate prompts.

**File:** `execution/research_templates.py` — `build_dp_prompt()`

---

## Orchestration Changes

### New `_generate_single_batch_6phase()`

Chains all 6 phases sequentially, each feeding output to the next. The Script Doctor's Visual Brief is optionally pre-computed and passed in (used for batching).

**Execution flow:**
```
Phase 0: Script Doctor → visual_brief (pre-computed, shared)
Phase 1: Director (visual_brief) → director_shots
Phase 2: Cinematographer (director_shots, visual_brief) → cinematographer_shots
Phase 3: Storyboard (cinematographer_shots, visual_brief) → storyboard_shots
Phase 4: Continuity (storyboard_shots, visual_brief) → corrected_shots [non-critical]
Phase 5: DP (corrected_shots, visual_brief) → final production table
```

**Model:** All phases use `gemini-2.5-flash` with phase-appropriate temperatures.

**Error handling:** Each phase checks for empty/error responses. Phase 4 (Continuity) is non-critical — if it fails, the pipeline continues with uncorrected shots. All other phase failures return errors for batch-level retry.

### Updated `generate_production_table()`

- Script Doctor runs ONCE on the full narration before batching
- Visual Brief shared across all batches
- Always uses `_generate_single_batch_6phase` (quality_mode parameter kept for backward compatibility but ignored)
- Existing batching logic (by act, with parallel execution) preserved

### Fast Mode Removed

- `_generate_single_batch()` still exists but is no longer called
- `build_production_prompt()` (combined Fast mode prompt) still exists but is no longer called
- `quality_mode` parameter ignored — always routes to 6-phase

**Files:** `execution/research_scriptwriter.py`

---

## Frontend Changes

### Quality Mode Selector Removed
- Replaced with static "6-Phase Pipeline" indicator showing the agent sequence
- `updateQualityModeHint()` simplified to legacy stub

### Status Messages Updated
Progressive status messages now reflect the 6-phase pipeline timing:
```
 0s: "Script Doctor analyzing narration..."
15s: "Director + Cinematographer working..."
35s: "Storyboard Artist composing scenes..."
55s: "Continuity review + DP writing prompts..."
80s: "Still generating — large scripts take longer..."
```

### Autosave/Project Load
- `quality_mode` field preserved as `'max_quality'` for backward compatibility
- Project load ignores the quality_mode field

**File:** `ui/index.html`

---

## Creative Direction Helper Updated

`_build_creative_direction_section()` now supports all 6 agent roles:

| Role | Emphasis |
|------|----------|
| `script_doctor` | Visual language, narrative approach, tone & feel |
| `director` | Narrative approach, pacing philosophy, format-specific cutting, tone |
| `cinematographer` | Video format (affects camera language), pacing philosophy, tone |
| `storyboard` | Visual language, world building, character approach, format |
| `continuity_supervisor` | Visual language, tone — verify consistency |
| `dp` | All fields — visual language, world building, character, narrative, format, tone |

**File:** `execution/research_templates.py` — `_build_creative_direction_section()`

---

## Performance Considerations

- **Latency:** ~60-120 seconds per batch (6 sequential AI calls vs previous 15-30s for 3-phase or 5-10s for Fast)
- **Cost:** ~$0.80-2.00 per batch (roughly double the previous max_quality mode)
- **Token budget:** The 62-technique library adds ~1,500 tokens to the Cinematographer prompt. Visual Brief adds ~60 words per beat to downstream prompts. Both manageable within context limits.
- **Reliability:** Phase 4 (Continuity) has non-critical fallthrough. Each batch retries up to 3 times on failure.

---

## Backward Compatibility

- Existing projects load correctly — production_data output format unchanged
- `quality_mode` parameter accepted but ignored (always 6-phase)
- All existing helper functions preserved: `_build_cast_section`, `_build_character_section`, `_build_prompt_format_instructions`, `DEFAULT_PROMPT_SCHEMA`
- Style analysis, creative direction, and cast systems fully preserved
- Frontend gracefully handles old projects with `quality_mode: 'fast'`

---

## Data Flow Summary

```
Narration + Style + Creative Direction + Cast
  ↓
Phase 0: Script Doctor
  → Visual Brief (per-beat: metaphors, mood, color, symbols, POV, tone)
  ↓ (shared with all phases below)
Phase 1: Director
  → Shot list + emotional_arc_analysis + camera_intent per shot
  ↓
Phase 2: Cinematographer
  → + camera_movement, camera_angle, lens_feel, composition, lighting_mood, depth_focus
  ↓
Phase 3: Storyboard Artist
  → + visual (3-4 sentences), shot_size, fg_mg_bg_layers, visual_metaphor_execution, wardrobe, expression
  ↓
Phase 4: Continuity Supervisor
  → + continuity_fix, continuity_grade (corrections applied)
  ↓
Phase 5: DP
  → + first_frame_prompt, last_frame_prompt, veo_prompt (final generation prompts)
  ↓
Production Table (ready for image/video generation)
```

---

## Files Changed Summary

| File | Changes |
|------|---------|
| `execution/research_templates.py` | 3 new functions (`build_script_doctor_prompt`, `build_cinematographer_prompt`, `build_continuity_supervisor_prompt`), 3 upgraded functions (`build_director_prompt`, `build_storyboard_prompt`, `build_dp_prompt`), updated `_build_creative_direction_section` with 6 agent roles |
| `execution/research_scriptwriter.py` | New `_generate_single_batch_6phase`, updated `generate_production_table` (Script Doctor before batching, always 6-phase), updated imports |
| `ui/index.html` | Removed quality mode selector, updated status messages for 6-phase timing, updated autosave/project load |
