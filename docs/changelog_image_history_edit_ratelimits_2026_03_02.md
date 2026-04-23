# Changelog: Image History Fix, Image Editor, Rate Limits — 2026-03-02

## Summary

Three major changes in this session:
1. **Fixed image history / Firebase Storage signed URLs on Cloud Run** — images were uploading but signed URLs failed silently
2. **Added iterative image editing in lightbox** — users can click any generated image, type an edit prompt, and Gemini modifies the image in-place
3. **Fixed rate limiting** — increased limits and added auto-retry so batch generation of 300+ images works reliably

---

## 1. Firebase Storage Signed URL Fix

### Problem
On Cloud Run (staging), `firebase-service-account.json` is excluded from Docker builds (correctly, for security via `.dockerignore`). The server uses Application Default Credentials (ADC), which works for **uploading** blobs but **fails for generating v4 signed URLs** (requires a private key for signing).

The `upload_to_storage()` function had both upload and signed URL generation in a single try-catch block. When the signed URL failed, the entire function returned `None` — even though the upload had already succeeded. This caused:
- UI fell back to local `/generated/` URLs (ephemeral on Cloud Run)
- Image history endpoint returned errors (couldn't generate signed URLs for blobs)
- Users couldn't see "Previous versions" when regenerating images

### Fix

**Files changed:** `execution/server.py`

1. **Added IAM signing credentials** (module-level, after Firebase init ~line 73):
   - Detects Cloud Run environment (no service account JSON present)
   - Caches `google.auth.default()` credentials for IAM-based URL signing
   - No new dependencies — `google-auth` is already a transitive dep of `firebase-admin`

2. **New `_generate_signed_url(blob)` helper**:
   - Tries direct signing first (works locally with service account key)
   - Falls back to IAM-based signing on Cloud Run using `service_account_email` + `access_token`
   - Returns `None` on failure (callers handle gracefully)

3. **Fixed `upload_to_storage()`**: Split into two separate try blocks — upload and URL generation. Upload success is never lost due to URL generation failure.

4. **Updated all 4 `generate_signed_url` call sites** to use the new helper:
   - `upload_to_storage()` (line ~140)
   - `refresh_reference_images()` endpoint
   - `visuals_sync_storage_images()` endpoint
   - `visuals_scene_image_history()` endpoint

5. **Added startup diagnostic logging** — logs which signing method is active (service account JSON vs IAM vs none).

6. **Fixed cross-project image leak**: The history endpoint was always loading legacy root-level blobs (`images/scene_*`) which contained images from ALL projects. Now it only searches within `images/{project_id}/` when a project ID is provided.

### IAM Role Requirement
The Cloud Run service account needs `roles/iam.serviceAccountTokenCreator` for IAM signing. Grant once:
```bash
PROJECT_NUMBER=$(gcloud projects describe gen-lang-client-0854991687 --format="value(projectNumber)")
SA_EMAIL="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
    --member="serviceAccount:${SA_EMAIL}" --role="roles/iam.serviceAccountTokenCreator"
```
This is documented as comments in both `deploy.sh` and `deploy_staging.sh`.

---

## 2. Iterative Image Editing in Lightbox

### Feature
Users can click any generated scene image to open it in a lightbox editor. They type an edit prompt (e.g. "make the sky more dramatic") and Gemini modifies the image using image-to-image editing. Users can edit repeatedly without closing the lightbox.

### How it works
1. User clicks a generated scene image
2. Lightbox opens with the image + edit controls (prompt textarea, model selector, "Edit Image" button)
3. User types edit instruction and clicks "Edit Image"
4. The current image is sent to Gemini as input along with the edit prompt
5. Gemini returns a modified image
6. The new image replaces the preview in the lightbox (ready for another edit)
7. The previous version is auto-saved to Firebase Storage (appears in "Previous versions")
8. User closes lightbox when satisfied — final version is the active scene image

### Files changed

**`execution/gemini_client.py`** — New `edit_scene_image()` function:
- Sends source image + edit instructions to Gemini's multipart API
- Uses same response handling and file saving pattern as `generate_scene_image()`
- Parts: system instruction ("you are an image editor") + source image bytes + edit prompt
- Reuses `_decode_ref_image()`, `_retry_api_call()`, same `GenerateContentConfig`

**`execution/server.py`** — New `POST /api/visuals/edit-image` endpoint:
- Accepts: `{ scene_id, source_image, edit_prompt, model, aspect_ratio, project_id }`
- `source_image` can be a signed URL or base64 data URI
- Uses `resolve_image_input()` to convert URLs to base64
- Calls `edit_scene_image()`, uploads result to Firebase Storage
- Rate limit: 600/hour (same as generate)
- Added `edit_scene_image` to imports from `gemini_client`

**`ui/index.html`** — Lightbox extended with edit mode:
- Main scene images now have `onclick="openImageEditor(idx)"` (both in initial render and `updateSceneCard()`)
- Lightbox HTML extended with edit panel: textarea, model selector dropdown, "Edit Image" button, error display
- `lightboxState` extended with `editMode` flag
- New `openImageEditor(idx)` — opens lightbox in edit mode (shows edit controls, hides "Use This Image")
- New `submitImageEdit()` — sends edit request, updates lightbox image on success, clears prompt for next edit
- `openImageLightbox()` still works for history thumbnails (read-only mode, no edit panel)

**`ui/style.css`** — New styles:
- `.lightbox-edit-panel`, `.lightbox-edit-prompt`, `.lightbox-edit-row`, `.lightbox-edit-error`
- Lightbox card widened from `max-width: 800px` to `900px`

---

## 3. Rate Limit Fixes

### Problem
Image generation endpoints had a 30/hour rate limit. Batch generation sends individual requests per scene (with 5 concurrent workers). A project with 10+ scenes would hit the limit during a single batch. After hitting the limit, users were stuck for an hour — even refreshing didn't help.

### Fix

**`execution/server.py`** — Increased rate limits:

| Endpoint | Before | After |
|----------|--------|-------|
| `/api/generate-image` | 30/hour | 600/hour |
| `/api/visuals/generate-image` | 30/hour | 600/hour |
| `/api/visuals/generate-batch-images` | 30/hour | 600/hour |
| `/api/visuals/start-animation` | 10/hour | 60/hour |
| `/api/visuals/start-batch-animation` | 10/hour | 60/hour |

Rationale: Users are authenticated and use their own Gemini API keys. The Gemini API enforces its own rate limits. Our server-side limit just needs to prevent abuse, not throttle normal usage.

**`ui/index.html`** — Auto-retry on 429 in `authFetch()`:
- On 429, automatically retries up to 3 times with backoff
- Waits the `Retry-After` header duration (capped at 30s) between attempts
- Only throws after all retries exhausted
- Benefits all endpoints (batch generation, regeneration, animation, editing)

**`ui/index.html`** — Increased batch concurrency:
- Changed `CONCURRENCY` from 3 to 5 parallel workers in `generateAllImages()`

---

## 4. UI Polish: Image History Strip

### Problem
The "Previous versions" thumbnail strip overflowed its CSS grid column, bleeding into the animation section.

### Fix

**`ui/style.css`**:
- Added `min-width: 0` to `.scene-card-body > *` — prevents CSS grid children from overflowing their column
- Added `min-width: 0` to `.scene-image-history`
- Increased thumbnail size from 100x60px to 130x74px for better visibility
- Added hover glow effect (`box-shadow`) on thumbnails

---

## File Change Summary

| File | Changes |
|------|---------|
| `execution/server.py` | IAM signing, `_generate_signed_url()` helper, fixed `upload_to_storage()`, new `/api/visuals/edit-image` endpoint, increased rate limits, fixed cross-project history leak |
| `execution/gemini_client.py` | New `edit_scene_image()` function |
| `ui/index.html` | Lightbox edit mode (HTML + JS), clickable scene images, 429 auto-retry, increased batch concurrency |
| `ui/style.css` | Lightbox edit panel styles, history strip overflow fix, larger thumbnails |
| `deploy.sh` | IAM role documentation comment |
| `deploy_staging.sh` | IAM role documentation comment |
