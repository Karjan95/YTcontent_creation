"""
Pydantic schemas for the 5-stage agentic production pipeline.

Design rules (lessons from the 6-phase pipeline failures):

1. NO Optional fields. Gemini's constrained decoder treats Optional as
   "may skip" and under output pressure the model drops carry-forward
   fields. Every field is required. If a stage doesn't have data for a
   field, it returns an empty string / empty list — never omits the key.

2. NO raw `dict` or `list[dict]` types. Both generate
   `additionalProperties: true` in the emitted JSON schema, which the
   Gemini API rejects. Use explicit nested BaseModel classes for every
   structured field.

3. NO model_config = ConfigDict(extra='allow'). Same reason.

4. Stage 5 emits ONLY new fields (prompts + continuity revisions). The
   orchestrator merges Stage 5 output with Stage 4 blueprints by
   shot_number server-side. The LLM is never asked to copy values
   forward — that's the carry-forward bug that broke Phase 5.
"""

from pydantic import BaseModel


# ──────────────────────────────────────────────────────────────────────
# Stage 1 — Story Treatment (Director)
# ──────────────────────────────────────────────────────────────────────

class _ArcMoment(BaseModel):
    act: str
    beat_ref: str
    emotional_state: str
    transition_note: str


class _SceneTreatment(BaseModel):
    scene_id: str
    beat_refs: list[str]
    treatment: str
    performance_note: str


class Stage1Treatment(BaseModel):
    logline: str
    theme: str
    emotional_arc: list[_ArcMoment]
    scene_treatments: list[_SceneTreatment]
    performance_notes: str
    tonal_references: list[str]


# ──────────────────────────────────────────────────────────────────────
# Stage 2 — World & Design (Production Designer)
# ──────────────────────────────────────────────────────────────────────

class _ColorEntry(BaseModel):
    name: str
    hex: str
    dominance_pct: int
    when_dominant: str


class Stage2WorldDesign(BaseModel):
    world_setting: str
    era: str
    rendering_style: str
    color_palette: list[_ColorEntry]
    texture_vocabulary: list[str]
    recurring_motifs: list[str]
    props_and_environment: str
    lighting_rules: str


# ──────────────────────────────────────────────────────────────────────
# Stage 3 — Cinematography Plan (DP)
# ──────────────────────────────────────────────────────────────────────

class _SceneLighting(BaseModel):
    scene_id: str
    key_to_fill: str
    color: str
    motivation: str
    mood: str


class _MoodPoint(BaseModel):
    beat_ref: str
    intensity: int
    visual_signal: str


class Stage3Cinematography(BaseModel):
    lens_vocabulary: str
    movement_language: str
    lighting_per_scene: list[_SceneLighting]
    mood_escalation: list[_MoodPoint]
    canonical_references: list[str]


# ──────────────────────────────────────────────────────────────────────
# Stage 4 — Shot List (Director + Storyboard Artist)
# ──────────────────────────────────────────────────────────────────────

class _CompositionLayers(BaseModel):
    foreground: str
    midground: str
    background: str


class _ShotBlueprint(BaseModel):
    shot_number: str
    timestamp: str
    duration: str
    # Narrative anchors — restored from the old pipeline so script_beat,
    # cutting_rationale, etc. survive into the Visuals tab + final exports.
    act: str
    beat: str
    script_beat: str  # the verbatim narration line this shot illustrates
    cutting_rationale: str
    emotion: str
    # Character (renamed from expression_state / wardrobe_state for clarity
    # and to match what the UI already expects).
    character_expression: str
    character_outfit: str
    # Cinematography
    directors_intent: str
    composition: _CompositionLayers
    camera_move: str
    lens: str
    angle: str


class Stage4ShotList(BaseModel):
    shots: list[_ShotBlueprint]


# ──────────────────────────────────────────────────────────────────────
# Stage 5 — Continuity Brief (Script Supervisor)
# ──────────────────────────────────────────────────────────────────────
#
# Sees the FULL Stage 4 shot list. Extracts the invariants Stage 6 batches
# all need to share so prompts written in different batches don't drift
# in phrasing, character description, or callbacks.

class _CharacterLock(BaseModel):
    character_name: str
    locked_descriptor: str  # one sentence reused verbatim across all shots


class _VocabLock(BaseModel):
    concept: str            # e.g. "amber light"
    canonical_phrase: str   # e.g. "warm amber glow"
    rationale: str


class _CallbackEntry(BaseModel):
    shot_number: str        # the shot that should echo another
    callback_to_shot: str   # the earlier shot it echoes
    note: str               # what specifically to echo (framing, palette, prop)


class _ActAtmosphere(BaseModel):
    act: str
    keywords: list[str]


class Stage5ContinuityBrief(BaseModel):
    character_locks: list[_CharacterLock]
    vocabulary_locks: list[_VocabLock]
    callback_map: list[_CallbackEntry]
    act_atmospheres: list[_ActAtmosphere]
    consistency_concerns: str  # issues found in the shot list to flag to user


# Two-phase fallback for >800 shots: split the OUTPUT work across two
# calls (both see the full shot list, so no continuity drift). Phase A
# returns character_locks only; Phase B returns everything else.

class Stage5PhaseA(BaseModel):
    character_locks: list[_CharacterLock]


class Stage5PhaseB(BaseModel):
    vocabulary_locks: list[_VocabLock]
    callback_map: list[_CallbackEntry]
    act_atmospheres: list[_ActAtmosphere]
    consistency_concerns: str


# ──────────────────────────────────────────────────────────────────────
# Stage 6 — Final Prompts (DP)
# ──────────────────────────────────────────────────────────────────────

class _ContinuityReview(BaseModel):
    variety_check: str
    consistency_notes: str
    pacing_notes: str
    revisions_made: list[str]


class _RevisedField(BaseModel):
    field_name: str
    new_value: str
    reason: str


class _FinalShotDelta(BaseModel):
    shot_number: str
    # Seven structured prompt sections — replace the unconstrained
    # first_frame_prompt string so the model cannot return a paragraph.
    # The merger concatenates these into a labeled first_frame_prompt
    # server-side.
    shot_size: str          # ECU / CU / MCU / Medium / Wide / Extreme Wide
    subject_pose: str       # who/what + action + expression
    environment: str        # location + bg/fg props
    lighting: str           # source + direction + color temp
    lens_dof: str           # focal length + aperture + depth of field
    color_palette: str      # dominant colors + contrast
    output_aesthetic: str   # MUST equal Stage 2 rendering_style verbatim
    veo_prompt: str
    revised_blueprint_fields: list[_RevisedField]


class Stage6Final(BaseModel):
    continuity_review: _ContinuityReview
    shot_deltas: list[_FinalShotDelta]


# ──────────────────────────────────────────────────────────────────────
# Lookup
# ──────────────────────────────────────────────────────────────────────

STAGE_SCHEMAS = {
    1: Stage1Treatment,
    2: Stage2WorldDesign,
    3: Stage3Cinematography,
    4: Stage4ShotList,
    5: Stage5ContinuityBrief,
    6: Stage6Final,
}

STAGE_NAMES = {
    1: "story_treatment",
    2: "world_design",
    3: "cinematography",
    4: "shot_list",
    5: "continuity_brief",
    6: "final_prompts",
}

STAGE_LABELS = {
    1: "Story Treatment",
    2: "World & Design",
    3: "Cinematography Plan",
    4: "Shot List",
    5: "Continuity Brief",
    6: "Final Prompts",
}

STAGE_ROLES = {
    1: "Director",
    2: "Production Designer",
    3: "Director of Photography",
    4: "Director + Storyboard Artist",
    5: "Script Supervisor",
    6: "Director of Photography",
}
