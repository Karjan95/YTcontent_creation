# Changelog — Visuals Batch Kie Compatibility

**Date:** 2026-05-27
**Status:** Implemented locally, NOT deployed to staging or production.

This logs every file change made for the Kie batch compatibility fix
described in `plan.md`.

---

## execution/server.py

**Section:** `_studio_dispatch_kie_generic` (around line 1071).

**Before:** Any failure from `kie_create_task` was flattened to
HTTP 500, including Kie's 429 rate-limit responses. The frontend
batch couldn't tell rate-limits apart from any other error and
couldn't retry.

**After:** Detect `"429"` or `"rate limit"` in the upstream error
string and forward as HTTP 429. Other failures still return 500.

```python
result = kie_create_task(schema['id'], prompt, g.kie_api_key,
                         image_urls=image_urls, **extras)
if not result.get('success'):
    err = result.get('error', 'Kie task failed')
    err_lower = str(err).lower()
    if '429' in err_lower or 'rate limit' in err_lower:
        return jsonify({'error': err}), 429
    return jsonify({'error': err}), 500
return jsonify({**result, 'backend': 'kie_generic'})
```

`kie_client._kie_request()` already retries 429 internally 3 times
with 2-8s backoff before raising; a 429 reaching this code path is a
sustained rate violation, not a blip. Forwarding lets the frontend
apply its own longer backoff.

---

## ui/index.html

### New helpers block (added before `generateAllImages`)

A self-contained block introducing Kie batch primitives:

| Helper | Purpose |
|---|---|
| `KIE_DISPATCH_RATE_HZ = 2` | Token-bucket refill rate matching Kie's documented 20/10s. |
| `KIE_DISPATCH_BUCKET_SIZE = 4` | Small burst allowance for scheduling jitter. |
| `KIE_MAX_INFLIGHT = 20` | Concurrent polling cap (well under Kie's 100+). |
| `_kieBucket`, `_refillKieBucket`, `_waitForKieToken` | Token bucket. Honors `_batchCancelled` between sleeps. |
| `_kieInflight`, `_acquireKieInflightSlot`, `_releaseKieInflightSlot` | Counting semaphore + resolver queue. |
| `_waitForKieDrain` | Wait for all in-flight slots to release. |
| `_dispatchStudioWithKieRetry(payload)` | POST `/api/studio/generate` with 4-attempt exponential backoff on HTTP 429 (2s → 4s → 8s → 16s + jitter). |
| `_awaitSceneTerminal(idx, kind)` | Polls the scene's status sentinel until `'complete'` or `'error'`. |
| `_willBatchUseKie(kind)` | Returns true if the active batch engine's schema has `backend === 'kie'`. |
| `_batchDispatched`, `_batchComplete`, `_completionTimes` | Counter state with rolling 30s window for ETA. |
| `_resetBatchCounters`, `_markBatchComplete` | Counter mutators. |
| `_updateBatchUI(btn, total)` | Updates button text + new status line + ETA. |
| `_hideBatchStatusLine` | Hides the status line at batch end. |
| `_runKieBatchImages(scenes, btn, total)` | Orchestration loop for Kie image batches. |
| `_runKieBatchVideos(scenes, btn, total)` | Orchestration loop for Kie video batches. |

### `generateAllImages` — Phase 2 rewrite

The Phase 2 block (the actual batch loop, when
`visualsGenerationPhase === 'preview'`) was restructured:

- Counters reset at the start (`_resetBatchCounters()`).
- Engine detected: `isKieBatch = _willBatchUseKie('image')`.
- **Kie path:** call `_runKieBatchImages(remaining, btn, totalToGenerate)`.
  Token bucket and in-flight semaphore handle pacing.
- **Gemini path:** keep existing CONCURRENCY=3 worker pool, but also
  wire it to the new counters (`_batchDispatched++` and
  `_markBatchComplete()` per scene).
- **Auto-retry phase:**
  - For Kie batches: `await _waitForKieDrain()` first, then run the
    `<50% failed` retry pass through `_runKieBatchImages` again.
  - For Gemini batches: existing retry-worker loop, now also
    updating the new counters.
- Status line hidden at the end (`_hideBatchStatusLine()`).

### `animateAllScenes` — engine-aware branch

Added an early branch: if `_willBatchUseKie('video')` is true, run
`_runKieBatchVideos(marked, btn, totalToGenerate)` against the
client-side orchestration. The legacy Veo server-batch path
(`/api/visuals/start-batch-animation`) is unchanged for non-Kie video
models — Google handles rate-limiting there server-side via
`gemini_client._retry_api_call()`.

### `updateImageProgress` / `updateVideoProgress` — done/polling split

Both updaters now distinguish `polling` from `generating`:

```js
function updateVideoProgress() {
    const total = visualsScenes.length;
    const done = visualsScenes.filter(s => s.videoStatus === 'complete').length;
    const polling = visualsScenes.filter(s => s.videoStatus === 'polling').length;
    const generating = visualsScenes.filter(s => s.videoStatus === 'generating').length;
    const active = polling + generating;
    // ...
    if (polling > 0 && generating === 0) {
        el.textContent = `Videos: ${done}/${total} done · ${polling} polling`;
    } else if (active > 0) {
        el.textContent = `Videos: ${done}/${total} done (${active} animating...)`;
    } else {
        el.textContent = `Videos: ${done}/${total} done`;
    }
}
```

Same shape applied to `updateImageProgress`.

### `_visualsPollStudioKie` — progress updater on terminal

Added `if (kind === 'image') updateImageProgress(); else updateVideoProgress();`
to each of the three terminal-status paths (completed with persisted
URLs, completed with no URLs → error, Kie reported failed). This
refreshes the topbar live as Kie tasks complete.

### Action-bar markup

Added a new status-line div inside `.visuals-action-bar`:

```html
<div id="batchStatusLine" class="batch-status" style="display: none;"></div>
```

---

## ui/style.css

### `.visuals-action-bar`

Added `flex-wrap: wrap;` so the new `batchStatusLine` div can drop
to its own row instead of disrupting the existing two-column layout.

### `.batch-status` (new rule)

```css
.batch-status {
    flex-basis: 100%;
    text-align: right;
    font-size: 0.78rem;
    color: rgba(255, 255, 255, 0.55);
    margin-top: 4px;
    font-variant-numeric: tabular-nums;
}
```

Tabular numerals keep the dispatched/complete counts from jittering
horizontally as they tick.

---

## Files NOT modified

Verified during investigation to be already correct:

- `execution/server.py` `/api/visuals/sync-storage-images` —
  engine-agnostic, scans `images/{project_id}/scene_*`.
- `execution/server.py` `/api/visuals/download-all` — zips
  `images/{project_id}/`, `videos/{project_id}/`, `audio/{project_id}/`.
- `execution/server.py` `/api/kie/poll/<task_id>` — already names
  files `scene_{id}_{ts}.ext` via `_rehost_kie_results`.
- `execution/kie_client.py` — internal 3-retry on 429 already in place.
- `_visualsPollStudioKie` state machine (besides the progress-updater
  additions noted above) — its terminal-status writes are what drive
  `_awaitSceneTerminal`.

---

## Outstanding

- Not deployed to staging or production.
- Verification plan steps 1–9 in `plan.md` have not been run.
- No automated tests added (this is UI batch orchestration; hard to
  unit-test without a real Kie key + browser).
