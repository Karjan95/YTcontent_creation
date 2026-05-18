# Changelog — Studio Engine: persistent assets, history strip, edit parity

**Date:** 2026-05-19
**Files:** `execution/server.py`, `ui/index.html`

## Problem

Users generating scene images/videos in the Visuals tab via the **Studio Engine** (Kie-backed models like Nano Banana 2, Grok Imagine I2V) hit three regressions vs. the legacy Gemini path:

1. **Assets disappeared after ~24h.** When the Kie poll endpoint couldn't download from Kie's `tempfile.redpandaai.co` / `tempfile.aiquickdraw.com` URL and re-host to Firebase Storage, it silently fell back to storing the raw Kie URL. Kie expires those URLs in ~24h, so scenes went dead overnight.
2. **No "previous versions" on regenerate.** The history-strip endpoint scans `images/{project_id}/scene_*` by filename pattern, but Kie uploads landed in `kie_images/{project_id}/{random_filename}` — invisible to the scanner.
3. **No Edit button parity.** Edit only worked for legacy Gemini models. Studio-Engine-generated images couldn't be iterated through the lightbox.
4. **No cross-tab visibility.** Visuals-driven Studio generations didn't show up in the Studio tab's asset gallery.

## Fixes

### Backend (`execution/server.py`)

- **New `_rehost_kie_results()` helper.** Retries Kie download up to 3× with 1s/3s/9s backoff, then retries Firebase upload up to 3×. When `scene_id` is provided, renames the local file to `scene_{id}_{ts}.ext` before upload so it lands at `images/{pid}/scene_{id}_{ts}.ext` (or `videos/...`) — same pattern the history scanner already looks for. **On total failure, never appends the kie URL** — returns `status: 'rehost_failed'` with the failed URLs so the client can surface a retryable error instead of silently storing an expiring link.
- **`/api/kie/poll/<task_id>` and `/api/kie/mj/poll/<task_id>`** now accept `scene_id` and `kind` (`image` | `video`) query params and delegate to the helper.
- **`/api/visuals/scene-video-history`** — new endpoint mirroring `scene-image-history` but scanning `videos/{pid}/scene_*`. Both endpoints now share a `_build_scene_history()` helper.
- **`_studio_dispatch_google_image()`** also renames sync output to `scene_{id}_{ts}` when `scene_id` is set, so Studio-Engine Google generations (Imagen, Nano Banana via Google native) get history-strip parity too.
- **`_ASSET_WRITE_FIELDS`** allows `scene_id` so library mirror entries can be tagged for future "filter by scene" views.

### Frontend (`ui/index.html`)

- **Payload threading.** `_visualsBuildStudioPayload` now includes `scene_id` + `kind`; `_visualsPollStudioKie` appends them to the poll URL.
- **`rehost_failed` handling.** Poll loop maps the new server status to a retryable error state ("Could not save to permanent storage — click Regenerate to retry") and **does not** write a kie URL into the scene.
- **`mirrorSceneToStudioLibrary()`** — fire-and-forget POST to `/api/projects/{pid}/assets` tagged with `scene_id`, `prompt`, `model_id`. Fires on every successful scene generation (sync image, async poll completion, edit). When the Studio tab is already loaded, the new asset is inserted optimistically into `studioState.assets` so the gallery updates without a tab roundtrip.
- **Video history strip.** New `renderVideoHistoryStrip` / `toggleVideoHistoryStrip` / `restoreVideoFromHistory` / `fetchVideoHistoryForScene` / `fetchVideoHistory` paralleling the image versions. Scene-card markup gets a `scene-video-history` slot rendered under the video result. Hover-to-preview thumbs (silent autoplay on mouseover). `fetchVideoHistory()` is called alongside `fetchImageHistory()` at all three call sites (initial render, refresh, project load).
- **Scene state init.** `videoHistory: existing?.videoHistory || []` added alongside `imageHistory`.
- **`gatherProjectState`** caps `imageHistory` / `videoHistory` at the last 20 entries each per scene before serializing to Firestore — bounds the project doc against the 1 MB ceiling.
- **Edit modal goes dynamic.** Hardcoded 3-option `<select>` removed. `openImageEditor()` now populates the dropdown from `studioState.schemas`, filtered to image-producing models with an image input slot (`image_urls` / `reference_images` / etc.). Defaults to the scene's current Studio Engine model if it's edit-capable, otherwise the scene's `imageModel`, otherwise `gemini-3-pro-image-preview`. Includes the legacy Gemini trio always so the picker works even before Studio loads.
- **`submitImageEdit()` routes by model.** Legacy Gemini models (set: `_LEGACY_EDIT_MODELS`) keep the old `/api/visuals/edit-image` path. Everything else routes through `/api/studio/generate` with the source image plugged into the model's image input slot (list vs. scalar detected from `max_count` / `type`). Async (Kie) edits push the previous image into `imageHistory` immediately, then hand off to `_visualsPollStudioKie`. New `_applyEditResult()` shared helper for the sync tails.

## Out of scope

- Legacy broken scenes from past sessions (decided: fix forward silently, no warning badge, no sweep — per Karen's call).
- Repairing already-expired kie tempfile URLs sitting in Firestore.
- Cross-collaborator real-time gallery refresh.
- Lineage tracking beyond the per-scene history strip.

## Validation

- `python3 -m pytest tests/test_api_workflows.py` — 4 passed.
- `python3 -c "import ast; ast.parse(open('execution/server.py').read())"` — OK.
- All 7 `<script>` blocks in `ui/index.html` parse cleanly via `new Function()`.
- End-to-end smoke test on staging still pending.

## Files changed

| File | Change summary |
|------|----------------|
| `execution/server.py` | `_rehost_kie_results`, `_build_scene_history`, kie poll routes, video-history endpoint, Google sync rename, asset write-field allowlist |
| `ui/index.html` | Studio payload threading, `rehost_failed` handling, library mirror, video history strip + helpers, history cap in autosave, dynamic edit picker, Studio-routed edit flow |
