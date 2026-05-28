# Visuals Batch — Kie Compatibility & Counter Fix

**Date:** 2026-05-27
**Status:** Implemented locally, not deployed.

## Context

The "Generate Remaining N Images" button + the topbar `Videos: X/Y done`
counter only worked correctly for the synchronous Google paths. When the
user toggled "Use for batch" on a Kie-backed Studio engine the batch
silently misbehaved:

1. **The CONCURRENCY=3 cap was bypassed.** `generateSceneViaStudio`
   returned the moment it got a Kie `taskId`; the poll loop ran in the
   background. The batch worker loop saw the call as "done" and
   immediately picked up the next scene. At 229 scenes the UI fired
   ~229 Kie createTask requests as fast as JS could dispatch — far
   above the 20/10s ceiling.
2. **Kie rejects above 20 requests / 10 seconds.** Per
   `docs.kie.ai/1973359m0.md`: *"Up to 20 new generation requests per
   10 seconds"*, and *"rejected requests will not enter the queue"* —
   so a 429 means the dispatch is *lost* unless we retry.
3. **The progress counter lied.** `Cancel Generation (X/Y)` incremented
   when a worker *dispatched* a Kie task, not when the image landed.
   The button could read "All Done" while 200 pollers were still
   running.
4. **Post-batch auto-retry didn't catch async Kie failures cleanly.**
   It ran after `Promise.all(workers)` resolved, but for the Kie path
   that's right after dispatch — pollers hadn't finished yet.

`Sync lost images` and `Download all assets` were already engine-
agnostic — Kie outputs already land at `images/{project_id}/scene_*`.

## What changed (summary)

1. **Engine-aware batch orchestration.** Detect whether the active
   batch uses sync (Google) or async (Kie) path up front; apply a
   different concurrency model to each.
2. **Kie dispatch pacing.** Frontend token bucket caps `createTask`
   rate to **2/sec** (the documented 20-per-10s limit). Burst
   allowance of 4. Transparent exponential-backoff retry on HTTP 429:
   2 → 4 → 8 → 16 s, max 4 attempts.
3. **Kie in-flight semaphore.** Allow up to **20 concurrent polling
   tasks**. Well under Kie's documented "100+" allowance.
4. **Real `dispatched · complete` counter.** Button text becomes
   `Cancel Generation (X complete · Y dispatched)`. New status line
   below shows `N polling · ETA ~M min`. Topbar `Videos: X/Y done · Z
   polling` for video batches.
5. **Cancel = stop dispatches, let in-flight polls finish.** Paid Kie
   tasks aren't wasted; recovery records already let refresh resume.
6. **Same model for video batch.** `animateAllScenes` branches: when
   the global engine is Kie video → routes through new orchestration;
   Veo native stays on the legacy server batch.
7. **Auto-retry moved to AFTER pollers drain.** Wait for
   `_kieInflight === 0` before running the existing `<50% failed`
   retry pass.

## Design choices

### Rate-limiting lives in the frontend only

Backend rate-limiting would need cross-request shared state, add
latency to every Studio call, and doesn't protect against a malicious
client. The batch loop is the only path that fires dozens of tasks.
One token bucket inside the batch loop is sufficient. The backend
just needs to faithfully propagate Kie's 429 status — which it did
NOT (it flattened to HTTP 500). Fixed.

### Concurrency caps

- Gemini sync: 3 (unchanged)
- Kie async dispatch rate: 2/sec
- Kie async in-flight cap: 20 concurrent polling tasks

These map directly to documented limits. At 400 scenes:
- Gemini: ~134 batches of 3 (sequential bursts) — depends on tier
- Kie: dispatched over ~200s, 20 always cooking, finishes in
  ~5-10 minutes for images, longer for videos (per-task time)

### Cancel semantics

`_batchCancelled = true` flag is checked inside the rate-limiter and
semaphore waits. New dispatches stop immediately. In-flight pollers
continue to completion — they self-terminate via the existing
`_visualsPollStudioKie` path and release their in-flight slot.

## Files modified

| File | Change |
|---|---|
| `execution/server.py` | `/api/studio/generate` Kie dispatch now forwards HTTP 429 (was flattened to 500). |
| `ui/index.html` | New helpers block before `generateAllImages`: token bucket, in-flight semaphore, 429-aware retry, terminal-status waiter, engine detection, batch UI updater, `_runKieBatchImages`, `_runKieBatchVideos`. |
| `ui/index.html` | `generateAllImages` branches on `_willBatchUseKie('image')`. Auto-retry moved after Kie drain. |
| `ui/index.html` | `animateAllScenes` branches on `_willBatchUseKie('video')`. |
| `ui/index.html` | `updateImageProgress` / `updateVideoProgress` show `done · polling` split when scenes are polling. |
| `ui/index.html` | `_visualsPollStudioKie` calls progress updater on terminal status. |
| `ui/index.html` | Added `<div id="batchStatusLine">` to the action bar markup. |
| `ui/style.css` | `.batch-status` rule + `flex-wrap: wrap` on `.visuals-action-bar`. |

**Not modified (already engine-agnostic):**
- `Sync lost images` / `Download all assets` endpoints.
- `/api/kie/poll/<task_id>` (file naming already correct).
- `_visualsPollStudioKie` terminal-status state machine.

## Verification plan (run on staging)

1. **Gemini baseline:** 10-scene batch with a Gemini engine — confirm
   CONCURRENCY=3, counter increments correctly, all reach `complete`.
2. **Backend 429 passthrough:** confirm a Kie 429 reaches frontend as
   HTTP 429.
3. **Kie happy path:** 20-scene batch with a Kie image model.
   Confirm 2/sec dispatch spacing, ≤20 in-flight, counter shows
   `X complete · Y dispatched` correctly, all reach `complete`.
4. **Kie 429 backoff:** force 429s, confirm console shows retry
   backoff, no scene permanently stuck.
5. **Cancel mid-batch:** 50-scene Kie batch, cancel at ~10
   dispatches. Dispatches freeze, in-flight polls finish, button
   returns to `Generate Remaining N`.
6. **Refresh resume:** start 30-scene Kie batch, refresh at ~10
   dispatches. Pollers re-attach via existing `resumeKieRecoveryForVisuals()`.
   User manually re-clicks Generate Remaining for undispatched.
7. **Sync lost images (regression):** mid-batch, kill some pollers,
   click Sync lost images. Confirm Firebase blobs re-linked.
8. **Download all assets (regression):** mixed Gemini+Kie batch zip
   contains outputs from both engines.
9. **Video batch:** Kie video model, 5-scene Animate All. Confirm
   topbar `Videos: X/Y done · Z polling` updates correctly.

## Out of scope (deferred)

- Backend rate-limit enforcement (frontend is sufficient).
- Pre-batch cost preview modal (user declined).
- Auto-resume of undispatched scenes on refresh (user prefers manual).
- Gemini Batch API integration for very-large jobs (24h SLA, out of
  scope for interactive UX).
- Per-engine concurrency tuning UI.
