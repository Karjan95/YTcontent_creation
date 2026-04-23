# Image History & Download Fixes — 2026-02-25

## Summary
Added per-scene image generation history so users can browse, preview, reuse, and download any previously generated image. Fixed the "Download All" feature which crashed with a JSON parse error when using Firebase Storage.

---

## 1. Download All Images Fix

### Problem
Clicking "Download All Images" threw:
```
Download failed: Failed to execute 'json' on 'Response': Unexpected end of JSON input
```

### Root Cause
`downloadAllAssets()` called `/api/visuals/download-all`, a server endpoint that zipped local files from disk. With Firebase Storage, those local files don't exist — the endpoint returned a non-JSON error, and the error handler called `res.json()` on it, causing the crash.

### Fix
Rewrote `downloadAllAssets()` to iterate `visualsScenes` client-side and download each image/video URL individually via the existing `/api/download-asset` proxy endpoint (which handles Firebase Storage URLs with CORS).

**File modified:** `ui/index.html`

---

## 2. Per-Scene Image Generation History (New Feature)

### Context
When a user regenerates an image for a scene, the previous image disappears from the UI (only the latest is shown). However, ALL previous versions remain in Firebase Storage — each regeneration creates a new file with a different timestamp: `scene_{id}_{timestamp}.png`. This feature surfaces that history inside each scene card.

### Files Modified
- `execution/server.py`
- `ui/index.html`
- `ui/style.css`

---

### A. Backend — New Endpoint (`server.py`)

**New route:** `POST /api/visuals/scene-image-history`

- Accepts `{ scene_ids: ["1", "2", ...], project_id: "..." }`
- Lists all blobs in Firebase Storage with prefix `images/{project_id}/scene_`
- For each scene ID, returns ALL matching images (not just latest), sorted newest-first
- Extracts unix timestamp from filename pattern `scene_{safe_id}_{timestamp}.{ext}`
- Returns `{ history: { "1": [{url, timestamp, filename}, ...], "2": [...] } }`

No changes to existing endpoints. No Firestore schema changes.

---

### B. Frontend — History Strip (`index.html`)

**Data model:** Added `imageHistory: []` property to each scene object in `initVisualsFromProductionTable()`.

**Scene card template:** Added `<div class="scene-image-history">` container after the image result area.

**New functions:**

| Function | Purpose |
|---|---|
| `renderImageHistoryStrip(idx)` | Renders collapsible strip with thumbnails below the active image. Hidden if < 2 versions exist. Filters out the current active image to avoid duplication. |
| `toggleHistoryStrip(idx)` | Show/hide the strip body |
| `fetchImageHistory()` | POSTs all scene IDs to the new endpoint, populates `s.imageHistory` for each scene |
| `fetchImageHistoryForScene(idx)` | Same but for a single scene — called after each successful image generation |
| `openImageLightbox(url, sceneIdx, filename)` | Opens modal with large image preview |
| `closeImageLightbox(event)` | Closes modal on overlay click or X button |
| `useHistoryImage()` | Swaps active `s.imageUrl` to the selected history image, triggers autosave |
| `downloadLightboxImage()` | Downloads the previewed image via existing `downloadFirebaseFile()` |

**History fetched automatically:**
- After `initVisualsFromProductionTable()` renders scenes
- After loading a saved project
- After batch image generation completes
- After each single image generation/regeneration succeeds

---

### C. Lightbox Modal (`index.html`)

Full-screen overlay modal with:
- Large image preview
- "Use This Image" button — swaps the active scene image to the selected history version
- "Download" button — downloads the individual image
- Close on X button or clicking outside the card

---

### D. Download All Dialog (`index.html`)

**Replaced `downloadAllAssets()`** with a version that:
1. Checks if any scene has image history (more than 1 version)
2. If yes, shows a dialog with 3 options:
   - **Active Images Only** — downloads only the current `s.imageUrl` per scene (original behavior)
   - **All Generated Images** — downloads every image from `s.imageHistory` per scene
   - **Cancel**
3. If no history exists, downloads active images directly (no dialog)
4. Videos are always included in both modes

**New function:** `showDownloadModeDialog()` — returns a Promise resolving to `'active'`, `'all'`, or `null` (cancel).

---

### E. Styles (`style.css`)

New CSS classes:

| Class | Purpose |
|---|---|
| `.scene-image-history` | Container for the history strip |
| `.history-strip-header` | Collapsible toggle header ("Previous versions (N)") |
| `.history-strip-body` | Horizontal scrolling thumbnail container |
| `.history-thumb-wrapper` | Individual thumbnail card |
| `.history-thumb` | Thumbnail image |
| `.history-thumb-meta` | Date label + download icon overlay |
| `.lightbox-overlay` | Full-screen modal backdrop |
| `.lightbox-card` | Modal content card |
| `.lightbox-body` | Image container inside modal |
| `.lightbox-actions` | Button row (Use This Image / Download) |

---

## Data Flow

```
Scene card → Regenerate → new image saved to Firebase Storage
                              ↓
fetchImageHistoryForScene(idx)
  → POST /api/visuals/scene-image-history { scene_ids: [idx] }
  → server lists all blobs matching scene_{id}_*
  → returns sorted list (newest first)
                              ↓
s.imageHistory = entries
renderImageHistoryStrip(idx)
  → shows "Previous versions (N)" if N ≥ 1
  → thumbnails with date labels
                              ↓
Click thumbnail → openImageLightbox()
  → "Use This Image" → swaps s.imageUrl, triggers autosave
  → "Download" → downloads via proxy endpoint
```

---

## User-Facing Controls

| Control | Location | Behavior |
|---|---|---|
| **Previous versions (N)** | Below each scene image | Collapsible strip showing all past generations |
| **Thumbnail click** | History strip | Opens lightbox with large preview |
| **Use This Image** | Lightbox modal | Swaps active image to selected version |
| **Download** | Lightbox modal | Downloads individual image |
| **Download All** | Top of Visuals tab | Asks "Active Only" / "All Generated" if history exists |
