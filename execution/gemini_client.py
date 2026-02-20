import os
import argparse
import base64
import time
import json
import traceback
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Load environment variables from project root
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))


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

        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config
        )
        if response.text is None:
            return "Error: Gemini returned an empty response (possibly blocked by safety filters)."
        return response.text
    except Exception as e:
        return f"Error: {str(e)}"


def generate_image_content(prompt, api_key=None):
    """
    Generate an image using Gemini's native image generation.
    Uses gemini-2.0-flash-exp-image-generation which supports people,
    unlike Imagen which blocks real person prompts.
    Falls back to imagen-4.0-generate-001 if the first model fails.
    """
    client = get_client(api_key)
    os.makedirs(os.path.join(os.path.dirname(__file__), '..', 'generated_images'), exist_ok=True)
    timestamp = int(time.time())

    # --- Strategy 1: Gemini native image generation (supports people) ---
    try:
        print(f"[Strategy 1] Trying gemini-3-pro-image-preview...")
        response = client.models.generate_content(
            model="gemini-3-pro-image-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            )
        )

        # Extract image from response parts
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
                    print(f"[Strategy 1] Success! Saved to {filename}")
                    return filename

        print(f"[Strategy 1] No image in response. Trying Strategy 2...")

    except Exception as e:
        print(f"[Strategy 1] Failed: {e}. Trying Strategy 2...")

    # --- Strategy 2: Imagen model (faster, higher quality, but blocks people) ---
    try:
        print(f"[Strategy 2] Trying imagen-4.0-generate-001...")
        response = client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
            )
        )

        if response.generated_images:
            image_data = response.generated_images[0].image.image_bytes
            filename = os.path.join(
                os.path.dirname(__file__), '..', 'generated_images',
                f"image_{timestamp}_0.png"
            )
            with open(filename, "wb") as f:
                f.write(image_data)
            print(f"[Strategy 2] Success! Saved to {filename}")
            return filename

        print(f"[Strategy 2] No images generated. Full response: {response}")
        return "Error: Both models failed to generate an image. Try a different prompt (avoid real person names)."

    except Exception as e:
        print(f"[Strategy 2] Failed: {e}")
        return f"Error: {str(e)}"


# All possible prompt fields for the dynamic schema system
PROMPT_FIELD_UNIVERSE = [
    "shot_size", "subject", "arrangement", "background", "mood",
    "lighting", "lighting_direction", "camera_lens", "camera_aperture",
    "dof", "film_stock", "color_restriction", "output_style",
    "room_objects", "made_out_of", "tags",
]

# Fields that are always required regardless of style
LOCKED_PROMPT_FIELDS = ["shot_size", "subject", "arrangement", "background"]


def _build_default_schema_from_detail_level(detail_level: str) -> dict:
    """Build a sensible default prompt_schema when AI doesn't provide one."""
    detail = (detail_level or "").lower()
    if "minimal" in detail:
        return {
            "always_include": LOCKED_PROMPT_FIELDS + ["mood"],
            "include": ["color_restriction", "output_style"],
            "exclude": ["camera_lens", "camera_aperture", "dof", "film_stock",
                        "made_out_of", "lighting", "lighting_direction", "room_objects", "tags"],
        }
    elif "abstract" in detail:
        return {
            "always_include": LOCKED_PROMPT_FIELDS + ["mood"],
            "include": ["color_restriction", "output_style", "tags"],
            "exclude": ["camera_lens", "camera_aperture", "dof", "film_stock",
                        "made_out_of", "lighting_direction", "room_objects"],
        }
    else:  # High Detail / Standard
        return {
            "always_include": LOCKED_PROMPT_FIELDS + ["mood"],
            "include": ["lighting", "lighting_direction", "camera_lens", "camera_aperture",
                        "dof", "film_stock", "color_restriction", "output_style",
                        "room_objects", "made_out_of", "tags"],
            "exclude": [],
        }


def _get_style_analysis_prompt():
    """Return the shared style analysis prompt used by both image and text analysis."""
    return """Analyze the provided style reference to create a **Production Style Guide** for an AI video generator that will create NARRATIVE SCENES (not product photos).

YOUR JOB HAS THREE PARTS:

═══ PART 1: EXTRACT ARTISTIC INTENT (CHARACTER RENDERING STYLE) ═══

CRITICAL DISTINCTIONS:
1. ARTISTIC INTENT = the CHARACTER RENDERING STYLE (e.g., "3D stylized figures like Pixar", "flat 2D cartoon", "anime")
2. INCIDENTAL DETAILS = the CONTEXT of the reference image itself (e.g., studio backdrop, white background, product display angle)
3. SCENE CONTEXT = this is a VIDEO — characters will be placed in REAL STORY ENVIRONMENTS, not on studio backdrops

⚠️ COMMON TRAP — DO NOT FALL INTO THIS:
If the reference shows a 3D figure on a white/studio background, the style is the CHARACTER RENDERING (3D, stylized, collectible proportions) — NOT "product photography on studio backdrops."
The characters will appear in forests, houses, streets, etc. — wherever the story takes place.
NEVER describe the style as "product photography", "studio showcase", or "display figure."
The reference defines HOW CHARACTERS LOOK, not WHERE THEY ARE.

═══ PART 2: DEFINE HOW SCENES SHOULD LOOK ═══

Since these prompts are for a VIDEO that tells a STORY, the environments must:
- Match the NARRATIVE (if the story mentions a forest, the background is a forest)
- Be rendered in the SAME VISUAL STYLE as the characters (3D stylized world if 3D characters, etc.)
- Support the EMOTIONAL BEAT of each scene
- NOT be "studio backdrops" or "clean seamless backgrounds" (unless the story literally takes place in a studio)

For "scene_complexity": Think about the STORY WORLD, not the reference image's background.
- A 3D animated character style → "Complex Environments" (like Pixar/animated movies, characters live in rich worlds)
- A minimalist stick figure → "Simple Environments" (matching the simple aesthetic)

═══ PART 3: RECOMMEND A PROMPT SCHEMA ═══

Based on the artistic intent, decide which prompt fields are RELEVANT for this style.

The UNIVERSE of possible prompt fields is:
- shot_size: Camera framing (wide, medium, close-up, extreme close-up)
- subject: Physical description of characters/objects in scene
- arrangement: Pose, body position, camera angle relative to subject
- background: Environment or backdrop description — MUST come from the story/narration
- mood: Emotional atmosphere of the scene
- lighting: Lighting setup, quality, direction
- lighting_direction: Specific key light position, fill, color temperature
- camera_lens: Focal length in mm (e.g., 35mm, 85mm)
- camera_aperture: f-stop value (e.g., f/2.8)
- dof: Depth of field description
- film_stock: Film grain, texture, analog feel
- color_restriction: Color palette rules
- output_style: Overall aesthetic (e.g., "3D animated film", "watercolor illustration", "pixel art")
- room_objects: Props and objects in the scene
- made_out_of: Material and texture of the subject
- tags: Aesthetic keyword tags

RULES FOR SCHEMA:
- shot_size, subject, arrangement, background MUST ALWAYS be included (composition is universal)
- For minimalist/simple styles: EXCLUDE technical camera fields (lens, aperture, dof), film_stock, made_out_of, lighting_direction
- For cinematic/realistic styles: INCLUDE everything
- For abstract/artistic styles: EXCLUDE technical camera, INCLUDE color_restriction, output_style, tags
- For 3D animated styles: INCLUDE lighting, output_style, made_out_of, room_objects. Consider whether technical camera fields add value.

═══ OUTPUT FORMAT ═══

Return a JSON object with exactly this structure:
{
    "style_summary": "One sentence describing the CHARACTER RENDERING STYLE (not the background of the reference image)",
    "style_intent": {
        "detail_level": "Minimalist | Standard | High Detail | Abstract",
        "scene_complexity": "How complex should STORY ENVIRONMENTS be (not the reference image's background)",
        "camera_language": "How to describe camera work for this style",
        "lighting_instruction": "How to handle lighting in prompts for this style",
        "subject_framing": "Default character/subject framing",
        "writing_style": "How prompt text should be written (concise/descriptive/technical)",
        "color_palette": "Color tendencies of this style",
        "texture": "Surface quality of characters (flat, textured, smooth vinyl, etc.)",
        "mood_default": "Default emotional quality"
    },
    "prompt_schema": {
        "always_include": ["shot_size", "subject", "arrangement", "background", "mood"],
        "include": ["fields that ARE relevant for this style"],
        "exclude": ["fields that are NOT relevant for this style"]
    }
}

REMEMBER: The "background" field describes STORY ENVIRONMENTS (forests, cities, rooms), NOT studio backdrops.
The "scene_complexity" should reflect the STORY WORLD complexity, not the reference image's background."""


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

        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=types.Content(parts=parts),
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

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

        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

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
        response = client.models.generate_content(
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


def generate_scene_image(prompt, model_name="gemini-3-pro-image-preview",
                         aspect_ratio="16:9", resolution="2K",
                         style_images=None, character_images=None,
                         additional_context="", scene_id=None, api_key=None):
    """
    Generate an image for a specific scene using Gemini's image generation models.
    Supports style reference images and character reference images for consistency.

    Args:
        prompt: The scene's first_frame_prompt
        model_name: 'gemini-2.5-flash-image' (fast) or 'gemini-3-pro-image-preview' (quality)
        aspect_ratio: e.g. '16:9', '9:16', '1:1'
        resolution: '1K', '2K', or '4K'
        style_images: List of base64 data URIs for style reference (max 4)
        character_images: List of base64 data URIs for character reference (max 10)
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

        # Build multipart contents list
        parts = []

        # 1. Add character reference images (First to define subjects)
        if character_images:
            parts.append(types.Part(text="These are the character reference images. Maintain their identity strictly in the generated scene:"))
            for img_data in character_images[:10]:
                if ',' in img_data:
                    header, b64_data = img_data.split(',', 1)
                    mime_type = header.split(':')[1].split(';')[0] if ':' in header else "image/jpeg"
                else:
                    b64_data = img_data
                    mime_type = "image/jpeg"
                image_bytes = base64.b64decode(b64_data)
                parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))

        # 2. Add style reference images (Second to apply style over subjects)
        # Explicit text instruction to override character style
        if style_images:
            parts.append(types.Part(text="These are the style reference images. The final image MUST match this visual style exactly. Ignore the style of the character references above:"))
            for img_data in style_images[:4]:
                if ',' in img_data:
                    header, b64_data = img_data.split(',', 1)
                    mime_type = header.split(':')[1].split(';')[0] if ':' in header else "image/jpeg"
                else:
                    b64_data = img_data
                    mime_type = "image/jpeg"
                image_bytes = base64.b64decode(b64_data)
                parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))

        # 3. Add the scene prompt with additional context (Last for recency)
        full_prompt = prompt
        if additional_context:
            full_prompt = f"{prompt}\n\nStyle notes: {additional_context}"
        
        # Explicitly tie it all together
        parts.append(types.Part(text=f"Generate an image of the scene described below, featuring the characters above, in the style of the style references above:\n\n{full_prompt}"))

        print(f"[Scene Image] Generating scene {scene_id} with {model_name} "
              f"({len(style_images or [])} style refs, {len(character_images or [])} char refs)")

        response = client.models.generate_content(
            model=model_name,
            contents=types.Content(parts=parts),
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
                image_config=types.ImageConfig(
                    aspect_ratio=aspect_ratio,
                ),
            )
        )

        # Extract image from response
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                    image_data = part.inline_data.data
                    ext = part.inline_data.mime_type.split("/")[-1]
                    safe_id = str(scene_id).replace("/", "_").replace(" ", "_")
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
        model_name: 'veo-3.1-generate-preview' (quality+audio) or 'veo-3.1-fast'
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

        operation = client.models.generate_videos(
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
