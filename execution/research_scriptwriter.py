"""
Research & Script Writer
========================
Orchestrates the script pipeline:
  Narration: Gemini writes a flowing narration (organized by acts/beats)
  Production: Gemini splits narration into timed shots and generates prompts

This module provides helper functions that server.py calls.
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(__file__))
from research_templates import (
    get_template,
    get_all_templates_metadata,
    build_research_queries,
    build_script_prompt,
    build_production_prompt,
    build_title_suggestions_prompt,
    build_tone_suggestion_prompt,
    build_beat_regeneration_prompt,
    build_script_doctor_prompt,
    build_director_prompt,
    build_cinematographer_prompt,
    build_storyboard_prompt,
    build_continuity_supervisor_prompt,
    build_dp_prompt,
)
from gemini_client import generate_content


def build_research_dossier(topic: str, template_id: str,
                           notebook_query_results: list) -> str:
    """
    Take raw NotebookLM query results and format them into a structured
    research dossier string for the script prompt.

    Args:
        topic: The research topic
        template_id: Which template was used
        notebook_query_results: List of dicts with {question, answer} pairs
    Returns:
        Formatted research dossier string
    """
    template = get_template(template_id)
    if not template:
        return f"Topic: {topic}\nNo structured research available."

    dossier_parts = [
        f"# Research Dossier: {topic}",
        f"## Template: {template['metadata']['name']}",
        f"## Research Mode: {template['research_config']['mode']}",
        "",
    ]

    for i, result in enumerate(notebook_query_results):
        question = result.get("question", f"Analysis #{i+1}")
        answer = result.get("answer", "No data found.")
        dossier_parts.append(f"### {question}")
        dossier_parts.append(answer)
        dossier_parts.append("")

    return "\n".join(dossier_parts)


def _parse_json_response(raw_response: str) -> dict:
    """Parse JSON from a Gemini response, handling markdown code fences."""
    if not raw_response:
        raise ValueError("Empty response from Gemini")
    text = raw_response.strip()

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove the opening ``` line
        lines = lines[1:]
        # Remove the closing ``` line (handle trailing whitespace/empty lines)
        while lines and lines[-1].strip() in ("```", ""):
            if lines[-1].strip() == "```":
                lines.pop()
                break
            lines.pop()
        text = "\n".join(lines).strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback: find the outermost { ... } in the text
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        candidate = text[first_brace:last_brace + 1]
        return json.loads(candidate)  # Let this raise if it also fails

    raise json.JSONDecodeError("No JSON object found", text, 0)


def generate_narration(topic: str, template_id: str, research_dossier: str,
                       duration_minutes: int = 10, audience: str = "general",
                       tone: str = "", focus: str = "", style_guide: str = None,
                       selected_title: str = None, format_preset: str = "",
                       viewer_outcome: str = "", style_blend_mode: str = "clone",
                       custom_audience: str = "", custom_tone: str = "",
                       api_key: str = None, structured: dict = None) -> dict:
    """
    PHASE 1: Generate a flowing narration script using Gemini.

    Returns the narration organized by acts/beats — no timestamps or scene table.
    This output feeds into production (generate_production_table).

    Returns:
        Dict with 'success' and 'narration' (the parsed JSON), or 'error'
    """
    prompt = build_script_prompt(
        template_id=template_id,
        topic=topic,
        research_dossier=research_dossier,
        duration_minutes=duration_minutes,
        audience=audience,
        tone=tone,
        focus=focus,
        style_guide=style_guide,
        selected_title=selected_title,
        format_preset=format_preset,
        viewer_outcome=viewer_outcome,
        style_blend_mode=style_blend_mode,
        custom_audience=custom_audience,
        custom_tone=custom_tone,
        structured=structured,
    )

    raw_response = generate_content(prompt, model_name="gemini-3-flash-preview", api_key=api_key)

    if not raw_response or raw_response.startswith("Error:"):
        return {"error": raw_response or "Gemini returned an empty response for narration."}

    try:
        narration_data = _parse_json_response(raw_response)
        return {"success": True, "narration": narration_data}
    except json.JSONDecodeError:
        return {
            "success": True,
            "narration": {
                "title": topic,
                "raw_text": raw_response,
                "parse_error": "Could not parse Phase 1 narration as JSON."
            }
        }


def auto_suggest_tone(template_id: str, selected_title: str,
                      audience: str = "General", api_key: str = None) -> dict:
    """Auto-suggest the best tone for a title + audience combination."""
    prompt = build_tone_suggestion_prompt(
        template_id=template_id,
        selected_title=selected_title,
        audience=audience,
    )
    raw_response = generate_content(prompt, model_name="gemini-3-flash-preview", api_key=api_key)
    if not raw_response or raw_response.startswith("Error:"):
        return {"suggested_tone": "Conversational", "reasoning": "Default (auto-suggest unavailable)"}
    try:
        return _parse_json_response(raw_response)
    except json.JSONDecodeError:
        return {"suggested_tone": "Conversational", "reasoning": "Default (parse error)"}


def regenerate_beats(topic: str, template_id: str, research_dossier: str,
                     full_narration: dict, target_act: str = None,
                     target_beat_indices: list = None, mode: str = "restyle",
                     audience: str = "General", tone: str = "",
                     duration_minutes: int = 10, api_key: str = None,
                     structured: dict = None) -> dict:
    """
    Regenerate specific beats or an entire act within a narration.

    Args:
        topic: Video topic
        template_id: Template being used
        research_dossier: Full research dossier text
        full_narration: Complete narration JSON {title, narration: [...]}
        target_act: If set, regenerate all beats in this act
        target_beat_indices: List of 0-based beat indices to regenerate
        mode: 'restyle' or 'reimagine'
        audience, tone, duration_minutes: Context for the prompt
        api_key: Gemini API key

    Returns:
        Dict with 'success' and 'beats' (list of regenerated beats), or 'error'
    """
    prompt = build_beat_regeneration_prompt(
        template_id=template_id,
        topic=topic,
        research_dossier=research_dossier,
        full_narration=full_narration,
        target_beat_indices=target_beat_indices or [],
        target_act=target_act,
        mode=mode,
        audience=audience,
        tone=tone,
        duration_minutes=duration_minutes,
        structured=structured,
    )

    if prompt.startswith("Error:"):
        return {"error": prompt}

    raw_response = generate_content(prompt, model_name="gemini-3-flash-preview", api_key=api_key)

    if not raw_response or raw_response.startswith("Error:"):
        return {"error": raw_response or "Gemini returned an empty response for beat regeneration."}

    try:
        regenerated = _parse_json_response(raw_response)
        if isinstance(regenerated, dict):
            regenerated = regenerated.get("beats", [regenerated])
        if not isinstance(regenerated, list):
            regenerated = [regenerated]
        return {"success": True, "beats": regenerated}
    except json.JSONDecodeError:
        return {"error": f"Could not parse regenerated beats as JSON: {raw_response[:200]}"}


def generate_production_table(narration_json: dict, duration_minutes: int = 10,
                              style_analysis: dict = None,
                              aspect_ratio: str = "16:9",
                              api_key: str = None,
                              pacing_tier: str = "Standard",
                              quality_mode: str = "fast",
                              creative_direction: dict = None,
                              cast: dict = None,
                              format_preset: str = "") -> dict:
    """
    Generate production-ready prompts from narration beats using the 6-phase pipeline.

    Pipeline: Script Doctor → Director → Cinematographer → Storyboard → Continuity → DP

    The Script Doctor runs ONCE on the full narration before batching.
    All subsequent phases run per-batch with the shared Visual Brief.

    Args:
        narration_json: Narration object {title, narration: [{act, beat, text}, ...]}
        duration_minutes: Target video length
        style_analysis: Structured style dict {style_summary, style_intent, prompt_schema}
        aspect_ratio: Video aspect ratio
        api_key: Gemini API key
        pacing_tier: Pacing speed (Meditative, Relaxed, Standard, High Energy, Frenetic)
        quality_mode: Deprecated — always uses 6-phase pipeline (kept for backward compat)
    """
    beats = narration_json.get("narration", [])

    if not beats:
        return {"error": "No narration beats found. Generate narration first."}

    title = narration_json.get("title", "Untitled")

    # Normalize script: Split massive beats to avoid token limits.
    # Essential for manual pasted JSON or overly verbose generation.
    import re
    MAX_WORDS_PER_BEAT = 45
    normalized_beats = []
    for beat in beats:
        act = beat.get("act", "ACT 1")
        beat_name = beat.get("beat", "Beat")
        text = beat.get("text", beat.get("narration", "")).strip()
        
        if len(text.split()) > MAX_WORDS_PER_BEAT:
            sentences = re.split(r'(?<=[.!?]) +', text)
            current_chunk = ""
            for sentence in sentences:
                proposed_length = len(current_chunk.split()) + len(sentence.split())
                if proposed_length > MAX_WORDS_PER_BEAT and current_chunk:
                    normalized_beats.append({"act": act, "beat": beat_name, "text": current_chunk.strip()})
                    current_chunk = sentence
                else:
                    current_chunk = (current_chunk + " " + sentence).strip()
            if current_chunk:
                normalized_beats.append({"act": act, "beat": beat_name, "text": current_chunk.strip()})
        else:
            normalized_beats.append({"act": act, "beat": beat_name, "text": text})
            
    beats = normalized_beats
    narration_json["narration"] = beats # Update original object so _generate_single_batch uses correct chunks

    # Auto-map pacing tier from format preset if user hasn't explicitly changed it
    if format_preset:
        from research_templates import FORMAT_PRESETS
        preset_data = FORMAT_PRESETS.get(format_preset, {})
        auto_tier = preset_data.get("auto_pacing_tier")
        if auto_tier and pacing_tier == "Standard":  # only override default
            pacing_tier = auto_tier
            print(f"[Production] Auto-selected pacing tier '{pacing_tier}' from preset '{format_preset}'")

    # Define pacing parameters
    PACE_TIERS = {
        "Meditative": {"beats_per_batch": 12, "words_per_shot": 15},
        "Relaxed": {"beats_per_batch": 10, "words_per_shot": 11},
        "Standard": {"beats_per_batch": 8, "words_per_shot": 9},
        "High Energy": {"beats_per_batch": 5, "words_per_shot": 5},
        "Frenetic": {"beats_per_batch": 3, "words_per_shot": 3}
    }
    
    tier_config = PACE_TIERS.get(pacing_tier, PACE_TIERS["Standard"])
    BEATS_PER_BATCH = tier_config["beats_per_batch"]
    WORDS_PER_SHOT_TARGET = tier_config["words_per_shot"]

    # ── Phase 0: Script Doctor (runs ONCE before batching) ──
    print(f"[Production] Phase 0: Script Doctor analyzing full narration...")
    try:
        script_doctor_prompt = build_script_doctor_prompt(narration_json, style_analysis, creative_direction)
        raw_brief = generate_content(script_doctor_prompt, model_name="gemini-2.5-flash",
                                      temperature=0.3, api_key=api_key)
        if raw_brief and not raw_brief.startswith("Error:"):
            visual_brief = _parse_json_response(raw_brief)
            brief_count = len(visual_brief.get("visual_brief", []))
            print(f"[Production] Script Doctor complete: {brief_count} beat briefs generated")
        else:
            print(f"[Production] Script Doctor failed: {(raw_brief or 'empty')[:100]}. Continuing without brief.")
            visual_brief = None
    except Exception as e:
        print(f"[Production] Script Doctor error: {e}. Continuing without brief.")
        visual_brief = None

    # Always use 6-phase pipeline
    batch_fn = _generate_single_batch_6phase
    mode_label = "6-Phase"

    # Small narrations: single call
    if len(beats) <= BEATS_PER_BATCH + 2:
        print(f"[Production] Mode: {mode_label}")
        return batch_fn(narration_json, duration_minutes,
                        style_analysis=style_analysis,
                        aspect_ratio=aspect_ratio,
                        api_key=api_key,
                        pacing_tier=pacing_tier,
                        creative_direction=creative_direction,
                        cast=cast,
                        format_preset=format_preset,
                        visual_brief=visual_brief)

    # Large narrations: batch by act
    MAX_CONCURRENT_BATCHES = 3
    print(f"[Production] Large narration ({len(beats)} beats). Mode: {mode_label}. Batching by act...")

    # Group beats by act
    acts = {}
    for beat in beats:
        act_name = beat.get("act", "Unknown")
        if act_name not in acts:
            acts[act_name] = []
        acts[act_name].append(beat)

    # Build batches from acts (split large acts into sub-batches)
    batches = []
    for act_name, act_beats in acts.items():
        if len(act_beats) > BEATS_PER_BATCH:
            for i in range(0, len(act_beats), BEATS_PER_BATCH):
                batches.append(act_beats[i:i + BEATS_PER_BATCH])
        else:
            batches.append(act_beats)

    all_shots = []
    all_continuity = []
    all_challenging = []
    style_summary = ""

    # Calculate total words for proportional duration splitting
    total_words = sum(len(b.get("text", b.get("narration", "")).split()) for b in beats)
    estimated_total_shots = max(1, int(total_words / WORDS_PER_SHOT_TARGET))

    MAX_RETRIES = 2

    def process_batch(batch_idx, batch_beats):
        # Calculate offset based on previous words
        previous_beats = []
        for b in batches[:batch_idx - 1]:
            previous_beats.extend(b)

        previous_words = sum(len(b.get("text", b.get("narration", "")).split()) for b in previous_beats)
        batch_words = sum(len(b.get("text", b.get("narration", "")).split()) for b in batch_beats)

        # Proportional duration and shot offset
        batch_duration = max(1, round(duration_minutes * batch_words / total_words)) if total_words > 0 else duration_minutes
        shot_offset = max(1, round(estimated_total_shots * previous_words / total_words)) + 1 if total_words > 0 else 1

        batch_narration = {
            "title": title,
            "hook_type": narration_json.get("hook_type", ""),
            "narration": batch_beats,
        }

        print(f"[Production] Batch {batch_idx}/{len(batches)}: "
              f"{len(batch_beats)} beats, ~{batch_words} words, ~{batch_duration}min (Start shot: {shot_offset}) - STARTED")

        last_error = None
        for attempt in range(1, MAX_RETRIES + 2):  # attempts 1, 2, 3
            result = batch_fn(batch_narration, batch_duration,
                              style_analysis=style_analysis,
                              aspect_ratio=aspect_ratio,
                              api_key=api_key,
                              shot_start_number=shot_offset,
                              batch_label=f"batch {batch_idx}/{len(batches)}",
                              pacing_tier=pacing_tier,
                              creative_direction=creative_direction,
                              cast=cast,
                              format_preset=format_preset,
                              visual_brief=visual_brief)

            if "error" not in result:
                break  # success

            last_error = result["error"]
            if attempt <= MAX_RETRIES:
                wait_sec = attempt * 3  # 3s, 6s backoff
                print(f"[Production] Batch {batch_idx} attempt {attempt} failed: {last_error}. "
                      f"Retrying in {wait_sec}s... ({MAX_RETRIES - attempt + 1} retries left)")
                time.sleep(wait_sec)
            else:
                print(f"[Production] Batch {batch_idx} FAILED after {MAX_RETRIES + 1} attempts: {last_error}")
                return {"batch_idx": batch_idx, "error": last_error}

        pt = result.get("production_table", {})
        batch_shots = pt.get("shots", [])
        print(f"[Production] Batch {batch_idx} COMPLETE: {len(batch_shots)} shots")

        return {
            "batch_idx": batch_idx,
            "shots": batch_shots,
            "continuity_notes": pt.get("continuity_notes", []),
            "challenging_shots": pt.get("production_notes", {}).get("challenging_shots", []),
            "style_summary": pt.get("style_summary", ""),
        }

    # Process batches in parallel
    batch_results = {}
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_BATCHES) as executor:
        future_to_batch = {
            executor.submit(process_batch, idx + 1, batch_beats): idx + 1
            for idx, batch_beats in enumerate(batches)
        }
        for future in as_completed(future_to_batch):
            batch_idx = future_to_batch[future]
            try:
                result = future.result()
                batch_results[result["batch_idx"]] = result
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"[Production] Batch {batch_idx} exception: {e}")
                batch_results[batch_idx] = {"batch_idx": batch_idx, "error": str(e)}

    # Reconstruct and NORMALIZE in order
    final_shots = []
    final_continuity = []
    final_challenging = []
    failed_batches = []

    current_shot_num = 1

    for batch_idx in sorted(batch_results.keys()):
        result = batch_results[batch_idx]
        if "error" in result:
            failed_batches.append({
                "batch": batch_idx,
                "total_batches": len(batches),
                "error": result["error"],
            })
            print(f"[Production] WARNING: Batch {batch_idx}/{len(batches)} failed permanently — "
                  f"these scenes will be missing from the final table. Error: {result['error']}")
            continue

        batch_shots = result.get("shots", [])
        batch_continuity = result.get("continuity_notes", [])

        # Map old Gemini-generated numbers to new global sequential numbers
        shot_map = {}

        for shot in batch_shots:
            old_num = str(shot.get("shot_number", ""))
            new_num = str(current_shot_num)
            shot_map[old_num] = new_num

            shot["shot_number"] = new_num
            # Note: we don't fix timestamps globally here because they are usually
            # relative to the clip start or already handled by Gemini's sense of pacing.

            final_shots.append(shot)
            current_shot_num += 1

        # Adjust continuity notes to point to new global numbers
        for note in batch_continuity:
            from_old = str(note.get("from_shot", ""))
            to_old = str(note.get("to_shot", ""))

            # Only include if we can map the shots (they belong to this batch)
            if from_old in shot_map:
                note["from_shot"] = shot_map[from_old]
            if to_old in shot_map:
                note["to_shot"] = shot_map[to_old]

            final_continuity.append(note)

        final_challenging.extend(result.get("challenging_shots", []))
        if batch_idx == 1:
            style_summary = result.get("style_summary", "")

    if not final_shots:
        return {"error": "All batches failed to produce shots."}

    # Build warning message for partial failures
    batch_warning = None
    if failed_batches:
        failed_labels = [f"batch {fb['batch']}/{fb['total_batches']}" for fb in failed_batches]
        batch_warning = (
            f"Warning: {len(failed_batches)} of {len(batches)} section(s) failed after retries "
            f"({', '.join(failed_labels)}). The production table has {len(final_shots)} shots "
            f"but some scenes from the middle of your script may be missing. "
            f"You can regenerate to try again."
        )
        print(f"[Production] {batch_warning}")

    merged = {
        "title": title,
        "aspect_ratio": aspect_ratio,
        "style_summary": style_summary,
        "total_shots": len(final_shots),
        "shots": final_shots,
        "continuity_notes": final_continuity,
        "production_notes": {
            "challenging_shots": final_challenging,
            "recommended_workflow": "Generate in batch order for visual continuity",
            "post_production": "Review cross-batch transitions for consistency",
        },
    }

    if batch_warning:
        merged["batch_warning"] = batch_warning
        merged["failed_batches"] = failed_batches

    print(f"[Production] Complete: {len(final_shots)} total shots (normalized 1-{len(final_shots)}) from {len(batches)} batches")
    return {"success": True, "production_table": merged}


def _generate_single_batch(narration_json: dict, duration_minutes: int = 10,
                           style_analysis: dict = None,
                           aspect_ratio: str = "16:9",
                           api_key: str = None,
                           shot_start_number: int = 1,
                           batch_label: str = "",
                           pacing_tier: str = "Standard",
                           creative_direction: dict = None,
                           cast: dict = None,
                           format_preset: str = "") -> dict:
    """Generate production table for a single batch of narration beats."""
    prompt = build_production_prompt(
        narration_json=narration_json,
        duration_minutes=duration_minutes,
        style_analysis=style_analysis,
        aspect_ratio=aspect_ratio,
        shot_start_number=shot_start_number,
        pacing_tier=pacing_tier,
        creative_direction=creative_direction,
        format_preset=format_preset
    )

    label = f" ({batch_label})" if batch_label else ""
    print(f"[Production] Generating production table{label}...")
    raw_response = generate_content(prompt, model_name="gemini-3.1-pro-preview", temperature=0.1, api_key=api_key)

    if not raw_response or raw_response.startswith("Error:"):
        return {"error": raw_response or "Gemini returned an empty response for production table."}

    try:
        production_data = _parse_json_response(raw_response)
        shot_count = len(production_data.get("shots", []))
        print(f"[Production] Got {shot_count} shots{label}")
        return {"success": True, "production_table": production_data}
    except json.JSONDecodeError:
        return {
            "success": True,
            "production_table": {
                "title": narration_json.get("title", "Untitled"),
                "raw_text": raw_response,
                "parse_error": f"Could not parse production JSON{label}."
            }
        }


def _generate_single_batch_3phase(narration_json: dict, duration_minutes: int = 10,
                                   style_analysis: dict = None,
                                   aspect_ratio: str = "16:9",
                                   api_key: str = None,
                                   shot_start_number: int = 1,
                                   batch_label: str = "",
                                   pacing_tier: str = "Standard",
                                   creative_direction: dict = None,
                                   cast: dict = None,
                                   format_preset: str = "") -> dict:
    """
    Generate production table using the 3-phase pipeline (Max Quality mode).

    Phase 1: Director — editorial cuts (where to split, duration, emotion)
    Phase 2: Storyboard Artist — visual composition (what each shot shows)
    Phase 3: DP — final prompts (first_frame, last_frame, veo)

    Same signature as _generate_single_batch() for drop-in compatibility.
    """
    label = f" ({batch_label})" if batch_label else ""

    # ── Phase 1: Director ──
    print(f"[Production 3-Phase] Phase 1: Director{label}...")
    director_prompt = build_director_prompt(
        narration_json=narration_json,
        duration_minutes=duration_minutes,
        shot_start_number=shot_start_number,
        pacing_tier=pacing_tier,
        creative_direction=creative_direction,
        format_preset=format_preset,
    )
    raw_director = generate_content(
        director_prompt, model_name="gemini-3.1-pro-preview",
        temperature=0.1, api_key=api_key
    )
    if not raw_director or raw_director.startswith("Error:"):
        return {"error": f"Phase 1 (Director) failed{label}: {raw_director or 'empty response'}"}

    try:
        director_data = _parse_json_response(raw_director)
        director_shots = director_data.get("shots", [])
    except json.JSONDecodeError as e:
        return {"error": f"Phase 1 (Director) JSON parse failed{label}: {e}"}

    print(f"[Production 3-Phase] Phase 1 complete: {len(director_shots)} shots{label}")

    # ── Phase 2: Storyboard Artist ──
    print(f"[Production 3-Phase] Phase 2: Storyboard Artist{label}...")
    style_intent = style_analysis.get("style_intent", {}) if style_analysis else {}
    storyboard_prompt = build_storyboard_prompt(
        director_shots=director_shots,
        narration_json=narration_json,
        style_intent=style_intent,
        creative_direction=creative_direction,
        cast=cast,
    )
    raw_storyboard = generate_content(
        storyboard_prompt, model_name="gemini-3.1-pro-preview",
        temperature=0.1, api_key=api_key
    )
    if not raw_storyboard or raw_storyboard.startswith("Error:"):
        return {"error": f"Phase 2 (Storyboard) failed{label}: {raw_storyboard or 'empty response'}"}

    try:
        storyboard_data = _parse_json_response(raw_storyboard)
        storyboard_shots = storyboard_data.get("shots", [])
    except json.JSONDecodeError as e:
        return {"error": f"Phase 2 (Storyboard) JSON parse failed{label}: {e}"}

    print(f"[Production 3-Phase] Phase 2 complete: {len(storyboard_shots)} shots{label}")

    # ── Phase 3: Director of Photography ──
    print(f"[Production 3-Phase] Phase 3: Director of Photography{label}...")
    title = narration_json.get("title", "Untitled")
    dp_prompt = build_dp_prompt(
        storyboard_shots=storyboard_shots,
        style_analysis=style_analysis,
        aspect_ratio=aspect_ratio,
        cast=cast,
        title=title,
        creative_direction=creative_direction,
    )
    raw_dp = generate_content(
        dp_prompt, model_name="gemini-3.1-pro-preview",
        temperature=0.1, api_key=api_key
    )
    if not raw_dp or raw_dp.startswith("Error:"):
        return {"error": f"Phase 3 (DP) failed{label}: {raw_dp or 'empty response'}"}

    try:
        production_data = _parse_json_response(raw_dp)
        shot_count = len(production_data.get("shots", []))
        print(f"[Production 3-Phase] Phase 3 complete: {shot_count} shots{label}")
        return {"success": True, "production_table": production_data}
    except json.JSONDecodeError:
        return {
            "success": True,
            "production_table": {
                "title": title,
                "raw_text": raw_dp,
                "parse_error": f"Could not parse Phase 3 (DP) JSON{label}."
            }
        }


def _generate_single_batch_6phase(narration_json: dict, duration_minutes: int = 10,
                                   style_analysis: dict = None,
                                   aspect_ratio: str = "16:9",
                                   api_key: str = None,
                                   shot_start_number: int = 1,
                                   batch_label: str = "",
                                   pacing_tier: str = "Standard",
                                   creative_direction: dict = None,
                                   cast: dict = None,
                                   format_preset: str = "",
                                   visual_brief: dict = None) -> dict:
    """
    Generate production table using the 6-phase pipeline.

    Phase 0: Script Doctor (pre-computed, passed via visual_brief)
    Phase 1: Director — editorial cuts + camera intent + emotional arc
    Phase 2: Cinematographer — camera technique from 62-technique library
    Phase 3: Storyboard Artist — layered visual compositions
    Phase 4: Continuity Supervisor — review + auto-fix
    Phase 5: DP — final prompts with lighting vocabulary
    """
    label = f" ({batch_label})" if batch_label else ""
    title = narration_json.get("title", "Untitled")
    style_intent = style_analysis.get("style_intent", {}) if style_analysis else {}

    # ── Phase 1: Director ──
    print(f"[Production 6-Phase] Phase 1: Director{label}...")
    director_prompt = build_director_prompt(
        narration_json=narration_json,
        duration_minutes=duration_minutes,
        shot_start_number=shot_start_number,
        pacing_tier=pacing_tier,
        creative_direction=creative_direction,
        format_preset=format_preset,
        visual_brief=visual_brief,
    )
    raw_director = generate_content(
        director_prompt, model_name="gemini-2.5-flash",
        temperature=0.1, api_key=api_key
    )
    if not raw_director or raw_director.startswith("Error:"):
        return {"error": f"Phase 1 (Director) failed{label}: {raw_director or 'empty response'}"}
    try:
        director_data = _parse_json_response(raw_director)
        director_shots = director_data.get("shots", [])
    except json.JSONDecodeError as e:
        return {"error": f"Phase 1 (Director) JSON parse failed{label}: {e}"}
    print(f"[Production 6-Phase] Phase 1 complete: {len(director_shots)} shots{label}")

    # ── Phase 2: Cinematographer ──
    print(f"[Production 6-Phase] Phase 2: Cinematographer{label}...")
    cinematographer_prompt = build_cinematographer_prompt(
        director_shots=director_shots,
        visual_brief=visual_brief,
    )
    raw_cinematographer = generate_content(
        cinematographer_prompt, model_name="gemini-2.5-flash",
        temperature=0.2, api_key=api_key
    )
    if not raw_cinematographer or raw_cinematographer.startswith("Error:"):
        return {"error": f"Phase 2 (Cinematographer) failed{label}: {raw_cinematographer or 'empty response'}"}
    try:
        cinematographer_data = _parse_json_response(raw_cinematographer)
        cinematographer_shots = cinematographer_data.get("shots", [])
    except json.JSONDecodeError as e:
        return {"error": f"Phase 2 (Cinematographer) JSON parse failed{label}: {e}"}
    print(f"[Production 6-Phase] Phase 2 complete: {len(cinematographer_shots)} shots{label}")

    # ── Phase 3: Storyboard Artist ──
    print(f"[Production 6-Phase] Phase 3: Storyboard Artist{label}...")
    storyboard_prompt = build_storyboard_prompt(
        director_shots=cinematographer_shots,
        narration_json=narration_json,
        style_intent=style_intent,
        creative_direction=creative_direction,
        cast=cast,
        visual_brief=visual_brief,
    )
    raw_storyboard = generate_content(
        storyboard_prompt, model_name="gemini-2.5-flash",
        temperature=0.1, api_key=api_key
    )
    if not raw_storyboard or raw_storyboard.startswith("Error:"):
        return {"error": f"Phase 3 (Storyboard) failed{label}: {raw_storyboard or 'empty response'}"}
    try:
        storyboard_data = _parse_json_response(raw_storyboard)
        storyboard_shots = storyboard_data.get("shots", [])
    except json.JSONDecodeError as e:
        return {"error": f"Phase 3 (Storyboard) JSON parse failed{label}: {e}"}
    print(f"[Production 6-Phase] Phase 3 complete: {len(storyboard_shots)} shots{label}")

    # ── Phase 4: Continuity Supervisor ──
    print(f"[Production 6-Phase] Phase 4: Continuity Supervisor{label}...")
    continuity_prompt = build_continuity_supervisor_prompt(
        storyboard_shots=storyboard_shots,
        visual_brief=visual_brief,
    )
    raw_continuity = generate_content(
        continuity_prompt, model_name="gemini-2.5-flash",
        temperature=0.05, api_key=api_key
    )
    if not raw_continuity or raw_continuity.startswith("Error:"):
        # Continuity is non-critical — fall through with uncorrected shots
        print(f"[Production 6-Phase] Phase 4 failed{label} — continuing with uncorrected shots")
        corrected_shots = storyboard_shots
    else:
        try:
            continuity_data = _parse_json_response(raw_continuity)
            corrected_shots = continuity_data.get("shots", storyboard_shots)
            modified = continuity_data.get("review_summary", {}).get("shots_modified", 0)
            print(f"[Production 6-Phase] Phase 4 complete: {modified} shots modified{label}")
        except json.JSONDecodeError:
            print(f"[Production 6-Phase] Phase 4 parse failed{label} — using uncorrected shots")
            corrected_shots = storyboard_shots

    # ── Phase 5: DP ──
    print(f"[Production 6-Phase] Phase 5: DP{label}...")
    dp_prompt = build_dp_prompt(
        storyboard_shots=corrected_shots,
        style_analysis=style_analysis,
        aspect_ratio=aspect_ratio,
        title=title,
        creative_direction=creative_direction,
        cast=cast,
        visual_brief=visual_brief,
    )
    raw_dp = generate_content(
        dp_prompt, model_name="gemini-2.5-flash",
        temperature=0.1, api_key=api_key
    )
    if not raw_dp or raw_dp.startswith("Error:"):
        return {"error": f"Phase 5 (DP) failed{label}: {raw_dp or 'empty response'}"}

    try:
        production_data = _parse_json_response(raw_dp)
        shot_count = len(production_data.get("shots", []))
        print(f"[Production 6-Phase] Phase 5 complete: {shot_count} shots with prompts{label}")
        return {"success": True, "production_table": production_data}
    except json.JSONDecodeError:
        return {
            "success": True,
            "production_table": {
                "title": title,
                "raw_text": raw_dp,
                "parse_error": f"Could not parse Phase 5 (DP) JSON{label}."
            }
        }


def start_deep_research(topic: str, template_id: str, api_key: str = None) -> dict:
    """
    Start an async deep research session using the Deep Research Agent.

    Uses the Interactions API with background=True. Returns immediately
    with an interaction_id that can be polled for results.

    Returns:
        Dict with 'interaction_id' and 'status', or 'error'
    """
    from google import genai

    template = get_template(template_id)
    template_name = template['metadata']['name'] if template else template_id
    analysis_questions = template['research_config']['analysis_questions'] if template else [
        f"Provide a comprehensive analysis of {topic}"
    ]

    questions_text = "\n".join(f"- {q}" for q in analysis_questions)

    research_input = f"""Conduct deep, comprehensive research on the following topic.

TOPIC: {topic}
RESEARCH TEMPLATE: {template_name}

Answer each of these analysis questions with specific facts, names, numbers, and dates:
{questions_text}

Provide a thorough research report with:
- Detailed answers to each question above
- Specific facts, statistics, and data points
- Named sources for key claims
- A summary of all findings"""

    try:
        if not api_key:
            raise ValueError("No API key provided. Please save your Gemini API key in Settings.")
        client = genai.Client(api_key=api_key)

        interaction = client.interactions.create(
            input=research_input,
            agent='deep-research-pro-preview-12-2025',
            background=True
        )

        print(f"[Deep Research] Started interaction: {interaction.id}")
        return {
            "interaction_id": interaction.id,
            "status": "in_progress",
        }

    except Exception as e:
        print(f"[Deep Research] Failed to start: {e}")
        return {"error": f"Deep Research failed to start: {str(e)}"}


def poll_deep_research(interaction_id: str, api_key: str = None) -> dict:
    """
    Poll a running deep research interaction for results.

    Returns:
        Dict with 'status' ('in_progress', 'completed', 'failed')
        and 'result' (the research text) when completed.
    """
    from google import genai

    try:
        if not api_key:
            raise ValueError("No API key provided. Please save your Gemini API key in Settings.")
        client = genai.Client(api_key=api_key)

        interaction = client.interactions.get(interaction_id)

        if interaction.status == "completed":
            result_text = interaction.outputs[-1].text if interaction.outputs else ""
            print(f"[Deep Research] Completed: {len(result_text)} chars")
            return {
                "status": "completed",
                "result": result_text,
            }
        elif interaction.status == "failed":
            error_msg = str(getattr(interaction, 'error', 'Unknown error'))
            print(f"[Deep Research] Failed: {error_msg}")
            return {
                "status": "failed",
                "error": error_msg,
            }
        else:
            print(f"[Deep Research] Status: {interaction.status}")
            return {
                "status": "in_progress",
            }

    except Exception as e:
        print(f"[Deep Research] Poll error: {e}")
        return {"status": "failed", "error": str(e)}


# ═══════════════════════════════════════════════════════════════════
#  STRUCTURED RESEARCH PIPELINE
#  (Planner → parallel Pro+Search sub-researchers → merger with stable ids)
# ═══════════════════════════════════════════════════════════════════

import re as _re
from datetime import datetime as _datetime


def _extract_grounding_sources(response) -> list:
    """Pull {url, title, snippet} entries from Gemini's grounding_metadata.

    The google-genai SDK exposes grounding data under candidates[0].grounding_metadata,
    but field names drift across versions (grounding_chunks vs grounding_supports).
    We try multiple shapes; on failure, return [] so the caller can fall back to
    regex-scraping URLs from response.text.
    """
    sources = []
    try:
        candidates = getattr(response, 'candidates', None) or []
        if not candidates:
            return []
        gm = getattr(candidates[0], 'grounding_metadata', None)
        if not gm:
            return []

        # Primary SDK shape: grounding_chunks[].web.{uri,title}
        chunks = getattr(gm, 'grounding_chunks', None) or []
        for chunk in chunks:
            web = getattr(chunk, 'web', None)
            if not web:
                continue
            url = getattr(web, 'uri', None) or getattr(web, 'url', None)
            title = getattr(web, 'title', None) or ''
            if url:
                sources.append({'url': url, 'title': title, 'snippet': ''})

        # Enrich with grounding_supports if available (maps chunks → text segments).
        if sources:
            supports = getattr(gm, 'grounding_supports', None) or []
            for s in supports:
                seg = getattr(s, 'segment', None)
                indices = getattr(s, 'grounding_chunk_indices', None) or []
                seg_text = getattr(seg, 'text', '') if seg else ''
                for idx in indices:
                    if 0 <= idx < len(sources) and seg_text and not sources[idx].get('snippet'):
                        sources[idx]['snippet'] = seg_text[:400]
    except Exception as e:
        print(f"[Research-Structured] Grounding extract failed: {e}")

    # De-dupe by URL
    seen = set()
    unique = []
    for s in sources:
        key = s.get('url')
        if key and key not in seen:
            seen.add(key)
            unique.append(s)
    return unique


def _scrape_urls_from_text(text: str) -> list:
    """Last-resort fallback: regex-extract URLs from text."""
    if not text:
        return []
    urls = _re.findall(r'https?://[^\s\)\]\}<>"\']+', text)
    seen = set()
    out = []
    for u in urls:
        u = u.rstrip('.,;:')
        if u and u not in seen:
            seen.add(u)
            out.append({'url': u, 'title': '', 'snippet': ''})
    return out


def _empty_structured(topic: str, template_id: str, mode: str, model: str) -> dict:
    """Return the canonical empty schema."""
    return {
        'meta': {
            'topic': topic,
            'template_id': template_id,
            'mode': mode,
            'model': model,
            'generated_at': _datetime.utcnow().isoformat() + 'Z',
        },
        'sections': [],
        'claims': [],
        'sources': [],
    }


def _markdown_from_structured(structured: dict) -> str:
    """Render the structured schema back into the legacy dossier markdown shape.

    Mirrors build_research_dossier()'s `# Research Dossier / ## Template / ### heading`
    layout so the UI renders unchanged.
    """
    if not structured or not isinstance(structured, dict):
        return ""

    meta = structured.get('meta', {}) or {}
    topic = meta.get('topic', '')
    template_id = meta.get('template_id', '')
    mode = meta.get('mode', '')

    template = get_template(template_id)
    template_name = template['metadata']['name'] if template else (template_id or 'General')

    parts = [
        f"# Research Dossier: {topic}",
        f"## Template: {template_name}",
        f"## Research Mode: {mode}",
        "",
    ]

    claims_by_id = {c.get('id'): c for c in structured.get('claims', []) if c.get('id')}
    sources_by_id = {s.get('id'): s for s in structured.get('sources', []) if s.get('id')}

    for section in structured.get('sections', []) or []:
        title = section.get('title', 'Section')
        summary = section.get('summary', '')
        claim_ids = section.get('claim_ids', []) or []

        parts.append(f"### {title}")
        if summary:
            parts.append(summary)
            parts.append("")

        for cid in claim_ids:
            claim = claims_by_id.get(cid)
            if not claim:
                continue
            text = claim.get('text', '')
            src_ids = claim.get('source_ids', []) or []
            cites = " ".join(f"[{sid}]" for sid in src_ids if sid in sources_by_id)
            line = f"- {text}"
            if cites:
                line += f" {cites}"
            parts.append(line)

        parts.append("")

    if structured.get('sources'):
        parts.append("### Sources")
        for s in structured['sources']:
            sid = s.get('id', '')
            url = s.get('url', '')
            title = s.get('title') or url or '(untitled)'
            publisher = s.get('publisher', '')
            line = f"- [{sid}] {title}"
            if publisher:
                line += f" — {publisher}"
            if url:
                line += f" ({url})"
            parts.append(line)

    return "\n".join(parts)


_STRUCTURED_CLAIM_SCHEMA_PROMPT = """Respond ONLY with a valid JSON object (no markdown fences) matching this shape:
{
  "section": { "title": "<section heading>", "summary": "<1-3 sentence section summary>" },
  "claims": [
    { "text": "<a single factual claim>", "confidence": "high|med|low", "source_urls": ["<url1>", "<url2>"] }
  ]
}
Rules:
- Emit 8-20 distinct claims per sub-query.
- Every claim MUST cite at least one source_url drawn from the web search results. Never fabricate URLs.
- Use "high" confidence only for facts stated by official/primary sources; "med" for analysis/news; "low" for opinion."""


def _planner_expand_subqueries(topic: str, template_id: str, api_key: str) -> list:
    """Use Flash (no search) to expand template search_layers into concrete sub-queries."""
    template = get_template(template_id)
    if not template:
        return [{"name": "General", "query": f"Comprehensive research on {topic}"}]

    layers = template["research_config"].get("search_layers", [])
    analysis_qs = template["research_config"].get("analysis_questions", [])

    layer_text = "\n".join(
        f"- {l.get('name','?')}: {l.get('query_template','{topic}').format(topic=topic)}"
        for l in layers
    )
    qs_text = "\n".join(f"- {q}" for q in analysis_qs[:6])

    planner_prompt = f"""You are planning a research project. Expand the research layers below into
3-6 SPECIFIC, CONCRETE sub-queries. Each sub-query will be run against Google Search independently.

TOPIC: {topic}

RESEARCH LAYERS:
{layer_text}

ANALYSIS QUESTIONS WE NEED TO ANSWER:
{qs_text}

Return ONLY JSON:
{{
  "sub_queries": [
    {{"name": "<short section name>", "query": "<concrete Google search query>"}}
  ]
}}"""

    raw = generate_content(
        planner_prompt,
        model_name="gemini-3-flash-preview",
        temperature=0.3,
        api_key=api_key,
        max_output_tokens=4096,
    )
    fallback = [
        {"name": l.get("name", f"Layer {i+1}"),
         "query": l.get("query_template", "{topic}").format(topic=topic)}
        for i, l in enumerate(layers[:5])
    ]
    if not raw or raw.startswith("Error:"):
        return fallback
    try:
        data = _parse_json_response(raw)
        subs = data.get("sub_queries", [])
        if isinstance(subs, list) and subs:
            # Keep only entries with both name + query
            cleaned = [s for s in subs if isinstance(s, dict) and s.get("query")]
            return cleaned or fallback
        return fallback
    except (json.JSONDecodeError, ValueError):
        return fallback


def _run_sub_researcher(sub_query: dict, topic: str, api_key: str, mode: str) -> dict:
    """Run one Pro+Search call for a sub-query. Returns {section, claims[], sources[]}."""
    name = sub_query.get("name", "Section")
    query = sub_query.get("query", topic)
    model_name = "gemini-3.1-pro-preview" if mode == "deep" else "gemini-3-flash-preview"

    prompt = f"""You are a research analyst. Use Google Search to answer the question below.
Return only factual claims with the source URLs that support them.

SECTION: {name}
QUESTION: {query}
TOPIC CONTEXT: {topic}

{_STRUCTURED_CLAIM_SCHEMA_PROMPT}

Return ONLY the JSON object."""

    try:
        response = generate_content(
            prompt,
            model_name=model_name,
            use_search=True,
            temperature=0.1,
            api_key=api_key,
            max_output_tokens=32768,
            return_response=True,
        )
    except Exception as e:
        print(f"[Research-Structured] Sub-researcher '{name}' failed: {e}")
        return {"section": {"title": name, "summary": ""}, "claims": [], "sources": []}

    text = getattr(response, 'text', None) or ""
    grounding_sources = _extract_grounding_sources(response)
    if not grounding_sources:
        grounding_sources = _scrape_urls_from_text(text)

    # Map URLs → provisional source dicts
    url_to_src = {}
    for gs in grounding_sources:
        url = gs.get("url")
        if not url:
            continue
        url_to_src[url] = {
            "url": url,
            "title": gs.get("title", ""),
            "publisher": "",
            "quote": gs.get("snippet", ""),
        }

    try:
        data = _parse_json_response(text)
    except (json.JSONDecodeError, ValueError):
        print(f"[Research-Structured] Sub-researcher '{name}' JSON parse failed")
        return {
            "section": {"title": name, "summary": (text[:400] if text else "")},
            "claims": [],
            "sources": list(url_to_src.values()),
        }

    section_obj = data.get("section") or {"title": name, "summary": ""}
    raw_claims = data.get("claims") if isinstance(data.get("claims"), list) else []

    # Merge any URLs the model cited that weren't in grounding metadata
    for claim in raw_claims:
        for url in (claim.get("source_urls") or []):
            if url and url not in url_to_src:
                url_to_src[url] = {"url": url, "title": "", "publisher": "", "quote": ""}

    return {
        "section": section_obj,
        "claims": raw_claims,
        "sources": list(url_to_src.values()),
    }


def _merge_subresearcher_outputs(topic: str, template_id: str, mode: str,
                                   model: str, sub_outputs: list) -> dict:
    """Merge parallel sub-researcher outputs into the canonical schema.

    Dedupes sources by URL, assigns stable c1..cN / s1..sN ids,
    and maps claim.source_urls → claim.source_ids.
    """
    url_to_sid = {}
    sources = []
    for sub in sub_outputs:
        for src in sub.get("sources", []) or []:
            url = src.get("url") or ""
            if not url or url in url_to_sid:
                continue
            sid = f"s{len(sources) + 1}"
            url_to_sid[url] = sid
            sources.append({
                "id": sid,
                "url": url,
                "title": src.get("title", ""),
                "publisher": src.get("publisher", ""),
                "quote": src.get("quote", ""),
                "accessed_at": _datetime.utcnow().isoformat() + "Z",
            })

    claims = []
    sections = []
    for idx, sub in enumerate(sub_outputs):
        section_obj = sub.get("section") or {}
        section_id = f"sec{idx + 1}"
        section_claim_ids = []

        for claim in sub.get("claims", []) or []:
            cid = f"c{len(claims) + 1}"
            urls = claim.get("source_urls") or []
            source_ids = [url_to_sid[u] for u in urls if u in url_to_sid]
            claims.append({
                "id": cid,
                "text": claim.get("text", ""),
                "confidence": claim.get("confidence", "med"),
                "source_ids": source_ids,
            })
            section_claim_ids.append(cid)

        sections.append({
            "id": section_id,
            "title": section_obj.get("title", f"Section {idx+1}"),
            "summary": section_obj.get("summary", ""),
            "claim_ids": section_claim_ids,
        })

    return {
        "meta": {
            "topic": topic,
            "template_id": template_id,
            "mode": mode,
            "model": model,
            "generated_at": _datetime.utcnow().isoformat() + "Z",
        },
        "sections": sections,
        "claims": claims,
        "sources": sources,
    }


def run_structured_research(topic: str, template_id: str,
                             api_key: str, mode: str = "deep") -> dict:
    """Orchestrate the 3-step structured research pipeline.

    1. Planner (Flash): expand template layers → 3-6 concrete sub-queries
    2. Sub-researchers (parallel Pro+Search calls with grounding metadata)
    3. Merger: dedupe sources, assign stable c1..cN / s1..sN ids

    Returns the canonical structured schema {meta, sections, claims, sources}.
    On any failure, returns an empty-but-valid schema so callers can always persist it.
    """
    try:
        print(f"[Research-Structured] Planning sub-queries for '{topic}'...")
        sub_queries = _planner_expand_subqueries(topic, template_id, api_key)
        print(f"[Research-Structured] Planner produced {len(sub_queries)} sub-queries")

        sub_outputs = []
        if sub_queries:
            worker_count = min(4, len(sub_queries))
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                futures = {
                    executor.submit(_run_sub_researcher, sq, topic, api_key, mode): sq
                    for sq in sub_queries
                }
                for fut in as_completed(futures):
                    try:
                        result = fut.result()
                        sub_outputs.append(result)
                        sec_name = result.get("section", {}).get("title", "?")
                        print(f"[Research-Structured] Sub-query '{sec_name}' → "
                              f"{len(result.get('claims', []))} claims, "
                              f"{len(result.get('sources', []))} sources")
                    except Exception as e:
                        sq = futures[fut]
                        print(f"[Research-Structured] Sub-query '{sq.get('name')}' failed: {e}")

        model_label = "gemini-3.1-pro-preview" if mode == "deep" else "gemini-3-flash-preview"
        structured = _merge_subresearcher_outputs(topic, template_id, mode, model_label, sub_outputs)
        print(f"[Research-Structured] Merged: {len(structured['sections'])} sections, "
              f"{len(structured['claims'])} claims, {len(structured['sources'])} sources")
        return structured
    except Exception as e:
        print(f"[Research-Structured] Pipeline failed: {e}")
        return _empty_structured(topic, template_id, mode,
                                  "gemini-3.1-pro-preview" if mode == "deep" else "gemini-3-flash-preview")


def structure_from_blob(text: str, topic: str, template_id: str,
                         mode: str, model: str, api_key: str) -> dict:
    """Best-effort: convert an unstructured research text blob into the canonical schema.

    Used for the deep_research_agent path where we receive a single text output and
    cannot access grounding metadata. Asks Flash to extract claims/sources from the text.
    Returns _empty_structured on any failure so the field is always present.
    """
    if not text or not text.strip():
        return _empty_structured(topic, template_id, mode, model)

    text_excerpt = text[:60000]
    extractor_prompt = f"""You are extracting claims and sources from a research report.

REPORT:
\"\"\"
{text_excerpt}
\"\"\"

TOPIC: {topic}

Break the report into 3-6 thematic sections. For each section, extract:
- 5-15 factual claims (short sentences)
- The source URLs that support each claim — copy any http/https URLs that appear in the report.
  If the report mentions a publication by name without a URL, include that in source_titles instead.

Return ONLY JSON:
{{
  "sections": [
    {{
      "title": "<section heading>",
      "summary": "<1-2 sentence section summary>",
      "claims": [
        {{
          "text": "<factual claim>",
          "confidence": "high|med|low",
          "source_urls": ["<url>", "..."],
          "source_titles": ["<publication/title for URL-less sources>"]
        }}
      ]
    }}
  ]
}}"""

    raw = generate_content(
        extractor_prompt,
        model_name="gemini-3-flash-preview",
        temperature=0.1,
        api_key=api_key,
        max_output_tokens=16384,
    )
    if not raw or raw.startswith("Error:"):
        return _empty_structured(topic, template_id, mode, model)

    try:
        parsed = _parse_json_response(raw)
    except (json.JSONDecodeError, ValueError):
        return _empty_structured(topic, template_id, mode, model)

    sub_outputs = []
    for sec in parsed.get("sections", []) or []:
        claims_out = []
        sources_out = []
        seen_keys = set()
        for c in sec.get("claims", []) or []:
            urls = c.get("source_urls") or []
            titles = c.get("source_titles") or []
            for u in urls:
                if u and u not in seen_keys:
                    seen_keys.add(u)
                    sources_out.append({"url": u, "title": "", "publisher": "", "quote": ""})
            for t in titles:
                key = f"title:{t}"
                if t and key not in seen_keys:
                    seen_keys.add(key)
                    sources_out.append({"url": "", "title": t, "publisher": "", "quote": ""})
            claims_out.append({
                "text": c.get("text", ""),
                "confidence": c.get("confidence", "med"),
                "source_urls": urls,
            })
        sub_outputs.append({
            "section": {"title": sec.get("title", "Section"), "summary": sec.get("summary", "")},
            "claims": claims_out,
            "sources": sources_out,
        })

    return _merge_subresearcher_outputs(topic, template_id, mode, model, sub_outputs)


if __name__ == "__main__":
    # Quick test: list templates
    templates = get_all_templates_metadata()
    for t in templates:
        print(f"  {t['icon']} {t['name']} — {t['description'][:60]}...")

