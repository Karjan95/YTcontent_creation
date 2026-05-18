# Studio UX & Stability Update (May 10, 2026)

This changelog outlines the series of user experience fixes, stability improvements, and architecture enhancements made to the Studio Tab workflow, specifically aimed at improving asset generation, generation management, and reference payload handling.

## 1. Resolved HTTP 413 "Payload Too Large" Errors
**Problem:** Generating assets with models like Nano Banana 2 while using multiple character reference images caused server-side rejection (`HTTP 413 Payload Too Large`).
**Solution:** 
- The client-side generation dispatcher (`studioGenerate` in `ui/index.html`) was aggressively including base64 encoded `dataUrl` strings within the payload.
- Refactored the payload mapping logic to strip `dataUrl` entirely before sending the request to `/api/studio/generate`. The system now correctly relies exclusively on the public `url` pointer stored in Firebase, significantly reducing payload sizes and avoiding Nginx size limits.

## 2. Concurrent Generation & Progress Indicators
**Problem:** The Studio tab could only handle one generation request at a time. The entire form was locked (`studioState.generating = true`) during processing, and there was no visual indication of progress beyond a small text note.
**Solution:**
- **State Refactor:** Replaced the boolean `generating` state with an array-based `activeTasks` tracking map inside `studioState`.
- **Unlocked UI:** Removed the generation button freezing logic, allowing users to rapidly click and queue multiple parallel generation requests.
- **Progress Cards:** Updated `studioRenderGallery()` to iterate over `activeTasks` and render dedicated, animated progress tiles at the top of the gallery for each active generation. The cards track elapsed time and display the target model.

## 3. Persistent Character References
**Problem:** Successfully generating a video or image cleared out the text prompt and all uploaded reference images, forcing users to re-upload character references for iterative shots.
**Solution:** 
- Updated `studioClearComposerInputs()` to preserve the `studioState.refs` array. 
- Generating an asset now clears the text prompt but leaves character references active in the Composer so users can easily iterate on shots.

## 4. Expired Asset Links Fix (Broken Images)
**Problem:** Images generated and stored via signed Google Cloud Storage URLs have a 4-hour expiration window. Returning to a project days later resulted in broken `<img>` tags in the gallery.
**Solution:**
- Updated the backend `GET /api/projects/<id>/assets` endpoint and serialization logic in `server.py` (`_serialize_asset`).
- The backend now inspects URLs matching `storage.googleapis.com`, parses the bucket and blob path, verifies if it's expired, and dynamically regenerates a fresh signed URL before serving the asset list to the client.

## 5. Gallery Index Misalignment Fix
**Problem:** When a user applied a filter (e.g., viewing only images) or used the search bar, clicking on an asset in the gallery would mistakenly open a different asset in the modal viewer.
**Solution:**
- The iteration index of the *filtered* array was mistakenly being passed to the viewer modal, which expected an index mapping to the *unfiltered* global array.
- Updated `studioRenderGallery` to pass down the `__realIdx` property of the asset instead, guaranteeing that clicks always map to the correct underlying state object.

## Deployment
All updates have been successfully deployed and verified on the Staging environment (`content-creation-app-staging`).
