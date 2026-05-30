# Agentic Stage 4 — No-Loss Beat Coverage + Word-Budget + Parallel Batching

**Date:** 2026-05-29
**Status:** Shipped to staging (pending validation)
**Related:** Builds on the agentic 5-stage pipeline (`docs/agentic_5stage_pipeline_2026_05_25/`) and reuses the beat-coverage net from the 6-phase pipeline (`execution/research_scriptwriter.py`). Reuses the resume/`missing_beats` UI+server path from `docs/changelog_production_table_unlimited_scale_2026_05_24.md`.

This file is the single source of truth for the work done in this session.

---

## 1. Problem

A user's project ("The Third Wave Experiment", 16 narration beats → 174 shots)
generated a production table that was **silently missing one entire beat** —
beat #10, "The Reveal" (ACT 3, the emotional payoff). All 9 sentences of that
beat were absent from every shot's `script_beat`; `shots_with_beatname("The
Reveal") = 0`.

Confirmed via Firestore export (`execution/export_project.py`), Cloud Run logs,
and a sentence-level coverage diff of the narration against the shot list.

The user's stated priorities:
1. **Don't fail in the first place** — prevention, not after-the-fact patching.
2. **No placeholder/stub shots** — recovery must produce real, directed shots.
3. **Never leave the user without a production JSON**, and **never make the
   whole run slow** for the safety net.
4. Then: if parallelizing Stage 4 is faster *without* losing quality, do it.

---

## 2. Root Cause (two compounding problems)

**(a) Output-cap truncation at a BATCH boundary — not the script's end.**
Stage 4 (`agentic_pipeline.py`) cut narration into fixed groups of
`STAGE4_BEATS_PER_BATCH = 10` and sent each group to Gemini as a separate
request. "The Reveal" is beat #10 of 16 — mid-script overall, but it sat at
**position 10/10: the last beat of batch 1**. Batch 1 (beats 1–10 ≈ **831
words**) was emitted as one large JSON object (~25 fields/shot); Gemini hit its
hard **65,536-token** output ceiling, produced shots for beats 1–9, and the
response was **cut off at its tail — beat #10**. Batch 2 (beats 11–16) ran as a
fresh request and returned fine, which is why everything after the gap was
present. Verified: the dropped beat lands exactly on the batch boundary — the
signature of output-cap truncation, not random model omission. Load-dependent,
which is why generation "worked sometimes, failed other times": light batches
fit under the cap, heavy ones truncated their last beat.

**(b) The only existing safety check counted shots, not beats.**
The Stage 4 pacing retry re-asked the model only when a batch returned *too few
shots* vs. its proportional target. The other 9 beats over-produced enough
shots to clear that target, so the batch looked complete — the check was
**blind to a whole beat contributing zero shots.**

The 6-phase pipeline already had a beat-coverage net (`_check_beat_coverage`,
`_beat_fingerprint`, targeted coverage retry, `coverage_failure` return). The
agentic pipeline had **none** of it.

---

## 3. Solution

Four layers, in `execution/agentic_pipeline.py` unless noted.

### Layer 1 — Prevent: word-budget batching
`_split_narration_into_batches()` now closes a batch when it hits **either**
`STAGE4_BEATS_PER_BATCH` beats **or** the new `STAGE4_MAX_BATCH_WORDS = 500`
word budget, whichever comes first. A single beat larger than the budget
becomes its own batch (a beat is never split across batches here). New helper
`_beat_word_count()` mirrors the field precedence of `_batch_word_count()`.

This keeps every Stage 4 call comfortably under the 65K output cap so the model
always has room to emit every beat. Verified on the real narration: the
old single 831-word batch becomes 3 batches of 390 / 441 / 394 words — none
over budget, all 16 beats preserved in order.

### Layer 2 — Detect: per-batch beat coverage (zero API cost)
After each batch (and after its pacing retry), `_check_beat_coverage` (imported
from `research_scriptwriter.py`) verifies every input beat in that batch
produced ≥1 shot. Pure in-memory string match — no API cost unless a beat is
actually missing.

### Layer 3 — Recover: targeted re-generation with real shots
If a beat produced zero shots, Stage 4 re-generates **only that beat** (up to
`STAGE4_COVERAGE_MAX_ATTEMPTS = 2` attempts) via the normal
`build_stage4_shot_list_prompt` → `_call_stage4_batch` path with a
coverage-recovery instruction. Real, directed shots — no stubs/placeholders.

### Layer 4 — Never block: final check + resume flag
A final `_check_beat_coverage` over the whole narration runs after the
dedupe/split/normalize post-passes. Any residual gap:
- does **not** block the run and does **not** insert placeholder shots;
- the run finishes with a complete, saved production JSON (Stages 5/6 proceed);
- `missing_beats` is returned from Stage 4 and written into
  `pipeline_checkpoints/task_state` (in `run_stage`) so the **existing Resume
  banner** (shared with the 6-phase pipeline) offers a one-click targeted
  retry via `/api/generate-production-table/retry-beats`.
- A clean Stage 4 run clears any stale coverage flag.

### Parallel Stage 4 (speed — quality-neutral)
Stage 4 batches are **fully independent**: each batch's prompt is built only
from the shared Production Bible (fixed before Stage 4) + its own narration
slice, and the model's per-batch shot numbers are discarded and reassigned at
assembly. So running batches concurrently is **byte-for-byte equivalent** to
sequential — only wall-clock changes.

The sequential `for` loop was refactored into a stateless `_run_one_batch()`
run through a `ThreadPoolExecutor` (`STAGE4_PARALLEL_WORKERS = 3`), mirroring
the proven Stage 6 pattern. Results are **assembled in batch-index order** (not
completion order) and then renumbered globally + sequentially, so the shot
sequence is identical to the sequential version. A single batch (the common
short-script case) skips the pool entirely — no overhead.

This erases the speed cost of the extra word-budget batches: more (smaller)
batches now run at the same time instead of one after another. Measured on the
real Third Wave narration (network boundary stubbed at 0.5s/call): 3 batches
ran concurrently → **0.51s wall-clock vs ~1.50s sequential**, all 16 beats
covered, shots in correct order.

### Prompt reinforcement
`build_stage4_shot_list_prompt()` (`agentic_prompts.py`) now explicitly
instructs the model to NEVER omit a beat — including the last beat in the
batch — alongside the existing "Cover every beat" line.

---

## 4. Files changed

| File | Change |
|------|--------|
| `execution/agentic_pipeline.py` | New consts `STAGE4_MAX_BATCH_WORDS`, `STAGE4_COVERAGE_MAX_ATTEMPTS`, `STAGE4_PARALLEL_WORKERS`; import `_check_beat_coverage`; new `_beat_word_count`; word-aware `_split_narration_into_batches`; refactored Stage 4 batch loop → stateless `_run_one_batch` run in a `ThreadPoolExecutor` with ordered assembly; per-batch + final coverage checks with targeted recovery; thread `missing_beats` → `task_state` in `run_stage`. |
| `execution/agentic_prompts.py` | "NEVER omit a beat" reinforcement in `build_stage4_shot_list_prompt`. |
| `tests/test_agentic_pipeline.py` | New `TestStage4WordBudgetBatching` (5), `TestBeatCoverageNet` (2), `TestStage4ParallelAssembly` (2). |

No changes needed in `server.py` / `ui/index.html` — the `missing_beats` →
`task_state` → resume-banner path already existed for the 6-phase pipeline and
is reused as-is.

---

## 5. Tests

`tests/test_agentic_pipeline.py`: **54 passed** (44 prior + 10 new). New tests:
- Word-budget batching: splits before beat-count when words are heavy; never
  drops/reorders a beat; a lone over-budget beat gets its own batch; beat-count
  still caps when words are light; short script stays one batch (no extra calls).
- Coverage net: detects a beat absent from all `script_beat`s; passes when all
  covered.
- Parallel assembly: out-of-order completion still assembles in batch-index
  order with globally sequential shot numbers; no shot lost across batches.

Full suite: **166 passed**, plus 2 pre-existing unrelated failures
(`test_scriptwriter_tracking::...6phase_tags_stages`,
`test_structured_research::...no_config_when_all_none`) and 1 pre-existing
Playwright UI error — all confirmed failing identically on the clean tree.

---

## 6. Scope decisions

- **Pipeline-only fix.** The existing "Third Wave" project was NOT
  auto-recovered — the user re-triggers generation themselves once deployed.
- **No stub/placeholder shots** anywhere; recovery is always real AI shots,
  with a flag-and-resume fallback as the final seatbelt.

---

## 7. Verification plan (staging)

1. Run agentic generation on a long script (≥800-word act) via Studio on
   `content-creation-app-staging`.
2. Confirm logs show `[Stage4 parallel] running N batches with 3 workers`,
   multiple smaller batches, and `[Stage4 coverage] OK — all N beats covered`.
3. Confirm all input beats appear in the final shots; runtime is not worse than
   before (parallelism offsets the extra batches).
4. Confirm a deliberately truncated batch triggers
   `[Stage4 batch ...] coverage gap` → targeted recovery and still yields a
   complete saved JSON; if forced to fail recovery, the Resume banner shows the
   missing beat.
