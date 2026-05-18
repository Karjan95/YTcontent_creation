# Changelog — Retry-Beats Fix, Task Persistence, Per-Project Production Isolation

**Date:** 2026-05-18 (evening session; follows `changelog_production_resumability_retry_salvage_2026_05_18.md`)
**Branch:** main
**Staging URL:** https://content-creation-app-staging-qj4rflrraa-uc.a.run.app

## Why

Two user reports after the earlier 2026-05-18 deploy:

1. **"Retry missing scenes" failing instantly** — clicking "🔁 Retry missing scenes" returned `"No existing production table to extend"` 400 error immediately. The "Regenerate full table" fallback also failed. Root cause: the streaming production worker saved its final result to the Firestore project doc, but the poll endpoint (`/api/production-task/{task_id}`) couldn't always hydrate `final_table` because the project doc wasn't accessible when `project_id` was missing or the doc didn't exist yet. The retry-beats endpoint also didn't attempt a server-side fallback when the client sent an empty `existing_table`.

2. **"Load Latest Production Table" loading wrong project** — when generating two production tables in parallel (one per project), clicking the button in the Visuals tab would re-import the same table that was already displayed, or worse, import data from the *other* project. The function trusted `currentProductionData` in memory — a global variable that could be stale from a background operation that completed for a different project.

3. **Download JSON button not working** — the "Download JSON" button under the production table relied on `final_table` from the poll response, which was `null` for the same reason as bug #1.

## Changes

### 1. Task result persistence to `.tmp/` (Bug #1 + #3 fix)

The streaming production worker and retry-beats worker now persist their final production table to a local `.tmp/` file (`task_prod_{task_id}.json`) immediately on completion, alongside the existing Firestore persistence. The poll endpoint reads from this file as the primary source when hydrating `final_table`, with the Firestore project doc as fallback.

**Why a temp file?** The Firestore project doc requires a valid `project_id` to look up, but some edge cases (e.g. the project not yet having been saved, or the `project_id` not being threaded into the poll path) left `final_table` as `null`. The temp file is keyed by `task_id` which is always available.

- `execution/server.py` (`_worker`, ~line 3525) — after persisting to Firestore, also writes `json.dumps(production_table)` to `TMP_DIR/task_prod_{task_id}.json`.
- `execution/server.py` (`_retry_worker`, ~line 3834) — same pattern for the retry-beats merged table.
- `execution/server.py` (`production_task_poll_route`, ~line 3625) — when `status == 'complete'` and `final_table` is not in the task doc, attempts to read from `TMP_DIR/task_prod_{task_id}.json` first, then falls back to the project doc's `production_data.production_table`.

**⚠️ Cloud Run caveat:** The `.tmp/` file lives on the container instance's local disk. With multi-instance autoscaling, a poll can land on a different instance from the one that ran the worker — in which case Priority 1 misses and Priority 2 (Firestore) is the durable source. On the current single-worker (`--workers 1`) Cloud Run config this rarely happens in practice, but Priority 2 is the real workhorse. Don't be tempted to remove the Firestore fallback.

**Tmp file cleanup (added in follow-up):** The poll endpoint now best-effort-deletes `task_prod_{task_id}.json` after successfully hydrating `final_table` on a terminal-state poll (the project doc has the data at that point, so Priority 2 covers all later polls — including the "Download JSON" button). Prevents unbounded accumulation on long-lived Cloud Run instances. Wrapped in try/except; a deletion failure is logged but never breaks the poll response.

### 2. Retry-beats server-side fallback (Bug #1 fix)

When the client sends an empty `existing_table` (no shots), the retry-beats endpoint now attempts to hydrate it from the Firestore project doc before returning the 400 error.

- `execution/server.py` (`retry_missing_beats_route`, ~line 3764) — new fallback block: if `existing_table` lacks `shots` and `project_id` is available, fetches the project doc from `users/{uid}/projects/{project_id}` and extracts `production_data.production_table`. Only returns `"No existing production table to extend"` if *both* the client payload and Firestore lookup fail.

### 3. `loadLatestProductionTable()` rewrite — project-scoped, de-duplicated (Bug #2 fix)

The function was completely rewritten to eliminate reliance on the potentially stale `currentProductionData` global.

**Before:** Checked `currentProductionData` in memory first → fell back to `/api/latest-production-table` endpoint (which scanned `.tmp/` for the most recent file, not necessarily the current project's file).

**After:** Always fetches fresh from the backend, with two priority sources:
1. **Priority 1:** Firestore project doc (`/api/projects/{currentProjectId}`) → extracts `production_data.production_table`. This is the authoritative, project-scoped source.
2. **Priority 2:** `.tmp/` fallback via `/api/latest-production-table?project_id={currentProjectId}` — only if the project doc has no production data.

- `ui/index.html` (`loadLatestProductionTable`, lines 6880–6953) — full rewrite. The function:
  - Always makes a fresh `authFetch` to `/api/projects/{currentProjectId}` to get the project doc.
  - Normalizes the response: handles both `{production_table: {...}}` and flat table structures.
  - Updates `currentProductionData` from the server response (not from stale memory).
  - **De-duplication guard:** Before calling `initVisualsFromProductionTable(pt)`, checks if the Visuals tab already has scenes loaded from an identical production table. If so, shows "Already loaded" status and returns without re-importing.
  - Status badge shows data source: `"from project doc"` or `"from tmp storage"`.

**De-dup guard tightening (added in follow-up):** The original guard compared only `title` + `shot count` + `visualsScenes.length`. Two distinct tables that happened to share a title and shot count (e.g. a regeneration of the same project) would falsely match and the new table would silently fail to load. The guard now also compares a 120-char prefix of the first shot's prompt fields (`first_frame_prompt`, falling back to `directors_intent` / `script_beat` / `veo_prompt`) — these are content-dependent and effectively disambiguate distinct generations.

### 4. Background op project scoping — `targetProjectId` pattern

Multiple async functions were using `currentProjectId` after `await` boundaries, which is unsafe because the user might switch projects during the async operation. These were hardened with a `const targetProjectId = currentProjectId` capture at function entry.

- `ui/index.html` (`suggestTitles`, ~line 3967) — captures `targetProjectId` at function entry, uses it for `setBackgroundOp` calls.
- `ui/index.html` (`generateProductionTable`, ~line 4660) — same pattern; all `setBackgroundOp` calls use `targetProjectId` instead of `currentProjectId`.
- `ui/index.html` (`retryMissingBeats`, ~line 5139) — same pattern.
- `ui/index.html` (`startProductionTaskPolling`, ~line 4820) — terminal state handlers (`complete`, `coverage_failure`, `failed`) now use `state.projectId` (captured at poll start) for `setBackgroundOp` and `clearBackgroundOp` calls, ensuring the correct project is updated even if the user switched projects while the poll was running.
- `ui/index.html` (`finalizeStreamedTable`, ~line 4971) — now receives `projectId` as an explicit parameter and passes it to `setBackgroundOp`.

### 5. State isolation on project switch

Two state leaks in `clearAppForNewProject` were fixed:

- `ui/index.html` (`clearAppForNewProject`, ~line 9864) — added `visualsProductionData = null` alongside the existing `visualsScenes = []` and `visualsCharacters = []` resets. Without this, the de-duplication guard in `loadLatestProductionTable` could compare against stale data from the previous project.
- `ui/index.html` (`clearAppForNewProject`, ~line 9883) — added reset of the `#visualsLoadStatus` DOM element to `"No production data loaded yet"`. Prevents showing stale "Loaded: Project A" text when switching to Project B.

## Files Touched

| File | Sections |
|------|----------|
| `execution/server.py` | `_worker` — task result persistence to `.tmp/` (~3499); `_retry_worker` — same (~3846); `production_task_poll_route` — `.tmp/` hydration fallback + best-effort cleanup on terminal-state hydration (~3653–3700); `retry_missing_beats_route` — Firestore fallback for empty `existing_table` (~3786) |
| `ui/index.html` | `loadLatestProductionTable` — full rewrite with project-scoped fetch + content-aware de-duplication guard (~6880–6966); `suggestTitles` — `targetProjectId` capture (~3967); `generateProductionTable` — `targetProjectId` capture (~4664); `retryMissingBeats` — `targetProjectId` capture (~5139); `startProductionTaskPolling` — `state.projectId` for terminal handlers (~4820); `finalizeStreamedTable` — explicit `projectId` parameter (~4971); `clearAppForNewProject` — `visualsProductionData = null` + `visualsLoadStatus` reset (~9865, ~9885) |

## Verification

1. **Retry-beats recovery** — Generate a production table, force a coverage failure (or wait for one naturally). Click "🔁 Retry missing scenes" → should successfully extend the existing table. If `existing_table` arrives empty, the server fetches from Firestore automatically.
2. **Download JSON** — After generation completes, click "Download JSON" under the table → should download a valid `.json` file. This works because `final_table` is now reliably hydrated from `.tmp/` in the poll endpoint.
3. **Per-project isolation** — Generate tables for two different projects in parallel. When Project A finishes:
   - Switch to Project A, go to Visuals tab, click "Load Latest Production Table" → should load Project A's table (status shows "from project doc").
   - Switch to Project B (which hasn't finished yet), go to Visuals tab, click "Load Latest Production Table" → should show Project B's data (or "no valid production data" if it hasn't finished), **not** Project A's data.
4. **De-duplication** — Load a production table in the Visuals tab. Click "Load Latest Production Table" again → should show "Already loaded: ..." status instead of re-importing and resetting scene states. Regenerate the table (same title, same shot count, different prompts) → should now correctly re-import (prompt-prefix signature distinguishes it from the previous version).
5. **Tmp file cleanup** — After a streaming generation completes and the client polls once, `ls .tmp/task_prod_*.json` should be empty for that task. The "Download JSON" button should still work because Priority 2 (Firestore) supplies `final_table` on subsequent polls.
6. **Project switch state reset** — Switch between two projects with production data. The Visuals tab status badge should reset to "No production data loaded yet" on each switch. No stale "Loaded: Project A" text should appear when viewing Project B.

## Deployment

Two deployments were made during this session:
1. **First deploy** — Bug #1 + #3 fixes (task result persistence, retry-beats fallback)
2. **Second deploy** — Bug #2 fix (per-project production isolation, de-duplication guard, state cleanup)

Both deployed to staging via `deploy_staging.sh`. Production deploy pending user verification.
