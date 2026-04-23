# Changelog: Seedance 2, Topaz Upscaler & Media File Upload — 2026-04-20

## Summary

Added ByteDance Seedance-2, Seedance-2 Fast, and Topaz Video Upscaler models to the platform. Built full multi-reference UI for Seedance in Kie Studio (mode tabs, image refs, video refs, audio refs). Implemented proper file upload pipeline for audio and video reference files. Fixed Topaz not appearing in the Kie Studio video model grid.

---

## 1. New Video Models Added

### `kie_client.py` — Model Registry

Three new models added to `KIE_MODELS`:

**Seedance 2.0** (`seedance-2`)
- Provider: ByteDance
- Modes: t2v, i2v
- Durations: 5s / 8s / 10s / 15s
- Resolutions: 480p / 720p / 1080p
- Pricing: $0.057/s (480p) · $0.125/s (720p) · $0.51/s (1080p)
- Quirks: `first_frame_url` (singular, not array), `generate_audio` bool, `web_search` required field

**Seedance 2 Fast** (`seedance-2-fast`)
- Provider: ByteDance
- Modes: t2v, i2v
- Durations: 4s / 8s
- Resolutions: 480p / 720p only
- Pricing: $0.0775/s (480p) · $0.165/s (720p)

**Topaz Video Upscaler** (`topaz-video-upscale`)
- Provider: Topaz
- Input: existing video URL + upscale factor (1× / 2× / 4×)
- Pricing: $0.06/sec of source video
- No prompt, no image input — completely different payload structure

### `server.py`

- Added all three models to `KIE_VIDEO_MODELS` set
- `visuals_start_animation` route: added Topaz early-return path (uses `video_url` not `image_url`), added Seedance multi-ref params
- `kie_generate` route: added ref image CDN re-upload loop before passing to `create_task`

---

## 2. Seedance Multi-Reference UI in Kie Studio

### `ui/index.html`

Replaced the static image input section in Kie Studio → Videos tab with a dynamically rendered `renderKieVideoInputSection(modelKey)` function.

**Three mode tabs for Seedance models:**
- **First Frame** — single source image for i2v
- **First + Last Frame** — source image + last frame image for controlled motion
- **Multimodal** — up to 9 reference images, up to 3 reference videos, up to 3 reference audio clips

**New state variables:**
- `kieVideoMode` — active mode tab
- `kieVideoLastFrameUrl` / `kieVideoLastFrameDataUrl` — last frame image
- `kieVideoRefImages` — array of `{dataUrl, firebaseUrl, name}`
- `kieVideoRefVideos` — array of `{url, name, uploading}`
- `kieVideoRefAudios` — array of `{url, name, uploading}`

**New handler functions:** `setKieVideoMode`, `handleKieLastFrameUpload`, `clearKieLastFrame`, `handleKieRefImagesUpload`, `removeKieRefImage`, `addKieRefVideo`, `removeKieRefVideo`, `addKieRefAudio`, `removeKieRefAudio`, `clearKieRefMedia`

### `ui/style.css`

Added styles for: `.seedance-mode-tabs`, `.mode-tab`, `.adv-group`, `.ref-images-row`, `.ref-thumb-wrap`, `.ref-thumb`, `.ref-remove`, `.ref-add-btn`, `.ref-media-slot`, `.ref-media-input-row`, `.ref-media-or`, `.ref-media-badge`, `.ref-media-icon`, `.ref-media-name`, `.ref-media-uploading`, `.spinner-tiny`

---

## 3. Audio & Video File Upload (Fix: "Invalid audio format")

**Problem:** Users dragging local files (`file:///…`) to the reference audio/video inputs caused Kie.ai to reject them with `Invalid audio format` — Kie.ai servers cannot access local file paths.

**Solution:** Full upload pipeline — browser file → base64 → Flask endpoint → Firebase Storage → Kie.ai CDN → HTTPS URL stored in state.

### `kie_client.py`

- `upload_image_url` now accepts an `upload_path` parameter (default `"images/user-uploads"`)
- Audio uploads use `"audios/user-uploads"`, video uploads use `"videos/user-uploads"`

### `server.py` — New Endpoint: `POST /api/kie/upload-media`

```
Body:  { data: "data:audio/mp3;base64,…", filename: "clip.mp3", media_type: "audio"|"video" }
Returns: { success: true, url: "https://kieai.redpandaai.co/…" }
```

Pipeline:
1. Decode base64 → temp file
2. Upload to Firebase Storage under `kie_refs/{media_type}/`
3. Re-host Firebase signed URL to Kie.ai CDN via `file-url-upload` endpoint
4. Return Kie.ai HTTPS URL (valid for Kie.ai's `reference_audio_urls` / `reference_video_urls`)

### `ui/index.html`

Reference Video and Reference Audio slots now use file-upload components instead of plain URL text inputs:
- **"Choose Video / Choose Audio"** button opens native file picker
- After picking: file is uploaded via `/api/kie/upload-media`, spinner shown during upload, filename badge shown on success
- **"or"** + URL input field remains as fallback for pasting HTTPS URLs directly
- Files that fail upload show a toast error and reset the slot
- Slots reset when switching video models

---

## 4. Topaz Video Upscaler in Kie Studio

**Problem:** Topaz was registered with `type: "upscale"` in `KIE_MODELS`, so `renderKieModelCards("video")` filtered it out and it never appeared in the Kie Studio video grid.

**Fix (`kie_client.py`):**
- Changed `type` from `"upscale"` to `"video"` so it passes the grid filter
- Updated `_build_task_payload` Topaz detection from `config.get("type") == "upscale"` to `"upscale" in config.get("modes", [])` — more robust

Topaz now shows as a card in the Kie Studio video tab. Selecting it renders a URL input + upscale factor selector (1× / 2× / 4×). The existing `kieGenerate()` Topaz early-return path handles submission.

---

## Files Modified

| File | Changes |
|------|---------|
| `execution/kie_client.py` | Added 3 models, `upload_path` param, Topaz type/detection fix |
| `execution/server.py` | `KIE_VIDEO_MODELS` update, Topaz/Seedance route handling, new `/api/kie/upload-media` endpoint |
| `ui/index.html` | `renderKieVideoInputSection`, mode tabs, multi-ref state + handlers, file-upload components, model switch reset |
| `ui/style.css` | Media upload slot styles, spinner |
