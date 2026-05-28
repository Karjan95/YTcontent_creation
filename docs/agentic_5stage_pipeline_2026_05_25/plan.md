# Plan — Agentic 5-Stage Production Pipeline

**Date:** 2026-05-25
**Status:** Approved, implementation in progress

---

## 1. Context

The current 6-phase production-table pipeline (`execution/research_scriptwriter.py:1095` — `generate_production_table()`, batched via `_generate_single_batch_6phase()` at line 1693) runs Director → Cinematographer → Storyboard → Continuity → DP across parallel batches of shots. After two weeks of patching it (parser ladder, Pydantic schemas, Phase 5 sub-batching, error log, cancel button — see `docs/production_table_json_resilience_2026_05_25/changelog.md`), the JSON failure mode is solved but a deeper architectural problem remains: **the pipeline is a JSON-shuffling exercise pretending to be a film team.**

Concrete failure modes from the latest staging runs:
- Phase 3 (Storyboard) occasionally returns 0 shots from a 131-shot batch input.
- Phase 5 (DP) emits creative fields (`first_frame_prompt`, `veo_prompt`) but drops carry-forward fields (`script_beat`, `duration`, `directors_intent`) because Optional Pydantic fields under output pressure get skipped.
- Each phase is a separate Gemini call passing JSON to the next phase. There is no shared memory, no critique loop, no back-and-forth. The "Director" never talks to the "Cinematographer" — Director outputs JSON, Cinematographer reads JSON fields.
- Parallel batching means Batch 4's Director has no idea what Batch 3's Director did. We patch the seams with a "boundary stitcher" but that is reactive.

User direction (2026-05-25 session): rebuild this as a real multi-stage agentic pipeline with **visible UI steps**, **smart and professional agents** that **maintain context like real film production**, **auto-flow with pause-anywhere**, **both direct edit and chat-feedback regeneration**, and **stage-level regeneration only**.

**Intended outcome:** Replace the 6-phase parallel-batching pipeline with a sequential 5-stage agentic pipeline where each stage is a real role (Director, Production Designer, DP, Director+Storyboard, Script Supervisor+DP), reads a growing markdown Production Bible as natural prose context, makes craft decisions with reasoning, and is exposed to the user as its own approvable panel in the Production tab. The final stage produces the same `production_table` row shape the Visuals tab already consumes, so nothing downstream changes.

---

## 2. The 5 Stages

Each stage corresponds to one Gemini call (no batching, no parallelism). Each writes its output to Firestore and appends a markdown section to the shared Production Bible. Subsequent stages read the full bible as natural prose.

| # | Stage | Role | Reads | Produces |
|---|---|---|---|---|
| 1 | Story Treatment | Director | script, research, audience, tone, format | logline, theme, emotional arc, scene-by-scene treatment, performance notes, tonal references |
| 2 | World & Design | Production Designer | Stage 1 + style refs + cast wardrobe | world/era/locations, color palette with dominance rules, texture vocabulary, recurring motifs, props & environment, lighting-source rules |
| 3 | Cinematography Plan | DP | Stages 1+2 + style refs | lens vocabulary with reasoning, camera movement language, lighting style per scene, mood escalation map, 3–5 canonical reference shots |
| 4 | Shot List | Director + Storyboard Artist | Stages 1+2+3 + cast | per-shot blueprint — shot_number, timestamp, duration, beat_ref, directors_intent, composition (FG/MG/BG), subject + action, camera move/lens/angle, expression/wardrobe state. **No prompts yet.** |
| 5 | Continuity + Final Prompts | Script Supervisor + DP | ALL prior stages | Step A: continuity sweep (shot-scale variety, character/wardrobe consistency, pacing rhythm) → revises Stage 4 list if needed. Step B: synthesizes `first_frame_prompt` + `veo_prompt` per shot, weaving every prior decision. |

**Key reuse:** Stage 5 output rows are the existing `production_table.shots[]` schema. They write to the existing `shots/` subcollection via `firestore_helpers.write_shots()`. Visuals tab consumption is **unchanged**.

---

## 3. The Production Bible (shared context mechanism)

The bible is the architectural change that makes this "real" instead of "more JSON shuffling."

- It is a single growing markdown document, composed from each stage's `bible_section` field.
- Every stage from #2 onward reads the bible-so-far as natural prose in its prompt — not JSON fields, not key-value carry-forward.
- This replaces the current "visual_brief" + JSON-handoff pattern with one document a real film crew would actually keep.
- Composed on the fly from `production_stages/*.bible_section` (no separate storage — always derived).
- User-edited fields override the agent's output when composing the bible.

---

## 4. Prompt Rewrite Philosophy

Every stage prompt follows this structure:

```
[PERSONA]   You are [role] with [experience]. You think like [...].
[BRIEF]     Read the production bible below. Internalize the world,
            the arc, the palette before deciding anything.
[PRINCIPLES] Make CHOICES with REASONS. Build on prior decisions, don't
            restate them. Reference real [DPs / films / designers] when
            it sharpens the brief. Don't list every possible technique;
            commit to a vocabulary.
[CONTEXT]   <full Production Bible markdown so far>
[USER FEEDBACK] (only if regenerating) "The user noted: '<feedback>'.
            Address this specifically while preserving what's working."
[OUTPUT]    One paragraph on shape, then schema-enforced JSON.
```

**Eliminated patterns:** `"shot_number": "<from input>"` template fill-ins. Schema enforces shape; prompt is a brief. Carry-forward between stages handled **server-side by merge**, not by asking the LLM to copy values.

---

## 5. Firestore Schema

New subcollection per project:

```
users/{uid}/projects/{pid}/production_stages/{stage_id}
  - stage_number: 1..5
  - stage_name: "story_treatment" | "world_design" | "cinematography" |
                "shot_list" | "final_prompts"
  - status: "pending" | "running" | "complete" | "approved" | "stale" | "error"
  - output: {<schema-enforced fields for this stage>}
  - bible_section: "## Stage N — Name\n\n..." (markdown rendered from output)
  - user_edits: {<field path>: <value>}
  - feedback_history: [{ts, note, prior_output_ref}]
  - error: <string|null>
  - created_at, updated_at
```

New flow-state doc:

```
users/{uid}/projects/{pid}/pipeline_checkpoints/agentic_flow
  - status: "idle" | "running" | "paused" | "complete" | "error" | "cancelled"
  - current_stage: 1..5
  - paused: bool
  - started_at, last_event_at
  - task_id: <string>
```

Stage 5 output still writes to existing `shots/` subcollection — Visuals tab unchanged.

---

## 6. Pydantic Schemas

`execution/agentic_schemas.py`. Required-fields-only (no `Optional`) to prevent the constrained decoder from skipping fields. No `dict`/`list[dict]` (explicit nested models). No `extra='allow'`.

Stage5Final.shot_deltas contains only the *new* fields (prompts + revisions). Server merges by `shot_number` to produce final `production_table.shots[]` — deterministic carry-forward.

---

## 7. Orchestrator

`execution/agentic_pipeline.py`:
- `run_stage(uid, pid, stage_number, feedback=None, ...)` — single-stage executor.
- `_run_pipeline_worker(uid, pid, task_id, api_key, start_at=1)` — auto-flow loop, honors pause + cancel.
- Reuses `_parse_json_response` ladder and `_GenerationCancelled` sentinel.

---

## 8. API Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/production/run` | Initialize stages, spawn worker. Returns `{task_id}`. |
| GET  | `/api/production/state` | Stages + flow_state + bible_markdown. Polled by UI. |
| POST | `/api/production/pause` | Sets paused=true. |
| POST | `/api/production/resume` | Clears paused, spawns worker. |
| POST | `/api/production/cancel` | Full-wipe semantics. |
| POST | `/api/production/stage/<n>/approve` | Mark stage approved. |
| POST | `/api/production/stage/<n>/edit` | Persist user edits. Marks downstream stale. |
| POST | `/api/production/stage/<n>/regenerate` | Re-run stage with feedback. Marks downstream stale. |

Old `/api/generate-production-table` preserved behind `USE_LEGACY_PRODUCTION=1` for one release.

---

## 9. UI — 5-Panel Production Tab

Replaces `phase3Card` block (`ui/index.html:1330–1738`). Per-panel controls: Approve / Edit / Regenerate-with-feedback. Top-level: Start / Pause / Cancel. Inline error log reused. Visuals tab unchanged.

---

## 10. Cutover Strategy

| Step | Risk |
|---|---|
| 1. Build behind `USE_NEW_PIPELINE=1` (default 1 on staging, 0 on prod) | Low |
| 2. UI feature-flagged via `/api/config` | Low |
| 3. Staging E2E against 3 reference projects (50/200/400 shots) | Medium |
| 4. Tune prompts vs. old-pipeline reference | Medium |
| 5. Flip prod flag | Medium |
| 6. After 1 week clean, delete old 6-phase code | Low |

---

## 11. Verification

### Unit
`pytest tests/test_agentic_pipeline.py -v`

### Staging E2E
1. `./deploy_staging.sh`
2. New project → complete Research+Script+Cast+Style → Start Pipeline
3. Verify auto-flow, pause/resume, regenerate-with-feedback, edit, cancel, refresh-restore
4. Compare Stage 5 output to old 6-phase output on same project

---

## 12. Risks

| Risk | Mitigation |
|---|---|
| Stage 1 writes thin "summary" instead of real treatment | Prompt enforces depth; reject if treatments < 80 words |
| Stage 5 over-revises Stage 4 | Cap revisions to 30% of shots |
| Bible grows large at Stage 5 | ~30–50KB for 400-shot project, acceptable |
| Stage 1 regenerate cascades 4 expensive stages | Show explicit cost estimate in confirmation |
| Quality comparison subjective | 3 reference projects pre-cutover |
| Flag misconfig ships wrong pipeline | Single `pipeline_mode()` helper, logged per run |

---

## 13. Out of Scope (deferred)

- Per-shot regeneration (stage-level only for v1)
- Streaming output rendering
- Pre-run cost estimate
- Automated A/B testing harness
- Multi-project parallel runs (already supported)
