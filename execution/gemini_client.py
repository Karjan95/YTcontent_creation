import os
import argparse
import base64
import time
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


def generate_content(prompt, model_name="gemini-2.0-flash", use_search=False, temperature=None, api_key=None):
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


def analyze_style_from_images(image_data_list, api_key=None):
    """
    Analyze visual style from 1-4 base64-encoded images using Gemini Vision.
    Returns a comprehensive style description string.

    Args:
        image_data_list: List of base64 data URIs (e.g., "data:image/jpeg;base64,/9j/4AAQ...")
        api_key: Optional Gemini API key (falls back to env var)

    Returns:
        String describing the extracted visual style, or error string starting with "Error:"
    """
    try:
        client = get_client(api_key)

        # Build multimodal prompt with images + text
        parts = []

        # Add all images
        for idx, img_data in enumerate(image_data_list):
            # Extract base64 data and mime type from data URI
            if ',' in img_data:
                header, b64_data = img_data.split(',', 1)
                # Extract mime type from header like "data:image/jpeg;base64"
                mime_type = header.split(':')[1].split(';')[0] if ':' in header else "image/jpeg"
            else:
                b64_data = img_data
                mime_type = "image/jpeg"

            # Decode base64 to bytes
            image_bytes = base64.b64decode(b64_data)

            parts.append(
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=mime_type
                )
            )

        # Add analysis instruction
        prompt = "Analyze this image and describe the visual style."

        parts.append(types.Part(text=prompt))

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=types.Content(parts=parts)
        )

        style_description = response.text.strip()
        print(f"[Style Analysis] Extracted style from {len(image_data_list)} images")
        return style_description

    except Exception as e:
        print(f"[Style Analysis] Failed: {e}")
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Interact with Google Gemini API")
    parser.add_argument("--prompt", type=str, required=True, help="The prompt to send")
    parser.add_argument("--model", type=str, default="gemini-2.0-flash", help="Model name")
    parser.add_argument("--image", action="store_true", help="Generate an image instead of text")

    args = parser.parse_args()

    if args.image:
        result = generate_image_content(args.prompt)
    else:
        result = generate_content(args.prompt, args.model)

    print(result)
