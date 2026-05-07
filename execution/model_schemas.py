"""Studio model registry — single source of truth for the unified Studio UI.

Each entry describes ONE generative model:
  - id            : exact string sent to its API
  - display_name  : user-facing label
  - provider      : grouping label for the UI ("Google", "Kling", …)
  - backend       : routing key for /api/studio/generate to know which API to call
  - kind          : modality enum (see KIND_* constants)
  - inputs[]      : required/optional content slots (text/image/video/audio)
  - params[]      : every tunable parameter with type, range, default
  - output        : what comes back ({kind, count_max, format})
  - cost          : free-form credits/pricing string + optional per-unit calc hints
  - notes[]       : human-readable quirks / constraints

This file is exposed to the frontend via `GET /api/studio/models` (defined in
server.py). The frontend renders a dynamic form from `inputs + params`, then
POSTs the user-filled values to `/api/studio/generate` which routes by
`backend` to the correct underlying API.

Sources: docs/research_google_ai_media_models_2026_05_05.md
         docs/research_kie_models_2026_05_05.md
"""

# ─────────────────────────────────────────────────────────────────────────────
# Modality kinds — used by the UI to pick the right "Image / Video / Music /
# Voice" tab and decide which preview to render.
# ─────────────────────────────────────────────────────────────────────────────
KIND_T2I            = "text_to_image"
KIND_IMAGE_EDIT     = "image_edit"
KIND_IMAGE_COMPOSE  = "image_compose"
KIND_IMAGE_UPSCALE  = "image_upscale"
KIND_IMAGE_BGREMOVE = "background_remove"
KIND_T2V            = "text_to_video"
KIND_I2V            = "image_to_video"
KIND_FRAMES_TO_VIDEO = "frames_to_video"
KIND_REF_TO_VIDEO   = "reference_to_video"
KIND_V2V            = "video_to_video"
KIND_VIDEO_EXTEND   = "video_extend"
KIND_VIDEO_UPSCALE  = "video_upscale"
KIND_VIDEO_ANIMATE  = "video_animate"
KIND_LIPSYNC        = "lipsync"
KIND_T2M            = "text_to_music"
KIND_LYRICS_TO_SONG = "lyrics_to_song"
KIND_SOUND_EFFECT   = "sound_effect"
KIND_TTS            = "text_to_speech"
KIND_TTS_DIALOGUE   = "multi_speaker_tts"
KIND_STT            = "speech_to_text"
KIND_AUDIO_ISOLATE  = "audio_isolate"
KIND_CHARACTER_REF  = "character_extract"
KIND_WATERMARK_RM   = "watermark_remove"


# ─────────────────────────────────────────────────────────────────────────────
# Param type primitives — drive form widget choice in the frontend.
# ─────────────────────────────────────────────────────────────────────────────
T_TEXT      = "text"          # textarea
T_LINE      = "line"          # single-line text input
T_INT       = "int"           # number input (integer)
T_FLOAT     = "float"         # number input (decimal)
T_SLIDER    = "slider"        # range slider (use for 0-1 or 0-N continuous params)
T_BOOL      = "bool"          # toggle / checkbox
T_ENUM      = "enum"          # select (or segmented if ≤4 options)
T_SEED      = "seed"          # int + "randomize" button
T_IMAGE     = "image"         # single image upload (URL or file)
T_IMAGE_N   = "image_list"    # multi-image upload (min/max count)
T_VIDEO     = "video"         # single video upload
T_AUDIO     = "audio"         # single audio upload
T_AUDIO_N   = "audio_list"    # multi-audio upload
T_VIDEO_N   = "video_list"    # multi-video upload
T_TASK_REF  = "task_ref"      # picker that lists prior tasks (for ops that consume taskId)
T_CHAR_REF  = "character_ref" # picker for Sora 2 character_ids


# ─────────────────────────────────────────────────────────────────────────────
# Backend routing keys — `/api/studio/generate` switches on this.
# ─────────────────────────────────────────────────────────────────────────────
B_GOOGLE_GEMINI_IMAGE = "google_gemini_image"   # client.models.generate_content w/ image modality
B_GOOGLE_IMAGEN       = "google_imagen"          # client.models.generate_images
B_GOOGLE_VEO          = "google_veo"             # client.models.generate_videos (long-running)
B_GOOGLE_TTS          = "google_tts"             # generate_content w/ SpeechConfig
B_GOOGLE_LYRIA        = "google_lyria"           # generate_content w/ Lyria models
B_KIE_GENERIC         = "kie_generic"            # /api/v1/jobs/createTask + poll
B_KIE_VEO             = "kie_veo3"               # veo3-api/* (Kie's Veo wrapper)
B_KIE_RUNWAY          = "kie_runway"             # runway-api/*
B_KIE_MIDJOURNEY      = "kie_midjourney"         # /mj/* legacy endpoints


# ─────────────────────────────────────────────────────────────────────────────
# Helpers for compact entry construction
# ─────────────────────────────────────────────────────────────────────────────
def _enum(name, options, default=None, label=None, help=None, unit=None):
    return {"name": name, "type": T_ENUM, "options": options,
            "default": default if default is not None else options[0],
            "label": label or name.replace("_", " ").title(),
            "help": help, "unit": unit}

def _int(name, mn, mx, default, step=1, label=None, help=None, unit=None):
    return {"name": name, "type": T_INT, "min": mn, "max": mx, "default": default,
            "step": step, "label": label or name.replace("_", " ").title(),
            "help": help, "unit": unit}

def _float(name, mn, mx, default, step=0.01, label=None, help=None):
    return {"name": name, "type": T_FLOAT, "min": mn, "max": mx, "default": default,
            "step": step, "label": label or name.replace("_", " ").title(), "help": help}

def _slider(name, mn, mx, default, step=0.01, label=None, help=None):
    return {"name": name, "type": T_SLIDER, "min": mn, "max": mx, "default": default,
            "step": step, "label": label or name.replace("_", " ").title(), "help": help}

def _bool(name, default=False, label=None, help=None):
    return {"name": name, "type": T_BOOL, "default": default,
            "label": label or name.replace("_", " ").title(), "help": help}

def _seed(name="seed", label="Seed", help="Same seed → same result. Leave blank for random."):
    return {"name": name, "type": T_SEED, "default": None, "label": label, "help": help}

def _text(name, required=False, max_chars=None, label=None, placeholder=None, help=None):
    return {"name": name, "type": T_TEXT, "required": required, "max_chars": max_chars,
            "label": label or name.replace("_", " ").title(),
            "placeholder": placeholder, "help": help}

def _line(name, required=False, max_chars=None, label=None, placeholder=None, help=None):
    return {"name": name, "type": T_LINE, "required": required, "max_chars": max_chars,
            "label": label or name.replace("_", " ").title(),
            "placeholder": placeholder, "help": help}

def _image(name, required=False, label=None, formats=None, max_mb=None, help=None):
    return {"name": name, "type": T_IMAGE, "required": required,
            "label": label or name.replace("_", " ").title(),
            "formats": formats or ["jpeg", "png", "webp"],
            "max_mb": max_mb, "help": help}

def _images(name, min_n=0, max_n=4, required=False, label=None, formats=None,
            max_mb=None, help=None):
    return {"name": name, "type": T_IMAGE_N, "min_count": min_n, "max_count": max_n,
            "required": required,
            "label": label or name.replace("_", " ").title(),
            "formats": formats or ["jpeg", "png", "webp"],
            "max_mb": max_mb, "help": help}

def _audio(name, required=False, label=None, formats=None, max_mb=None, help=None):
    return {"name": name, "type": T_AUDIO, "required": required,
            "label": label or name.replace("_", " ").title(),
            "formats": formats or ["mp3", "wav"], "max_mb": max_mb, "help": help}

def _video(name, required=False, label=None, formats=None, max_mb=None, help=None):
    return {"name": name, "type": T_VIDEO, "required": required,
            "label": label or name.replace("_", " ").title(),
            "formats": formats or ["mp4", "mov"], "max_mb": max_mb, "help": help}


# ═════════════════════════════════════════════════════════════════════════════
# REGISTRY
# ═════════════════════════════════════════════════════════════════════════════
MODEL_SCHEMAS = {}


def _register(entry):
    MODEL_SCHEMAS[entry["id"]] = entry
    return entry


# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE — Gemini-native image models (Nano Banana family)
# Backend: B_GOOGLE_GEMINI_IMAGE → client.models.generate_content
# ─────────────────────────────────────────────────────────────────────────────
_register({
    "id": "gemini-2.5-flash-image",
    "display_name": "Nano Banana",
    "provider": "Google",
    "backend": B_GOOGLE_GEMINI_IMAGE,
    "kind": KIND_T2I,
    "kinds_supported": [KIND_T2I, KIND_IMAGE_EDIT],
    "inputs": [
        _text("prompt", required=True, max_chars=10000,
              placeholder="Describe the image you want…"),
        _images("reference_images", min_n=0, max_n=3, max_mb=20,
                help="Up to 3 reference images. Optimal is ≤3."),
    ],
    "params": [
        _enum("aspect_ratio", ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4",
                               "9:16", "16:9", "21:9"], default="1:1"),
        _int("num_images", 1, 4, 1, label="Variations"),
    ],
    "output": {"kind": "image", "count_max": 4, "format": "png"},
    "cost": {"per_image_usd": 0.039},
    "notes": ["Stable. Fixed 1024px base (e.g. 1:1=1024x1024, 16:9=1344x768).",
              "Includes SynthID watermark."],
})

_register({
    "id": "gemini-3-pro-image-preview",
    "display_name": "Nano Banana Pro",
    "provider": "Google",
    "backend": B_GOOGLE_GEMINI_IMAGE,
    "kind": KIND_T2I,
    "kinds_supported": [KIND_T2I, KIND_IMAGE_EDIT, KIND_IMAGE_COMPOSE],
    "inputs": [
        _text("prompt", required=True, max_chars=10000),
        _images("reference_images", min_n=0, max_n=6, max_mb=30,
                help="Up to 6 object refs OR 5 character refs."),
    ],
    "params": [
        _enum("aspect_ratio", ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4",
                               "9:16", "16:9", "21:9"], default="1:1"),
        _enum("image_size", ["1K", "2K", "4K"], default="1K", label="Resolution"),
        _int("num_images", 1, 4, 1, label="Variations"),
        _bool("use_google_search", default=False,
              label="Ground in Google Search",
              help="Lets the model reference real-world information."),
    ],
    "output": {"kind": "image", "count_max": 4, "format": "png"},
    "cost": {"per_image_usd_1k": 0.134, "per_image_usd_4k": 0.24},
    "notes": ["Thinking model — may stream interim images.",
              "Excellent text rendering."],
})

_register({
    "id": "gemini-3.1-flash-image-preview",
    "display_name": "Nano Banana 2",
    "provider": "Google",
    "backend": B_GOOGLE_GEMINI_IMAGE,
    "kind": KIND_T2I,
    "kinds_supported": [KIND_T2I, KIND_IMAGE_EDIT, KIND_IMAGE_COMPOSE],
    "inputs": [
        _text("prompt", required=True, max_chars=20000),
        _images("reference_images", min_n=0, max_n=10, max_mb=30,
                help="Up to 10 object refs OR 4 character refs."),
    ],
    "params": [
        _enum("aspect_ratio",
              ["1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5",
               "5:4", "8:1", "9:16", "16:9", "21:9"], default="1:1"),
        _enum("image_size", ["512", "1K", "2K", "4K"], default="1K",
              label="Resolution"),
        _enum("thinking_level", ["minimal", "high"], default="minimal"),
        _int("num_images", 1, 4, 1, label="Variations"),
        _bool("use_google_search", default=False, label="Ground in Google Search"),
    ],
    "output": {"kind": "image", "count_max": 4, "format": "png"},
    "cost": {"per_image_usd_1k": 0.067, "per_image_usd_4k": 0.151},
    "notes": ["Widest aspect-ratio menu of any image model.",
              "Up to 2 interim 'thinking' images may stream."],
})


# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE — Imagen 4 family
# Backend: B_GOOGLE_IMAGEN → client.models.generate_images
# ─────────────────────────────────────────────────────────────────────────────
_imagen_common_params = [
    _enum("aspect_ratio", ["1:1", "3:4", "4:3", "9:16", "16:9"], default="1:1"),
    _enum("image_size", ["1K", "2K"], default="1K", label="Resolution"),
    _enum("person_generation", ["DONT_ALLOW", "ALLOW_ADULT", "ALLOW_ALL"],
          default="ALLOW_ADULT"),
    _enum("safety_filter_level",
          ["BLOCK_LOW_AND_ABOVE", "BLOCK_MEDIUM_AND_ABOVE",
           "BLOCK_ONLY_HIGH", "BLOCK_NONE"],
          default="BLOCK_MEDIUM_AND_ABOVE"),
    _text("negative_prompt", help="What to avoid (may be ignored on Imagen 4)."),
    _seed(),
    _enum("language", ["auto", "en", "ja", "ko", "hi", "zh", "pt", "es"],
          default="auto"),
    _enum("output_mime_type", ["image/png", "image/jpeg"], default="image/png",
          label="Output format"),
    _bool("add_watermark", default=True, label="SynthID watermark"),
    _bool("enhance_prompt", default=False,
          label="Auto-enhance prompt", help="LLM rewrites your prompt first."),
]

_register({
    "id": "imagen-4.0-generate-001",
    "display_name": "Imagen 4",
    "provider": "Google",
    "backend": B_GOOGLE_IMAGEN,
    "kind": KIND_T2I,
    "inputs": [_text("prompt", required=True, max_chars=2000,
                     help="Prompt limit ~480 tokens.")],
    "params": [_int("num_images", 1, 4, 1, label="Variations")] + _imagen_common_params,
    "output": {"kind": "image", "count_max": 4, "format": "png"},
    "cost": {"per_image_usd": 0.04},
})

_register({
    "id": "imagen-4.0-fast-generate-001",
    "display_name": "Imagen 4 Fast",
    "provider": "Google",
    "backend": B_GOOGLE_IMAGEN,
    "kind": KIND_T2I,
    "inputs": [_text("prompt", required=True, max_chars=2000)],
    "params": [_int("num_images", 1, 4, 1, label="Variations")] + _imagen_common_params,
    "output": {"kind": "image", "count_max": 4, "format": "png"},
    "cost": {"per_image_usd": 0.02},
    "notes": ["Lower latency, slightly reduced fidelity."],
})

_register({
    "id": "imagen-4.0-ultra-generate-001",
    "display_name": "Imagen 4 Ultra",
    "provider": "Google",
    "backend": B_GOOGLE_IMAGEN,
    "kind": KIND_T2I,
    "inputs": [_text("prompt", required=True, max_chars=2000)],
    "params": _imagen_common_params,  # num_images locked to 1
    "output": {"kind": "image", "count_max": 1, "format": "png"},
    "cost": {"per_image_usd": 0.06},
    "notes": ["Highest fidelity. num_images locked to 1."],
})


# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE — Veo (video)
# Backend: B_GOOGLE_VEO → client.models.generate_videos (polled)
# ─────────────────────────────────────────────────────────────────────────────
def _veo_entry(model_id, display, resolutions, durations, refs_supported,
               extension_supported, audio_default, pricing_note):
    inputs = [
        _text("prompt", required=True, max_chars=5000),
        _image("first_frame", required=False,
               help="Optional. Animate from this image (image-to-video)."),
        _image("last_frame", required=False,
               help="Optional. With first_frame, interpolate between the two."),
    ]
    if refs_supported:
        inputs.append(_images("reference_images", min_n=0, max_n=3,
                              help="Subject/style consistency refs."))
    if extension_supported:
        inputs.append(_video("source_video", required=False,
                             help="Extend an existing video (720p only)."))
    params = [
        _enum("aspect_ratio", ["16:9", "9:16"], default="16:9"),
        _enum("resolution", resolutions, default=resolutions[0]),
        _enum("duration_seconds", durations, default=str(durations[0]),
              label="Duration", help="1080p/4K require 8 sec."),
        _bool("generate_audio", default=audio_default, label="Generate audio"),
        _text("negative_prompt"),
        _seed(),
        _enum("compression_quality", ["OPTIMIZED", "LOSSLESS"],
              default="OPTIMIZED"),
        _enum("person_generation", ["allow_all", "allow_adult", "dont_allow"],
              default="allow_adult"),
        _bool("enhance_prompt", default=False, label="Auto-enhance prompt"),
        _int("num_videos", 1, 1, 1, label="Variations"),
    ]
    return {
        "id": model_id, "display_name": display, "provider": "Google",
        "backend": B_GOOGLE_VEO,
        "kind": KIND_T2V,
        "kinds_supported": [KIND_T2V, KIND_I2V, KIND_FRAMES_TO_VIDEO]
            + ([KIND_REF_TO_VIDEO] if refs_supported else [])
            + ([KIND_VIDEO_EXTEND] if extension_supported else []),
        "inputs": inputs,
        "params": params,
        "output": {"kind": "video", "count_max": 1, "format": "mp4"},
        "cost": {"note": pricing_note},
        "notes": ["Long-running operation — polled until complete (typ. 11s–6 min).",
                  "24 fps output."],
    }

_register(_veo_entry("veo-3.1-generate-preview", "Veo 3.1",
                     ["720p", "1080p", "4k"], ["4", "6", "8"],
                     refs_supported=True, extension_supported=True,
                     audio_default=True,
                     pricing_note="$0.40/s @ 720p/1080p · $0.60/s @ 4K"))
_register(_veo_entry("veo-3.1-fast-generate-preview", "Veo 3.1 Fast",
                     ["720p", "1080p", "4k"], ["4", "6", "8"],
                     refs_supported=True, extension_supported=True,
                     audio_default=True,
                     pricing_note="$0.10/s @ 720p · $0.12/s @ 1080p · $0.30/s @ 4K"))
_register(_veo_entry("veo-3.1-lite-generate-preview", "Veo 3.1 Lite",
                     ["720p", "1080p"], ["4", "6", "8"],
                     refs_supported=True, extension_supported=False,
                     audio_default=True,
                     pricing_note="$0.05/s @ 720p · $0.08/s @ 1080p"))
_register(_veo_entry("veo-3.0-generate-001", "Veo 3",
                     ["720p", "1080p"], ["4", "6", "8"],
                     refs_supported=False, extension_supported=False,
                     audio_default=True,
                     pricing_note="$0.40/s standard"))
_register(_veo_entry("veo-3.0-fast-generate-001", "Veo 3 Fast",
                     ["720p", "1080p", "4k"], ["4", "6", "8"],
                     refs_supported=False, extension_supported=False,
                     audio_default=True,
                     pricing_note="$0.10/s @ 720p · $0.12/s @ 1080p · $0.30/s @ 4K"))
_register({
    "id": "veo-2.0-generate-001",
    "display_name": "Veo 2 (silent)",
    "provider": "Google",
    "backend": B_GOOGLE_VEO,
    "kind": KIND_T2V,
    "kinds_supported": [KIND_T2V, KIND_I2V],
    "inputs": [
        _text("prompt", required=True, max_chars=5000),
        _image("first_frame", required=False),
    ],
    "params": [
        _enum("aspect_ratio", ["16:9", "9:16"], default="16:9"),
        _enum("duration_seconds", ["5", "6", "8"], default="5"),
        _enum("person_generation", ["allow_all", "allow_adult", "dont_allow"],
              default="allow_adult"),
        _text("negative_prompt"),
        _seed(),
        _int("num_videos", 1, 2, 1, label="Variations"),
    ],
    "output": {"kind": "video", "count_max": 2, "format": "mp4"},
    "cost": {"note": "$0.35/s"},
    "notes": ["Silent only (no audio generation).", "Legacy — prefer Veo 3.x."],
})


# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE — TTS
# Backend: B_GOOGLE_TTS → generate_content + SpeechConfig
# ─────────────────────────────────────────────────────────────────────────────
GOOGLE_TTS_VOICES = [
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
    "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Despina",
    "Erinome", "Algieba", "Rasalgethi", "Laomedeia", "Achernar", "Alnilam",
    "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat", "Algenib",
]

def _google_tts(model_id, display, pricing):
    return {
        "id": model_id, "display_name": display, "provider": "Google",
        "backend": B_GOOGLE_TTS, "kind": KIND_TTS,
        "kinds_supported": [KIND_TTS, KIND_TTS_DIALOGUE],
        "inputs": [_text("prompt", required=True, max_chars=32000,
                         label="Text to speak",
                         help="Inline directions like 'Say cheerfully:' control tone.")],
        "params": [
            _enum("voice", GOOGLE_TTS_VOICES, default="Kore",
                  help="30 prebuilt voices; case-sensitive."),
            _line("language_code",
                  placeholder="auto-detect (e.g. en-US, ja-JP)",
                  help="BCP-47. Leave blank for auto-detect."),
        ],
        "output": {"kind": "audio", "count_max": 1, "format": "wav",
                   "details": "24 kHz mono 16-bit PCM"},
        "cost": {"note": pricing},
        "notes": ["No streaming.", "Multi-speaker (max 2) via dialogue mode.",
                  "Includes SynthID."],
    }

_register(_google_tts("gemini-2.5-flash-preview-tts", "Gemini 2.5 Flash TTS",
                      "$0.50/$10.00 per 1M tokens (in/out)"))
_register(_google_tts("gemini-2.5-pro-preview-tts", "Gemini 2.5 Pro TTS",
                      "$1.00/$20.00 per 1M tokens"))
_register(_google_tts("gemini-3.1-flash-tts-preview", "Gemini 3.1 Flash TTS",
                      "$1.00/$20.00 per 1M tokens"))


# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE — Lyria (music)
# Backend: B_GOOGLE_LYRIA
# ─────────────────────────────────────────────────────────────────────────────
_register({
    "id": "lyria-3-clip-preview",
    "display_name": "Lyria 3 Clip",
    "provider": "Google",
    "backend": B_GOOGLE_LYRIA,
    "kind": KIND_T2M,
    "kinds_supported": [KIND_T2M, KIND_LYRICS_TO_SONG],
    "inputs": [
        _text("prompt", required=True, max_chars=5000,
              help="Use [Verse]/[Chorus]/[Bridge] tags + [M:SS – M:SS] timestamps."),
        _images("mood_references", min_n=0, max_n=10,
                help="Optional mood reference images."),
    ],
    "params": [],
    "output": {"kind": "audio", "count_max": 1, "format": "mp3",
               "details": "30 sec, 44.1 kHz stereo"},
    "cost": {"per_song_usd": 0.04},
})

_register({
    "id": "lyria-3-pro-preview",
    "display_name": "Lyria 3 Pro",
    "provider": "Google",
    "backend": B_GOOGLE_LYRIA,
    "kind": KIND_T2M,
    "kinds_supported": [KIND_T2M, KIND_LYRICS_TO_SONG],
    "inputs": [
        _text("prompt", required=True, max_chars=10000,
              help="Lyrics + structure tags. Up to ~3 min via prompt control."),
        _images("mood_references", min_n=0, max_n=10),
    ],
    "params": [
        _enum("output_format", ["mp3", "wav"], default="mp3"),
    ],
    "output": {"kind": "audio", "count_max": 1, "format": "mp3"},
    "cost": {"per_song_usd": 0.08},
})


# ═════════════════════════════════════════════════════════════════════════════
# KIE — Image generation
# Backend: B_KIE_GENERIC for all unless noted
# ═════════════════════════════════════════════════════════════════════════════

# ─── Seedream family ─────────────────────────────────────────────────────────
_register({
    "id": "bytedance/seedream-v4-text-to-image",
    "display_name": "Seedream V4",
    "provider": "Seedream", "backend": B_KIE_GENERIC, "kind": KIND_T2I,
    "inputs": [_text("prompt", required=True, max_chars=5000)],
    "params": [
        _enum("image_size",
              ["square", "square_hd", "portrait_4_3", "portrait_3_2",
               "portrait_16_9", "landscape_4_3", "landscape_3_2",
               "landscape_16_9", "landscape_21_9"], default="square_hd"),
        _enum("image_resolution", ["1K", "2K", "4K"], default="1K",
              label="Resolution"),
        _int("max_images", 1, 6, 1, label="Variations",
             help="Also state the count in your prompt for best results."),
        _seed(), _bool("nsfw_checker", help="Off = filtering enabled."),
    ],
    "output": {"kind": "image", "count_max": 6, "format": "png"},
    "cost": {"note": "See Kie credits dashboard"},
})

_register({
    "id": "bytedance/seedream-v4-edit",
    "display_name": "Seedream V4 Edit",
    "provider": "Seedream", "backend": B_KIE_GENERIC, "kind": KIND_IMAGE_EDIT,
    "inputs": [
        _text("prompt", required=True, max_chars=5000),
        _images("image_input", min_n=1, max_n=6, required=True),
    ],
    "params": MODEL_SCHEMAS["bytedance/seedream-v4-text-to-image"]["params"],
    "output": {"kind": "image", "count_max": 6, "format": "png"},
    "cost": {"note": "See Kie credits dashboard"},
})

# Seedream 4.5 + 5 Lite share the V4 param shape (variant note in research doc).
for _vid, _disp in [
    ("bytedance/seedream-4-5-text-to-image", "Seedream 4.5"),
    ("bytedance/seedream-4-5-edit", "Seedream 4.5 Edit"),
    ("bytedance/seedream-5-lite-text-to-image", "Seedream 5 Lite"),
    ("bytedance/seedream-5-lite-image-to-image", "Seedream 5 Lite I2I"),
]:
    _is_edit = "edit" in _vid or "image-to-image" in _vid
    _register({
        "id": _vid, "display_name": _disp, "provider": "Seedream",
        "backend": B_KIE_GENERIC,
        "kind": KIND_IMAGE_EDIT if _is_edit else KIND_T2I,
        "inputs": ([_text("prompt", required=True, max_chars=5000),
                    _images("image_input", min_n=1, max_n=6, required=True)]
                   if _is_edit else
                   [_text("prompt", required=True, max_chars=5000)]),
        "params": MODEL_SCHEMAS["bytedance/seedream-v4-text-to-image"]["params"],
        "output": {"kind": "image", "count_max": 6, "format": "png"},
        "cost": {"note": "See Kie credits dashboard"},
    })


# ─── Kie / Google wrappers ───────────────────────────────────────────────────
_register({
    "id": "google/nano-banana",
    "display_name": "Nano Banana (Kie)",
    "provider": "Google · Kie", "backend": B_KIE_GENERIC, "kind": KIND_T2I,
    "inputs": [_text("prompt", required=True, max_chars=5000)],
    "params": [
        _enum("image_size",
              ["1:1", "9:16", "16:9", "3:4", "4:3", "3:2", "2:3", "5:4",
               "4:5", "21:9", "auto"], default="1:1", label="Aspect ratio"),
        _enum("output_format", ["png", "jpeg"], default="png"),
    ],
    "output": {"kind": "image", "count_max": 1, "format": "png"},
    "cost": {"note": "See Kie credits dashboard"},
})

_register({
    "id": "google/nano-banana-edit",
    "display_name": "Nano Banana Edit (Kie)",
    "provider": "Google · Kie", "backend": B_KIE_GENERIC, "kind": KIND_IMAGE_EDIT,
    "inputs": [
        _text("prompt", required=True, max_chars=5000),
        _images("image_input", min_n=1, max_n=3, required=True),
    ],
    "params": MODEL_SCHEMAS["google/nano-banana"]["params"],
    "output": {"kind": "image", "count_max": 1, "format": "png"},
    "cost": {"note": "See Kie credits dashboard"},
})

_register({
    "id": "nano-banana-2",
    "display_name": "Nano Banana 2 (Kie)",
    "provider": "Google · Kie", "backend": B_KIE_GENERIC, "kind": KIND_T2I,
    "kinds_supported": [KIND_T2I, KIND_IMAGE_COMPOSE],
    "inputs": [
        _text("prompt", required=True, max_chars=20000),
        _images("image_input", min_n=0, max_n=14, max_mb=30),
    ],
    "params": [
        _enum("aspect_ratio",
              ["1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5",
               "5:4", "8:1", "9:16", "16:9", "21:9", "auto"], default="auto"),
        _enum("resolution", ["1K", "2K", "4K"], default="1K"),
        _enum("output_format", ["png", "jpg"], default="jpg"),
    ],
    "output": {"kind": "image", "count_max": 1, "format": "png"},
    "cost": {"note": "See Kie credits dashboard"},
})

_register({
    "id": "nano-banana-pro",
    "display_name": "Nano Banana Pro (Kie)",
    "provider": "Google · Kie", "backend": B_KIE_GENERIC, "kind": KIND_T2I,
    "kinds_supported": [KIND_T2I, KIND_IMAGE_EDIT, KIND_IMAGE_COMPOSE],
    "inputs": [
        _text("prompt", required=True, max_chars=10000),
        _images("image_input", min_n=0, max_n=8, max_mb=30),
    ],
    "params": [
        _enum("aspect_ratio",
              ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16",
               "16:9", "21:9", "auto"], default="1:1"),
        _enum("resolution", ["1K", "2K", "4K"], default="1K"),
        _enum("output_format", ["png", "jpg"], default="png"),
    ],
    "output": {"kind": "image", "count_max": 1, "format": "png"},
    "cost": {"note": "See Kie credits dashboard"},
})

# Imagen 4 trio via Kie — wrappers; same shape as direct Google but routed via Kie.
for _vid, _disp in [
    ("google/imagen4", "Imagen 4 (Kie)"),
    ("google/imagen4-fast", "Imagen 4 Fast (Kie)"),
    ("google/imagen4-ultra", "Imagen 4 Ultra (Kie)"),
]:
    _register({
        "id": _vid, "display_name": _disp, "provider": "Google · Kie",
        "backend": B_KIE_GENERIC, "kind": KIND_T2I,
        "inputs": [_text("prompt", required=True, max_chars=2000)],
        "params": [
            _enum("aspect_ratio", ["1:1", "3:4", "4:3", "9:16", "16:9"],
                  default="1:1"),
            _int("num_images", 1, 1 if "ultra" in _vid else 4,
                 1, label="Variations"),
            _text("negative_prompt"), _seed(),
        ],
        "output": {"kind": "image",
                   "count_max": 1 if "ultra" in _vid else 4, "format": "png"},
        "cost": {"note": "See Kie credits dashboard"},
    })


# ─── Flux 2 family ───────────────────────────────────────────────────────────
_flux2_params = [
    _enum("aspect_ratio", ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3"],
          default="1:1"),
    _enum("resolution", ["1K", "2K"], default="1K"),
    _bool("nsfw_checker"),
]
for _vid, _disp, _kind, _has_image in [
    ("flux-2/pro-text-to-image", "Flux 2 Pro", KIND_T2I, False),
    ("flux-2/pro-image-to-image", "Flux 2 Pro Edit", KIND_IMAGE_EDIT, True),
    ("flux-2/flex-text-to-image", "Flux 2 Flex", KIND_T2I, False),
    ("flux-2/flex-image-to-image", "Flux 2 Flex Edit", KIND_IMAGE_EDIT, True),
]:
    _ins = [_text("prompt", required=True, max_chars=5000)]
    if _has_image:
        _ins.append(_images("image_input", min_n=1, max_n=4, required=True))
    _register({
        "id": _vid, "display_name": _disp, "provider": "Flux",
        "backend": B_KIE_GENERIC, "kind": _kind,
        "inputs": _ins, "params": _flux2_params,
        "output": {"kind": "image", "count_max": 1, "format": "png"},
        "cost": {"note": "See Kie credits dashboard"},
    })


# ─── Ideogram V3 + Character ─────────────────────────────────────────────────
_ideogram_v3_params = [
    _enum("rendering_speed", ["TURBO", "BALANCED", "QUALITY"], default="BALANCED"),
    _enum("style", ["AUTO", "GENERAL", "REALISTIC", "DESIGN"], default="AUTO"),
    _bool("expand_prompt", default=False, label="MagicPrompt rewrite"),
    _enum("image_size",
          ["square", "square_hd", "portrait_4_3", "portrait_16_9",
           "landscape_4_3", "landscape_16_9"], default="square_hd"),
    _seed(),
    _text("negative_prompt", max_chars=5000),
]
for _vid, _disp, _kind, _refs in [
    ("ideogram/v3-text-to-image", "Ideogram V3", KIND_T2I, None),
    ("ideogram/v3-edit", "Ideogram V3 Edit", KIND_IMAGE_EDIT, ("image_input", 1, 2)),
    ("ideogram/v3-remix", "Ideogram V3 Remix", KIND_IMAGE_EDIT, ("image_input", 1, 2)),
    ("ideogram/v3-reframe", "Ideogram V3 Reframe", KIND_IMAGE_EDIT, ("image_input", 1, 1)),
    ("ideogram/character", "Ideogram Character", KIND_T2I, ("character_reference_image", 1, 4)),
    ("ideogram/character-edit", "Ideogram Character Edit", KIND_IMAGE_EDIT, ("character_reference_image", 1, 4)),
    ("ideogram/character-remix", "Ideogram Character Remix", KIND_IMAGE_EDIT, ("character_reference_image", 1, 4)),
]:
    _ins = [_text("prompt", required=True, max_chars=5000)]
    if _refs:
        n, lo, hi = _refs
        _ins.append(_images(n, min_n=lo, max_n=hi, required=True))
    _register({
        "id": _vid, "display_name": _disp, "provider": "Ideogram",
        "backend": B_KIE_GENERIC, "kind": _kind,
        "inputs": _ins, "params": _ideogram_v3_params,
        "output": {"kind": "image", "count_max": 1, "format": "png"},
        "cost": {"note": "See Kie credits dashboard"},
    })


# ─── Qwen ────────────────────────────────────────────────────────────────────
_qwen_params = [
    _enum("image_size",
          ["square", "square_hd", "portrait_4_3", "portrait_16_9",
           "landscape_4_3", "landscape_16_9"], default="square_hd"),
    _int("num_inference_steps", 2, 250, 30),
    _slider("guidance_scale", 0, 20, 2.5, step=0.1, help="CFG scale"),
    _seed(),
    _text("negative_prompt", max_chars=500),
    _bool("enable_safety_checker", default=True),
    _enum("output_format", ["png", "jpeg"], default="png"),
    _enum("acceleration", ["none", "regular", "high"], default="none"),
    _bool("nsfw_checker"),
]
for _vid, _disp, _kind, _refs in [
    ("qwen/text-to-image", "Qwen Image", KIND_T2I, None),
    ("qwen/image-to-image", "Qwen Image I2I", KIND_IMAGE_EDIT, 1),
    ("qwen/image-edit", "Qwen Image Edit", KIND_IMAGE_EDIT, 1),
    ("qwen2/text-to-image", "Qwen 2 Image", KIND_T2I, None),
    ("qwen2/image-edit", "Qwen 2 Image Edit", KIND_IMAGE_EDIT, 1),
]:
    _ins = [_text("prompt", required=True, max_chars=5000)]
    if _refs:
        _ins.append(_images("image_input", min_n=1, max_n=_refs, required=True))
    _register({
        "id": _vid, "display_name": _disp, "provider": "Qwen",
        "backend": B_KIE_GENERIC, "kind": _kind,
        "inputs": _ins, "params": _qwen_params,
        "output": {"kind": "image", "count_max": 1, "format": "png"},
        "cost": {"note": "See Kie credits dashboard"},
    })


# ─── GPT Image (legacy 1.5 + new 2) ──────────────────────────────────────────
for _vid, _disp, _kind, _refs in [
    ("gpt-image-2-text-to-image", "GPT Image 2", KIND_T2I, None),
    ("gpt-image-2-image-to-image", "GPT Image 2 I2I", KIND_IMAGE_EDIT, 4),
    ("gpt-image/1-5-text-to-image", "GPT Image 1.5", KIND_T2I, None),
    ("gpt-image/1-5-image-to-image", "GPT Image 1.5 I2I", KIND_IMAGE_EDIT, 4),
]:
    _ins = [_text("prompt", required=True, max_chars=20000)]
    if _refs:
        _ins.append(_images("image_input", min_n=1, max_n=_refs, required=True))
    _register({
        "id": _vid, "display_name": _disp, "provider": "OpenAI",
        "backend": B_KIE_GENERIC, "kind": _kind,
        "inputs": _ins,
        "params": [
            _enum("aspect_ratio", ["auto", "1:1", "9:16", "16:9", "4:3", "3:4"],
                  default="auto"),
            _enum("resolution", ["1K", "2K", "4K"], default="1K"),
        ],
        "output": {"kind": "image", "count_max": 1, "format": "png"},
        "cost": {"note": "See Kie credits dashboard"},
        "notes": ["1:1 cannot go to 4K. 'auto' aspect → 1K only."],
    })


# ─── Misc image (Z-Image, Wan, Grok) ─────────────────────────────────────────
for _vid, _disp, _provider, _kind, _refs in [
    ("z-image/z-image", "Z-Image", "Z-Image", KIND_T2I, None),
    ("wan/2-7-image", "Wan 2.7 Image", "Wan", KIND_T2I, None),
    ("wan/2-7-image-pro", "Wan 2.7 Image Pro", "Wan", KIND_T2I, None),
    ("grok-imagine/text-to-image", "Grok Imagine", "xAI", KIND_T2I, None),
    ("grok-imagine/image-to-image", "Grok Imagine I2I", "xAI", KIND_IMAGE_EDIT, 1),
]:
    _ins = [_text("prompt", required=True, max_chars=5000)]
    if _refs:
        _ins.append(_images("image_input", min_n=1, max_n=_refs, required=True))
    _register({
        "id": _vid, "display_name": _disp, "provider": _provider,
        "backend": B_KIE_GENERIC, "kind": _kind, "inputs": _ins,
        "params": [
            _enum("aspect_ratio",
                  ["1:1", "16:9", "9:16", "4:3", "3:4"], default="1:1"),
            _seed(),
        ],
        "output": {"kind": "image", "count_max": 1, "format": "png"},
        "cost": {"note": "See Kie credits dashboard"},
    })


# ─── Image utilities ─────────────────────────────────────────────────────────
_register({
    "id": "topaz/image-upscale", "display_name": "Topaz Image Upscale",
    "provider": "Topaz", "backend": B_KIE_GENERIC, "kind": KIND_IMAGE_UPSCALE,
    "inputs": [_image("image_url", required=True, max_mb=10)],
    "params": [_enum("upscale_factor", ["1", "2", "4", "8"], default="2")],
    "output": {"kind": "image", "count_max": 1, "format": "png"},
    "cost": {"note": "See Kie credits dashboard"},
})
_register({
    "id": "recraft/remove-background", "display_name": "Remove Background",
    "provider": "Recraft", "backend": B_KIE_GENERIC, "kind": KIND_IMAGE_BGREMOVE,
    "inputs": [_image("image", required=True, max_mb=5,
                      help="≤5 MB, ≤16 MP, dim 256–4096 px")],
    "params": [],
    "output": {"kind": "image", "count_max": 1, "format": "png"},
    "cost": {"note": "See Kie credits dashboard"},
})
_register({
    "id": "recraft/crisp-upscale", "display_name": "Recraft Crisp Upscale",
    "provider": "Recraft", "backend": B_KIE_GENERIC, "kind": KIND_IMAGE_UPSCALE,
    "inputs": [_image("image", required=True, max_mb=10)],
    "params": [],
    "output": {"kind": "image", "count_max": 1, "format": "png"},
    "cost": {"note": "See Kie credits dashboard"},
})


# ═════════════════════════════════════════════════════════════════════════════
# KIE — Video generation
# ═════════════════════════════════════════════════════════════════════════════

# ─── Kling family ────────────────────────────────────────────────────────────
def _kling_entry(model_id, display, kind, has_image, has_audio=False,
                 has_neg_prompt=True):
    inputs = [_text("prompt", required=True, max_chars=2500)]
    if has_neg_prompt:
        inputs.append(_text("negative_prompt", max_chars=2500))
    if has_image:
        inputs.append(_image("image_url", required=True, max_mb=10))
    if has_audio:
        inputs.append(_audio("audio_url", required=True, max_mb=10,
                             formats=["mp3", "wav", "aac", "mp4", "ogg"]))
    return {
        "id": model_id, "display_name": display, "provider": "Kling",
        "backend": B_KIE_GENERIC, "kind": kind, "inputs": inputs,
        "params": [
            _enum("duration", ["5", "10"], default="5", unit="sec"),
            _enum("aspect_ratio", ["16:9", "9:16", "1:1"], default="16:9"),
            _slider("cfg_scale", 0, 1, 0.5, step=0.1, help="Prompt adherence"),
        ],
        "output": {"kind": "video", "count_max": 1, "format": "mp4"},
        "cost": {"note": "See Kie credits dashboard"},
    }

_register(_kling_entry("kling/v2-5-turbo-text-to-video-pro", "Kling 2.5 Turbo Pro",
                       KIND_T2V, has_image=False))
_register(_kling_entry("kling/v2-5-turbo-image-to-video-pro", "Kling 2.5 Turbo Pro I2V",
                       KIND_I2V, has_image=True))
_register(_kling_entry("kling/v2-1-master-text-to-video", "Kling 2.1 Master",
                       KIND_T2V, has_image=False))
_register(_kling_entry("kling/v2-1-master-image-to-video", "Kling 2.1 Master I2V",
                       KIND_I2V, has_image=True))
_register(_kling_entry("kling/v2-1-pro", "Kling 2.1 Pro", KIND_I2V, has_image=True))
_register(_kling_entry("kling/v2-1-standard", "Kling 2.1", KIND_I2V, has_image=True))
_register(_kling_entry("kling/kling-3-0", "Kling 3.0", KIND_T2V, has_image=False))
_register(_kling_entry("kling/text-to-video", "Kling T2V", KIND_T2V, has_image=False))
_register(_kling_entry("kling/image-to-video", "Kling I2V", KIND_I2V, has_image=True))

# Kling lipsync / avatar
_register({
    "id": "kling/ai-avatar-pro", "display_name": "Kling AI Avatar Pro",
    "provider": "Kling", "backend": B_KIE_GENERIC, "kind": KIND_LIPSYNC,
    "inputs": [
        _image("image_url", required=True, max_mb=10),
        _audio("audio_url", required=True, max_mb=10,
               formats=["mp3", "wav", "aac", "mp4", "ogg"]),
        _text("prompt", max_chars=5000),
    ],
    "params": [],
    "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "See Kie credits dashboard"},
})
_register({
    "id": "kling/ai-avatar-standard", "display_name": "Kling AI Avatar",
    "provider": "Kling", "backend": B_KIE_GENERIC, "kind": KIND_LIPSYNC,
    "inputs": [
        _image("image_url", required=True, max_mb=10),
        _audio("audio_url", required=True, max_mb=10,
               formats=["mp3", "wav", "aac", "mp4", "ogg"]),
        _text("prompt", max_chars=5000),
    ],
    "params": [],
    "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "See Kie credits dashboard"},
})

# Kling motion control
for _vid, _disp in [
    ("kling/motion-control", "Kling Motion Control"),
    ("kling/motion-control-v3", "Kling Motion Control v3"),
]:
    _register({
        "id": _vid, "display_name": _disp, "provider": "Kling",
        "backend": B_KIE_GENERIC, "kind": KIND_VIDEO_ANIMATE,
        "inputs": [
            _text("prompt", required=True, max_chars=2500),
            _image("image_url", required=True, max_mb=10,
                   label="Character image"),
            _video("motion_video_url", required=True, max_mb=20,
                   label="Motion reference"),
        ],
        "params": [
            _enum("duration", ["5", "10"], default="5", unit="sec"),
            _enum("aspect_ratio", ["16:9", "9:16", "1:1"], default="16:9"),
        ],
        "output": {"kind": "video", "count_max": 1, "format": "mp4"},
        "cost": {"note": "See Kie credits dashboard"},
    })


# ─── Seedance family ─────────────────────────────────────────────────────────
_seedance_full_inputs = [
    _text("prompt", required=True, max_chars=20000),
    # Field names confirmed against https://docs.kie.ai/market/bytedance/seedance-2 —
    # the API expects `first_frame_url`, `last_frame_url`, `reference_image_urls`,
    # `reference_video_urls`, `reference_audio_urls`. Earlier names (`first_frame`,
    # `ref_image_urls`, etc.) were silently dropped by the API, which then fell
    # back to text-to-video — exactly the "ignored my reference image" bug.
    _image("first_frame_url", help="Animate from this image (I2V mode)."),
    _image("last_frame_url", help="With first_frame_url, interpolate (Frames mode)."),
    _images("reference_image_urls", min_n=0, max_n=9, max_mb=30,
            help="Up to 9 multimodal subject references (Multimodal-R2V mode)."),
    {"name": "reference_video_urls", "type": T_VIDEO_N, "min_count": 0, "max_count": 3,
     "required": False, "label": "Reference Video URLs",
     "formats": ["mp4", "mov"], "max_mb": 50,
     "help": "Up to 3 reference videos (15s total, ≤50 MB each)."},
    {"name": "reference_audio_urls", "type": T_AUDIO_N, "min_count": 0, "max_count": 3,
     "required": False, "label": "Reference Audio URLs",
     "formats": ["mp3", "wav"], "max_mb": 15,
     "help": "Up to 3 reference audios (15s total, ≤15 MB each)."},
]
_seedance_full_params = [
    _enum("resolution", ["480p", "720p", "1080p"], default="720p"),
    _enum("aspect_ratio",
          ["1:1", "4:3", "3:4", "16:9", "9:16", "21:9", "adaptive"],
          default="16:9"),
    # Dropdown of every accepted second so the user can't type 50 and waste a
    # request on the API rejection. Range comes from the official 4–15s window.
    _enum("duration", [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
          default=5, unit="sec"),
    _bool("generate_audio", default=True,
          help="Adds cost. Disable for silent video."),
    _bool("web_search", default=False),
    _bool("nsfw_checker"),
]
for _vid, _disp in [
    ("bytedance/seedance-2", "Seedance 2"),
    ("bytedance/seedance-2-fast", "Seedance 2 Fast"),
    ("bytedance/seedance-1-5-pro", "Seedance 1.5 Pro"),
]:
    _register({
        "id": _vid, "display_name": _disp, "provider": "Seedance",
        "backend": B_KIE_GENERIC, "kind": KIND_T2V,
        "kinds_supported": [KIND_T2V, KIND_I2V, KIND_FRAMES_TO_VIDEO,
                            KIND_REF_TO_VIDEO],
        "inputs": _seedance_full_inputs, "params": _seedance_full_params,
        "output": {"kind": "video", "count_max": 1, "format": "mp4"},
        "cost": {"note": "See Kie credits dashboard"},
        "notes": ["I2V (first), Frames (first+last) and Multimodal-R2V are mutually exclusive."],
    })

# Seedance v1 variants — simpler shape
for _vid, _disp, _kind in [
    ("bytedance/v1-pro-text-to-video", "Seedance v1 Pro", KIND_T2V),
    ("bytedance/v1-pro-image-to-video", "Seedance v1 Pro I2V", KIND_I2V),
    ("bytedance/v1-pro-fast-image-to-video", "Seedance v1 Pro Fast I2V", KIND_I2V),
    ("bytedance/v1-lite-text-to-video", "Seedance v1 Lite", KIND_T2V),
    ("bytedance/v1-lite-image-to-video", "Seedance v1 Lite I2V", KIND_I2V),
]:
    _ins = [_text("prompt", required=True, max_chars=10000)]
    if _kind == KIND_I2V:
        _ins.append(_image("first_frame", required=True))
    _register({
        "id": _vid, "display_name": _disp, "provider": "Seedance",
        "backend": B_KIE_GENERIC, "kind": _kind, "inputs": _ins,
        "params": [
            _enum("resolution", ["480p", "720p", "1080p"], default="720p"),
            _enum("aspect_ratio",
                  ["16:9", "9:16", "1:1", "4:3", "3:4"], default="16:9"),
            _int("duration", 5, 10, 5, unit="sec"),
        ],
        "output": {"kind": "video", "count_max": 1, "format": "mp4"},
        "cost": {"note": "See Kie credits dashboard"},
    })


# ─── Hailuo family ───────────────────────────────────────────────────────────
for _vid, _disp, _kind, _has_image in [
    ("hailuo/2-3-image-to-video-pro", "Hailuo 2.3 Pro", KIND_I2V, True),
    ("hailuo/2-3-image-to-video-standard", "Hailuo 2.3", KIND_I2V, True),
    ("hailuo/02-text-to-video-pro", "Hailuo 02 Pro", KIND_T2V, False),
    ("hailuo/02-image-to-video-pro", "Hailuo 02 Pro I2V", KIND_I2V, True),
    ("hailuo/02-text-to-video-standard", "Hailuo 02", KIND_T2V, False),
    ("hailuo/02-image-to-video-standard", "Hailuo 02 I2V", KIND_I2V, True),
]:
    _ins = [_text("prompt", required=True, max_chars=5000)]
    if _has_image:
        _ins.append(_image("image_url", required=True, max_mb=10))
    _register({
        "id": _vid, "display_name": _disp, "provider": "Hailuo",
        "backend": B_KIE_GENERIC, "kind": _kind, "inputs": _ins,
        "params": [
            _enum("duration", ["6", "10"], default="6", unit="sec",
                  help="10s unavailable at 1080P."),
            _enum("resolution", ["768P", "1080P"], default="768P"),
            _bool("nsfw_checker"),
        ],
        "output": {"kind": "video", "count_max": 1, "format": "mp4"},
        "cost": {"note": "See Kie credits dashboard"},
    })


# ─── Sora 2 family ───────────────────────────────────────────────────────────
def _sora2_entry(model_id, display, kind, has_image=False,
                 chars_supported=False):
    ins = [_text("prompt", required=True, max_chars=10000)]
    if has_image:
        ins.append(_image("image_url", required=True))
    if chars_supported:
        ins.append({"name": "character_ids", "type": T_CHAR_REF,
                    "min_count": 0, "max_count": 5,
                    "label": "Sora characters",
                    "help": "Pick previously extracted character IDs."})
    return {
        "id": model_id, "display_name": display, "provider": "Sora",
        "backend": B_KIE_GENERIC, "kind": kind, "inputs": ins,
        "params": [
            _enum("aspect_ratio", ["portrait", "landscape"], default="landscape"),
            _enum("n_frames", ["10", "15"], default="10"),
            _enum("size", ["standard", "high"], default="high"),
            _bool("remove_watermark", default=False),
        ],
        "output": {"kind": "video", "count_max": 1, "format": "mp4"},
        "cost": {"note": "See Kie credits dashboard"},
    }

_register(_sora2_entry("sora-2-text-to-video", "Sora 2", KIND_T2V))
_register(_sora2_entry("sora-2-image-to-video", "Sora 2 I2V", KIND_I2V, has_image=True))
_register(_sora2_entry("sora-2-pro-text-to-video", "Sora 2 Pro", KIND_T2V,
                       chars_supported=True))
_register(_sora2_entry("sora-2-pro-image-to-video", "Sora 2 Pro I2V", KIND_I2V,
                       has_image=True, chars_supported=True))

_register({
    "id": "sora-2-pro-storyboard", "display_name": "Sora 2 Pro Storyboard",
    "provider": "Sora", "backend": B_KIE_GENERIC, "kind": KIND_T2V,
    "inputs": [
        _text("storyboard_json", required=True, max_chars=20000,
              label="Storyboard JSON",
              help="Multi-shot storyboard. See Sora docs for structure."),
    ],
    "params": [
        _enum("aspect_ratio", ["portrait", "landscape"], default="landscape"),
        _enum("size", ["standard", "high"], default="high"),
    ],
    "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "See Kie credits dashboard"},
})

_register({
    "id": "sora-2-characters-pro", "display_name": "Extract Sora Character",
    "provider": "Sora", "backend": B_KIE_GENERIC, "kind": KIND_CHARACTER_REF,
    "inputs": [
        {"name": "origin_task_id", "type": T_TASK_REF, "required": True,
         "label": "Source Sora video", "filter_provider": "Sora"},
        _line("timestamps", required=True,
              placeholder="e.g. 2.5,5.0",
              help="Window in 'start,end' seconds (1–4 sec window)."),
        _text("character_prompt", required=True, label="Character description"),
        _line("character_user_name", max_chars=40, label="Character name"),
        _text("safety_instruction"),
    ],
    "params": [],
    "output": {"kind": "character_id"},
    "cost": {"note": "See Kie credits dashboard"},
})

_register({
    "id": "sora-watermark-remover", "display_name": "Sora Watermark Remover",
    "provider": "Sora", "backend": B_KIE_GENERIC, "kind": KIND_WATERMARK_RM,
    "inputs": [{"name": "origin_task_id", "type": T_TASK_REF, "required": True,
                "label": "Source Sora video", "filter_provider": "Sora"}],
    "params": [], "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "See Kie credits dashboard"},
})


# ─── Wan family ──────────────────────────────────────────────────────────────
# Per https://docs.kie.ai/market/wan/2-7-* the 4 variants accept different
# param sets — sharing one blob caused "ratio is not supported for I2V" errors.
# T2V uses `ratio`, R2V/V2V use `aspect_ratio`, I2V has no aspect param at all.
_wan_27_common_params = [
    _enum("resolution", ["720p", "1080p"], default="1080p"),
    _enum("duration", [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
          default=5, unit="sec"),
    _bool("prompt_extend", default=True, label="Auto-enhance prompt"),
    _bool("watermark", default=False),
    _seed(), _bool("nsfw_checker"),
]
_wan_27_t2v_params = [_wan_27_common_params[0],  # resolution
                     _enum("ratio", ["16:9", "9:16", "1:1", "4:3", "3:4"], default="16:9"),
                     *_wan_27_common_params[1:]]
_wan_27_r2v_params = [_wan_27_common_params[0],  # resolution
                     _enum("aspect_ratio", ["16:9", "9:16", "1:1", "4:3", "3:4"], default="16:9"),
                     *_wan_27_common_params[1:]]
_wan_27_i2v_params = list(_wan_27_common_params)  # no aspect/ratio at all
_register({
    "id": "wan/2-7-text-to-video", "display_name": "Wan 2.7", "provider": "Wan",
    "backend": B_KIE_GENERIC, "kind": KIND_T2V,
    "inputs": [
        _text("prompt", required=True, max_chars=5000),
        _text("negative_prompt", max_chars=500),
        _audio("audio_url", help="Custom audio track (optional)."),
    ],
    "params": _wan_27_t2v_params,
    "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "See Kie credits dashboard"},
})
_register({
    "id": "wan/2-7-image-to-video", "display_name": "Wan 2.7 I2V",
    "provider": "Wan", "backend": B_KIE_GENERIC, "kind": KIND_I2V,
    # Field names confirmed via https://docs.kie.ai/market/wan/2-7-image-to-video —
    # API expects `first_frame_url` / `last_frame_url` / `first_clip_url` /
    # `driving_audio_url`. Old `image_url` / `audio_url` were silently ignored.
    "inputs": [
        _text("prompt", required=True, max_chars=5000),
        _text("negative_prompt", max_chars=500),
        _image("first_frame_url", required=True, max_mb=10,
               help="Animate from this image (I2V)."),
        _image("last_frame_url", max_mb=10,
               help="Optional end frame for interpolation."),
        _video("first_clip_url", max_mb=50,
               help="Optional start-clip (extends from a video)."),
        _audio("driving_audio_url", help="Custom audio track (optional)."),
    ],
    "params": _wan_27_i2v_params,
    "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "See Kie credits dashboard"},
})
_register({
    "id": "wan/2-7-r2v", "display_name": "Wan 2.7 Reference-to-Video",
    "provider": "Wan", "backend": B_KIE_GENERIC, "kind": KIND_REF_TO_VIDEO,
    # Field names confirmed via https://docs.kie.ai/market/wan/2-7-r2v — API
    # accepts `reference_image` / `reference_video` (arrays), plus `first_frame`
    # (single) and `reference_voice` (audio). Earlier `audio_url` was silently
    # ignored.
    "inputs": [
        _text("prompt", required=True, max_chars=5000),
        _text("negative_prompt", max_chars=500),
        _images("reference_image", min_n=0, max_n=9, max_mb=10,
                label="Reference Images",
                help="Up to 9 reference images."),
        {"name": "reference_video", "type": T_VIDEO_N, "min_count": 0, "max_count": 3,
         "required": False, "label": "Reference Videos",
         "formats": ["mp4", "mov"], "max_mb": 50,
         "help": "Up to 3 reference videos."},
        _image("first_frame", max_mb=10,
               help="Optional start frame to anchor the animation."),
        _audio("reference_voice",
               help="Audio for voice-timbre matching (WAV/MP3)."),
    ],
    "params": _wan_27_r2v_params,
    "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "See Kie credits dashboard"},
    "notes": ["Provide at least one reference_image OR reference_video."],
})
_register({
    "id": "wan/2-7-videoedit", "display_name": "Wan 2.7 Video Edit",
    "provider": "Wan", "backend": B_KIE_GENERIC, "kind": KIND_V2V,
    # Field names confirmed via https://docs.kie.ai/market/wan/2-7-videoedit —
    # API accepts `video_url` (not `source_video_url`) plus `reference_image`
    # for style guidance and an `audio_setting` enum.
    "inputs": [
        _text("prompt", required=True, max_chars=5000),
        _text("negative_prompt", max_chars=500),
        _video("video_url", required=True, max_mb=50,
               label="Source Video"),
        _image("reference_image", max_mb=10,
               help="Optional style/identity reference image."),
    ],
    "params": _wan_27_r2v_params,  # V2V uses aspect_ratio same as R2V
    "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "See Kie credits dashboard"},
})

# Wan 2.6 / 2.5 simpler variants
for _vid, _disp, _kind, _has_image, _is_v2v in [
    ("wan/2-6-text-to-video", "Wan 2.6", KIND_T2V, False, False),
    ("wan/2-6-image-to-video", "Wan 2.6 I2V", KIND_I2V, True, False),
    ("wan/2-6-video-to-video", "Wan 2.6 V2V", KIND_V2V, False, True),
    ("wan/2-6-flash-image-to-video", "Wan 2.6 Flash I2V", KIND_I2V, True, False),
    ("wan/2-6-flash-video-to-video", "Wan 2.6 Flash V2V", KIND_V2V, False, True),
    ("wan/2-5-text-to-video", "Wan 2.5", KIND_T2V, False, False),
    ("wan/2-5-image-to-video", "Wan 2.5 I2V", KIND_I2V, True, False),
]:
    _ins = [_text("prompt", required=True, max_chars=5000),
            _text("negative_prompt", max_chars=500)]
    if _has_image:
        _ins.append(_image("image_url", required=True, max_mb=10))
    if _is_v2v:
        _ins.append(_video("source_video_url", required=True, max_mb=50))
    _register({
        "id": _vid, "display_name": _disp, "provider": "Wan",
        "backend": B_KIE_GENERIC, "kind": _kind, "inputs": _ins,
        "params": [
            _enum("resolution", ["480p", "720p", "1080p"], default="720p"),
            _enum("ratio", ["16:9", "9:16", "1:1", "4:3", "3:4"], default="16:9"),
            _int("duration", 2, 15, 5, unit="sec"),
            _seed(),
        ],
        "output": {"kind": "video", "count_max": 1, "format": "mp4"},
        "cost": {"note": "See Kie credits dashboard"},
    })

# Wan 2.2 turbo + animate + speech
_wan22_turbo_params = [
    _enum("resolution", ["480p", "580p", "720p"], default="480p"),
    _enum("aspect_ratio", ["16:9", "9:16", "1:1"], default="16:9"),
    _int("duration", 2, 8, 5, unit="sec"),
    _seed(),
]
_register({
    "id": "wan/2-2-a14b-text-to-video-turbo", "display_name": "Wan 2.2 Turbo",
    "provider": "Wan", "backend": B_KIE_GENERIC, "kind": KIND_T2V,
    "inputs": [_text("prompt", required=True, max_chars=5000),
               _text("negative_prompt", max_chars=500)],
    "params": _wan22_turbo_params,
    "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "See Kie credits dashboard"},
})
_register({
    "id": "wan/2-2-a14b-image-to-video-turbo", "display_name": "Wan 2.2 Turbo I2V",
    "provider": "Wan", "backend": B_KIE_GENERIC, "kind": KIND_I2V,
    "inputs": [_text("prompt", required=True, max_chars=5000),
               _text("negative_prompt", max_chars=500),
               _image("image_url", required=True, max_mb=10)],
    "params": _wan22_turbo_params,
    "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "See Kie credits dashboard"},
})
_register({
    "id": "wan/2-2-a14b-speech-to-video-turbo",
    "display_name": "Wan 2.2 Speech-to-Video",
    "provider": "Wan", "backend": B_KIE_GENERIC, "kind": KIND_LIPSYNC,
    "inputs": [
        _text("prompt", required=True, max_chars=5000),
        _image("image_url", required=True, max_mb=10),
        _audio("audio_url", required=True, max_mb=10,
               formats=["mp3", "wav", "ogg", "m4a", "flac", "aac"]),
        _text("negative_prompt", max_chars=500),
    ],
    "params": [
        _int("num_frames", 40, 120, 80, step=4),
        _int("frames_per_second", 4, 60, 16, label="FPS"),
        _enum("resolution", ["480p", "580p", "720p"], default="480p"),
        _seed(),
        _int("num_inference_steps", 2, 40, 27),
        _slider("guidance_scale", 1, 10, 3.5, step=0.1),
        _slider("shift", 1, 10, 5, step=0.1),
        _bool("nsfw_checker"),
    ],
    "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "See Kie credits dashboard"},
})
_register({
    "id": "wan/2-2-animate-move", "display_name": "Wan Animate (Motion)",
    "provider": "Wan", "backend": B_KIE_GENERIC, "kind": KIND_VIDEO_ANIMATE,
    "inputs": [
        _video("source_video", required=True, max_mb=10),
        _video("motion_video", required=True, max_mb=10,
               help="Motion to transfer onto source."),
    ],
    "params": [
        _enum("resolution", ["480p", "580p", "720p"], default="480p"),
        _bool("nsfw_checker"),
    ],
    "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "See Kie credits dashboard"},
})
_register({
    "id": "wan/2-2-animate-replace", "display_name": "Wan Animate (Replace)",
    "provider": "Wan", "backend": B_KIE_GENERIC, "kind": KIND_VIDEO_ANIMATE,
    "inputs": [
        _video("source_video", required=True, max_mb=10),
        _image("character_image", required=True, max_mb=10),
    ],
    "params": [
        _enum("resolution", ["480p", "580p", "720p"], default="480p"),
        _bool("nsfw_checker"),
    ],
    "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "See Kie credits dashboard"},
})


# ─── HappyHorse ──────────────────────────────────────────────────────────────
_hh_params = [
    _enum("resolution", ["720p", "1080p"], default="1080p"),
    _enum("aspect_ratio", ["16:9", "9:16", "1:1", "4:3", "3:4"], default="16:9"),
    _int("duration", 3, 15, 5, unit="sec"),
    _seed(),
]
_register({
    "id": "happyhorse/text-to-video", "display_name": "HappyHorse",
    "provider": "HappyHorse", "backend": B_KIE_GENERIC, "kind": KIND_T2V,
    "inputs": [_text("prompt", required=True, max_chars=5000)],
    "params": _hh_params,
    "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "See Kie credits dashboard"},
})
_register({
    "id": "happyhorse/image-to-video", "display_name": "HappyHorse I2V",
    "provider": "HappyHorse", "backend": B_KIE_GENERIC, "kind": KIND_I2V,
    # API field is `image_urls` (plural, array) per
    # https://docs.kie.ai/market/happyhorse/image-to-video
    "inputs": [_text("prompt", required=True, max_chars=5000),
               _images("image_urls", min_n=1, max_n=4, required=True,
                       max_mb=10, label="Image URLs")],
    "params": _hh_params,
    "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "See Kie credits dashboard"},
})
_register({
    "id": "happyhorse/reference-to-video", "display_name": "HappyHorse R2V",
    "provider": "HappyHorse", "backend": B_KIE_GENERIC, "kind": KIND_REF_TO_VIDEO,
    # Field name confirmed via https://docs.kie.ai/market/happyhorse/reference-to-video —
    # API accepts a single `reference_image` array (was `ref_image_urls`).
    "inputs": [
        _text("prompt", required=True, max_chars=5000,
              help="Image order = character1, character2…"),
        _images("reference_image", min_n=1, max_n=9, required=True, max_mb=10,
                label="Reference Images"),
    ],
    "params": _hh_params,
    "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "See Kie credits dashboard"},
})
_register({
    "id": "happyhorse/video-edit", "display_name": "HappyHorse Video Edit",
    "provider": "HappyHorse", "backend": B_KIE_GENERIC, "kind": KIND_V2V,
    "inputs": [
        _text("prompt", required=True, max_chars=5000),
        _video("source_video_url", required=True, max_mb=50),
    ],
    "params": _hh_params,
    "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "See Kie credits dashboard"},
})


# ─── InfiniTalk lipsync ──────────────────────────────────────────────────────
_register({
    "id": "infinitalk/from-audio", "display_name": "InfiniTalk Lipsync",
    "provider": "InfiniTalk", "backend": B_KIE_GENERIC, "kind": KIND_LIPSYNC,
    "inputs": [
        _image("image_url", required=True, max_mb=10),
        _audio("audio_url", required=True, max_mb=10,
               formats=["mp3", "wav", "aac", "mp4", "ogg"]),
        _text("prompt", max_chars=5000),
    ],
    "params": [
        _enum("resolution", ["480p", "720p"], default="480p"),
        _int("seed", 10000, 1000000, 100000),
    ],
    "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "See Kie credits dashboard"},
})


# ─── Grok Imagine video ──────────────────────────────────────────────────────
for _vid, _disp, _kind, _has_image in [
    ("grok-imagine/text-to-video", "Grok Imagine Video", KIND_T2V, False),
    ("grok-imagine/image-to-video", "Grok Imagine I2V", KIND_I2V, True),
]:
    _ins = [_text("prompt", required=True, max_chars=5000)]
    if _has_image:
        _ins.append(_image("image_url", required=True, max_mb=10))
    _register({
        "id": _vid, "display_name": _disp, "provider": "xAI",
        "backend": B_KIE_GENERIC, "kind": _kind, "inputs": _ins,
        "params": [
            _enum("aspect_ratio", ["16:9", "9:16", "1:1"], default="16:9"),
            _enum("duration", ["5", "10"], default="5", unit="sec"),
        ],
        "output": {"kind": "video", "count_max": 1, "format": "mp4"},
        "cost": {"note": "See Kie credits dashboard"},
    })

_register({
    "id": "grok-imagine/extend", "display_name": "Grok Imagine Extend",
    "provider": "xAI", "backend": B_KIE_GENERIC, "kind": KIND_VIDEO_EXTEND,
    "inputs": [
        {"name": "origin_task_id", "type": T_TASK_REF, "required": True,
         "label": "Source video", "filter_provider": "xAI"},
        _text("prompt", max_chars=5000),
    ],
    "params": [_enum("duration", ["5", "10"], default="5", unit="sec")],
    "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "See Kie credits dashboard"},
})
_register({
    "id": "grok-imagine/upscale", "display_name": "Grok Imagine Video Upscale",
    "provider": "xAI", "backend": B_KIE_GENERIC, "kind": KIND_VIDEO_UPSCALE,
    "inputs": [{"name": "origin_task_id", "type": T_TASK_REF, "required": True,
                "label": "Source video", "filter_provider": "xAI"}],
    "params": [],
    "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "See Kie credits dashboard"},
})


# ─── Veo 3 via Kie wrapper ───────────────────────────────────────────────────
_register({
    "id": "veo3-kie", "display_name": "Veo 3 (via Kie)",
    "provider": "Google · Kie", "backend": B_KIE_VEO,
    "kind": KIND_T2V,
    "kinds_supported": [KIND_T2V, KIND_I2V, KIND_FRAMES_TO_VIDEO,
                        KIND_REF_TO_VIDEO],
    "inputs": [
        _text("prompt", required=True, max_chars=5000),
        _images("imageUrls", min_n=0, max_n=3,
                help="1 = ref / 2 = first+last frames / 3 = material refs."),
    ],
    "params": [
        _enum("model", ["veo3", "veo3_fast", "veo3_lite"], default="veo3_fast"),
        _enum("aspect_ratio", ["16:9", "9:16", "Auto"], default="16:9"),
        _enum("resolution", ["720p", "1080p", "4k"], default="720p",
              help="4K ≈ 2× credits."),
        _line("watermark", help="Optional text overlay."),
        _bool("enableTranslation", default=True,
              label="Auto-translate to English"),
    ],
    "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "~25% of Google official Veo pricing"},
})
_register({
    "id": "veo3-kie-extend", "display_name": "Veo 3 Extend (via Kie)",
    "provider": "Google · Kie", "backend": B_KIE_VEO, "kind": KIND_VIDEO_EXTEND,
    "inputs": [{"name": "origin_task_id", "type": T_TASK_REF, "required": True,
                "label": "Source Veo video"},
               _text("prompt", max_chars=5000)],
    "params": [],
    "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "See Kie credits dashboard"},
})


# ─── Runway via Kie ──────────────────────────────────────────────────────────
_register({
    "id": "runway-gen", "display_name": "Runway Gen",
    "provider": "Runway", "backend": B_KIE_RUNWAY, "kind": KIND_T2V,
    "kinds_supported": [KIND_T2V, KIND_I2V],
    "inputs": [
        _text("prompt", required=True, max_chars=2048),
        _image("image_url", help="First frame (image-to-video)."),
    ],
    "params": [
        _enum("aspectRatio", ["16:9", "9:16", "4:3", "3:4", "1:1", "21:9"],
              default="16:9"),
        _int("duration", 5, 10, 5, unit="sec"),
        _seed(),
        _line("waterMark", help="Optional watermark text."),
    ],
    "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "See Kie credits dashboard"},
})
_register({
    "id": "runway-aleph", "display_name": "Runway Aleph",
    "provider": "Runway", "backend": B_KIE_RUNWAY, "kind": KIND_V2V,
    "inputs": [
        _text("prompt", required=True, max_chars=2048),
        _video("videoUrl", required=True),
        _image("referenceImage", help="Style/content reference."),
    ],
    "params": [
        _enum("aspectRatio", ["16:9", "9:16", "4:3", "3:4", "1:1", "21:9"],
              default="16:9"),
        _seed(),
        _bool("uploadCn", default=False),
    ],
    "output": {"kind": "video", "count_max": 1, "format": "mp4",
               "details": "URLs valid 14 days"},
    "cost": {"note": "See Kie credits dashboard"},
})
_register({
    "id": "runway-extend", "display_name": "Runway Extend",
    "provider": "Runway", "backend": B_KIE_RUNWAY, "kind": KIND_VIDEO_EXTEND,
    "inputs": [{"name": "origin_task_id", "type": T_TASK_REF, "required": True,
                "label": "Source Runway video", "filter_provider": "Runway"}],
    "params": [_int("duration", 5, 10, 5, unit="sec")],
    "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "See Kie credits dashboard"},
})


# ─── Topaz video ─────────────────────────────────────────────────────────────
_register({
    "id": "topaz/video-upscale", "display_name": "Topaz Video Upscale",
    "provider": "Topaz", "backend": B_KIE_GENERIC, "kind": KIND_VIDEO_UPSCALE,
    "inputs": [_video("video_url", required=True, max_mb=200)],
    "params": [_enum("upscale_factor", ["2", "4"], default="2")],
    "output": {"kind": "video", "count_max": 1, "format": "mp4"},
    "cost": {"note": "See Kie credits dashboard"},
})


# ═════════════════════════════════════════════════════════════════════════════
# KIE — Speech / Audio (ElevenLabs)
# ═════════════════════════════════════════════════════════════════════════════
_register({
    "id": "elevenlabs/text-to-speech-multilingual-v2",
    "display_name": "ElevenLabs Multilingual v2",
    "provider": "ElevenLabs", "backend": B_KIE_GENERIC, "kind": KIND_TTS,
    "inputs": [_text("text", required=True, max_chars=5000)],
    "params": [
        _line("voice", placeholder="Rachel",
              help="80+ preset voices or custom voice_id."),
        _slider("stability", 0, 1, 0.5),
        _slider("similarity_boost", 0, 1, 0.75),
        _slider("style", 0, 1, 0),
        _slider("speed", 0.7, 1.2, 1.0, step=0.05),
        _bool("timestamps", default=False),
        _text("previous_text", max_chars=5000, help="Continuity context."),
        _text("next_text", max_chars=5000),
        _line("language_code", placeholder="auto (e.g. en, es, fr)"),
    ],
    "output": {"kind": "audio", "count_max": 1, "format": "mp3"},
    "cost": {"note": "See Kie credits dashboard"},
})

_register({
    "id": "elevenlabs/text-to-speech-turbo-2-5",
    "display_name": "ElevenLabs Turbo 2.5",
    "provider": "ElevenLabs", "backend": B_KIE_GENERIC, "kind": KIND_TTS,
    "inputs": [_text("text", required=True, max_chars=5000)],
    "params": MODEL_SCHEMAS["elevenlabs/text-to-speech-multilingual-v2"]["params"],
    "output": {"kind": "audio", "count_max": 1, "format": "mp3"},
    "cost": {"note": "See Kie credits dashboard"},
    "notes": ["Lower latency than Multilingual v2."],
})

_register({
    "id": "elevenlabs/text-to-dialogue-v3",
    "display_name": "ElevenLabs Dialogue v3",
    "provider": "ElevenLabs", "backend": B_KIE_GENERIC, "kind": KIND_TTS_DIALOGUE,
    "inputs": [
        _text("dialogue_json", required=True, max_chars=5000,
              label="Dialogue JSON",
              help='Array of {"text": "...", "voice": "voice_id"} turns. Combined ≤5000 chars.'),
    ],
    "params": [
        _enum("stability", ["0.0", "0.5", "1.0"], default="0.5"),
        _line("language_code", placeholder="auto"),
    ],
    "output": {"kind": "audio", "count_max": 1, "format": "mp3"},
    "cost": {"note": "See Kie credits dashboard"},
})

_register({
    "id": "elevenlabs/sound-effect-v2",
    "display_name": "ElevenLabs Sound Effect",
    "provider": "ElevenLabs", "backend": B_KIE_GENERIC, "kind": KIND_SOUND_EFFECT,
    "inputs": [_text("text", required=True, max_chars=5000)],
    "params": [
        _slider("duration_seconds", 0.5, 22, 5, step=0.5,
                help="Auto if omitted."),
        _slider("prompt_influence", 0, 1, 0.3),
        _bool("loop", default=False, label="Smooth loop"),
        _enum("output_format",
              ["mp3_44100_128", "mp3_44100_192", "pcm_44100", "pcm_22050",
               "ulaw_8000", "alaw_8000", "opus_48000_64"],
              default="mp3_44100_128"),
    ],
    "output": {"kind": "audio", "count_max": 1, "format": "mp3"},
    "cost": {"note": "See Kie credits dashboard"},
})

_register({
    "id": "elevenlabs/speech-to-text", "display_name": "ElevenLabs STT",
    "provider": "ElevenLabs", "backend": B_KIE_GENERIC, "kind": KIND_STT,
    "inputs": [_audio("audio_url", required=True, max_mb=200,
                      formats=["mp3", "wav", "aac", "ogg"])],
    "params": [
        _line("language_code", placeholder="auto"),
        _bool("tag_audio_events", help="Tag laughs, applause, etc."),
        _bool("diarize", help="Annotate who is speaking."),
    ],
    "output": {"kind": "text"},
    "cost": {"note": "See Kie credits dashboard"},
})

_register({
    "id": "elevenlabs/audio-isolation", "display_name": "ElevenLabs Audio Isolation",
    "provider": "ElevenLabs", "backend": B_KIE_GENERIC, "kind": KIND_AUDIO_ISOLATE,
    "inputs": [_audio("audio_url", required=True, max_mb=200)],
    "params": [],
    "output": {"kind": "audio", "count_max": 1, "format": "mp3"},
    "cost": {"note": "See Kie credits dashboard"},
})


# ═════════════════════════════════════════════════════════════════════════════
# Provider grouping for the model picker (UI display order).
# ═════════════════════════════════════════════════════════════════════════════
def get_provider_groups():
    """Return providers in display order with their model_ids grouped by kind."""
    order = [
        "Google", "Google · Kie", "Seedream", "Flux", "Ideogram", "Qwen",
        "OpenAI", "xAI", "Z-Image", "Wan", "Recraft", "Topaz",
        "Kling", "Seedance", "Hailuo", "Sora", "HappyHorse", "Runway",
        "InfiniTalk", "ElevenLabs",
    ]
    groups = {p: [] for p in order}
    extras = {}
    for mid, m in MODEL_SCHEMAS.items():
        prov = m["provider"]
        bucket = groups.get(prov)
        if bucket is None:
            bucket = extras.setdefault(prov, [])
        bucket.append({
            "id": mid, "display_name": m["display_name"],
            "kind": m["kind"], "kinds_supported": m.get("kinds_supported", [m["kind"]]),
        })
    out = [{"provider": p, "models": groups[p]} for p in order if groups[p]]
    for p, ms in extras.items():
        out.append({"provider": p, "models": ms})
    return out


def get_schema(model_id):
    return MODEL_SCHEMAS.get(model_id)


def list_kinds():
    return sorted({m["kind"] for m in MODEL_SCHEMAS.values()}
                  | {k for m in MODEL_SCHEMAS.values()
                       for k in m.get("kinds_supported", [])})
