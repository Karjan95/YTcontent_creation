# Changelog — Narrative Spine

**Date:** 2026-04-26
**Scope:** New intermediate ranking layer between research and script generation. Closes the gap where the entire markdown dossier was dumped verbatim into the script prompt with no ranking, no citation binding, and no story-angle awareness.
**Feature flag:** `NARRATIVE_SPINE=1` (off by default during rollout).

---

## Why

The script-generation prompt at `execution/research_templates.py:1744-1746` was dumping the whole research dossier verbatim and asking Gemini to do four jobs in one pass: rank facts, invent beat structure, write narration, and self-track sources. Five concrete failures lived in the code:

1. The narration JSON's `sources_used` field was non-binding — Gemini frequently omitted it.
2. Beat regeneration truncated the dossier to 4000 chars (`research_templates.py:1843`), so regenerated beats could drift onto different facts than the originals.
3. `build_production_prompt` only received the narration JSON, never the dossier — source traceability vanished before visuals were generated. Director / Storyboard / DP at `research_scriptwriter.py:244-880` had no way to know which research source backed any shot.
4. Short-form presets (micro / quick_take) crammed the full dossier into 30–60 second narration with no ranked claim list to compress against.
5. Empty-dossier failures silently produced hallucinated scripts.

On top of all that, the dossier's "what matters" ranking was generic. A video titled *"How Nuclear Power Saves the Planet"* and a video titled *"The Day Chernobyl Melted Down"* — same dossier, same generic ranking, same brief to Gemini. The angle only influenced prose, not which facts were load-bearing.

---

## What changed

### A new layer: the Narrative Spine

The spine is a ranked, source-bound outline derived from the dossier. It's stored on the project doc as `research_spine` and consumed by every downstream prompt.

```jsonc
{
  "version": 1,
  "topic": "...",
  "key_claims": [
    {
      "id": "k1",                   // 'k' prefix to disambiguate from c1/s1 in research_structured
      "text": "Atomic claim text.",
      "importance": "primary | supporting | color",
      "source_ids": ["s1", "s4"]
    }
  ],
  "logical_flow": ["k1", "k4", "k2"],   // narrative order; ⊆ key_claims ids
  "source_map": {
    "s1": {"url": "...", "title": "...", "publisher": "", "quote": ""}
  },
  "extracted_at": "ISO8601",
  "edited_by_user": false,
  "reranked_for": {"title": "...", "audience": "...", "tone": "...", "format_preset": "..."}
}
```

Persistence is additive — every downstream prompt accepts `spine=None` and reverts to legacy behavior, so existing projects keep working without migration.

### Phase 1 — Extraction

- `execution/research_templates.py` — new `build_spine_extraction_prompt()` and `_format_spine_block()` mirror the structured-research patterns at `_format_structured_claims_block` (line 1377).
- `execution/research_scriptwriter.py` — new `extract_narrative_spine()` calls Gemini 2.5 Flash, parses the spine, and validates id integrity (drops dangling `source_ids` and flow ids that don't exist in `key_claims`).
- `execution/server.py` — new flag `NARRATIVE_SPINE_ENABLED`, helper `_load_project_spine()`, two routes `POST /api/research/spine` (extract) and `PUT /api/research/spine` (save user edits, server-side schema validation), and auto-extract hooks in both research routes (`/api/research`, `/api/research/poll`).

### Phase 2 — Script generation consumes the spine

- `build_script_prompt()` injects a `NARRATIVE SPINE` block between the structured-claims block and the style guide. Each beat is bound to spine `claim_ids` via a new schema field. The loose `sources_used` field is replaced with a derived `claim_ids_used`.
- `_sanitize_narration_claim_ids()` runs after Gemini returns: drops any beat `claim_ids` not in the spine, recomputes `claim_ids_used`, leaves beats with zero valid ids in place (UI renders them as *"no source"*).

### Phase 3 — Beat regeneration anchors to the spine

- `build_beat_regeneration_prompt()` accepts `spine=`. When present, the legacy 4000-char dossier truncation is dropped entirely — the spine block becomes the source of truth, eliminating fact drift.
- `regenerate_beats()` captures the originals' `claim_ids` before the call. **Restyle mode** enforces set-equality: if the regenerated beats drift onto different ids, one tighter retry; second failure accepts with a warning. **Reimagine mode** allows different facts but still strips claim ids that don't exist in the spine.

### Phase 4 — Production pipeline carries `claim_id` to every shot

- `build_production_prompt()` and `build_director_prompt()` accept `spine=`. Per-beat narration lines gain a `[Claims: k1, k4]` tag, the full SPINE REFERENCE block is appended near the visual style section, and the output schema gains `"claim_id": "k1"` per shot.
- New `CRITICAL RULE`: every shot must inherit a single best-fit `claim_id` from its parent beat's `claim_ids`.
- Downstream phases (Cinematographer, Storyboard, Continuity, DP) already carry `CARRY FORWARD every field` rules, so `claim_id` propagates through the 6-phase chain without per-phase prompt changes.
- `generate_production_table`, `_generate_single_batch_3phase`, `_generate_single_batch_6phase` all forward `spine`. `/api/generate-production-table` loads it via `_load_project_spine`.

### Angle-aware rerank — closes the generic-ranking gap

After extraction, the spine is ranked generically. When the user picks a title (and optionally audience/tone), a cheap second pass re-ranks the *same* claims for *that* angle:

- New prompt `build_spine_rerank_prompt()`. The set of claims is fixed — only `importance` and `logical_flow` change. Re-rank metadata is stored on the spine as `reranked_for: {title, audience, tone, format_preset}`.
- New function `rerank_narrative_spine()`. On any failure, the original spine is returned unchanged so callers never lose data.
- New route `POST /api/research/spine/rerank`.

### AI-suggested edits — for users who don't know how to direct

A "narrative coach" pass that proposes 0–5 targeted improvements with rationales:

- New prompt `build_spine_suggest_edits_prompt()` and function `suggest_spine_edits()`. Each suggestion is one of `reorder | importance | edit_text` with a one-sentence rationale. Server-side validation strips suggestions referencing unknown ids, invalid kinds, or invalid importance values. Capped at 5.
- New route `POST /api/research/spine/suggest-edits`. Suggestions are NOT applied — the UI shows them with Apply/Reject controls per suggestion.

### UI — collapsed by default, plain-English, with feedback

The original editor exposed implementation details (drag handles, `k3` ids, importance dropdown) to users who aren't directors. Replaced with a friendlier surface:

- **Collapsed by default.** One-line summary row: *"AI organized N facts into a story arc with M lead claims. Open to review ▾"*. Most users never click. Power users do.
- **Plain-English chips.** Beat chips show the first ~5 words of the claim (*"Steam spins turbines…"*) instead of `k3`. Full text + sources still on hover. The k-prefixed ids are for the AI, not the user.
- **"Ask AI to suggest changes" button.** Calls `/api/research/spine/suggest-edits` and renders suggestions like *"Move 'Steam spins turbines' to position 1 — Stronger hook for this title."* with Apply / Reject buttons per suggestion.
- **Auto-rerank on title selection.** When the user clicks a title in the suggestions list, `/api/research/spine/rerank` fires. Two visible toasts: *"Re-ranking story arc for this title…"* → *"Story arc tuned for this title ✓"*. Respects manual edits — if `edited_by_user: true`, skips the auto-rerank with a notice rather than overwriting.
- **App-wide `showToast()` primitive.** Reusable from any feature.

---

## Files modified

| File | Changes |
|---|---|
| `execution/research_templates.py` | New: `_format_spine_block`, `build_spine_extraction_prompt`, `build_spine_rerank_prompt`, `build_spine_suggest_edits_prompt`. Extended: `build_script_prompt`, `build_beat_regeneration_prompt`, `build_production_prompt`, `build_director_prompt` to consume `spine=`. |
| `execution/research_scriptwriter.py` | New: `extract_narrative_spine`, `_validate_spine`, `_now_iso`, `_sanitize_narration_claim_ids`, `_claim_ids_match`, `rerank_narrative_spine`, `suggest_spine_edits`. Extended: `generate_narration`, `regenerate_beats`, `generate_production_table`, both `_generate_single_batch_*` to forward `spine=`. |
| `execution/server.py` | New flag `NARRATIVE_SPINE_ENABLED`, helper `_load_project_spine`, validator `_validate_spine_edit`. New routes: `POST /api/research/spine`, `PUT /api/research/spine`, `POST /api/research/spine/rerank`, `POST /api/research/spine/suggest-edits`. Auto-extract hooks in `/api/research` (sync) and `/api/research/poll` (deep). Spine load in `/api/generate-script`, `/api/regenerate-beat`, `/api/generate-production-table`. |
| `ui/index.html` | Spine editor surface in research tab (collapsed default + summary), claim-coverage chips on every beat in the script tab, AI-suggest panel, auto-rerank on title selection, toast primitive, hydration from `project.research_spine`. New CSS for chips, suggestion panel, toast. |
| `tests/test_narrative_spine.py` | New file. 36 tests covering: extractor happy path / parse errors / empty dossier / dangling ids / structured-bootstrap; format spine block; PUT validator; script prompt with/without spine; claim-id sanitization; regen prompt with/without spine; restyle equality + retry; reimagine sanitization; production / director prompts with/without spine; **end-to-end test pinning the contract** (claim id `k3` survives research → narration → regen → director); rerank preservation, parse-error recovery, dangling id stripping, no-spine error; suggest-edits happy path, invalid-suggestion stripping, 5-suggestion cap. |

---

## Rollout & cost

- **Flag-gated soft launch.** With `NARRATIVE_SPINE=0` (default) every prompt builder accepts `spine=None` and behaves identically to the previous release. Enable in `deploy_staging.sh` first to dogfood, then promote.
- **Cost.** One Gemini Flash call at extraction time (~3–6k input + ~1k output ≈ $0.003–0.006). One additional Flash call per title selection for the rerank, and one more if the user clicks "Ask AI to suggest". All trivial against the multi-call production pipeline. No per-beat or per-shot overhead.
- **Cost tracking.** Each spine call is labeled in `cost_tracker` with descriptions `extract_narrative_spine`, `rerank_narrative_spine`, `suggest_spine_edits`, so per-feature ROI is visible in the existing dashboard.

---

## Failure modes

| Failure | Behavior |
|---|---|
| Spine extraction returns invalid JSON or empty | Persist `research_spine: null`, surface yellow UI banner *"Spine unavailable — falling back to legacy script generation."*, script-gen falls back to legacy path. User has a Retry button. |
| Empty dossier | Extractor short-circuits and returns an error before calling Gemini. |
| Gemini omits `claim_ids` on a beat | Server-side accept-with-warning, render *"no source"* chip in the UI. Do NOT auto-retry the full script (too expensive). User can target a beat regen. |
| Beat regen breaks claim-id equality (restyle) | One retry with a tighter STRICT system message. Second failure accepts with warning. |
| Rerank parse error or empty response | Original spine returned unchanged; UI shows *"Couldn't re-rank story arc"* toast. |
| User has manually edited the spine, then picks a title | Auto-rerank is skipped with a friendly notice — manual edits are never silently overwritten. |
| `NARRATIVE_SPINE=0` on the server | All four routes return 403; UI surfaces a one-line info banner; everything else proceeds via the legacy path. |

---

## Verification

- **Unit:** `pytest tests/test_narrative_spine.py -v` — 36 passing. The headline E2E test `test_e2e_claim_id_survives_research_to_production` pins the contract that future refactors must preserve.
- **No regressions:** Full backend suite passes (90/90 excluding the pre-existing playwright fixture in `test_ui_workflows.py`).
- **Manual (staging, `NARRATIVE_SPINE=1`):**
  1. Create project, run research on a known topic.
  2. Confirm the 🦴 collapsed summary row appears in the research tab; click to expand the editor.
  3. Pick a title from suggestions → toasts appear: *"Re-ranking story arc for this title…"* → *"Story arc tuned for this title ✓"*. Open the editor; the order/importance reflects the chosen angle.
  4. Click *"Ask AI to suggest changes"* → 0–5 suggestions render with Apply/Reject. Apply one → Save Spine.
  5. Generate script → every beat shows a claim chip with first-5-words text; hover shows full claim + source URLs. Beats with no anchor render the red *"no source"* chip.
  6. Restyle a beat → chip stays the same (id-equality). Reimagine → chip can change but still resolves to a real spine claim.
  7. Generate production table → inspect Firestore: each shot has a `claim_id` from its parent beat.
  8. Toggle `NARRATIVE_SPINE=0`, regenerate → identical legacy behavior; no chips; no toasts; no editor.
- **Cost:** check `cost_tracker` per-project breakdown — spine calls show as labeled rows ≈ $0.005 each.
