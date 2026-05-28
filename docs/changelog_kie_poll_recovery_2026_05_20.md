# Changelog — Kie Poll Recovery: Don't Lose Tasks the User Already Paid For

**Date:** 2026-05-20
**Branch:** main
**Scope:** Visuals tab (Phase 4) — Kie image/video generation polling

## Why

User report: when a Kie image/video generation in the Visuals tab fails to fetch the result, regenerating charges the user again — even though the Kie task already completed successfully on Kie's side. Two distinct symptoms:

1. **"Image error: Rate limit exceeded after retries."** — surfaced from the frontend `authFetch` wrapper, not from Kie. Our own server's Flask-Limiter (`@limiter.limit("600/hour")` on `/api/kie/poll/<task_id>`) was emptying its bucket under realistic load: 4s polling × multi-minute Kie video tasks × parallel scenes = >600 polls/hour. Once 429s started, `authFetch` retried 3× then threw; the polling loop's `consecutive >= 5` check killed the loop entirely; the Kie task kept running and finished, but the UI was locked in an error state with no way back to the result.
2. **"Stays generating forever even though Kie shows it's done."** — `s.imageStatus = 'polling'` was autosaved to Firestore, but the Kie `task_id` itself lived only in JS closure memory. On refresh, the spinner came back but had no task to rejoin against. After follow-up testing the user also hit: **"closed the tab right after Generate ×5 → reopened → production table not loaded, Visuals scenes empty, even after clicking 'Load production table' the in-flight tasks are gone."** Root cause: the Firestore autosave of `visuals_scenes` is a fire-and-forget `fetch` PUT that the browser cancels when the tab closes mid-flight — so `pendingKieTaskId` never reached the server.

The orthogonal failure modes share one root cause: **the only durable record of a Kie task lived inside an async network round-trip we couldn't guarantee would finish.**

## Changes

### 1. Server: raise polling rate limits

`execution/server.py:792, :834` — both `kie_poll` and `kie_mj_poll` bumped from `600/hour` to `3600/hour` per user.

Polls are read-only and idempotent; the expensive operation is `kie_create_task` (`/api/kie/generate`, still `120/hour`). Throttling the poll path was the wrong defense layer — it punished users for waiting on long Veo/Kie video jobs instead of for spamming generations. At 4s polling, 3600/hour comfortably covers ~10 parallel scenes polling for an hour.

### 2. Frontend: exponential-backoff polling that doesn't give up

`ui/index.html:_visualsPollStudioKie` (~6870) — full rewrite of the poll loop.

- **Before:** 4s fixed interval, `consecutive++` on errors, bail to status `error` after 5 consecutive failures, 10-min wall-clock timeout. A 429 storm killed the loop in ~30s while the Kie task happily kept running.
- **After:** 4s base interval, doubles on each error up to a 30s cap, resets on a clean poll. No early give-up — the loop runs to its (now 20-min) wall-clock timeout. On HTTP errors logs `[Kie poll] HTTP <status> on scene <id> — backing off to <delay>s`.
- **Why 20 min, not 10:** Kie video models (Seedance, Veo) routinely take 5–8 min; with backoff on rate limits the effective polling window needs more headroom.

### 3. Frontend: persist `pendingKieTaskId` on the scene (Firestore path)

`ui/index.html:_visualsPollStudioKie` (~6877) — at poll entry, writes `pendingKieTaskId`, `pendingKieKind`, `pendingKieStartedAt` onto the scene object and calls `doSaveProject()`. Cleared only on terminal **success** (or on Kie-reported `status: 'failed'`, which is genuinely unrecoverable). Timeout and rate-limit-give-up paths intentionally leave the fields set so the user can recover.

`ui/index.html:loadProject` (~10433) — after restoring `visuals_scenes`, scans for any scene with `pendingKieTaskId` and immediately re-enters `_visualsPollStudioKie` against the saved task. Also heals stuck spinners (`imageStatus === 'polling'` with no `pendingKieTaskId` and no `imageUrl` — pre-existing sessions before this fix) by flipping them to `error` with a "polling lost across reload" message, so the spinner doesn't lie.

### 4. Frontend: `localStorage` recovery store (the durable layer)

`ui/index.html` (~6802) — Round 3's belt-and-suspenders fix after the user reported that closing the tab right after Generate lost the taskIds.

| Helper | Purpose |
|--------|---------|
| `setKieRecoveryRecord(projectId, sceneId, taskId, kind)` | Synchronous `localStorage` write, keyed `kieRecover:<projectId>`. Survives instant tab close. |
| `clearKieRecoveryRecord(projectId, sceneId)` | Removes one record; deletes the parent key when empty. |
| `getKieRecoveryRecords(projectId)` | Reads the per-project record map. |
| `resumeKieRecoveryForVisuals()` | Scans localStorage, attaches `pendingKieTaskId` to matching scenes by `sceneId`, resumes polling. Idempotent. 48h TTL so dead records auto-clean (Kie tempfile URLs expire in ~24h, so anything older is unrecoverable). |

`_visualsPollStudioKie` writes to localStorage **before** calling `doSaveProject()`. Captures `targetProjectId` at function entry (same pattern as the `changelog_retry_fix_project_isolation_2026_05_18.md` work) so a mid-poll project switch can't clear the wrong project's record.

### 5. Frontend: auto-recovery on project reopen

Two paths converge on `resumeKieRecoveryForVisuals()`:

- **`ui/index.html:initVisualsFromProductionTable`** (~7253) — after rebuilding scenes from the production table (which drops `pendingKieTaskId` because it re-maps from raw `pt.shots`), immediately re-attaches the taskIds from localStorage. Appends a small `— resumed N in-flight Kie tasks` note to the load-status banner.
- **`ui/index.html:loadProject`** (~10537) — after restoring (or failing to restore) `visuals_scenes`, also runs the localStorage sweep. **Critical add (~10544):** if `visualsScenes` is empty but `currentProductionData` is set AND localStorage has pending records, auto-calls `initVisualsFromProductionTable(pt)` so the user doesn't have to click "Load Latest Production Table" before recovery can kick in. This covers the most common failure mode: user hit Generate ×N then closed the tab before autosave could persist `visuals_scenes`.

### 6. Frontend: "Recover task" button on errored scenes

`ui/index.html:getStatusHtml` (~7822) — when a scene is in `error` state and `pendingKieTaskId` is set, renders a `Recover task` button alongside the error message. Click → `recoverPendingKieTask(idx)` → re-enters `_visualsPollStudioKie` with the saved task. No charge if the task already finished.

This is the manual escape hatch for cases where auto-resume didn't fire (e.g. a non-Kie engine briefly errored, or the user dismissed the auto-recovery).

## Files Touched

| File | Sections |
|------|----------|
| `execution/server.py` | `kie_poll` rate limit (`:792`); `kie_mj_poll` rate limit (`:834`) |
| `ui/index.html` | `_kieRecoveryKey` + recovery store helpers (~6802–6837); `resumeKieRecoveryForVisuals` (~6839) with 48h TTL; `_visualsPollStudioKie` rewrite — backoff, taskId persistence, terminal-state clears (~6870–6975); `recoverPendingKieTask` (~6981); `getStatusHtml` — Recover button (~7822); `initVisualsFromProductionTable` — resume hook + load-status banner (~7253); `loadProject` — heal stuck spinners + resume from scene + resume from localStorage + auto-load production table when needed (~10433, ~10537–10553) |

## Verification

1. **Generate-then-close recovery (the original symptom).** Hit Generate ×5 in Visuals, close the tab immediately. Reopen the project. Expected: Visuals tab auto-populates scenes, 5 polling spinners appear, results stream in within Kie's normal completion window. Console shows `[Visuals] auto-loading production table to recover N in-flight Kie task(s)` and `[Visuals] resuming Kie poll (localStorage) scene=... task=...`. No "Sync lost images" needed, no re-charge.
2. **Rate-limit storm.** Generate ~10 Kie scenes in parallel. Watch console for `[Kie poll] HTTP 429 ... backing off to Xs` — backoff should grow to the 30s cap and the loops should keep listening until Kie finishes. No `Rate limit exceeded after retries` error on the scene cards.
3. **Mid-poll refresh.** Start a Kie video generation, hard-refresh once the spinner is visible. Expected: spinner returns, polling resumes from the same task_id (visible via `localStorage.getItem('kieRecover:<projectId>')` in DevTools), result appears on completion. No new task created.
4. **Recover button.** Force an error path (block `/api/kie/poll` in DevTools for 90s). The scene should backoff but eventually stop with status `error`. The `Recover task` button should appear; clicking it re-enters polling without charging Kie again.
5. **Cross-project safety.** Start a Kie generation in Project A. Switch to Project B before it completes. Switch back to Project A — polling should still be tracking the right task, and the localStorage record should be under `kieRecover:<projectA-id>`, not B's.
6. **TTL cleanup.** Manually backdate a localStorage record to >48h old. Next `resumeKieRecoveryForVisuals` call should drop it without trying to resume.
7. **Rate limits.** After deploy, in Cloud Run logs grep for `429` on `kie/poll` paths — should be essentially zero given the new 3600/hr ceiling.

## Known Gaps / Follow-ups

- **Cross-device recovery.** localStorage is per-origin per-browser. A user who starts generation on their laptop and reopens on their phone won't see the in-flight tasks. Closing that gap requires server-side task tracking — keep a `users/{uid}/kie_tasks/{taskId}` collection on the Firestore project doc at the moment `/api/studio/generate` returns the taskId. Deferred.
- **Rehost still blocks the poll request.** `_rehost_kie_results` in `server.py:709` runs synchronously inside the poll handler, so a `completed` poll can take 10–30s while the server downloads from Kie and uploads to Firebase. The new 3600/hr ceiling absorbs the resulting poll-cadence drift, but the cleaner fix is to move rehost into a background worker (same blueprint as `_run_retry_beats` in `changelog_production_resumability_retry_salvage_2026_05_18.md`) and have the poll return `status: 'rehosting'` immediately. Deferred — revisit if rehost-induced 429s appear after this deploy.
- **Auto-load on project open without pending tasks.** `loadProject` only auto-runs `initVisualsFromProductionTable` when localStorage has pending records. If a user wants the Visuals tab populated automatically every time (no manual "Load Latest Production Table" click), that's a UX question to resolve separately.
- **Frontend `authFetch` 429 backoff is now somewhat redundant.** It still retries 3× with up to 30s `Retry-After` waits before throwing — but the calling poll loop now handles 429 via its own backoff. The double-layer isn't harmful (worst case is a longer effective delay before the loop sees the error) but could be simplified to a single layer in a future pass.

## Deployment

User deploys via `./deploy_staging.sh` then `./deploy.sh` after staging verification of the recovery scenarios above.
