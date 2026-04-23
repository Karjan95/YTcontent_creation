# Fix: Visuals Tab Persistence on Page Refresh — 2026-03-02

## Summary
Resolved critical UX issue where refreshing the page after generating images on the Visuals tab caused all work to disappear. Users previously had to manually click "Load Latest Production Table" and regenerate all images despite them existing in Firebase Storage. Also hardened the production table loading endpoint to prevent cross-project data contamination.

---

## 1. Save-on-Unload — Flush Pending Auto-Save Before Page Close

### Problem
The auto-save system uses a 2-second debounce. If the user refreshed within that window, the latest state (including newly generated image URLs) was never persisted to Firestore.

### Root Cause
The `beforeunload` handler only warned about active background operations — it did not flush the pending debounced auto-save.

### Fix
Modified the `beforeunload` handler to detect any pending save timeout and immediately flush the full project state using `fetch` with `keepalive: true` (which completes even during page unload).

**File modified:** `ui/index.html` (~line 1562)

---

## 2. Auto-Sync Condition — Always Recover Missing Images

### Problem
On page restore, the auto-sync with Firebase Storage only ran if *some* scenes had images and *some* didn't. If all image URLs were lost (e.g., due to save timing), the condition `visualsScenes.some(s => s.imageUrl)` was `false`, so recovery never triggered — even though every image existed in Firebase Storage.

### Fix
Changed the auto-sync condition to trigger whenever *any* scenes are missing images, as long as a `currentProjectId` exists. Removed the requirement that at least one scene must already have an image URL.

**Before:**
```javascript
if (scenesWithoutImages.length > 0 && visualsScenes.some(s => s.imageUrl)) {
```

**After:**
```javascript
if (scenesWithoutImages.length > 0 && currentProjectId) {
```

**File modified:** `ui/index.html` (~line 6203)

---

## 3. Immediate Save After Image/Video Generation

### Problem
After generating an image or video, the app called `triggerAutosave()` which used a 2-second debounce. If the user refreshed or navigated away before the debounce fired, the newly generated URL was lost.

### Fix
Changed `triggerAutosave()` to `doSaveProject()` (immediate, non-debounced save) after both image and video generation completes. Each generated URL is now persisted to Firestore the moment it's received.

**File modified:** `ui/index.html` (~lines 4655, 5232)

---

## 4. Preserve Existing Images on "Load Latest Production Table"

### Problem
When clicking "Load Latest Production Table", the `initVisualsFromProductionTable()` function rebuilt the entire `visualsScenes` array from scratch, setting every `imageUrl` and `videoUrl` to `null`. This wiped all previously generated images even if they were already loaded in the UI.

### Fix
Added a lookup map of existing scene data (keyed by `sceneId`) before rebuilding. When constructing new scene objects, the function now preserves `imageUrl`, `videoUrl`, `imageModel`, `veoModel`, `selectedCharacters`, and `imageHistory` from any matching existing scene.

**File modified:** `ui/index.html` (~line 4087)

---

## 5. Project ID Guard on `loadLatestProductionTable()`

### Problem
If `currentProjectId` was null/undefined, the fallback API call to `/api/latest-production-table` would search the flat `.tmp/` root directory and could return a production table from a completely different project.

### Fix
Added an early guard that requires `currentProjectId` before proceeding. Also changed the fallback API call to always include the `project_id` parameter.

**File modified:** `ui/index.html` (~line 3994)

---

## 6. Hardened `/api/latest-production-table` Endpoint

### Problem
The `.tmp/` directory stored all production table files flat (no project subdirectories) despite the code having project-scoping logic. The endpoint would search the flat root when no `project_id` was provided, returning whichever project's file was most recently modified — a cross-project contamination risk.

### Fix
- Now **requires** `project_id` parameter (returns 400 if missing)
- **Priority 1:** Checks Firestore project document first (authoritative source)
- **Priority 2:** Falls back to `.tmp/{project_id}/` subdirectory only (never the flat root)

**File modified:** `execution/server.py` (~line 1458)

---

## Files Modified
| File | Changes |
|------|---------|
| `ui/index.html` | `beforeunload` flush, auto-sync condition, immediate save after gen, image preservation in `initVisualsFromProductionTable`, project_id guard |
| `execution/server.py` | `/api/latest-production-table` — require project_id, Firestore-first lookup, scoped `.tmp/` fallback |

## Verification
- [x] No conflicts with existing bugfixes (SSRF validation, scene history double-prefix fix)
- [ ] Generate images on Visuals tab, refresh page — visuals should auto-restore with all images
- [ ] Create production tables in two different projects — verify no cross-project interference
- [ ] Generate images, refresh immediately (< 1 second) — images recovered via auto-sync from Firebase Storage
- [ ] Click "Load Latest Production Table" after images exist — previously generated images preserved

---
**Date:** March 2, 2026
**Developer:** Antigravity (AI Assistant)
