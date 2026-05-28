"""
Agentic prompt builders for the 5-stage production pipeline.

Each stage prompt follows the same structure:

    [PERSONA]     — who you are, your craft, your experience
    [BRIEF]       — read the bible, internalize it before deciding
    [PRINCIPLES]  — make CHOICES with REASONS; commit to a vocabulary;
                    build on prior decisions
    [CONTEXT]     — the production bible markdown so far
    [USER FEEDBACK] — only when regenerating
    [OUTPUT]      — schema-pointed, no template fill-ins

The schema enforces JSON shape. The prompt is a brief, not a form.
"""

import json
from typing import Any

from agentic_schemas import (
    Stage1Treatment, Stage2WorldDesign, Stage3Cinematography,
    Stage4ShotList, Stage5ContinuityBrief, Stage6Final,
    STAGE_LABELS, STAGE_NAMES,
)

# Backwards-compat alias for any caller still importing Stage5Final from here.
Stage5Final = Stage6Final


# ──────────────────────────────────────────────────────────────────────
# Bible composer + per-stage section renderers
# ──────────────────────────────────────────────────────────────────────

def _compose_bible(stages: list[dict], project_title: str = "") -> str:
    """Concatenate completed stages' bible_sections into one markdown doc.

    Stages should be passed in stage_number order (1..5). Stages with
    status 'pending' or 'stale' or 'error' are skipped — only the
    finished prose makes it into the bible the next stage reads.
    """
    title = (project_title or "Untitled").strip()
    parts = [f"# Production Bible — {title}\n"]
    skip_statuses = {"pending", "stale", "error", "running"}
    for s in sorted(stages, key=lambda x: x.get("stage_number", 0)):
        if s.get("status") in skip_statuses:
            continue
        section = (s.get("bible_section") or "").strip()
        if section:
            parts.append(section)
            parts.append("")  # blank line between sections
    return "\n".join(parts).rstrip() + "\n"


def render_stage1_bible(output: dict) -> str:
    arc_lines = []
    for m in (output.get("emotional_arc") or []):
        arc_lines.append(
            f"- **{m.get('act', '')} · {m.get('beat_ref', '')}**: "
            f"{m.get('emotional_state', '')} — {m.get('transition_note', '')}"
        )
    scene_lines = []
    for s in (output.get("scene_treatments") or []):
        beat_refs = ", ".join(s.get("beat_refs") or [])
        scene_lines.append(
            f"### Scene {s.get('scene_id', '')} ({beat_refs})\n"
            f"{s.get('treatment', '')}\n\n"
            f"*Performance note:* {s.get('performance_note', '')}"
        )
    refs = "\n".join(f"- {r}" for r in (output.get("tonal_references") or []))
    return (
        f"## Stage 1 — Story Treatment\n\n"
        f"**Logline:** {output.get('logline', '')}\n\n"
        f"**Theme:** {output.get('theme', '')}\n\n"
        f"### Emotional Arc\n"
        + ("\n".join(arc_lines) if arc_lines else "_(no arc moments)_")
        + "\n\n### Scene Treatments\n\n"
        + ("\n\n".join(scene_lines) if scene_lines else "_(no treatments)_")
        + "\n\n### Performance Notes\n"
        + (output.get("performance_notes") or "_(none)_")
        + "\n\n### Tonal References\n"
        + (refs if refs else "_(none)_")
    )


def render_stage2_bible(output: dict) -> str:
    palette = []
    for c in (output.get("color_palette") or []):
        palette.append(
            f"- **{c.get('name', '')}** `{c.get('hex', '')}` "
            f"({c.get('dominance_pct', 0)}%): {c.get('when_dominant', '')}"
        )
    return (
        f"## Stage 2 — World & Design\n\n"
        f"**Rendering style (canonical aesthetic — echo verbatim in every prompt):** "
        f"{output.get('rendering_style', '')}\n\n"
        f"**World setting:** {output.get('world_setting', '')}\n\n"
        f"**Era:** {output.get('era', '')}\n\n"
        f"### Color Palette\n"
        + ("\n".join(palette) if palette else "_(no palette)_")
        + "\n\n**Texture vocabulary:** "
        + ", ".join(output.get("texture_vocabulary") or [])
        + "\n\n**Recurring motifs:** "
        + ", ".join(output.get("recurring_motifs") or [])
        + f"\n\n### Props & Environment\n{output.get('props_and_environment', '')}\n\n"
        + f"### Lighting Rules\n{output.get('lighting_rules', '')}"
    )


def render_stage3_bible(output: dict) -> str:
    lighting = []
    for L in (output.get("lighting_per_scene") or []):
        lighting.append(
            f"- **Scene {L.get('scene_id', '')}**: "
            f"key:fill {L.get('key_to_fill', '')}, "
            f"color {L.get('color', '')}, "
            f"motivation {L.get('motivation', '')}, "
            f"mood {L.get('mood', '')}"
        )
    mood = []
    for m in (output.get("mood_escalation") or []):
        mood.append(
            f"- Beat {m.get('beat_ref', '')} · intensity {m.get('intensity', 0)}/10 · "
            f"{m.get('visual_signal', '')}"
        )
    refs = "\n".join(f"- {r}" for r in (output.get("canonical_references") or []))
    return (
        f"## Stage 3 — Cinematography Plan\n\n"
        f"### Lens Vocabulary\n{output.get('lens_vocabulary', '')}\n\n"
        f"### Movement Language\n{output.get('movement_language', '')}\n\n"
        f"### Lighting Per Scene\n"
        + ("\n".join(lighting) if lighting else "_(none)_")
        + "\n\n### Mood Escalation\n"
        + ("\n".join(mood) if mood else "_(none)_")
        + "\n\n### Canonical References\n"
        + (refs if refs else "_(none)_")
    )


def render_stage4_bible(output: dict) -> str:
    shots = output.get("shots") or []
    count = len(shots)
    summary_lines = []
    # Render first 5 + last 2 as a sample so the bible doesn't bloat.
    sample = (shots[:5] + (["..."] + shots[-2:] if count > 7 else [])) if count > 7 else shots
    for s in sample:
        if s == "...":
            summary_lines.append(f"\n_(... {count - 7} shots omitted ...)_\n")
            continue
        summary_lines.append(
            f"**Shot {s.get('shot_number', '?')}** ({s.get('timestamp', '')}, "
            f"{s.get('duration', '')}s) — beat {s.get('beat_ref', '')}\n"
            f"  *Intent:* {s.get('directors_intent', '')}\n"
            f"  *Subject:* {s.get('subject', '')} — {s.get('action', '')}\n"
            f"  *Camera:* {s.get('camera_move', '')} / {s.get('lens', '')} / {s.get('angle', '')}"
        )
    return (
        f"## Stage 4 — Shot List ({count} shots)\n\n"
        + ("\n\n".join(summary_lines) if summary_lines else "_(no shots)_")
    )


def render_stage5_bible(output: dict) -> str:
    """Render the Continuity Brief into bible-section markdown.

    Stage 6 batches read this verbatim — it's what gives every batch the
    same locked vocabulary, character descriptors, and callback map.
    """
    char_lines = []
    for c in (output.get("character_locks") or []):
        char_lines.append(
            f"- **{c.get('character_name', '')}**: "
            f"{c.get('locked_descriptor', '')}"
        )
    vocab_lines = []
    for v in (output.get("vocabulary_locks") or []):
        vocab_lines.append(
            f"- **{v.get('concept', '')}** → "
            f"`{v.get('canonical_phrase', '')}`"
            + (f"  _({v.get('rationale', '')})_"
               if v.get('rationale') else "")
        )
    callback_lines = []
    for c in (output.get("callback_map") or []):
        callback_lines.append(
            f"- Shot **{c.get('shot_number', '')}** ← echoes shot "
            f"**{c.get('callback_to_shot', '')}**: {c.get('note', '')}"
        )
    atmo_lines = []
    for a in (output.get("act_atmospheres") or []):
        kws = ", ".join(a.get("keywords") or [])
        atmo_lines.append(f"- **{a.get('act', '')}**: {kws}")
    return (
        "## Stage 5 — Continuity Brief\n\n"
        "_Stage 6 batches read this brief verbatim. Locked vocabulary "
        "and character descriptors below must be echoed identically "
        "across every prompt._\n\n"
        "### Character Locks (use the locked descriptor verbatim in every shot featuring this character)\n"
        + ("\n".join(char_lines) if char_lines else "_(no characters locked)_")
        + "\n\n### Vocabulary Locks (canonical phrasing — use verbatim wherever the concept appears)\n"
        + ("\n".join(vocab_lines) if vocab_lines else "_(no vocab locked)_")
        + "\n\n### Callback Map (these shots must visually echo the referenced earlier shot)\n"
        + ("\n".join(callback_lines) if callback_lines else "_(no callbacks)_")
        + "\n\n### Per-Act Atmosphere Keywords\n"
        + ("\n".join(atmo_lines) if atmo_lines else "_(none)_")
        + "\n\n### Consistency Concerns Flagged\n"
        + (output.get("consistency_concerns") or "_(none)_")
    )


def render_stage6_bible(output: dict) -> str:
    review = output.get("continuity_review") or {}
    revisions = review.get("revisions_made") or []
    rev_lines = "\n".join(f"- {r}" for r in revisions)
    return (
        f"## Stage 6 — Final Prompts\n\n"
        f"### Continuity Review\n"
        f"**Variety:** {review.get('variety_check', '')}\n\n"
        f"**Consistency:** {review.get('consistency_notes', '')}\n\n"
        f"**Pacing:** {review.get('pacing_notes', '')}\n\n"
        f"**Revisions made:** "
        + (f"\n{rev_lines}" if rev_lines else "_(none)_")
        + f"\n\n_{len(output.get('shot_deltas') or [])} final prompts synthesized._"
    )


BIBLE_RENDERERS = {
    1: render_stage1_bible,
    2: render_stage2_bible,
    3: render_stage3_bible,
    4: render_stage4_bible,
    5: render_stage5_bible,
    6: render_stage6_bible,
}


# ──────────────────────────────────────────────────────────────────────
# Prompt builders — one per stage
# ──────────────────────────────────────────────────────────────────────

def _format_feedback(feedback: str | None) -> str:
    if not feedback or not feedback.strip():
        return ""
    return (
        "\n\n## User feedback on the prior attempt\n"
        f"The user noted: \"{feedback.strip()}\"\n\n"
        "Address this specifically. Don't throw away what was working — "
        "make the targeted change and preserve the rest of the craft.\n"
    )


def _format_narration(narration: dict) -> str:
    """Render the narration script as readable markdown for the prompt."""
    if not narration:
        return "_(no narration provided)_"
    parts = []
    title = narration.get("title") or narration.get("topic") or ""
    if title:
        parts.append(f"**Title:** {title}\n")
    beats = narration.get("narration") or narration.get("beats") or []
    if isinstance(beats, list):
        for b in beats:
            if not isinstance(b, dict):
                continue
            act = b.get("act", "")
            beat_id = b.get("beat", b.get("beat_id", ""))
            text = b.get("voiceover", b.get("text", b.get("narration", "")))
            duration = b.get("duration", "")
            header = f"### Act {act} · Beat {beat_id}"
            if duration:
                header += f" ({duration}s)"
            parts.append(header)
            parts.append(text.strip() if isinstance(text, str) else json.dumps(text))
            parts.append("")
    else:
        parts.append(str(beats))
    return "\n".join(parts)


def _format_cast(cast: dict | None) -> str:
    if not cast or not cast.get("cast"):
        return "_(no cast defined)_"
    lines = []
    for member in cast.get("cast", []):
        lines.append(
            f"- **{member.get('name', '?')}** ({member.get('role', '')}): "
            f"{member.get('description', '')}\n"
            f"  - Wardrobe: {member.get('wardrobe', '')}\n"
            f"  - Expressions: {member.get('expressions', '')}"
        )
    return "\n".join(lines)


def _format_style_refs(style_analysis: dict | None) -> str:
    if not style_analysis:
        return "_(no style references provided)_"
    parts = []
    if style_analysis.get("creative_direction"):
        parts.append(f"**Creative direction:** {style_analysis['creative_direction']}")
    if style_analysis.get("style_summary"):
        parts.append(f"**Style summary:** {style_analysis['style_summary']}")
    if style_analysis.get("visual_keywords"):
        kw = style_analysis["visual_keywords"]
        if isinstance(kw, list):
            kw = ", ".join(kw)
        parts.append(f"**Visual keywords:** {kw}")
    if style_analysis.get("color_palette"):
        cp = style_analysis["color_palette"]
        if isinstance(cp, list):
            cp = ", ".join(str(c) for c in cp)
        parts.append(f"**Reference palette:** {cp}")
    if style_analysis.get("style_lock_mode"):
        parts.append(f"**Style lock:** {style_analysis['style_lock_mode']}")
    return "\n".join(parts) if parts else "_(style references present but no summary text)_"


# ─── Stage 1 ──────────────────────────────────────────────────────────

def build_stage1_treatment_prompt(
    *, narration: dict, research_dossier: str | None,
    audience: str, tone: str, format_preset: str,
    viewer_outcome: str | None = None, feedback: str | None = None,
) -> tuple[str, type]:
    narration_block = _format_narration(narration)
    research_block = (research_dossier or "").strip() or "_(no research dossier)_"
    audience_block = f"Audience: {audience or 'general'}"
    tone_block = f"Tone: {tone or 'conversational'}"
    format_block = f"Format: {format_preset or 'standard'}"
    if viewer_outcome:
        format_block += f" · Viewer outcome: {viewer_outcome}"

    prompt = f"""# Stage 1 — Story Treatment

## Who you are
You are an experienced film and documentary Director. You've read thousands of scripts and you know
the difference between something that's "fine on the page" and something that will hold a viewer's
attention frame by frame. You think in scenes, in arcs, in moments of escalation and release.
You're writing the document that the rest of the team — Production Designer, DP, Storyboard Artist,
Script Supervisor — will read tomorrow morning before they start work.

## Your job
Write a real treatment. Not a summary. Not bullet points of "what happens." A treatment is the document
where the Director declares what this thing IS — its soul, its arc, the felt experience the viewer
should walk away with. Every downstream crew member depends on you getting this right.

## Principles
- **Commit.** Don't hedge with "perhaps" or "could be." Make decisions. The Production Designer is
  going to read your treatment and build a world from it — they need direction, not options.
- **Find the emotional spine.** Where does tension build? Where does it release? Where is the
  reveal, the betrayal, the laugh, the gut-punch? Map it beat by beat.
- **Performance matters.** Even with AI-generated faces, expression and posture carry meaning.
  Tell the team what each character is *feeling* at each beat — not just what they're doing.
- **Reference real work.** If this evokes Errol Morris, say so. If it should feel like a Werner
  Herzog cold open, say it. Naming reference works sharpens every other decision downstream.
- **Don't restate the script.** The team has the script. Your treatment interprets it — adds the
  layer of meaning and felt experience that isn't on the page.

## Format and context
{audience_block}
{tone_block}
{format_block}

## Narration script
{narration_block}

## Research dossier
{research_block}
{_format_feedback(feedback)}

## Output
Return a JSON object matching the Stage1Treatment schema:
- `logline` — one sentence. What is this video, what's at stake, why should I watch.
- `theme` — the deeper idea. One sentence.
- `emotional_arc` — list of moments through the story. Each: act, beat_ref, emotional_state,
  transition_note (what shifts to land us at the next state).
- `scene_treatments` — for every scene/beat group, a real paragraph (60+ words minimum) of
  prose describing what that scene IS, what it feels like, what the camera should be witnessing.
  Include `performance_note` per scene.
- `performance_notes` — overall performance direction for the cast. Energy levels, restraint vs.
  intensity, how characters should hold themselves.
- `tonal_references` — 3 to 7 specific real-world references (films, directors, documentary
  series, photographers). Be specific. "Cinéma vérité" alone is not enough — "the observational
  rigor of Frederick Wiseman, the warmth of Agnès Varda" is.

Write JSON only — no preamble.
"""
    return prompt, Stage1Treatment


# ─── Stage 2 ──────────────────────────────────────────────────────────

def build_stage2_world_design_prompt(
    *, bible_so_far: str, style_analysis: dict | None,
    cast: dict | None, feedback: str | None = None,
) -> tuple[str, type]:
    user_style = ((style_analysis or {}).get('style_summary') or '').strip()
    if user_style:
        rendering_style_directive = (
            f"- `rendering_style` — **Set this field to the following text VERBATIM (no rephrasing, "
            f"no embellishment, no truncation):**\n\n  \"{user_style}\"\n\n"
            f"  This is the user-approved style anchor. Every downstream shot prompt will echo it. "
            f"Changing the wording here breaks the visual contract with the user."
        )
    else:
        rendering_style_directive = (
            "- `rendering_style` — ONE crisp sentence (50–180 chars) that captures the OUTPUT AESTHETIC the\n"
            "  image and video models should render. Translate the user's creative direction above into this\n"
            "  sentence verbatim where possible. Examples of well-formed rendering_style values:\n"
            "    * \"Polished hand-drawn graphic-novel: confident ink linework, cross-hatched texture, warm painterly digital coloring.\"\n"
            "    * \"Photoreal cinematic 35mm film grain, anamorphic flares, muted teal-and-amber palette.\"\n"
            "    * \"Vintage 16mm documentary look: handheld, soft grain, faded Kodachrome warmth.\"\n"
            "  This single sentence will be echoed verbatim into every downstream shot prompt. It is the\n"
            "  single most important field in Stage 2. Be specific. Do not hedge."
        )

    prompt = f"""# Stage 2 — World & Design

## Who you are
You are the Production Designer. You've designed worlds for everything from intimate dramas to
period epics. Your job is the look and feel of the world the camera will inhabit — what's in the
frame, what color it is, what it's made of, what era it belongs to. The DP shoots your world; you
build it.

## Your job
Read the Director's treatment below. Internalize the emotional arc and tonal references. Then
declare the visual world this film lives in. Be specific. The DP will read your output tomorrow
and use it to choose lenses and lighting.

## Principles
- **Commit to a palette.** "Warm tones" is not a palette. Name the colors. Give hex codes. Say
  which dominates and when.
- **Texture is a language.** Wood, glass, concrete, fabric, skin — what does this world feel like
  to touch? Build a vocabulary the DP can light to.
- **Recurring motifs make a film feel composed.** What visual element returns? A shape, a prop,
  a kind of light, a color shift? Name 2-4 motifs that should appear repeatedly.
- **Light has a source.** Are we in a world of motivated light (real sources, daylight, lamps)
  or stylized light? What's the rule?
- **Don't restate Stage 1.** Build on it. The Director gave you the soul; you give the materials.

## Production Bible so far
{bible_so_far}

## Style references
{_format_style_refs(style_analysis)}

## Cast (for wardrobe alignment)
{_format_cast(cast)}
{_format_feedback(feedback)}

## Output
Return a JSON object matching the Stage2WorldDesign schema. Required fields:
{rendering_style_directive}
- `world_setting` — concrete paragraph. Where are we, when, what does it look like at a glance.
- `era` — period reference (e.g., "Late-summer 2026, suburban America" or "Edwardian London,
  industrial").
- `color_palette` — 4-7 entries. Each: name, hex, dominance_pct (sum to ~100), when_dominant
  (which beats/scenes/moods).
- `texture_vocabulary` — list of textures (e.g., "scuffed concrete", "amber polyester",
  "frosted glass", "translucent skin").
- `recurring_motifs` — 2-4 visual motifs that should appear repeatedly through the film.
- `props_and_environment` — paragraph on key props, environmental storytelling, things in the
  background that earn their place.
- `lighting_rules` — paragraph. Motivated vs. stylized, key sources, how light tracks the arc.

JSON only.
"""
    return prompt, Stage2WorldDesign


# ─── Stage 3 ──────────────────────────────────────────────────────────

def build_stage3_cinematography_prompt(
    *, bible_so_far: str, style_analysis: dict | None,
    feedback: str | None = None,
) -> tuple[str, type]:
    prompt = f"""# Stage 3 — Cinematography Plan

## Who you are
You are the Director of Photography. You've shot for Lubezki and Deakins and you have your own
voice. You make choices with reasons. You don't catalogue every lens in the bag — you commit to
a vocabulary that serves the story the Director is telling.

## Your job
Read the treatment (Stage 1) and the production design (Stage 2). Internalize the arc, the world,
the palette. Then write the cinematography plan that the Storyboard Artist will follow tomorrow.

This is not a technique checklist. It's the brief that says: *"In this film, when the camera moves
it means X. When we go wide we are saying Y. We've earned one extreme close-up, and we're saving
it for beat 7."*

## Principles
- **Commit to a vocabulary.** "We're a wide-lens film with one intimate close-up reserved for the
  reveal" is a choice. "We can use any lens" is not.
- **Movement is meaning.** When does the camera move? Why? When is it still? Stillness is also
  a choice and it has to be a deliberate one.
- **Lighting tracks the arc.** Don't list lighting setups in the abstract — say how light gets
  warmer or colder, harder or softer, as the story progresses.
- **Reference real DPs and films when it sharpens the brief.** "Roger Deakins' kitchen scenes in
  *Skyfall*" tells the team more than "low-key lighting."
- **Don't restate Stages 1 or 2.** Build on them.

## Available technique vocabulary
You can draw from the full vocabulary below — but don't list it. Pick what serves the story.

CAMERA MOVEMENT: static, dolly-in (push), dolly-out (pull), tracking, crane up/down, steadicam,
handheld, whip pan, slow push-in, orbit/arc, optical zoom, tilt up/down, boom.
ANGLE: eye-level, low, high, bird's eye, worm's eye, dutch, OTS, POV, profile.
LENS: wide-angle, standard, telephoto, macro, fisheye, anamorphic, tilt-shift.
COMPOSITION: rule of thirds, center/symmetry, golden ratio, leading lines, frame-within-frame,
negative space, foreground framing, diagonal, layered depth.
LIGHTING MOOD: high-key, low-key, Rembrandt, split, silhouette, rim/backlight, practical,
chiaroscuro, golden hour, motivated.
DEPTH/FOCUS: deep focus, shallow DOF, rack focus, split diopter, bokeh, pull focus.

## Production Bible so far
{bible_so_far}

## Style references
{_format_style_refs(style_analysis)}
{_format_feedback(feedback)}

## Output
Return a JSON object matching the Stage3Cinematography schema:
- `lens_vocabulary` — paragraph. Which lenses dominate, when each comes out, what they mean
  emotionally in *this* film.
- `movement_language` — paragraph. The rules for camera movement. When still, when moving,
  what triggers movement.
- `lighting_per_scene` — list of entries, one per scene. Each: scene_id, key_to_fill ratio,
  color, motivation (the in-world source), mood label.
- `mood_escalation` — list mapping each beat_ref to an intensity (1-10) and the visual_signal
  that carries that intensity (e.g., "warmer color temp + slower cuts").
- `canonical_references` — 3-5 specific shot references from real films/works. Concrete enough
  that a storyboard artist can look them up.

JSON only.
"""
    return prompt, Stage3Cinematography


# ─── Stage 4 ──────────────────────────────────────────────────────────

def build_stage4_shot_list_prompt(
    *, bible_so_far: str, cast: dict | None,
    narration: dict, format_preset: str | None,
    style_analysis: dict | None = None,
    target_shot_count: int = 0,
    pacing_tier: str = "Standard",
    total_words: int = 0,
    feedback: str | None = None,
    batch_info: str = "",
    starting_shot_number: int = 1,
    max_shot_duration: float = 6.0,
    target_wps: float = 2.7,
) -> tuple[str, type]:
    """Build the Stage 4 prompt.

    When `narration` is the *full* narration, target_shot_count is the full
    target. When called for a batch, pass the slice of narration containing
    only this batch's beats and a per-batch target_shot_count proportional
    to that slice's word count. `starting_shot_number` lets each batch
    number shots continuously across the whole film.
    """
    narration_block = _format_narration(narration)
    fmt_block = f"Format preset: {format_preset or 'standard'}"

    # Per-shot word ceiling derived from the user's max_shot_duration and the
    # planning speech rate. At 6s and 2.7 wps that's ~16 words per shot —
    # any narration sentence longer than that MUST be split into multiple shots.
    max_words_per_shot = max(4, int(max_shot_duration * target_wps))

    # Pacing brief — gives the LLM the target shot count derived from
    # words-per-shot for the pacing tier. Old pipeline hit this target by
    # construction (batched by beat with WORDS_PER_SHOT_TARGET); we have to
    # tell the LLM explicitly.
    if target_shot_count > 0:
        low = max(1, int(target_shot_count * 0.85))
        high = int(target_shot_count * 1.15)
        pacing_brief = (
            f"## Pacing target (NON-NEGOTIABLE)\n"
            f"- Pacing tier: **{pacing_tier}** (auto-selected from format preset "
            f"'{format_preset or 'standard'}')\n"
            f"- Narration word count (this batch): **{total_words}**\n"
            f"- **Target shot count for this batch: approximately {target_shot_count} shots "
            f"(acceptable range {low}–{high}).**\n"
            f"- This is calibrated from words-per-shot for this pacing tier. "
            f"Producing far fewer shots means each shot is summarizing multiple ideas — "
            f"that's a treatment, not a shot list. Producing too many means you're cutting "
            f"for the sake of cutting.\n"
            f"- If a beat has 60+ words, it MUST get multiple shots. Don't collapse "
            f"multi-sentence beats into a single shot.\n"
        )
        if starting_shot_number > 1:
            pacing_brief += (
                f"- **Numbering: start `shot_number` at {starting_shot_number} "
                f"and increment by 1.** This batch's shots come after earlier batches "
                f"in the final shot list.\n"
            )
    else:
        pacing_brief = ""

    shot_length_brief = (
        f"## Shot-length cap (NON-NEGOTIABLE)\n"
        f"- **Max shot duration: {max_shot_duration:.1f}s.** The video model can only generate "
        f"clips up to this length. Any shot longer than this is unusable.\n"
        f"- **Max script_beat words per shot: ~{max_words_per_shot} words** (at ~{target_wps} wps "
        f"reading rate × {max_shot_duration:.1f}s = {max_words_per_shot} words). If a narration "
        f"sentence has more words than this, it MUST be split across multiple shots.\n"
        f"- **No two shots may share the same script_beat.** Duplicating a line across shots "
        f"is a bug — it means you padded the count instead of splitting the text. If you need "
        f"multiple shots to cover one sentence, give each shot a DIFFERENT CLAUSE of that "
        f"sentence (split on commas, em-dashes, conjunctions), not the whole sentence repeated.\n"
        f"\n"
        f"### Creative-split cookbook\n"
        f"When a single narration sentence exceeds {max_words_per_shot} words, split it into "
        f"2–4 shots and make each shot earn its place:\n"
        f"1. **Slice the sentence on natural breath boundaries** — commas, em-dashes, "
        f"conjunctions, prepositional pivots. Assign each slice to its own shot's `script_beat`.\n"
        f"2. **Vary shot scale across the splits** — e.g. wide establishing → medium pivot → "
        f"close emphasis → reaction. Don't repeat the same `lens`/`shot_size` across consecutive "
        f"splits of one sentence.\n"
        f"3. **Vary camera move** — e.g. locked-off → slow push-in → tilt down → handheld drift. "
        f"The camera doing the same thing twice in a row is a missed opportunity.\n"
        f"4. **Vary the subject of attention** — foreground/midground/background swap. If shot A "
        f"foregrounds the character, shot B might foreground the environment with the character "
        f"in midground.\n"
        f"5. **The shots must read as a sequence, not duplicates.** Each one moves the eye to "
        f"something new while the VO keeps going.\n"
    )

    batch_header = f" {batch_info}" if batch_info else ""

    prompt = f"""# Stage 4 — Shot List{batch_header}

## Who you are
You are the Director, sitting with the Storyboard Artist. You've finished pre-production. The
treatment is locked, the world is designed, the DP has committed to a cinematic vocabulary. Now
the two of you compose the actual shot list — every shot of the film, in order.

## Your job
Read the entire production bible below. Read the narration carefully — every beat is a unit of
story you need to cover with one or more shots. Produce the complete shot list at the target
density for this film's pacing.

You are NOT writing prompts yet. That's Stage 5's job. You are producing the *blueprint*: what
each shot is, where it goes, how long, what it covers, what the camera does, who is in frame,
what they're feeling and wearing.

{pacing_brief}
{shot_length_brief}
## Principles
- **Hit the shot count target.** Don't summarize beats into single shots. If the target says
  ~200 shots and you produce 30, you're handing back a treatment — not a shot list.
- **Cover every beat.** Each narration beat needs at least one shot. Beats with more words
  need proportionally more shots.
- **`script_beat` is a verbatim slice of the narration, not a paraphrase.** Editors and the
  Visuals tab use this to align voice-over to picture. Copy text directly from the narration —
  a sentence if it fits the shot-length cap, or a CLAUSE (split on commas/em-dashes/
  conjunctions) if the sentence is longer than the cap.
- **Vary the rhythm.** Don't shoot every beat with the same shot scale. The DP's plan tells you
  when to push close and when to pull wide — follow it.
- **Each shot has an intent and a reason to cut.** `directors_intent` is why this shot exists;
  `cutting_rationale` is why the edit lands here.
- **Composition layers matter.** Foreground, midground, background. Real shots have depth. Lazy
  shots are flat. Use the layered-depth vocabulary from Stage 3.
- **Honor the cast.** `character_expression` and `character_outfit` must match the moment. The
  cinematographer can't read minds — tell them what the character is feeling and wearing at this
  exact moment.
- **Match camera language to Stage 3.** When you say `camera_move: "slow push-in"`, the DP has
  already told you what that means in this film. Don't invent new vocabulary — execute theirs.

## Production Bible so far
{bible_so_far}

## Style anchor (carry into every shot)
{_format_style_refs(style_analysis)}

## Narration (the source of truth for beats)
{narration_block}

## Cast
{_format_cast(cast)}

## Format
{fmt_block}
{_format_feedback(feedback)}

## Output
Return a JSON object matching the Stage4ShotList schema. The `shots` field is a list of
ShotBlueprint entries. For each shot, fill EVERY field:

**Narrative anchors (these survive into the final exports — write them carefully):**
- `shot_number` — sequential, "1", "2", etc.
- `timestamp` — MM:SS format, the start time within the video
- `duration` — seconds as a string (e.g., "4")
- `act` — which act this shot belongs to, e.g. "ACT 1: HOOK", "ACT 2: INVESTIGATION"
- `beat` — narrative beat name (short label that names the story moment)
- `script_beat` — **the verbatim narration sentence this shot illustrates.** Copy a single
  sentence directly from the narration text above — do not paraphrase. This is the line the
  voiceover speaks while this shot is on screen.
- `cutting_rationale` — one sentence: why does the edit cut here? What story logic drives the
  cut to this shot?
- `emotion` — the emotional state of the moment (e.g. "Anxious anticipation", "Quiet awe")

**Character (locked across shots unless story-driven change):**
- `character_expression` — character emotional state in this exact frame, including facial
  detail (e.g. "Furrowed brow, eyes narrowed in concentration, lips slightly pressed")
- `character_outfit` — what the character is wearing (locked from cast unless story-driven
  change requires a new outfit)

**Cinematography:**
- `directors_intent` — one sentence on why this shot exists
- `composition` — {{ foreground, midground, background }} — three concrete sentences
- `camera_move` — drawn from the Stage 3 vocabulary
- `lens` — drawn from the Stage 3 vocabulary
- `angle` — eye-level, low, high, dutch, etc.

Every field is required. Cover all beats. JSON only.
"""
    return prompt, Stage4ShotList


# ─── Stage 5 — Continuity Brief ──────────────────────────────────────

def _compact_shot_for_brief(s: dict) -> str:
    """One-line representation of a shot for the Continuity Brief input.

    Pipe-delimited compact form keeps ~200 chars/shot so a 1000-shot list
    fits in ~200KB — well within Gemini's input window. The Script
    Supervisor sees: number | beat | character | outfit | script_beat.
    """
    def _trim(v, n):
        return (str(v or "")[:n]).replace("|", "/").replace("\n", " ")
    return (
        f"{s.get('shot_number', '?')}|"
        f"{_trim(s.get('beat') or s.get('beat_ref'), 32)}|"
        f"{_trim(s.get('character_expression') or s.get('expression_state'), 48)}|"
        f"{_trim(s.get('character_outfit') or s.get('wardrobe_state'), 48)}|"
        f"{_trim(s.get('script_beat'), 64)}"
    )


def build_stage5_continuity_brief_prompt(
    *, bible_so_far: str, shot_blueprints: list[dict],
    style_analysis: dict | None = None,
    cast: dict | None = None,
    feedback: str | None = None,
) -> tuple[str, type]:
    """Build the Stage 5 (Continuity Brief) prompt.

    Sees the FULL shot list and extracts invariants every Stage 6 batch
    must share. Output is small (~10KB) regardless of input size.
    """
    compact_shots = "\n".join(_compact_shot_for_brief(s) for s in shot_blueprints)
    cast_block = _format_cast(cast)
    prompt = f"""# Stage 5 — Continuity Brief

## Who you are
You are the **Script Supervisor**. Across every shot of this film, your one job is to make sure
nothing contradicts itself. Wardrobe consistent. Recurring props described the same way every
time. Phrasing of recurring images locked. Callbacks honored.

The Director and DP just handed you the full shot list ({len(shot_blueprints)} shots). Tomorrow
the DP will write final image-generation prompts in batches — possibly 20+ separate writing
sessions. Without this brief, batches will independently invent different words for the same
amber light, the same scarred wall, the same character's wardrobe. The film will look stitched
together by strangers.

Your output is the contract every batch will read VERBATIM before writing a single prompt.

## Your job
1. **Lock the characters.** For every named character or recurring agent in the shot list:
   write ONE sentence (60–120 chars) that describes them physically. Every batch will paste this
   sentence verbatim into the `SUBJECT CORE` of every shot featuring that character. Wardrobe,
   build, distinctive features. Be specific.

2. **Lock the vocabulary.** Find concepts that recur across multiple shots — "amber light",
   "scarred concrete wall", "wet pavement", "sister wasp's antenna" — and commit to ONE
   canonical phrase per concept. Every batch will use the canonical phrase verbatim. Aim for
   8–20 vocab locks for a typical film. Skip vocabulary that only appears once.

3. **Build the callback map.** Read the shot list cover-to-cover. When you see a shot that
   should visually echo an earlier one (same composition, same prop, returning subject), record
   it. The DP writing batch 19 won't have read batch 1's prompts — your callback note is how
   batch 19 knows shot 47 must mirror shot 12.

4. **Tag per-act atmosphere.** For each act in the shot list, give 4–8 keywords that capture the
   atmospheric register of that act (e.g., Act 1: "warm, observational, low-stakes" → Act 3:
   "icy, claustrophobic, fractured"). Every batch within an act will lean on these keywords.

5. **Flag consistency concerns.** If you spot contradictions in the shot list itself
   (character wears different things in adjacent shots with no story justification, lens
   vocabulary breaks Stage 3's rules, etc.), describe them in `consistency_concerns` so the
   user can fix the shot list before paying for Stage 6.

## Principles
- **Verbatim is the point.** "Locked" means *exact words*, not paraphrases. The whole reason
  this stage exists is that different batches won't see each other's prompts. If two batches
  use synonyms for the same thing, the generated images won't match.
- **Be ruthless about which concepts deserve a lock.** A vocab lock is a tax on every prompt;
  only lock things that recur 3+ times.
- **Character locks beat wardrobe states.** The blueprint's `wardrobe_state` field can be
  story-driven (a character changes clothes). The character lock is the *physical body*: face,
  build, distinguishing features — the parts that never change across the film.
- **Callback notes are concrete.** "Shot 47 echoes shot 12 — same low-angle composition through
  the hex tunnel, same pool of amber light pooling on the floor" — not "echoes shot 12."

## Production Bible (Stages 1–4)
{bible_so_far}

## Style references
{_format_style_refs(style_analysis)}

## Cast (for character lock cross-reference)
{cast_block}

## Full shot list (compact, all {len(shot_blueprints)} shots)
{compact_shots}
{_format_feedback(feedback)}

## Output
Return a JSON object matching the Stage5ContinuityBrief schema:
- `character_locks` — list of {{ character_name, locked_descriptor }}
- `vocabulary_locks` — list of {{ concept, canonical_phrase, rationale }}
- `callback_map` — list of {{ shot_number, callback_to_shot, note }}
- `act_atmospheres` — list of {{ act, keywords }}
- `consistency_concerns` — string. Empty if none.

JSON only.
"""
    return prompt, Stage5ContinuityBrief


# ─── Stage 5 — two-phase fallback for >800 shots ─────────────────────
#
# Above ~800 shots, the single Stage 5 call risks hitting Gemini's
# output-token cap. We split the OUTPUT work into two calls that both
# see the FULL shot list (so no continuity drift). Phase A locks the
# characters; Phase B reads Phase A and emits everything else.

def build_stage5_phase_a_prompt(
    *, bible_so_far: str, shot_blueprints: list[dict],
    style_analysis: dict | None = None,
    cast: dict | None = None,
    feedback: str | None = None,
) -> tuple[str, type]:
    """Phase 5a — character locks only. Sees the full shot list."""
    from agentic_schemas import Stage5PhaseA
    compact_shots = "\n".join(_compact_shot_for_brief(s) for s in shot_blueprints)
    cast_block = _format_cast(cast)
    prompt = f"""# Stage 5 — Continuity Brief, Phase A (Character Locks)

## Who you are
You are the **Script Supervisor**. This is a large production ({len(shot_blueprints)} shots) and
we're locking continuity in two phases. **Phase A is yours: character locks only.**

## Your job — character locks
For every named character or recurring agent in the shot list, write ONE sentence
(60–120 chars) that describes them physically. Every Stage 6 batch will paste this verbatim
into the `subject_pose` field for shots featuring that character. Wardrobe, build,
distinctive features — be specific.

Aim for one entry per unique recurring agent. Don't lock one-off background figures.

## Principles
- **Verbatim is the point.** "Locked" means *exact words*, not paraphrases.
- **The character lock is the *physical body*: face, build, distinguishing features** — the
  parts that never change across the film. Story-driven wardrobe changes belong in
  `character_outfit` on the shot, not here.

## Production Bible (Stages 1–4)
{bible_so_far}

## Style references
{_format_style_refs(style_analysis)}

## Cast (for character lock cross-reference)
{cast_block}

## Full shot list (compact, all {len(shot_blueprints)} shots)
{compact_shots}
{_format_feedback(feedback)}

## Output
Return a JSON object matching the Stage5PhaseA schema:
- `character_locks` — list of {{ character_name, locked_descriptor }}

JSON only.
"""
    return prompt, Stage5PhaseA


def build_stage5_phase_b_prompt(
    *, bible_so_far: str, shot_blueprints: list[dict],
    character_locks: list[dict],
    style_analysis: dict | None = None,
    cast: dict | None = None,
    feedback: str | None = None,
) -> tuple[str, type]:
    """Phase 5b — vocab locks, callbacks, atmospheres, concerns.

    Sees the full shot list AND Phase A's character_locks (so callback
    notes and consistency concerns can reference them).
    """
    from agentic_schemas import Stage5PhaseB
    compact_shots = "\n".join(_compact_shot_for_brief(s) for s in shot_blueprints)
    locks_block = (
        "\n".join(f"- {c.get('character_name','')}: {c.get('locked_descriptor','')}"
                  for c in character_locks) or "_(no character locks committed)_"
    )
    prompt = f"""# Stage 5 — Continuity Brief, Phase B (Vocab, Callbacks, Atmospheres)

## Who you are
You are the **Script Supervisor**, Phase B. Phase A already locked the characters. Your job
now is to lock the rest of the continuity layer so Stage 6 batches don't drift.

## Phase A's character locks (already committed)
{locks_block}

## Your job

1. **Lock the vocabulary.** Find concepts that recur across multiple shots ("amber light",
   "scarred concrete wall") and commit to ONE canonical phrase per concept. Every Stage 6 batch
   will use it verbatim. Aim for 8–20 vocab locks. Skip vocabulary that only appears once.

2. **Build the callback map.** When a shot should visually echo an earlier one (same
   composition, same prop, returning subject), record it. The Stage 6 batch writing shot 47
   won't see batch 1's prompts — your note is how they know to mirror shot 12.

3. **Tag per-act atmosphere.** For each act, give 4–8 keywords capturing its atmospheric
   register (Act 1: "warm, observational" → Act 3: "icy, fractured").

4. **Flag consistency concerns.** If you spot contradictions in the shot list itself
   (wardrobe jumps, lens vocab breaks Stage 3, etc.), describe them so the user can fix
   the shot list before paying for Stage 6.

## Production Bible (Stages 1–4)
{bible_so_far}

## Style references
{_format_style_refs(style_analysis)}

## Cast
{_format_cast(cast)}

## Full shot list (compact, all {len(shot_blueprints)} shots)
{compact_shots}
{_format_feedback(feedback)}

## Output
Return a JSON object matching the Stage5PhaseB schema:
- `vocabulary_locks` — list of {{ concept, canonical_phrase, rationale }}
- `callback_map` — list of {{ shot_number, callback_to_shot, note }}
- `act_atmospheres` — list of {{ act, keywords }}
- `consistency_concerns` — string. Empty if none.

JSON only.
"""
    return prompt, Stage5PhaseB


# ─── Stage 6 — Final Prompts ─────────────────────────────────────────

def build_stage6_final_prompts_prompt(
    *, bible_so_far: str, shot_blueprints: list[dict],
    continuity_brief: dict | None = None,
    style_analysis: dict | None = None,
    rendering_style: str = "",
    aspect_ratio: str = "16:9",
    batch_info: str = "",
    feedback: str | None = None,
) -> tuple[str, type]:
    blueprints_block = json.dumps(shot_blueprints, indent=2)

    # Seven structured prompt fields. We split the old single
    # first_frame_prompt string into separate schema fields so the model
    # cannot return a paragraph — Stage 6's schema enforces the shape, and
    # the merger concatenates them into a labeled `first_frame_prompt`
    # server-side. Same precision as the old 12-section template at ~1/3
    # the tokens.
    template_block = (
        "Each `shot_delta` carries SEVEN STRUCTURED PROMPT FIELDS. Fill each one with a "
        "concrete, load-bearing sentence — no padding, no skipped sections. The merger will "
        "concatenate them into the labeled `first_frame_prompt` automatically.\n\n"
        "Required fields per shot:\n"
        "- `shot_size` — ECU / CU / MCU / Medium / Wide / Extreme Wide (pick one)\n"
        "- `subject_pose` — who/what is in frame, including the locked character descriptor "
        "(verbatim from Continuity Brief), their pose, action, expression\n"
        "- `environment` — the world around the subject; foreground/midground/background depth, "
        "set details, textures\n"
        "- `lighting` — source + quality + direction + color temp in one sentence\n"
        "- `lens_dof` — focal length + aperture + depth of field (e.g. '35mm at f/1.8, shallow "
        "with bokeh on background')\n"
        "- `color_palette` — dominant colors + contrast level + accent colors\n"
        "- `output_aesthetic` — **the canonical rendering_style verbatim (see below)**. No "
        "paraphrasing. This is the style anchor — every shot's output_aesthetic is the same "
        "exact sentence.\n\n"
        f"Aspect ratio for this project: **{aspect_ratio}**.\n\n"
        "Every `veo_prompt` describes MOTION (what moves, what the camera does):\n"
        "```\n"
        "<Shot size> of <subject + action>, <camera movement using Stage 3 vocabulary>.\n"
        "Lighting: <one sentence on lighting>.\n"
        "Camera: <one sentence on lens + movement>.\n"
        "Audio: <ambient + diegetic sounds for this moment>.\n"
        "Style: <the rendering_style verbatim>.\n"
        "```"
    )

    style_block = _format_style_refs(style_analysis)
    rendering_anchor = (rendering_style or "").strip()
    if rendering_anchor:
        rendering_anchor_block = (
            f"## Canonical rendering style (verbatim into every `output_aesthetic`)\n"
            f"```\n{rendering_anchor}\n```\n"
            f"This exact sentence is `output_aesthetic` for EVERY shot in this batch. Copy "
            f"it character-for-character into the `output_aesthetic` field. Also include it "
            f"verbatim on the `Style:` line of every `veo_prompt`. The merger validates this "
            f"and will overwrite any drift, so save the round-trip and just paste it."
        )
    else:
        rendering_anchor_block = (
            "## Canonical rendering style\n"
            "Stage 2 did not commit a rendering_style. Derive it yourself from the bible + "
            "style references below and use the same exact sentence for every shot's "
            "`output_aesthetic` and `Style:` line."
        )

    # Render the Continuity Brief inline so every batch sees the same locked
    # vocabulary, character descriptors, and callback map.
    if continuity_brief:
        brief_block = "## Continuity Brief (from Stage 5 — read this VERBATIM)\n\n"
        char_locks = continuity_brief.get('character_locks') or []
        if char_locks:
            brief_block += "**Character locks (paste verbatim into `subject_pose` whenever this character appears):**\n"
            for c in char_locks:
                brief_block += (f"- `{c.get('character_name', '')}` → "
                                f"{c.get('locked_descriptor', '')}\n")
            brief_block += "\n"
        vocab_locks = continuity_brief.get('vocabulary_locks') or []
        if vocab_locks:
            brief_block += "**Vocabulary locks (use the canonical phrase verbatim wherever the concept appears):**\n"
            for v in vocab_locks:
                brief_block += (f"- `{v.get('concept', '')}` → "
                                f"\"{v.get('canonical_phrase', '')}\"\n")
            brief_block += "\n"
        callbacks = continuity_brief.get('callback_map') or []
        # Filter callback map to shots in this batch — keeps the prompt
        # focused without losing relevant callbacks.
        batch_shot_nums = {str(b.get('shot_number')) for b in shot_blueprints}
        relevant_callbacks = [c for c in callbacks
                              if str(c.get('shot_number')) in batch_shot_nums]
        if relevant_callbacks:
            brief_block += "**Callbacks anchored in THIS batch (echo the referenced shot's framing/imagery):**\n"
            for c in relevant_callbacks:
                brief_block += (f"- Shot {c.get('shot_number', '')} echoes shot "
                                f"{c.get('callback_to_shot', '')}: {c.get('note', '')}\n")
            brief_block += "\n"
        atmospheres = continuity_brief.get('act_atmospheres') or []
        if atmospheres:
            brief_block += "**Per-act atmosphere keywords (weave into `lighting` and `color_palette` so the act feels coherent):**\n"
            for a in atmospheres:
                kws = ", ".join(a.get('keywords') or [])
                brief_block += f"- {a.get('act', '')}: {kws}\n"
            brief_block += "\n"
    else:
        brief_block = ("## Continuity Brief\n_(no brief — Stage 5 was skipped or empty. "
                       "Continuity across batches WILL drift.)_\n")

    prompt = f"""# Stage 6 — Final Prompts {batch_info}

## Who you are
You are the **Director of Photography**, writing the final image-generation prompts that the
visuals team hands to Veo and the image models. The Script Supervisor (Stage 5) has already
locked the vocabulary and characters — your job is to write rich, structured prompts that
respect those locks.

## Your job

**Step A — Light continuity sweep.** Skim this batch's shot list. If you spot a shot that
contradicts the bible (e.g., a wardrobe state that breaks a character lock), propose a
targeted revision via `revised_blueprint_fields`. Surgical fixes only.

**Step B — Final prompts.** For EVERY shot in the blueprint list, produce two prompts using
the structured templates below. NO ONE-LINERS. Each prompt must be the full template.

## Output template (MANDATORY)

{template_block}

{rendering_anchor_block}

{brief_block}

## Principles for prompts
- **Locks are verbatim.** Character locks paste into `subject_pose`. Vocab locks replace any
  synonym you might've reached for. Rendering style verbatim in `output_aesthetic` and the
  `Style:` line of `veo_prompt`.
- **Every word is load-bearing.** No "beautiful, cinematic, high-quality" padding.
- **Honor the bible.** If Stage 2 said "amber dominant palette," every prompt reflects that.
- **Veo prompts describe MOTION.** What moves. What the camera does. Static description
  belongs in the seven structured fields, not in veo_prompt.
- **No field collapse.** Don't dump everything into `subject_pose` and leave others terse.
  Each of the seven fields earns its line.

## Production Bible (Stages 1–5)
{bible_so_far}

## Style references (raw — already in the bible, included for redundancy)
{style_block}

## Shot blueprints (this batch — emit one delta per blueprint, in order)
{blueprints_block}
{_format_feedback(feedback)}

## Output
Return a JSON object matching the Stage6Final schema:
- `continuity_review` — {{ variety_check, consistency_notes, pacing_notes, revisions_made }}
- `shot_deltas` — one entry per shot in this batch, IN ORDER. Each entry:
  - `shot_number` — must match the blueprint shot_number EXACTLY
  - `shot_size`, `subject_pose`, `environment`, `lighting`, `lens_dof`, `color_palette`,
    `output_aesthetic` — the seven structured prompt fields described above
  - `veo_prompt` — the structured veo template above
  - `revised_blueprint_fields` — list of {{field_name, new_value, reason}} ONLY for fields you
    want to change (empty list `[]` if no revisions for this shot)

CRITICAL: emit one shot_delta per shot in the input batch. Do NOT skip shots. Fill ALL SEVEN
prompt fields per shot — the schema enforces this.

JSON only.
"""
    return prompt, Stage6Final


# ──────────────────────────────────────────────────────────────────────
# Dispatch
# ──────────────────────────────────────────────────────────────────────

STAGE_PROMPT_BUILDERS = {
    1: build_stage1_treatment_prompt,
    2: build_stage2_world_design_prompt,
    3: build_stage3_cinematography_prompt,
    4: build_stage4_shot_list_prompt,
    5: build_stage5_continuity_brief_prompt,
    6: build_stage6_final_prompts_prompt,
}
