"""
Research & Script Writer
========================
Orchestrates the 2-phase script pipeline:
  Phase 1: Gemini writes a flowing narration (organized by acts/beats)
  Phase 2: Gemini breaks that narration into timed scene rows

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
    build_breakdown_prompt,
    build_production_prompt,
    DEFAULT_STYLE_CONFIG,
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
    text = raw_response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])
    return json.loads(text)


def generate_narration(topic: str, template_id: str, research_dossier: str,
                       duration_minutes: int = 10, audience: str = "General",
                       tone: str = "", focus: str = "", style_guide: str = None,
                       api_key: str = None) -> dict:
    """
    PHASE 1: Generate a flowing narration script using Gemini.

    Returns the narration organized by acts/beats — no timestamps or scene table.
    This output feeds into Phase 2 (breakdown_narration).

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
    )

    raw_response = generate_content(prompt, model_name="gemini-2.5-flash", api_key=api_key)

    if raw_response.startswith("Error:"):
        return {"error": raw_response}

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


def breakdown_narration(narration_json: dict, duration_minutes: int = 10,
                        template_id: str = "educational_explainer",
                        api_key: str = None) -> dict:
    """
    PHASE 2: Break a flowing narration into timed scene rows.

    Takes the Phase 1 narration output and produces the final scene table
    with accurate timestamps based on speech pacing (2.5 words/sec).

    Returns:
        Dict with 'success' and 'script' (the scene table), or 'error'
    """
    prompt = build_breakdown_prompt(
        narration_json=narration_json,
        duration_minutes=duration_minutes,
        template_id=template_id,
    )

    raw_response = generate_content(prompt, model_name="gemini-2.5-flash", api_key=api_key)

    if raw_response.startswith("Error:"):
        return {"error": raw_response}

    try:
        script_data = _parse_json_response(raw_response)

        # VALIDATION: Check if script has scenes
        if "script" not in script_data or not script_data["script"]:
            print(f"[Phase 2 ERROR] Gemini returned no scenes!")
            print(f"[Phase 2 ERROR] Raw response (first 500 chars): {raw_response[:500]}")
            return {
                "error": "Phase 2 breakdown produced no scenes. Gemini may have failed to parse the narration. Check the raw response in logs."
            }

        return {"success": True, "script": script_data}
    except json.JSONDecodeError as e:
        print(f"[Phase 2 ERROR] JSON parse failed: {e}")
        print(f"[Phase 2 ERROR] Raw response (first 1000 chars): {raw_response[:1000]}")
        return {
            "success": True,
            "script": {
                "title": narration_json.get("title", "Untitled"),
                "raw_text": raw_response,
                "parse_error": "Could not parse Phase 2 breakdown as JSON."
            }
        }


def generate_full_script(topic: str, template_id: str, research_dossier: str,
                         duration_minutes: int = 10, audience: str = "General",
                         tone: str = "", focus: str = "", style_guide: str = None,
                         api_key: str = None) -> dict:
    """
    Full two-phase pipeline: Narration → Scene Breakdown.

    Phase 1: Write a compelling flowing narration
    Phase 2: Break it into timed scene rows

    Returns:
        Dict with 'success' and 'script' (final scene table), or 'error'
    """
    # ── Phase 1: Generate narration ──
    print("[Phase 1] Writing narration...")
    phase1 = generate_narration(
        topic=topic,
        template_id=template_id,
        research_dossier=research_dossier,
        duration_minutes=duration_minutes,
        audience=audience,
        tone=tone,
        focus=focus,
        style_guide=style_guide,
        api_key=api_key,
    )

    if "error" in phase1:
        return {"error": f"Phase 1 failed: {phase1['error']}"}

    narration_json = phase1["narration"]

    # Check if Phase 1 returned raw text instead of structured JSON
    if "raw_text" in narration_json:
        print("[Phase 1] Warning: got raw text instead of structured JSON")
        return {
            "success": True,
            "script": narration_json  # Pass through raw text
        }

    narration_beats = narration_json.get("narration", [])
    total_words = sum(len(b.get("text", "").split()) for b in narration_beats)
    print(f"[Phase 1] Complete: '{narration_json.get('title', 'Untitled')}' — "
          f"{len(narration_beats)} beats, {total_words} words")

    # ── Phase 2: Break down into scenes ──
    print("[Phase 2] Breaking narration into timed scenes...")
    phase2 = breakdown_narration(
        narration_json=narration_json,
        duration_minutes=duration_minutes,
        template_id=template_id,
        api_key=api_key,
    )

    if "error" in phase2:
        return {"error": f"Phase 2 failed: {phase2['error']}"}

    script_data = phase2["script"]

    # Correctly access the scenes array (nested inside script_data)
    if isinstance(script_data, dict) and "script" in script_data:
        scene_count = len(script_data.get("script", []))
    else:
        scene_count = 0

    print(f"[Phase 2] Complete: {scene_count} scenes generated")

    return {"success": True, "script": script_data}


def generate_production_table(scene_breakdown_json: dict,
                              style_config: dict = None,
                              style_analysis: str = None,
                              api_key: str = None) -> dict:
    """
    PHASE 3: Generate production-ready prompts from a scene breakdown.

    Takes the Phase 2 scene breakdown and produces first-frame prompts,
    last-frame prompts, and Veo 3.1 video prompts for each shot.

    For large scripts (>12 scenes), processes in batches of 10 to avoid
    hitting Gemini's output token limit.

    Args:
        scene_breakdown_json: The Phase 2 output (with 'script' array)
        style_config: Optional visual style preferences dict

    Returns:
        Dict with 'success' and 'production_table', or 'error'
    """
    # DEBUG: Print what we received
    print(f"[Phase 3 DEBUG] scene_breakdown_json keys: {scene_breakdown_json.keys()}")
    print(f"[Phase 3 DEBUG] scene_breakdown_json type: {type(scene_breakdown_json)}")

    scenes = scene_breakdown_json.get("script", [])

    # VALIDATION: Ensure scenes exist
    if not scenes or len(scenes) == 0:
        print(f"[Phase 3 ERROR] No scenes found in scene_breakdown_json!")
        print(f"[Phase 3 ERROR] Received data: {scene_breakdown_json}")
        return {"error": "No scenes found in the scene breakdown. Make sure Phase 2 completed successfully and generated a script with scenes."}
    total_scenes = len(scenes)
    BATCH_SIZE = 10

    # Small scripts: single call
    if total_scenes <= BATCH_SIZE + 2:
        return _generate_single_batch(scene_breakdown_json, style_config, style_analysis=style_analysis, api_key=api_key)

    # Large scripts: batch processing WITH PARALLELIZATION
    MAX_CONCURRENT_BATCHES = 3  # Process 3 batches at a time
    print(f"[Phase 3] Large script detected ({total_scenes} scenes). "
          f"Processing in batches of {BATCH_SIZE} with {MAX_CONCURRENT_BATCHES} concurrent workers...")

    all_shots = []
    all_continuity = []
    all_challenging = []
    style_summary = ""
    title = scene_breakdown_json.get("title", "Untitled")
    aspect_ratio = (style_config or {}).get("aspect_ratio",
                    DEFAULT_STYLE_CONFIG["aspect_ratio"])

    # Split scenes into batches
    batches = []
    for i in range(0, total_scenes, BATCH_SIZE):
        batches.append(scenes[i:i + BATCH_SIZE])

    # Helper function to process a single batch (for parallel execution)
    def process_batch(batch_idx, batch_scenes):
        batch_start = batch_scenes[0].get("scene", "?")
        batch_end = batch_scenes[-1].get("scene", "?")
        print(f"[Phase 3] Batch {batch_idx}/{len(batches)}: "
              f"scenes {batch_start}-{batch_end} "
              f"({len(batch_scenes)} scenes) - STARTED")

        # Build a mini-breakdown for this batch
        batch_breakdown = {
            "title": title,
            "duration_minutes": scene_breakdown_json.get("duration_minutes", 10),
            "script": batch_scenes,
        }

        result = _generate_single_batch(batch_breakdown, style_config,
                                        style_analysis=style_analysis,
                                        api_key=api_key,
                                        batch_label=f"batch {batch_idx}/{len(batches)}")

        if "error" in result:
            print(f"[Phase 3] Batch {batch_idx} FAILED: {result['error']}")
            return {"batch_idx": batch_idx, "error": result["error"]}

        pt = result.get("production_table", {})
        batch_shots = pt.get("shots", [])
        print(f"[Phase 3] Batch {batch_idx} COMPLETE: got {len(batch_shots)} shots")

        return {
            "batch_idx": batch_idx,
            "shots": batch_shots,
            "continuity_notes": pt.get("continuity_notes", []),
            "challenging_shots": pt.get("production_notes", {}).get("challenging_shots", []),
            "style_summary": pt.get("style_summary", ""),
        }

    # Process batches in parallel with ThreadPoolExecutor
    batch_results = {}
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_BATCHES) as executor:
        # Submit all batch jobs
        future_to_batch = {
            executor.submit(process_batch, idx + 1, batch_scenes): idx + 1
            for idx, batch_scenes in enumerate(batches)
        }

        # Collect results as they complete
        for future in as_completed(future_to_batch):
            batch_idx = future_to_batch[future]
            try:
                result = future.result()
                batch_results[result["batch_idx"]] = result
            except Exception as e:
                print(f"[Phase 3] Batch {batch_idx} raised exception: {e}")
                batch_results[batch_idx] = {"batch_idx": batch_idx, "error": str(e)}

    # Reconstruct results in order (by batch_idx)
    for batch_idx in sorted(batch_results.keys()):
        result = batch_results[batch_idx]

        if "error" in result:
            continue

        # Collect shots
        all_shots.extend(result.get("shots", []))

        # Collect continuity notes
        all_continuity.extend(result.get("continuity_notes", []))

        # Collect production notes
        all_challenging.extend(result.get("challenging_shots", []))

        # Grab style summary from first batch
        if batch_idx == 1:
            style_summary = result.get("style_summary", "")

    if not all_shots:
        return {"error": "All batches failed to produce shots."}

    # Merge into final production table
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

    print(f"[Phase 3] Complete: {len(all_shots)} total shots from "
          f"{len(batches)} batches")
    return {"success": True, "production_table": merged}


def _generate_single_batch(scene_breakdown_json: dict,
                           style_config: dict = None,
                           style_analysis: str = None,
                           api_key: str = None,
                           batch_label: str = "") -> dict:
    """Generate production table for a single batch of scenes."""
    prompt = build_production_prompt(
        scene_breakdown_json=scene_breakdown_json,
        style_config=style_config,
        style_analysis=style_analysis,
    )

    label = f" ({batch_label})" if batch_label else ""
    print(f"[Phase 3] Generating production table{label}...")
    # Use temperature=0.1 for maximum preservation of input narration
    raw_response = generate_content(prompt, model_name="gemini-2.5-pro", temperature=0.1, api_key=api_key)

    if raw_response.startswith("Error:"):
        return {"error": raw_response}

    try:
        production_data = _parse_json_response(raw_response)

        # PROGRAMMATICALLY preserve narration from input scenes
        # Build a lookup map: scene_number -> narration text
        scenes = scene_breakdown_json.get("script", [])
        scene_narration_map = {}
        for scene in scenes:
            scene_num = scene.get("scene")
            narration = scene.get("narration", "")
            beat = scene.get("beat", "")
            act = scene.get("act", "")
            if scene_num:
                scene_narration_map[scene_num] = {
                    "narration": narration,
                    "beat": beat,
                    "act": act
                }

        # For each shot, replace script_beat with EXACT narration from input
        for shot in production_data.get("shots", []):
            scene_refs = shot.get("scene_refs", [])
            if scene_refs and len(scene_refs) > 0:
                # Use the first referenced scene's narration
                first_scene = scene_refs[0]
                if first_scene in scene_narration_map:
                    scene_data = scene_narration_map[first_scene]
                    # GUARANTEED exact preservation - no AI involved
                    shot["script_beat"] = f"{scene_data['narration']} | {scene_data['beat']}"
                    shot["act"] = scene_data["act"]

        shot_count = len(production_data.get("shots", []))
        print(f"[Phase 3] Got {shot_count} shots{label} - narration preserved programmatically")
        return {"success": True, "production_table": production_data}
    except json.JSONDecodeError:
        return {
            "success": True,
            "production_table": {
                "title": scene_breakdown_json.get("title", "Untitled"),
                "raw_text": raw_response,
                "parse_error": f"Could not parse Phase 3 JSON{label}."
            }
        }


# ── Legacy alias for backward compatibility ──
def generate_script(topic: str, template_id: str, research_dossier: str,
                    duration_minutes: int = 10, audience: str = "General",
                    tone: str = "", focus: str = "", style_guide: str = None,
                    api_key: str = None) -> dict:
    """Legacy wrapper — calls the full two-phase pipeline."""
    return generate_full_script(
        topic=topic,
        template_id=template_id,
        research_dossier=research_dossier,
        duration_minutes=duration_minutes,
        audience=audience,
        tone=tone,
        focus=focus,
        style_guide=style_guide,
        api_key=api_key,
    )


if __name__ == "__main__":
    # Quick test: list templates
    templates = get_all_templates_metadata()
    for t in templates:
        print(f"  {t['icon']} {t['name']} — {t['description'][:60]}...")

