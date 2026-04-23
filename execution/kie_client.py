"""
Kie.ai API Client — Multi-model image and video generation via Kie.ai's unified API.

This module is completely separate from gemini_client.py. It handles:
- Model registry with per-model parameter quirks
- Task creation, polling, image upload
- Credit checking
- Input normalization across 14+ models with different parameter formats

API Docs: https://docs.kie.ai/
"""

import os
import json
import time
import logging
import tempfile
import urllib.request
import urllib.error
import urllib.parse

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────
#  CONSTANTS
# ────────────────────────────────────────────────────────────────

KIE_BASE_URL = "https://api.kie.ai/api/v1"
KIE_FILE_UPLOAD_URL = "https://kieai.redpandaai.co/api/file-url-upload"
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds

# Browser-like headers to avoid Cloudflare 403/1010 blocks
_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


# ────────────────────────────────────────────────────────────────
#  MODEL REGISTRY
# ────────────────────────────────────────────────────────────────

KIE_MODELS = {
    # ══════════════ VIDEO MODELS ══════════════

    "kling-3.0": {
        "display_name": "Kling 3.0",
        "provider": "Kuaishou",
        "type": "video",
        "modes": ["t2v", "i2v"],
        "model_id": "kling-3.0/video",
        "durations": ["3", "5", "10", "15"],
        "resolutions": ["720p", "1080p"],
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "supports_audio": True,
        "image_param": "image_urls",
        "max_images": 1,
        "pricing": {
            "720p": {"per_sec_no_audio": 0.10, "per_sec_audio": 0.15},
            "1080p": {"per_sec_no_audio": 0.135, "per_sec_audio": 0.20},
        },
        "description": "Top-tier video generation with multi-shot storytelling and native audio",
    },

    "kling-2.6": {
        "display_name": "Kling 2.6",
        "provider": "Kuaishou",
        "type": "video",
        "modes": ["i2v"],
        "model_id": "kling-2.6/image-to-video",
        "durations": ["5", "10"],
        "resolutions": ["720p", "1080p"],
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "supports_audio": True,
        "image_param": "image_urls",
        "max_images": 1,
        "pricing": {
            "5s_no_audio": 0.28, "10s_no_audio": 0.55,
            "5s_audio": 0.55, "10s_audio": 1.10,
        },
        "description": "Image-to-video with optional audio synthesis",
    },

    "sora-2": {
        "display_name": "Sora 2 (Stable)",
        "provider": "OpenAI",
        "type": "video",
        "modes": ["i2v"],
        "model_id": "sora-2-image-to-video-stable",
        "durations": ["10", "15"],
        "resolutions": ["720p"],
        "aspect_ratios": ["landscape", "portrait"],
        "supports_audio": False,
        "image_param": "image_urls",
        "max_images": 1,
        "uses_n_frames": True,
        "has_progress": True,
        "pricing": {"10s": 0.15, "15s": 0.175},
        "description": "OpenAI's video model with progress tracking and stable output",
    },

    "grok-imagine-video": {
        "display_name": "Grok Imagine",
        "provider": "xAI",
        "type": "video",
        "modes": ["i2v"],
        "model_id": "grok-imagine/image-to-video",
        "durations": ["6", "10", "15"],
        "resolutions": ["480p", "720p"],
        "aspect_ratios": ["2:3", "3:2", "1:1", "9:16", "16:9"],
        "supports_audio": False,
        "image_param": "image_urls",
        "max_images": 1,
        "pricing": {
            "6s_480p": 0.05, "6s_720p": 0.10,
            "10s_480p": 0.10, "10s_720p": 0.15,
            "15s_480p": 0.15, "15s_720p": 0.20,
        },
        "description": "Budget-friendly video generation from xAI",
    },

    "wan-2.6": {
        "display_name": "Wan 2.6",
        "provider": "Alibaba",
        "type": "video",
        "modes": ["i2v"],
        "model_id": "wan/2-6-image-to-video",
        "durations": ["5", "10", "15"],
        "resolutions": ["720p", "1080p"],
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "supports_audio": False,
        "image_param": "image_urls",
        "max_images": 1,
        "pricing": {
            "5s_720p": 0.35, "5s_1080p": 0.53,
            "10s_720p": 0.70, "10s_1080p": 1.05,
            "15s_720p": 1.05, "15s_1080p": 1.58,
        },
        "description": "High-quality video with precise motion control",
    },

    "hailuo-2.3": {
        "display_name": "Hailuo 2.3 Pro",
        "provider": "MiniMax",
        "type": "video",
        "modes": ["i2v"],
        "model_id": "hailuo/2-3-image-to-video-pro",
        "durations": ["6", "10"],
        "resolutions": ["768P", "1080P"],
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "supports_audio": False,
        "image_param": "image_url",  # QUIRK: singular string, NOT array
        "max_images": 1,
        "constraints": {"no_10s_1080p": True},  # 10s at 1080P not supported
        "pricing": {
            "6s_768P": 0.22, "10s_768P": 0.45,
            "6s_1080P": 0.39,
        },
        "description": "Physics-based motion with facial micro-expressions",
    },

    "seedance-2": {
        "display_name": "Seedance 2.0",
        "provider": "ByteDance",
        "type": "video",
        "modes": ["t2v", "i2v"],
        "model_id": "bytedance/seedance-2",
        "durations": ["5", "8", "10", "15"],
        "resolutions": ["480p", "720p", "1080p"],
        "aspect_ratios": ["1:1", "4:3", "3:4", "16:9", "9:16", "21:9", "adaptive"],
        "supports_audio": True,
        "uses_generate_audio": True,  # QUIRK: uses generate_audio bool, not sound
        "image_param": "first_frame_url",  # QUIRK: singular URL string for i2v
        "max_images": 1,
        "default_params": {"web_search": False},  # required field per API docs
        "pricing": {
            # Per-second, no-video-input tier (i2v with first_frame_url)
            "1080p_per_sec": 0.51, "720p_per_sec": 0.125, "480p_per_sec": 0.057,
        },
        "description": "ByteDance flagship video model — native audio, 4-15s, up to 1080p",
    },

    "seedance-2-fast": {
        "display_name": "Seedance 2.0 Fast",
        "provider": "ByteDance",
        "type": "video",
        "modes": ["t2v", "i2v"],
        "model_id": "bytedance/seedance-2-fast",
        "durations": ["5", "8", "10", "15"],
        "resolutions": ["480p", "720p"],
        "aspect_ratios": ["1:1", "4:3", "3:4", "16:9", "9:16", "21:9", "adaptive"],
        "supports_audio": True,
        "uses_generate_audio": True,
        "image_param": "first_frame_url",  # QUIRK: singular URL string for i2v
        "max_images": 1,
        "default_params": {"web_search": False},
        "pricing": {
            "720p_per_sec": 0.165, "480p_per_sec": 0.0775,
        },
        "description": "Faster ByteDance video model — audio, 4-15s, up to 720p",
    },

    "topaz-video-upscale": {
        "display_name": "Topaz Video Upscaler",
        "provider": "Topaz",
        "type": "video",
        "modes": ["upscale"],
        "model_id": "topaz/video-upscale",
        "upscale_factors": ["1", "2", "4"],
        "supports_audio": False,
        "image_param": None,
        "pricing": {"per_sec": 0.06},
        "description": "Upscale existing videos 1x/2x/4x — $0.06/sec",
    },

    # ══════════════ IMAGE MODELS ══════════════

    "nano-banana-2": {
        "display_name": "Nano Banana 2",
        "provider": "Google",
        "type": "image",
        "modes": ["t2i"],
        "model_id": "nano-banana-2",
        "resolutions": ["1K", "2K", "4K"],
        "aspect_ratios": ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"],
        "output_formats": ["png", "jpg"],
        "supports_ref_images": True,
        "image_param": "image_input",  # QUIRK: uses image_input
        "max_images": 14,
        "pricing": {"1K": 0.04, "2K": 0.06, "4K": 0.09},
        "description": "Google's image model with text rendering and subject consistency",
    },

    "nano-banana-pro": {
        "display_name": "Nano Banana Pro",
        "provider": "Google",
        "type": "image",
        "modes": ["t2i", "i2i"],
        "model_id": "nano-banana-pro",
        "resolutions": ["1K", "2K", "4K"],
        "aspect_ratios": ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"],
        "output_formats": ["png", "jpg"],
        "image_param": "image_input",  # QUIRK: uses image_input
        "max_images": 8,
        "pricing": {"1K": 0.09, "2K": 0.09, "4K": 0.12},
        "description": "Premium Google image model with inpainting and multilingual text",
    },

    "seedream-5-lite-t2i": {
        "display_name": "Seedream 5.0 Lite",
        "provider": "ByteDance",
        "type": "image",
        "modes": ["t2i"],
        "model_id": "seedream/5-lite-text-to-image",
        "resolutions": ["basic", "high"],  # Uses quality param, not resolution
        "aspect_ratios": ["1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2", "21:9"],
        "uses_quality_param": True,  # QUIRK: quality instead of resolution
        "image_param": None,
        "pricing": {"basic": 0.028, "high": 0.028},
        "description": "Fast and affordable text-to-image with up to 3K output",
    },

    "seedream-5-lite-i2i": {
        "display_name": "Seedream 5.0 Lite (Edit)",
        "provider": "ByteDance",
        "type": "image",
        "modes": ["i2i"],
        "model_id": "seedream/5-lite-image-to-image",
        "resolutions": ["basic", "high"],
        "aspect_ratios": ["1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2", "21:9"],
        "uses_quality_param": True,  # QUIRK
        "image_param": "image_urls",
        "max_images": 14,
        "pricing": {"basic": 0.028, "high": 0.028},
        "description": "Image-to-image editing with Seedream 5.0 Lite",
    },

    "flux-2-pro-t2i": {
        "display_name": "Flux 2 Pro",
        "provider": "Black Forest Labs",
        "type": "image",
        "modes": ["t2i"],
        "model_id": "flux-2/pro-text-to-image",
        "resolutions": ["1K", "2K"],
        "aspect_ratios": ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3"],
        "image_param": None,
        "pricing": {"1K": 0.025, "2K": 0.035},
        "description": "Photorealistic text-to-image with character consistency",
    },

    "flux-2-pro-i2i": {
        "display_name": "Flux 2 Pro (Edit)",
        "provider": "Black Forest Labs",
        "type": "image",
        "modes": ["i2i"],
        "model_id": "flux-2/pro-image-to-image",
        "resolutions": ["1K", "2K"],
        "aspect_ratios": ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "auto"],
        "image_param": "input_urls",  # QUIRK: uses input_urls
        "max_images": 8,
        "pricing": {"1K": 0.025, "2K": 0.035},
        "description": "Multi-reference image-to-image transformation",
    },

    "grok-imagine-t2i": {
        "display_name": "Grok Imagine",
        "provider": "xAI",
        "type": "image",
        "modes": ["t2i"],
        "model_id": "grok-imagine/text-to-image",
        "resolutions": ["default"],
        "aspect_ratios": ["2:3", "3:2", "1:1", "16:9", "9:16"],
        "image_param": None,
        "pricing": {"default": 0.02},
        "description": "Fast text-to-image (returns 6 images per request)",
        "batch_count": 6,
    },

    "grok-imagine-i2i": {
        "display_name": "Grok Imagine (Edit)",
        "provider": "xAI",
        "type": "image",
        "modes": ["i2i"],
        "model_id": "grok-imagine/image-to-image",
        "resolutions": ["default"],
        "aspect_ratios": ["2:3", "3:2", "1:1", "16:9", "9:16"],
        "image_param": "image_urls",
        "max_images": 1,
        "pricing": {"default": 0.02},
        "description": "Image-to-image editing (returns 2 images per request)",
        "batch_count": 2,
    },

    # ══════════════ MIDJOURNEY MODELS ══════════════

    "midjourney-t2i": {
        "display_name": "Midjourney",
        "provider": "Midjourney",
        "type": "image",
        "modes": ["t2i"],
        "model_id": "custom_midjourney",
        "is_midjourney": True,
        "task_type": "mj_txt2img",
        "aspect_ratios": ["1:1", "16:9", "9:16", "2:3", "3:2", "3:4", "4:3", "5:6", "6:5", "2:1", "1:2"],
        "mj_speeds": ["relaxed", "fast", "turbo"],
        "mj_versions": ["7", "6.1", "6", "5.2", "5.1", "niji7", "niji6"],
        "mj_stylization": [0, 1000],
        "mj_weirdness": [0, 3000],
        "mj_variety": [0, 100],
        "image_param": None,
        "batch_count": 4,
        "pricing": {"relaxed": 0.015, "fast": 0.04, "turbo": 0.08},
        "description": "Iconic AI art generator — unmatched style, 4 images per request",
    },

    "midjourney-i2i": {
        "display_name": "Midjourney (Edit)",
        "provider": "Midjourney",
        "type": "image",
        "modes": ["i2i"],
        "model_id": "custom_midjourney",
        "is_midjourney": True,
        "task_type": "mj_img2img",
        "aspect_ratios": ["1:1", "16:9", "9:16", "2:3", "3:2", "3:4", "4:3", "5:6", "6:5", "2:1", "1:2"],
        "mj_speeds": ["relaxed", "fast", "turbo"],
        "mj_versions": ["7", "6.1", "6", "5.2", "5.1", "niji7", "niji6"],
        "mj_stylization": [0, 1000],
        "mj_weirdness": [0, 3000],
        "mj_variety": [0, 100],
        "image_param": "fileUrl",
        "max_images": 1,
        "batch_count": 4,
        "pricing": {"relaxed": 0.015, "fast": 0.04, "turbo": 0.08},
        "description": "Transform images with Midjourney's artistic style engine",
    },

    "midjourney-video": {
        "display_name": "Midjourney Video",
        "provider": "Midjourney",
        "type": "video",
        "modes": ["i2v"],
        "model_id": "custom_midjourney",
        "is_midjourney": True,
        "task_type": "mj_video",
        "aspect_ratios": ["1:1", "16:9", "9:16", "2:3", "3:2", "3:4", "4:3"],
        "mj_speeds": ["relaxed", "fast", "turbo"],
        "image_param": "fileUrl",
        "max_images": 1,
        "pricing": {"relaxed": 0.10, "fast": 0.20, "turbo": 0.35},
        "description": "Animate images into 5-second video clips with Midjourney",
    },
}


# ────────────────────────────────────────────────────────────────
#  HTTP HELPER
# ────────────────────────────────────────────────────────────────

def _kie_request(method, url, api_key, json_data=None, timeout=60):
    """Make an authenticated request to Kie.ai with retry on 429."""
    headers = {
        **_BROWSER_HEADERS,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    body = json.dumps(json_data).encode("utf-8") if json_data else None

    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                return resp_data
        except urllib.error.HTTPError as e:
            status = e.code
            error_body = ""
            try:
                error_body = e.read().decode("utf-8")
            except Exception:
                pass

            if status == 429 and attempt < MAX_RETRIES - 1:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(f"[Kie] Rate limited (429), retrying in {delay}s (attempt {attempt + 1})")
                time.sleep(delay)
                continue
            elif status == 401:
                raise ValueError("Invalid or expired Kie.ai API key")
            elif status == 402:
                raise ValueError("Insufficient Kie.ai credits")
            else:
                logger.error(f"[Kie] HTTP {status}: {error_body}")
                raise ValueError(f"Kie.ai API error ({status}): {error_body[:200]}")
        except urllib.error.URLError as e:
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(f"[Kie] Connection error, retrying in {delay}s: {e}")
                time.sleep(delay)
                continue
            raise ValueError(f"Failed to connect to Kie.ai: {e}")

    raise ValueError("Kie.ai request failed after max retries")


# ────────────────────────────────────────────────────────────────
#  PAYLOAD BUILDER (handles per-model quirks)
# ────────────────────────────────────────────────────────────────

def _build_task_payload(model_key, prompt, image_urls=None, **params):
    """Build the createTask payload, normalizing per-model parameter quirks."""
    if model_key not in KIE_MODELS:
        raise ValueError(f"Unknown model: {model_key}")

    config = KIE_MODELS[model_key]

    # ── Midjourney: completely different payload structure ──
    if config.get("is_midjourney"):
        return _build_mj_payload(config, prompt, image_urls, **params)

    # ── Topaz upscale: completely different payload (video-in, no prompt) ──
    if "upscale" in config.get("modes", []):
        video_url = params.get("video_url", "")
        upscale_factor = str(params.get("upscale_factor", "2"))
        return {
            "model": config["model_id"],
            "input": {"video_url": video_url, "upscale_factor": upscale_factor},
        }

    input_data = {}

    # Seed model default params (e.g. web_search required by seedance)
    for k, v in config.get("default_params", {}).items():
        input_data[k] = v

    # Prompt
    if prompt:
        input_data["prompt"] = prompt

    # ── Image parameter normalization ──
    if image_urls:
        param_name = config.get("image_param")
        if param_name == "image_url":
            # Hailuo: singular string
            input_data["image_url"] = image_urls[0] if isinstance(image_urls, list) else image_urls
        elif param_name == "first_frame_url":
            # Seedance: first_frame_url singular string for i2v
            input_data["first_frame_url"] = image_urls[0] if isinstance(image_urls, list) else image_urls
        elif param_name == "image_input":
            # Nano Banana: image_input (array)
            input_data["image_input"] = image_urls if isinstance(image_urls, list) else [image_urls]
        elif param_name == "input_urls":
            # Flux I2I: input_urls (array)
            input_data["input_urls"] = image_urls if isinstance(image_urls, list) else [image_urls]
        elif param_name == "image_urls":
            # Default: image_urls (array)
            input_data["image_urls"] = image_urls if isinstance(image_urls, list) else [image_urls]

    # ── Duration / n_frames normalization ──
    duration = params.get("duration")
    if duration:
        if config.get("uses_n_frames"):
            # Sora 2: convert duration to n_frames string
            input_data["n_frames"] = str(duration)
        else:
            input_data["duration"] = str(duration)

    # ── Resolution / Quality normalization ──
    resolution = params.get("resolution")
    if resolution:
        if config.get("uses_quality_param"):
            # Seedream: quality instead of resolution
            input_data["quality"] = resolution
        else:
            input_data["resolution"] = resolution

    # ── Aspect ratio ──
    aspect_ratio = params.get("aspect_ratio")
    if aspect_ratio:
        input_data["aspect_ratio"] = aspect_ratio

    # ── Seedance last_frame_url (first+last frame mode) ──
    last_frame_url = params.get("last_frame_url")
    if last_frame_url:
        input_data["last_frame_url"] = last_frame_url

    # ── Seedance multimodal reference arrays ──
    ref_image_urls = params.get("ref_image_urls") or []
    if ref_image_urls:
        input_data["reference_image_urls"] = ref_image_urls[:9]

    ref_video_urls = params.get("ref_video_urls") or []
    if ref_video_urls:
        input_data["reference_video_urls"] = ref_video_urls[:3]

    ref_audio_urls = params.get("ref_audio_urls") or []
    if ref_audio_urls:
        input_data["reference_audio_urls"] = ref_audio_urls[:3]

    # ── Audio (video models) ──
    if config.get("uses_generate_audio"):
        # Seedance: generate_audio boolean (default true per API, adds cost)
        input_data["generate_audio"] = bool(params.get("audio", True))
    elif "audio" in params and config.get("supports_audio"):
        input_data["sound"] = params["audio"]

    # ── Output format (image models) ──
    output_format = params.get("output_format")
    if output_format:
        input_data["output_format"] = output_format

    # ── Hailuo constraint: no 10s at 1080P ──
    if config.get("constraints", {}).get("no_10s_1080p"):
        if input_data.get("duration") == "10" and input_data.get("resolution") == "1080P":
            raise ValueError("Hailuo 2.3: 10-second videos at 1080P are not supported. Use 768P for 10s or 1080P for 6s.")

    payload = {
        "model": config["model_id"],
        "input": input_data,
    }

    return payload


def _build_mj_payload(config, prompt, image_urls=None, **params):
    """Build Midjourney-specific payload. MJ uses flat structure (no model/input wrapper)."""
    payload = {
        "taskType": config["task_type"],
    }

    if prompt:
        payload["prompt"] = prompt

    # Image URLs for I2I / Video (use fileUrls array per docs)
    if image_urls:
        urls = image_urls if isinstance(image_urls, list) else [image_urls]
        payload["fileUrls"] = urls

    # Speed mode (not used for mj_video or mj_omni_reference per docs)
    speed = params.get("speed", "fast")
    if config["task_type"] not in ("mj_video", "mj_omni_reference"):
        payload["speed"] = speed

    # Aspect ratio (camelCase for MJ API)
    aspect_ratio = params.get("aspect_ratio")
    if aspect_ratio:
        payload["aspectRatio"] = aspect_ratio

    # Version (only for image models, not video)
    version = params.get("version")
    if version and config["task_type"] != "mj_video":
        payload["version"] = str(version)

    # Stylization (0-1000)
    stylization = params.get("stylization")
    if stylization is not None and config.get("mj_stylization"):
        payload["stylization"] = int(stylization)

    # Weirdness (0-3000)
    weirdness = params.get("weirdness")
    if weirdness is not None and config.get("mj_weirdness"):
        payload["weirdness"] = int(weirdness)

    # Variety (0-100)
    variety = params.get("variety")
    if variety is not None and config.get("mj_variety"):
        payload["variety"] = int(variety)

    return payload


# ────────────────────────────────────────────────────────────────
#  PUBLIC API FUNCTIONS
# ────────────────────────────────────────────────────────────────

def check_credits(api_key):
    """Get the user's remaining Kie.ai credit balance."""
    try:
        resp = _kie_request("GET", f"{KIE_BASE_URL}/chat/credit", api_key)
        if resp.get("code") == 200:
            data = resp.get("data", {})
            return {"credits": data.get("credits", 0), "success": True}
        return {"credits": 0, "success": False, "error": resp.get("msg", "Unknown error")}
    except Exception as e:
        return {"credits": 0, "success": False, "error": str(e)}


def upload_image_url(image_url, api_key, upload_path="images/user-uploads"):
    """Upload a file URL to Kie.ai CDN so it can be used in generation tasks.

    Works for images, audio, and video — pass upload_path accordingly:
      images/user-uploads, audios/user-uploads, videos/user-uploads
    Returns: {'url': str} — the Kie-hosted URL to use in subsequent calls.
    """
    try:
        resp = _kie_request("POST", KIE_FILE_UPLOAD_URL, api_key, json_data={
            "fileUrl": image_url,
            "uploadPath": upload_path,
        })
        logger.info(f"[Kie] Upload response: success={resp.get('success')}, code={resp.get('code')}")
        if resp.get("code") == 200 or resp.get("success"):
            data = resp.get("data", {})
            # Docs: response has fileUrl (direct) and downloadUrl
            result_url = data.get("downloadUrl") or data.get("fileUrl") or data.get("url", "")
            if result_url:
                return {"url": result_url, "success": True}
        return {"url": None, "success": False, "error": resp.get("msg", "Upload failed")}
    except Exception as e:
        return {"url": None, "success": False, "error": str(e)}


def create_task(model_key, prompt, api_key, image_urls=None, **params):
    """Create a generation task on Kie.ai.

    Args:
        model_key: Key from KIE_MODELS registry (e.g., 'kling-3.0', 'nano-banana-2')
        prompt: Text prompt for generation
        api_key: User's Kie.ai API key
        image_urls: Optional list of image URLs for I2V/I2I
        **params: Model-specific params (duration, resolution, aspect_ratio, audio, etc.)

    Returns: {'taskId': str, 'success': True} or {'error': str, 'success': False}
    """
    try:
        payload = _build_task_payload(model_key, prompt, image_urls=image_urls, **params)
        resp = _kie_request("POST", f"{KIE_BASE_URL}/jobs/createTask", api_key, json_data=payload)

        if resp.get("code") == 200:
            task_id = resp.get("data", {}).get("taskId", "")
            return {"taskId": task_id, "success": True}
        return {"taskId": None, "success": False, "error": resp.get("msg", "Task creation failed")}
    except ValueError as e:
        return {"taskId": None, "success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"[Kie] create_task error: {e}")
        return {"taskId": None, "success": False, "error": str(e)}


def poll_task(task_id, api_key):
    """Poll a task for completion status.

    Returns: {
        'status': 'processing' | 'completed' | 'failed',
        'progress': int | None (0-100, only for Sora 2),
        'result_urls': [str] | None,
        'error': str | None
    }
    """
    try:
        url = f"{KIE_BASE_URL}/jobs/recordInfo?taskId={urllib.parse.quote(task_id)}"
        resp = _kie_request("GET", url, api_key)

        if resp.get("code") != 200:
            return {"status": "failed", "error": resp.get("msg", "Poll failed")}

        data = resp.get("data", {})
        state = data.get("state", "")
        progress = data.get("progress")

        # Map API states to simplified states
        if state in ("waiting", "queuing", "generating"):
            return {
                "status": "processing",
                "progress": progress,
                "result_urls": None,
            }
        elif state == "success":
            # Parse resultJson to extract URLs — different models use different keys
            result_json_str = data.get("resultJson", "{}")
            try:
                result_data = json.loads(result_json_str) if isinstance(result_json_str, str) else (result_json_str or {})
            except (json.JSONDecodeError, TypeError):
                result_data = {}

            logger.info(f"[Kie] Task {task_id} success. resultJson keys: {list(result_data.keys()) if isinstance(result_data, dict) else type(result_data)}")

            # Try multiple known result keys (models vary)
            result_urls = []
            if isinstance(result_data, dict):
                # Array formats
                result_urls = (result_data.get("resultUrls")
                    or result_data.get("result_urls")
                    or result_data.get("images")
                    or result_data.get("videos")
                    or result_data.get("outputs")
                    or result_data.get("output")
                    or [])
                # Singular string format
                if not result_urls:
                    single = (result_data.get("resultUrl")
                        or result_data.get("result_url")
                        or result_data.get("image")
                        or result_data.get("video")
                        or result_data.get("url")
                        or "")
                    if single:
                        result_urls = [single]
                # Ensure it's always a list
                if isinstance(result_urls, str):
                    result_urls = [result_urls]
            elif isinstance(result_data, list):
                result_urls = result_data

            # Fallback: check data-level fields if resultJson had nothing
            if not result_urls:
                direct_url = data.get("resultUrl") or data.get("result_url") or ""
                if direct_url:
                    result_urls = [direct_url]

            if not result_urls:
                logger.warning(f"[Kie] Task {task_id} completed but no result URLs found. Full data keys: {list(data.keys())}, resultJson: {result_json_str[:500]}")

            return {
                "status": "completed",
                "progress": 100,
                "result_urls": result_urls,
            }
        elif state == "fail":
            return {
                "status": "failed",
                "progress": None,
                "result_urls": None,
                "error": data.get("failReason", "Generation failed"),
            }
        else:
            return {"status": "processing", "progress": progress, "result_urls": None}

    except Exception as e:
        logger.error(f"[Kie] poll_task error: {e}")
        return {"status": "failed", "error": str(e)}


def mj_create_task(model_key, prompt, api_key, image_urls=None, **params):
    """Create a Midjourney generation task using the dedicated /mj/ endpoint.

    MJ uses POST /api/v1/mj/generate with a flat payload (no model/input wrapper).
    Returns: {'taskId': str, 'success': True} or {'error': str, 'success': False}
    """
    try:
        payload = _build_mj_payload(KIE_MODELS[model_key], prompt, image_urls, **params)
        resp = _kie_request("POST", f"{KIE_BASE_URL}/mj/generate", api_key, json_data=payload)

        if resp.get("code") == 200:
            task_id = resp.get("data", {}).get("taskId", "")
            return {"taskId": task_id, "success": True}
        return {"taskId": None, "success": False, "error": resp.get("msg", "MJ task creation failed")}
    except ValueError as e:
        return {"taskId": None, "success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"[Kie/MJ] mj_create_task error: {e}")
        return {"taskId": None, "success": False, "error": str(e)}


def mj_poll_task(task_id, api_key):
    """Poll a Midjourney task using the dedicated /mj/ endpoint.

    MJ uses GET /api/v1/mj/record-info?taskId=...
    Response format differs from standard:
      - successFlag: 0 = generating, 1 = success, 2 = failed, 3 = generation failed
      - resultInfoJson.resultUrls[].resultUrl for completed URLs
    """
    try:
        url = f"{KIE_BASE_URL}/mj/record-info?taskId={urllib.parse.quote(task_id)}"
        resp = _kie_request("GET", url, api_key)

        if resp.get("code") != 200:
            return {"status": "failed", "error": resp.get("msg", "MJ poll failed")}

        data = resp.get("data", {})
        flag = data.get("successFlag")

        if flag == 0:
            # Still generating
            return {"status": "processing", "progress": None, "result_urls": None}
        elif flag == 1:
            # Success — extract URLs from resultInfoJson.resultUrls[].resultUrl
            result_info = data.get("resultInfoJson", {})
            if isinstance(result_info, str):
                try:
                    result_info = json.loads(result_info)
                except (json.JSONDecodeError, TypeError):
                    result_info = {}

            result_urls = []
            raw_urls = result_info.get("resultUrls", [])
            for item in raw_urls:
                if isinstance(item, dict):
                    url_val = item.get("resultUrl", "")
                    if url_val:
                        result_urls.append(url_val)
                elif isinstance(item, str):
                    result_urls.append(item)

            if not result_urls:
                logger.warning(f"[Kie/MJ] Task {task_id} success but no URLs. resultInfoJson: {result_info}")

            return {"status": "completed", "progress": 100, "result_urls": result_urls}
        elif flag in (2, 3):
            fail_reason = data.get("failReason", "") or data.get("resultInfoJson", {})
            if isinstance(fail_reason, dict):
                fail_reason = fail_reason.get("failReason", "Generation failed")
            return {"status": "failed", "progress": None, "result_urls": None, "error": str(fail_reason) or "MJ generation failed"}
        else:
            # Unknown flag, treat as processing
            return {"status": "processing", "progress": None, "result_urls": None}

    except Exception as e:
        logger.error(f"[Kie/MJ] mj_poll_task error: {e}")
        return {"status": "failed", "error": str(e)}


def mj_upscale(task_id, image_index, api_key):
    """Upscale one of the 4 MJ images. imageIndex: 0-3."""
    try:
        payload = {"taskId": task_id, "imageIndex": int(image_index)}
        resp = _kie_request("POST", f"{KIE_BASE_URL}/mj/generateUpscale", api_key, json_data=payload)
        if resp.get("code") == 200:
            new_task_id = resp.get("data", {}).get("taskId", "")
            return {"taskId": new_task_id, "success": True}
        return {"taskId": None, "success": False, "error": resp.get("msg", "Upscale failed")}
    except Exception as e:
        logger.error(f"[Kie/MJ] mj_upscale error: {e}")
        return {"taskId": None, "success": False, "error": str(e)}


def mj_vary(task_id, image_index, api_key):
    """Create variations of one of the 4 MJ images. imageIndex: 1-4."""
    try:
        payload = {"taskId": task_id, "imageIndex": int(image_index)}
        resp = _kie_request("POST", f"{KIE_BASE_URL}/mj/generateVary", api_key, json_data=payload)
        if resp.get("code") == 200:
            new_task_id = resp.get("data", {}).get("taskId", "")
            return {"taskId": new_task_id, "success": True}
        return {"taskId": None, "success": False, "error": resp.get("msg", "Vary failed")}
    except Exception as e:
        logger.error(f"[Kie/MJ] mj_vary error: {e}")
        return {"taskId": None, "success": False, "error": str(e)}


def get_models_info():
    """Return the model registry for frontend display. No API call needed."""
    result = {}
    for key, config in KIE_MODELS.items():
        info = {
            "display_name": config["display_name"],
            "provider": config["provider"],
            "type": config["type"],
            "modes": config["modes"],
            "durations": config.get("durations"),
            "resolutions": config.get("resolutions", []),
            "aspect_ratios": config.get("aspect_ratios", []),
            "supports_audio": config.get("supports_audio", False),
            "has_progress": config.get("has_progress", False),
            "pricing": config.get("pricing", {}),
            "description": config.get("description", ""),
            "batch_count": config.get("batch_count"),
            "max_images": config.get("max_images"),
            "supports_ref_images": config.get("supports_ref_images", False),
            "output_formats": config.get("output_formats"),
            "constraints": config.get("constraints"),
        }
        # Midjourney-specific fields
        if config.get("is_midjourney"):
            info["is_midjourney"] = True
            info["mj_speeds"] = config.get("mj_speeds", [])
            info["mj_versions"] = config.get("mj_versions", [])
            info["mj_stylization"] = config.get("mj_stylization")
            info["mj_weirdness"] = config.get("mj_weirdness")
            info["mj_variety"] = config.get("mj_variety")
        result[key] = info
    return result


def download_result(result_url, task_id):
    """Download a Kie.ai result to a local temp file.

    Kie.ai URLs expire in 24 hours, so we download immediately.
    Returns: local file path or None on failure.
    """
    try:
        # Determine extension from URL
        parsed = urllib.parse.urlparse(result_url)
        path = parsed.path.lower()
        if path.endswith(".mp4") or "video" in path:
            ext = ".mp4"
        elif path.endswith(".png"):
            ext = ".png"
        elif path.endswith(".webp"):
            ext = ".webp"
        else:
            ext = ".jpg"

        tmp_dir = tempfile.mkdtemp()
        tmp_path = os.path.join(tmp_dir, f"kie_{task_id}{ext}")

        req = urllib.request.Request(result_url, headers=_BROWSER_HEADERS)
        with urllib.request.urlopen(req, timeout=120) as resp:
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)

        return tmp_path
    except Exception as e:
        logger.error(f"[Kie] Failed to download result for task {task_id}: {e}")
        return None
