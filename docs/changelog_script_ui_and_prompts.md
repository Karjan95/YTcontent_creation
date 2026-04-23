# Frontend & Prompt Engineering Overhaul Summary

This document summarizes the major modifications and feature additions we've completed together during this session. Our goal was to make the script generation process more dynamic, customizable, and capable of deeply nuanced creative direction.

## 1. Dynamic Script Parameters in UI (Step A & Step C)
We replaced old, hardcoded HTML selects with dynamic inputs that sync directly with the backend (`research_templates.py`).

*   **Step A (Audience)**: The audience dropdown now pulls directly from the `AUDIENCE_PROFILES` definition.
*   **Step C (Script Parameters)**:
    *   **Format Presets**: Replaced the static "Video Length" with "Format Presets" (Short Form, Standard, Deep Dive, Custom). This sets both the target duration AND the preferred pacing (e.g., hyper-fast hooks vs. slow-burn documentaries).
    *   **Expanded Tones**: Replaced the 6 hardcoded tones with a comprehensive list pulled from `TONE_DEFINITIONS`.
    *   **Viewer Outcome**: Added a new dropdown (from `VIEWER_OUTCOMES`) that allows you to engineer the ending of the script (e.g., "Minds Blown," "Call to Action," "Reflective Note").

## 2. Style Blend Mode (Transcript Analysis)
We noticed that when users uploaded a reference transcript (e.g., "MrBeast style") but also selected specific Audience/Tone settings (e.g., "Entertainment Seekers" + "Villain Energy"), the Gemini prompt was getting confused. We built a two-branch solution:

*   **Full Clone**: The AI completely adopts the uploaded creator's style. Your tone and audience selections are suppressed and ignored. Pure imitation.
*   **Blend with My Settings**: The AI uses the uploaded transcript purely for **structure, pacing, and hook transitions**, while the **emotional layer and vocabulary** are taken from your selected Tone and Audience. 
*   **UI Update**: Added intuitive radio buttons and dynamic hint text under the transcript paste area.

## 3. "Custom" Audience and Tone Inputs
To give users ultimate control without needing to edit the backend Python templates, we added "✏️ Custom" options to both the Audience and Tone dropdowns.

*   **How it works (Frontend)**: When you select "Custom", a text input field appears. You can type a plain-English description of your audience (e.g., *"Millennials who love tech and memes"*) or your tone (e.g., *"Playful but slightly dark, like a true crime comedy podcast"*).
*   **How it works (Backend)**: If a custom value is detected, the AI is given explicit instructions to analyze your short description and infer the necessary stylistic choices:
    *   **Custom Audience Prompting**: The AI is told to infer the appropriate vocabulary level, assumed knowledge, and analogy style based on your description.
    *   **Custom Tone Prompting**: The AI is told to infer sentence style, rhetorical devices, and emotional stance, and repeatedly warned to *fully commit* to this exact vibe without watering it down.

## 4. Deep Research & Script Prompt Engineering (`research_templates.py`)
Beyond the UI settings, we radically overhauled the hidden prompt architecture that drives Gemini's research and writing phases:

*   **`search_layers`**: We moved away from simple, generic search queries. Now, the AI performs multi-layered research:
    *   *Broad Context:* The basic facts and history.
    *   *Controversy/Debate:* Finding the friction and alternate viewpoints.
    *   *Micro-details/Anecdotes:* Finding specific, highly-engaging stories rather than just high-level summaries.
    *   *Expert/Data:* Hard numbers and expert consensus.
*   **`analysis_questions`**: We replaced basic data extraction with deep analytical synthesis. The AI now actively looks for the "counter-narrative", the "hidden mechanisms", and the "emotional core" of the dossier before it starts writing.
*   **`narrative_goals`**: Each template now has explicit narrative goals to ensure the script has a specific trajectory rather than just listing facts.
*   **Dynamic Cinematic Beats**: We added a **CRITICAL DIRECTING RULE** to the script generation prompt to fix the issue of boring, generic segment titles.
    *   *The Rule:* "Do NOT just blindly copy the basic beat names from the Story Structure above. You are the Director. Invent your own highly specific, active, and cinematic beats that perfectly match the actual facts in the dossier. (e.g. Instead of a beat called 'The Hook', name your beat something active like 'Cold Open: The Paradox of X')."
    *   *The Result:* The AI now generates highly descriptive, engaging act headers that guide the actual narration much better.

## Summary of Files Modified
*   **`ui/index.html`**: Redesigned Step A/C, added dynamic toggle functions (`onAudienceChange`, `onToneChange`, `onFormatPresetChange`, `toggleStyleInput`), and updated the `generate-script` API payload.
*   **`execution/server.py`**: Extracted new fields (`style_blend_mode`, `custom_audience`, `custom_tone`) from the JSON request and passed them to the scriptwriter.
*   **`execution/research_scriptwriter.py`**: Passed the new parameters through `generate_narration` directly down to the prompt builder.
*   **`execution/research_templates.py`**: Overhauled `build_script_prompt()` to include the "Clone vs. Blend" logic pathway, handle priority constraints, and process the new custom audience/tone description blocks.
