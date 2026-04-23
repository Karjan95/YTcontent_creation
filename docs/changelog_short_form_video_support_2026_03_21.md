# Changelog: Short-Form Video Support (Micro & Quick Take)

**Date:** 2026-03-21

---

## Feature: Adaptive Short-Form Video Presets

**Problem:** The platform treated all video durations (1-60 min) identically — same multi-act template structures, same default pacing, same shot estimation. A 1-minute video was forced into a 4-act, 17-beat structure. Shot count math produced 50+ shots for a 3-minute video. No templates were optimized for TikTok/Reels/YouTube Shorts pacing.

**Solution:** Two new format presets with adaptive template structures, auto-pacing, and shot count capping.

### New Format Presets

| Preset | Duration | Pacing Tier | Shot Range | Use Case |
|--------|----------|-------------|------------|----------|
| 🎯 Micro | 30-60 sec | High Energy | 4-8 shots | TikTok, Reels, Shorts |
| ⚡ Quick Take | 1-3 min | High Energy | 8-20 shots | Punchy explainers, hot takes |
| 📱 Short Form | 5-7 min | Standard | 20-40 shots | *(existing, now with shot range)* |
| 📺 Standard | 10-12 min | Standard | No cap | *(existing, unchanged)* |
| 📖 Deep Dive | 18-22 min | Relaxed | No cap | *(existing, unchanged)* |

Each preset now includes `auto_pacing_tier` and `shot_range` fields for downstream consumption.

---

## Feature: Adaptive Template Structures

**Problem:** All 7 templates (General Deep Dive, Investigative Expose, Educational Explainer, Product/Tech Review, Personal Story, Trending News, Political Deep Dive) had fixed multi-act structures designed for 10+ minute content. A 1-minute video splitting into 4 acts with 17 beats is unusable.

**Solution:** Each template now defines `short_structures` with domain-specific `micro` (1 act, 3 beats) and `quick_take` (2-3 acts, 5-7 beats) variants alongside the existing full structure. A new helper function `_resolve_structure_for_duration()` picks the right structure at runtime.

### Structure Summary Per Template

| Template | Micro (3 beats) | Quick Take (5-7 beats) |
|----------|-----------------|----------------------|
| General Deep Dive | Hook → Core Insight → Payoff | Hook + Stakes → Core + Evidence + Nuance → Takeaway + Closer |
| Investigative Expose | The Crime → The Proof → The Punchline | Scandal + Villain → Mechanism + Human Cost + Systemic Failure → Aftermath + Warning |
| Educational Explainer | The Myth → The Truth → The Mind-Blow | Illusion + Promise → Analogy + Mechanism + Surprise → Application + Mind-Bender |
| Product/Tech Review | Verdict → Reason → Caveat | Verdict + Context → Best + Worst + Competitor → Perfect Buyer + Skip |
| Personal Story | The Moment → The Choice → The Legacy | In Media Res + Setup → Turning Point + Lowest Point + Decision → Outcome + Lesson |
| Trending News | What Happened → Why It Matters → The Take | Explosive Opener + Stakes → Backstory + Argument + Counter → Prediction + Provocation |
| Political Deep Dive | The Fact → The Money → The Objective Truth | Cold Open + Stakes → Reality + Money Trail + Steelman → Next Steps + Neutral Truth |

### Structure Resolution Logic

```
format_preset = "micro"    → use short_structures["micro"]
format_preset = "quick_take" → use short_structures["quick_take"]
format_preset = "standard"  → use full story_structure
format_preset = "custom", duration ≤ 1  → fallback to micro
format_preset = "custom", duration ≤ 3  → fallback to quick_take
format_preset = "custom", duration > 3  → full structure
```

**File:** `execution/research_templates.py` — `_resolve_structure_for_duration()`

---

## Feature: Short-Form Constraints in Narration Prompt

**Problem:** Even with a low word count target (150 words for 1 min), Gemini would still generate multi-paragraph beats and gradual context-building because the prompt structure assumed long-form content.

**Solution:** When `format_preset` is `micro` or `quick_take`, a SHORT-FORM CONSTRAINTS block is injected into the narration prompt:

- Each beat = 1-3 sentences MAX
- No transitions between beats — jump-cut from idea to idea
- Start with the payoff, then explain (not the reverse)
- Hook must land in the FIRST sentence
- Strict word count enforcement
- Micro-specific: "Write like a social media post that became a voiceover"

**File:** `execution/research_templates.py` — `build_script_prompt()`

---

## Feature: Shot Count Capping in Production Prompt

**Problem:** A 3-minute video at Standard pacing would estimate ~50 shots (450 words ÷ 9 words/shot), which is absurd for short content.

**Solution:** `build_production_prompt` and `build_director_prompt` now accept `format_preset` and apply shot range capping:

- **Micro:** 4-8 shots, prefer 4s durations, 1 beat = 1-2 shots max
- **Quick Take:** 8-20 shots, mix 4s/6s durations, 1 beat = 2-3 shots max
- **Short Form:** 20-40 shots

A `⚠️ SHORT-FORM VIDEO — SHOT COUNT IS CRITICAL` block is injected into the prompt for micro/quick_take presets.

**Files:** `execution/research_templates.py` — `build_production_prompt()`, `build_director_prompt()`

---

## Feature: Auto Pacing Tier Selection

**Problem:** The format preset (which determines duration and pacing intent) was disconnected from the pacing tier (which controls shots-per-second in production). Users selecting "Micro" would still get "Standard" pacing (3-4s per shot) unless they manually changed it.

**Solution:** Two-level auto-selection:

1. **Frontend:** `onFormatPresetChange()` auto-selects the pacing tier dropdown when the format preset changes
2. **Backend:** `generate_production_table()` auto-overrides pacing tier from `FORMAT_PRESETS.auto_pacing_tier` if the user hasn't explicitly changed it from the default

| Preset | Auto Pacing Tier |
|--------|-----------------|
| Micro | High Energy (~2s/shot) |
| Quick Take | High Energy (~2s/shot) |
| Short Form | Standard (~3-4s/shot) |
| Standard | Standard (~3-4s/shot) |
| Deep Dive | Relaxed (~4-6s/shot) |

**Files:** `ui/index.html` — `onFormatPresetChange()`, `execution/research_scriptwriter.py` — `generate_production_table()`

---

## Improvement: Updated Pacing Guides

Each template's `pacing_guide` now includes entries for durations 1 and 2 minutes:

| Template | 1 min | 2 min | 5 min | 10 min |
|----------|-------|-------|-------|--------|
| General Deep Dive | 15 | 30 | 70 | 140 |
| Investigative Expose | 15 | 35 | 75 | 150 |
| Educational Explainer | 12 | 25 | 60 | 120 |
| Product/Tech Review | 12 | 25 | 60 | 130 |
| Personal Story | 13 | 28 | 65 | 130 |
| Trending News | 15 | 32 | 80 | 160 |
| Political Deep Dive | 15 | 32 | 75 | 150 |

**File:** `execution/research_templates.py` — each template's `pacing_guide`

---

## Frontend: New Dropdown Options

The Video Format dropdown now includes Micro and Quick Take:

```
🎯 Micro (30-60 sec)
⚡ Quick Take (1-3 min)
📱 Short Form (5-7 min)      ← icon updated from ⚡ to 📱
📺 Standard (10-12 min)      ← default
📖 Deep Dive (18-22 min)
🔢 Custom
```

`getSelectedDuration()` updated to map `micro: 1`, `quick_take: 2`.

Production table request body now includes `format_preset` field.

**File:** `ui/index.html`

---

## `format_preset` Threading

The `format_preset` value is now threaded end-to-end through the entire production pipeline:

```
Frontend (dropdown)
  → POST /api/generate-production-table { format_preset: "micro" }
    → server.py: generate_production_table_route()
      → research_scriptwriter.py: generate_production_table()
        → auto-pacing tier resolution
        → _generate_single_batch() or _generate_single_batch_3phase()
          → research_templates.py: build_production_prompt(format_preset=...)
          → research_templates.py: build_director_prompt(format_preset=...)
            → shot count capping + short-form cutting instructions
```

**Files:** `execution/server.py`, `execution/research_scriptwriter.py`, `execution/research_templates.py`

---

## Backward Compatibility

- Existing presets (`short_form`, `standard`, `deep_dive`, `custom`) are fully preserved
- New fields (`auto_pacing_tier`, `shot_range`) are additive — existing code ignores unknown keys
- `format_preset` defaults to `""` throughout — no behavior change when not provided
- Auto-pacing only overrides if pacing tier is still at default ("Standard")
- Existing projects load and render correctly

---

## Files Changed Summary

| File | Changes |
|------|---------|
| `execution/research_templates.py` | New FORMAT_PRESETS (micro, quick_take), `_resolve_structure_for_duration()`, `short_structures` on all 7 templates, pacing_guide updates, short-form constraints in `build_script_prompt`, shot capping in `build_production_prompt` and `build_director_prompt` |
| `execution/research_scriptwriter.py` | `format_preset` param on `generate_production_table`, `_generate_single_batch`, `_generate_single_batch_3phase`; auto-pacing tier resolution |
| `execution/server.py` | Extract and pass `format_preset` in production table route |
| `ui/index.html` | New dropdown options, `getSelectedDuration` mapping, auto-pacing in `onFormatPresetChange`, `format_preset` in production request body |
