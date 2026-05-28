# Changelog — Agentic 5-Stage Production Pipeline

**Date:** 2026-05-25
**Status:** Implemented, deployed to staging

This is the cutover from the 6-phase parallel-batching production pipeline
to a sequential 5-stage agentic pipeline. See `plan.md` for the design
rationale and `docs/production_table_json_resilience_2026_05_25/changelog.md`
for the prior session that motivated this rewrite.

---

## What shipped

### Backend (new files)

- **`execution/agentic_schemas.py`** — Five Pydantic v2 models, one per
  stage. All fields are required (no `Optional`) and use explicit nested
  models (no raw `dict`/`list[dict]`) so the emitted JSON schemas are
  Gemini-safe — zero `additionalProperties`, zero `anyOf`. Verified with
  a unit test that scans the JSON schema strings.

- **`execution/agentic_prompts.py`** — Five prompt builders + per-stage
  bible-section renderers + the `_compose_bible(stages, title)` helper.
  Each prompt follows the same brief structure: persona / brief /
  principles / bible context / optional user feedback / output. No
  template fill-ins like `"shot_number": "<from input>"` — the schema
  carries the shape, the prompt carries the brief.

- **`execution/agentic_pipeline.py`** — Single-stage executor
  (`run_stage()`) and auto-flow worker (`run_pipeline_worker()`).
  Stage 5's server-side merge (`_merge_stage5_with_blueprints()`) takes
  the LLM's `shot_deltas` and merges them into Stage 4's full shot
  blueprint by `shot_number`. This deterministically carries forward
  every blueprint field — the LLM is no longer asked to copy values, so
  the drop-field bug from Phase 5 can't recur. Cooperative cancellation
  via `GenerationCancelled` sentinel, polled between stages by the
  worker and inside `run_stage` before each Firestore write.

- **`tests/test_agentic_pipeline.py`** — 17 unit tests covering: schema
  round-trips, Gemini-safe schema emission, `_compose_bible` ordering
  and pending/error skip, Stage 5 merge carry-forward, revised-field
  overrides, unmatched-delta tolerance, user-edits dotted-path
  application, prompt-builder shape checks, feedback inclusion.

### Backend (modified)

- **`execution/firestore_helpers.py`** — Added four new helpers:
  - `read_production_stages(uid, pid)` — list all stage docs ordered by
    `stage_number`.
  - `read_production_stage(uid, pid, n)` — single stage doc.
  - `write_production_stage(uid, pid, n, payload)` — upsert one stage,
    merging into existing doc. Auto-adds `updated_at` and `stage_number`.
  - `clear_production_stages(uid, pid)` — wipe the subcollection (used
    by Cancel and by fresh-run reset).
  - `mark_stages_stale(uid, pid, from_stage)` — mark stages
    `[from_stage..5]` as `status='stale'` so the UI can warn the user
    that downstream output may no longer match earlier-stage edits.
  - Extended `cascade_delete_project_subcollections()` to also wipe
    `production_stages/` on project delete.

- **`execution/server.py`** — Eight new endpoints (~250 lines inserted
  after the existing `production_task_cancel_route`):
  - `POST /api/production/run` — initializes 5 pending stage docs and
    spawns the auto-flow worker.
  - `GET  /api/production/state` — returns `{stages, flow_state,
    bible_markdown, task_id}` for UI polling.
  - `POST /api/production/pause` — sets the paused flag; worker exits
    at the next stage boundary.
  - `POST /api/production/resume` — clears paused, spawns a fresh
    worker starting at the current stage.
  - `POST /api/production/cancel` — full-wipe semantics: clears
    `production_stages/`, `shots/`, `pipeline_checkpoints/`, plus
    `production_data` on the project doc.
  - `POST /api/production/stage/<n>/approve` — marks a complete stage
    as approved (cosmetic — auto-flow doesn't gate on it).
  - `POST /api/production/stage/<n>/edit` — persists user edits
    (dotted-path → value). Marks `[n+1..5]` stale automatically.
  - `POST /api/production/stage/<n>/regenerate` — re-runs stage `n`
    with optional feedback, then auto-flows the rest. Marks downstream
    stale before kicking off.

### UI (modified `ui/index.html`)

- Replaced the old "Generate Production Table" button group + Resume
  banner with:
  - **Top control bar:** Start / Pause / Resume / Cancel buttons +
    status text.
  - **Five collapsible stage panels** (`#stagePanel1` through
    `#stagePanel5`), each with status badge, per-stage body renderer,
    Approve / Regenerate-with-feedback action row.
- Removed `productionResumeBanner` and `phase3Error` — their roles are
  taken by the panel statuses and inline `.stage-error-box`.
- Kept `#productionErrorLog` (the persistent error tile list) — same
  pattern, repurposed to surface stage-level errors as well.
- ~900 lines of new JS for: `startProductionPipeline`,
  `pollProductionState`, five stage-specific renderers, `approveStage`,
  `openStageRegenerate`/`submitStageRegenerate`/`cancelStageRegenerate`,
  `pausePipeline`/`resumePipeline`/`cancelPipeline`, and
  `restoreAgenticPipelineState` (wired into the existing
  `restoreProjectState` so refresh/project-switch rehydrates panels).

### UI (modified `ui/style.css`)

- Added `.stage-panel*` rules: collapsible panel with header / body /
  toggle, 6 status-badge variants (pending/running/complete/approved/
  stale/error) with pulse animation on `running`, action row, inline
  feedback textarea, error box, running indicator.

---

## Bugs fixed during implementation

- **Stage 5 prompt f-string crash on unescaped JSON example braces.**
  The output instruction included raw `{ variety_check, ... }` and
  `{ foreground, midground, background }` which Python tried to parse
  as f-string fields. Doubled to `{{ ... }}`. Surfaced by the prompt-
  builder unit tests on first run.

- **`#productionCancelBtn` had `display: none` in CSS but my new JS uses
  inline `style.display = 'inline-flex'` to show.** Reverted the CSS
  default to no display rule, so inline JS toggling works without
  fighting specificity.

---

## Lessons baked into the design

These are the failure modes from the prior 6-phase pipeline that this
rewrite deliberately removes:

1. **No more carry-forward by the LLM.** Stage 5 only outputs the new
   fields (prompts + revisions). Everything else comes from Stage 4 via
   server-side merge. The LLM can't drop fields it's not asked to emit.

2. **No more parallel batches with no shared memory.** Pipeline is
   sequential; each stage is one Gemini call holding the full bible in
   context. No boundary stitcher needed — continuity emerges naturally.

3. **No more `Optional` fields.** Every Pydantic field is required.
   Empty string / empty list is allowed, but the key is always present.
   Gemini's constrained decoder can't skip required fields.

4. **No more `additionalProperties: true`** from raw `dict`/`list[dict]`
   types. Every nested structure is its own BaseModel.

5. **JSON parser ladder reused from `research_scriptwriter.py:576`**
   as defense-in-depth even though the schema constraint should
   eliminate parse failures.

---

## Cutover state

- Old 6-phase code in `research_scriptwriter.py` is **untouched and
  still callable** — the old `/api/generate-production-table` route is
  preserved for the legacy `USE_LEGACY_PRODUCTION=1` env flag (one-
  release safety net).
- The UI now talks exclusively to the new `/api/production/*`
  endpoints. The old "Generate Production Table" path is no longer
  reachable through the UI.
- Visuals tab consumption is **unchanged** — Stage 5 writes the merged
  shots to the same `shots/` subcollection and the same
  `production_data.production_table.shots` field on the project doc
  that the Visuals tab has always read from.

---

## Verification

### Unit
```
$ python3 -m pytest tests/test_agentic_pipeline.py -v
17 passed in 1.22s
```

### Compile
```
$ python3 -c "py_compile agentic_pipeline.py server.py"
ok
```

### Schema safety
```
$ for stage in 1..5: dumps(model.model_json_schema())
   .count('additionalProperties') == 0
   .count('anyOf') == 0
```
All five clean.

### Staging deploy

Deployed via `./deploy_staging.sh` (see deploy task output). Service URL:
`https://content-creation-app-staging-637532740810.us-central1.run.app`.

### Manual smoke test (after deploy)

The user should:
1. Open a project that has a finished Phase 2 (Script).
2. Click **▶ Start Pipeline** on the Production tab.
3. Watch Stages 1→5 light up in sequence (each ~30s–2min).
4. Try **⏸ Pause** between stages — worker should stop at next boundary.
5. Try **↻ Regenerate with feedback** on Stage 2 with a note like
   "use a colder palette" — Stage 2 reruns and Stages 3–5 mark stale,
   then auto-flow.
6. After Stage 5 completes, confirm the production table populates and
   the Visuals tab reads it correctly.
7. Refresh the browser mid-run — panels should rehydrate from
   Firestore in the same state.

---

## Files touched

```
Created:
  execution/agentic_schemas.py        (~190 lines)
  execution/agentic_prompts.py        (~500 lines)
  execution/agentic_pipeline.py       (~400 lines)
  tests/test_agentic_pipeline.py      (~240 lines)
  docs/agentic_5stage_pipeline_2026_05_25/plan.md
  docs/agentic_5stage_pipeline_2026_05_25/changelog.md   (this file)

Modified:
  execution/firestore_helpers.py      (+70 lines: 5 helpers + cascade)
  execution/server.py                 (+250 lines: 8 routes)
  ui/index.html                       (+800 lines JS, +90 lines DOM)
  ui/style.css                        (+180 lines stage-panel rules)

Removed (DOM only — code paths preserved for legacy flag):
  #productionResumeBanner block
  #phase3Error element
```

---

## Follow-up patch — 2026-05-26

User-reported issues after first staging smoke:

1. **Production table came back as a summary** — 1700-word script produced only
   20 shots (old 6-phase pipeline produced 117 from the same script). Root
   cause: Stage 4 prompt had no shot-count target, so the LLM defaulted to
   roughly one shot per beat.
2. **Style ignored** — user's typed `creative_direction` text never reached
   Stage 5's `first_frame_prompt` / `veo_prompt`. Root cause: style fed only
   to Stage 2/3, Stage 2 schema had no slot for "rendering style," Stage 5
   prompt instructed "weave, don't list" so the model compressed prompts to
   one-liners with no style anchor.
3. **No approval gating** — pipeline auto-flowed through all 5 stages; user
   edits on completed stages didn't propagate downstream unless re-runs were
   triggered manually.

### Changes

**Schemas (`agentic_schemas.py`)**
- Added `rendering_style: str` to `Stage2WorldDesign`. This is the canonical
  output-aesthetic phrase that every downstream prompt must echo verbatim.

**Pacing math (`agentic_pipeline.py`)**
- Ported `PACE_TIERS` and `FORMAT_PRESETS.auto_pacing_tier` lookup from
  `research_scriptwriter.py`. New helpers `_resolve_pacing_tier`,
  `_count_narration_words`, `_compute_target_shot_count` derive a target
  shot count from the narration word count and the project's format preset.
  Surfaced on the context dict as `target_shot_count`, `pacing_tier`,
  `total_words`.

**Prompts (`agentic_prompts.py`)**
- Stage 2: prompt now requires a one-sentence `rendering_style` translating
  the user's creative direction. Bible renderer foregrounds it.
- Stage 4: accepts `target_shot_count` / `pacing_tier` / `total_words` /
  `style_analysis`. Embeds a non-negotiable pacing brief with an explicit
  range (target ± 15 %). Adds a "Style anchor" block.
- Stage 5: accepts `style_analysis` / `rendering_style` / `aspect_ratio` /
  `batch_info`. **Restored the 12-section labeled `first_frame_prompt`
  template** (SHOT SIZE / SUBJECT CORE / POSE / ENVIRONMENT / VIBE /
  LIGHTING SOURCE / LIGHTING DIRECTION / LENS FX / DEPTH OF FIELD / COLOR
  PALETTE / OUTPUT AESTHETIC / AESTHETIC TAGS / ASPECT RATIO) and the
  structured `veo_prompt` shape (shot/action, Lighting:, Camera:, Audio:,
  Style:). The OUTPUT AESTHETIC and Style: lines are pinned to the
  canonical `rendering_style` from Stage 2.

**Stage 5 batching (`agentic_pipeline.py`)**
- New `_run_stage5_batched()` runs Stage 5 in sequential batches of
  `STAGE5_BATCH_SIZE = 25` shots. Each batch sees full bible + full style +
  only its blueprint slice. Deltas + continuity reviews accumulate across
  batches and merge once at the end. Cooperative-cancel checked between
  batches. Avoids the 65 536 max-output-tokens ceiling on 200+ shot runs.

**Approval gating (`agentic_pipeline.py` + `server.py` + `ui/index.html`)**
- Worker rewritten to execute exactly ONE stage and exit. No auto-flow.
- `/api/production/run` runs Stage 1 only.
- `/api/production/stage/<n>/approve` now does real work: marks stage
  approved, finds the lowest pending/stale/error stage, spawns a worker for
  it, returns `{advancing_to_stage, task_id}`. The UI restarts polling on
  the new task_id.
- `/api/production/stage/<n>/regenerate` no longer auto-flows downstream —
  it just re-runs the target stage. Downstream stays stale until the user
  reviews + approves each one.
- `/api/production/pause` and `/api/production/resume` deleted. With
  stage-by-stage approval the pipeline is paused by default between
  stages; `cancel` covers mid-stage interrupt.
- `find_next_runnable_stage()` helper added.

**UI (`ui/index.html`)**
- Pause/Resume buttons removed from the top control bar. `pausePipeline()` /
  `resumePipeline()` JS deleted.
- Approve button label is now dynamic: `Approve & Run Stage N+1: <label>` so
  the user knows exactly what they're triggering.
- Stage 2 panel renders the `rendering_style` field at the top in an
  amber-bordered call-out so the user can review/edit the canonical
  aesthetic before approving.
- Polling stops on `awaiting_approval` flow status (worker is idle between
  stages); `approveStage()` restarts polling with the new task_id.

### Verification

```
$ python3 -m pytest tests/test_agentic_pipeline.py -v
17 passed in 1.27s
```

Smoke checks (PACE_TIERS math + prompt-builder content):

```
       micro → tier=High Energy target=340 shots
  quick_take → tier=High Energy target=340 shots
  short_form → tier=   Standard target=189 shots
    standard → tier=   Standard target=189 shots
   deep_dive → tier=    Relaxed target=155 shots
      custom → tier=   Standard target=189 shots

Stage 4 prompt has target?       True
Stage 4 prompt has style anchor? True
Stage 5 has SHOT SIZE label?     True
Stage 5 has OUTPUT AESTHETIC:    True
Stage 5 has rendering_style:     True
```

---

## Second follow-up — 2026-05-26 (scale to ~500 shots)

User wanted the pipeline to handle 1000+ shot / 30-min videos without
quality regressions. Walked through the failure modes and got user
sign-off on a 6-stage redesign targeting ~500-shot reliability:

| Risk found | Fix |
|---|---|
| Continuity drift: Stage 5 batches independently wrote prompts and reinvented vocab | **New Stage 5 — Continuity Brief**: a single Gemini call that sees the *full* shot list and emits character locks, vocabulary locks, callback map, per-act atmospheres. Stage 6 batches read this brief verbatim. |
| Stage 4 single-call cap: 500+ blueprints exceed 65K-token output | **Batched Stage 4**: split narration into ~10-beat groups, allocate per-batch shot targets proportional to word count, renumber shots server-side so batches don't have to coordinate. |
| Cloud Run timeout (60 min) at 500+ shots | **Per-batch checkpointing**: Stage 6 persists each batch's deltas to Firestore as soon as the batch returns. New `/api/production/stage/6/resume` endpoint reads the checkpoint and picks up at the next unfinished batch. |
| 1 MB Firestore doc limit on project doc | **Dropped `shots` array from project-doc write**. UI Visuals tab already reads from the `shots/` subcollection. |

### Stage map

| # | Role | What it does | Batched? |
|---|---|---|---|
| 1 | Director | Story Treatment | – |
| 2 | Production Designer | World & Design (+ `rendering_style`) | – |
| 3 | Director of Photography | Cinematography Plan | – |
| 4 | Director + Storyboard | Shot List blueprints | ✓ ~10 beats/batch |
| 5 | Script Supervisor | **Continuity Brief** (new) | – (full shot list, one call) |
| 6 | Director of Photography | Final Prompts | ✓ 25 shots/batch, checkpointed |

### Files touched

```
Modified:
  execution/agentic_schemas.py      Added Stage5ContinuityBrief, renamed Stage5Final → Stage6Final, kept alias.
  execution/agentic_prompts.py      Added build_stage5_continuity_brief_prompt; renamed final-prompts builder to stage 6;
                                    Stage 4 builder accepts batch_info + starting_shot_number; bible renderers extended.
  execution/agentic_pipeline.py     Added _run_stage4_batched, _run_stage6_batched; Stage 4 + 6 dispatched through batched
                                    executors in run_stage; per-batch checkpointing for Stage 6; dropped shots-array write
                                    to project doc; find_next_runnable_stage and get_pipeline_state now range 1..7.
  execution/server.py               All stage range checks bumped 1..6; new POST /api/production/stage/6/resume; seed
                                    6 pending stage docs in /run.
  ui/index.html                     Added stagePanel6 DOM + Stage 6 renderer; new Stage 5 renderer for the Continuity
                                    Brief (character/vocab/callback/atmosphere blocks); Resume button on Stage 6 errors
                                    when checkpoint exists; STAGE_LABELS_UI/STAGE_ROLES expanded to 6 entries.
  tests/test_agentic_pipeline.py    Renamed Stage 5 tests → Stage 6; added Stage5ContinuityBrief schema/roundtrip test,
                                    Stage 5 prompt sees-full-list test, Stage 6 reads-continuity-brief test, Stage 4
                                    batching helper tests. Now 23 tests, all green.
```

### Known follow-ups (deferred)

- Stage 5 Continuity Brief is itself a single Gemini call. At 1000+ shots
  the compact shot listing approaches input-token comfort. If the user
  needs >1000 shots reliably, the Brief itself will need batching with a
  global merge.
- Stage 5 input renderer (`_compact_shot_for_brief`) truncates wardrobe
  long-form. If wardrobe vocabulary is rich, the brief may miss locks.
- No retry-on-batch yet. A transient 503 from Gemini still fails the
  whole batch — `Resume Stage 6` recovers but the user has to click it.

---

## Third follow-up — 2026-05-26 (Restoration & Hardening)

User ran the new pipeline on production and surfaced three concurrent
regressions vs the old pipeline:

1. **Shot count collapsed.** A ~1700-word script with Standard pacing
   produced 20 shots vs the old pipeline's 117 (expected ~190). Root cause
   in `_count_narration_words`: it only handled `narration` and `beats`
   keys, missing the legacy `acts → beats` nesting. When narration_data
   used the nested shape, total_words returned 0, target_shots floored to
   0, the model returned whatever it wanted (~10 per batch × 2 batches).

2. **`first_frame_prompt` regressed to a paragraph.** Old: 2181-char
   labeled template. New: 325-char paragraph. The Stage 6 schema's
   `first_frame_prompt: str` was unconstrained — model returned whatever
   shape it pleased despite prompt instructions.

3. **Style propagation broken.** User's `rendering_style` from Stage 2
   appeared as preamble text but nothing enforced it per-shot. Old
   pipeline hard-overrode the `OUTPUT AESTHETIC` field at merge time
   (`research_templates.py:2528`); new pipeline lost this mechanism.

Plus user-requested architecture improvements for scale (500-1000 shots
typical, occasionally more):

- **Pacing as user-controlled baseline** with ±15% tolerance, not
  hardcoded math
- **Style enforcement at schema level**, not just prompt instructions
- **Parallel Stage 6 batches** for speed
- **Per-batch error visibility** with manual resume control
- **Stage 5 scale strategy** that doesn't risk continuity drift

### Resolution

Plan written to
[`docs/plan_pipeline_restoration_2026_05_26.md`](../plan_pipeline_restoration_2026_05_26.md).
Implementation summary:

#### Stage 4 shot schema (narrative anchors restored, character renamed)

`_ShotBlueprint` in `agentic_schemas.py` now carries:
- **Added:** `act`, `beat`, `script_beat` (verbatim narration line),
  `cutting_rationale`, `emotion`
- **Renamed:** `expression_state` → `character_expression`,
  `wardrobe_state` → `character_outfit`
- **Dropped:** `subject`, `action`, `beat_ref` (subsumed by new fields)
- **Kept:** cinematography (`composition`, `camera_move`, `lens`, `angle`,
  `directors_intent`, `timestamp`, `duration`, `shot_number`)

#### Stage 6 prompt schema split into 7 structured fields

`_FinalShotDelta`'s single unconstrained `first_frame_prompt: str` is
gone. Replaced with seven required schema fields the model fills:
`shot_size`, `subject_pose`, `environment`, `lighting`, `lens_dof`,
`color_palette`, `output_aesthetic`. The model can't return a paragraph
because the schema enforces the shape.

Server-side merger (renamed `_merge_stage6_with_blueprints`) assembles
the labeled `first_frame_prompt` from these seven fields. Same precision
as the old 12-section template at ~1/3 the tokens.

#### Style-lock at merge time

`_style_lock_check()` scans every shot's `output_aesthetic` for the key
phrases from Stage 2's `rendering_style`. If the model drifted, the
merger mechanically overwrites `output_aesthetic` with the anchor
verbatim. Mirrors the old `research_templates.py:2528` hard-override.
Style propagation is now a hard guarantee, not a hope.

#### Pacing diagnostics + tolerance retry

- `_count_narration_words` now handles `narration` / `beats` /
  `acts → beats` / `script_beat` field shapes.
- `_compute_target_shot_count` logs `target / tier / words_per_shot /
  narration_shape / beats_count` so future regressions are visible.
- `_run_stage4_batched` validates per-batch shot count against
  `±15%` tolerance band; **auto-retries the batch once** with a
  stricter prompt that quotes the actual count if it undershoots.

#### Stage 5 — single-call up to 800 shots, two-phase above

- Tightened `_compact_shot_for_brief` to pipe-delimited
  `{shot_number}|{beat}|{character_expression}|{character_outfit}|{script_beat}`
  — 1000 shots fits in ~200 KB input.
- Above `STAGE5_TWO_PHASE_THRESHOLD` (800 shots) `_run_stage5_two_phase`
  splits the **output** work across two calls (both see the full shot
  list, so zero drift): Phase A locks characters; Phase B locks
  vocabulary, callbacks, atmospheres, concerns. Safe to ~3000 shots.

#### Stage 6 parallelization

`ThreadPoolExecutor(max_workers=STAGE6_PARALLEL_WORKERS=3)`:
- Cancel check moved **inside each future** (was once-per-loop).
- Per-batch checkpoint write guarded by `threading.Lock()` so concurrent
  batches can't trample `completed_batches`.
- gemini_client already retries 503/429/quota internally; added a
  **wrapper retry** at the batch level for parse/empty-response failures
  (different error class).
- If one batch fails, in-flight batches finish (so their checkpoints
  save), then a `RuntimeError` summarizes all failures. `Resume Stage 6`
  picks up at the next unfinished batch.

Speed gain at 1000 shots: ~20 min sequential → ~7 min parallel.

#### Top-level `production_table` metadata restored

After Stage 6 completes, the project doc now carries:
- `title`, `aspect_ratio`, `total_shots` (existing)
- `style_summary` (from Stage 2 `rendering_style`)
- `continuity_notes` (flattened from Stage 5 `callback_map`)
- `production_notes` (`challenging_shots` from Stage 5
  `consistency_concerns`, plus default `recommended_workflow`)
- `continuity_review` (existing)

Shots array stays out of the doc — still streams from `shots/`
subcollection (Firestore 1 MB doc limit at >400 shots).

#### UI: per-batch error breakdown

When Stage 6 errors with prior progress, the UI now lists each batch
(`✓ Batch N — completed` / `⚠ Batch N — not completed`) alongside the
error text. The Resume button label clarifies it auto-resumes at the
next unfinished batch.

Stage 4 panel renamed columns: `Beat` → `Act / Beat` (both shown), added
`Script Beat` column showing the verbatim narration line, `Subject /
Action` column replaced with `Character` (expression + outfit).

#### Tests

`tests/test_agentic_pipeline.py` updated for new schema + behaviors:
- `TestStage6Merge` (renamed from `TestStage5Merge`) — 6 tests including
  `test_style_lock_inject_on_drift` and `test_style_lock_no_inject_when_intact`
- New `TestPacingMath` class — 4 tests covering all narration shapes,
  including the `acts → beats` nesting that caused the original regression
- New `TestStage6Assembly` class — `test_assemble_produces_eight_labels`,
  `test_style_lock_check`
- Existing prompt-builder tests updated for the new field names and the
  pipe-delimited Stage 5 compact form

**Result:** 31/31 agentic pipeline tests pass. Pre-existing failures in
`test_scriptwriter_tracking` and `test_structured_research` (unrelated
to this work — `thinking_level` kwarg mismatch in fixture, gemini_client
default config change).

### Files modified

- `execution/agentic_schemas.py` — Stage 4 + 6 shot schemas, Stage 5
  Phase A + Phase B schemas, dropped `Stage5Final` alias
- `execution/agentic_prompts.py` — Stage 4 + 6 prompt builders, tighter
  `_compact_shot_for_brief`, new `build_stage5_phase_a/b_prompt`
- `execution/agentic_pipeline.py` — diagnostic logging, pacing retry,
  wrapper retry, `_merge_stage6_with_blueprints` (renamed),
  `_assemble_first_frame_prompt`, `_style_lock_check`,
  `_run_stage5_two_phase`, parallel Stage 6 with semaphore + lock,
  top-level metadata
- `ui/index.html` — Stage 4 panel column rework, Stage 6 per-batch
  error breakdown
- `tests/test_agentic_pipeline.py` — fixtures + new tests
- `docs/plan_pipeline_restoration_2026_05_26.md` — new plan document

---

## Fourth follow-up — 2026-05-27 (style anchor field fix + shot-duration controls)

After the restoration patch shipped, the pipeline ran cleanly on a fresh
1700-word script: 159 shots, ~6s per shot, no batch failures, sub-7-minute
total runtime. The user verified pacing and the Stage 6 prompt structure
were right — but one regression remained: **the user-defined style was
not reaching the final shot prompts.**

### Symptom

Every shot in the latest run carried the same `output_aesthetic` —
expected, that's the style-lock doing its job — but the locked text was a
generic LLM-invented "Photoreal cinematic macro-cinematography…"
sentence, not the user's chosen style. Confirmed by inspection of
`docs/production_table_1779854277957.json`: 159 unique shots, one
identical `output_aesthetic`, none of it traceable to the user's input.

### Root cause — field-name mismatch

The UI persists the user-approved style dict on the project document
under the key `approved_style` (set at `ui/index.html:11730`, restored at
`:11268-11272`). The agentic pipeline's context loader at
`agentic_pipeline.py:204-205` read `project.get('style_analysis')` /
`project.get('visual_style_analysis')` — **neither key exists on the
project document.** `server.py` has zero writes that would land under
those keys; only the legacy single-shot endpoint at line 3763 accepted
`style_analysis` in the request body.

The cascade with empty `style_analysis`:

1. **Stage 2** prompt at `agentic_prompts.py:391-413` has two branches.
   With `style_summary` present it instructs the LLM to paste the user
   text verbatim into `rendering_style`; with `style_summary` empty it
   tells the LLM to invent a generic sentence. Empty input → generic
   invention.
2. **Stage 6 anchor resolution** at `agentic_pipeline.py:918-937` picks
   `user_style = style_analysis.style_summary` first and only falls back
   to Stage 2's `rendering_style` if absent. With the user dict empty,
   the anchor was Stage 2's invention.
3. **Style-lock merger** at `agentic_pipeline.py:343-346` then force-
   stamped the invented anchor onto every shot's `output_aesthetic`.

Net effect: style propagation looked correct (uniform across shots) but
the source was wrong.

### Fix

`agentic_pipeline.py:204-211` — add `approved_style` as the first-priority
read on the project doc:

```python
'style_analysis': project.get('approved_style')
                  or project.get('style_analysis')
                  or project.get('visual_style_analysis') or {},
```

One line of logic, three lines of comment explaining why
`approved_style` is preferred. Both legacy keys remain as fallbacks so
any older project doc that happened to carry one keeps working.

With this change:

- Stage 2 sees `style_analysis.style_summary` populated → fires the
  verbatim-paste branch → `rendering_style` matches the user text
  exactly.
- Stage 6 resolves the anchor with `anchor_source='user_style_summary'`
  (visible in the `[Stage6 anchor]` log line).
- Style-lock check still runs as a safety net; if any per-shot drift is
  detected the merger overwrites with the user's text.
- The top-level `production_table.style_summary` written to the project
  doc at `agentic_pipeline.py:1443-1451` now also reflects the user's
  choice rather than the Stage 2 fallback.

### Other behaviors documented during this session

The previous follow-up's plan mentioned them only in passing — surfacing
here so the changelog reflects current `agentic_pipeline.py`:

#### Configurable max shot duration

`max_shot_duration` is now a per-project field (UI input at
`#maxShotDurationInput`, default 6s, persisted on the project doc).
Read at `agentic_pipeline.py:191-197`, clamped to `[2.0, 15.0]`, threaded
through Stage 4 batch builder, dedupe-and-split post-pass, and duration
normalizer.

#### Deterministic dedupe + split post-pass on Stage 4 (`_dedupe_and_split_shots`)

After the batched LLM output:

1. **Dedupe** — adjacent shots that share the same `script_beat` get
   their text re-sliced into clauses on natural breath boundaries (em
   dash, semicolon, comma, conjunction). Cinematography fields stay
   per-shot; only the text differs.
2. **Split oversize** — any shot whose `script_beat` would need more
   than `max_shot_duration × TARGET_WPS` words to read is replaced by K
   child shots, each with a clause and cycling vocab from
   `_SPLIT_CAMERA_MOVES` / `_SPLIT_LENSES` / `_SPLIT_SHOT_SIZES` so the
   children feel like a real sequence instead of duplicates.

Both passes renumber shots sequentially after the rewrite.

#### Deterministic duration + timestamp normalization (`_normalize_shot_durations`)

Replaces whatever the model wrote with
`max(MIN_SHOT_DURATION, word_count(script_beat) / TARGET_WPS)`
(constants: `TARGET_WPS=2.7`, `MIN_SHOT_DURATION=1.5s`). Then caps each
shot at `max_shot_duration` as a safety net and rebuilds `timestamp` as
cumulative `MM:SS`. The runtime of the assembled film now matches the
narration's reading time instead of whatever the model invented.

### Files modified (this follow-up)

- `execution/agentic_pipeline.py:204-211` — accept `approved_style` as
  primary source for `style_analysis` context
- `docs/agentic_5stage_pipeline_2026_05_25/changelog.md` — this section
- `docs/plan_pipeline_restoration_2026_05_26.md` — rewritten as an
  as-built reference reflecting current pipeline behavior

### Verification

- Manual trace of the field flow from `ui/index.html` save → project doc
  → `_load_project_context` → Stage 2 prompt branching →
  Stage 6 anchor resolution → merger style-lock.
- The `[Stage6 anchor]` log line will print `source=user_style_summary`
  on the next run if the user has approved a style; otherwise
  `stage2_rendering_style`. This is the canonical observability hook
  for confirming the fix took effect.
- No code change required to `server.py`, the schemas, the prompts, or
  the UI — the regression was purely in the project-doc field name
  lookup and is fully contained to one read.
