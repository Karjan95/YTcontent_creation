# Changelog — Production Table Resumability, Real Retry Delays, JSON Salvage, Phase 4 Opt-in

**Date:** 2026-05-18 (later same day; complements `changelog_production_table_reliability_streaming_2026_05_18.md`)
**Branch:** main
**Staging URL:** https://content-creation-app-staging-qj4rflrraa-uc.a.run.app

## Why

User report from staging:

1. **40–50 min production-table generation, sometimes freezing.** Cloud Run logs confirmed Gemini 503/429 storms (e.g. clusters at 12:00–12:30 UTC and 04:30–05:00 UTC) where every text phase — Director, Cinematographer, Storyboard, Continuity, DP — would burn its 4 retry attempts inside ~12s of exponential backoff while Gemini's response headers asked for `retryDelay: 57s`. A single coverage retry observed taking **14 minutes** end-to-end (12:14–12:28 UTC) only to fail at the JSON parse step.
2. **"X script beats couldn't be turned into shots" with no recovery.** Logs show JSON parse failures on huge phase outputs: `Phase 3 (Storyboard) JSON parse failed: Expecting ',' delimiter: line 887 column 8 (char 71311)` and `Phase 5 (DP) JSON parse failed: ... (char 121076)`. Gemini was hitting its output token cap mid-array; the strict parser then dropped every shot, including the ~60 that were already complete. The "Retry missing scenes" button itself ran as a synchronous POST that was observed taking **654s and 759s** — a refresh during that window orphaned the retry.
3. **No resume after refresh.** The in-flight `task_id` lived only in JS memory (`productionTaskState`). Refreshing mid-generation orphaned the polling even though the worker kept running on the server and per-batch shots were already in Firestore.

Bundled into this pass: resumability via persisted `task_id`, real backoff using Gemini's own `RetryInfo`, JSON salvage so a truncated phase doesn't lose all shots, a hard 180s per-call ceiling, streaming retry-beats endpoint, and making Phase 4 (Continuity Supervisor) opt-in.

## Changes

### 1. Resumability after refresh (A1 + A2 + 404 handling)

`task_id` is now persisted to `sessionStorage` via the existing `backgroundOps` map, and `loadProject()` rejoins polling automatically.

- `ui/index.html` (`generateProductionTable`, ~line 4742) — after the streaming POST returns `{task_id}`, `setBackgroundOp` writes `{status: 'in_progress', type: 'production', taskId, startedAt}`. `backgroundOps` already serializes through `saveBackgroundOps` to `sessionStorage` (`:2337–2349`), so no new storage plumbing.
- `ui/index.html` (`pollProductionTask`, ~line 4889) — `data.status === 'failed'` branch now calls `setBackgroundOp(state.projectId, {status: 'failed', ...})` so the failed state survives a refresh and the UI doesn't show a phantom spinner.
- `ui/index.html` (`pollProductionTask`, ~line 4854) — `resp.status === 404` is treated as terminal failure (worker / task doc no longer exists). Without this, a resume from a stale `taskId` (e.g. after a multi-day gap) would poll forever.
- `ui/index.html` (`loadProject`, ~line 9225) — when `op.type === 'production' && op.taskId`, calls `startProductionTaskPolling(op.taskId, id, {btn, btnText, spinner, errorDiv}, {retainExistingRows: true})`. The first poll either renders the in-progress state or rolls straight to the terminal handler if the task already finished. If the op has `status: 'in_progress'` but no `taskId` (pre-flight that never got a response), `clearBackgroundOp(id)` clears it so the user isn't stuck on a phantom spinner.
- `ui/index.html` (`startProductionTaskPolling`, ~line 4819) — new `options.retainExistingRows` parameter. When set, the function skips `tbody.innerHTML = ''` so a resume / retry doesn't flash the table empty before re-populating from Firestore. Used by both the resume path and the streaming retry-beats path (below).

### 2. Real retry delays — honor Gemini's `RetryInfo.retryDelay`

The old retry path waited `(2 ** attempt) + jitter` → 1–9s across 4 attempts. Gemini routinely returns `retryDelay: 57s` in its 429 envelope; the client exhausted attempts well inside Gemini's own outage window.

- `execution/gemini_client.py:22–58` — new `_extract_retry_delay(e)` helper. Tries three sources in order: structured `e.response_json['error']['details']` with `'@type': '...RetryInfo'`, then a `[Pp]lease retry in N s` regex on `str(e)`, then a `'retryDelay': 'Ns'` regex (covers stringified SDK exceptions). Capped at `MAX_RETRY_WAIT_S = 90` so a runaway delay can't stall a worker.
- `execution/gemini_client.py:_retry_api_call` — if `_extract_retry_delay` returns a value, wait `delay + jitter` (capped) and log `Waiting Xs (server retryDelay 57.0s) before retry...`. Falls back to exponential backoff when the error envelope has no `RetryInfo`. Attempt count unchanged at 4 total (`MAX_RETRIES = 3`), so the worst-case wait per retry sequence is bounded.

### 3. JSON salvage — recover N-1 shots instead of zero

Gemini occasionally truncates JSON mid-string when it hits its max output token cap. The old `_parse_json_response` raised `JSONDecodeError` and the entire phase returned zero shots; downstream coverage check then reported up to 10 missing beats in one batch (matching the user's screenshot).

- `execution/research_scriptwriter.py:_salvage_truncated_shots(text)` — new helper. Locates the `"shots": [` marker, walks character-by-character with brace-depth + string-state tracking (handles JSON escape rules: `\"`, `\\` etc.), records the position immediately after each completed top-level object inside the array, then reconstructs `text[:array_start] + text[array_start:last_good_end] + "]}"` and re-parses. Returns `None` if the array was already complete (full parse would have worked) or no complete objects exist.
- `execution/research_scriptwriter.py:_parse_json_response` — fall-through fourth step. Order is now: direct parse → outer-brace extraction → salvage → raise. Logs `[parse] Salvaged truncated JSON: recovered N shots` so log analysis shows when salvage fired.
- Smoke-tested against six cases: truncated mid-string with realistic shot objects, truncated with nested braces inside escaped string values, fenced + truncated, intact JSON (passthrough), empty `{"shots": []}`, fully garbled (raises as before). All passed.
- Downstream impact: coverage check sees the recovered shots, only the truly missing beats trigger the targeted retry path — the 71 KB / 121 KB failures in the logs would now recover most shots automatically.

### 4. Hard 180s per-call timeout

Without an explicit timeout, the genai SDK relies on OS-level network timeouts; a stuck connection could stall a phase for minutes before anyone noticed.

- `execution/gemini_client.py:generate_content` — new `timeout_s=180` parameter (default 180s, set to `None` to disable). When non-None, populates `config.http_options = types.HttpOptions(timeout=int(timeout_s * 1000))` — the SDK's `HttpOptions.timeout` is in milliseconds. Verified the snake_case alias works on `GenerateContentConfig` (camelCase `httpOptions` also accepted).
- Why 180s: a healthy Phase 3 / 5 call on a 70-shot batch can legitimately take 60–90s. 180s is a "definitely stuck, not just slow" ceiling — a hung call becomes a retryable exception within 3 min instead of an indeterminate wait.

### 5. Streaming retry-beats endpoint

The "Retry missing scenes" button used to be a synchronous 10+ minute POST (`654s and 759s` observed in `httpRequest.latency`). A refresh during the retry orphaned everything.

- `execution/server.py` — extracted `_run_retry_beats(...)` helper that returns one of `{'kind': 'success'|'coverage_failure'|'error', ...}`. Shared between sync and streaming paths.
- `execution/server.py:/api/generate-production-table/retry-beats` — accepts `streaming: true` in the body. Spawns a daemon worker thread, returns `{task_id, streaming: true}` immediately. Worker writes to `users/{uid}/production_tasks/{task_id}` with `action: 'retry_beats'`, `missing_beats_count: N`. On completion writes the merged table to the project doc and updates task status to `complete` / `coverage_failure` / `failed`. Re-uses the existing poll endpoint `/api/production-task/{task_id}` and `final_table` hydration path from the project doc — no new poll route needed.
- `ui/index.html:retryMissingBeats` — sends `streaming: true`, hands off to `startProductionTaskPolling(taskId, ..., { retainExistingRows: true })` so the partial table stays visible while the retry runs. Also sets a `backgroundOps` entry with `action: 'retry'` so a refresh resumes via the same `loadProject` path as the main flow. Legacy synchronous handling kept as fallback for when the backend doesn't return a `task_id`.

### 6. Phase 4 Continuity Supervisor — opt-in

Per the 2026-05-18 changelog, Phase 4 is the slowest non-critical phase (~90–120s per batch, fall-through on failure). The `quality_mode` parameter on `generate_production_table` was previously a deprecated no-op; it now controls whether Phase 4 runs.

- `execution/research_scriptwriter.py:_generate_single_batch_6phase` — new `skip_continuity: bool = False` parameter. When `True`, Phase 4 is skipped entirely and `corrected_shots = storyboard_shots` directly. Logs `[Production 6-Phase] Phase 4 skipped (fast mode)`.
- `execution/research_scriptwriter.py:generate_production_table` — derives `skip_continuity = (quality_mode or "fast").lower() != "max"`. Threaded into both the small-narration single-call site and the parallel batch worker. Default `'fast'` (`server.py:3324`) means Phase 4 is skipped by default. Users can opt back into the slower / more-polished pipeline by sending `quality_mode: 'max'` — no UI toggle yet, plumbing is trivial to wire up when needed.
- Estimated savings: ~90–120s per batch × N batches. For a 6-batch script this is ~9–12 min off the wall clock with no quality loss for the common case (Phase 4 modifies far fewer shots than the prompt suggests).

## Files Touched

| File | Sections |
|------|----------|
| `ui/index.html` | `setBackgroundOp` taskId persistence (~4742), `pollProductionTask` 404 + failed handlers (~4854, ~4889), `startProductionTaskPolling` retainExistingRows option (~4819), `loadProject` resume path (~9225), `retryMissingBeats` streaming opt-in (~5126) |
| `execution/gemini_client.py` | `_extract_retry_delay` helper, `_retry_api_call` server-delay path (22–95), `generate_content` `timeout_s` param + `HttpOptions` config (67–110) |
| `execution/research_scriptwriter.py` | `_salvage_truncated_shots` helper + `_parse_json_response` fall-through (~364–470), `_generate_single_batch_6phase` `skip_continuity` (~1475, ~1588), `generate_production_table` quality_mode wiring (~993, ~1075) |
| `execution/server.py` | `_run_retry_beats` helper + streaming `retry-beats` route rewrite (~3593–3770) |

## Verification

1. **Resumability** — Start a production-table generation, wait until 1–2 batches stream in (`Act 2/N ready…` banner), then hard-refresh the tab. Expected: spinner returns, polling resumes from the same `task_id` (visible in `sessionStorage.backgroundOps`), final table renders normally. No "start from scratch" loss.
2. **Stale task** — Manually corrupt `sessionStorage.backgroundOps` to point at a non-existent `taskId`, refresh, load the project. Expected: poll gets 404, "Previous task expired — please retry" banner, `backgroundOps` cleared, button re-enabled. No infinite poll loop.
3. **Retry-beats streaming** — Force a coverage failure (e.g. run on a stress script during a Gemini 503 spike). Click "Retry missing scenes" → spinner appears, partial table stays visible (no flash empty), `productionTaskState` shows the new retry `task_id`. Refresh mid-retry → polling resumes, retry completes, full merged table renders.
4. **RetryInfo honor** — In Cloud Run logs after a deploy, grep for `[Retry] ... Waiting Xs (server retryDelay`. Expected: 30–60s waits during 429/503 storms instead of 1.8–9s. Coverage retries that previously failed in 14 min should now succeed in 2–4 min.
5. **JSON salvage** — Log line `[parse] Salvaged truncated JSON: recovered N shots` should appear in place of `Phase X JSON parse failed`. Coverage check then either passes (full recovery) or hits the targeted retry path for the truly missing beats.
6. **Phase 4 skip** — First log line per batch now reads `Phase 4 skipped (fast mode)`. Phase 4 only runs when the request explicitly sets `quality_mode: 'max'`.
7. **Tests** — `pytest tests/test_production_batching.py tests/test_api_workflows.py tests/test_research.py tests/test_all_templates.py` — all 7 pass. JSON salvage smoke-tested against 6 representative inputs.

## Known Gaps / Follow-ups

- **Worker death (Cloud Run cold-start, deploy, OOM mid-run).** If the daemon worker thread itself is killed, the in-flight batch's intra-phase progress is lost. The task doc stays at `status: 'running'` forever; refresh polls a task whose worker no longer exists (the 404 handler doesn't fire because the task doc still exists). Two follow-ups close this:
  1. Persist per-phase progress inside a batch (Director shots → Firestore, then Cinematographer, etc.) so a fresh worker can pick up at the next phase.
  2. Scheduled reaper that marks `status: 'running'` tasks older than ~30 min as `failed` so the UI doesn't poll forever.
- **B1 sub-chunking deferred** — Originally planned to split Phase 3 / Phase 5 calls when input > 8 shots to avoid token-cap truncation at the source. Made redundant for now by JSON salvage (B2); revisit if salvage proves insufficient on production traffic.
- **C3 concurrency tuning deferred** — The 2026-05-18 changelog bumped `ThreadPoolExecutor(max_workers=6)`; with real `RetryInfo` waits the optimal value may now be 4 to leave headroom under Gemini's per-key RPM cap. Needs measurement post-deploy.
- **`gemini-3-pro-image` 429 storms** — Separate Visuals-tab issue (20 RPM cap, observed in same log window). Not in scope here; worth a token-bucket limiter at ~18 RPM in a future pass.
- **UI quality toggle** — The `quality_mode: 'max'` plumbing exists end-to-end but no checkbox in the UI yet. Add when users ask for the polished output.
