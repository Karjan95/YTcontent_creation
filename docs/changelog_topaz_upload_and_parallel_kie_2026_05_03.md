# Changelog: Topaz Video Upload + Parallel Kie Studio Generation — 2026-05-03

## Summary

Two improvements to the Kie Studio video tab:

1. **Topaz Video Upscaler** now accepts a direct file upload (mp4 / mov / mkv, max 50 MB) in addition to pasting an HTTPS URL. The unused text prompt textarea is hidden when Topaz is selected since the Kie API doesn't take one.
2. **Parallel video generation.** Users can now fire off multiple Kie video jobs at once. Each running task renders its own pending card in the gallery with an independent progress indicator instead of locking the Generate button until the single active job completes.

---

## 1. Topaz Source-Video Upload

### `ui/index.html`

**New state:**
- `kieTopazSourceVideo = {url, name, uploading}` — tracks the uploaded source video for Topaz separately from Seedance reference media.

**New handlers:**
- `handleKieTopazVideoUpload(event)` — validates size (≤ 50 MB) and MIME (`video/mp4`, `video/quicktime`, `video/x-matroska`) on the client, then routes the file through the existing `/api/kie/upload-media` pipeline (Firebase Storage → Kie.ai CDN).
- `clearKieTopazSourceVideo()` — clears the chosen source.

**`renderKieVideoInputSection` (Topaz branch):**
- Replaced the URL-only input with a "Choose Video" button + paste-URL fallback (same pattern as Seedance reference video slots).
- Hint text now lists the actual Topaz constraints (mp4 / mov / mkv, max 50 MB) and notes that no text prompt is needed.
- Upload spinner / filename badge / clear button render based on state.

**`kieGenerate('video')` (Topaz branch):**
- Validation now blocks submission while an upload is in flight and accepts either the uploaded Kie CDN URL or a manually pasted URL.
- After `createTask` returns the `taskId`, the Generate button re-enables immediately so the user can queue another job.

**`selectKieModel`:**
- For Topaz, the prompt area stays visible (it contains the Generate button + input section) but the textarea inside it is hidden, since Topaz's createTask payload only accepts `video_url` and `upscale_factor`.

> **Note on the earlier regression:** the first iteration hid the entire `kieVideoPromptArea`, which inadvertently hid `kieVideoImageSection` (nested inside it) and the Generate button — Topaz appeared as a bare title. Now only the textarea is toggled.

### File picker

`<input type="file">` `accept` attribute restricted to `video/mp4,video/quicktime,video/x-matroska` so the OS file dialog only surfaces formats Kie's Topaz model actually accepts.

### Why the prompt is hidden

Per [docs.kie.ai/market/topaz/video-upscale](https://docs.kie.ai/market/topaz/video-upscale), the createTask payload is:

```json
{
  "model": "topaz/video-upscale",
  "input": { "video_url": "...", "upscale_factor": "1" | "2" | "4" }
}
```

Topaz Video Upscale is a pixel-domain enhancer (Topaz Video AI under the hood), not a generative model — there's no text-conditioning channel for it to consume.

---

## 2. Parallel Video Generation

### Problem

After clicking Generate, `kieGenerate('video')` set `btn.disabled = true`, and `kieStartPolling` only re-enabled the button when polling finished. The single shared `#kieVideoProgressContainer` and the "generating" highlight on the model card were also globally mutated. Net effect: one job at a time per Kie Studio tab.

### Fix — `ui/index.html`

**`kieGenerate(type)`:**
- Re-enables the Generate button immediately after `kieStartPolling(taskId, …)` is called for both the Topaz and standard paths. Failure path (createTask error) still re-enables.

**`kieStartPolling(taskId, type, modelKey)`:**
- No longer touches `kieVideoGenerateBtn`, `kieVideoProgressContainer`, or the model-card "generating" class. Each task is fully independent.
- On entry, calls `addKiePendingCard(taskId, type, modelKey)` to drop a placeholder card at the top of the gallery.
- On `processing` polls, updates that card via `updateKiePendingCard(taskId, progress, hasProgress)`.
- On `completed`, removes the pending card and prepends the real video via the existing `addToKieGallery` flow, then `triggerAutosave()`.
- On `failed`, swaps the card to a failed state via `markKiePendingCardFailed(taskId, error)` with a Dismiss button, plus the existing `showKieError` toast.

**New helpers:**
- `addKiePendingCard(taskId, type, modelKey)` — creates `<div class="kie-gallery-item kie-pending-card" id="kie-pending-{taskId}">` with spinner + model display name + status text.
- `updateKiePendingCard(taskId, progress, hasProgress)` — updates the per-task status line (e.g. `Generating… 42%`).
- `markKiePendingCardFailed(taskId, errorMsg)` — replaces card body with error icon, message, and Dismiss button.
- `removeKiePendingCard(taskId)` — DOM cleanup on completion.

`kieActivePolling` (existing `Map<taskId, intervalId>`) already keyed each polling loop separately; no changes needed there.

### Fix — `ui/style.css`

Added:
- `.kie-pending-card` — dashed cyan border, min-height 180px, centered body, fits the gallery's `auto-fill` grid.
- `.kie-pending-body` — flex column, gap 10px, centered.
- `.kie-pending-spinner` — 32px ring with cyan top border, `kie-spin` 0.9s linear infinite.
- `@keyframes kie-spin` — 360° rotation.
- `.kie-pending-label` / `.kie-pending-status` — typography for model name + progress text.
- `.kie-pending-failed` / `.kie-pending-fail-icon` — red-tinted variant for the error state.

### Result

- Click Generate → pending card appears, button re-enables.
- Tweak model / prompt / refs → click Generate again → second pending card appears alongside the first.
- Repeat as many times as desired (subject to Kie's per-key rate limits and your credits).
- Each card resolves into its own video tile when its task finishes.

---

## Files Modified

| File | Changes |
|------|---------|
| `ui/index.html` | Topaz upload state + handlers, Topaz section render, prompt textarea toggle, Generate button re-enable after createTask, `kieStartPolling` rewritten to use per-task cards, four new pending-card helpers |
| `ui/style.css` | `.kie-pending-card` and related pending/failed-state styles |

## Deployment

Deployed to staging (`content-creation-app-staging`, region `us-central1`) across revisions `00100-6qk` → `00103-gq5`.

## Files Not Touched

- `execution/server.py` — no backend changes needed; the `/api/kie/upload-media` and `/api/kie/generate` endpoints already supported video uploads and parallel task creation.
- `execution/kie_client.py` — Topaz payload (`model: "topaz/video-upscale"`, `input.video_url`, `input.upscale_factor`) already matches Kie's docs exactly.
