# Production Table — JSON Resilience + UI Cleanup

**Date:** 2026-05-25
**Status:** Shipped to staging (pending Wasp-project validation)
**Plan:** `docs/production_table_json_resilience_2026_05_25/plan.md`
**Predecessor:** `docs/changelog_production_table_unlimited_scale_2026_05_24.md` (Steps 1–11)

This session ships the **Tier 1 + 2 + 3 + UI** subset of the approved plan.
Tier 4 (the prose→structured-fields rewrite of Phase 5) was explicitly **skipped** because Tiers 1–3 already fix the reported failure and Tier 4 would change user-visible generation quality without an A/B path.

---

## 1. Problem statement (recap)

After Steps 9–11 (2026-05-24) shipped — gemini-3.5-flash, structured JSON mode, 64K tokens, CPU-throttling fixed — Phase 5 (DP) was **still failing every batch** on the Wasp project with the same error string:

```
[parse] FAILED — no parseable JSON. Length=125787.
Head: '{ "title":"The Wasp...","total_shots":29,"shots":[...'
Tail: '... } }'
[Production] Batch 7 FAILED after 3 attempts: Phase 5 (DP) JSON parse failed
```

Forensics (this session): responses were **not** empty and **not** truncated — brackets balanced, salvager bailed because the `]` closed cleanly. The only remaining cause: **literal control characters (`\n`/`\t`) inside string values**. Python's strict `json.loads` rejects them. This is a known limitation of Gemini's `response_mime_type="application/json"` mode for long-form prose values.

Two separate user-experience problems were also surfaced in the same session:

- Two redundant failure UIs (the "🔁 Retry missing scenes" modal + the Resume/Discard banner) confused the recovery flow.
- No way to cancel a long-running generation mid-flight.
- Failures were invisible to users — they had to ask the developer to pull Cloud Run logs to see why a batch died.

---

## 2. Tier 1 — Parser robustness ladder

**File:** `execution/research_scriptwriter.py:418` (`_parse_json_response`)
**Dependency:** `json-repair==0.59.10` added to `requirements.txt`

The parser now runs a **five-step recovery ladder** before raising:

1. `json.loads(text)` — strict (current happy path).
2. **NEW:** `json.loads(text, strict=False)` — allows raw `\n`/`\t`/`\r`/control chars inside strings. This single step recovers every failure seen in the Wasp logs.
3. Outer-brace extraction (`text[first_brace:last_brace+1]`), tried both strict and `strict=False`.
4. `_salvage_truncated_shots` (preserved) — handles real truncations where the `]` never closes.
5. **NEW:** `json_repair.loads(text)` — final fallback for trailing commas, missing quotes, stray prose, half-closed brackets. Used in production by LangChain/LlamaIndex for the same problem.

The head + tail diagnostic (Step 11) remains as the last line of defense; only fires when all five paths fail.

**Tests:** new `tests/test_json_parser_ladder.py` with 9 cases covering raw newlines, raw tabs, trailing commas, prose-wrapped JSON, code fences, truncation salvage, and the strict-path happy case. All pass.

---

## 3. Tier 2 — Pydantic `response_schema` (sampler-level enforcement)

**Files:** `execution/gemini_client.py:173-178`, `execution/research_scriptwriter.py:40-153, 1525+`
**Dependency:** `pydantic>=2.0,<3.0` added to `requirements.txt` (was transitive via `google-genai`; now explicit since we import it directly).

`generate_content()` accepts a new `response_schema` parameter. When set, it's attached to `GenerateContentConfig.response_schema` alongside the existing `response_mime_type`. Both wrapped in defensive `try/except` so older SDKs degrade gracefully.

Five new permissive Pydantic v2 models cover the 6-phase outputs:

| Model | Phase | Inherits from | Adds |
|---|---|---|---|
| `Phase1DirectorOutput` | Director | — | `emotional_arc_analysis` + shot fields (shot_number, script_beat, duration, act, beat, emotion, directors_intent, camera_intent, cutting_rationale, emotional_arc_position) |
| `Phase2CinematographerOutput` | Cinematographer | Phase 1 fields | camera_movement, camera_angle, lens_feel, composition, lighting_mood, depth_focus, visual_storytelling_technique |
| `Phase3StoryboardOutput` | Storyboard | Phase 2 fields | story_analysis + visual, shot_size, fg_mg_bg_layers, visual_metaphor_execution, character_outfit, character_expression, visual_continuity_notes |
| `Phase4ContinuityOutput` | Continuity Supervisor | Phase 3 fields | review_summary + continuity_fix, continuity_grade |
| `Phase5DPOutput` | DP | Phase 4 fields | title, aspect_ratio, style_summary, total_shots, timestamp, first_frame_prompt, veo_prompt, continuity_notes, production_notes |

All fields are `Optional[...]` and every model uses `ConfigDict(extra='allow')` for forward compatibility. `_call_phase` accepts a `response_schema` kwarg and threads it into both the primary call and the dropped-shot retry call. Phase 4 continuity wired directly.

Per Google's 2026 structured-outputs announcement, the sampler is constrained at inference time to emit only tokens that keep the JSON valid against the schema — strongest available guarantee that the output parses cleanly. Tier 1's parser ladder stays in place as defense-in-depth.

---

## 4. Tier 3 — Phase 5 sub-batching (blast-radius reduction)

**File:** `execution/research_scriptwriter.py` (Phase 5 block in `_generate_single_batch_6phase`)

Phase 5 has the largest per-shot prose payload. On the Wasp project, a single ~40-shot call produced ~150 KB of JSON. Now:

- New constants: `MAX_PHASE5_SHOTS = 10`, `MAX_PHASE5_CONCURRENCY = 4`.
- New inner helper `_call_phase5(sub_shots, sub_label)` — wraps a Phase 5 call so it can run from a thread pool. Returns `(sub_shots, sub_production_dict, error_or_None)`.
- Below 10 shots: single call (no overhead).
- Above 10: split into ≤10-shot chunks, run via `ThreadPoolExecutor(max_workers=4)`, then merge.
- Merge logic preserves shot order (results array indexed by chunk position) and reuses the first successful sub-batch's top-level metadata (`title`, `aspect_ratio`, `style_summary`). Updates `total_shots` to the merged count.
- Partial-success path: if some sub-batches succeed and others fail, the surviving shots are returned with a `Phase 5 partial` log line — the existing coverage check / resume banner picks up the gap.

**Effect:** per-call output drops from ~150 KB to ~30 KB. If anything sneaks past Tiers 1+2, a single sub-batch failure costs 10 shots instead of 40.

---

## 5. UI cleanup — one banner, Cancel button, inline error log

User direction this session: *"delete the popup, keep only the banner above the table, add a Cancel button, and show errors inline like the image history strip — I want to see what's failing."*

### 5a. Deleted the coverage-failure modal

- `ui/index.html:209-224` — removed `coverageFailureModal` DOM (modal overlay + summary + beats list + retry/use-partial buttons).
- Removed `openCoverageFailureModal`, `closeCoverageFailureModal`, `retryMissingBeats`, `pendingCoverageRetry` (~110 lines).
- The two call sites that opened the modal (sync path at `~4778`, streaming terminal at `~4928`) now call `checkProductionResumable(currentProjectId)` — the Resume/Discard banner is the single failure-recovery UI.

### 5b. Inline error log — image-history-tile pattern

- `ui/style.css` — new `.production-error-log` strip + `.production-error-tile` styles. Collapsible header + scrollable body, mirrors the existing image-history strip at `style.css:3426`.
- `ui/index.html:1672-1679` — DOM container right above the resume banner. Hidden when `errors.length === 0`.
- `renderProductionErrorLog(errors)` — renders one tile per error in reverse chronological order. Tile summary row shows **phase · batch · timestamp · short message**.
- `toggleProductionErrorTile(idx)` — click a tile to expand inline: full error string, response length, response head, response tail, task_id (for cross-reference with Cloud Run logs).
- Wired into `checkProductionResumable` so the log refreshes on project switch, page reload, and every terminal poll state.

### 5c. Cancel button — full-wipe semantics

- `ui/index.html:1665` — `#productionCancelBtn` next to the Generate button. Hidden by default; shown by `startProductionTaskPolling`, hidden by `stopProductionTaskPolling`.
- `cancelProductionTable()` — confirms with the user, POSTs to the new backend endpoint, then wipes the local table body, hides the resume banner, clears the error log, and returns the page to the pre-generation state.

### 5d. Backend wiring

- `execution/firestore_helpers.py` — new `append_error(uid, pid, error_record, max_keep=50)`. Appends `{phase, batch, ts (ISO UTC), error, task_id, response_length?, response_head?, response_tail?}` to `pipeline_checkpoints/task_state.errors[]`. The `max_keep=50` cap bounds the array so a runaway failure loop can't blow the 1 MB doc-size limit; older records drop first.
- `execution/server.py` — `_progress_cb` mirrors every `batch_failed` event into `task_state.errors[]`. Pipeline-error and worker-exception terminal paths also call `append_error`.
- `execution/server.py:2789` — `/api/projects/<id>/resumable` now returns `errors: []` in its response.
- `execution/server.py` — new endpoint `POST /api/production-task/<task_id>/cancel`. Flips task to `status='cancelled'`, then calls `fh.clear_shots` + `fh.clear_checkpoints` so the user sees a clean slate immediately.
- `execution/server.py` — `_progress_cb` cooperatively checks `task.status == 'cancelled'` on every `batch` / `batch_failed` event and raises a new `_GenerationCancelled` sentinel. The worker's outer handler catches it and **skips all terminal writes** (no status='failed', no commit) so the cancel endpoint's clean wipe sticks.

---

## 6. Tier 4 — explicitly skipped

Tier 4 (rewrite Phase 5 to emit structured component fields + server-side prompt composer) was on the plan but deferred. Rationale:

- The current parse-failure problem is fully addressed by Tiers 1+2+3.
- Tier 4 is the **only** tier that changes user-visible generation output quality — `first_frame_prompt` / `veo_prompt` strings get assembled differently and would produce subtly (or substantially) different images/videos.
- The plan's own risk callout said Tier 4 needs A/B validation against 2–3 reference projects before promoting. That validation requires actual generation runs against the live Gemini/Veo/MJ APIs and side-by-side image comparisons.
- Skipping it saves ~1 day of work that isn't needed for the reported bug.

If a future workload still hits some new parse failure mode that Tiers 1+2+3 can't catch, Tier 4 is on the shelf in the plan file.

---

## 7. Files changed

| File | Status | Change |
|---|---|---|
| `execution/research_scriptwriter.py` | Modified | 5-step parser ladder; Pydantic schemas (~115 new lines); `_call_phase` accepts `response_schema`; Phase 5 sub-batching (~70 new lines) |
| `execution/gemini_client.py` | Modified | `generate_content` accepts `response_schema`; wires into `GenerateContentConfig` defensively |
| `execution/server.py` | Modified | `/api/projects/<id>/resumable` returns errors; `_progress_cb` mirrors failures + checks cancel; new `_GenerationCancelled` sentinel; new `POST /api/production-task/<id>/cancel` endpoint; pipeline + worker terminal paths call `append_error` |
| `execution/firestore_helpers.py` | Modified | New `append_error(uid, pid, record, max_keep=50)` |
| `ui/index.html` | Modified | Modal + handlers removed (~115 lines); error log DOM + 3 new JS functions; Cancel button + handler; banner is single failure-recovery UI |
| `ui/style.css` | Modified | `.production-error-log` + `.production-error-tile` styles (~110 new lines mirroring history-strip pattern) |
| `requirements.txt` | Modified | `+ json-repair==0.59.10`, `+ pydantic>=2.0,<3.0` |
| `tests/test_json_parser_ladder.py` | NEW | 9 tests covering control chars, json_repair fallback, regressions |
| `docs/production_table_json_resilience_2026_05_25/plan.md` | NEW | The approved plan |
| `docs/production_table_json_resilience_2026_05_25/changelog.md` | NEW | This file |

---

## 8. Test results

```
$ pytest tests/test_json_parser_ladder.py -v
9 passed in 1.44s

$ pytest tests/test_api_workflows.py tests/test_firestore_helpers.py \
         tests/test_production_batching.py tests/test_pricing.py \
         tests/test_cost_tracker.py tests/test_usage_routes.py \
         tests/test_json_parser_ladder.py tests/test_structured_research.py \
         tests/test_narrative_spine.py -q
101 passed, 1 failed in 1.39s
```

The single failure (`tests/test_structured_research.py::test_generate_content_no_config_when_all_none`) **reproduces on clean HEAD before any of these changes** — confirmed via `git stash` + re-run. Not a regression; it's pre-existing dead code in the test asserting `config is None` when the default `timeout_s=180` already forces a config object.

---

## 9. Staging validation plan (Wasp project)

After `./deploy_staging.sh`:

1. **Stale task recovery** — open the Wasp project. The Step 8 sweep should pick up the orphaned tasks (`721a080b…`, `8dc8c106…`) and surface them via the Resume banner. The new error log should show the historical Phase 5 failures from the 2026-05-24 run as clickable tiles.

2. **Resume → completion** — click Resume. With Tier 1 + 2 in place, the missing-beats retry should now succeed. Watch for `Phase 5 complete: N shots with prompts (sub X/Y)` lines across every sub-batch. **No** `[parse] FAILED — no parseable JSON` lines.

3. **Fresh large generation** — regenerate a new ~400-shot project from scratch. Confirm:
   - No worker exits mid-flight (CPU throttling fix from Step 10 holds).
   - All batches complete on first try (Tiers 1 + 2 hold).
   - Phase 5 sub-batches are visible in logs as `(sub 1/4)`, `(sub 2/4)`, etc.

4. **Inline error log** — force a failure by, e.g., temporarily revoking your Gemini key partway through a run. Confirm:
   - A tile appears in the inline error log immediately.
   - Tile shows phase, batch, timestamp, summary.
   - Clicking expands to show the full error + response head/tail + task_id.
   - Tiles persist across page reload.

5. **Cancel button** — start a long generation, click Cancel. Confirm:
   - `shots/` subcollection wipes immediately.
   - `pipeline_checkpoints/` wipes.
   - Resume banner does NOT appear (full-wipe semantics).
   - Page returns to pre-generation state.
   - Cloud Run logs show `task <id> cancelled by user` and the worker exits without writing terminal state.

6. **No coverage modal under any failure scenario** — the 🔁 Retry missing scenes modal should never appear regardless of how a run fails.

---

## 10. Traceability

| Reported symptom | Root cause | Fix |
|---|---|---|
| Phase 5 batches keep failing with "No JSON object found" despite Steps 9-11 | Raw control characters inside string values; strict `json.loads` rejects | Tier 1: 5-step parser ladder with `strict=False` + `json_repair` |
| Same prompt → same failure → 3 retries → still fails | No sampler-level constraint that JSON must be valid | Tier 2: Pydantic `response_schema` on all 6-phase calls |
| Single 40-shot Phase 5 call produces 150 KB output, hard to recover any | One monolithic call per batch | Tier 3: ≤10-shot sub-batches, parallel, partial-success path |
| Two redundant retry UIs (modal + banner) | Historical artifact | UI: deleted modal, banner is sole failure UI |
| Users can't see what error happened without asking dev to pull logs | No persistent UI surface for failures | UI: inline error log + `task_state.errors[]` |
| No way to abort a long-running generation | No cancel endpoint / worker check | UI: Cancel button + cooperative cancel via `_GenerationCancelled` sentinel |
