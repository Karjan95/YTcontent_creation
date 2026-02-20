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
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])
    return json.loads(text)


def generate_narration(topic: str, template_id: str, research_dossier: str,
                       duration_minutes: int = 10, audience: str = "General",
                       tone: str = "", focus: str = "", style_guide: str = None,
                       selected_title: str = None, api_key: str = None) -> dict:
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
                     duration_minutes: int = 10, api_key: str = None) -> dict:
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
                              api_key: str = None) -> dict:
    """
    Generate production-ready prompts from narration beats.

    Takes narration (acts/beats with flowing text) and produces:
    - Creatively split shots with editorial rationale
    - Visual direction per shot
    - First-frame, last-frame, and Veo 3.1 prompts using dynamic schema

    Args:
        narration_json: Narration object {title, narration: [{act, beat, text}, ...]}
        duration_minutes: Target video length
        style_analysis: Structured style dict {style_summary, style_intent, prompt_schema}
        aspect_ratio: Video aspect ratio (Veo hardware constraint)
        api_key: Gemini API key

    For large narrations (>8 beats), processes in batches by act.
    """
    beats = narration_json.get("narration", [])

    if not beats:
        return {"error": "No narration beats found. Generate narration first."}

    title = narration_json.get("title", "Untitled")
    BEATS_PER_BATCH = 8

    # Small narrations: single call
    if len(beats) <= BEATS_PER_BATCH + 2:
        return _generate_single_batch(narration_json, duration_minutes,
                                      style_analysis=style_analysis,
                                      aspect_ratio=aspect_ratio,
                                      api_key=api_key)

    # Large narrations: batch by act
    MAX_CONCURRENT_BATCHES = 3
    print(f"[Production] Large narration ({len(beats)} beats). Batching by act...")

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

    def process_batch(batch_idx, batch_beats):
        batch_words = sum(len(b.get("text", b.get("narration", "")).split()) for b in batch_beats)
        batch_duration = max(1, round(duration_minutes * batch_words / total_words)) if total_words > 0 else duration_minutes

        batch_narration = {
            "title": title,
            "hook_type": narration_json.get("hook_type", ""),
            "narration": batch_beats,
        }

        print(f"[Production] Batch {batch_idx}/{len(batches)}: "
              f"{len(batch_beats)} beats, ~{batch_words} words, ~{batch_duration}min - STARTED")

        result = _generate_single_batch(batch_narration, batch_duration,
                                        style_analysis=style_analysis,
                                        aspect_ratio=aspect_ratio,
                                        api_key=api_key,
                                        batch_label=f"batch {batch_idx}/{len(batches)}")

        if "error" in result:
            print(f"[Production] Batch {batch_idx} FAILED: {result['error']}")
            return {"batch_idx": batch_idx, "error": result["error"]}

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
                print(f"[Production] Batch {batch_idx} exception: {e}")
                batch_results[batch_idx] = {"batch_idx": batch_idx, "error": str(e)}

    # Reconstruct in order
    for batch_idx in sorted(batch_results.keys()):
        result = batch_results[batch_idx]
        if "error" in result:
            continue
        all_shots.extend(result.get("shots", []))
        all_continuity.extend(result.get("continuity_notes", []))
        all_challenging.extend(result.get("challenging_shots", []))
        if batch_idx == 1:
            style_summary = result.get("style_summary", "")

    if not all_shots:
        return {"error": "All batches failed to produce shots."}

    merged = {
        "title": title,
        "aspect_ratio": aspect_ratio,
        "style_summary": style_summary,
        "total_shots": len(all_shots),
        "shots": all_shots,
        "continuity_notes": all_continuity,
        "production_notes": {
            "challenging_shots": all_challenging,
            "recommended_workflow": "Generate in batch order for visual continuity",
            "post_production": "Review cross-batch transitions for consistency",
        },
    }

    print(f"[Production] Complete: {len(all_shots)} total shots from {len(batches)} batches")
    return {"success": True, "production_table": merged}


def _generate_single_batch(narration_json: dict, duration_minutes: int = 10,
                           style_analysis: dict = None,
                           aspect_ratio: str = "16:9",
                           api_key: str = None,
                           batch_label: str = "") -> dict:
    """Generate production table for a single batch of narration beats."""
    prompt = build_production_prompt(
        narration_json=narration_json,
        duration_minutes=duration_minutes,
        style_analysis=style_analysis,
        aspect_ratio=aspect_ratio,
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
        key = api_key or os.environ.get("GEMINI_API_KEY")
        client = genai.Client(api_key=key)

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
        key = api_key or os.environ.get("GEMINI_API_KEY")
        client = genai.Client(api_key=key)

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


if __name__ == "__main__":
    # Quick test: list templates
    templates = get_all_templates_metadata()
    for t in templates:
        print(f"  {t['icon']} {t['name']} — {t['description'][:60]}...")

