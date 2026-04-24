# Per-User / Per-Project Cost Dashboard — Implementation Plan

> Status tracker: tick each box as phases land. Each phase has its own test sub-section so "done" always means "tested".

## Context

Gemini Studio makes **100–250 billable Gemini calls per full video production** (30–72 text calls across the 6-phase pipeline, 30–50 images, 30–50 Veo shots, TTS, style analysis). Today **none of that usage is captured** — `execution/gemini_client.py:60` `generate_content()` throws away the response object and returns only `.text`, and retries tracked inside `_retry_api_call()` (lines 29–51) are counted but discarded.

Users bring their own Gemini API key and eat the cost directly. There is currently **zero per-project spend visibility**, which makes pricing client work impossible and creates bill-shock risk. This plan adds **live, actual-spend tracking** from `usage_metadata` (tokens already include reference-image bytes automatically), with per-project + account-wide dashboards and a 30-day trend chart. Rates live in a Firestore config doc so Google-side price changes require one edit, not a redeploy.

## Scope (user-confirmed)

- ✅ In v1: per-project tool breakdown, account-wide totals, date range filter + daily trend chart, editable rates without redeploy.
- ❌ Not in v1: budget alerts, CSV export, version history, job queue, historical backfill.

---

## Phase A — `execution/pricing.py` (new module) ✅

- [x] A1. Create `execution/pricing.py` with `load_pricing(force=False)` (fetch `config/gemini_pricing` Firestore doc, cache in module-level dict, TTL=300s, `threading.Lock`).
- [x] A2. `get_rate(tool, model)` — returns rate dict; missing model returns `fallback[tool]` and caller stamps `status="fallback"`.
- [x] A3. Seed helper `_DEFAULT_PRICING` constant (used if Firestore doc missing so tests/CLI don't crash).

**Tests (Phase A)** — 9/9 pass
- [x] `tests/test_pricing.py` — known rates (text/image/imagen/tts/veo), fallback on unknown model, cache TTL, force refresh, pricing_version stamp.

---

## Phase B — `execution/cost_tracker.py` (new module) ✅

- [x] B1. `get_cost(tool, model, usage) -> (usd, pricing_version, is_fallback)` applying rates per tool.
- [x] B2. `record_usage(...)` — builds event doc + rollup increments in one `db.batch()`, commits asynchronously via `ThreadPoolExecutor(max_workers=4)`.
- [x] B3. Helpers: `track_text`, `track_image`, `track_imagen`, `track_tts`, `track_veo`, `track_veo_refund`.
- [x] B4. Graceful no-op when `uid is None` (CLI / test paths).

**Tests (Phase B)** — 11/11 pass
- [x] Cost math: text (with cached-token subtraction), veo, image, tts.
- [x] Fallback flagged when model unknown.
- [x] `record_usage` writes event + rollup batch with `merge=True` and `Increment` dot-paths, `.commit()` called once.
- [x] `uid=None` is a no-op.
- [x] `_extract_token_usage` / `_count_images_in_response` helpers covered.
- [x] `track_veo_refund` emits negative cost.

---

## Phase C — `execution/gemini_client.py` instrumentation ✅

- [x] C1. `generate_content`: added `uid, project_id, description` kwargs; retained `response`; calls `track_text`.
- [x] C2. `_generate_with_gemini_model` / `_generate_with_imagen_model` / `generate_image_content`: uid/pid threaded; event emitted per attempted model.
- [x] C3. `analyze_style_from_images`, `analyze_style_from_text`, `expand_creative_direction`, `refine_creative_direction`: uid/pid + `track_text` added.
- [x] C4. `generate_tts`: uid/pid + `track_tts(... len(prompt) ...)`.
- [x] C5. `generate_scene_image` (imagen + gemini branches) and `edit_scene_image`: uid/pid + per-scene tracking.
- [x] C6. `start_video_generation`: uid/pid + provisional Veo billing; `_video_operations[op_name]` upgraded to metadata dict.
- [x] C7. `poll_video_generation`: unpacks op dict; emits `track_veo_refund` on safety-block and exception paths.

**Tests (Phase C)** — 8/8 pass
- [x] `test_generate_content_tracks_tokens` — exact token counts captured from `usage_metadata`.
- [x] `test_generate_content_retries_counted` — `retries=2` after 2 transient 503s.
- [x] `test_generate_content_noop_without_uid` — runs without uid (record_usage gets uid=None).
- [x] `test_generate_scene_image_imagen_tracks_per_image` — `tool="imagen"`, `images=1`.
- [x] `test_generate_scene_image_gemini_tracks_per_image` — `tool="image"`, `images=1`.
- [x] `test_generate_tts_tracks_char_count` — `tts_chars=11` for "hello world".
- [x] `test_start_video_generation_bills_provisionally` — `tool="veo"`, `status="provisional"`, 6.0 seconds.
- [x] `test_poll_video_failure_emits_refund` — refund event with negative `cost_override`.

---

## Phase D — `execution/research_scriptwriter.py` wiring ✅

- [x] D1. `uid, project_id` added to: `generate_narration`, `auto_suggest_tone`, `regenerate_beats`, `generate_production_table`, `_generate_single_batch`, `_generate_single_batch_3phase`, `_generate_single_batch_6phase`, `run_structured_research`, `_run_sub_researcher`, `_planner_expand_subqueries`, `structure_from_blob`.
- [x] D2. Forwarded into every `generate_content(...)` call in the pipeline.
- [x] D3. `description=` stamped with stage label (`narration`, `director_6phase`, `cinematographer_6phase`, `storyboard_6phase`, `continuity_6phase`, `dp_6phase`, `script_doctor`, `research_planner`, `sub_researcher(<name>)`, `structure_from_blob`, `regenerate_beats`, `auto_suggest_tone`).

**Tests (Phase D)** — 4/4 pass
- [x] `test_generate_narration_forwards_uid` — uid/pid + description stamped correctly.
- [x] `test_auto_suggest_tone_forwards_uid`.
- [x] `test_production_pipeline_6phase_tags_stages` — all 6 stages present + uid/pid consistent across every call.
- [x] `test_regenerate_beats_forwards_uid`.

---

## Phase E — `execution/server.py` wiring + new routes ✅

- [x] E1. uid/project_id threaded into every gemini_client / scriptwriter call: `/api/generate-image`, `/api/generate-tts`, `/api/analyze-style-images`, `/api/analyze-style-text`, `/api/structure-script`, `/api/suggest-cast`, `/api/generate-cast-portrait`, `/api/generate-cast-portraits-batch`, `/api/expand-creative-direction`, `/api/refine-creative-direction`, `/api/research` + fallback + structured pipeline, `/api/deep-research/poll` structure_from_blob, `/api/suggest-titles`, `/api/auto-suggest-tone`, `/api/generate-script`, `/api/regenerate-beat`, `/api/generate-production-table`, `/api/visuals/generate-image`, `/api/visuals/edit-image`, `/api/visuals/generate-batch-images`, `/api/visuals/start-animation`, `/api/visuals/start-batch-animation`.
- [x] E2. 4 new routes added:
  - `GET /api/usage/account?start=&end=`
  - `GET /api/usage/trend?days=30` (or explicit start/end)
  - `GET /api/usage/project/<pid>?start=&end=`
  - `GET /api/admin/pricing` (gated by `ADMIN_UIDS` env)
- [x] E3. Date parser with 30-day default, 366-day cap, format/range validation.

**Tests (Phase E)** — 6/6 pass
- [x] `test_account_sums_rollups` — 2 rollup docs merged to correct total.
- [x] `test_trend_fills_zero_days` — `?days=5` returns 5 ordered entries, gaps zero-filled.
- [x] `test_account_rejects_invalid_date` — 400 on bad format.
- [x] `test_account_rejects_reversed_range` — 400 on end<start.
- [x] `test_admin_pricing_requires_admin_uid` — 403 for non-admin.
- [x] `test_admin_pricing_allowed_for_admin` — 200 + pricing doc returned.

---

## Phase F — `ui/index.html` Usage tab ✅

- [x] F1. Chart.js 4.4.1 CDN added in `<head>` (~70KB gz).
- [x] F2. New **"Usage"** tab button + `#tab-usage` panel.
- [x] F3. KPI row: Today / MTD / Last 30d.
- [x] F4. Date range picker + 7 / 30 / 90-day presets + Refresh button.
- [x] F5. Stacked bar trend chart (text/image/imagen/tts/veo).
- [x] F6. By-project table with Calls / Cost / % columns, sorted by cost desc.
- [x] F7. By-tool donut.
- [x] F8. CSS: `.usage-kpi` styling in `ui/style.css`.

**Manual test (Phase F)** — verified by static inspection; full end-to-end UI test requires the Flask dev server with Firebase creds (not available in this environment). Steps documented in Verification section below.

> Deferred to a follow-up: "$X.XX spent" badge on Research/Visuals tabs deep-linking to Usage pre-filtered by project_id. Requires project_id state-watching in those tabs — trivial to add once the dashboard is live and we have real numbers to show.

---

## Data Model (Firestore)

**Event** — `users/{uid}/cost_events/{eventId}` (append-only):
```
ts                 Timestamp (serverTimestamp)
day                "YYYY-MM-DD" (UTC)
project_id         string | null
tool               "text"|"image"|"imagen"|"tts"|"veo"
model              string
status             "ok"|"error"|"fallback"|"provisional"|"refund"
retries            int
usage              { in_tokens, out_tokens, cached_tokens, images, video_seconds, tts_chars }
cost_usd           float
pricing_version    string
description        string
op_name            string|null
```

**Daily rollup** — `users/{uid}/cost_rollups/{YYYY-MM-DD}`:
```
day, total_usd, updated_at
by_tool     { text: {calls, cost_usd, in_tokens, out_tokens, cached_tokens}, ... }
by_model    { "<model>": {calls, cost_usd}, ... }
by_project  { "<pid>": {calls, cost_usd}, "_account": {...} }
```

**Pricing config** — `config/gemini_pricing` (single doc):
```
version            ISO8601
text_models        { "<model>": {in_per_1m, out_per_1m, cached_in_per_1m} }
image_models       { "<model>": {per_image} }
tts_models         { "<model>": {per_1k_chars} }
video_models       { "<model>": {per_second} }
fallback           { text: {...}, image: {per_image}, tts: {...}, veo: {...} }
```

## Verification (end-to-end, on staging)

1. Deploy to `content-creation-app-staging`; populate `config/gemini_pricing` via Firestore console.
2. Run a research pipeline — expect 30–72 text events + 1 rollup doc for today.
3. Open Usage tab → KPIs/table/chart populate. Spot-check: sum events via console = rollup `total_usd`.
4. Force image fallback — expect 2 events, first with `status="fallback"`.
5. Start a Veo shot with `duration=6s` — provisional event appears; force failure → refund event with negative cost.
6. Edit `config/gemini_pricing` in console, wait ≤5 min, trigger new call — verify new `pricing_version` on event.
7. `GET /api/usage/trend?days=30` returns ≤30 points in ascending date order.

## Risks / Open Questions

- **Veo billing timing**: SDK returns no usage on `generate_videos`; bill provisionally at submit, refund on poll-failure.
- **Image fallback chain**: produces 2 events per logical generate — UI groups by description.
- **Rollup write amplification**: 72 increments on one doc is under Firestore soft caps; shard only if observed.
- **Stale pricing**: ≤5 min TTL; events stamp `pricing_version` for audit.
- **CLI / non-authed callers**: `uid=None` → `record_usage` no-ops.

## Critical Files

- `execution/pricing.py` — **new**
- `execution/cost_tracker.py` — **new**
- `execution/gemini_client.py` — instrumentation at all call sites
- `execution/research_scriptwriter.py` — thread uid/pid through pipeline
- `execution/server.py` — route wiring + 4 `/api/usage/*` routes
- `ui/index.html` — new Usage tab + Chart.js CDN
- `tests/test_pricing.py`, `tests/test_cost_tracker.py`, `tests/test_gemini_instrumentation.py`, `tests/test_scriptwriter_tracking.py`, `tests/test_usage_routes.py` — **new**
