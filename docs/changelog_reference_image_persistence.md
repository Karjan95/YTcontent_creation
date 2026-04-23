# Changelog: Reference Image Persistence & Refresh System

**Date:** 2026-03-01
**Scope:** `execution/server.py`, `execution/gemini_client.py`, `ui/index.html`

---

## Problem

Firebase Storage signed URLs expire after 4 hours. When projects are saved, only URLs are stored (base64 image data is stripped to stay under Firestore's 1MB document limit). On reload:

- Character reference images become inaccessible (expired URLs)
- Style reference images disappear entirely (`STYLE IMAGES: 0` in debug)
- Style Lock / performance modes have no effect (no style images to apply them to)
- Character thumbnails in scene selectors break (show blank)
- Image generation history strip disappears
- Newly uploaded characters/styles appear to not work after any page reload

---

## Solution: Blob Path Storage + On-Load Refresh

Instead of relying on expiring signed URLs, we now store the **Firebase Storage blob path** (e.g., `references/projectId/character/file.png`) which never expires. On project load, a new refresh system fetches fresh signed URLs and base64 data from these paths.

---

## Changes

### 1. Server (`execution/server.py`)

#### `upload_to_storage()` — new `return_path` parameter
- Added optional `return_path=True` parameter
- When enabled, returns `(url, blob_path)` tuple instead of just `url`
- All existing callers unaffected (default `return_path=False`)

#### `/api/upload-reference-image` — now returns blob path
- Response changed from `{ success, url }` to `{ success, url, path }`
- `path` is the Firebase Storage blob path (e.g., `references/proj123/character/char_1709292828_bobi.png`)

#### New endpoint: `POST /api/refresh-reference-images`
- **Accepts:** `{ paths: ["references/proj/character/file.png", ...] }`
- **Returns:** `{ images: { "path": { url, data } } }` where `url` is a fresh 4-hour signed URL and `data` is the full base64 data URI
- Limit: 20 images per request
- Only allows paths starting with `references/` (security)
- Logs refresh counts for monitoring

#### `resolve_image_input()` — graceful failure
- URL download failures now return `None` instead of crashing the entire request
- Logs warning: `[Resolve] Failed to fetch image from URL (may be expired)`

#### Null-safety in generation endpoints
- Both single (`/api/visuals/generate-image`) and batch (`/api/visuals/generate-batch-images`) endpoints now filter out `None` values after resolving images
- Prevents crashes when some reference images fail to resolve

### 2. Gemini Client (`execution/gemini_client.py`)

#### Null-safe image decoding in `generate_scene_image()`
- All three image decode loops (structured characters, legacy characters, style references) now:
  - Skip `None` / falsy image data
  - Wrap `_decode_ref_image()` in try/catch
  - Log failures instead of crashing the entire generation

### 3. Frontend (`ui/index.html`)

#### `uploadReferenceImage()` — returns object instead of string
- **Before:** returned `url` (string or null)
- **After:** returns `{ url, path }` object
- All three callers updated:
  - Character image upload (`handleCharImageUpload`)
  - Visuals style image upload (`handleVisualsStyleUpload`)
  - Phase 3 style image upload (`handleStyleImageUpload`)

#### New function: `refreshReferenceImages()`
- Called automatically on every project load
- Collects all reference images missing base64 data (style images, character images, Phase 3 style images)
- Extracts blob paths from image objects (or from signed URLs for backward compatibility)
- Calls `POST /api/refresh-reference-images` with all paths
- Restores `data` (base64) and `url` (fresh signed URL) on each image object
- Re-renders all UI components that depend on image data

#### New function: `extractBlobPathFromUrl(url)`
- Extracts blob path from a Firebase Storage signed URL
- Provides backward compatibility for projects saved before this change (which only have URLs, no paths)

#### New function: `getImagePath(img)`
- Returns `img.path` if available, otherwise extracts from `img.url`

#### Project save — now includes `path`
- `visuals_config.styleImages` entries now save `{ name, url, path }`
- `visuals_characters[].images` entries now save `{ name, url, path }`
- `style_reference_images` entries now save `{ name, url, path }`

#### Project load — updated filters
- Style images filter now keeps images with `path` even if `url` is expired: `img.data || img.url || img.path`
- Phase 3 style reference images now restore `path` field

#### Character thumbnail fix
- Scene character selector thumbnail changed from `ch.images[0]?.data || ''` to `ch.images[0]?.data || ch.images[0]?.url || ''`
- Thumbnails now display correctly after project reload

---

## Data Flow (After Changes)

```
── UPLOAD ──
User uploads image
  → FileReader reads as base64 (data)
  → uploadReferenceImage() sends to server
  → Server stores in Firebase Storage
  → Returns { url: signedUrl, path: blobPath }
  → Stored in memory: { name, data, url, path }

── SAVE ──
triggerAutosave() / saveProject()
  → Strips base64 data (Firestore 1MB limit)
  → Saves: { name, url, path }

── LOAD ──
loadProject()
  → Restores: { name, url: maybeExpired, path, data: null }
  → refreshReferenceImages() fires
    → Collects all images missing data
    → POST /api/refresh-reference-images with paths
    → Server fetches from Firebase Storage
    → Returns fresh { url, data } for each path
    → Updates image objects in memory
    → Re-renders UI (thumbnails, previews, scene cards)

── GENERATE ──
buildImageRequestBody()
  → Uses img.data (base64, always available after refresh)
  → Falls back to img.url if data somehow missing
  → Server receives base64 or URL
  → resolve_image_input() converts URLs to base64
  → Gemini API receives binary image parts
```

---

## Backward Compatibility

- Projects saved before this change have `{ name, url }` (no `path`)
- `extractBlobPathFromUrl()` can derive the blob path from signed URLs
- `getImagePath()` tries `img.path` first, then falls back to URL extraction
- Old projects will auto-migrate: on first load after this change, paths are extracted and stored; on next save, paths are persisted

---

## Files Modified

| File | Lines Changed | Key Changes |
|---|---|---|
| `execution/server.py` | ~80 | `upload_to_storage` return_path, refresh endpoint, resolve_image_input safety, null filtering |
| `execution/gemini_client.py` | ~30 | Null-safe image decoding with try/catch in 3 locations |
| `ui/index.html` | ~90 | refreshReferenceImages system, path storage, thumbnail fix, save/load updates |
