# Changelog — Project naming, sidebar live-update, download-all streaming, video sync

**Date:** 2026-05-29
**Files:** `execution/server.py`, `ui/index.html`

## Problems (4 user-reported bugs)

1. **Project name changed itself.** After a user named a new project and then
   generated/pasted a script, the next autosave silently renamed the project to
   the script's title. The list also appeared to require a page refresh to show
   the correct/updated name.
2. **New/updated projects needed a refresh to appear in the sidebar.**
3. **"Download All" (Visuals tab) returned a 500** after showing "zipping…",
   especially on video-heavy projects.
4. **Kie videos were never recovered by "Sync lost images".** Sync finished but
   videos stayed missing.

## Root causes

| Bug | Cause |
|-----|-------|
| 1 | `gatherProjectState()` derived the title and then **overwrote it with `currentNarration.title`** (`ui/index.html` ~12745). Any generated script title clobbered the user's chosen name on the next autosave. |
| 2 | The sidebar cache (`_lastSavedProjects`) was only re-rendered on full `fetchProjects()`. Saves patched the active row's DOM directly but didn't update the cache, so any re-render reverted it; a freshly created project could also be dropped by the background `fetchProjects()` if Firestore hadn't indexed it yet (read-after-write lag). |
| 3 | `/api/visuals/download-all` built the **entire zip in an in-memory `BytesIO`** (all images + videos + audio) on a 2 GB Cloud Run instance → memory exhaustion → 500. |
| 4 | `syncOrphanedImages()` only targeted scenes missing an **image** and the endpoint only scanned `images/`. Kie videos (which finish re-hosting after the scene was last saved) were never looked for. |

## Fixes

### Project name is now authoritative (Bug 1)
- New global `currentProjectTitle` holds the **user-chosen** name. Set on
  **create** (`confirmNewProject`), **rename** (`editProjectTitle`), and
  **load** (`loadProject`).
- `gatherProjectState()` now uses `currentProjectTitle` as the title and
  **no longer overwrites it** with the narration/script title. Fallback chain
  (`currentProjectTitle || selectedTitle || topic || 'Untitled Project'`) only
  applies when no name was ever set.
- `clearAppForNewProject()` intentionally does **not** reset
  `currentProjectTitle` (create sets it before clearing).

### Sidebar live-update (Bug 2)
- New `updateSidebarEntry(projectId, {title, date})` helper updates **both** the
  in-memory `_lastSavedProjects` cache and the DOM, creating the entry if
  missing. Wired into both save paths (`doSaveProject` + debounced autosave).
- `fetchProjects()` now **preserves the currently-open project** if the server
  query hasn't returned it yet (read-after-write lag), so a just-created project
  no longer vanishes until refresh.

### Download-all streaming (Bug 3)
- `/api/visuals/download-all` rewritten to **stream** the zip. Each blob is
  copied into the archive in **1 MB chunks** via `zf.open(arcname,'w')` +
  `blob.open('rb')`, and the bytes are flushed to the HTTP response as produced.
- Uses a non-seekable sink (`_ChunkSink` exposes `write`/`tell`/`flush` but no
  `seek`), so `zipfile` emits streaming-safe **data descriptors** instead of
  seeking back to patch headers. Peak memory is now ~one chunk regardless of
  project size. Verified locally that the streamed archive unzips cleanly
  (`testzip` clean, byte-for-byte match) and `_seekable` is `False`.
- Returns a Flask `Response(generate(), …)` with
  `Content-Disposition: attachment` and `X-Accel-Buffering: no`.

### Sync recovers Kie videos too (Bug 4)
- `/api/visuals/sync-storage-images` now scans **both** `images/{pid}/scene_*`
  and `videos/{pid}/scene_*` (shared `_latest_per_scene()` helper) and returns
  `{ matches, video_matches }`.
- `syncOrphanedImages()` now targets scenes missing an image **or** a video,
  applies both result maps (only filling empty slots), and reports counts
  (e.g. "Recovered 2 images and 3 videos").

## Verification
- `python3 -m py_compile execution/server.py` — OK.
- `pytest tests/test_api_workflows.py` — 4 passed.
- Streaming-zip pattern exercised standalone with mixed image/video/audio
  payloads → valid archive.

## Notes / follow-ups
- The Download-All fix assumes the 500 was memory exhaustion (consistent with
  the code and the "video-heavy projects" symptom). If a live staging test still
  500s, pull the Cloud Run error log to rule out a signing/permission cause.
- Streamed responses send no `Content-Length` (chunked), so browsers won't show
  a download progress percentage — acceptable trade-off for memory safety.
