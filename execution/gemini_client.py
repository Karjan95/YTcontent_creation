import os
import argparse
import base64
import time
import json
import random
import traceback
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Load environment variables from project root
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# ── Retry logic for transient Gemini API errors ──
MAX_RETRIES = 3


def _is_retryable_error(e):
    """Check if an exception is a transient 503/429 error worth retrying."""
    error_str = str(e).lower()
    return any(indicator in error_str for indicator in [
        '503', 'unavailable', '429', 'resource_exhausted',
        'overloaded', 'high demand', 'rate limit', 'quota',
        'temporarily unavailable', 'server error',
    ])


def _retry_api_call(api_fn, max_retries=MAX_RETRIES, description="API call"):
    """Execute api_fn() with exponential backoff on transient errors.

    Returns: (result, retries_used) where retries_used=0 means first attempt succeeded.
    Raises: the last exception if all retries are exhausted.
    """
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            result = api_fn()
            if attempt > 0:
                print(f"[Retry] {description} succeeded on attempt {attempt + 1}/{max_retries + 1}")
            return result, attempt
        except Exception as e:
            last_error = e
            if _is_retryable_error(e) and attempt < max_retries:
                wait = (2 ** attempt) + random.uniform(0, 1)
                print(f"[Retry] {description} attempt {attempt + 1}/{max_retries + 1} failed: {e}")
                print(f"[Retry] Waiting {wait:.1f}s before retry...")
                time.sleep(wait)
            else:
                raise
    raise last_error


def get_client(api_key=None):
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError("GEMINI_API_KEY not found. Please provide an API key.")
    return genai.Client(api_key=key)


def generate_content(prompt, model_name="gemini-3-flash-preview", use_search=False, temperature=None, api_key=None):
    """Generate text content using Gemini, optionally with Google Search."""
    try:
        client = get_client(api_key)

        # Configure tools if search is requested
        config = None
        if use_search or temperature is not None:
            config = types.GenerateContentConfig()
            if use_search:
                config.tools = [types.Tool(google_search=types.GoogleSearch())]
            if temperature is not None:
                config.temperature = temperature

        def _call():
            return client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config
            )

        response, retries = _retry_api_call(_call, description=f"generate_content({model_name})")
        if response.text is None:
            return "Error: Gemini returned an empty response (possibly blocked by safety filters)."
        return response.text
    except Exception as e:
        return f"Error (after {MAX_RETRIES + 1} attempts): {str(e)}"


def _generate_with_gemini_model(client, model_name, prompt, timestamp):
    """Generate image using Gemini's native image generation (generate_content API)."""
    print(f"[Image Gen] Trying Gemini model: {model_name}...")

    def _call():
        return client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            )
        )

    response, _retries = _retry_api_call(_call, description=f"image_gen({model_name})")
    if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                image_data = part.inline_data.data
                ext = part.inline_data.mime_type.split("/")[-1]
                filename = os.path.join(
                    os.path.dirname(__file__), '..', 'generated_images',
                    f"image_{timestamp}_0.{ext}"
                )
                with open(filename, "wb") as f:
                    f.write(image_data)
                print(f"[Image Gen] Success with {model_name}! Saved to {filename}")
                return filename
    return None


def _generate_with_imagen_model(client, model_name, prompt, timestamp):
    """Generate image using Imagen API (generate_images endpoint)."""
    print(f"[Image Gen] Trying Imagen model: {model_name}...")

    def _call():
        return client.models.generate_images(
            model=model_name,
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
            )
        )

    response, _retries = _retry_api_call(_call, description=f"imagen_gen({model_name})")
    if response.generated_images:
        image_data = response.generated_images[0].image.image_bytes
        filename = os.path.join(
            os.path.dirname(__file__), '..', 'generated_images',
            f"image_{timestamp}_0.png"
        )
        with open(filename, "wb") as f:
            f.write(image_data)
        print(f"[Image Gen] Success with {model_name}! Saved to {filename}")
        return filename
    return None


def generate_image_content(prompt, model_name=None, api_key=None):
    """
    Generate an image using the specified model.

    Args:
        prompt: Text prompt for image generation
        model_name: One of:
            - 'gemini-3-pro-image-preview' (Gemini 3 Pro, quality)
            - 'gemini-2.5-flash-image' (Gemini Flash, fast)
            - 'imagen-4.0-generate-001' (Imagen 4 Standard)
            - 'imagen-4.0-fast-generate-001' (Imagen 4 Fast)
            - 'imagen-4.0-ultra-generate-001' (Imagen 4 Ultra)
            - None (auto: tries Gemini 3 Pro → Imagen 4 Standard fallback)
        api_key: Gemini API key

    Returns:
        Path to saved image file, or error string starting with "Error:"
    """
    client = get_client(api_key)
    os.makedirs(os.path.join(os.path.dirname(__file__), '..', 'generated_images'), exist_ok=True)
    timestamp = int(time.time())

    # Direct model selection — no fallback
    if model_name:
        try:
            if model_name.startswith("imagen-"):
                result = _generate_with_imagen_model(client, model_name, prompt, timestamp)
            else:
                result = _generate_with_gemini_model(client, model_name, prompt, timestamp)

            if result:
                return result
            return f"Error: {model_name} returned no image. Try a different prompt."
        except Exception as e:
            print(f"[Image Gen] {model_name} failed: {e}")
            return f"Error: {str(e)}"

    # Auto mode (backward compat): Gemini 3 Pro → Imagen 4 fallback
    try:
        result = _generate_with_gemini_model(client, "gemini-3-pro-image-preview", prompt, timestamp)
        if result:
            return result
        print(f"[Image Gen] Gemini 3 Pro returned no image. Trying Imagen fallback...")
    except Exception as e:
        print(f"[Image Gen] Gemini 3 Pro failed: {e}. Trying Imagen fallback...")

    try:
        result = _generate_with_imagen_model(client, "imagen-4.0-generate-001", prompt, timestamp)
        if result:
            return result
        return "Error: Both models failed to generate an image. Try a different prompt (avoid real person names)."
    except Exception as e:
        print(f"[Image Gen] Imagen fallback failed: {e}")
        return f"Error: {str(e)}"


# All possible prompt fields for the dynamic schema system
PROMPT_FIELD_UNIVERSE = [
    "shot_size", "subject", "expression", "wardrobe", "arrangement", "background", "photography", "mood",
    "lighting", "lighting_direction", "camera_lens", "camera_aperture",
    "dof", "film_stock", "color_restriction", "output_style",
    "room_objects", "made_out_of", "tags",
]

# Fields that are always required regardless of style
LOCKED_PROMPT_FIELDS = ["shot_size", "subject", "expression", "wardrobe", "arrangement", "background", "photography", "mood"]


def _build_default_schema_from_detail_level(detail_level: str) -> dict:
    """Build a sensible default prompt_schema when AI doesn't provide one."""
    detail = (detail_level or "").lower()
    if "minimal" in detail:
        return {
            "always_include": LOCKED_PROMPT_FIELDS,
            "include": ["color_restriction", "output_style"],
            "exclude": ["camera_lens", "camera_aperture", "dof", "film_stock",
                        "made_out_of", "lighting", "lighting_direction", "room_objects", "tags"],
        }
    elif "abstract" in detail:
        return {
            "always_include": LOCKED_PROMPT_FIELDS,
            "include": ["color_restriction", "output_style", "tags"],
            "exclude": ["camera_lens", "camera_aperture", "dof", "film_stock",
                        "made_out_of", "lighting_direction", "room_objects"],
        }
    else:  # High Detail / Standard
        return {
            "always_include": LOCKED_PROMPT_FIELDS,
            "include": ["lighting", "lighting_direction", "camera_lens", "camera_aperture",
                        "dof", "film_stock", "color_restriction", "output_style",
                        "room_objects", "made_out_of", "tags"],
            "exclude": [],
        }


def _get_style_analysis_prompt():
    """Return the shared style analysis prompt used by both image and text analysis."""
    return """Analyze the provided style reference to create a **Production Style Guide** for an AI video generator that will create NARRATIVE SCENES.

YOUR JOB HAS FOUR PARTS:

═══ PART 1: EXTRACT ARTISTIC INTENT & MICRO-AESTHETICS ═══
Do not describe the literal story of the reference image. Extract the TRANSFERABLE AESTHETIC RULES.
Perform a silent "Micro Sweep":
- Look at textures, overall imperfections (film grain, brush strokes, clean digital vectors).
- Look at lighting quality (Hard/Soft/Diffused, warm/cool temperature).
- Look at color contrast levels and palette rules.

═══ PART 2: EXTRACT CHARACTER RENDERING IDENTITY ═══
⚠️ THIS IS CRITICAL. Look at HOW CHARACTERS ARE RENDERED in the reference images.
Do NOT describe the character as a real person. Describe the RENDERING STYLE of the character:
- What do characters LOOK LIKE as rendered objects? (e.g., "stick figure with large white circular head, thick black outline body, dot eyes" or "3D clay figure with soft matte skin" or "realistic photographic human")
- What are the body proportions? (e.g., "simplified stick limbs" or "chibi/large head" or "realistic proportions")
- What are the facial features? (e.g., "two dot eyes, no nose, curved line mouth" or "photorealistic face with pores")
- What is the wardrobe rendering style? (e.g., "flat color fills with no folds" or "detailed fabric with wrinkles")

Write a single "character_description" paragraph that can be used as a TEMPLATE to describe ANY character in this style.
This description will REPLACE generic terms like "man", "woman", "person" in every production prompt.

Example for stick figure style: "A stick figure character with a large white circular head, thick black outline body, simple dot eyes, no nose, minimal curved-line mouth. Clothing rendered as flat solid-color shapes over the body outline."
Example for photorealistic: "A photorealistic human with natural skin texture, detailed facial features, and physically accurate proportions."

═══ PART 3: DEFINE HOW ENVIRONMENTS SHOULD BE RENDERED ═══
Since these prompts are for a STORY, the environments must match the narrative, NOT the reference image's background.

⚠️ IMPORTANT: Character rendering and environment rendering may use DIFFERENT levels of detail.
For example, stick figure characters can exist in rich cinematic environments. Cartoon characters can exist in photorealistic backgrounds.

Determine the "rendering_split":
- "unified" = characters and environments are rendered the SAME way (e.g., both photorealistic, or both cartoon/flat)
- "hybrid" = characters are rendered DIFFERENTLY from environments (e.g., 2D stick figures in detailed cinematic worlds, cartoon characters in painterly backgrounds)

Write an "environment_description" paragraph that describes HOW ENVIRONMENTS/BACKGROUNDS should be rendered.
This is SEPARATE from the character rendering style.

Examples:
- For stick figures in cinematic worlds: "Rich, detailed cinematic environments with dramatic lighting, depth of field, and volumetric atmosphere rendered in a painterly or semi-realistic style"
- For fully cartoon: "Flat solid-color backgrounds with simple geometric shapes matching the character rendering"
- For photorealistic: "Photorealistic environments with natural lighting and physically accurate materials"

Also define:
- "scene_complexity": How complex should STORY ENVIRONMENTS be (simple/standard/rich/cinematic)

═══ PART 4: RECOMMEND A PROMPT SCHEMA ═══
Based on the intent, decide which prompt fields are RELEVANT.
The UNIVERSE of fields: shot_size, subject, expression, wardrobe, arrangement, background, photography, mood, lighting, lighting_direction, camera_lens, camera_aperture, dof, film_stock, color_restriction, output_style, room_objects, made_out_of, tags.

RULES:
- shot_size, subject, expression, wardrobe, arrangement, background, photography, mood MUST ALWAYS be included.
- For UNIFIED minimalist styles (characters AND environments are simple): EXCLUDE technical camera fields (lens, aperture, dof), film_stock, made_out_of, lighting_direction.
- For UNIFIED cinematic styles: INCLUDE everything.
- For HYBRID styles (minimalist characters + rich environments): INCLUDE technical camera fields — they will be applied to the ENVIRONMENT layer only. The prompt builder handles this separation.

═══ OUTPUT FORMAT ═══
Return a JSON object with EXACTLY this structure:
{
    "style_summary": "One sentence describing the CHARACTER RENDERING STYLE and global atmosphere",
    "style_intent": {
        "character_description": "Complete description of how ALL characters should be rendered in prompts. This replaces 'man'/'woman'/'person' in every prompt. Be specific about head shape, body style, facial features, limb rendering, and wardrobe rendering.",
        "environment_description": "Complete description of how ALL environments/backgrounds should be rendered. Can differ from character rendering in hybrid styles.",
        "rendering_split": "unified | hybrid",
        "detail_level": "Minimalist | Standard | High Detail | Micro-Detail (Scratches/Imperfections)",
        "scene_complexity": "How complex should STORY ENVIRONMENTS be",
        "camera_language": "Eye-level/High-angle/Low-angle limitations",
        "lighting_instruction": "Specify Source (Sunlight/Artificial), Direction, and Quality (Hard/Soft/Diffused)",
        "subject_framing": "Close-up/Wide-shot tendencies",
        "writing_style": "How prompt text should be written",
        "color_palette": "Dominant tones and context level (High/Low/Medium contrast)",
        "texture": "Rough/Smooth/Metallic/Fabric-type OR digital/painterly texture rules",
        "mood_default": "Weather/Atmosphere tendencies (e.g. Chaotic/Serene/Foggy)"
    },
    "prompt_schema": {
        "always_include": ["shot_size", "subject", "expression", "wardrobe", "arrangement", "background", "photography", "mood"],
        "include": ["fields RELEVANT for this style"],
        "exclude": ["fields NOT RELEVANT for this style"]
    }
}"""


def analyze_style_from_images(image_data_list, api_key=None):
    """
    Analyze visual style from 1-4 base64-encoded images using Gemini Vision.
    Returns a structured dict with style_summary, style_intent, and prompt_schema.

    Args:
        image_data_list: List of base64 data URIs (e.g., "data:image/jpeg;base64,/9j/4AAQ...")
        api_key: Optional Gemini API key (falls back to env var)

    Returns:
        Dict with {style_summary, style_intent, prompt_schema}, or error string starting with "Error:"
    """
    try:
        client = get_client(api_key)

        # Build multimodal prompt with images + text
        parts = []

        # Add all images
        for idx, img_data in enumerate(image_data_list):
            if ',' in img_data:
                header, b64_data = img_data.split(',', 1)
                mime_type = header.split(':')[1].split(';')[0] if ':' in header else "image/jpeg"
            else:
                b64_data = img_data
                mime_type = "image/jpeg"

            image_bytes = base64.b64decode(b64_data)
            parts.append(
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            )

        parts.append(types.Part(text=_get_style_analysis_prompt()))

        def _call():
            return client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=types.Content(parts=parts),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )

        response, _retries = _retry_api_call(_call, description="analyze_style_from_images")

        try:
            result = json.loads(response.text)
            # Validate and ensure prompt_schema exists
            if "prompt_schema" not in result:
                detail_level = result.get("style_intent", {}).get("detail_level", "Standard")
                result["prompt_schema"] = _build_default_schema_from_detail_level(detail_level)
            # Ensure always_include has the locked fields
            always = result.get("prompt_schema", {}).get("always_include", [])
            for field in LOCKED_PROMPT_FIELDS:
                if field not in always:
                    always.append(field)
            result.setdefault("prompt_schema", {})["always_include"] = always

            print(f"[Style Analysis] Extracted: {result.get('style_summary', 'Unknown')}")
            print(f"[Style Analysis] Schema includes: {result['prompt_schema'].get('include', [])}")
            print(f"[Style Analysis] Schema excludes: {result['prompt_schema'].get('exclude', [])}")
            return result

        except json.JSONDecodeError:
            print(f"[Style Analysis] Failed to parse JSON: {response.text}")
            return f"Error: Could not parse style analysis response"

    except Exception as e:
        print(f"[Style Analysis] Failed: {e}")
        return f"Error: {str(e)}"


def analyze_style_from_text(style_description, api_key=None):
    """
    Analyze visual style from a free-text description using Gemini.
    Returns the same structured dict as analyze_style_from_images().

    Args:
        style_description: Free-text style description (e.g., "2D cartoon, bright colors")
        api_key: Optional Gemini API key

    Returns:
        Dict with {style_summary, style_intent, prompt_schema}, or error string starting with "Error:"
    """
    try:
        client = get_client(api_key)

        prompt = f"""The user wants to create a video in this visual style:

"{style_description}"

{_get_style_analysis_prompt()}"""

        def _call():
            return client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )

        response, _retries = _retry_api_call(_call, description="analyze_style_from_text")

        try:
            result = json.loads(response.text)
            if "prompt_schema" not in result:
                detail_level = result.get("style_intent", {}).get("detail_level", "Standard")
                result["prompt_schema"] = _build_default_schema_from_detail_level(detail_level)
            always = result.get("prompt_schema", {}).get("always_include", [])
            for field in LOCKED_PROMPT_FIELDS:
                if field not in always:
                    always.append(field)
            result.setdefault("prompt_schema", {})["always_include"] = always

            print(f"[Style Analysis from Text] Extracted: {result.get('style_summary', 'Unknown')}")
            return result

        except json.JSONDecodeError:
            print(f"[Style Analysis from Text] Failed to parse JSON: {response.text}")
            return f"Error: Could not parse style analysis response"

    except Exception as e:
        print(f"[Style Analysis from Text] Failed: {e}")
        return f"Error: {str(e)}"


# ── Creative Direction Expansion ──────────────────────────────────

def _get_creative_direction_prompt():
    """Return the shared prompt for expanding/refining creative direction."""
    return """You are a creative director for an AI video production pipeline.
The user has described what KIND of video they want. Your job is to expand this
into structured creative guidance that will direct three production agents:
- A DIRECTOR (who makes editorial/cutting decisions)
- A STORYBOARD ARTIST (who designs visual compositions)
- A DIRECTOR OF PHOTOGRAPHY (who writes final image/video generation prompts)

YOUR JOB HAS TWO PARTS:

═══ PART 1: EXPAND THE CREATIVE DIRECTION ═══
Take the user's description and fill in any gaps they didn't specify.
Be creative but stay faithful to their vision. If they said "stick figure explainer,"
don't turn it into a cinematic epic. If they said "documentary," don't make it a cartoon.

Be flexible — self-suggest details the user didn't mention based on what would make
sense for this type of video and this script's content. The user can always edit or
remove your suggestions.

For each field below, provide a clear, actionable directive:
- direction_summary: 2-3 sentence elevator pitch of the creative vision
- video_format: The type/genre of video (explainer, documentary, essay, tutorial, etc.)
- visual_language: How visual storytelling works (literal depiction, visual metaphors, abstract, symbolic, etc.)
- narrative_approach: How the story is told (direct address, observational, dramatic reenactment, POV, educational walkthrough, etc.)
- pacing_philosophy: The rhythm and energy (contemplative with slow reveals, rapid-fire montage, building crescendo, steady educational pace, etc.)
- world_building: What environments/worlds look like (minimalist void, rich fantasy, real-world locations, stylized abstractions, etc.)
- character_approach: How characters/subjects are treated (stick figures, 3D rendered humans, silhouettes, no characters — objects only, etc.)
- tone_and_feel: The emotional register (playful and irreverent, serious and authoritative, warm and intimate, etc.)

═══ PART 2: SUGGEST STYLE DEFAULTS ═══
Based on the creative direction, suggest appropriate visual style defaults.
These will pre-populate a style review panel that the user can edit.

Generate a complete suggested_style_defaults object with:
- style_summary: One sentence describing the rendering style
- style_intent: {character_description, environment_description, rendering_split, detail_level, scene_complexity, camera_language,
  lighting_instruction, subject_framing, writing_style, color_palette, texture, mood_default}
- prompt_schema: {always_include, include, exclude}

RULES for style_intent fields:
- character_description: Complete template for rendering ANY character in this style (e.g., "A stick figure with large white circular head, thick black outline body, dot eyes")
- environment_description: Complete template for rendering environments/backgrounds. Can differ from character rendering. (e.g., "Rich cinematic environments with dramatic lighting and depth" or "Flat solid-color backgrounds")
- rendering_split: "unified" if characters and environments use the same rendering style, "hybrid" if they differ (e.g., stick figures in cinematic worlds). If the user mentions simple/minimalist characters but rich/detailed/cinematic environments, this MUST be "hybrid".
- detail_level: One of "Minimalist", "Standard", "High Detail", "Micro-Detail"
- scene_complexity: How complex story environments should be
- camera_language: Eye-level/angle tendencies
- lighting_instruction: Light source, direction, quality
- subject_framing: Close-up/wide tendencies
- writing_style: How prompt text should be written (concise, descriptive, technical)
- color_palette: Dominant tones and contrast level
- texture: Surface quality rules (rough, smooth, digital, painterly)
- mood_default: Weather/atmosphere tendencies

RULES for prompt_schema:
- always_include MUST contain: shot_size, subject, expression, wardrobe, arrangement, background, photography, mood
- For UNIFIED minimalist styles (characters AND environments are simple): EXCLUDE technical camera fields (camera_lens, camera_aperture, dof), film_stock, made_out_of, lighting_direction
- For UNIFIED cinematic/3D styles: INCLUDE everything
- For HYBRID styles (minimalist characters + rich environments): INCLUDE technical camera fields — they apply to environments only
- Use your judgment for styles in between

═══ OUTPUT FORMAT ═══
Return a JSON object with EXACTLY this structure:
{
    "direction_summary": "...",
    "video_format": "...",
    "visual_language": "...",
    "narrative_approach": "...",
    "pacing_philosophy": "...",
    "world_building": "...",
    "character_approach": "...",
    "tone_and_feel": "...",
    "suggested_style_defaults": {
        "style_summary": "...",
        "style_intent": {
            "character_description": "...",
            "environment_description": "...",
            "rendering_split": "unified | hybrid",
            "detail_level": "...",
            "scene_complexity": "...",
            "camera_language": "...",
            "lighting_instruction": "...",
            "subject_framing": "...",
            "writing_style": "...",
            "color_palette": "...",
            "texture": "...",
            "mood_default": "..."
        },
        "prompt_schema": {
            "always_include": ["shot_size", "subject", "expression", "wardrobe", "arrangement", "background", "photography", "mood"],
            "include": ["...relevant fields..."],
            "exclude": ["...irrelevant fields..."]
        }
    }
}"""


def expand_creative_direction(user_direction, narration_context=None, api_key=None):
    """
    Expand a user's free-form creative direction into structured guidance
    plus auto-suggested style defaults.

    Args:
        user_direction: Free-form description (e.g., "stick figure explainer with POV style")
        narration_context: Optional narration JSON {title, narration: [{act, beat, text}...]}
        api_key: Optional Gemini API key

    Returns:
        Dict with direction fields + suggested_style_defaults, or error string starting with "Error:"
    """
    try:
        client = get_client(api_key)

        # Build context snippet from narration if available
        narration_snippet = ""
        if narration_context:
            title = narration_context.get("title", "Untitled")
            beats = narration_context.get("narration", [])
            beat_texts = [b.get("text", b.get("narration", ""))[:100] for b in beats[:6]]
            narration_snippet = f"""

SCRIPT CONTEXT (use this to inform your creative decisions):
Title: {title}
Total beats: {len(beats)}
Opening beats:
{chr(10).join(f'- {t}' for t in beat_texts)}
"""

        prompt = f"""The user wants to create this type of video:

"{user_direction}"
{narration_snippet}
{_get_creative_direction_prompt()}"""

        def _call():
            return client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )

        response, _retries = _retry_api_call(_call, description="expand_creative_direction")

        try:
            result = json.loads(response.text)

            # Validate suggested_style_defaults
            defaults = result.get("suggested_style_defaults", {})
            if "prompt_schema" not in defaults:
                detail_level = defaults.get("style_intent", {}).get("detail_level", "Standard")
                defaults["prompt_schema"] = _build_default_schema_from_detail_level(detail_level)

            # Ensure locked fields in always_include
            always = defaults.get("prompt_schema", {}).get("always_include", [])
            for field in LOCKED_PROMPT_FIELDS:
                if field not in always:
                    always.append(field)
            defaults.setdefault("prompt_schema", {})["always_include"] = always
            result["suggested_style_defaults"] = defaults

            print(f"[Creative Direction] Expanded: {result.get('direction_summary', '')[:80]}")
            return result

        except json.JSONDecodeError:
            print(f"[Creative Direction] Failed to parse JSON: {response.text}")
            return "Error: Could not parse creative direction response"

    except Exception as e:
        print(f"[Creative Direction] Expand failed: {e}")
        return f"Error: {str(e)}"


def refine_creative_direction(current_direction, user_feedback, narration_context=None, api_key=None):
    """
    Refine an already-expanded creative direction based on user feedback.

    Args:
        current_direction: The current expanded direction dict
        user_feedback: User's adjustment request (e.g., "make it more playful")
        narration_context: Optional narration JSON for context
        api_key: Optional Gemini API key

    Returns:
        Updated direction dict (same structure), or error string starting with "Error:"
    """
    try:
        client = get_client(api_key)

        narration_snippet = ""
        if narration_context:
            title = narration_context.get("title", "Untitled")
            beats = narration_context.get("narration", [])
            beat_texts = [b.get("text", b.get("narration", ""))[:100] for b in beats[:6]]
            narration_snippet = f"""

SCRIPT CONTEXT:
Title: {title}
Total beats: {len(beats)}
Opening beats:
{chr(10).join(f'- {t}' for t in beat_texts)}
"""

        prompt = f"""You previously expanded a creative direction for a video production.
Here is the current creative direction:

{json.dumps(current_direction, indent=2)}
{narration_snippet}
The user wants to adjust it. Their feedback:
"{user_feedback}"

Please regenerate the COMPLETE creative direction incorporating this feedback.
Keep everything the user didn't mention the same, and update what they requested.
Also update the suggested_style_defaults if the changes affect visual style.

{_get_creative_direction_prompt()}"""

        def _call():
            return client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )

        response, _retries = _retry_api_call(_call, description="refine_creative_direction")

        try:
            result = json.loads(response.text)

            # Validate suggested_style_defaults
            defaults = result.get("suggested_style_defaults", {})
            if "prompt_schema" not in defaults:
                detail_level = defaults.get("style_intent", {}).get("detail_level", "Standard")
                defaults["prompt_schema"] = _build_default_schema_from_detail_level(detail_level)

            always = defaults.get("prompt_schema", {}).get("always_include", [])
            for field in LOCKED_PROMPT_FIELDS:
                if field not in always:
                    always.append(field)
            defaults.setdefault("prompt_schema", {})["always_include"] = always
            result["suggested_style_defaults"] = defaults

            print(f"[Creative Direction] Refined: {result.get('direction_summary', '')[:80]}")
            return result

        except json.JSONDecodeError:
            print(f"[Creative Direction] Failed to parse refined JSON: {response.text}")
            return "Error: Could not parse refined creative direction response"

    except Exception as e:
        print(f"[Creative Direction] Refine failed: {e}")
        return f"Error: {str(e)}"


def generate_tts(text, voice_name="Kore", style_instructions="", api_key=None):
    """
    Generate speech audio from text using Gemini TTS.
    Returns the path to the saved WAV file, or an error string.
    """
    import wave

    client = get_client(api_key)
    os.makedirs(os.path.join(os.path.dirname(__file__), '..', 'generated_audio'), exist_ok=True)
    timestamp = int(time.time())

    # Build the prompt: prepend style instructions if provided
    if style_instructions.strip():
        prompt = f"{style_instructions.strip()}: {text}"
    else:
        prompt = text

    try:
        print(f"[TTS] Generating with voice={voice_name}, style='{style_instructions}'")

        def _call():
            return client.models.generate_content(
                model="gemini-2.5-flash-preview-tts",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice_name,
                            )
                        )
                    ),
                )
            )

        response, _retries = _retry_api_call(_call, description="generate_tts")

        # Extract raw PCM audio data
        data = response.candidates[0].content.parts[0].inline_data.data

        filename = os.path.join(
            os.path.dirname(__file__), '..', 'generated_audio',
            f"tts_{timestamp}.wav"
        )

        # Save as WAV file (24kHz, 16-bit, mono)
        with wave.open(filename, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(data)

        print(f"[TTS] Success! Saved to {filename}")
        return filename

    except Exception as e:
        print(f"[TTS] Failed: {e}")
        return f"Error: {str(e)}"


# ── In-memory storage for async video operations ──
_video_operations = {}  # operation_name -> operation object


def _decode_ref_image(img_data):
    """Decode a base64 data URI into (bytes, mime_type)."""
    if ',' in img_data:
        header, b64_data = img_data.split(',', 1)
        mime_type = header.split(':')[1].split(';')[0] if ':' in header else "image/jpeg"
    else:
        b64_data = img_data
        mime_type = "image/jpeg"
    return base64.b64decode(b64_data), mime_type


def generate_scene_image(prompt, model_name="gemini-3-pro-image-preview",
                         aspect_ratio="16:9", resolution="2K",
                         style_images=None, characters=None,
                         character_images=None, additional_context="",
                         style_mode="art_only", scene_id=None, api_key=None):
    """
    Generate an image for a specific scene using Gemini or Imagen models.
    Supports style/character reference images for Gemini models.
    Imagen models use text-only prompts (refs not supported).

    Args:
        prompt: The scene's first_frame_prompt
        model_name: Image model name. Gemini models support refs, Imagen models are text-only.
            Gemini: 'gemini-3-pro-image-preview', 'gemini-2.5-flash-image'
            Imagen: 'imagen-4.0-generate-001', 'imagen-4.0-fast-generate-001', 'imagen-4.0-ultra-generate-001'
        aspect_ratio: e.g. '16:9', '9:16', '1:1'
        resolution: '1K', '2K', or '4K'
        style_images: List of base64 data URIs for style reference (max 4, Gemini only)
        characters: List of dicts [{name: str, images: [base64_str]}] for labeled character refs (Gemini only)
        character_images: Legacy flat list of base64 data URIs (fallback if characters not provided)
        additional_context: Extra style notes (e.g. '2D Cartoon Style')
        scene_id: Identifier for the scene (used in filename)
        api_key: Gemini API key

    Returns:
        dict with {success, image_url, scene_id} or {error}
    """
    try:
        client = get_client(api_key)
        os.makedirs(os.path.join(os.path.dirname(__file__), '..', 'generated_images'), exist_ok=True)
        timestamp = int(time.time())
        safe_id = str(scene_id).replace("/", "_").replace(" ", "_")

        # ── Imagen models: text-only, no multipart refs ──
        if model_name.startswith("imagen-"):
            full_prompt = prompt
            if additional_context:
                full_prompt = f"{prompt}\n\nStyle notes: {additional_context}"

            print(f"[Scene Image] Generating scene {scene_id} with Imagen model {model_name}")

            def _call_imagen():
                return client.models.generate_images(
                    model=model_name,
                    prompt=full_prompt,
                    config=types.GenerateImagesConfig(
                        number_of_images=1,
                        aspect_ratio=aspect_ratio,
                    )
                )

            response, _retries = _retry_api_call(_call_imagen, description=f"scene_imagen({scene_id})")

            if response.generated_images:
                image_data = response.generated_images[0].image.image_bytes
                filename = f"scene_{safe_id}_{timestamp}.png"
                filepath = os.path.join(
                    os.path.dirname(__file__), '..', 'generated_images', filename
                )
                with open(filepath, "wb") as f:
                    f.write(image_data)
                print(f"[Scene Image] Scene {scene_id} saved to {filepath}")
                return {
                    "success": True,
                    "image_url": f"/generated/{filename}",
                    "scene_id": scene_id,
                    "local_path": filepath,
                }
            return {"error": f"No image generated for scene {scene_id}. Imagen returned no image data."}

        # ── Gemini models: support multipart style/character refs ──
        parts = []
        has_structured_chars = characters and len(characters) > 0
        has_legacy_chars = character_images and len(character_images) > 0
        has_style = style_images and len(style_images) > 0

        # 1. System instruction: overall task framing and rules
        system_instruction = (
            "You are generating a single image for a scene in a visual story. "
            "You will receive CHARACTER REFERENCE images (defining who appears) "
            "and STYLE REFERENCE images (defining the visual aesthetic).\n"
            "CRITICAL RULES:\n"
            "- Each character's FACIAL FEATURES, HAIR, BODY TYPE, AGE, SKIN TONE, and ETHNICITY "
            "must EXACTLY match their reference images. This is non-negotiable.\n"
            "- Characters must wear ONLY the clothing described in the scene prompt, "
            "NOT the clothing from their reference images.\n"
            "- The art style, colors, lighting, and medium must match the STYLE references, "
            "NOT the character references.\n"
            "- If a character name appears in the scene description, you MUST use "
            "that specific character's reference.\n"
            "- Do NOT blend or merge different characters' features together.\n"
            "- Do NOT invent new characters not described in the scene.\n"
        )
        parts.append(types.Part(text=system_instruction))

        # 2. Character references: labeled per-character sections
        if has_structured_chars:
            for char in characters:
                char_name = char.get('name', 'Unknown')
                char_images = char.get('images', [])
                if not char_images:
                    continue

                ref_mode = char.get('ref_mode', 'identity')
                if ref_mode == 'full_look':
                    char_instruction = (
                        f"\n--- CHARACTER: \"{char_name}\" (Full Look) ---\n"
                        f"The following {len(char_images)} image(s) show \"{char_name}\". "
                        f"Preserve this character's COMPLETE appearance exactly: facial features, "
                        f"hair, skin tone, body build, clothing, outfit, accessories, and overall "
                        f"aesthetic. They must look identical to these references in every way:"
                    )
                else:  # identity (default)
                    char_instruction = (
                        f"\n--- CHARACTER: \"{char_name}\" (Identity Only) ---\n"
                        f"The following {len(char_images)} image(s) show \"{char_name}\". "
                        f"Preserve this character's exact facial structure, features, hair, "
                        f"skin tone, body build, and age. Do NOT copy their clothing, outfit, "
                        f"or accessories from these references — dress them according to the "
                        f"scene prompt instead:"
                    )
                parts.append(types.Part(text=char_instruction))

                for img_data in char_images[:4]:
                    image_bytes, mime_type = _decode_ref_image(img_data)
                    parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))

            # Character-to-scene binding instruction
            char_names = [c.get('name', 'Unknown') for c in characters if c.get('images')]
            if char_names:
                binding = (
                    "\n--- CHARACTER BINDING ---\n"
                    f"Characters available in this scene: {', '.join(char_names)}.\n"
                    "When the scene description mentions a person, map them to the "
                    "closest matching character reference above based on the description. "
                    "If the scene explicitly names a character, you MUST use exactly "
                    "that character's reference images for their appearance.\n"
                )
                parts.append(types.Part(text=binding))

        elif has_legacy_chars:
            # Legacy fallback: flat unlabeled images
            parts.append(types.Part(text=(
                "These are character reference images. You MUST strictly maintain "
                "their core physical identity (facial features, hair, body structure, "
                "age, skin tone, ethnicity) in the generated scene. "
                "Do NOT copy clothing or poses from these references:"
            )))
            for img_data in character_images[:10]:
                image_bytes, mime_type = _decode_ref_image(img_data)
                parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))

        # 3. Style reference images (mode-dependent instruction)
        if has_style:
            if style_mode == "full":
                style_instruction = (
                    "\n--- STYLE REFERENCE ---\n"
                    "The following images define the EXACT visual style for the output. "
                    "Match this art style, color palette, lighting, mood, texture, line weight, "
                    "and artistic medium PRECISELY. The style references override ALL visual "
                    "aspects including mood and lighting. Only use character references for "
                    "physical identity, not for style:"
                )
            elif style_mode == "loose":
                style_instruction = (
                    "\n--- STYLE REFERENCE (loose inspiration) ---\n"
                    "Use the following images as loose visual inspiration for the general "
                    "aesthetic direction. The scene prompt takes priority for ALL visual "
                    "decisions including style, lighting, mood, and atmosphere. These "
                    "references are suggestions, not strict requirements:"
                )
            else:  # art_only (default)
                style_instruction = (
                    "\n--- STYLE REFERENCE ---\n"
                    "Match the art style, technique, color palette, texture, and line weight "
                    "from the following images. But for lighting, mood, atmosphere, and time "
                    "of day — follow the scene prompt instead. The style references define "
                    "HOW things look (medium, rendering) but NOT the scene's mood or lighting:"
                )
            parts.append(types.Part(text=style_instruction))
            for img_data in style_images[:4]:
                image_bytes, mime_type = _decode_ref_image(img_data)
                parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))

        # 4. Scene prompt with additional context (LAST for recency bias)
        scene_block = f"\n--- SCENE TO GENERATE ---\n{prompt}"
        if additional_context:
            scene_block += f"\n\nADDITIONAL STYLE NOTES: {additional_context}"

        # Mode-dependent reminder
        if style_mode == "full":
            scene_block += (
                "\n\nREMINDER: Each character MUST visually match their reference images. "
                "The art style, lighting, and mood MUST match the style reference images. "
                "Generate a single cohesive image."
            )
        elif style_mode == "loose":
            scene_block += (
                "\n\nREMINDER: Each character MUST visually match their reference images. "
                "Follow the scene description above for style, lighting, and mood. "
                "Style references are only loose inspiration. Generate a single cohesive image."
            )
        else:  # art_only
            scene_block += (
                "\n\nREMINDER: Each character MUST visually match their reference images. "
                "Use the art style/medium from the style references, but follow THIS scene's "
                "description for lighting, mood, and atmosphere. Generate a single cohesive image."
            )
        parts.append(types.Part(text=scene_block))

        # Log what we're sending
        if has_structured_chars:
            char_summary = ", ".join(
                f"{c.get('name','?')}({len(c.get('images',[]))} imgs)"
                for c in characters if c.get('images')
            )
        elif has_legacy_chars:
            char_summary = f"{len(character_images)} unlabeled"
        else:
            char_summary = "none"
        print(f"[Scene Image] Generating scene {scene_id} with {model_name} "
              f"({len(style_images or [])} style refs, chars=[{char_summary}]"
              f"{', context=' + repr(additional_context[:50]) if additional_context else ''})")

        def _call_gemini_scene():
            return client.models.generate_content(
                model=model_name,
                contents=types.Content(parts=parts),
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                    image_config=types.ImageConfig(
                        aspect_ratio=aspect_ratio,
                    ),
                )
            )

        response, _retries = _retry_api_call(_call_gemini_scene, description=f"scene_gemini({scene_id})")

        # Extract image from response
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                    image_data = part.inline_data.data
                    ext = part.inline_data.mime_type.split("/")[-1]
                    filename = f"scene_{safe_id}_{timestamp}.{ext}"
                    filepath = os.path.join(
                        os.path.dirname(__file__), '..', 'generated_images', filename
                    )
                    with open(filepath, "wb") as f:
                        f.write(image_data)
                    print(f"[Scene Image] Scene {scene_id} saved to {filepath}")
                    return {
                        "success": True,
                        "image_url": f"/generated/{filename}",
                        "scene_id": scene_id,
                        "local_path": filepath,
                    }

        return {"error": f"No image generated for scene {scene_id}. Model returned no image data."}

    except Exception as e:
        print(f"[Scene Image] Failed for scene {scene_id}: {e}")
        traceback.print_exc()
        return {"error": str(e)}


def start_video_generation(image_path, prompt, model_name="veo-3.1-generate-preview",
                           aspect_ratio="16:9", duration=6,
                           resolution="720p", scene_id=None, api_key=None):
    """
    Start async video generation (image-to-video) using Veo 3.1.

    Args:
        image_path: Local path to the source image
        prompt: Animation/motion prompt (veo_prompt)
        model_name: 'veo-3.1-generate-preview' (quality+audio) or 'veo-3.1-fast-generate-preview' (fast)
        aspect_ratio: '16:9' or '9:16'
        duration: 4, 6, or 8 (seconds)
        resolution: '720p', '1080p', or '4k'
        scene_id: Scene identifier
        api_key: Gemini API key

    Returns:
        dict with {operation_name, scene_id, status} or {error}
    """
    try:
        client = get_client(api_key)

        # Read the source image
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        # Determine mime type from extension
        ext = os.path.splitext(image_path)[1].lower()
        mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
        mime_type = mime_map.get(ext, "image/png")

        print(f"[Veo] Starting animation for scene {scene_id} with {model_name} "
              f"(duration={duration}s, resolution={resolution})")

        def _call():
            return client.models.generate_videos(
                model=model_name,
                prompt=prompt,
                image=types.Image(
                    image_bytes=image_bytes,
                    mime_type=mime_type,
                ),
                config=types.GenerateVideosConfig(
                    aspect_ratio=aspect_ratio,
                    resolution=resolution,
                    duration_seconds=int(duration),
                ),
            )

        operation, _retries = _retry_api_call(_call, description=f"veo_start({scene_id})")

        # Store operation for later polling
        op_name = operation.name
        _video_operations[op_name] = operation

        print(f"[Veo] Operation started: {op_name}")
        return {
            "operation_name": op_name,
            "scene_id": scene_id,
            "status": "in_progress",
        }

    except Exception as e:
        print(f"[Veo] Failed to start for scene {scene_id}: {e}")
        traceback.print_exc()
        return {"error": str(e)}


def poll_video_generation(operation_name, scene_id=None, api_key=None):
    """
    Poll an async Veo video generation operation.

    Args:
        operation_name: The operation name from start_video_generation
        scene_id: Scene identifier
        api_key: Gemini API key

    Returns:
        dict with {status, video_url, scene_id} or {status: 'in_progress'} or {error}
    """
    try:
        client = get_client(api_key)

        # Retrieve stored operation
        operation = _video_operations.get(operation_name)
        if not operation:
            return {"error": f"Operation {operation_name} not found. Server may have restarted."}

        # Refresh operation status
        operation = client.operations.get(operation)
        _video_operations[operation_name] = operation

        if not operation.done:
            return {"status": "in_progress", "scene_id": scene_id}

        # Operation complete — download video
        os.makedirs(os.path.join(os.path.dirname(__file__), '..', 'generated_videos'), exist_ok=True)
        timestamp = int(time.time())

        if operation.response and operation.response.generated_videos:
            video = operation.response.generated_videos[0]

            safe_id = str(scene_id).replace("/", "_").replace(" ", "_")
            filename = f"scene_{safe_id}_{timestamp}.mp4"
            filepath = os.path.join(
                os.path.dirname(__file__), '..', 'generated_videos', filename
            )

            # Download and save video
            client.files.download(file=video.video)
            video.video.save(filepath)

            print(f"[Veo] Scene {scene_id} video saved to {filepath}")

            # Clean up stored operation
            del _video_operations[operation_name]

            return {
                "status": "completed",
                "video_url": f"/video/{filename}",
                "scene_id": scene_id,
                "local_path": filepath,
            }

        # Operation done but no video (possibly blocked by safety filters)
        del _video_operations[operation_name]
        return {
            "status": "failed",
            "error": "Video generation completed but no video was returned (possibly blocked by safety filters).",
            "scene_id": scene_id,
        }

    except Exception as e:
        print(f"[Veo] Poll failed for scene {scene_id}: {e}")
        traceback.print_exc()
        return {"status": "failed", "error": str(e), "scene_id": scene_id}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Interact with Google Gemini API")
    parser.add_argument("--prompt", type=str, required=True, help="The prompt to send")
    parser.add_argument("--model", type=str, default="gemini-3-flash-preview", help="Model name")
    parser.add_argument("--image", action="store_true", help="Generate an image instead of text")

    args = parser.parse_args()

    if args.image:
        result = generate_image_content(args.prompt)
    else:
        result = generate_content(args.prompt, args.model)

    print(result)
