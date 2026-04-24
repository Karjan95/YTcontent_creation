# Cost Dashboard — Live Per-User / Per-Project Gemini Spend Tracking — 2026-04-24

## Summary
Introduced end-to-end live cost tracking for every billable Gemini call (text, image, Imagen, TTS, Veo) with a Usage tab that shows account-wide totals, a daily-spend trend chart, and per-project / per-tool breakdowns. Token usage is captured straight from `response.usage_metadata` so multi-image prompts and cached-input reuse are billed correctly at call time. Rates live in a Firestore doc with a 5-minute cache so Google-side price changes are a single-doc edit.

Branch: `claude/brainstorm-app-improvements-TCNK5`
Commits: `086fdee` (feature), `43ade9c` (pricing seed)

---

## What Changed for Users

- **New "Usage" tab** in the top nav, beside Kie Studio.
- **Header KPIs**: Today / Month-to-date / Last 30 days total spend.
- **Date range picker** with 7 / 30 / 90-day presets.
- **Trend chart**: stacked daily bars colored by tool (text / image / imagen / tts / veo).
- **By-tool donut**: percentage of spend per tool for the selected range.
- **By-project table**: calls, cost, and % of total per project, sorted by cost.
- **Banner note**: tracking starts the day the feature deploys — earlier spend is invisible because `usage_metadata` can't be backfilled.

---

## Architecture

### New modules

#### `execution/pricing.py`
- Loads `config/gemini_pricing` Firestore doc with 5-minute TTL in-memory cache (thread-safe).
- Ships with a `_DEFAULT_PRICING` constant containing real April-2026 Google rates (sourced from ai.google.dev, OpenRouter, Google blog) so tests / CLI / first-deploy work without a seeded Firestore doc.
- `get_rate(tool, model)` returns `(rate_dict, is_fallback)` — callers stamp `status="fallback"` on the event when an unknown model is encountered.
- `get_pricing_version()` returns the stamp written on every event for audit.

#### `execution/cost_tracker.py`
- `get_cost(tool, model, usage)` → `(usd, pricing_version, is_fallback)`. Text: (prompt − cached) × in_rate + cached × cached_rate + out × out_rate. Image/Imagen: images × per_image. TTS: chars × per_1k. Veo: seconds × per_second.
- `record_usage(uid, project_id, tool, model, usage, retries, status, description, op_name, cost_override)` writes an event doc + daily-rollup increments in a single `db.batch()`, dispatched via a 4-worker `ThreadPoolExecutor` so request latency is unchanged.
- Graceful `uid=None` no-op (CLI path) — doesn't pollute production data.
- Per-tool helpers: `track_text`, `track_image`, `track_imagen`, `track_tts`, `track_veo`, `track_veo_refund`.

### Instrumentation

#### `execution/gemini_client.py`
- `generate_content()`: added `uid`, `project_id`, `description` kwargs; always retains the `response` object so `usage_metadata` can be read; calls `track_text` before returning `.text`.
- `_generate_with_gemini_model` / `_generate_with_imagen_model` / `generate_image_content`: uid/pid threaded; emits one event per attempted model so fallback chains (Gemini → Imagen) are visible.
- `analyze_style_from_images`, `analyze_style_from_text`, `expand_creative_direction`, `refine_creative_direction`: accept uid/pid and call `track_text`.
- `generate_tts`: accepts uid/pid and calls `track_tts(..., len(prompt), ...)`.
- `generate_scene_image`, `edit_scene_image`: uid/pid threaded; tracking per scene.
- `start_video_generation`: uid/pid threaded; bills provisionally at submit (`status="provisional"`). `_video_operations[op_name]` upgraded from a bare operation to a dict carrying `{operation, uid, project_id, duration, model, scene_id}` so polling has the billing context.
- `poll_video_generation`: on safety-block or exception, emits `track_veo_refund` — negative-cost event that offsets the provisional charge.

#### `execution/research_scriptwriter.py`
- `uid`, `project_id` threaded through every pipeline-entry function: `generate_narration`, `auto_suggest_tone`, `regenerate_beats`, `generate_production_table`, `_generate_single_batch`, `_generate_single_batch_3phase`, `_generate_single_batch_6phase`, `_planner_expand_subqueries`, `_run_sub_researcher`, `run_structured_research`, `structure_from_blob`.
- Every `generate_content(...)` call now forwards uid/pid and stamps a stage label (`narration`, `director_6phase`, `cinematographer_6phase`, `storyboard_6phase`, `continuity_6phase`, `dp_6phase`, `script_doctor`, `research_planner`, `sub_researcher(<section>)`, `structure_from_blob`, `regenerate_beats`, `auto_suggest_tone`). Events are self-describing when browsing the drilldown.

#### `execution/server.py`
- `uid=g.uid, project_id=data.get('project_id')` now passed on every call site: `/api/generate-image`, `/api/generate-tts`, `/api/analyze-style-images`, `/api/analyze-style-text`, `/api/structure-script`, `/api/suggest-cast`, `/api/generate-cast-portrait`, `/api/generate-cast-portraits-batch`, `/api/expand-creative-direction`, `/api/refine-creative-direction`, `/api/research` + fallback + structured pipeline, `/api/deep-research/poll` blob-extraction, `/api/suggest-titles`, `/api/auto-suggest-tone`, `/api/generate-script`, `/api/regenerate-beat`, `/api/generate-production-table`, `/api/visuals/generate-image`, `/api/visuals/edit-image`, `/api/visuals/generate-batch-images`, `/api/visuals/start-animation`, `/api/visuals/start-batch-animation`.

### New API Routes

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/usage/account?start=&end=` | Account-wide totals across the range, merged `by_tool` / `by_project` / `by_model`. |
| `GET` | `/api/usage/trend?days=30` (or explicit `start`/`end`) | Ordered daily series for the stacked chart. Zero-fills missing days so the chart has no gaps. |
| `GET` | `/api/usage/project/<pid>?start=&end=` | Per-project totals + last 100 events for the drilldown. |
| `GET` | `/api/admin/pricing` | Read-only view of the current pricing doc. Gated by `ADMIN_UIDS` env. |

All routes are `@require_auth` and rate-limited to 600/hr (60/hr for admin).

Date-range defaults: end = today, start = today − 30d. Range is capped at 366 days.

### Frontend

- Added Chart.js 4.4.1 via CDN in `<head>` (~70KB gz). Rationale: stacked bars + hover tooltips + legends via custom SVG would be ~300 LOC; Chart.js pays for itself on first hover.
- New `#tab-usage` panel with KPI row, date picker, trend canvas, donut canvas, project table.
- JavaScript: `loadUsageDashboard()`, `setUsagePreset(days)`, `_renderUsageTrend()`, `_renderUsageToolDonut()`, `_renderUsageProjectTable()`. Reuses existing `authFetch()`.
- `ui/style.css`: minimal `.usage-kpi` styling.

---

## Firestore Schema

### Per-call events (append-only)
Path: `users/{uid}/cost_events/{autoId}`
```
ts              Timestamp (serverTimestamp)
day             "YYYY-MM-DD" (UTC)
project_id      string | null
tool            "text" | "image" | "imagen" | "tts" | "veo"
model           string
status          "ok" | "error" | "fallback" | "provisional" | "refund"
retries         int
usage           { in_tokens, out_tokens, cached_tokens,
                  images, tts_chars, video_seconds }
cost_usd        float
pricing_version string
description     string   # e.g. "director_6phase"
op_name         string   # set for Veo to correlate submit+refund
```

### Daily rollups (for fast dashboard reads)
Path: `users/{uid}/cost_rollups/{YYYY-MM-DD}` — updated via `Increment` dot-paths in the same batch as the event write:
```
day, total_usd, updated_at
by_tool      { text: {calls, cost_usd, in_tokens, out_tokens, cached_tokens}, ... }
by_model     { "<model>": {calls, cost_usd}, ... }
by_project   { "<pid>": {calls, cost_usd}, "_account": {...} }
```

### Pricing config (editable without redeploy)
Path: `config/gemini_pricing`
```
version            ISO8601 or semver-ish tag
text_models        { "<model>": {in_per_1m, out_per_1m, cached_in_per_1m}, ... }
image_models       { "<model>": {per_image}, ... }
tts_models         { "<model>": {per_1k_chars}, ... }
video_models       { "<model>": {per_second}, ... }
fallback           { text: {...}, image: {per_image}, tts: {...}, veo: {...} }
```

---

## Seeded Default Rates (April 2026)

| Model | Input / 1M | Output / 1M | Cached / 1M |
|-------|-----------|-------------|-------------|
| gemini-3-pro-preview | $2.00 | $12.00 | $0.50 |
| gemini-3.1-pro-preview | $2.00 | $12.00 | $0.50 |
| gemini-3-flash-preview | $0.50 | $3.00 | $0.05 |
| gemini-2.5-pro | $1.25 | $10.00 | $0.31 |
| gemini-2.5-flash | $0.30 | $2.50 | $0.075 |

| Image Model | Per image |
|-------------|-----------|
| gemini-3-pro-image-preview | $0.134 (2K tier) |
| gemini-2.5-flash-image | $0.039 |
| imagen-4.0-fast-generate-001 | $0.02 |
| imagen-4.0-generate-001 | $0.04 |
| imagen-4.0-ultra-generate-001 | $0.06 |

| Veo Model | Per second |
|-----------|-----------|
| veo-3.1-generate-preview | $0.40 |
| veo-3.1-fast-generate-preview | $0.10 (post Apr 7 2026 drop) |
| veo-3.1-lite-generate-preview | $0.05 |

| TTS Model | Per 1K chars |
|-----------|-------------|
| gemini-2.5-flash-preview-tts | $0.010 (rough proxy for audio-token billing) |

### Known rate caveats (documented in `pricing.py`)
1. **Gemini 3 Pro context tiers** — the default charges the ≤200K tier. Above 200K the true rate is $4.00 / $18.00. Prompts regularly exceeding 200K will under-bill unless the Firestore doc is customized.
2. **Gemini 3 Pro Image 4K** — default is the 2K rate ($0.134). 4K generation is $0.24/image; override in Firestore if you move to 4K.
3. **TTS per_1k_chars** — Google bills TTS by audio-output tokens, not input characters. The $0.010 default is a rough conversion based on ~4 output tokens per English character. Calibrate against actual invoices for precision.

---

## Testing

38 new tests across 5 files, all passing:

- `tests/test_pricing.py` (11) — rate lookup for every tool, fallback on unknown model, cache TTL, force refresh, post-April-drop Veo rates, Gemini 3 Pro ≤200K tier assertion.
- `tests/test_cost_tracker.py` (11) — cost math per tool, cached-token subtraction, event + rollup batch writes with `merge=True` and `Increment` dot-paths, `uid=None` no-op, Veo refund.
- `tests/test_gemini_instrumentation.py` (8) — token capture from `usage_metadata`, retry counting, image/imagen per-image billing, TTS char count, Veo provisional + refund on failure.
- `tests/test_scriptwriter_tracking.py` (4) — uid/project_id + stage descriptions forwarded through narration / tone / 6-phase pipeline / regenerate_beats.
- `tests/test_usage_routes.py` (6) — account sums, trend zero-fills gaps, date validation, reversed-range rejection, `ADMIN_UIDS` gating.

Pre-existing `tests/test_api_workflows.py` still passes — no regression. Total offline-safe suite: 45/45.

---

## Files Changed

### New
- `execution/pricing.py`
- `execution/cost_tracker.py`
- `tests/test_pricing.py`
- `tests/test_cost_tracker.py`
- `tests/test_gemini_instrumentation.py`
- `tests/test_scriptwriter_tracking.py`
- `tests/test_usage_routes.py`
- `docs/cost_dashboard_plan.md` (progress tracker with phase checkboxes)
- `docs/changelog_cost_dashboard_2026_04_24.md` (this file)

### Modified
- `execution/gemini_client.py`
- `execution/research_scriptwriter.py`
- `execution/server.py`
- `ui/index.html`
- `ui/style.css`

---

## Operator Checklist

Before the dashboard reflects real numbers in production:

1. Deploy the branch — `./deploy.sh` or `./deploy_staging.sh`.
2. (Optional) Seed `config/gemini_pricing` in the Firestore console. If you skip this step, `_DEFAULT_PRICING` is used and every event stamps `pricing_version="2026-04-defaults"` so you can tell which rates were applied.
3. (Optional) Set `ADMIN_UIDS` env var to enable the `/api/admin/pricing` read endpoint.
4. Run any generation — the first event creates today's rollup doc automatically.
5. Open the Usage tab — KPIs, chart, and tables populate.

Tracking is live from deploy time forward; historical spend is not recoverable because the Gemini API does not include billing metadata in responses.
