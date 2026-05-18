# Changelog — Production Table Reliability, Cross-Act Continuity, Streaming, Token Diet

**Date:** 2026-05-18
**Branch:** main
**Staging revision:** `content-creation-app-staging-00164-2gg`
**Service URL:** https://content-creation-app-staging-qj4rflrraa-uc.a.run.app

## Why

Yesterday's loss-proof script-import fix (2026-05-17) made Phase 2 structuring deterministic. But the *production-table* layer downstream still produced partial output silently — the user re-ran the 17-paragraph fly-biology script and got a table "starting from idk where." Diagnosis: Phase 2 produced a complete narration, but `generate_production_table` was silently dropping batches inside the parallel 6-phase pipeline (`research_scriptwriter.py:910–946`). When batch 1 failed permanently after retries, surviving shots got renumbered `1..N` and the UI showed "Scene 1" that was actually mid-script. The existing `batch_warning` field surfaced only as a soft yellow div (easy to miss).

Bundled into this pass:

1. **Production table dropping scenes silently.** No coverage assertion existed between input beats and output shots. Any batch failure → silent partial table. Any per-phase JSON truncation (Phase 2/3/4/5) → silent shot loss.
2. **No cross-act continuity.** Phase 4 Continuity Supervisor only sees its own batch — act joints get zero review because parallel batches don't see each other.
3. **`last_frame_prompt` wasted DP tokens.** Modern video models (Veo 3.1, Kie Sora, Grok I2V) take first-frame + motion only; the last-frame field was generated, stored, and rendered but never *consumed*.
4. **Time-to-first-visual ~3 minutes.** The `/api/generate-production-table` route was fully synchronous — users waited the whole run before any rows appeared.
5. **Cloud Run streaming hit Firestore's 1 MiB doc limit** (first staging deploy of the streaming feature). Per-batch shots were `ArrayUnion`'d into a single task doc; cumulative shot data with full `first_frame_prompt` + `veo_prompt` exceeded 1 MiB on long scripts → `400 Document … cannot be written` from Firestore.

## Changes

### 1. `last_frame_prompt` removed (token diet)

DP no longer writes the field; UI no longer renders it. Saves both input *and* output tokens — the entire LAST FRAME PROMPT format template (~30 lines of bracket schema) is dropped from `build_prompt_formats`. Defense-in-depth: existing "do NOT add last_frame_prompt" guards in Phase 3/4 prompts are kept (`research_templates.py:3473, :3959`) so intermediate phases can't leak it back.

- `execution/research_templates.py` — DP JSON schema (`:2968`), DP role description (`:4311`), DP prompt header (`:4434`), DP YOUR TASK section (`:4501–4511`), and the DP output example (`:4572`) all stripped of `last_frame_prompt`. `build_prompt_formats` no longer emits the LAST FRAME PROMPT format block (`:2637–2640`) — biggest input-token saving.
- `ui/index.html` — production table `<th>` (`:1681`), `<td>` cell (`:4786`), `copyLastFramePrompts()` function, "🖼️ Copy All Last Frame Prompts" button, `last_frame_prompt` line in `copyAllPrompts`, and the `colspan="7"` raw-text recovery fallback all dropped (now `colspan="6"`).
- Kept: `lastFramePrompt: shot.last_frame_prompt || ''` mapping in `initVisualsFromProductionTable` (`:6845`) so old saved tables still load without errors. The string is just never read downstream.
- Tests: `tests/test_production_batching.py` mocks updated — `script_beat` now echoes the input beat text so the new coverage check (below) recognizes the shots.

### 2. Beat coverage check + targeted retry + per-phase guard + blocking modal

Three layers of defense against silent shot loss.

**Backend layer A — `_check_beat_coverage` + auto-retry inside `generate_production_table`:**
- `execution/research_scriptwriter.py:691–732` — new `_beat_fingerprint(text, n_words=8)` and `_check_beat_coverage(input_beats, final_shots)` helpers. Beat is "covered" iff its lowercased, punctuation-stripped first 8 words appear as a substring in any shot's `script_beat`. Falls back to a 4-word match for Gemini paraphrases.
- After the parallel merge (`:1119–1168`), if any beat is uncovered, build a tiny retry batch containing only the uncovered beats and call `_generate_single_batch_6phase` once. Renumber appended shots from `current_shot_num`. Re-check coverage; if still uncovered → return `{error: "coverage_failure", missing_beats: [...], production_table: <partial>}`.
- Edge case: all batches failed → return error with `missing_beats` populated from the original input so the UI modal can still offer a retry path.

**Backend layer B — per-phase shot-count guard inside `_generate_single_batch_6phase`:**
- `execution/research_scriptwriter.py:1308–1346` — new inner closure `_call_phase(phase_name, prompt, temperature, description, prev_count)` runs the phase, parses shots, and if `len(shots) < prev_count * 0.9` retries the exact same call once with `_retry` description suffix. Catches mid-pipeline JSON truncation cheaply (Gemini output token usage varies run-to-run; retries usually succeed).
- Applied to Phases 2 (Cinematographer), 3 (Storyboard), 5 (DP). Phase 1 (Director) has no prior count. Phase 4 (Continuity) gets a slightly different guard: if it returns <90% of storyboard shots, fall back to uncorrected `storyboard_shots` rather than retrying (continuity is best-effort by design, `:1406–1422`).

**Backend layer C — `/api/generate-production-table/retry-beats` endpoint:**
- `execution/server.py:3469–3552` — new route accepts `{project_id, missing_beats, existing_table, ...same style config as main route}`. Calls `_generate_single_batch_6phase` once, renumbers appended shots, re-checks coverage. Returns `{success, production_table}` on full coverage or `{error: "coverage_failure", missing_beats, production_table}` if still gaps.
- Main route (`:3370–3382`) now returns coverage failures as HTTP 200 with `error: "coverage_failure"` and the partial `production_table` so the UI can render-and-modal rather than 500. Partial table is still persisted to the project doc.

**Frontend — blocking modal:**
- `ui/index.html:211–227` — new `#coverageFailureModal` (matches existing `modal-overlay`/`modal-card` pattern from `#projectNameModal`). Lists missing beats with act/beat header + first 140 chars of text, offers **Retry missing scenes** (cheap targeted retry) or **Use partial** (close modal, keep partial table).
- `ui/index.html:4895–4985` — `openCoverageFailureModal`, `closeCoverageFailureModal`, `retryMissingBeats`. The retry handler reuses the same `currentNarration` / `approvedStyle` / `currentCast` / `currentCreativeDirection` config that the original request used, POSTs to `/api/generate-production-table/retry-beats`, then either re-opens the modal (if still gaps) or renders the completed table + fires a success toast via existing `showToast`.
- `ui/index.html:4737–4748` — `generateProductionTable`'s response handler intercepts `data.error === 'coverage_failure'` (now HTTP 200) and opens the modal instead of throwing.

### 3. Boundary Stitcher (cross-act continuity)

One extra Gemini call per multi-batch run patches act joints; never regenerates shots.

- `execution/research_templates.py:3478–3550` — new `build_boundary_stitcher_prompt(boundary_pairs, visual_brief)`. Narrow prompt: sees only `{prev: shot, next: shot, prev_act, next_act}` pairs + the global `visual_brief.global_motifs`. Strict output schema: `{patches: [{shot_number, field, new_value, reason}]}`. Allowed fields restricted to `camera_movement | camera_angle | lighting_mood | visual | first_frame_prompt`. Explicit instruction: "don't smooth everything — viewers expect cut energy. Only patch genuine breaks."
- `execution/research_scriptwriter.py:740–816` — new `_stitch_act_boundaries(final_shots, visual_brief, api_key, ...)`. Auto-detects boundaries by iterating `final_shots` and finding consecutive shots whose `act` field differs (so any time the act changes, that's a joint). Sends all joints in one call, parses patches, validates field against `_PATCHABLE_FIELDS` whitelist, applies in place by `shot_number`. Returns count of patches applied for logging. All exceptions swallowed — stitcher is non-critical, never blocks completion.
- Call site `:1170–1175` — runs after coverage check passes, before the `merged` dict is assembled. Skipped when `len(batches) == 1` (no joints possible).

### 4. Background task + polling streaming (act-by-act delivery)

The `/api/generate-production-table` route is now a task launcher when `streaming: true` is in the body; legacy synchronous path preserved for tests + fallback.

**Backend:**
- `execution/server.py:3340–3454` — when `streaming: true`, generate `task_id = uuid4().hex`, capture `g.uid` / `g.api_key` into locals (Flask `g` is request-scoped), spawn a daemon thread named `prodtable-<task_id[:8]>` running the full pipeline with a `progress_callback`. Return `{task_id, streaming: true}` immediately.
- `execution/research_scriptwriter.py:823–833` — `generate_production_table` accepts `progress_callback` kwarg. Fires events: `{type: "stage", label, total_batches}` (once batches calculated), `{type: "batch", batch_idx, total_batches, shots}` (per contiguous-prefix flush), `{type: "batch_failed", batch_idx, total_batches, error}`. Errors in the callback are swallowed so they can't break the pipeline.
- `execution/research_scriptwriter.py:1056–1138` — parallel pool restructured. Batches still finish in arbitrary order, but a new `_drain_ready()` closure flushes only the contiguous prefix `1..K` whose batches have all landed. This way shot numbers are still assigned deterministically (no race on `current_shot_num`) while still giving the UI Act 1 as soon as batch 1 finishes.
- `execution/server.py:3437–3457` — new `GET /api/production-task/<task_id>` poll endpoint. Reads task root doc + `batches` subcollection + (if status terminal) the project doc's `production_data` as the authoritative `final_table`.

**Frontend:**
- `ui/index.html:4727–4744` — `generateProductionTable` now sets `requestBody.streaming = true` and hands off to the poller on `data.task_id`.
- `ui/index.html:4817–4940` — new module-level `productionTaskState`, `startProductionTaskPolling`, `pollProductionTask` (2.5 s `setInterval`, matches existing `startPolling` pattern at `:8523`), `stopProductionTaskPolling`, `appendStreamedBatchRows` (inserts rows progressively into `#productionTableBody`), `finalizeStreamedTable` (replaces progressive rows with the final boundary-stitched table on completion). Banner reads `Act K/N ready · X failed…` driven by `total_batches` vs `seenBatchIdx.size`.
- Project-context guard: if user switches projects mid-stream, UI updates suspend (`projectMatches = state.projectId === currentProjectId`) but the poller continues so the original project's project doc still gets written.

### 5. Firestore 1 MiB doc limit fix (subcollection per batch)

First staging deploy of the streaming feature failed for long scripts with `400 Document … (1,350,775 bytes) exceeds the maximum allowed size of 1,048,576 bytes`. Root cause: `firestore.ArrayUnion([...batch shots...])` was accumulating every batch's full shot data (with long `first_frame_prompt` + `veo_prompt` strings) into one task doc. A 10-batch script with verbose prompts blew the cap.

- `execution/server.py:3367–3404` — root task doc shrunk to metadata only (`status`, `project_id`, `title`, `total_batches`, `failed_batches`, timestamps). Per-batch payloads moved to `users/{uid}/production_tasks/{task_id}/batches/{batch_idx}` — one doc per batch, each ~30–60 KB. Each batch doc holds `{batch_idx, shots, created_at}`.
- `execution/server.py:3433–3441` — on completion, `final_table` is written **only** to the project doc (`users/{uid}/projects/{project_id}.production_data`), not the task doc. The project doc is the single source of truth.
- `execution/server.py:3478–3520` — poll endpoint streams the `batches` subcollection (`task_ref.collection('batches').stream()`), sorts by `batch_idx`, and on terminal status (`complete` | `coverage_failure`) hydrates `final_table` from the project doc. Response shape is unchanged from the frontend's perspective — still `{batches_completed: [{batch_idx, shots}, ...], final_table, ...}`.

### 6. Concurrency bump (3 → 6)

`execution/research_scriptwriter.py:953` — `MAX_CONCURRENT_BATCHES = 6` (was `3`). Same 6-phase pipeline per batch; just twice as many batches in flight. For a 10-batch script: wall-clock ~175 s → ~95 s (~46% faster). For 5-batch: ~95 s → ~55 s. Quality unchanged.

Worth knowing: at concurrency 6, the bottleneck shifts to Gemini's per-key RPM cap. Free-tier keys may rate-limit on very long scripts; user-tier keys typically don't.

## Files Changed

| File | Why |
|------|-----|
| `execution/research_templates.py` | Strip `last_frame_prompt` from DP; new `build_boundary_stitcher_prompt` |
| `execution/research_scriptwriter.py` | `_beat_fingerprint`, `_check_beat_coverage`, `_stitch_act_boundaries`, `_PATCHABLE_FIELDS`; per-phase guard helper; `progress_callback` plumbing; contiguous-prefix drain logic; concurrency bump |
| `execution/server.py` | Streaming task launcher; subcollection batch writes; `/api/production-task/<id>` poll endpoint; `/api/generate-production-table/retry-beats` endpoint; coverage-failure passthrough (200, not 500) |
| `ui/index.html` | Drop last-frame column + copy button; coverage-failure modal + handlers; streaming poller (`startProductionTaskPolling`, `pollProductionTask`, `appendStreamedBatchRows`, `finalizeStreamedTable`) |
| `tests/test_production_batching.py` | Mock shots now echo input beat text so coverage check passes |

## Verification

**Token diet (Part 1):**
1. Generate any new production table on staging. DevTools → Network → inspect `/api/production-task/<id>` response (or the project doc's `production_data`). Confirm no `last_frame_prompt` keys appear on any shot.
2. Production table UI has 6 columns (was 7) — no "Last Frame Prompt" header.
3. Load an old project (pre-deploy) — should render fine; legacy `last_frame_prompt` data is just ignored.

**Coverage check + retry (Part 2):**
1. Paste the 17-paragraph fly-biology script from `docs/changelog_script_import_visuals_engine_grok_studio_persistence_2026_05_17.md` (verification section).
2. Run Phase 3. Expect: completion within ~60–90 s (concurrency 6), banner reads `Act K/N ready…` during generation.
3. Confirm Scene 1's `script_beat` begins with "You've seen flies your entire life…" — NOT "Stay until the end,".
4. If a batch happens to fail: blocking modal lists the missing beats with text snippets. Click "Retry missing scenes" → modal closes, table fills, toast confirms `Recovered N missing scenes`.

**Boundary stitcher (Part 3):**
1. Generate a 3+ act production table.
2. Server logs should include `[Production] Boundary stitcher: K joint(s) found` and `[Production] Boundary stitcher: P patch(es) applied across K joint(s)`.
3. In the UI, compare `camera_movement` + `lighting_mood` on the last shot of Act 1 vs the first shot of Act 2 — they should reference each other or follow naturally (e.g. "dolly continues from prev shot's end framing").

**Streaming (Part 4):**
1. Generate a long-paste production table. Act 1's rows should appear in the table within ~30 s (vs ~3 min in the synchronous path).
2. While streaming, refresh the browser tab. Polling resumes from Firestore — previously-streamed rows reappear without re-running the pipeline.
3. Switch to a different project mid-stream. The previous project's row updates suspend; the worker still completes and persists the table to that project's doc.

**Doc-size fix (Part 5):**
1. Repeat the 17-paragraph fly-script test. No `400 Document … exceeds maximum size` from Firestore.
2. In Firebase console, inspect `users/{uid}/production_tasks/{task_id}` — root doc is small (~1 KB). `batches` subcollection has one doc per batch, each ~30–60 KB.

**Concurrency (Part 6):**
1. Generate a 10-batch script. Wall-clock should be roughly half what it was pre-deploy.
2. If user's Gemini key rate-limits: per-batch retries already handle 429s with backoff. Visible in server logs as `[Production] Batch K attempt N failed: …. Retrying in Ms…`.

**Regression:**
- `pytest tests/test_production_batching.py tests/test_api_workflows.py` — 7/7 pass.
- Legacy sync path still works (tests don't set `streaming: true`).
- Existing projects with pre-deploy production tables load without errors.

## Known follow-ups (not in this deploy)

- **Per-row Visuals gating during streaming** — today, Visuals tab still builds from the *completed* production table (not incrementally as batches stream in). Click-to-generate-image-on-Act-1-while-Act-2-streams is deferred until we wire incremental `visualsScenes` updates and `renderVisualsScenes()` calls into `appendStreamedBatchRows`.
- **Old `tempfile.redpandaai.co` URLs** in Kie generations from before 2026-05-17 still show as broken tiles. Self-heal is not retroactive — affected items must be deleted/regenerated.
- **Pipeline pruning options** (drop Phase 4 Continuity Supervisor, merge Phase 2 Cinematographer into Phase 3 Storyboard, draft single-call mode) considered but **declined** to preserve quality. Available as future levers if perceived speed becomes a complaint again.
