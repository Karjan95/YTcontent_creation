# Production Pipeline — As-Built Reference

**Status:** Implemented and verified on staging (2026-05-27).
**Originally drafted:** 2026-05-26 as a forward plan; revised in place
on 2026-05-27 to document current behavior plus the style-anchor field
fix shipped that day.

This document describes how the 6-stage agentic production pipeline
actually behaves in `execution/agentic_pipeline.py` today. Companion
changelog (with implementation history): `docs/agentic_5stage_pipeline_2026_05_25/changelog.md`.

---

## Overview

The pipeline is six sequential agentic stages, run on a background
thread kicked off by `POST /api/production/run`. Each stage gets its
own Pydantic schema and prompt builder. Stage 4 and Stage 6 are
batched; Stage 5 has a two-phase fallback for >800 shots. The UI polls
`/api/production/state` to render per-stage panels and offers per-stage
Approve / Feedback / Edit controls.

| # | Stage | Role | Output | Batched |
|---|---|---|---|---|
| 1 | Story Treatment | Director | Logline, theme, arc, scene treatments | No |
| 2 | World & Design | Production Designer | World, era, **rendering_style**, palette, motifs, lighting rules | No |
| 3 | Cinematography Plan | DP | Lens vocab, movement language, per-scene lighting, mood escalation | No |
| 4 | Shot List | Director + Storyboard Artist | Full shot blueprints with narrative anchors | Yes (~10 beats/batch, sequential) |
| 5 | Continuity Brief | Script Supervisor | Character locks, vocab locks, callback map, act atmospheres | Two-phase above 800 shots |
| 6 | Final Prompts | DP | 7 structured prompt fields per shot → assembled `first_frame_prompt` + `veo_prompt` | Yes (25 shots/batch, **3 workers in parallel**) |

---

## Stage-by-stage current behavior

### Stage 4 — Shot List

**Pacing baseline (user-controlled).** `_compute_target_shot_count()`
takes the format_preset → resolves a pacing tier (Meditative / Relaxed
/ Standard / High Energy / Frenetic) → looks up `words_per_shot` →
divides total narration words. Defaults to Standard (9 words/shot).
The user picks the tier via the format preset; the pipeline doesn't
hardcode shot count.

```
PACE_TIERS = {
    "Meditative":  {"words_per_shot": 15},
    "Relaxed":     {"words_per_shot": 11},
    "Standard":    {"words_per_shot": 9},
    "High Energy": {"words_per_shot": 5},
    "Frenetic":    {"words_per_shot": 3},
}
```

**Max shot duration (user-controlled).** Per-project field
(`max_shot_duration`, UI input at `#maxShotDurationInput`, default 6s,
clamped `[2.0, 15.0]` on read). Threaded through:
- Stage 4 prompt (instruction to keep shots under the cap)
- `_dedupe_and_split_shots` (split oversize shots into multiple)
- `_normalize_shot_durations` (final cap as safety net)

**Batching.** `_split_narration_into_batches` slices the narration into
groups of `STAGE4_BEATS_PER_BATCH=10`. Per-batch target is
`round(total_target × batch_words / total_words)` so the sum across
batches matches the global pacing target. `shot_number` is renumbered
sequentially server-side.

**Pacing tolerance retry.** After each batch returns, if
`len(batch_shots) < batch_target × (1 - PACING_TOLERANCE)` (i.e.,
undershooting by more than 15%), the batch is retried **once** with a
strict feedback note that quotes the actual count and the required
range. No infinite loop — accept the second result whatever it is.

**Deterministic post-pass.** Two passes run regardless of model output:

1. `_dedupe_and_split_shots(shots, max_shot_duration)` —
   - Dedupe adjacent shots with identical `script_beat` by slicing the
     text into clauses on natural breath boundaries (em dash,
     semicolon, comma, conjunction).
   - Split any shot whose `script_beat` exceeds
     `max_shot_duration × TARGET_WPS` words into K child shots, each
     with a clause and cycling vocab from `_SPLIT_CAMERA_MOVES` /
     `_SPLIT_LENSES` / `_SPLIT_SHOT_SIZES`.

2. `_normalize_shot_durations(shots, max_shot_duration)` —
   - Recompute each shot's `duration` as
     `max(MIN_SHOT_DURATION, word_count(script_beat) / TARGET_WPS)`
     then cap at `max_shot_duration`.
   - Rebuild `timestamp` as cumulative `MM:SS`.

Constants: `TARGET_WPS=2.7`, `MIN_SHOT_DURATION=1.5`. The runtime of
the assembled film now matches the narration's reading time.

**Schema (`_ShotBlueprint`).** Per shot, required fields:
- Narrative anchors: `act`, `beat`, `script_beat` (verbatim narration
  line this shot illustrates), `cutting_rationale`, `emotion`
- Character: `character_expression`, `character_outfit`
- Cinematography: `directors_intent`, `composition` (`foreground` /
  `midground` / `background`), `camera_move`, `lens`, `angle`
- Bookkeeping: `shot_number`, `timestamp`, `duration`

### Stage 5 — Continuity Brief

Sees the full Stage 4 shot list (compacted via `_compact_shot_for_brief`
into pipe-delimited
`{shot_number}|{beat}|{character_expression}|{character_outfit}|{script_beat}`).
Extracts invariants that Stage 6's parallel batches must share so
prompts written in different batches don't drift.

Output (`Stage5ContinuityBrief`):
- `character_locks` — one canonical descriptor per recurring character
- `vocabulary_locks` — canonical phrasing for recurring concepts
- `callback_map` — visual echoes between shots
- `act_atmospheres` — keyword sets per act
- `consistency_concerns` — issues to flag to the user

**Two-phase split above 800 shots.** `_run_stage5_two_phase`:
- Phase A: sees full shot list → emits `character_locks` only
- Phase B: sees full shot list + Phase A's locks → emits everything else
- Merged into a single `Stage5ContinuityBrief`. Both phases see all
  shots so there's zero continuity drift. Adds ~30s wall time. Safe to
  ~3000 shots.

### Stage 6 — Final Prompts (parallel + checkpointed)

**Schema (`_FinalShotDelta`).** Per shot, the model fills seven
structured prompt fields plus `veo_prompt` and any explicit
`revised_blueprint_fields`:

```
shot_size         # ECU / CU / MCU / Medium / Wide / Extreme Wide
subject_pose      # who/what + action + expression
environment       # location + bg/fg props
lighting          # source + direction + color temp
lens_dof          # focal length + aperture + depth of field
color_palette     # dominant colors + contrast
output_aesthetic  # the style anchor (force-locked, see below)
```

`first_frame_prompt` is no longer a model output — it's assembled
server-side from these seven fields via `_assemble_first_frame_prompt`
into the labeled 8-section template (the 8th label being
`ASPECT RATIO`). Same precision as the old 12-section template at
roughly a third of the tokens.

**Parallelization.** `ThreadPoolExecutor(max_workers=STAGE6_PARALLEL_WORKERS=3)`
with `STAGE6_BATCH_SIZE=25`. At 1000 shots this brings Stage 6 from
~20 minutes sequential down to ~7 minutes.

**Cancel-inside-future.** The cancel check is performed at the start
of each submitted task, not once per loop iteration — otherwise a
cancel issued after submit but before pickup would be ignored.

**Per-batch checkpoint.** Each batch's `shot_deltas` plus
`continuity_review` are appended to the persisted output and the
`completed_batches` set under a `threading.Lock` so concurrent writes
don't trample each other. Resume picks up at the next unfinished
batch via the existing `/api/production/stage/6/resume` endpoint.

**Wrapper retry.** `gemini_client` already retries 503/429/quota
internally. The wrapper here adds one retry for a different failure
class: empty response or `_parse_json_response` failure. One retry,
then mark the batch failed.

**Failure handling.** If batch N fails after retry, in-flight batches
finish first (so their checkpoints save), then a `RuntimeError`
summarizes all failures. The UI shows a per-batch breakdown and a
Resume button.

### Style anchor — how it propagates to every shot (fixed 2026-05-27)

This is the path that was broken before 2026-05-27 and is now correct:

1. **User defines style** in the Phase 3 style panel (uploads
   references / writes description / approves). The UI keeps the
   structured dict `{style_summary, style_intent, prompt_schema}` in
   memory as `approvedStyle`.

2. **UI autosave** persists it on the project doc under the key
   `approved_style` (`ui/index.html:11730`). `loadProject()` restores
   it (`:11268-11272`).

3. **Pipeline read.** `_load_project_context()` in
   `agentic_pipeline.py:204-211` reads:

   ```python
   'style_analysis': project.get('approved_style')
                     or project.get('style_analysis')
                     or project.get('visual_style_analysis') or {},
   ```

   `approved_style` is the canonical source; the other two keys are
   legacy-tolerance fallbacks. **This three-key lookup is the fix
   from 2026-05-27** — previously the pipeline only checked
   `style_analysis` / `visual_style_analysis`, neither of which the UI
   ever writes, so the user's style never reached any stage.

4. **Stage 2 verbatim-paste.** `build_stage2_world_design_prompt`
   (`agentic_prompts.py:391-413`) reads
   `style_analysis.style_summary`. If non-empty, the prompt instructs
   the LLM to set `rendering_style` to that text **verbatim, no
   rephrasing**. If empty, it asks the LLM to invent one — that
   fallback should now rarely trigger.

5. **Stage 6 anchor resolution.** `_run_stage6_batched` in
   `agentic_pipeline.py:918-937` resolves:

   ```python
   user_style = style_analysis.get('style_summary')
   rendering_style = user_style or stage2_rendering_style
   ```

   The user-approved text is the source of truth; Stage 2's output is
   only used if the user never approved a style. The chosen source is
   logged as `[Stage6 anchor] source=user_style_summary text=…` —
   this is the canonical observability hook.

6. **Style-lock at merge time.** `_merge_stage6_with_blueprints`
   (`agentic_pipeline.py:300-372`) calls `_style_lock_check()` on
   every shot's `output_aesthetic`. If fewer than 50% of the anchor's
   distinctive keywords appear in the model's output, the merger
   **mechanically overwrites `output_aesthetic` with the anchor
   verbatim**. Style propagation is guaranteed, not hoped for.

7. **Top-level metadata.** After Stage 6, the project doc's
   `production_data.production_table.style_summary` is written from
   the user-approved text (fallback to Stage 2 only if the user never
   approved). UI surfaces show the user's style.

### Top-level `production_table` shape

Written to the project doc after Stage 6 completes:
- `title` (from project)
- `aspect_ratio` (from project)
- `style_summary` (user-approved → Stage 2 fallback)
- `continuity_notes` (flattened from Stage 5 `callback_map`)
- `production_notes`:
  - `challenging_shots` (from Stage 5 `consistency_concerns`)
  - `post_production` (empty by default)
  - `recommended_workflow` (default string)
- `total_shots`
- `continuity_review` (aggregated from all Stage 6 batches)

The full `shots` array is **not** on the project doc — it lives in the
`shots/` subcollection because at >400 shots the doc would exceed
Firestore's 1 MB limit. The Visuals tab reads from the subcollection.

---

## Key constants (in `agentic_pipeline.py`)

| Constant | Value | Purpose |
|---|---|---|
| `PACE_TIERS` | dict | words_per_shot per pacing tier |
| `PACING_TOLERANCE` | `0.15` | ±15% before retrying a Stage 4 batch |
| `TARGET_WPS` | `2.7` | Words-per-second for duration normalization |
| `MIN_SHOT_DURATION` | `1.5` | Floor on per-shot duration |
| `STAGE4_BEATS_PER_BATCH` | `10` | Stage 4 batch size in beats |
| `STAGE6_BATCH_SIZE` | `25` | Stage 6 batch size in shots |
| `STAGE6_PARALLEL_WORKERS` | `3` | Stage 6 parallel worker count |
| `STAGE5_TWO_PHASE_THRESHOLD` | `800` | Above this, Stage 5 splits |
| `max_shot_duration` (per-project) | default `6.0`, clamp `[2.0, 15.0]` | Max per-shot duration in seconds |

---

## Field map: where state lives

| Field | Where it's written | Where it's read |
|---|---|---|
| `approved_style` (full dict) | UI autosave (`ui/index.html:11730`) | `_load_project_context` (primary) |
| `style_analysis`, `visual_style_analysis` | Legacy / not written by current code | `_load_project_context` (fallbacks) |
| `narration_data` | Phase 2 generate-script endpoint + autosave | `_load_project_context` |
| `cast_data` | Phase 3 cast tab autosave | `_load_project_context` |
| `format_preset`, `audience`, `tone`, `aspect_ratio` | Project settings autosave | `_load_project_context` |
| `max_shot_duration` | Pacing panel autosave | `_load_project_context` (clamped on read) |
| `production_stages/{1..6}` | `fh.write_production_stage` | `fh.read_production_stages`, UI polls |
| `shots/{shot_id}` | `fh.write_shots` after Stage 6 merge | Visuals tab |
| `production_data.production_table` (metadata only) | After Stage 6 in `run_stage` | Visuals tab top-of-page summary |
| `agentic_flow` checkpoint | `_write_flow` (cancel/pause signaling) | Cooperative check between stages |

---

## Observability — log lines to grep for

When debugging a run, these print statements identify the moment things
go right or wrong:

- `[Stage4 pacing] preset=… tier=… words_per_shot=… total_words=… target=… narration_shape=… beats_field=… beats_count=…`
- `[Stage4 batched] N batches | target=T shots from W words | tier=… format_preset=…`
- `[Stage4 batch K/N] returned X shots (target T, delta ±D)` per batch
- `[Stage4 batch K] returned X shots, below tolerance L–H. Retrying with stricter prompt.` if pacing-retry triggers
- `[Stage4 dedupe+split] pre → post shots (cap=Ds)` if the post-pass added/removed shots
- `[Stage4 normalize] runtime=…s narration_implied=…s shots=N target_wps=2.7 max_shot=Ds`
- `[Stage5 two-phase] N shots — splitting into Phase A + Phase B` only if >800
- `[Stage6 anchor] source=user_style_summary|stage2_rendering_style|none text=…` — **canonical hook for verifying the style fix**
- `[Stage6 parallel] running M batches with 3 workers (of N total)`
- `[Stage6 batch K/N] completed with D deltas (persisted)`
- `[Stage6 merge] style-lock injected on N shot(s) that drifted from rendering_anchor`

If the anchor log shows `source=none`, the user never approved a style
and the pipeline is correctly falling through to Stage 2 — that's not a
bug; that's the documented fallback path.

---

## Smoke test (after deploy)

1. Create a fresh project; paste a ~1700-word narration.
2. Approve a distinctive style (e.g., "Hand-drawn graphic novel: bold
   inky linework, hatched shadows, muted Riso colors") in the Phase 3
   style panel.
3. Set Pacing = Standard, Max Shot = 6s.
4. Click Run Pipeline. Approve each stage as it completes.
5. After Stage 6 finishes, inspect:
   - **Logs:** `[Stage6 anchor] source=user_style_summary` (not
     `stage2_rendering_style`).
   - **Firestore project doc:** `production_data.production_table.style_summary`
     equals the approved text.
   - **Any shot in `shots/` subcollection:** `output_aesthetic` matches
     the approved text; `first_frame_prompt` starts with `SHOT SIZE:`
     and contains 8 labeled sections including `OUTPUT AESTHETIC:`
     followed by the approved text.
6. Visuals tab: generating an image for any shot produces a result in
   the chosen visual style, not a generic photoreal default.
