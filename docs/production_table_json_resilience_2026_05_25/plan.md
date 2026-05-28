# Plan — Production Table JSON Resilience

**Date:** 2026-05-25
**Status:** Approved (planning complete, implementation pending)
**Scope:** Tiers 1–4 (parser + schema + batching + structure) + UI cleanup (delete retry popup, add Cancel button, add inline error log)

---

## 1. Context

The 6-phase production-table pipeline (`execution/research_scriptwriter.py`) is the **core** feature of the app, and is currently failing for any project past trivial size. The most recent staging logs (Wasp project, 2026-05-24) show Phase 5 (DP) failing every batch with the same root error:

```
[parse] FAILED — no parseable JSON. Length=125787.
Head: '{ "title":"The Wasp...","total_shots":29,"shots":[ ...'
Tail: '... } }'
[Production] Batch 7 FAILED after 3 attempts: Phase 5 (DP) JSON parse failed
```

Diagnosis: responses are NOT empty and NOT truncated. Brackets are balanced (the salvager bails because the `]` closes cleanly). The only remaining cause is **unescaped control characters (literal `\n`/`\t`) inside string values** — Python's strict `json.loads` rejects them. This is a known limitation of Gemini's `response_mime_type="application/json"` mode for long-form prose values.

The user-visible recovery UIs (the "Retry missing scenes" modal and the "Resume/Discard" banner) are **not broken** — they're correctly routing to the same `/api/generate-production-table/retry-beats` endpoint, but every retry re-hits the identical parse wall.

This plan implements the full industry-standard fix stack so the production table becomes durable across all batch sizes and prose lengths, plus a UI cleanup that removes the redundant retry popup, adds a Cancel button, and surfaces all errors in a persistent inline log (mirroring the image-history-tile pattern).

---

## 2. Scope (all four tiers + UI cleanup)

| Tier | Goal | Estimated effort |
|---|---|---|
| 1 | Parser robustness — `strict=False` + `json-repair` fallback | 15 min |
| 2 | Source-side enforcement — Pydantic `response_schema` on 6-phase calls | 2–3 hr |
| 3 | Blast-radius reduction — cap Phase 5 batches at ~10 shots | half day |
| 4 | Architectural — separate structured fields from prose in Phase 5 output | 1 day |
| **UI** | **Delete retry popup, add Cancel button, add inline error log** | **2–3 hr** |

---

## 3. Tier 1 — Parser robustness

### Files
- `execution/research_scriptwriter.py` — `_parse_json_response` at line 418
- `requirements.txt` — add `json-repair`

### Changes

In `_parse_json_response`, extend the existing four-attempt ladder:

1. `json.loads(text)` — current direct parse (strict).
2. **NEW:** `json.loads(text, strict=False)` — allows raw `\n`/`\t`/`\r` inside strings. Per Python stdlib docs this is the documented escape hatch.
3. Current bracket-extract fallback (`text[first_brace:last_brace+1]`) — also retry with `strict=False`.
4. Current `_salvage_truncated_shots` (line 364) — keep, handles real truncations.
5. **NEW:** `json_repair.loads(text)` final fallback — handles missing quotes, stray prose, trailing commas, etc. Used in production by LangChain/LlamaIndex for the same problem.
6. Only then raise with head+tail diagnostic (current behavior preserved).

`requirements.txt`: add `json-repair==0.30.3` (or current stable).

### Why this alone fixes today's bug
The Wasp-project log shows JSON that is structurally balanced (Tier 1 step 5 isn't needed) but fails strict parsing — step 2 alone clears it.

---

## 4. Tier 2 — Schema-enforced output

### Files
- `execution/gemini_client.py` — `generate_content` at line 178. Already threads `response_mime_type`; add `response_schema` param. (Refs lines 220–227.)
- `execution/research_scriptwriter.py` — `_call_phase` at line 1525. Add Pydantic models for Phase 1/2/3/5 outputs.

### Changes

Define Pydantic models matching what each phase already returns, e.g.:

```python
class Shot(BaseModel):
    shot_number: str
    timestamp: str
    script_beat: str
    duration: str
    # ...etc, matching the actual fields each phase emits

class Phase5Output(BaseModel):
    shots: list[Shot]
    post_production: str | None = None
```

In `_call_phase` (line 1540), pass the model as `response_schema=Phase5Output` alongside the existing `response_mime_type="application/json"`. Per Google's 2026 structured-outputs announcement, the sampler is constrained at inference time to emit only schema-valid tokens — the model literally cannot produce an unescaped `\n` mid-string.

Each phase gets its own model since the field shapes differ (Director adds `directors_intent`, Cinematographer adds `camera_technique`, DP adds `first_frame_prompt`/`veo_prompt`).

Keep Tier 1 in place as defense-in-depth even after Tier 2 ships — schema enforcement is strong but the parser ladder costs nothing.

---

## 5. Tier 3 — Smaller Phase 5 batches

### Files
- `execution/research_scriptwriter.py` — batch sizing logic feeding `_generate_single_batch_6phase` (line 1497). Search for `batch_size` / `BATCH_SHOTS` constants in `server.py` streaming worker.

### Changes
- Cap Phase 5 calls at ~10 shots (Phase 1–3 can remain larger; Phase 5 has the largest per-shot prose payload).
- Reuse the existing batch parallelism — multiple ~10-shot Phase 5 calls run concurrently instead of one ~40-shot call.
- Expected response size drops from ~150 KB to ~30 KB per call. Even pre-Tier-1 this would have stayed comfortably under the 64K token cap.

This is a constants/loop-bound change, not a structural one.

---

## 6. Tier 4 — Structure vs. prose separation

### Files
- `execution/research_templates.py` — Phase 5 DP prompt template (find via `build_dp_prompt` usage; called from research_scriptwriter.py:1465).
- `execution/research_scriptwriter.py` — Phase 5 output handling.

### Changes
- Change Phase 5 to emit **structured component fields** (`camera_move`, `lens`, `lighting_tags: [...]`, `mood_tags: [...]`, `subject_focus`, `composition_notes`) rather than a single long `veo_prompt` string.
- Add a server-side deterministic composer that assembles the final Veo/first-frame prompt from those fields. This is the same pattern used for the existing style + cast composition.
- Net effect: JSON string values are short and constrained — exactly the regime where Gemini structured outputs are bulletproof. Plus, downstream editing becomes structured (change a field, not regex through prose).

This tier is the only one that touches the prompt shape; queue it last so Tiers 1–3 stabilize first.

---

## 6½. UI cleanup — one banner, Cancel button, inline error log

User requirements (verbatim direction this session):
- **Delete** the "🔁 Retry missing scenes" modal popup. It's redundant with the Resume/Discard banner and confusing as a second UI for the same backend action.
- **Keep** only the Resume/Discard banner above the production table as the sole failure-recovery UI.
- **Add a Cancel button** so the user can abort an in-progress generation. Cancel = **full wipe** (no partial preservation — matches Discard semantics).
- **Add an inline error log** modeled on the **image-history-tile pattern** (`ui/index.html:2755` and `scene-image-history` at `:7937`). Errors should be persistently visible as small clickable tiles/rows — *not* a banner, *not* a modal, *not* a toast. Clicking a tile expands the full error (phase, batch, error string, response excerpt). User must be able to see what error occurred at a glance.

### UI changes — `ui/index.html`

| Change | Where |
|---|---|
| **Delete** `🔁 Retry missing scenes` button | line 217 |
| **Delete** `openCoverageFailureModal` / `closeCoverageFailureModal` / `retryMissingBeats` / `pendingCoverageRetry` | lines ~5253–5362 |
| **Delete** `coverageFailureModal` DOM node | search modal definition |
| **Reroute** coverage_failure handler at line 4778 / 4928 → just call `checkProductionResumable(projectId)` so the existing banner renders | lines 4776–4787, 4928–4935 |
| **Add Cancel button** to the Generate Production Table button area; visible only while a task is in flight | next to `productionBtn` |
| **Add error-log container** `<div id="productionErrorLog" class="error-log-strip">` above or below the resume banner. Tile rendering mirrors `image-history-tile` (`:2755`) | new block near `productionResumeBanner` (`:1683`) |
| **Surface live in-flight errors** into the error log instead of `phase3Error` inline red text (kept only for hard pre-task validation errors like missing narration) | `startProductionTaskPolling` (`:4880+`) on every batch-failed log line |

### Error log behavior (mirroring image history)

```
┌─ Errors (3) ─────────────────────────────────────────┐
│  [tile] Phase 5 · batch 7 · 23:33:33 · parse failed │
│  [tile] Phase 5 · batch 4 · 23:38:33 · parse failed │
│  [tile] Phase 3 · coverage retry · 504 DEADLINE     │
└──────────────────────────────────────────────────────┘
```

- Each tile: phase + batch + timestamp + short error summary.
- Click a tile → expands inline (no modal) showing: full error string, response length, head + tail of the unparseable text, `task_id` for cross-reference with server logs.
- Persists across page reloads (errors stored in `pipeline_checkpoints/task_state.errors[]`).
- Clears when user clicks Discard or starts a successful new generation.

### Cancel button — backend wiring

- **New endpoint** `POST /api/production-task/<task_id>/cancel` in `execution/server.py`. Sets `production_tasks/{task_id}.status='cancel_requested'`.
- **Worker check** in the streaming production worker (`server.py:3377+`) — between batches AND between phases, read `task.status`; if `cancel_requested`, break the loop and call new `_handle_cancel(uid, pid, task_id)` which:
  1. Wipes `shots/` subcollection via `fh.clear_shots`.
  2. Clears `pipeline_checkpoints/` via `fh.clear_checkpoints`.
  3. Marks task `status='cancelled'`.
- **UI** — Cancel button calls the endpoint, then clears the table body and hides the resume banner. Returns to the pre-generation state.

### Error capture — backend

In `execution/research_scriptwriter.py` `_call_phase` (line 1525) and the streaming worker batch loop:
- On any phase failure, append a structured error record to `pipeline_checkpoints/task_state.errors[]`:
  ```python
  {
    "phase": "Phase 5 (DP)",
    "batch": "7/10",
    "ts": SERVER_TIMESTAMP,
    "error": "<message>",
    "response_length": 125787,
    "response_head": "...",  # already captured by Step 10c diagnostic
    "response_tail": "...",
    "task_id": "<task>",
  }
  ```
- `/api/projects/<id>/resumable` returns these in the response so the UI can render the error log tiles immediately.

### Files affected by UI changes

| File | What changes |
|---|---|
| `ui/index.html` | Delete coverage modal + handlers; add error log + Cancel button; rewire coverage_failure path to banner-only |
| `execution/server.py` | New cancel endpoint + worker cancel check; error-log writes into `task_state.errors[]`; `/resumable` returns errors |
| `execution/research_scriptwriter.py` | Phase failures append to error list (called via callback from worker) |
| `execution/firestore_helpers.py` | Possibly extend `write_checkpoint` to handle the errors array, or add `append_error(uid, pid, error)` helper |

---

## 7. Existing utilities to reuse (do NOT duplicate)

| Utility | Path | Use in |
|---|---|---|
| `_parse_json_response` | `research_scriptwriter.py:418` | Tier 1 extension |
| `_salvage_truncated_shots` | `research_scriptwriter.py:364` | Keep as-is; complements json-repair |
| `_diagnose_empty_response` | `gemini_client.py` (Step 9) | Pair with schema errors |
| `_call_phase` | `research_scriptwriter.py:1525` | Single point to thread `response_schema` for Phases 1/2/3/5 |
| Phase 4 continuity call | `research_scriptwriter.py:~1652` | Same `response_schema` treatment |
| `_commit_production_table` | `server.py` (Step 3 helper) | No change — already durable per-shot writes |
| Resume/coverage retry path | `/api/generate-production-table/retry-beats` | No change — will start succeeding once parser works |
| `image-history-tile` CSS + DOM pattern | `ui/index.html:2755`, `renderImageHistory` ~`:8966` | Pattern to mirror for the new error-log tiles |
| `productionResumeBanner` + `checkProductionResumable` | `ui/index.html:1683`, `:5025` | Becomes the *only* failure UI; coverage_failure path reroutes into it |
| `fh.clear_shots` / `fh.clear_checkpoints` | `execution/firestore_helpers.py` | Reused for Cancel = wipe semantics |

---

## 8. Verification

### Local
```bash
pytest tests/                       # existing suite must stay green
pytest tests/test_research.py -v    # phase-pipeline behavior
```

Add at minimum one new unit test in `tests/test_research.py` that feeds `_parse_json_response` a payload with embedded raw `\n` characters and asserts it parses successfully (covers Tier 1).

### Staging end-to-end
1. `./deploy_staging.sh`.
2. Reopen the failing **Wasp** project. Confirm: stale-task sweep populates the Resume banner (Step 8 behavior preserved). Error log tiles show the historical Phase 5 failures.
3. Click Resume → confirm Phase 5 batches now complete (search logs for `Phase 5 complete: N shots with prompts (batch X/Y)` across every batch).
4. Generate a fresh 400+ shot production from scratch. Confirm:
   - No `[parse] FAILED — no parseable JSON` lines.
   - No `Worker exiting`/`Shutting down: Master` mid-generation.
   - Coverage gap at end is 0/N or recoverable in one retry-beats call.
5. After Tier 3: verify Phase 5 call sizes via log inspection (`Length=` lines from any forced-failure test) drop to ~30 KB.

### UI verification
6. Confirm the `🔁 Retry missing scenes` modal **never appears** under any failure scenario. Only the resume banner above the table shows up.
7. Force a parse failure (temporarily revert Tier 1 in a feature branch, or inject a malformed response). Confirm:
   - An error tile appears in the inline error log immediately.
   - Tile shows phase + batch + timestamp + short summary.
   - Clicking expands to show full error string + response head/tail + task_id.
   - Tiles persist across page reload (read from `task_state.errors[]`).
8. Start a long generation, click **Cancel** mid-flight. Confirm:
   - Worker stops within one batch boundary.
   - `shots/` subcollection is empty.
   - `pipeline_checkpoints/` cleared.
   - Resume banner does NOT appear (Cancel = full wipe).
   - Page returns to pre-generation state.

### Production
Promote only after staging completes a full 400+ shot run with zero parse failures.

---

## 9. Risks / open questions

- **json-repair dependency** — small, MIT-licensed, no transitive C deps. Adds ~50 KB to the image. Acceptable.
- **Pydantic schema drift** — if a phase prompt changes to emit a new field, the schema must be updated or the call will fail. Mitigated by keeping the Tier 1 parser ladder as fallback (the model output stays usable even if the schema is stale).
- **Tier 4 prompt rewrite** — Phase 5 prompt is large and well-tuned; rewriting it changes outputs subtly. Capture a before/after diff and review against 2–3 reference projects before promoting.

---

## 10. Deliverables

1. **This plan**, in `docs/production_table_json_resilience_2026_05_25/plan.md` (done).
2. Code changes per tiers 1→4.
3. Tier-completion changelog appended to the same folder as `docs/production_table_json_resilience_2026_05_25/changelog.md` following the project's existing dated-changelog convention.
4. Update `directives/research_and_scriptwriting.md` once Tier 4 ships (prompt shape changes).
