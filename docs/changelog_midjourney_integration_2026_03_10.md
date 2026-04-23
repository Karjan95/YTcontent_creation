# Changelog: Midjourney API Integration (Kie Studio)

**Date:** 2026-03-10
**Scope:** Full Midjourney API support via Kie.ai's dedicated `/mj/` endpoints, added as 3rd sub-tab in Kie Studio

---

## Summary

Added **Midjourney generation** (T2I, I2I, Video) to the Kie Studio tab using Kie.ai's dedicated Midjourney API endpoints (`/api/v1/mj/*`). Includes **Upscale** and **Vary** actions on generated images. All existing Kie Studio and Gemini functionality remains untouched.

---

## Key Technical Decision

Midjourney on Kie.ai uses **completely separate API endpoints** from the standard models:

| Standard Models | Midjourney |
|----------------|------------|
| `POST /api/v1/jobs/createTask` | `POST /api/v1/mj/generate` |
| `GET /api/v1/jobs/recordInfo` | `GET /api/v1/mj/record-info` |
| Payload: `{model, input: {...}}` | Payload: flat `{taskType, prompt, speed, ...}` |
| Response: `data.state` (string) | Response: `data.successFlag` (0/1/2/3) |
| Result: `data.resultJson.resultUrls` | Result: `data.resultInfoJson.resultUrls[].resultUrl` |

This required dedicated create/poll functions rather than routing through the existing `create_task()`/`poll_task()`.

---

## Modified Files

### `execution/kie_client.py`

**4 new functions added:**

| Function | Endpoint | Purpose |
|----------|----------|---------|
| `mj_create_task()` | `POST /mj/generate` | Create MJ generation with flat payload |
| `mj_poll_task()` | `GET /mj/record-info` | Poll with `successFlag` parsing (0=generating, 1=success, 2/3=failed) |
| `mj_upscale()` | `POST /mj/generateUpscale` | Upscale one of 4 grid images (imageIndex 0-3) |
| `mj_vary()` | `POST /mj/generateVary` | Create variations of one image (imageIndex 1-4) |

**`_build_mj_payload()`** (added in prior session) builds the flat MJ payload:
- `taskType`: `mj_txt2img`, `mj_img2img`, or `mj_video`
- `prompt`, `speed`, `fileUrls`, `aspectRatio`, `version`
- Optional sliders: `stylization` (0-1000), `weirdness` (0-3000), `variety` (0-100)

**3 MJ model entries in `KIE_MODELS` registry:**
- `midjourney-t2i` — Text-to-image, 4 images per request
- `midjourney-i2i` — Image-to-image editing, 4 images per request
- `midjourney-video` — Image-to-video, 5-second clips

---

### `execution/server.py`

**New imports:**
```python
mj_create_task as kie_mj_create_task,
mj_poll_task as kie_mj_poll_task,
mj_upscale as kie_mj_upscale,
mj_vary as kie_mj_vary
```

**Modified route — `/api/kie/generate`:**
- Now detects `midjourney-*` model keys and routes to `kie_mj_create_task()` instead of standard `kie_create_task()`

**3 new routes:**

| Route | Method | Rate Limit | Purpose |
|-------|--------|------------|---------|
| `/api/kie/mj/poll/<task_id>` | GET | 600/hr | Poll MJ task; downloads result and persists to Firebase Storage on completion |
| `/api/kie/mj/upscale` | POST | 120/hr | Upscale one of 4 grid images (`{taskId, imageIndex}`) |
| `/api/kie/mj/vary` | POST | 120/hr | Create variations of one image (`{taskId, imageIndex}`) |

The MJ poll route reuses the same download-and-persist pattern as the standard Kie poll (download from expiring Kie URL, upload to Firebase Storage for permanent access).

---

### `ui/index.html`

**Frontend changes (added in prior session, updated here):**

- **Midjourney sub-tab** — 3rd tab alongside Images/Videos with mode selector (T2I / I2I / Video)
- **Parameter controls** — Speed (Relaxed/Fast/Turbo), Version (7/6.1/6/niji7/etc), Aspect Ratio, Stylization/Weirdness/Variety sliders
- **`mjStartPolling()`** — Updated to call `/api/kie/mj/poll/` (MJ-specific endpoint)
- **`addToMjGallery()`** — Now accepts `taskId` and `imageIndex`, renders **Upscale** and **Vary** buttons on each generated image
- **`mjUpscaleImage()`** — New function: calls `/api/kie/mj/upscale`, polls result
- **`mjVaryImage()`** — New function: calls `/api/kie/mj/vary`, polls result
- **`restoreKieGallery()`** — Updated to pass taskId when restoring MJ items

### `ui/style.css`

(Added in prior session, no changes in this session)

- `.mj-mode-bar`, `.mj-mode-btn` — Mode selector styling
- `.mj-sliders`, `.mj-slider-group`, `.mj-slider` — Range slider styles
- Responsive breakpoints for MJ components

---

## Models Supported

### Midjourney Image (2 models)

| Model | Modes | Versions | Speed Tiers | Pricing |
|-------|-------|----------|-------------|---------|
| Midjourney | T2I | 7, 6.1, 6, 5.2, 5.1, niji7, niji6 | Relaxed $0.015, Fast $0.04, Turbo $0.08 | 4 images/request |
| Midjourney (Edit) | I2I | Same as above | Same as above | 4 images/request |

### Midjourney Video (1 model)

| Model | Modes | Duration | Pricing |
|-------|-------|----------|---------|
| Midjourney Video | I2V | ~5s | Relaxed $0.10, Fast $0.20, Turbo $0.35 |

### Post-Generation Actions

| Action | Endpoint | Input |
|--------|----------|-------|
| Upscale | `/mj/generateUpscale` | taskId + imageIndex (0-3) |
| Vary | `/mj/generateVary` | taskId + imageIndex (1-4) |

---

## Architecture Decisions

1. **Separate API functions** — `mj_create_task()`/`mj_poll_task()` are independent from standard `create_task()`/`poll_task()` because MJ uses different endpoints, payload format, and response format.
2. **Smart routing in server** — The existing `/api/kie/generate` route detects `midjourney-*` models and delegates to the correct function, so the frontend doesn't need separate generate endpoints.
3. **Dedicated poll route** — `/api/kie/mj/poll/` is separate because MJ response parsing (`successFlag` + `resultInfoJson.resultUrls[].resultUrl`) is fundamentally different from standard (`state` + `resultJson`).
4. **Same persistence pattern** — MJ results use the same download-and-persist to Firebase Storage pattern as other Kie models (Kie URLs expire in 24h).
5. **No new dependencies** — All MJ functions use the existing `_kie_request()` HTTP helper and Python stdlib.

---

## Testing

- **Python syntax:** Both `kie_client.py` and `server.py` pass AST parse
- **Module import:** All 4 MJ functions importable, all 3 MJ models registered
- **Test suite:** 7/7 existing tests pass (1 pre-existing Playwright fixture error, unrelated)
- **JS functions:** All MJ functions confirmed present in HTML (`mjGenerate`, `mjStartPolling`, `addToMjGallery`, `mjUpscaleImage`, `mjVaryImage`)
