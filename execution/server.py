import os
import sys
import io
import json
import re
import logging
import glob as glob_module
import zipfile
import socket
import ipaddress
from functools import wraps
from datetime import timedelta, datetime
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, render_template, request, jsonify, send_from_directory, send_file, g

logger = logging.getLogger(__name__)
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
import firebase_admin
from firebase_admin import credentials, auth, firestore
# firebase_admin.firestore re-exports these from google.cloud.firestore at
# runtime, but the firebase_admin type stubs don't list them — pyrefly
# flags every `SERVER_TIMESTAMP` etc. as missing-attribute. Pull
# them from the canonical module so the IDE stays quiet. Runtime behavior
# is identical (same Sentinel / Query / transform objects).
from google.cloud.firestore import (
    SERVER_TIMESTAMP, DELETE_FIELD, Query, ArrayUnion, ArrayRemove,
)

# Ensure the execution directory is in the Python path
sys.path.insert(0, os.path.dirname(__file__))
from gemini_client import (generate_image_content, generate_tts, generate_content,
                           analyze_style_from_images, analyze_style_from_text,
                           analyze_image_for_identity,
                           expand_creative_direction, refine_creative_direction,
                           generate_scene_image, edit_scene_image,
                           start_video_generation, poll_video_generation,
                           generate_music_content)
from research_templates import (get_all_templates_metadata, get_template, build_research_queries,
                                build_title_suggestions_prompt, AUDIENCE_PROFILES, TONE_DEFINITIONS,
                                FORMAT_PRESETS, VIEWER_OUTCOMES)
from research_scriptwriter import (
    build_research_dossier, generate_narration, generate_production_table,
    auto_suggest_tone, regenerate_beats, start_deep_research, poll_deep_research,
    run_structured_research, structure_from_blob, _markdown_from_structured,
    extract_narrative_spine, rerank_narrative_spine, suggest_spine_edits,
)
from youtube_utils import analyze_style
from kie_client import (check_credits as kie_check_credits,
                        upload_image_url as kie_upload_image,
                        create_task as kie_create_task,
                        poll_task as kie_poll_task,
                        get_models_info as kie_get_models_info,
                        download_result as kie_download_result,
                        mj_create_task as kie_mj_create_task,
                        mj_poll_task as kie_mj_poll_task,
                        mj_upscale as kie_mj_upscale,
                        mj_vary as kie_mj_vary)
from seedance_studio import register_routes as register_seedance_routes
from model_schemas import (MODEL_SCHEMAS as STUDIO_MODELS,
                           get_provider_groups as studio_provider_groups,
                           get_schema as studio_get_schema)
import firestore_helpers as fh

# Paths relative to this script's location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
UI_DIR = os.path.join(PROJECT_DIR, "ui")
GENERATED_DIR = os.path.join(PROJECT_DIR, "generated_images")
AUDIO_DIR = os.path.join(PROJECT_DIR, "generated_audio")
VIDEO_DIR = os.path.join(PROJECT_DIR, "generated_videos")
TMP_DIR = os.path.join(PROJECT_DIR, ".tmp")
DEBUG_SAVE_TMP = os.environ.get('DEBUG_SAVE_TMP', 'true').lower() == 'true'
# Feature flag: when true, /api/research emits a structured {sections, claims, sources}
# object alongside the legacy markdown dossier. Kept off by default during rollout.
RESEARCH_STRUCTURED_ENABLED = os.environ.get('RESEARCH_STRUCTURED', '0').lower() in ('1', 'true', 'yes')
RESEARCH_SCHEMA_VERSION = 1

# Feature flag: when true, /api/research auto-extracts a Narrative Spine
# (ranked claims + logical flow + source map) and downstream prompts consume it
# to keep facts and citations stable across script gen, beat regen, and production.
NARRATIVE_SPINE_ENABLED = os.environ.get('NARRATIVE_SPINE', '0').lower() in ('1', 'true', 'yes')

# ── Firebase Initialization ──
SERVICE_ACCOUNT_PATH = os.path.join(PROJECT_DIR, "firebase-service-account.json")
try:
    with open(SERVICE_ACCOUNT_PATH) as f:
        _service_acc = json.load(f)
        _project_id = _service_acc.get("project_id", "gen-lang-client-0854991687")
except Exception:
    _project_id = "gen-lang-client-0854991687"

bucket_name = f"{_project_id}.firebasestorage.app"

# Guard against double-init: if a lazy import elsewhere re-imports this module
# under a different name (e.g. `server` vs `execution.server`), we'd otherwise
# crash with "default Firebase app already exists" inside the second load.
if not firebase_admin._apps:
    if os.path.exists(SERVICE_ACCOUNT_PATH):
        cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(cred, {'storageBucket': bucket_name})
    else:
        # Fall back to default credentials (e.g., on Cloud Run with GOOGLE_APPLICATION_CREDENTIALS)
        firebase_admin.initialize_app(options={'storageBucket': bucket_name})

db = firestore.client()

try:
    from firebase_admin import storage
    bucket = storage.bucket()
except Exception as e:
    print(f"Warning: Could not initialize Firebase Storage: {e}")
    bucket = None

# ── IAM Signing Credentials (for Cloud Run where no private key is available) ──
_signing_email = None
_signing_credentials = None

if not os.path.exists(SERVICE_ACCOUNT_PATH):
    try:
        import google.auth
        import google.auth.transport.requests
        _signing_credentials, _project = google.auth.default()
        auth_request = google.auth.transport.requests.Request()
        _signing_credentials.refresh(auth_request)
        _signing_email = _signing_credentials.service_account_email
        print(f"[Storage] IAM signing configured for: {_signing_email}")
    except Exception as e:
        print(f"[Storage] Warning: Could not configure IAM signing: {e}")

# Log active signing method
if os.path.exists(SERVICE_ACCOUNT_PATH):
    print(f"[Storage] Using service account JSON for signing: {SERVICE_ACCOUNT_PATH}")
elif _signing_email:
    print(f"[Storage] Using IAM signing (Cloud Run mode) with: {_signing_email}")
else:
    print("[Storage] WARNING: No signing method available. Signed URLs will fail.")


def _generate_signed_url(blob, expiration=timedelta(days=7)):
    """Generate a signed URL for a blob, with IAM-based fallback for Cloud Run.

    Default 7 days (Firebase/GCS signed URL max). The MCP App viewer holds onto
    these URLs in chat history; a 4h TTL caused "ExpiredToken" the next day.
    """
    try:
        return blob.generate_signed_url(
            version="v4",
            expiration=expiration,
            method="GET",
        )
    except Exception:
        if _signing_email and _signing_credentials:
            try:
                import google.auth.transport.requests
                auth_request = google.auth.transport.requests.Request()
                _signing_credentials.refresh(auth_request)
                return blob.generate_signed_url(
                    version="v4",
                    expiration=expiration,
                    method="GET",
                    service_account_email=_signing_email,
                    access_token=_signing_credentials.token,
                )
            except Exception as iam_err:
                print(f"[Storage] IAM signing failed for {blob.name}: {iam_err}")
                return None
        return None


def create_signed_put_url(blob_path: str, content_type: str,
                          expiration_seconds: int = 900):
    """Generate a v4-signed PUT URL plus a read-only GET URL for the same blob.

    Lets clients (Claude's sandbox, the user's browser, etc.) upload bytes
    directly to Firebase Storage without going through the API. Returns
    (put_url, get_url) or (None, None) on failure. The PUT URL expires in
    `expiration_seconds` (default 15 min); the GET URL uses the usual 4-hour
    lifetime from `_generate_signed_url`.

    The client MUST send a `Content-Type` header matching `content_type`
    exactly, or the signed-URL verification will reject the PUT.
    """
    if not bucket:
        return (None, None)
    try:
        blob = bucket.blob(blob_path)
        try:
            put_url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(seconds=expiration_seconds),
                method="PUT",
                content_type=content_type,
            )
        except Exception:
            if _signing_email and _signing_credentials:
                import google.auth.transport.requests
                auth_request = google.auth.transport.requests.Request()
                _signing_credentials.refresh(auth_request)
                put_url = blob.generate_signed_url(
                    version="v4",
                    expiration=timedelta(seconds=expiration_seconds),
                    method="PUT",
                    content_type=content_type,
                    service_account_email=_signing_email,
                    access_token=_signing_credentials.token,
                )
            else:
                return (None, None)
        # Generate the GET URL the client will use to reference the blob in
        # studio_generate after the upload completes.
        get_url = _generate_signed_url(blob)
        return (put_url, get_url)
    except Exception as e:
        print(f"[Storage] create_signed_put_url failed for {blob_path}: {e}")
        return (None, None)


def upload_to_storage(local_path, remote_folder, project_id=None, return_path=False):
    """Uploads a local file to Firebase Storage and returns a time-limited signed URL.
    If return_path=True, returns (url, blob_path) tuple instead of just url."""
    if not bucket or not os.path.exists(local_path):
        return (None, None) if return_path else None

    filename = os.path.basename(local_path)
    path_prefix = f"{remote_folder}/{project_id}" if project_id else remote_folder
    blob_path = f"{path_prefix}/{filename}"
    blob = bucket.blob(blob_path)

    # Upload (separate from URL generation so upload success is preserved)
    try:
        blob.upload_from_filename(local_path)
        print(f"[Storage] Uploaded {local_path} -> {blob_path}")
    except Exception as e:
        print(f"[Storage] Failed to upload {local_path}: {e}")
        return (None, None) if return_path else None

    # Generate signed URL (upload already succeeded at this point)
    url = _generate_signed_url(blob)
    if not url:
        print(f"[Storage] Upload succeeded but signed URL failed for {blob_path}")

    return (url, blob_path) if return_path else url

import urllib.request
import base64 as base64_module
import tempfile
import time
from cryptography.fernet import Fernet

# ── API Key Encryption ──
_ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY")
if not _ENCRYPTION_KEY:
    print("WARNING: ENCRYPTION_KEY not set. Generating a temporary key — "
          "API keys encrypted this session won't be decryptable after restart! "
          "Set ENCRYPTION_KEY env var with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")
    _ENCRYPTION_KEY = Fernet.generate_key().decode()

_fernet = Fernet(_ENCRYPTION_KEY.encode())


def encrypt_api_key(plain_key: str) -> str:
    """Encrypt an API key for storage."""
    return _fernet.encrypt(plain_key.encode()).decode()


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt an API key from storage. Returns None if decryption fails."""
    if not encrypted_key:
        return None
    try:
        return _fernet.decrypt(encrypted_key.encode()).decode()
    except Exception:
        # If it looks like a raw Gemini key (starts with "AI"), treat as legacy plain-text
        if encrypted_key.startswith("AI"):
            logger.warning("Legacy plain-text API key detected — re-save to encrypt")
            return encrypted_key
        # Otherwise decryption genuinely failed (wrong ENCRYPTION_KEY)
        logger.error("Failed to decrypt API key — ENCRYPTION_KEY may have changed. "
                     "User needs to re-save their API key.")
        return None

# ── Safe Error Response ──
_SAFE_ERROR_PATTERNS = re.compile(
    r'rate limit|quota|429|content.*blocked|safety|returned no result|'
    r'resource.?exhausted|overloaded|high demand',
    re.IGNORECASE
)


def safe_error_response(e, status_code=500):
    """Log the full error server-side, return a safe message to the client."""
    logger.exception("Request failed")
    error_str = str(e)
    if _SAFE_ERROR_PATTERNS.search(error_str):
        return jsonify({'error': error_str}), status_code
    return jsonify({'error': 'An internal error occurred. Please try again.'}), status_code


def _load_project_structured(project_id):
    """Return the research_structured object for a project, or None.

    Lets downstream prompt builders cite sources with stable [sN] ids without
    requiring the client to re-send the whole research blob on every request.
    """
    if not project_id:
        return None
    try:
        doc = db.collection('users').document(g.uid).collection('projects').document(project_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        return data.get('research_structured')
    except Exception as e:
        print(f"[Project] Failed to load research_structured for {project_id}: {e}")
        return None


def _load_project_spine(project_id):
    """Return the research_spine object for a project, or None.

    Spine is the ranked-claim narrative outline derived from the dossier;
    downstream prompts cite claims by stable [kN] ids. Returns None when the
    project has no spine (legacy projects, flag disabled, or extraction failed).
    """
    if not project_id:
        return None
    try:
        doc = db.collection('users').document(g.uid).collection('projects').document(project_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        return data.get('research_spine')
    except Exception as e:
        print(f"[Project] Failed to load research_spine for {project_id}: {e}")
        return None


# ── URL Validation (SSRF Protection) ──
_ALLOWED_URL_DOMAINS = {
    'storage.googleapis.com',
    'firebasestorage.googleapis.com',
}


def validate_url(url):
    """Validate URL is from an allowed domain and doesn't resolve to a private IP."""
    if not url or not isinstance(url, str):
        raise ValueError("URL is required")
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        raise ValueError("Only HTTP(S) URLs are allowed")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Invalid URL: no hostname")
    
    is_allowed = any(hostname == d or hostname.endswith('.' + d) for d in _ALLOWED_URL_DOMAINS)
    if not is_allowed:
        raise ValueError(f"URL domain not allowed: {hostname}")
    
    try:
        for info in socket.getaddrinfo(hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                raise ValueError("URL resolves to a private address")
    except socket.gaierror:
        raise ValueError("Could not resolve URL hostname")


# ── Input Validation ──
def validate_input(data, field, field_type=str, required=True, max_length=None, min_val=None, max_val=None):
    """Validate a single input field. Returns (value, error_message)."""
    value = data.get(field)
    if required and (value is None or (isinstance(value, str) and not value.strip())):
        return None, f'{field} is required'
    if value is not None:
        if field_type == str and not isinstance(value, str):
            return None, f'{field} must be a string'
        if field_type == int:
            try:
                value = int(value)
            except (ValueError, TypeError):
                return None, f'{field} must be an integer'
        if field_type == list and not isinstance(value, list):
            return None, f'{field} must be a list'
        if max_length is not None and isinstance(value, (str, list)) and len(value) > max_length:
            return None, f'{field} exceeds maximum length of {max_length}'
        if min_val is not None and isinstance(value, (int, float)) and value < min_val:
            return None, f'{field} must be at least {min_val}'
        if max_val is not None and isinstance(value, (int, float)) and value > max_val:
            return None, f'{field} must be at most {max_val}'
    return value, None


def resolve_image_input(image_input):
    """Accept base64 data URI or allowed Storage URL. Return base64 data URI for Gemini."""
    if not image_input:
        return None
    if image_input.startswith('data:'):
        return image_input
    if image_input.startswith('http'):
        try:
            validate_url(image_input)
            resp = urllib.request.urlopen(image_input)
            raw = resp.read()
            ct = resp.headers.get('Content-Type', 'image/jpeg')
            b64 = base64_module.b64encode(raw).decode('utf-8')
            return f"data:{ct};base64,{b64}"
        except Exception as e:
            print(f"[Resolve] Failed to fetch image from URL (may be expired): {e}")
            return None
    return image_input

def ensure_local_image(image_url):
    """Ensure the image exists locally. If remote, download from allowed domains."""
    filename = image_url.split("/")[-1].split("?")[0]

    # Ensure directory exists before downloading
    os.makedirs(GENERATED_DIR, exist_ok=True)

    image_path = os.path.join(GENERATED_DIR, filename)
    if not os.path.exists(image_path):
        if image_url.startswith("http"):
            try:
                validate_url(image_url)
                print(f"[Storage] Downloading missing local file")
                urllib.request.urlretrieve(image_url, image_path)
            except Exception as e:
                print(f"[Storage] Failed to download image: {e}")
                return None
        else:
            return None
    return image_path


app = Flask(__name__, static_url_path='', static_folder=UI_DIR, template_folder=UI_DIR)

# ── Rate Limiting ──
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

def _rate_limit_key():
    uid = getattr(g, 'uid', None)
    return uid if uid else get_remote_address()

limiter = Limiter(app=app, key_func=_rate_limit_key, storage_uri="memory://", default_limits=[])


# ── Auth Decorator ──
def require_auth(f):
    """Verify Firebase ID token and load user's Gemini API key from Firestore."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid Authorization header'}), 401

        id_token = auth_header.split('Bearer ')[1]
        try:
            decoded_token = auth.verify_id_token(id_token)
            g.uid = decoded_token['uid']
        except Exception as e:
            return jsonify({'error': 'Invalid or expired auth token'}), 401

        # Fetch user's API keys from Firestore (encrypted)
        user_doc = db.collection('users').document(g.uid).get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            stored_key = user_data.get('gemini_api_key')
            g.api_key = decrypt_api_key(stored_key) if stored_key else None
            stored_kie_key = user_data.get('kie_api_key')
            g.kie_api_key = decrypt_api_key(stored_kie_key) if stored_kie_key else None
        else:
            g.api_key = None
            g.kie_api_key = None

        return f(*args, **kwargs)
    return decorated


register_seedance_routes(app, limiter, require_auth, upload_to_storage)

# ── MCP server (Studio tab over OAuth 2.1 + Firebase) ──
from mcp_studio import register_routes as register_mcp_routes
register_mcp_routes(
    app, limiter, require_auth,
    db=db,
    decrypt_api_key=decrypt_api_key,
    upload_to_storage=upload_to_storage,
    create_signed_put_url=create_signed_put_url,
    encryption_key=_ENCRYPTION_KEY,
    firestore_module=firestore,
    encrypt_api_key=encrypt_api_key,
)


@app.route('/')
def index():
    return render_template('index.html')


# ────────────────────────────────────────────────────────────────
#  API KEY MANAGEMENT
# ────────────────────────────────────────────────────────────────

@app.route('/api/save-api-key', methods=['POST'])
@require_auth
@limiter.limit("200/hour")
def save_api_key():
    """Save or update the user's Gemini API key in Firestore."""
    try:
        data = request.json
        api_key = data.get('api_key', '').strip()

        if not api_key:
            return jsonify({'error': 'API key is required'}), 400

        db.collection('users').document(g.uid).set(
            {'gemini_api_key': encrypt_api_key(api_key)}, merge=True
        )

        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/check-api-key', methods=['GET'])
@require_auth
@limiter.limit("200/hour")
def check_api_key():
    """Check if the authenticated user has a Gemini API key saved."""
    has_key = bool(g.api_key)
    return jsonify({'has_key': has_key})


# ────────────────────────────────────────────────────────────────
#  KIE.AI INTEGRATION
# ────────────────────────────────────────────────────────────────

@app.route('/api/kie/save-api-key', methods=['POST'])
@require_auth
@limiter.limit("200/hour")
def kie_save_api_key():
    """Save the user's Kie.ai API key (Fernet encrypted, stored separately from Gemini key)."""
    try:
        data = request.json
        api_key = data.get('api_key', '').strip()
        if not api_key:
            return jsonify({'error': 'API key is required'}), 400
        db.collection('users').document(g.uid).set(
            {'kie_api_key': encrypt_api_key(api_key)}, merge=True
        )
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/kie/check-api-key', methods=['GET'])
@require_auth
@limiter.limit("200/hour")
def kie_check_api_key():
    """Check if the authenticated user has a Kie.ai API key saved."""
    has_key = bool(g.kie_api_key)
    return jsonify({'has_key': has_key})


@app.route('/api/kie/check-credits', methods=['GET'])
@require_auth
@limiter.limit("60/hour")
def kie_check_credits_route():
    """Get the user's remaining Kie.ai credits."""
    if not g.kie_api_key:
        return jsonify({'error': 'No Kie.ai API key configured'}), 400
    result = kie_check_credits(g.kie_api_key)
    return jsonify(result)


@app.route('/api/kie/models', methods=['GET'])
@require_auth
@limiter.limit("200/hour")
def kie_list_models():
    """Return available Kie.ai models with pricing info for frontend display."""
    return jsonify({'models': kie_get_models_info()})


@app.route('/api/kie/upload-image', methods=['POST'])
@require_auth
@limiter.limit("120/hour")
def kie_upload_image_route():
    """Upload an image to Kie.ai for use in I2V/I2I generation.
    Accepts: {image_url: str} (Firebase Storage URL)."""
    if not g.kie_api_key:
        return jsonify({'error': 'No Kie.ai API key configured'}), 400
    data = request.json
    image_url = data.get('image_url', '').strip()
    if not image_url:
        return jsonify({'error': 'image_url is required'}), 400
    # Validate URL is from Firebase Storage (SSRF protection)
    try:
        validate_url(image_url)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    result = kie_upload_image(image_url, g.kie_api_key)
    if not result.get('success'):
        return jsonify({'error': result.get('error', 'Upload failed')}), 500
    return jsonify(result)


@app.route('/api/kie/upload-media', methods=['POST'])
@require_auth
@limiter.limit("60/hour")
def kie_upload_media():
    """Upload a base64 audio or video file to Firebase Storage then to Kie.ai CDN.

    Accepts: {data: 'data:audio/mp3;base64,...', filename: 'clip.mp3', media_type: 'audio'|'video'}
    Returns: {success: bool, url: str}  — the Kie.ai CDN URL ready for ref_audio_urls / ref_video_urls
    """
    if not g.kie_api_key:
        return jsonify({'error': 'No Kie.ai API key configured'}), 400
    try:
        body = request.json
        data_uri = body.get('data', '')
        filename = body.get('filename', 'upload')
        media_type = body.get('media_type', 'audio')  # 'audio' or 'video'

        if not data_uri or not data_uri.startswith('data:'):
            return jsonify({'error': 'Valid base64 data URI is required'}), 400

        header, encoded = data_uri.split(',', 1)
        raw = base64_module.b64decode(encoded)

        # Derive safe extension from MIME or filename
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ('mp3' if media_type == 'audio' else 'mp4')
        safe_name = f"{media_type}_{int(time.time())}_{filename}"

        tmp_dir = tempfile.mkdtemp()
        tmp_path = os.path.join(tmp_dir, safe_name)
        with open(tmp_path, 'wb') as f:
            f.write(raw)

        remote_folder = f"kie_refs/{media_type}"
        firebase_url, _ = upload_to_storage(tmp_path, remote_folder, return_path=True)
        os.unlink(tmp_path)
        os.rmdir(tmp_dir)

        if not firebase_url:
            return jsonify({'error': 'Firebase Storage upload failed'}), 500

        # Re-host via Kie.ai CDN so Kie.ai servers can access the file
        upload_path = f"{'audios' if media_type == 'audio' else 'videos'}/user-uploads"
        kie_result = kie_upload_image(firebase_url, g.kie_api_key, upload_path=upload_path)
        if not kie_result.get('success'):
            return jsonify({'error': kie_result.get('error', 'Kie.ai CDN upload failed')}), 500

        return jsonify({'success': True, 'url': kie_result['url']})
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/kie/generate', methods=['POST'])
@require_auth
@limiter.limit("120/hour")
def kie_generate():
    """Create a Kie.ai generation task.
    Body: {model: str, prompt: str, image_urls?: [str], ...params}
    Returns: {taskId: str, success: bool}"""
    if not g.kie_api_key:
        return jsonify({'error': 'No Kie.ai API key configured'}), 400
    data = request.json
    model = data.get('model', '').strip()
    prompt = data.get('prompt', '').strip()
    image_urls = data.get('image_urls')

    if not model:
        return jsonify({'error': 'model is required'}), 400

    # Extract model-specific params (everything except model, prompt, image_urls, project_id)
    reserved_keys = {'model', 'prompt', 'image_urls', 'project_id'}
    params = {k: v for k, v in data.items() if k not in reserved_keys}

    # Upload ref images/videos/audios to Kie.ai CDN (Seedance multimodal — Firebase URLs need re-hosting).
    # User-uploaded files via /api/kie/upload-media are already on the Kie CDN; this is idempotent for those.
    def _rehost_refs(urls, limit, upload_path):
        out = []
        for u in (urls or [])[:limit]:
            if not u:
                continue
            s = str(u)
            # Skip if already on Kie's CDN
            if 'tempfile.redpandaai.co' in s:
                out.append(s)
                continue
            up = kie_upload_image(s, g.kie_api_key, upload_path=upload_path)
            if up.get('success'):
                out.append(up['url'])
        return out

    if params.get('ref_image_urls'):
        params['ref_image_urls'] = _rehost_refs(params['ref_image_urls'], 9, 'images/user-uploads')
    if params.get('ref_video_urls'):
        params['ref_video_urls'] = _rehost_refs(params['ref_video_urls'], 3, 'videos/user-uploads')
    if params.get('ref_audio_urls'):
        params['ref_audio_urls'] = _rehost_refs(params['ref_audio_urls'], 3, 'audios/user-uploads')

    print(f"[Kie Generate] model={model}, prompt={prompt[:50]}, images={len(image_urls or [])}, params={list(params.keys())}")

    # Midjourney models use separate /mj/ endpoints
    if model.startswith('midjourney-'):
        result = kie_mj_create_task(model, prompt, g.kie_api_key, image_urls=image_urls, **params)
    else:
        result = kie_create_task(model, prompt, g.kie_api_key, image_urls=image_urls, **params)
    print(f"[Kie Generate] result: {result}")
    if not result.get('success'):
        return jsonify({'error': result.get('error', 'Task creation failed')}), 500
    return jsonify(result)


def _rehost_kie_results(result_urls, task_id, project_id, scene_id=None, kind=None):
    """Download Kie tempfile URLs and re-host them to Firebase Storage.

    Critical invariant: never return a kie tempfile URL as if it were durable.
    Kie URLs expire in ~24h; the user's project would die overnight. If every
    retry fails, return ([], failed_kie_urls) so the caller can surface a
    retryable error instead of silently storing a ticking time bomb.

    When scene_id is provided, files land in `images/{pid}/scene_{id}_{ts}.ext`
    (or `videos/{pid}/scene_{id}_{ts}.ext`) so the existing scene-image-history
    scanner finds them — same shape as legacy Gemini uploads.
    """
    firebase_urls = []
    failed = []
    for kie_url in result_urls:
        local_path = None
        # 3 attempts with exponential backoff. Kie's tempfile CDN is sometimes
        # transiently slow, not permanently broken.
        for attempt in range(3):
            local_path = kie_download_result(kie_url, task_id)
            if local_path:
                break
            wait_s = (3 ** attempt)
            print(f"[Kie Rehost] download attempt {attempt + 1} failed for "
                  f"{kie_url[:80]}, retrying in {wait_s}s...")
            time.sleep(wait_s)

        if not local_path:
            print(f"[Kie Rehost] download exhausted retries for {kie_url[:120]}")
            failed.append(kie_url)
            continue

        try:
            is_video = local_path.endswith('.mp4')
            inferred_kind = kind or ('video' if is_video else 'image')
            folder = 'videos' if inferred_kind == 'video' else 'images'
            ext = os.path.splitext(local_path)[1] or ('.mp4' if is_video else '.jpg')

            # Scene-aware filename so /api/visuals/scene-{image,video}-history
            # picks the file up (it scans for `scene_{id}_{ts}.ext` in
            # `{folder}/{project_id}/`). Falls back to legacy `kie_{folder}/`
            # path with random naming when scene_id isn't supplied.
            if scene_id:
                safe_id = str(scene_id).replace('/', '_').replace(' ', '_')
                ts = int(time.time())
                target_name = f"scene_{safe_id}_{ts}{ext}"
                target_path = os.path.join(os.path.dirname(local_path), target_name)
                try:
                    os.rename(local_path, target_path)
                    local_path = target_path
                except OSError as e:
                    print(f"[Kie Rehost] rename failed ({e}); uploading with original name")
            else:
                folder = 'kie_videos' if is_video else 'kie_images'

            firebase_url = None
            for attempt in range(3):
                firebase_url = upload_to_storage(local_path, folder, project_id=project_id)
                if firebase_url:
                    break
                wait_s = (3 ** attempt)
                print(f"[Kie Rehost] upload attempt {attempt + 1} returned None, "
                      f"retrying in {wait_s}s...")
                time.sleep(wait_s)

            if firebase_url:
                firebase_urls.append(firebase_url)
                print(f"[Kie Rehost] persisted: {firebase_url[:120]}")
            else:
                print(f"[Kie Rehost] upload exhausted retries for {kie_url[:80]}")
                failed.append(kie_url)
        finally:
            try:
                os.unlink(local_path)
                os.rmdir(os.path.dirname(local_path))
            except OSError:
                pass

    return firebase_urls, failed


@app.route('/api/kie/poll/<task_id>', methods=['GET'])
@require_auth
@limiter.limit("3600/hour")
def kie_poll(task_id):
    """Poll a Kie.ai task for completion.
    On success, downloads result and uploads to Firebase Storage for persistence.

    Optional query params:
      project_id — for project-scoped storage path
      scene_id   — when set, file is named scene_{id}_{ts} so the history
                   scanner picks it up (parity with legacy Gemini path)
      kind       — 'image' or 'video' (otherwise inferred from extension)
    """
    if not g.kie_api_key:
        return jsonify({'error': 'No Kie.ai API key configured'}), 400

    result = kie_poll_task(task_id, g.kie_api_key)
    print(f"[Kie Poll] task={task_id} status={result.get('status')} urls={len(result.get('result_urls') or [])}")

    if result.get('status') == 'completed' and result.get('result_urls'):
        project_id = request.args.get('project_id')
        scene_id = request.args.get('scene_id')
        kind = request.args.get('kind')
        firebase_urls, failed = _rehost_kie_results(
            result['result_urls'], task_id, project_id,
            scene_id=scene_id, kind=kind,
        )
        if firebase_urls:
            result['firebase_urls'] = firebase_urls
        # If anything failed to persist, flag it so the client can show a
        # retryable error instead of silently storing the expiring kie URL.
        if failed and not firebase_urls:
            result['status'] = 'rehost_failed'
            result['rehost_failed_urls'] = failed
        elif failed:
            result['rehost_partial_failed_urls'] = failed
    elif result.get('status') == 'completed' and not result.get('result_urls'):
        print(f"[Kie Poll] Task completed but NO result_urls found!")

    return jsonify(result)


@app.route('/api/kie/mj/poll/<task_id>', methods=['GET'])
@require_auth
@limiter.limit("3600/hour")
def kie_mj_poll(task_id):
    """Poll a Midjourney task using the dedicated /mj/ endpoint.
    On success, downloads result and uploads to Firebase Storage for persistence."""
    if not g.kie_api_key:
        return jsonify({'error': 'No Kie.ai API key configured'}), 400

    result = kie_mj_poll_task(task_id, g.kie_api_key)
    print(f"[Kie/MJ Poll] task={task_id} status={result.get('status')} urls={len(result.get('result_urls') or [])}")

    if result.get('status') == 'completed' and result.get('result_urls'):
        project_id = request.args.get('project_id')
        scene_id = request.args.get('scene_id')
        kind = request.args.get('kind')
        firebase_urls, failed = _rehost_kie_results(
            result['result_urls'], task_id, project_id,
            scene_id=scene_id, kind=kind,
        )
        if firebase_urls:
            result['firebase_urls'] = firebase_urls
        if failed and not firebase_urls:
            result['status'] = 'rehost_failed'
            result['rehost_failed_urls'] = failed
        elif failed:
            result['rehost_partial_failed_urls'] = failed
    elif result.get('status') == 'completed' and not result.get('result_urls'):
        print(f"[Kie/MJ Poll] Task completed but NO result_urls found!")

    return jsonify(result)


@app.route('/api/kie/mj/upscale', methods=['POST'])
@require_auth
@limiter.limit("120/hour")
def kie_mj_upscale_route():
    """Upscale one of the 4 MJ grid images.
    Body: {taskId: str, imageIndex: 0-3}"""
    if not g.kie_api_key:
        return jsonify({'error': 'No Kie.ai API key configured'}), 400
    data = request.json
    task_id = data.get('taskId', '').strip()
    image_index = data.get('imageIndex')
    if not task_id or image_index is None:
        return jsonify({'error': 'taskId and imageIndex are required'}), 400
    result = kie_mj_upscale(task_id, image_index, g.kie_api_key)
    if not result.get('success'):
        return jsonify({'error': result.get('error', 'Upscale failed')}), 500
    return jsonify(result)


@app.route('/api/kie/mj/vary', methods=['POST'])
@require_auth
@limiter.limit("120/hour")
def kie_mj_vary_route():
    """Create variations of one of the 4 MJ grid images.
    Body: {taskId: str, imageIndex: 1-4}"""
    if not g.kie_api_key:
        return jsonify({'error': 'No Kie.ai API key configured'}), 400
    data = request.json
    task_id = data.get('taskId', '').strip()
    image_index = data.get('imageIndex')
    if not task_id or image_index is None:
        return jsonify({'error': 'taskId and imageIndex are required'}), 400
    result = kie_mj_vary(task_id, image_index, g.kie_api_key)
    if not result.get('success'):
        return jsonify({'error': result.get('error', 'Vary failed')}), 500
    return jsonify(result)


# ────────────────────────────────────────────────────────────────
#  STUDIO — unified model registry & generate dispatcher
# ────────────────────────────────────────────────────────────────

@app.route('/api/studio/models', methods=['GET'])
@require_auth
def studio_list_models():
    """Return the full Studio model registry, grouped by provider.

    The frontend uses this to render the model picker and the dynamic
    parameter form. Schema is the single source of truth — see
    execution/model_schemas.py."""
    return jsonify({
        "providers": studio_provider_groups(),
        "schemas": STUDIO_MODELS,
    })


@app.route('/api/studio/generate', methods=['POST'])
@require_auth
@limiter.limit("600/hour")
def studio_generate():
    """Single dispatch point for every model in the registry.

    Body: {model_id, inputs:{...}, params:{...}, project_id?}

    Routes to the right backend (`google_imagen` / `kie_generic` / etc.)
    based on the schema's `backend` field. The frontend never needs to
    know which underlying API to call."""
    data = request.json or {}
    model_id = (data.get('model_id') or '').strip()
    inputs = data.get('inputs') or {}
    params = data.get('params') or {}
    project_id = data.get('project_id')
    # When the Visuals tab drives Studio Engine for a scene, scene_id lets
    # sync (Google) results land at images/{pid}/scene_{id}_{ts}.png so the
    # history strip picks them up. Async (Kie) flows pass it again in the poll.
    scene_id = data.get('scene_id')

    schema = studio_get_schema(model_id)
    if not schema:
        return jsonify({'error': f'Unknown model: {model_id}'}), 400

    backend = schema['backend']
    print(f"[Studio] model={model_id} backend={backend} kind={schema['kind']} scene={scene_id}")

    try:
        if backend == 'kie_generic':
            return _studio_dispatch_kie_generic(schema, inputs, params, project_id)
        if backend == 'kie_veo3':
            return _studio_dispatch_kie_veo(schema, inputs, params, project_id)
        if backend == 'kie_runway':
            return _studio_dispatch_kie_runway(schema, inputs, params, project_id)
        if backend == 'google_gemini_image':
            return _studio_dispatch_google_image(schema, inputs, params, project_id,
                                                 native=True, scene_id=scene_id)
        if backend == 'google_imagen':
            return _studio_dispatch_google_image(schema, inputs, params, project_id,
                                                 native=False, scene_id=scene_id)
        if backend == 'google_veo':
            return _studio_dispatch_google_veo(schema, inputs, params, project_id)
        if backend == 'google_tts':
            return _studio_dispatch_google_tts(schema, inputs, params, project_id)
        if backend == 'google_lyria':
            return _studio_dispatch_google_lyria(schema, inputs, params, project_id)
        return jsonify({'error': f'Backend not yet implemented: {backend}'}), 501
    except Exception as e:
        return safe_error_response(e)


def _studio_dispatch_kie_generic(schema, inputs, params, project_id):
    """Most Kie market models — hand off to /api/v1/jobs/createTask via kie_create_task."""
    if not g.kie_api_key:
        return jsonify({'error': 'No Kie.ai API key configured'}), 400
    payload = {**inputs, **params}
    prompt = (inputs.get('prompt') or inputs.get('text') or '').strip()
    image_urls = inputs.get('image_input') or inputs.get('image_urls') or []
    if isinstance(image_urls, str):
        image_urls = [image_urls]
    extras = {k: v for k, v in payload.items()
              if k not in {'prompt', 'text', 'image_input', 'image_urls'}}

    # Two Kie models accept a structured array in a field the UI can only ship
    # as a JSON text blob — parse here so the request body matches the docs.
    #   ElevenLabs Dialogue v3 → `dialogue` (array of {text, voice})
    #   Sora 2 Pro Storyboard  → `shots`    (array of {Scene, duration})
    import json as _json
    for _json_field in ('dialogue', 'shots'):
        if _json_field in extras and isinstance(extras[_json_field], str):
            raw = extras[_json_field].strip()
            if raw:
                try:
                    extras[_json_field] = _json.loads(raw)
                except _json.JSONDecodeError as e:
                    return jsonify({'error': f'{_json_field} must be valid JSON: {e}'}), 400

    # ── Re-host Firebase Storage URLs to KIE CDN ──
    # Firebase URLs (firebasestorage.googleapis.com) are behind Firebase auth;
    # KIE servers can't access them.  Upload to KIE's CDN first so the API
    # receives reachable URLs.  This mirrors the rehosting in /api/kie/generate
    # and fixes Seedance 2 character references / multimodal refs in Studio.
    def _rehost_url(url, upload_path='images/user-uploads'):
        """Re-host a single URL to KIE CDN if it isn't already there."""
        if not url or not isinstance(url, str):
            return url
        if 'tempfile.redpandaai.co' in url:
            return url  # already on KIE CDN
        up = kie_upload_image(url, g.kie_api_key, upload_path=upload_path)
        if up.get('success'):
            return up['url']
        print(f"[Studio] KIE rehost failed for {url[:80]}: {up.get('error')}")
        return url  # fallback: pass original, API may still reject

    def _rehost_list(key, limit, upload_path):
        urls = extras.get(key)
        if not urls or not isinstance(urls, list):
            return
        out = []
        for u in urls[:limit]:
            out.append(_rehost_url(u, upload_path))
        extras[key] = out

    # Multimodal ref arrays (Seedance, Wan R2V, HappyHorse R2V, etc.)
    _rehost_list('reference_image_urls', 9, 'images/user-uploads')
    _rehost_list('reference_image', 9, 'images/user-uploads')
    _rehost_list('reference_video_urls', 3, 'videos/user-uploads')
    _rehost_list('reference_video', 3, 'videos/user-uploads')
    _rehost_list('reference_audio_urls', 3, 'audios/user-uploads')
    _rehost_list('image_urls', 14, 'images/user-uploads')
    # Newer field names introduced by the doc-verified sweep:
    #   input_urls — Flux 2 I2I, GPT Image I2I, Wan 2.7 Image, Kling motion-control,
    #                Seedance 1.5 Pro
    #   video_urls — Wan 2.6 V2V/Flash V2V, Kling motion-control
    _rehost_list('input_urls', 16, 'images/user-uploads')
    _rehost_list('video_urls', 3, 'videos/user-uploads')

    # Single-URL image/video/audio inputs across all models. Per the
    # doc-verified sweep these include the new field names: tail_image_url
    # (Kling 2.1 Pro), end_image_url (Hailuo 02 + Seedance v1 Lite),
    # mask_url (Ideogram V3 Edit + character variants).
    for single_key in ('first_frame_url', 'last_frame_url', 'first_frame',
                        'image_url', 'image', 'video_url', 'reference_voice',
                        'driving_audio_url', 'audio_url',
                        'tail_image_url', 'end_image_url', 'mask_url',
                        'first_clip_url'):
        if single_key in extras and isinstance(extras[single_key], str):
            upload_path = 'images/user-uploads'
            if 'video' in single_key or single_key == 'first_clip_url':
                upload_path = 'videos/user-uploads'
            elif 'audio' in single_key or 'voice' in single_key:
                upload_path = 'audios/user-uploads'
            extras[single_key] = _rehost_url(extras[single_key], upload_path)

    # Also rehost top-level image_urls (the primary image input)
    if image_urls:
        image_urls = [_rehost_url(u) for u in image_urls]

    result = kie_create_task(schema['id'], prompt, g.kie_api_key,
                             image_urls=image_urls, **extras)
    if not result.get('success'):
        err = result.get('error', 'Kie task failed')
        # Surface upstream 429 so a batch caller can apply its own backoff.
        # kie_client already retries 3x internally with 2-8s waits; if we
        # land here on a 429 it's a sustained rate violation, not a blip.
        err_lower = str(err).lower()
        if '429' in err_lower or 'rate limit' in err_lower:
            return jsonify({'error': err}), 429
        return jsonify({'error': err}), 500
    return jsonify({**result, 'backend': 'kie_generic'})


def _studio_dispatch_kie_veo(schema, inputs, params, project_id):
    """Kie's Veo 3 wrapper lives under /veo3-api/* with a different request shape
    than generic market models. Until task #8 wires it natively, surface a clear
    error rather than silently mis-routing through /jobs/createTask."""
    if not g.kie_api_key:
        return jsonify({'error': 'No Kie.ai API key configured'}), 400
    return jsonify({
        'error': 'Veo via Kie isn\'t wired in Studio yet — use the Google '
                 'Veo entries (provider: Google) for now, or wait for task #8.'
    }), 501


def _studio_dispatch_kie_runway(schema, inputs, params, project_id):
    """Runway lives under /runway-api/* with its own shape — same situation as Veo."""
    if not g.kie_api_key:
        return jsonify({'error': 'No Kie.ai API key configured'}), 400
    return jsonify({
        'error': 'Runway via Kie isn\'t wired in Studio yet (different endpoint '
                 'shape than market models). Coming in task #8.'
    }), 501


def _studio_dispatch_google_image(schema, inputs, params, project_id, native, scene_id=None):
    """Google's image models — Gemini-native (Nano Banana family) or Imagen.

    Plumbs reference images, count (num_images), and @-mention `prompt_parts`
    through to gemini_client. Returns a list of public URLs in `image_urls`
    plus a back-compat `image_url` for the first result.

    When scene_id is provided, output filenames are renamed to
    `scene_{id}_{ts}.ext` before upload so the scene-image-history endpoint
    discovers them — same behavior as the legacy /api/visuals/generate-image
    path."""
    prompt = (inputs.get('prompt') or '').strip()
    prompt_parts = inputs.get('prompt_parts') or None
    if not prompt and not prompt_parts:
        return jsonify({'error': 'prompt is required'}), 400

    refs = inputs.get('reference_images') or []
    if isinstance(refs, str):
        refs = [refs]
    if (refs or prompt_parts) and not native:
        return jsonify({
            'error': 'Imagen models can\'t use reference images. Pick a Nano Banana variant for image-to-image.'
        }), 400

    # Clamp count against schema's declared range so a hostile/malformed param
    # can't ask for 99 images.
    count = 1
    for p in (schema.get('params') or []):
        if p.get('name') in ('num_images', 'max_images'):
            try:
                want = int(params.get(p['name']) or p.get('default') or 1)
            except (TypeError, ValueError):
                want = 1
            count = max(int(p.get('min', 1)), min(want, int(p.get('max', 4))))
            break

    aspect_ratio = (params.get('aspect_ratio') or '').strip() or None
    image_size = (params.get('image_size') or '').strip() or None

    paths = generate_image_content(
        prompt or '', model_name=schema['id'], api_key=g.api_key,
        uid=g.uid, project_id=project_id,
        reference_images=refs if refs else None,
        prompt_parts=prompt_parts,
        count=count,
        aspect_ratio=aspect_ratio,
        image_size=image_size,
        return_list=True,
    )
    if not paths or (isinstance(paths, str) and paths.startswith('Error')):
        return jsonify({'error': paths or 'Image generation returned no result'}), 500

    image_urls = []
    for p in paths:
        upload_path = p
        if scene_id:
            safe_id = str(scene_id).replace('/', '_').replace(' ', '_')
            ts = int(time.time())
            ext = os.path.splitext(p)[1] or '.png'
            renamed = os.path.join(os.path.dirname(p), f"scene_{safe_id}_{ts}{ext}")
            try:
                os.rename(p, renamed)
                upload_path = renamed
            except OSError as e:
                print(f"[Studio/Google] rename failed ({e}); uploading with original name")
        public_url = upload_to_storage(upload_path, 'images', project_id=project_id)
        image_urls.append(public_url or f'/generated/{os.path.basename(upload_path)}')
    return jsonify({
        'success': True,
        'image_urls': image_urls,
        'image_url': image_urls[0],
        'backend': 'google_gemini_image' if native else 'google_imagen',
    })


def _studio_dispatch_google_veo(schema, inputs, params, project_id):
    """Veo — long-running. Supports T2V, I2V, first→last frame interpolation,
    and reference-image conditioning. All ref slots accept URLs / data URIs /
    local paths; gemini_client resolves them to types.Image."""
    prompt = (inputs.get('prompt') or '').strip()
    if not prompt:
        return jsonify({'error': 'prompt is required'}), 400

    first_frame = inputs.get('first_frame') or None
    last_frame = inputs.get('last_frame') or None
    refs = inputs.get('reference_images') or []
    if isinstance(refs, str):
        refs = [refs]

    if last_frame and not first_frame:
        return jsonify({
            'error': 'last_frame requires first_frame — Veo interpolates between the two.'
        }), 400

    op = start_video_generation(
        image_path=first_frame, prompt=prompt, model_name=schema['id'],
        aspect_ratio=params.get('aspect_ratio') or '16:9',
        duration=int(params.get('duration_seconds') or 6),
        resolution=params.get('resolution') or '720p',
        api_key=g.api_key, uid=g.uid, project_id=project_id,
        last_frame=last_frame,
        reference_images=refs or None,
        negative_prompt=(params.get('negative_prompt') or '').strip() or None,
        seed=params.get('seed'),
        enhance_prompt=params.get('enhance_prompt'),
    )
    return jsonify({'success': True, 'operation': op, 'backend': 'google_veo'})


def _studio_dispatch_google_tts(schema, inputs, params, project_id):
    text = (inputs.get('prompt') or inputs.get('text') or '').strip()
    if not text:
        return jsonify({'error': 'text is required'}), 400
    audio_path = generate_tts(
        text, voice_name=(params.get('voice') or 'Kore').lower(),
        api_key=g.api_key, uid=g.uid, project_id=project_id,
    )
    if not audio_path:
        return jsonify({'error': 'TTS returned no audio'}), 500
    public_url = upload_to_storage(audio_path, 'audio', project_id=project_id)
    return jsonify({
        'success': True,
        'audio_url': public_url or f'/audio/{os.path.basename(audio_path)}',
        'backend': 'google_tts',
    })


def _studio_dispatch_google_lyria(schema, inputs, params, project_id):
    """Lyria 3 — text-to-music with optional mood-image refs.
    Output is mp3 (Clip) or mp3/wav (Pro). Synchronous; not long-running."""
    prompt = (inputs.get('prompt') or '').strip()
    if not prompt:
        return jsonify({'error': 'prompt is required'}), 400

    mood_refs = inputs.get('mood_references') or []
    if isinstance(mood_refs, str):
        mood_refs = [mood_refs]

    output_format = (params.get('output_format') or 'mp3').strip().lower()
    if output_format not in {'mp3', 'wav'}:
        output_format = 'mp3'

    audio_path = generate_music_content(
        prompt, model_name=schema['id'], api_key=g.api_key,
        uid=g.uid, project_id=project_id,
        mood_references=mood_refs or None,
        output_format=output_format,
    )
    if not audio_path or (isinstance(audio_path, str) and audio_path.startswith('Error')):
        return jsonify({'error': audio_path or 'Lyria returned no audio'}), 500

    public_url = upload_to_storage(audio_path, 'audio', project_id=project_id)
    audio_url = public_url or f'/generated/{os.path.basename(audio_path)}'
    return jsonify({
        'success': True,
        'audio_url': audio_url,
        'backend': 'google_lyria',
    })


# ────────────────────────────────────────────────────────────────
#  IMAGE GENERATION
# ────────────────────────────────────────────────────────────────

@app.route('/api/generate-image', methods=['POST'])
@require_auth
@limiter.limit("600/hour")
def generate_image_route():
    try:
        data = request.json
        prompt, err = validate_input(data, 'prompt', max_length=10000)
        if err:
            return jsonify({'error': err}), 400
        model = data.get('model')  # optional: specific model selection

        project_id = data.get('project_id')
        print(f"Generating image for prompt: {prompt} (model: {model or 'auto'})")
        image_path = generate_image_content(prompt, model_name=model, api_key=g.api_key,
                                            uid=g.uid, project_id=project_id)

        if not image_path or (isinstance(image_path, str) and image_path.startswith("Error")):
            return jsonify({'error': image_path or 'Image generation returned no result'}), 500

        public_url = upload_to_storage(image_path, "images", project_id=project_id)
        image_url = public_url if public_url else f'/generated/{os.path.basename(image_path)}'

        return jsonify({'image_url': image_url})

    except Exception as e:
        return safe_error_response(e)


@app.route('/api/upload-reference-image', methods=['POST'])
@require_auth
@limiter.limit("60/hour")
def upload_reference_image():
    """Upload a base64 reference image to Firebase Storage, return public URL."""
    try:
        data = request.json
        image_b64 = data.get('image')
        image_type = data.get('type', 'style')
        project_id = data.get('project_id')
        filename = data.get('filename', 'image.jpg')

        if not image_b64 or not image_b64.startswith('data:'):
            return jsonify({'error': 'Valid base64 data URI is required'}), 400

        header, encoded = image_b64.split(',', 1)
        ext = 'png' if 'png' in header else 'jpg'
        safe_name = f"{image_type}_{int(time.time())}_{filename.rsplit('.', 1)[0]}.{ext}"

        tmp_dir = tempfile.mkdtemp()
        tmp_path = os.path.join(tmp_dir, safe_name)
        tmp = open(tmp_path, 'wb')
        tmp.write(base64_module.b64decode(encoded))
        tmp.close()

        remote_folder = f"references/{project_id}/{image_type}" if project_id else f"references/{image_type}"
        url, blob_path = upload_to_storage(tmp_path, remote_folder, return_path=True)
        os.unlink(tmp_path)
        os.rmdir(tmp_dir)

        if not url:
            return jsonify({'error': 'Failed to upload to storage'}), 500

        return jsonify({'success': True, 'url': url, 'path': blob_path})
    except Exception as e:
        return safe_error_response(e)


def _upload_reference_media(kind, allowed_mime_prefixes, default_ext_map):
    """Shared logic for video/audio reference uploads. Accepts a base64 data URI.

    `kind`: 'video' or 'audio' — used as the storage subfolder.
    `allowed_mime_prefixes`: tuple of MIME prefixes the data URI's header must match.
    `default_ext_map`: { mime_substr: ext } for filename extension inference.
    """
    try:
        data = request.json or {}
        media_b64 = data.get('media')
        project_id = data.get('project_id')
        filename = data.get('filename', f'{kind}.bin')

        if not media_b64 or not media_b64.startswith('data:'):
            return jsonify({'error': 'Valid base64 data URI is required'}), 400
        header, encoded = media_b64.split(',', 1)
        if not any(p in header for p in allowed_mime_prefixes):
            return jsonify({'error': f'Expected a {kind} data URI'}), 400

        ext = next((v for k, v in default_ext_map.items() if k in header), default_ext_map['_default'])
        safe_name = f"{kind}_{int(time.time())}_{filename.rsplit('.', 1)[0]}.{ext}"

        tmp_dir = tempfile.mkdtemp()
        tmp_path = os.path.join(tmp_dir, safe_name)
        with open(tmp_path, 'wb') as tmp:
            tmp.write(base64_module.b64decode(encoded))

        remote_folder = f"references/{project_id}/{kind}" if project_id else f"references/{kind}"
        url, blob_path = upload_to_storage(tmp_path, remote_folder, return_path=True)
        os.unlink(tmp_path)
        os.rmdir(tmp_dir)

        if not url:
            return jsonify({'error': 'Failed to upload to storage'}), 500
        return jsonify({'success': True, 'url': url, 'path': blob_path})
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/upload-reference-video', methods=['POST'])
@require_auth
@limiter.limit("30/hour")
def upload_reference_video():
    """Upload a base64 reference video to Firebase Storage, return public URL."""
    return _upload_reference_media(
        'video',
        allowed_mime_prefixes=('video/',),
        default_ext_map={'mp4': 'mp4', 'webm': 'webm', 'quicktime': 'mov',
                         'mov': 'mov', '_default': 'mp4'},
    )


@app.route('/api/upload-reference-audio', methods=['POST'])
@require_auth
@limiter.limit("30/hour")
def upload_reference_audio():
    """Upload a base64 reference audio file to Firebase Storage, return public URL."""
    return _upload_reference_media(
        'audio',
        allowed_mime_prefixes=('audio/',),
        default_ext_map={'mpeg': 'mp3', 'mp3': 'mp3', 'wav': 'wav',
                         'ogg': 'ogg', 'webm': 'webm', 'm4a': 'm4a',
                         'aac': 'aac', '_default': 'mp3'},
    )


@app.route('/api/refresh-reference-images', methods=['POST'])
@require_auth
def refresh_reference_images():
    """Given blob paths, return fresh signed URLs and base64 data for each.

    Accepts: { paths: ["references/proj/character/file.png", ...] }
    Returns: { images: { "path": { url, data } } }
    """
    try:
        if not bucket:
            return jsonify({'error': 'Firebase Storage not configured'}), 500

        data = request.json
        paths = data.get('paths', [])
        if not paths or not isinstance(paths, list):
            return jsonify({'images': {}})

        # Limit to 20 images per request to prevent abuse
        paths = paths[:20]
        result = {}
        for blob_path in paths:
            if not isinstance(blob_path, str) or not blob_path.startswith('references/'):
                continue
            try:
                blob = bucket.blob(blob_path)
                if not blob.exists():
                    print(f"[Refresh] Blob not found: {blob_path}")
                    continue
                url = _generate_signed_url(blob)
                if not url:
                    print(f"[Refresh] Could not generate signed URL for {blob_path}")
                    continue
                # Also return base64 data so client can use it directly
                raw = blob.download_as_bytes()
                ct = blob.content_type or 'image/jpeg'
                b64 = base64_module.b64encode(raw).decode('utf-8')
                result[blob_path] = {
                    'url': url,
                    'data': f"data:{ct};base64,{b64}"
                }
            except Exception as e:
                print(f"[Refresh] Failed to refresh {blob_path}: {e}")
                continue

        print(f"[Refresh] Refreshed {len(result)}/{len(paths)} reference images")
        return jsonify({'images': result})

    except Exception as e:
        return safe_error_response(e)


@app.route('/generated/<path:filename>')
def serve_generated_file(filename):
    """Serve generated images (local fallback when Storage upload fails)."""
    return send_from_directory(GENERATED_DIR, filename)


# ────────────────────────────────────────────────────────────────
#  TTS GENERATION
# ────────────────────────────────────────────────────────────────

@app.route('/api/generate-tts', methods=['POST'])
@require_auth
@limiter.limit("60/hour")
def generate_tts_route():
    try:
        data = request.json
        text, err = validate_input(data, 'text', max_length=50000)
        if err:
            return jsonify({'error': err}), 400
        voice = data.get('voice', 'kore').lower()
        style_instructions = data.get('style_instructions', '')

        project_id = data.get('project_id')
        print(f"Generating TTS for text ({len(text)} chars), voice={voice}")
        audio_path = generate_tts(text, voice_name=voice, style_instructions=style_instructions,
                                  api_key=g.api_key, uid=g.uid, project_id=project_id)

        if not audio_path or (isinstance(audio_path, str) and audio_path.startswith("Error")):
            return jsonify({'error': audio_path or 'TTS generation returned no result'}), 500

        public_url = upload_to_storage(audio_path, "audio", project_id=project_id)
        audio_url = public_url if public_url else f'/audio/{os.path.basename(audio_path)}'

        return jsonify({'audio_url': audio_url})

    except Exception as e:
        return safe_error_response(e)


@app.route('/audio/<path:filename>')
def serve_audio_file(filename):
    """Serve generated audio (local fallback when Storage upload fails)."""
    return send_from_directory(AUDIO_DIR, filename)


# ────────────────────────────────────────────────────────────────
#  STYLE ANALYSIS (VISION)
# ────────────────────────────────────────────────────────────────

@app.route('/api/analyze-style-images', methods=['POST'])
@require_auth
@limiter.limit("60/hour")
def analyze_style_images_route():
    """
    Analyze visual style from 1-4 uploaded images using Gemini Vision.
    Accepts: { images: [base64_data_uri_1, base64_data_uri_2, ...] }
    Returns: { style_analysis: {style_summary, style_intent, prompt_schema} }
    """
    try:
        data = request.json
        images, err = validate_input(data, 'images', field_type=list, max_length=4)
        if err:
            return jsonify({'error': err}), 400
        if not images:
            return jsonify({'error': 'At least one image is required'}), 400

        # Resolve URLs to base64 if needed (images restored from Firebase Storage)
        images = [resolve_image_input(img) for img in images]

        project_id = data.get('project_id')
        print(f"[Style Analysis] Analyzing {len(images)} images...")
        style_analysis = analyze_style_from_images(
            images, api_key=g.api_key, uid=g.uid, project_id=project_id,
        )

        if not style_analysis or (isinstance(style_analysis, str) and style_analysis.startswith("Error")):
            return jsonify({'error': style_analysis or 'Style analysis returned no result'}), 500

        summary = style_analysis.get('style_summary', '') if isinstance(style_analysis, dict) else str(style_analysis)[:100]
        print(f"[Style Analysis] Complete: {summary}")
        return jsonify({
            'success': True,
            'style_analysis': style_analysis
        })

    except Exception as e:
        return safe_error_response(e)


@app.route('/api/analyze-style-text', methods=['POST'])
@require_auth
@limiter.limit("60/hour")
def analyze_style_text_route():
    """
    Analyze visual style from a free-text description.
    Accepts: { description: "2D cartoon, bright colors, simple backgrounds" }
    Returns: { style_analysis: {style_summary, style_intent, prompt_schema} }
    """
    try:
        data = request.json
        description = data.get('description', '').strip()

        if not description:
            return jsonify({'error': 'Style description is required'}), 400

        project_id = data.get('project_id')
        print(f"[Style Analysis from Text] Analyzing: '{description[:80]}...'")
        style_analysis = analyze_style_from_text(
            description, api_key=g.api_key, uid=g.uid, project_id=project_id,
        )

        if not style_analysis or (isinstance(style_analysis, str) and style_analysis.startswith("Error")):
            return jsonify({'error': style_analysis or 'Style analysis returned no result'}), 500

        summary = style_analysis.get('style_summary', '') if isinstance(style_analysis, dict) else str(style_analysis)[:100]
        print(f"[Style Analysis from Text] Complete: {summary}")
        return jsonify({
            'success': True,
            'style_analysis': style_analysis
        })

    except Exception as e:
        return safe_error_response(e)


# ────────────────────────────────────────────────────────────────
#  CAST SUGGESTION
# ────────────────────────────────────────────────────────────────

@app.route('/api/structure-script', methods=['POST'])
@require_auth
@limiter.limit("60/hour")
def structure_script_route():
    """Structure a pasted plain-text script into acts/beats without losing words.

    Architecture: the LLM never re-emits user text. We deterministically split
    the paste into chunks, ask the LLM only for act/beat labels keyed by chunk
    index, then reconstruct the narration by zipping verbatim chunks back to
    those labels. A whitespace-normalized equality check guarantees zero loss;
    any failure falls back to deterministic labeling so the user is never
    blocked.

    Accepts: { raw_text, duration_minutes }
    Returns: { success, narration, structuring_mode: "llm" | "fallback" }
    """
    import json as _json
    import re as _re

    try:
        data = request.json
        raw_text = data.get('raw_text', '').strip()
        duration_minutes = data.get('duration_minutes', 10)

        if not raw_text:
            return jsonify({'error': 'No script text provided'}), 400

        from research_templates import build_script_structuring_prompt
        from research_scriptwriter import split_script_into_chunks

        def _normalize(s):
            return _re.sub(r'\s+', ' ', s or '').strip()

        def _default_title(text):
            words = text.strip().split()
            return ' '.join(words[:8]) if words else 'Imported Script'

        def _deterministic_narration(chunks, reason):
            print(f"[Script Structure] fell back to deterministic labeling: {reason}")
            beats = [
                {'act': 'ACT 1', 'beat': f'Beat {i + 1}', 'text': chunk}
                for i, chunk in enumerate(chunks)
            ]
            return {
                'title': _default_title(chunks[0]) if chunks else 'Imported Script',
                'duration_minutes': duration_minutes,
                'narration': beats,
            }

        chunks = split_script_into_chunks(raw_text)
        if not chunks:
            return jsonify({'error': 'Script appears to be empty after parsing'}), 400

        print(f"[Script Structure] Split {len(raw_text.split())} words into {len(chunks)} chunks")

        # Single-chunk paste → no need to consult the LLM.
        if len(chunks) <= 1:
            narration = {
                'title': _default_title(chunks[0]),
                'duration_minutes': duration_minutes,
                'narration': [{'act': 'ACT 1', 'beat': 'Full Script', 'text': chunks[0]}],
            }
            return jsonify({
                'success': True,
                'narration': narration,
                'structuring_mode': 'llm',  # trivial path is still authoritative
            })

        # Too many chunks for a single labeler call — go deterministic to keep
        # the LLM response bounded and avoid token-limit truncation.
        MAX_CHUNKS_FOR_LLM = 200
        if len(chunks) > MAX_CHUNKS_FOR_LLM:
            narration = _deterministic_narration(chunks, f'{len(chunks)} chunks exceeds LLM cap')
            return jsonify({'success': True, 'narration': narration, 'structuring_mode': 'fallback'})

        prompt = build_script_structuring_prompt(chunks=chunks, duration_minutes=duration_minutes)
        raw_response = generate_content(
            prompt, model_name="gemini-3.1-flash-lite",
            temperature=0.2, api_key=g.api_key,
            uid=g.uid, project_id=data.get('project_id'),
            description="structure_script",
        )

        labels_by_index = {}
        title = None
        llm_ok = True

        if not raw_response or (isinstance(raw_response, str) and raw_response.startswith("Error")):
            llm_ok = False
        else:
            cleaned = raw_response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
            try:
                parsed = _json.loads(cleaned)
                title = parsed.get('title') if isinstance(parsed.get('title'), str) else None
                for lab in parsed.get('labels', []) or []:
                    if not isinstance(lab, dict):
                        continue
                    idx = lab.get('index')
                    act = lab.get('act')
                    beat = lab.get('beat')
                    if (isinstance(idx, int) and 0 <= idx < len(chunks)
                            and isinstance(act, str) and act.strip()
                            and isinstance(beat, str) and beat.strip()):
                        labels_by_index[idx] = (act.strip(), beat.strip())
            except (_json.JSONDecodeError, ValueError, TypeError) as parse_err:
                print(f"[Script Structure] LLM JSON parse error: {parse_err}")
                llm_ok = False

        # If LLM produced nothing usable, deterministic fallback.
        if not llm_ok or not labels_by_index:
            narration = _deterministic_narration(chunks, 'LLM returned no usable labels')
            return jsonify({'success': True, 'narration': narration, 'structuring_mode': 'fallback'})

        # Reconstruct: verbatim chunk text + per-index labels (default-filling any gaps).
        reconstructed = []
        for i, chunk in enumerate(chunks):
            act, beat = labels_by_index.get(i, ('ACT 1', f'Beat {i + 1}'))
            reconstructed.append({'act': act, 'beat': beat, 'text': chunk})

        # Merge consecutive entries sharing (act, beat).
        merged = []
        for entry in reconstructed:
            if merged and merged[-1]['act'] == entry['act'] and merged[-1]['beat'] == entry['beat']:
                merged[-1]['text'] = merged[-1]['text'] + '\n\n' + entry['text']
            else:
                merged.append(dict(entry))

        # Equality assertion: joined beat text == input (whitespace-normalized).
        joined = '\n\n'.join(b['text'] for b in merged)
        if _normalize(joined) != _normalize(raw_text):
            narration = _deterministic_narration(chunks, 'equality check failed after reconstruction')
            return jsonify({'success': True, 'narration': narration, 'structuring_mode': 'fallback'})

        narration = {
            'title': title or _default_title(chunks[0]),
            'duration_minutes': duration_minutes,
            'narration': merged,
        }
        act_count = len({b['act'] for b in merged})
        print(f"[Script Structure] Complete: {act_count} acts, {len(merged)} beats (mode=llm)")
        return jsonify({'success': True, 'narration': narration, 'structuring_mode': 'llm'})

    except Exception as e:
        return safe_error_response(e)


@app.route('/api/suggest-cast', methods=['POST'])
@require_auth
@limiter.limit("60/hour")
def suggest_cast_route():
    """
    Analyze the finalized script and suggest a cast of characters.
    Accepts: { narration_json: {...}, character_description: "...", rendering_split: "unified" }
    Returns: { cast_data: {title, has_characters, cast: [...], casting_notes} }
    """
    try:
        data = request.json
        narration_json = data.get('narration_json')
        character_description = data.get('character_description', '')
        rendering_split = data.get('rendering_split', 'unified')
        creative_direction = data.get('creative_direction')
        style_analysis = data.get('style_analysis') or {}
        style_summary = style_analysis.get('style_summary', '') if isinstance(style_analysis, dict) else ''

        if not narration_json or not narration_json.get('narration'):
            return jsonify({'error': 'Narration data with beats is required'}), 400

        from research_templates import build_cast_suggestion_prompt

        print(f"[Cast Suggestion] Analyzing script for characters (style={'yes' if style_summary else 'none'})...")
        prompt = build_cast_suggestion_prompt(
            narration_json=narration_json,
            character_description=character_description,
            rendering_split=rendering_split,
            creative_direction=creative_direction,
            style_summary=style_summary,
        )

        raw_response = generate_content(
            prompt, model_name="gemini-3-flash-preview",
            temperature=0.3, api_key=g.api_key,
            uid=g.uid, project_id=data.get('project_id'),
            description="suggest_cast",
        )

        if not raw_response or (isinstance(raw_response, str) and raw_response.startswith("Error")):
            return jsonify({'error': raw_response or 'Cast suggestion returned no result'}), 500

        # Parse JSON response
        import json
        # Strip markdown code fences if present
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()

        full_data = json.loads(cleaned)
        cast_count = len(full_data.get('cast', []))
        has_chars = full_data.get('has_characters', cast_count > 0)

        # Split the LLM response into cast_data and locations_data so the
        # frontend can render them in their own panels independently.
        cast_data = {
            'title': full_data.get('title', ''),
            'has_characters': has_chars,
            'total_beats': full_data.get('total_beats', 0),
            'cast': full_data.get('cast', []),
            'casting_notes': full_data.get('casting_notes', ''),
        }

        locations_list = full_data.get('locations') or []
        has_locations = full_data.get('has_locations', len(locations_list) > 0)
        locations_data = {
            'has_locations': has_locations,
            'locations': locations_list,
            'location_notes': full_data.get('location_notes', ''),
        }

        loc_count = len(locations_list)
        print(f"[Cast Suggestion] Complete: {cast_count} characters, {loc_count} locations, "
              f"has_characters={has_chars}, has_locations={has_locations}")

        return jsonify({
            'success': True,
            'cast_data': cast_data,
            'locations_data': locations_data,
        })

    except json.JSONDecodeError as e:
        print(f"[Cast Suggestion] JSON parse error: {e}")
        return jsonify({'error': f'Failed to parse cast suggestion response: {e}'}), 500
    except Exception as e:
        return safe_error_response(e)


# ────────────────────────────────────────────────────────────────
#  CAST PORTRAIT GENERATION
# ────────────────────────────────────────────────────────────────

@app.route('/api/generate-cast-portrait', methods=['POST'])
@require_auth
@limiter.limit("600/hour")
def generate_cast_portrait():
    """Generate a portrait image for a cast member (face closeup or full body)."""
    try:
        data = request.json
        prompt, err = validate_input(data, 'prompt', max_length=10000)
        if err:
            return jsonify({'error': err}), 400

        portrait_type = data.get('portrait_type', 'reference_sheet')
        character_name = data.get('character_name', 'Unknown')
        project_id = data.get('project_id')

        if portrait_type not in ('reference_sheet', 'face_closeup', 'full_body'):
            return jsonify({'error': 'portrait_type must be reference_sheet, face_closeup, or full_body'}), 400
        if not project_id:
            return jsonify({'error': 'project_id is required'}), 400

        model = data.get('model', 'gemini-3-pro-image-preview')
        # Ensure we use a Gemini model (Imagen doesn't support style refs)
        if model.startswith('imagen-'):
            model = 'gemini-3-pro-image-preview'

        if portrait_type == 'reference_sheet':
            aspect_ratio = '16:9'
        elif portrait_type == 'face_closeup':
            aspect_ratio = '1:1'
        else:
            aspect_ratio = '9:16'

        style_images = [r for r in (resolve_image_input(img) for img in data.get('style_images', []) if img) if r]
        style_mode = data.get('style_mode', 'art_only')
        style_summary = data.get('style_summary', '')

        safe_name = ''.join(c if c.isalnum() or c in ('-', '_') else '_' for c in character_name.lower())
        scene_id = f"portrait_{safe_name}_{portrait_type}"

        print(f"[Cast Portrait] Generating {portrait_type} for '{character_name}' "
              f"(model={model}, {len(style_images)} style refs)")

        result = generate_scene_image(
            prompt=prompt,
            model_name=model,
            aspect_ratio=aspect_ratio,
            resolution='2K',
            style_images=style_images or None,
            characters=None,
            character_images=None,
            additional_context=style_summary,
            style_mode=style_mode,
            scene_id=scene_id,
            api_key=g.api_key,
            uid=g.uid, project_id=project_id,
        )

        if "error" in result:
            return jsonify({'error': result['error'], 'portrait_type': portrait_type, 'character_name': character_name}), 500

        # Upload to Firebase Storage under references path
        if result.get("success") and "local_path" in result:
            url, blob_path = upload_to_storage(
                result["local_path"],
                f"references/{project_id}/character",
                return_path=True
            )
            if url:
                result["image_url"] = url
                result["blob_path"] = blob_path
            del result["local_path"]

        result["portrait_type"] = portrait_type
        result["character_name"] = character_name
        return jsonify(result)

    except Exception as e:
        return safe_error_response(e)


@app.route('/api/generate-cast-portraits-batch', methods=['POST'])
@require_auth
@limiter.limit("60/hour")
def generate_cast_portraits_batch():
    """Generate portraits for all cast members (2 images each: face closeup + full body)."""
    try:
        data = request.json
        cast = data.get('cast', [])
        if not cast:
            return jsonify({'error': 'cast array is required'}), 400

        project_id = data.get('project_id')
        if not project_id:
            return jsonify({'error': 'project_id is required'}), 400

        model = data.get('model', 'gemini-3-pro-image-preview')
        if model.startswith('imagen-'):
            model = 'gemini-3-pro-image-preview'

        style_images = [r for r in (resolve_image_input(img) for img in data.get('style_images', []) if img) if r]
        style_mode = data.get('style_mode', 'art_only')
        style_summary = data.get('style_summary', '')
        api_key = g.api_key
        tracking_uid = g.uid

        def generate_one_portrait(char_name, prompt, portrait_type):
            safe_name = ''.join(c if c.isalnum() or c in ('-', '_') else '_' for c in char_name.lower())
            scene_id = f"portrait_{safe_name}_{portrait_type}"
            if portrait_type == 'reference_sheet':
                aspect_ratio = '16:9'
            elif portrait_type == 'face_closeup':
                aspect_ratio = '1:1'
            else:
                aspect_ratio = '9:16'

            res = generate_scene_image(
                prompt=prompt,
                model_name=model,
                aspect_ratio=aspect_ratio,
                resolution='2K',
                style_images=style_images or None,
                characters=None,
                character_images=None,
                additional_context=style_summary,
                style_mode=style_mode,
                scene_id=scene_id,
                api_key=api_key,
                uid=tracking_uid, project_id=project_id,
            )

            if res.get("success") and "local_path" in res:
                url, blob_path = upload_to_storage(
                    res["local_path"],
                    f"references/{project_id}/character",
                    return_path=True
                )
                if url:
                    res["image_url"] = url
                    res["blob_path"] = blob_path
                if "local_path" in res:
                    del res["local_path"]

            res["portrait_type"] = portrait_type
            res["character_name"] = char_name
            return res

        # Build list of portrait jobs — one per character (reference_sheet, fallback to face_closeup)
        jobs = []
        for char in cast:
            name = char.get('name', 'Unknown')
            prompts = char.get('portrait_prompts', {})
            if prompts.get('reference_sheet'):
                jobs.append((name, prompts['reference_sheet'], 'reference_sheet'))
            elif prompts.get('face_closeup'):
                jobs.append((name, prompts['face_closeup'], 'face_closeup'))
            elif prompts.get('full_body'):
                jobs.append((name, prompts['full_body'], 'full_body'))

        if not jobs:
            return jsonify({'error': 'No portrait prompts found in cast data'}), 400

        print(f"[Cast Portrait] Batch generating {len(jobs)} reference sheets for {len(cast)} characters")

        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(generate_one_portrait, *job): job for job in jobs}
            for future in as_completed(futures):
                try:
                    res = future.result()
                    results.append(res)
                except Exception as exc:
                    job = futures[future]
                    results.append({
                        "error": str(exc),
                        "character_name": job[0],
                        "portrait_type": job[2]
                    })

        # Group results by character
        grouped = {}
        for res in results:
            name = res.get('character_name', 'Unknown')
            ptype = res.get('portrait_type', '')
            if name not in grouped:
                grouped[name] = {"character_name": name}
            grouped[name][ptype] = {
                "success": res.get("success", False),
                "image_url": res.get("image_url"),
                "blob_path": res.get("blob_path"),
                "error": res.get("error"),
            }

        success_count = sum(1 for r in results if r.get('success'))
        print(f"[Cast Portrait] Batch complete: {success_count}/{len(jobs)} succeeded")

        return jsonify({'results': list(grouped.values())})

    except Exception as e:
        return safe_error_response(e)


# ────────────────────────────────────────────────────────────────
#  LOCATION REFERENCE GENERATION
# ────────────────────────────────────────────────────────────────

@app.route('/api/generate-location-reference', methods=['POST'])
@require_auth
@limiter.limit("600/hour")
def generate_location_reference():
    """Generate a 2x3 reference grid image for a location."""
    try:
        data = request.json
        prompt, err = validate_input(data, 'prompt', max_length=10000)
        if err:
            return jsonify({'error': err}), 400

        location_name = data.get('location_name', 'Unknown')
        project_id = data.get('project_id')
        if not project_id:
            return jsonify({'error': 'project_id is required'}), 400

        model = data.get('model', 'gemini-3-pro-image-preview')
        if model.startswith('imagen-'):
            model = 'gemini-3-pro-image-preview'

        style_images = [r for r in (resolve_image_input(img) for img in data.get('style_images', []) if img) if r]
        style_mode = data.get('style_mode', 'art_only')
        style_summary = data.get('style_summary', '')

        safe_name = ''.join(c if c.isalnum() or c in ('-', '_') else '_' for c in location_name.lower())
        scene_id = f"location_{safe_name}_reference"

        print(f"[Location Reference] Generating reference grid for '{location_name}' "
              f"(model={model}, {len(style_images)} style refs)")

        result = generate_scene_image(
            prompt=prompt,
            model_name=model,
            aspect_ratio='16:9',
            resolution='2K',
            style_images=style_images or None,
            characters=None,
            character_images=None,
            additional_context=style_summary,
            style_mode=style_mode,
            scene_id=scene_id,
            api_key=g.api_key,
            uid=g.uid, project_id=project_id,
        )

        if "error" in result:
            return jsonify({'error': result['error'], 'location_name': location_name}), 500

        if result.get("success") and "local_path" in result:
            url, blob_path = upload_to_storage(
                result["local_path"],
                f"references/{project_id}/location",
                return_path=True
            )
            if url:
                result["image_url"] = url
                result["blob_path"] = blob_path
            del result["local_path"]

        result["location_name"] = location_name
        return jsonify(result)

    except Exception as e:
        return safe_error_response(e)


@app.route('/api/generate-location-references-batch', methods=['POST'])
@require_auth
@limiter.limit("60/hour")
def generate_location_references_batch():
    """Generate reference grids for all locations in parallel."""
    try:
        data = request.json
        locations = data.get('locations', [])
        if not locations:
            return jsonify({'error': 'locations array is required'}), 400

        project_id = data.get('project_id')
        if not project_id:
            return jsonify({'error': 'project_id is required'}), 400

        model = data.get('model', 'gemini-3-pro-image-preview')
        if model.startswith('imagen-'):
            model = 'gemini-3-pro-image-preview'

        style_images = [r for r in (resolve_image_input(img) for img in data.get('style_images', []) if img) if r]
        style_mode = data.get('style_mode', 'art_only')
        style_summary = data.get('style_summary', '')
        api_key = g.api_key
        tracking_uid = g.uid

        def generate_one_location(loc_name, prompt):
            safe_name = ''.join(c if c.isalnum() or c in ('-', '_') else '_' for c in loc_name.lower())
            scene_id = f"location_{safe_name}_reference"

            res = generate_scene_image(
                prompt=prompt,
                model_name=model,
                aspect_ratio='16:9',
                resolution='2K',
                style_images=style_images or None,
                characters=None,
                character_images=None,
                additional_context=style_summary,
                style_mode=style_mode,
                scene_id=scene_id,
                api_key=api_key,
                uid=tracking_uid, project_id=project_id,
            )

            if res.get("success") and "local_path" in res:
                url, blob_path = upload_to_storage(
                    res["local_path"],
                    f"references/{project_id}/location",
                    return_path=True
                )
                if url:
                    res["image_url"] = url
                    res["blob_path"] = blob_path
                if "local_path" in res:
                    del res["local_path"]

            res["location_name"] = loc_name
            return res

        jobs = []
        for loc in locations:
            name = loc.get('name', 'Unknown')
            prompt = loc.get('reference_sheet_prompt') or loc.get('prompt')
            if prompt:
                jobs.append((name, prompt))

        if not jobs:
            return jsonify({'error': 'No reference prompts found in locations data'}), 400

        print(f"[Location Reference] Batch generating {len(jobs)} reference grids")

        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(generate_one_location, *job): job for job in jobs}
            for future in as_completed(futures):
                try:
                    res = future.result()
                    results.append(res)
                except Exception as exc:
                    job = futures[future]
                    results.append({
                        "error": str(exc),
                        "location_name": job[0],
                    })

        grouped = {}
        for res in results:
            name = res.get('location_name', 'Unknown')
            grouped[name] = {
                "location_name": name,
                "reference_sheet": {
                    "success": res.get("success", False),
                    "image_url": res.get("image_url"),
                    "blob_path": res.get("blob_path"),
                    "error": res.get("error"),
                }
            }

        success_count = sum(1 for r in results if r.get('success'))
        print(f"[Location Reference] Batch complete: {success_count}/{len(jobs)} succeeded")

        return jsonify({'results': list(grouped.values())})

    except Exception as e:
        return safe_error_response(e)


# ────────────────────────────────────────────────────────────────
#  UPLOADED REFERENCE ANALYSIS + RESTYLE
# ────────────────────────────────────────────────────────────────

@app.route('/api/analyze-uploaded-reference', methods=['POST'])
@require_auth
@limiter.limit("120/hour")
def analyze_uploaded_reference():
    """Analyze a user-uploaded reference image. Returns identity_text +
    style_summary + style_mismatch flag (vs project's approved style)."""
    try:
        data = request.json
        image_url = data.get('image_url')
        image_b64 = data.get('image_b64')
        kind = data.get('kind', 'character')
        approved_style_summary = (data.get('style_summary') or '').strip()

        image_data = image_b64 or image_url
        if not image_data:
            return jsonify({'error': 'image_url or image_b64 is required'}), 400
        if kind not in ('character', 'location'):
            return jsonify({'error': "kind must be 'character' or 'location'"}), 400

        result = analyze_image_for_identity(
            image_data=image_data,
            kind=kind,
            api_key=g.api_key,
            uid=g.uid,
            project_id=data.get('project_id'),
        )

        if isinstance(result, str) and result.startswith("Error"):
            return jsonify({'error': result}), 500

        identity_text = (result.get('identity_text') or '').strip()
        upload_style_summary = (result.get('style_summary') or '').strip()

        # Keyword-overlap heuristic — fewer than 30% of meaningful tokens shared
        # is treated as a mismatch. False positives are acceptable because the
        # user can dismiss the warning by toggling active ref.
        style_mismatch = False
        if approved_style_summary and upload_style_summary:
            def _tokens(s):
                return set(t for t in ''.join(c if c.isalnum() or c.isspace() else ' '
                                              for c in s.lower()).split()
                           if len(t) > 3)
            a = _tokens(approved_style_summary)
            b = _tokens(upload_style_summary)
            if a and b:
                overlap = len(a & b)
                style_mismatch = (overlap / max(len(a), len(b))) < 0.3

        return jsonify({
            'success': True,
            'identity_text': identity_text,
            'style_summary': upload_style_summary,
            'style_mismatch': style_mismatch,
        })

    except Exception as e:
        return safe_error_response(e)


@app.route('/api/restyle-reference', methods=['POST'])
@require_auth
@limiter.limit("60/hour")
def restyle_reference():
    """Regenerate a reference (cast portrait or location grid) in the project's
    style, using the uploaded image's identity/description text as the subject.
    Returns the new generated ref URL. The original upload is untouched."""
    try:
        data = request.json
        kind = data.get('kind', 'character')
        name = data.get('name', 'Unknown')
        identity_text = (data.get('identity_text') or '').strip()
        project_id = data.get('project_id')

        if kind not in ('character', 'location'):
            return jsonify({'error': "kind must be 'character' or 'location'"}), 400
        if not identity_text:
            return jsonify({'error': 'identity_text is required'}), 400
        if not project_id:
            return jsonify({'error': 'project_id is required'}), 400

        model = data.get('model', 'gemini-3-pro-image-preview')
        if model.startswith('imagen-'):
            model = 'gemini-3-pro-image-preview'

        style_images = [r for r in (resolve_image_input(img) for img in data.get('style_images', []) if img) if r]
        style_mode = data.get('style_mode', 'art_only')
        style_summary = (data.get('style_summary') or '').strip()
        style_prefix = f"{style_summary}. " if style_summary else ""

        if kind == 'character':
            prompt = (
                f"{style_prefix}Create a professional character reference sheet for {name}: "
                f"{identity_text}. Use a clean, neutral plain background. Arrange in two "
                f"horizontal rows: Top row: four full-body standing views side-by-side — "
                f"front view, left profile (facing left), right profile (facing right), back "
                f"view. Bottom row: three highly detailed close-up portraits — front portrait, "
                f"left profile (facing left), right profile (facing right). Maintain perfect "
                f"identity consistency. Relaxed A-pose, consistent scale. Even spacing, clean "
                f"panel separation. Consistent lighting. Crisp, print-ready."
            )
            folder = f"references/{project_id}/character"
            safe_name = ''.join(c if c.isalnum() or c in ('-', '_') else '_' for c in name.lower())
            scene_id = f"portrait_{safe_name}_reference_sheet"
        else:
            prompt = (
                f"{style_prefix}Create a 2x3 reference grid for the location \"{name}\": "
                f"{identity_text}. Six panels arranged in two rows of three. Choose six diverse "
                f"angles that best capture this specific location. Maintain perfect spatial and "
                f"lighting consistency across all six panels. Clean panel separation, even spacing."
            )
            folder = f"references/{project_id}/location"
            safe_name = ''.join(c if c.isalnum() or c in ('-', '_') else '_' for c in name.lower())
            scene_id = f"location_{safe_name}_reference"

        print(f"[Restyle] Generating restyled {kind} reference for '{name}'")

        result = generate_scene_image(
            prompt=prompt,
            model_name=model,
            aspect_ratio='16:9',
            resolution='2K',
            style_images=style_images or None,
            characters=None,
            character_images=None,
            additional_context=style_summary,
            style_mode=style_mode,
            scene_id=scene_id,
            api_key=g.api_key,
            uid=g.uid, project_id=project_id,
        )

        if "error" in result:
            return jsonify({'error': result['error']}), 500

        if result.get("success") and "local_path" in result:
            url, blob_path = upload_to_storage(result["local_path"], folder, return_path=True)
            if url:
                result["image_url"] = url
                result["blob_path"] = blob_path
            del result["local_path"]

        result["kind"] = kind
        result["name"] = name
        return jsonify(result)

    except Exception as e:
        return safe_error_response(e)


# ────────────────────────────────────────────────────────────────
#  CREATIVE DIRECTION
# ────────────────────────────────────────────────────────────────

@app.route('/api/expand-creative-direction', methods=['POST'])
@require_auth
@limiter.limit("60/hour")
def expand_creative_direction_route():
    """
    Expand user's free-form creative direction into structured guidance + style defaults.
    Accepts: { direction: "stick figure explainer", narration_context: {...} }
    Returns: { creative_direction: {direction_summary, ..., suggested_style_defaults} }
    """
    try:
        data = request.json
        direction = data.get('direction', '').strip()
        narration_context = data.get('narration_context')

        if not direction:
            return jsonify({'error': 'Creative direction description is required'}), 400

        print(f"[Creative Direction] Expanding: '{direction[:80]}...'")
        result = expand_creative_direction(
            user_direction=direction,
            narration_context=narration_context,
            api_key=g.api_key,
            uid=g.uid, project_id=data.get('project_id'),
        )

        if isinstance(result, str) and result.startswith("Error"):
            return jsonify({'error': result}), 500

        print(f"[Creative Direction] Expanded: {result.get('direction_summary', '')[:80]}")
        return jsonify({'success': True, 'creative_direction': result})

    except Exception as e:
        return safe_error_response(e)


@app.route('/api/refine-creative-direction', methods=['POST'])
@require_auth
@limiter.limit("60/hour")
def refine_creative_direction_route():
    """
    Refine an already-expanded creative direction based on user feedback.
    Accepts: { current_direction: {...}, feedback: "make it more playful", narration_context: {...} }
    Returns: { creative_direction: {direction_summary, ..., suggested_style_defaults} }
    """
    try:
        data = request.json
        current = data.get('current_direction')
        feedback = data.get('feedback', '').strip()
        narration_context = data.get('narration_context')

        if not current:
            return jsonify({'error': 'Current direction is required'}), 400
        if not feedback:
            return jsonify({'error': 'Feedback is required'}), 400

        print(f"[Creative Direction] Refining with feedback: '{feedback[:80]}...'")
        result = refine_creative_direction(
            current_direction=current,
            user_feedback=feedback,
            narration_context=narration_context,
            api_key=g.api_key,
            uid=g.uid, project_id=data.get('project_id'),
        )

        if isinstance(result, str) and result.startswith("Error"):
            return jsonify({'error': result}), 500

        print(f"[Creative Direction] Refined: {result.get('direction_summary', '')[:80]}")
        return jsonify({'success': True, 'creative_direction': result})

    except Exception as e:
        return safe_error_response(e)


# ────────────────────────────────────────────────────────────────
#  RESEARCH & SCRIPT WRITING
# ────────────────────────────────────────────────────────────────

@app.route('/api/templates', methods=['GET'])
@require_auth
@limiter.limit("200/hour")
def list_templates():
    """Return all available research/script templates."""
    return jsonify({'templates': get_all_templates_metadata()})


@app.route('/api/script-options', methods=['GET'])
@require_auth
@limiter.limit("200/hour")
def get_script_options():
    """Return all available audience profiles, tones, format presets, and viewer outcomes for the UI."""
    return jsonify({
        'audiences': [{"id": k, "label": v["label"]} for k, v in AUDIENCE_PROFILES.items()],
        'tones': [{"id": k, "label": v["label"]} for k, v in TONE_DEFINITIONS.items()],
        'format_presets': [{"id": k, "label": v["label"], "duration_minutes": v.get("duration_minutes")} for k, v in FORMAT_PRESETS.items()],
        'viewer_outcomes': [{"id": k, "label": v["label"]} for k, v in VIEWER_OUTCOMES.items()],
    })


@app.route('/api/research', methods=['POST'])
@require_auth
@limiter.limit("30/hour")
def run_research():
    """
    Conduct research using Gemini as the research engine.
    Accepts: topic, template_id
    Returns: structured research dossier

    Note: This uses Gemini directly for research synthesis.
    NotebookLM integration happens at the agent/MCP level for
    deeper research when called by the AI assistant.
    """
    try:
        data = request.json
        topic, err = validate_input(data, 'topic', max_length=500)
        if err:
            return jsonify({'error': err}), 400
        topic = topic.strip()
        template_id = data.get('template_id', 'educational_explainer')
        research_model = data.get('research_model', 'fast')  # 'fast', 'deep', or 'deep_research_agent'
        project_id = data.get('project_id')

        template = get_template(template_id)
        if not template:
            return jsonify({'error': f'Unknown template: {template_id}'}), 400

        # Deep Research Agent: async path
        if research_model == 'deep_research_agent':
            print(f"[Research] Starting Deep Research Agent for '{topic}'")
            result = start_deep_research(
                topic=topic,
                template_id=template_id,
                api_key=g.api_key,
            )
            if "error" in result:
                return jsonify({'error': result['error']}), 500
            return jsonify({
                'async': True,
                'interaction_id': result['interaction_id'],
                'status': 'in_progress',
            })

        # Configure model based on selection
        if research_model == 'deep':
            model_name = "gemini-3.1-pro-preview"
            use_search = True
            print(f"[Research] Using DEEP mode: {model_name} + Google Search")
        else:
            model_name = "gemini-3-flash-preview"
            use_search = False
            print(f"[Research] Using FAST mode: {model_name}")

        print(f"[Research] Starting research on '{topic}' using template '{template_id}'")

        # Build research queries from template layers
        queries = build_research_queries(template_id, topic)
        analysis_questions = template["research_config"]["analysis_questions"]

        print(f"DEBUG: queries type: {type(queries)}, len: {len(queries)}")
        for i, q in enumerate(queries):
            print(f"DEBUG: query {i} type: {type(q)}")

        print(f"DEBUG: analysis_questions type: {type(analysis_questions)}, len: {len(analysis_questions)}")
        for i, q in enumerate(analysis_questions):
            print(f"DEBUG: question {i} type: {type(q)}")

        queries_text = chr(10).join(f'{i+1}. {q}' for i, q in enumerate(queries))
        questions_text = chr(10).join(f'{i+1}. {q}' for i, q in enumerate(analysis_questions))

        # Extract source requirements from template
        template = get_template(template_id)
        if template and "research_config" in template:
            min_sources = template["research_config"].get("min_sources", 10)
            source_types_dict = template["research_config"].get("source_types", {})
            source_reqs_text = chr(10).join(f"- {count}+ sources from: {stype.replace('_', ' ').title()}" for stype, count in source_types_dict.items())
        else:
            min_sources = 10
            source_reqs_text = "- Diverse and credible sources"

        # Use Gemini to do comprehensive research
        research_prompt = f"""You are a world-class research analyst producing an EXHAUSTIVE research dossier. Your goal is MAXIMUM DEPTH AND DETAIL — not brevity.

TOPIC: {topic}

RESEARCH LAYERS (investigate each one thoroughly):
{queries_text}

SOURCE DIVERSITY REQUIREMENTS:
You MUST search for and cite at least {min_sources} distinct sources.
You MUST actively search for and include information from the following categories:
{source_reqs_text}

ANALYSIS QUESTIONS — Answer EACH question with a COMPREHENSIVE, multi-paragraph essay-style response:
{questions_text}

═══════ CRITICAL OUTPUT INSTRUCTIONS ═══════
- Each answer MUST be at least 3-5 detailed paragraphs (NOT a brief summary)
- Include specific names, exact dates, precise dollar amounts, percentages, and statistics in EVERY answer
- DO NOT summarize or abbreviate — be EXHAUSTIVE
- Use sub-headings, bullet points, and numbered lists within answers for organization
- Every claim must reference its source context
- If the question asks for N examples, provide AT LEAST N examples (more is better)
- Write as if you are creating a reference document that will be used to write a 20-minute documentary

Return a JSON object:
{{
  "results": [
    {{"question": "the analysis question", "answer": "A comprehensive, multi-paragraph essay-style answer. Include every relevant detail, specific data point, named source, and supporting evidence. DO NOT summarize — be exhaustive. Use sub-points and structured formatting within the answer."}}
  ],
  "key_facts": ["Include at least 15-20 specific, verifiable facts with exact numbers"],
  "sources_mentioned": ["source1", "source2", ...],
  "summary": "A thorough 3-5 paragraph executive summary synthesizing all major findings, key statistics, and critical insights"
}}

REMEMBER: You are building a COMPREHENSIVE RESEARCH DATABASE, not writing a brief overview.
The more specific and detailed your answers, the better. No vague language. No approximations.
Return ONLY the JSON."""

        print(f"[Research] Sending research prompt to Gemini...")
        research_max_tokens = 32768 if research_model == 'deep' else 16384
        research_pid = data.get('project_id')
        raw = generate_content(research_prompt, model_name=model_name, use_search=use_search,
                               api_key=g.api_key, max_output_tokens=research_max_tokens,
                               uid=g.uid, project_id=research_pid,
                               description=f"research({research_model})")

        # Fallback: if Deep (Pro) failed, retry with Flash + Search
        if raw and raw.startswith("Error:") and model_name != "gemini-3-flash-preview":
            fallback_model = "gemini-3-flash-preview"
            print(f"[Research] Primary model failed. Falling back to {fallback_model} + Search...")
            raw = generate_content(research_prompt, model_name=fallback_model, use_search=True,
                                   api_key=g.api_key, max_output_tokens=16384,
                                   uid=g.uid, project_id=research_pid,
                                   description="research(fallback)")

        if not raw or raw.startswith("Error:"):
            return jsonify({'error': raw or 'Research query returned no result'}), 500

        # Parse JSON
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])

        try:
            research_data = json.loads(text)
        except json.JSONDecodeError:
            research_data = {
                "results": [{"question": "General Research", "answer": text}],
                "key_facts": [],
                "sources_mentioned": [],
                "summary": text[:500]
            }

        # Build the formatted dossier
        dossier = build_research_dossier(
            topic, template_id, research_data.get("results", [])
        )

        # Optional structured pipeline (planner → parallel sub-researchers → merger).
        # Runs in addition to the legacy call so the existing dossier stays unchanged
        # when extraction fails. Gated by the RESEARCH_STRUCTURED env flag.
        structured = None
        if RESEARCH_STRUCTURED_ENABLED:
            try:
                print(f"[Research] RESEARCH_STRUCTURED enabled — running structured pipeline")
                structured = run_structured_research(
                    topic=topic,
                    template_id=template_id,
                    api_key=g.api_key,
                    mode='deep' if research_model == 'deep' else 'fast',
                    uid=g.uid, project_id=research_pid,
                )
            except Exception as e:
                print(f"[Research] Structured pipeline failed: {e}")
                structured = None

        # Narrative Spine extraction — additive ranked outline consumed by downstream prompts.
        spine = None
        if NARRATIVE_SPINE_ENABLED:
            try:
                print(f"[Research] NARRATIVE_SPINE enabled — extracting spine")
                spine_result = extract_narrative_spine(
                    topic=topic,
                    research_dossier=dossier,
                    structured=structured,
                    api_key=g.api_key,
                    uid=g.uid, project_id=research_pid,
                )
                if spine_result.get("success"):
                    spine = spine_result["spine"]
                    print(f"[Research] Spine: {len(spine.get('key_claims', []))} claims")
                else:
                    print(f"[Research] Spine extraction failed: {spine_result.get('error', 'unknown')}")
            except Exception as e:
                print(f"[Research] Spine extraction error: {e}")
                spine = None

        # Save to .tmp for reference
        if DEBUG_SAVE_TMP:
            save_dir = TMP_DIR
            if project_id:
                save_dir = os.path.join(TMP_DIR, project_id)
            os.makedirs(save_dir, exist_ok=True)
            safe_topic = "".join(c if c.isalnum() or c in " -_" else "" for c in topic)[:50]
            dossier_path = os.path.join(save_dir, f"research_{safe_topic}.md")
            with open(dossier_path, "w") as f:
                f.write(dossier)
            print(f"[Research] Dossier saved to {dossier_path}")

        # Save dossier to Project Firestore document
        if project_id:
            try:
                project_ref = db.collection('users').document(g.uid).collection('projects').document(project_id)
                project_payload = {
                    'research_dossier': dossier,
                    'research_summary': research_data.get("summary", ""),
                    'research_key_facts': research_data.get("key_facts", []),
                    'research_sources': research_data.get("sources_mentioned", []),
                    'last_updated_at': SERVER_TIMESTAMP
                }
                if structured is not None:
                    project_payload['research_structured'] = structured
                    project_payload['research_schema_version'] = RESEARCH_SCHEMA_VERSION
                if spine is not None:
                    project_payload['research_spine'] = spine
                project_ref.set(project_payload, merge=True)
                print(f"[Research] Saved to project document {project_id}")
            except Exception as e:
                print(f"[Research] Warning: Failed to save to project document: {e}")

        # Save dossier to Firestore for persistence/reuse
        try:
            dossier_ref = db.collection('users').document(g.uid).collection('dossiers').document()
            dossier_payload = {
                'topic': topic,
                'template_id': template_id,
                'template_name': template["metadata"]["name"],
                'dossier': dossier,
                'key_facts': research_data.get("key_facts", []),
                'sources': research_data.get("sources_mentioned", []),
                'summary': research_data.get("summary", ""),
                'created_at': SERVER_TIMESTAMP,
                'research_model': research_model
            }
            if structured is not None:
                dossier_payload['structured'] = structured
                dossier_payload['schema_version'] = RESEARCH_SCHEMA_VERSION
            dossier_ref.set(dossier_payload)
            print(f"[Research] Dossier saved to Firestore: {dossier_ref.id}")
        except Exception as fs_err:
            print(f"[Research] Warning: Firestore save failed: {fs_err}")

        response = {
            'success': True,
            'dossier': dossier,
            'key_facts': research_data.get("key_facts", []),
            'sources': research_data.get("sources_mentioned", []),
            'summary': research_data.get("summary", ""),
            'template_name': template["metadata"]["name"]
        }
        if structured is not None:
            response['structured'] = structured
        if spine is not None:
            response['spine'] = spine
        return jsonify(response)

    except Exception as e:
        return safe_error_response(e)


# ────────────────────────────────────────────────────────────────
#  PROJECTS API (PERSISTENCE)
# ────────────────────────────────────────────────────────────────

@app.route('/api/projects', methods=['GET'])
@require_auth
@limiter.limit("200/hour")
def list_projects():
    """List all saved projects for the user."""
    try:
        docs = db.collection('users').document(g.uid).collection('projects') \
                 .order_by('last_updated_at', direction=Query.DESCENDING).stream()
                 
        projects = []
        for doc in docs:
            d = doc.to_dict()
            ts = d.get('last_updated_at')
            projects.append({
                'id': doc.id,
                'title': d.get('title', 'Untitled Project'),
                'topic': d.get('topic', ''),
                'last_updated_at': ts.isoformat() if ts else None
            })
            
        return jsonify({'projects': projects})
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/projects', methods=['POST'])
@require_auth
@limiter.limit("200/hour")
def create_project():
    """Create a new empty project."""
    try:
        data = request.json or {}
        title, err = validate_input(data, 'title', required=False, max_length=200)
        title = title or 'Untitled Project'
        if err:
            return jsonify({'error': err}), 400
        
        project_ref = db.collection('users').document(g.uid).collection('projects').document()
        new_project = {
            'title': title,
            'topic': data.get('topic', ''),
            'settings': data.get('settings', {}),
            'research_dossier': data.get('research_dossier', ''),
            'narration_data': data.get('narration_data', None),
            'production_data': data.get('production_data', None),
            'created_at': SERVER_TIMESTAMP,
            'last_updated_at': SERVER_TIMESTAMP,
        }
        project_ref.set(new_project)

        # Firestore SERVER_TIMESTAMP is a sentinel that isn't JSON-serializable;
        # replace with an ISO string (client only needs a sortable value here).
        now_iso = datetime.utcnow().isoformat() + 'Z'
        response_project = {**new_project, 'created_at': now_iso, 'last_updated_at': now_iso}
        return jsonify({
            'success': True,
            'project_id': project_ref.id,
            'project': response_project
        })
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/projects/<project_id>', methods=['GET'])
@require_auth
@limiter.limit("200/hour")
def get_project(project_id):
    """Load a specific project's full state.

    Shots and visuals live in subcollections (so a 1000-shot project doesn't
    exceed Firestore's 1MB per-doc limit). On first load of a legacy project,
    `fh.migrate_project` splits the embedded `production_data` /
    `visuals_scenes` fields out into subcollections — idempotent, transparent.
    """
    try:
        doc = db.collection('users').document(g.uid).collection('projects').document(project_id).get()
        if not doc.exists:
            return jsonify({'error': 'Project not found'}), 404

        project_data = doc.to_dict()
        project_data['id'] = doc.id

        try:
            migrated = fh.migrate_project(g.uid, project_id, project_data)
            if migrated:
                # Drop the legacy fields from the response so the UI sees the
                # post-migration shape (subcollection sources only).
                project_data.pop('production_data', None)
                project_data.pop('visuals_scenes', None)
        except Exception as mig_err:
            print(f"[Migration] project {project_id}: {mig_err}")

        # Assemble subcollection data into the response. Keep the legacy keys
        # the UI already expects so loadProject() doesn't need to change shape.
        shots = fh.read_shots(g.uid, project_id)
        if shots:
            project_data['production_data'] = {
                'production_table': {'shots': shots, 'total_shots': len(shots)}
            }
        visuals = fh.read_visuals(g.uid, project_id)
        if visuals:
            project_data['visuals_scenes'] = visuals
        project_data['pipeline_state'] = fh.read_checkpoints(g.uid, project_id)

        # Convert Firestore timestamps to ISO strings for JSON serialization
        for key in ('created_at', 'last_updated_at', 'migrated_at'):
            if key in project_data and hasattr(project_data[key], 'isoformat'):
                project_data[key] = project_data[key].isoformat()
        return jsonify({'success': True, 'project': project_data})
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/projects/<project_id>', methods=['PUT'])
@require_auth
@limiter.limit("200/hour")
def update_project(project_id):
    """Auto-save / Update a specific project.

    `production_data` and `visuals_scenes` are intercepted here and routed
    into the shots/ and visuals/ subcollections — they used to blow the 1MB
    project-doc cap on large tables. The rest of the autosave payload (title,
    settings, narration_data, etc.) goes onto the project doc as before.
    """
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        # Don't update timestamps provided from client, use server timestamp
        data.pop('last_updated_at', None)
        data.pop('created_at', None)

        legacy_pd = data.pop('production_data', None)
        legacy_vs = data.pop('visuals_scenes', None)

        if legacy_pd is not None:
            shots = fh.extract_legacy_shots(legacy_pd) if isinstance(legacy_pd, dict) else []
            try:
                fh.clear_shots(g.uid, project_id)
                if shots:
                    fh.write_shots(g.uid, project_id, shots, start_order=0)
            except Exception as e:
                print(f"[autosave/shots] project {project_id}: {e}")

        if isinstance(legacy_vs, list):
            try:
                fh.clear_visuals(g.uid, project_id)
                if legacy_vs:
                    fh.write_visuals(g.uid, project_id, legacy_vs, start_order=0)
            except Exception as e:
                print(f"[autosave/visuals] project {project_id}: {e}")

        data['last_updated_at'] = SERVER_TIMESTAMP

        db.collection('users').document(g.uid).collection('projects').document(project_id).set(
            data, merge=True
        )
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/projects/<project_id>', methods=['DELETE'])
@require_auth
@limiter.limit("200/hour")
def delete_project(project_id):
    """Delete a specific project, its asset subcollection, and Storage files."""
    try:
        project_ref = db.collection('users').document(g.uid).collection('projects').document(project_id)

        # Cascade-delete the assets subcollection (Firestore doesn't auto-cascade).
        try:
            asset_docs = list(project_ref.collection('assets').stream())
            for ad in asset_docs:
                ad.reference.delete()
            if asset_docs:
                print(f"[Asset Cleanup] Deleted {len(asset_docs)} asset docs for project {project_id}")
        except Exception as e:
            print(f"[Asset Cleanup] Error: {e}")

        # Cascade-delete the production subcollections (shots, visuals,
        # pipeline_checkpoints). These live alongside `assets`.
        try:
            n = fh.cascade_delete_project_subcollections(g.uid, project_id)
            if n:
                print(f"[Subcoll Cleanup] Deleted {n} docs across shots/visuals/checkpoints for {project_id}")
        except Exception as e:
            print(f"[Subcoll Cleanup] Error: {e}")

        project_ref.delete()

        # Clean up Firebase Storage files for this project
        if bucket:
            storage_prefixes = [
                f"images/{project_id}/",
                f"videos/{project_id}/",
                f"audio/{project_id}/",
                f"references/{project_id}/",
            ]
            deleted_count = 0
            for prefix in storage_prefixes:
                try:
                    blobs = list(bucket.list_blobs(prefix=prefix))
                    for blob in blobs:
                        blob.delete()
                        deleted_count += 1
                except Exception as e:
                    print(f"[Storage Cleanup] Error deleting {prefix}: {e}")
            if deleted_count > 0:
                print(f"[Storage Cleanup] Deleted {deleted_count} files for project {project_id}")

        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


# ────────────────────────────────────────────────────────────────
#  STUDIO — per-project asset library (Firestore subcollection)
# ────────────────────────────────────────────────────────────────

# Fields the client is allowed to set/update on an asset doc.
# `scene_id` tags assets that came from a specific Visuals scene so a future
# filter ("show only assets from scene 3") can group them.
_ASSET_WRITE_FIELDS = {
    'kind', 'url', 'thumbnail_url', 'prompt', 'model_id', 'provider',
    'refs', 'params', 'favorite', 'scene_id',
}
# Fields the client is allowed to PATCH after creation.
_ASSET_PATCH_FIELDS = {'favorite', 'prompt'}


def _serialize_asset(doc):
    d = doc.to_dict() or {}
    d['id'] = doc.id
    ts = d.get('ts')
    if hasattr(ts, 'isoformat'):
        d['ts'] = ts.isoformat()
        
    # Check and refresh signed URL if it has expired
    url = d.get('url', '')
    if url and "X-Goog-Signature" in url and bucket:
        try:
            from urllib.parse import urlparse, parse_qs
            import datetime
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            if "X-Goog-Date" in qs and "X-Goog-Expires" in qs:
                date_str = qs["X-Goog-Date"][0]
                expires_sec = int(qs["X-Goog-Expires"][0])
                issue_time = datetime.datetime.strptime(date_str, "%Y%m%dT%H%M%SZ")
                expiry_time = issue_time + datetime.timedelta(seconds=expires_sec)
                now = datetime.datetime.utcnow()
                
                if now > expiry_time:
                    # Extract blob path from url
                    bucket_name = bucket.name
                    path = parsed.path
                    prefix = f"/{bucket_name}/"
                    if path.startswith(prefix):
                        blob_path = path[len(prefix):]
                        # Regenerate signed URL
                        blob = bucket.blob(blob_path)
                        new_url = _generate_signed_url(blob)
                        d['url'] = new_url
                        # Update the database to store the new URL
                        try:
                            doc.reference.update({'url': new_url})
                        except Exception as update_err:
                            print(f"[Storage] Failed to update asset doc with new URL: {update_err}")
        except Exception as e:
            print(f"[Storage] Failed to refresh URL for asset {doc.id}: {e}")
            
    return d


# ────────────────────────────────────────────────────────────────
#  Production table — granular shot + resume endpoints
# ────────────────────────────────────────────────────────────────

# A production task whose `updated_at` is older than this without reaching a
# terminal status is treated as orphaned (the worker thread died — most likely
# its Cloud Run instance was killed). Threshold needs to be long enough that
# a slow Gemini call inside a still-running task doesn't trip it; 15 min is
# well above the observed 8-12 min ceiling for a single batch including
# Gemini's RetryInfo waits.
_STALE_TASK_AGE_MIN = 15


def _recover_stale_production_tasks(uid, project_id):
    """Sweep any orphaned production_tasks for this project whose worker
    died before writing a terminal status. Shots that completed before the
    crash live in `production_tasks/{tid}/batches/` (the ephemeral buffer
    added 2026-05-18). Move them into the durable `shots/` subcollection,
    compute missing beats from the project's narration, and write a
    `task_state` checkpoint so the Resume banner picks them up.

    Idempotent — once a task is marked terminal, subsequent calls skip it.
    Returns the recovered task_id or None.
    """
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=_STALE_TASK_AGE_MIN)

    tasks_ref = db.collection('users').document(uid).collection('production_tasks')
    try:
        candidates = list(tasks_ref.where('project_id', '==', project_id)
                                   .where('status', '==', 'running').stream())
    except Exception as e:
        print(f"[Recovery] query failed for {project_id}: {e}")
        return None

    for task_snap in candidates:
        task_data = task_snap.to_dict() or {}
        updated_at = task_data.get('updated_at')
        # Firestore timestamps come back as datetime; SERVER_TIMESTAMP that
        # never resolved would be None — treat as stale.
        if updated_at and hasattr(updated_at, 'timestamp'):
            if updated_at > cutoff:
                continue  # still warm, leave it alone
        elif updated_at is not None:
            continue  # unknown shape, be conservative

        task_id = task_snap.id
        # Reassemble shots from per-batch docs.
        try:
            batch_docs = list(task_snap.reference.collection('batches').stream())
        except Exception as e:
            print(f"[Recovery] {task_id} batches read failed: {e}")
            continue
        all_shots = []
        for bd in batch_docs:
            bdata = bd.to_dict() or {}
            shots = bdata.get('shots') or []
            if shots:
                all_shots.append((bdata.get('batch_idx', 0), shots))
        all_shots.sort(key=lambda t: t[0])
        recovered_shots = [s for _, batch in all_shots for s in batch]

        if not recovered_shots:
            # Worker died before producing any shots — nothing to salvage,
            # but still mark the task terminal so future polls stop.
            try:
                task_snap.reference.update({
                    'status': 'failed',
                    'error': 'Worker terminated before producing any shots (instance kill suspected)',
                    'updated_at': SERVER_TIMESTAMP,
                })
            except Exception:
                pass
            continue

        # Move into the durable home. Preserve any shots already there (e.g.
        # from a prior retry) by appending — keyed by shot_number when present,
        # else by current count.
        try:
            existing = fh.read_shots(uid, project_id) or []
            existing_keys = {str(s.get('shot_number') or s.get('_id') or i)
                             for i, s in enumerate(existing)}
            to_add = [s for s in recovered_shots
                      if str(s.get('shot_number') or '') not in existing_keys
                      or not s.get('shot_number')]
            if to_add:
                # Renumber order to extend after existing.
                start = len(existing)
                fh.write_shots(uid, project_id, to_add, start_order=start)
        except Exception as e:
            print(f"[Recovery] {task_id} write_shots failed: {e}")
            continue

        # Compute missing beats so Resume can target just the gap.
        missing_beats = []
        try:
            proj_snap = (db.collection('users').document(uid)
                           .collection('projects').document(project_id).get())
            if proj_snap.exists:
                narration_data = (proj_snap.to_dict() or {}).get('narration_data') or {}
                input_beats = narration_data.get('narration') or []
                if input_beats:
                    from research_scriptwriter import _check_beat_coverage
                    merged = (fh.read_shots(uid, project_id) or [])
                    missing_beats = _check_beat_coverage(input_beats, merged)
        except Exception as e:
            print(f"[Recovery] {task_id} coverage check failed: {e}")

        # Update checkpoints + close out the task.
        try:
            fh.write_checkpoint(uid, project_id, 'task_state', {
                'active_task_id': task_id,
                'last_completed_phase': 'phase5_dp',
                'partial': True,
                'status': 'recovered_from_stale_task',
                'missing_beats': missing_beats,
                'error': 'Worker terminated mid-stream (instance kill suspected); shots recovered from ephemeral buffer.',
            })
            task_snap.reference.update({
                'status': 'failed',
                'error': 'Worker terminated mid-stream; shots recovered from ephemeral buffer',
                'recovered_shot_count': len(recovered_shots),
                'updated_at': SERVER_TIMESTAMP,
            })
            print(f"[Recovery] {task_id}: salvaged {len(recovered_shots)} shots into project {project_id}, "
                  f"{len(missing_beats)} beats still missing")
        except Exception as e:
            print(f"[Recovery] {task_id} checkpoint write failed: {e}")
            continue

        return task_id

    return None


@app.route('/api/projects/<project_id>/resumable', methods=['GET'])
@require_auth
@limiter.limit("400/hour")
def project_resumable_state(project_id):
    """Report whether the project has a partial production run that can be
    resumed. Backed by `pipeline_checkpoints/task_state` which generation
    endpoints update at terminal points, plus a sweep for orphaned
    `production_tasks` (Cloud Run instance kills that never reached a
    terminal handler).
    """
    try:
        # Self-heal: any stale running task with stranded batch data gets
        # swept into the durable shots/ subcollection and surfaced via
        # task_state. Cheap (one indexed query) on the happy path.
        try:
            _recover_stale_production_tasks(g.uid, project_id)
        except Exception as rec_err:
            print(f"[Recovery] sweep error: {rec_err}")

        state = fh.read_checkpoint(g.uid, project_id, 'task_state') or {}
        shots_n = fh.shots_count(g.uid, project_id)
        partial = bool(state.get('partial'))
        return jsonify({
            'resumable': partial,
            'last_completed_phase': state.get('last_completed_phase'),
            'status': state.get('status'),
            'shots_written': shots_n,
            'total_shots': state.get('total_shots') or shots_n,
            'missing_beats': state.get('missing_beats') or [],
            'error': state.get('error'),
            'active_task_id': state.get('active_task_id'),
            # Surface persisted per-phase/batch errors so the UI's inline
            # error log can render them (see ui/index.html:renderProductionErrorLog).
            'errors': state.get('errors') or [],
        })
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/projects/<project_id>/pipeline_state', methods=['DELETE'])
@require_auth
@limiter.limit("200/hour")
def clear_project_pipeline_state(project_id):
    """Discard a resumable partial run. Optional query flags:
       - clear_shots=1 also wipes the shots/ subcollection (Start Over).
    """
    try:
        also_clear_shots = request.args.get('clear_shots', '0') in ('1', 'true', 'yes')
        n = fh.clear_checkpoints(g.uid, project_id)
        shots_cleared = 0
        if also_clear_shots:
            shots_cleared = fh.clear_shots(g.uid, project_id)
        return jsonify({
            'success': True,
            'checkpoints_cleared': n,
            'shots_cleared': shots_cleared,
        })
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/projects/<project_id>/shots/<shot_id>', methods=['PUT'])
@require_auth
@limiter.limit("1200/hour")
def update_shot(project_id, shot_id):
    """Upsert a single shot doc. Used for inline-edit autosave so the UI
    doesn't have to re-send the whole table on every keystroke.
    """
    try:
        data = request.json or {}
        if not isinstance(data, dict):
            return jsonify({'error': 'Shot payload must be an object'}), 400
        fh.write_shot(g.uid, project_id, shot_id, data)
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/projects/<project_id>/shots/<shot_id>', methods=['DELETE'])
@require_auth
@limiter.limit("600/hour")
def delete_shot_route(project_id, shot_id):
    try:
        fh.delete_shot(g.uid, project_id, shot_id)
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/projects/<project_id>/visuals/<visual_id>', methods=['PUT'])
@require_auth
@limiter.limit("1200/hour")
def update_visual(project_id, visual_id):
    try:
        data = request.json or {}
        if not isinstance(data, dict):
            return jsonify({'error': 'Visual payload must be an object'}), 400
        fh.write_visual(g.uid, project_id, visual_id, data)
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/projects/<project_id>/visuals/<visual_id>', methods=['DELETE'])
@require_auth
@limiter.limit("600/hour")
def delete_visual_route(project_id, visual_id):
    try:
        fh.delete_visual(g.uid, project_id, visual_id)
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/projects/<project_id>/assets', methods=['GET'])
@require_auth
@limiter.limit("600/hour")
def list_project_assets(project_id):
    """List Studio assets for a project, newest first."""
    try:
        try:
            limit = max(1, min(int(request.args.get('limit', 200)), 500))
        except (TypeError, ValueError):
            limit = 200
        kind = request.args.get('kind')

        coll = (db.collection('users').document(g.uid)
                  .collection('projects').document(project_id)
                  .collection('assets'))
        query = coll.order_by('ts', direction=Query.DESCENDING).limit(limit)
        if kind in {'image', 'video', 'audio'}:
            query = coll.where('kind', '==', kind) \
                        .order_by('ts', direction=Query.DESCENDING).limit(limit)

        assets = [_serialize_asset(d) for d in query.stream()]
        return jsonify({'success': True, 'assets': assets})
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/projects/<project_id>/assets', methods=['POST'])
@require_auth
@limiter.limit("1200/hour")
def create_project_asset(project_id):
    """Persist a Studio generation result to the project's asset library."""
    try:
        data = request.json or {}
        kind = (data.get('kind') or '').strip()
        url = (data.get('url') or '').strip()
        if kind not in {'image', 'video', 'audio'}:
            return jsonify({'error': 'kind must be image, video, or audio'}), 400
        if not url:
            return jsonify({'error': 'url is required'}), 400

        doc = {k: data[k] for k in _ASSET_WRITE_FIELDS if k in data}
        doc['kind'] = kind
        doc['url'] = url
        doc['favorite'] = bool(doc.get('favorite', False))
        doc['created_by'] = g.uid
        doc['ts'] = SERVER_TIMESTAMP

        ref = (db.collection('users').document(g.uid)
                 .collection('projects').document(project_id)
                 .collection('assets').document())
        ref.set(doc)

        # Echo back with an ISO timestamp so the client can render immediately
        # without re-fetching (SERVER_TIMESTAMP isn't JSON-serializable).
        echo = {**doc, 'id': ref.id, 'ts': datetime.utcnow().isoformat() + 'Z'}
        return jsonify({'success': True, 'asset': echo})
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/projects/<project_id>/assets/<asset_id>', methods=['PATCH'])
@require_auth
@limiter.limit("1200/hour")
def patch_project_asset(project_id, asset_id):
    """Toggle favorite, edit prompt, etc. — whitelist of fields only."""
    try:
        data = request.json or {}
        update = {k: data[k] for k in _ASSET_PATCH_FIELDS if k in data}
        if not update:
            return jsonify({'error': 'No updatable fields supplied'}), 400
        if 'favorite' in update:
            update['favorite'] = bool(update['favorite'])

        ref = (db.collection('users').document(g.uid)
                 .collection('projects').document(project_id)
                 .collection('assets').document(asset_id))
        ref.set(update, merge=True)
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/projects/<project_id>/assets/<asset_id>', methods=['DELETE'])
@require_auth
@limiter.limit("600/hour")
def delete_project_asset(project_id, asset_id):
    try:
        (db.collection('users').document(g.uid)
           .collection('projects').document(project_id)
           .collection('assets').document(asset_id).delete())
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/dossiers', methods=['GET'])
@require_auth
@limiter.limit("200/hour")
def list_dossiers():
    """List saved research dossiers for the current user."""
    try:
        docs = db.collection('users').document(g.uid).collection('dossiers') \
                 .order_by('created_at', direction=Query.DESCENDING) \
                 .limit(20).stream()

        dossiers = []
        for doc in docs:
            d = doc.to_dict()
            dossiers.append({
                'id': doc.id,
                'topic': d.get('topic', ''),
                'template_name': d.get('template_name', ''),
                'summary': (d.get('summary', '') or '')[:200],
                'research_model': d.get('research_model', 'unknown')
            })

        return jsonify({'dossiers': dossiers})
    except Exception as e:
        logger.exception("Failed to list dossiers")
        return jsonify({'dossiers': []})


@app.route('/api/dossiers/<dossier_id>', methods=['GET'])
@require_auth
@limiter.limit("200/hour")
def get_dossier(dossier_id):
    """Load a specific saved dossier."""
    try:
        doc = db.collection('users').document(g.uid).collection('dossiers').document(dossier_id).get()
        if not doc.exists:
            return jsonify({'error': 'Dossier not found'}), 404
        return jsonify(doc.to_dict())
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/research/poll', methods=['POST'])
@require_auth
@limiter.limit("200/hour")
def poll_research():
    """
    Poll an async Deep Research Agent interaction for results.
    Accepts: interaction_id, topic, template_id
    Returns: { status: 'in_progress'|'completed'|'failed', ... }
    When completed, formats results into a dossier and saves to Firestore.
    """
    try:
        data = request.json
        interaction_id = data.get('interaction_id')
        topic = data.get('topic', 'unknown_topic')
        template_id = data.get('template_id', 'educational_explainer')
        project_id = data.get('project_id')

        if not interaction_id:
            return jsonify({'error': 'interaction_id is required'}), 400

        result = poll_deep_research(interaction_id, api_key=g.api_key)

        if result['status'] == 'in_progress':
            return jsonify({'status': 'in_progress'})

        if result['status'] == 'failed':
            return jsonify({'error': result.get('error', 'Deep research failed')}), 500

        # Completed — format into dossier
        research_text = result.get('result', '')
        template = get_template(template_id)

        # Build dossier from the deep research output
        notebook_results = [{"question": "Deep Research Report", "answer": research_text}]
        dossier = build_research_dossier(topic, template_id, notebook_results)

        # Optional: extract a structured schema from the unstructured blob.
        # The deep_research_agent API does not expose grounding metadata, so this
        # is best-effort — empty sources are acceptable.
        structured = None
        if RESEARCH_STRUCTURED_ENABLED:
            try:
                print(f"[Deep Research] RESEARCH_STRUCTURED enabled — extracting structure from blob")
                structured = structure_from_blob(
                    text=research_text,
                    topic=topic,
                    template_id=template_id,
                    mode='deep_research_agent',
                    model='deep-research-pro-preview-12-2025',
                    api_key=g.api_key,
                    uid=g.uid, project_id=data.get('project_id'),
                )
            except Exception as e:
                print(f"[Deep Research] Structure extraction failed: {e}")
                structured = None

        # Narrative Spine extraction (same as /api/research path).
        spine = None
        if NARRATIVE_SPINE_ENABLED:
            try:
                print(f"[Deep Research] NARRATIVE_SPINE enabled — extracting spine")
                spine_result = extract_narrative_spine(
                    topic=topic,
                    research_dossier=dossier,
                    structured=structured,
                    api_key=g.api_key,
                    uid=g.uid, project_id=data.get('project_id'),
                )
                if spine_result.get("success"):
                    spine = spine_result["spine"]
                    print(f"[Deep Research] Spine: {len(spine.get('key_claims', []))} claims")
                else:
                    print(f"[Deep Research] Spine extraction failed: {spine_result.get('error', 'unknown')}")
            except Exception as e:
                print(f"[Deep Research] Spine extraction error: {e}")
                spine = None

        # Save to Firestore
        try:
            dossier_ref = db.collection('users').document(g.uid).collection('dossiers').document()
            dossier_payload = {
                'topic': topic,
                'template_id': template_id,
                'template_name': template["metadata"]["name"] if template else template_id,
                'dossier': dossier,
                'key_facts': [],
                'sources': [],
                'summary': research_text[:500],
                'created_at': SERVER_TIMESTAMP,
                'research_model': 'deep_research_agent'
            }
            if structured is not None:
                dossier_payload['structured'] = structured
                dossier_payload['schema_version'] = RESEARCH_SCHEMA_VERSION
            dossier_ref.set(dossier_payload)
            print(f"[Deep Research] Dossier saved to Firestore: {dossier_ref.id}")
        except Exception as fs_err:
            print(f"[Deep Research] Warning: Firestore save failed: {fs_err}")

        # Save to .tmp
        if DEBUG_SAVE_TMP:
            save_dir = TMP_DIR
            if project_id:
                save_dir = os.path.join(TMP_DIR, project_id)
            os.makedirs(save_dir, exist_ok=True)
            safe_topic = "".join(c if c.isalnum() or c in " -_" else "" for c in topic)[:50]
            dossier_path = os.path.join(save_dir, f"research_{safe_topic}_deep.md")
            with open(dossier_path, "w") as f:
                f.write(dossier)
            print(f"[Deep Research] Dossier saved to {dossier_path}")

        # Save to Project Firestore document
        if project_id:
            try:
                project_ref = db.collection('users').document(g.uid).collection('projects').document(project_id)
                project_payload = {
                    'research_dossier': dossier,
                    'research_summary': research_text[:500],
                    'research_key_facts': [],
                    'research_sources': [],
                    'last_updated_at': SERVER_TIMESTAMP
                }
                if structured is not None:
                    project_payload['research_structured'] = structured
                    project_payload['research_schema_version'] = RESEARCH_SCHEMA_VERSION
                if spine is not None:
                    project_payload['research_spine'] = spine
                project_ref.set(project_payload, merge=True)
                print(f"[Deep Research] Saved to project document {project_id}")
            except Exception as e:
                print(f"[Deep Research] Warning: Failed to save to project document: {e}")

        response = {
            'status': 'completed',
            'dossier': dossier,
            'key_facts': [],
            'sources': [],
            'summary': research_text[:500],
            'template_name': template["metadata"]["name"] if template else template_id,
        }
        if structured is not None:
            response['structured'] = structured
        if spine is not None:
            response['spine'] = spine
        return jsonify(response)

    except Exception as e:
        return safe_error_response(e)


# ────────────────────────────────────────────────────────────────
#  NARRATIVE SPINE — extract / save user edits
# ────────────────────────────────────────────────────────────────

def _validate_spine_edit(spine):
    """Validate a user-edited spine before persisting. Returns (cleaned, error_msg)."""
    if not isinstance(spine, dict):
        return None, "spine must be an object"
    claims = spine.get("key_claims")
    if not isinstance(claims, list) or not claims:
        return None, "key_claims must be a non-empty list"

    seen_ids = set()
    cleaned_claims = []
    valid_importance = {"primary", "supporting", "color"}
    for c in claims:
        if not isinstance(c, dict):
            continue
        kid = (c.get("id") or "").strip()
        text = (c.get("text") or "").strip()
        if not kid or not text:
            return None, "every claim needs an id and text"
        if kid in seen_ids:
            return None, f"duplicate claim id: {kid}"
        seen_ids.add(kid)
        importance = c.get("importance") if c.get("importance") in valid_importance else "supporting"
        cleaned = {
            "id": kid,
            "text": text,
            "importance": importance,
            "source_ids": [s for s in (c.get("source_ids") or []) if isinstance(s, str)],
        }
        if c.get("act_hint"):
            cleaned["act_hint"] = c["act_hint"]
        cleaned_claims.append(cleaned)

    flow = spine.get("logical_flow") or []
    if not isinstance(flow, list):
        return None, "logical_flow must be a list"
    for k in flow:
        if k not in seen_ids:
            return None, f"logical_flow references unknown id: {k}"

    source_map = spine.get("source_map") or {}
    if not isinstance(source_map, dict):
        return None, "source_map must be an object"
    for c in cleaned_claims:
        for sid in c["source_ids"]:
            if sid not in source_map:
                return None, f"claim {c['id']} references unknown source: {sid}"

    return {
        "version": spine.get("version", 1),
        "topic": spine.get("topic", ""),
        "key_claims": cleaned_claims,
        "logical_flow": list(flow),
        "source_map": source_map,
        "extracted_at": spine.get("extracted_at"),
        "edited_by_user": True,
    }, None


@app.route('/api/research/spine', methods=['POST'])
@require_auth
@limiter.limit("30/hour")
def research_spine_extract():
    """Extract a Narrative Spine from a dossier and persist it on the project doc.

    Body: { project_id?, topic, dossier?, structured? }
    If project_id is supplied and dossier is omitted, loads the dossier from Firestore.
    Returns: { success, spine } or { error }.
    """
    if not NARRATIVE_SPINE_ENABLED:
        return jsonify({'error': 'Narrative Spine is not enabled on this server'}), 403
    try:
        data = request.json or {}
        project_id = data.get('project_id')
        topic = (data.get('topic') or '').strip()
        dossier = data.get('dossier') or ''
        structured = data.get('structured')

        if project_id and (not dossier or not topic or structured is None):
            try:
                doc = db.collection('users').document(g.uid).collection('projects').document(project_id).get()
                if doc.exists:
                    pdata = doc.to_dict() or {}
                    dossier = dossier or pdata.get('research_dossier', '')
                    topic = topic or pdata.get('topic') or pdata.get('name', '')
                    if structured is None:
                        structured = pdata.get('research_structured')
            except Exception as e:
                print(f"[Spine] Failed to load project {project_id}: {e}")

        if not dossier or not dossier.strip():
            return jsonify({'error': 'Dossier is required'}), 400

        result = extract_narrative_spine(
            topic=topic,
            research_dossier=dossier,
            structured=structured,
            api_key=g.api_key,
            uid=g.uid, project_id=project_id,
        )
        if not result.get('success'):
            return jsonify({'error': result.get('error', 'Spine extraction failed')}), 502

        spine = result['spine']

        if project_id:
            try:
                project_ref = db.collection('users').document(g.uid).collection('projects').document(project_id)
                project_ref.set({
                    'research_spine': spine,
                    'last_updated_at': SERVER_TIMESTAMP,
                }, merge=True)
            except Exception as e:
                print(f"[Spine] Failed to persist for {project_id}: {e}")

        return jsonify({'success': True, 'spine': spine})

    except Exception as e:
        return safe_error_response(e)


@app.route('/api/research/spine', methods=['PUT'])
@require_auth
@limiter.limit("120/hour")
def research_spine_save():
    """Save a user-edited Narrative Spine to the project doc.

    Body: { project_id, spine }
    Returns: { success, spine } or { error }.
    """
    try:
        data = request.json or {}
        project_id = data.get('project_id')
        spine = data.get('spine')
        if not project_id:
            return jsonify({'error': 'project_id is required'}), 400

        cleaned, err = _validate_spine_edit(spine)
        if err:
            return jsonify({'error': f'Invalid spine: {err}'}), 400

        try:
            project_ref = db.collection('users').document(g.uid).collection('projects').document(project_id)
            project_ref.set({
                'research_spine': cleaned,
                'last_updated_at': SERVER_TIMESTAMP,
            }, merge=True)
        except Exception as e:
            print(f"[Spine] Save failed for {project_id}: {e}")
            return jsonify({'error': 'Failed to save spine'}), 500

        return jsonify({'success': True, 'spine': cleaned})

    except Exception as e:
        return safe_error_response(e)


@app.route('/api/research/spine/rerank', methods=['POST'])
@require_auth
@limiter.limit("60/hour")
def research_spine_rerank():
    """Re-rank an existing spine for a chosen title / audience / tone.

    Body: { project_id, title?, audience?, tone?, format_preset? }
    Loads the spine from Firestore, re-ranks via Gemini, persists the result.
    Returns: { success, spine } or { error }.

    On any failure (parse error, empty model response), the original spine is
    preserved in Firestore and returned in the error response so the caller
    can surface the error without losing data.
    """
    if not NARRATIVE_SPINE_ENABLED:
        return jsonify({'error': 'Narrative Spine is not enabled on this server'}), 403
    try:
        data = request.json or {}
        project_id = data.get('project_id')
        if not project_id:
            return jsonify({'error': 'project_id is required'}), 400

        spine = _load_project_spine(project_id)
        if not spine:
            return jsonify({'error': 'No spine found for this project. Run extraction first.'}), 404

        result = rerank_narrative_spine(
            spine=spine,
            title=(data.get('title') or '').strip(),
            audience=(data.get('audience') or '').strip(),
            tone=(data.get('tone') or '').strip(),
            format_preset=(data.get('format_preset') or '').strip(),
            api_key=g.api_key,
            uid=g.uid, project_id=project_id,
        )
        if not result.get('success'):
            return jsonify({'error': result.get('error', 'Rerank failed'), 'spine': spine}), 502

        new_spine = result['spine']
        try:
            project_ref = db.collection('users').document(g.uid).collection('projects').document(project_id)
            project_ref.set({
                'research_spine': new_spine,
                'last_updated_at': SERVER_TIMESTAMP,
            }, merge=True)
        except Exception as e:
            print(f"[Spine rerank] Persist failed for {project_id}: {e}")

        return jsonify({'success': True, 'spine': new_spine})

    except Exception as e:
        return safe_error_response(e)


@app.route('/api/research/spine/suggest-edits', methods=['POST'])
@require_auth
@limiter.limit("60/hour")
def research_spine_suggest_edits():
    """Ask the AI to propose 0-5 targeted improvements to the current spine.

    Body: { project_id, title?, audience? }
    Returns: { success, suggestions: [...], overall_note: "..." } or { error }.

    Suggestions are NOT applied. The UI shows them with apply/reject controls
    and PUTs the final spine back via /api/research/spine when the user accepts.
    """
    if not NARRATIVE_SPINE_ENABLED:
        return jsonify({'error': 'Narrative Spine is not enabled on this server'}), 403
    try:
        data = request.json or {}
        project_id = data.get('project_id')
        if not project_id:
            return jsonify({'error': 'project_id is required'}), 400

        spine = _load_project_spine(project_id)
        if not spine:
            return jsonify({'error': 'No spine found for this project. Run extraction first.'}), 404

        result = suggest_spine_edits(
            spine=spine,
            title=(data.get('title') or '').strip(),
            audience=(data.get('audience') or '').strip(),
            api_key=g.api_key,
            uid=g.uid, project_id=project_id,
        )
        if not result.get('success'):
            return jsonify({'error': result.get('error', 'Suggestion generation failed')}), 502

        return jsonify(result)

    except Exception as e:
        return safe_error_response(e)


@app.route('/api/suggest-titles', methods=['POST'])
@require_auth
@limiter.limit("60/hour")
def suggest_titles():
    """
    Generate 5 YouTube title suggestions based on research results.
    Each title represents a genuinely different narrative angle.
    Accepts: topic, template_id, dossier, audience
    Returns: { titles: [ { title, description }, ... ] }
    """
    try:
        data = request.json
        topic = data.get('topic', '').strip()
        template_id = data.get('template_id', 'educational_explainer')
        dossier = data.get('dossier', '')
        audience = data.get('audience', 'General')
        project_id = data.get('project_id')

        if not topic:
            return jsonify({'error': 'Topic is required'}), 400
        if not dossier:
            return jsonify({'error': 'Research dossier is required'}), 400

        prompt = build_title_suggestions_prompt(
            template_id=template_id,
            topic=topic,
            dossier=dossier,
            audience=audience,
            structured=_load_project_structured(project_id),
        )

        print(f"[Titles] Generating 5 title suggestions for '{topic}' (audience: {audience})")
        raw = generate_content(prompt, model_name="gemini-3-flash-preview", api_key=g.api_key,
                               uid=g.uid, project_id=project_id,
                               description="suggest_titles")

        if not raw or raw.startswith("Error:"):
            return jsonify({'error': raw or 'Title generation returned no result'}), 500

        # Parse JSON
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])

        try:
            titles = json.loads(text)
            if not isinstance(titles, list):
                titles = titles.get('titles', [])
        except json.JSONDecodeError:
            return jsonify({'error': 'Failed to parse title suggestions'}), 500

        print(f"[Titles] Generated {len(titles)} title suggestions")
        return jsonify({'success': True, 'titles': titles[:5]})

    except Exception as e:
        return safe_error_response(e)


@app.route('/api/auto-suggest-tone', methods=['POST'])
@require_auth
@limiter.limit("60/hour")
def auto_suggest_tone_route():
    """Auto-suggest the best tone for a selected title and audience."""
    try:
        data = request.json
        template_id = data.get('template_id', 'educational_explainer')
        selected_title = data.get('selected_title', '')
        audience = data.get('audience', 'General')

        if not selected_title:
            return jsonify({'error': 'Selected title is required'}), 400

        print(f"[Tone] Auto-suggesting tone for: '{selected_title}' (audience: {audience})")

        result = auto_suggest_tone(
            template_id=template_id,
            selected_title=selected_title,
            audience=audience,
            api_key=g.api_key,
            uid=g.uid, project_id=data.get('project_id'),
        )

        print(f"[Tone] Suggested: {result.get('suggested_tone', '?')}")
        return jsonify({'success': True, **result})

    except Exception as e:
        return safe_error_response(e)


@app.route('/api/generate-script', methods=['POST'])
@require_auth
@limiter.limit("30/hour")
def generate_script_route():
    """
    Generate narration from research results (acts/beats, no scene breakdown).
    Accepts: topic, template_id, dossier, duration_minutes, audience, tone, focus, selected_title
    Returns: { success, narration: { title, hook_type, narration: [...], ... } }
    """
    try:
        data = request.json
        topic, err = validate_input(data, 'topic', max_length=500)
        if err:
            return jsonify({'error': err}), 400
        topic = topic.strip()
        template_id = data.get('template_id', 'educational_explainer')
        dossier = data.get('dossier', '')
        duration, err = validate_input(data, 'duration_minutes', field_type=int, required=False, min_val=1, max_val=60)
        if err:
            return jsonify({'error': err}), 400
        duration = duration if duration is not None else 10
        audience = data.get('audience', 'general')
        tone = data.get('tone', '')
        focus = data.get('focus', '')
        selected_title = data.get('selected_title', '')
        format_preset = data.get('format_preset', '')
        viewer_outcome = data.get('viewer_outcome', '')
        custom_audience = data.get('custom_audience', '')
        custom_tone = data.get('custom_tone', '')
        project_id = data.get('project_id')

        style_mode = data.get('style_mode', 'template')  # 'template' or 'transcript'
        style_transcript = data.get('style_transcript', '')
        style_blend_mode = data.get('style_blend_mode', 'clone')  # 'clone' or 'blend'
        if not dossier:
            return jsonify({'error': 'Research dossier is required. Run research first.'}), 400

        style_guide = None
        if style_mode == 'transcript' and style_transcript:
            print(f"[Narration] Analyzing style from transcript ({len(style_transcript)} chars)...")
            style_guide = analyze_style(style_transcript, api_key=g.api_key)
            if not style_guide or style_guide.startswith("Error:"):
                print(f"[Narration] Style analysis failed: {style_guide}")
                return jsonify({'error': f"Style analysis failed: {style_guide or 'empty response'}"}), 500
            print(f"[Narration] Style analysis complete (blend_mode={style_blend_mode}).")

        print(f"[Narration] Generating narration for '{topic}' ({template_id}, {duration}min, audience={audience}, tone={tone})")

        result = generate_narration(
            topic=topic,
            template_id=template_id,
            research_dossier=dossier,
            duration_minutes=duration,
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
            api_key=g.api_key,
            structured=_load_project_structured(project_id),
            spine=_load_project_spine(project_id),
            uid=g.uid, project_id=project_id,
        )

        if "error" in result:
            return jsonify({'error': result["error"]}), 500

        # Save to Project Firestore document
        if project_id:
            try:
                project_ref = db.collection('users').document(g.uid).collection('projects').document(project_id)
                project_ref.set({
                    'narration_data': result.get('narration', result),
                    'last_updated_at': SERVER_TIMESTAMP
                }, merge=True)
                print(f"[Narration] Saved to project document {project_id}")
            except Exception as e:
                print(f"[Narration] Warning: Failed to save to project document: {e}")

        # Save narration to .tmp
        if DEBUG_SAVE_TMP:
            save_dir = TMP_DIR
            if project_id:
                save_dir = os.path.join(TMP_DIR, project_id)
            os.makedirs(save_dir, exist_ok=True)
            safe_topic = "".join(c if c.isalnum() or c in " -_" else "" for c in topic)[:50]
            narration_path = os.path.join(save_dir, f"narration_{safe_topic}.json")
            with open(narration_path, "w") as f:
                json.dump(result, f, indent=2)
            print(f"[Narration] Saved to {narration_path}")

        return jsonify(result)

    except Exception as e:
        return safe_error_response(e)


@app.route('/api/regenerate-beat', methods=['POST'])
@require_auth
@limiter.limit("60/hour")
def regenerate_beat_route():
    """
    Regenerate specific beats or an entire act within a narration.
    Accepts: topic, template_id, dossier, narration, target_act, target_beat_indices,
             mode ('restyle' or 'reimagine'), audience, tone, duration_minutes
    Returns: { success, beats: [...] }
    """
    try:
        data = request.json
        topic = data.get('topic', '').strip()
        template_id = data.get('template_id', 'educational_explainer')
        dossier = data.get('dossier', '')
        narration = data.get('narration')
        target_act = data.get('target_act')
        target_beat_indices = data.get('target_beat_indices', [])
        mode = data.get('mode', 'restyle')
        audience = data.get('audience', 'General')
        tone = data.get('tone', '')
        duration_minutes = int(data.get('duration_minutes', 10))
        project_id = data.get('project_id')

        if not narration:
            return jsonify({'error': 'Narration is required'}), 400
        if not target_act and not target_beat_indices:
            return jsonify({'error': 'Either target_act or target_beat_indices is required'}), 400

        label = f"act '{target_act}'" if target_act else f"beats {target_beat_indices}"
        print(f"[Regenerate] {mode} {label} for '{topic}'")

        result = regenerate_beats(
            topic=topic,
            template_id=template_id,
            research_dossier=dossier,
            full_narration=narration,
            target_act=target_act,
            target_beat_indices=target_beat_indices,
            mode=mode,
            audience=audience,
            tone=tone,
            duration_minutes=duration_minutes,
            api_key=g.api_key,
            structured=_load_project_structured(project_id),
            spine=_load_project_spine(project_id),
            uid=g.uid, project_id=project_id,
        )

        if "error" in result:
            return jsonify({'error': result['error']}), 500

        print(f"[Regenerate] Got {len(result.get('beats', []))} regenerated beats")
        return jsonify(result)

    except Exception as e:
        return safe_error_response(e)


def _commit_production_table(uid, pid, table, task_state_patch=None):
    """Durably persist a production table into the per-project shots/
    subcollection. Replaces the older pattern of writing the whole table
    as a `production_data` field on the project doc (which blew Firestore's
    1MB per-doc cap once shot counts grew past ~400).

    Also writes a `pipeline_checkpoints/task_state` doc so the Resume flow
    can see what was last committed. `task_state_patch` lets the caller
    overlay phase/status/error fields without re-fetching.
    """
    if not pid:
        return
    shots = []
    if isinstance(table, dict):
        shots = fh.extract_legacy_shots(table) or table.get('shots') or []
    try:
        fh.clear_shots(uid, pid)
        if shots:
            fh.write_shots(uid, pid, shots, start_order=0)
    except Exception as e:
        print(f"[Production] commit-shots error for {pid}: {e}")
    try:
        state = {
            'shots_written': len(shots),
            'total_shots': len(shots),
        }
        if isinstance(task_state_patch, dict):
            state.update(task_state_patch)
        fh.write_checkpoint(uid, pid, 'task_state', state)
    except Exception as e:
        print(f"[Production] task_state checkpoint error for {pid}: {e}")
    # Bump the project doc's last_updated_at so the sidebar's sort order
    # reflects the generation event. The doc itself stays tiny.
    try:
        db.collection('users').document(uid).collection('projects').document(pid).set({
            'last_updated_at': SERVER_TIMESTAMP,
        }, merge=True)
    except Exception as e:
        print(f"[Production] last_updated_at bump error for {pid}: {e}")


@app.route('/api/generate-production-table', methods=['POST'])
@require_auth
@limiter.limit("60/hour")
def generate_production_table_route():
    """
    PHASE 3: Generate production-ready prompts from narration.
    Accepts: narration (narration JSON with acts/beats), duration_minutes,
             plus optional style config fields or style_analysis.
             If body contains streaming: true, returns {task_id} immediately and
             writes per-batch progress to Firestore. Poll via
             /api/production-task/<task_id>.
    Returns: production table with split shots, first-frame, and Veo prompts.
    """
    try:
        data = request.json
        narration = data.get('narration')
        duration_minutes = int(data.get('duration_minutes', 10))
        project_id = data.get('project_id')
        streaming = bool(data.get('streaming', False))

        if not narration:
            return jsonify({'error': 'Narration is required. Generate narration first.'}), 400

        beats = narration.get('narration', [])
        print(f"[Production] Received narration: '{narration.get('title', 'Untitled')}' "
              f"({len(beats)} beats, {duration_minutes}min, streaming={streaming})")

        # Check for structured style analysis (from images or text)
        style_analysis = data.get('style_analysis')
        aspect_ratio = data.get('aspect_ratio', '16:9')
        pacing_tier = data.get('pacing_tier', 'Standard')
        quality_mode = data.get('quality_mode', 'fast')
        format_preset = data.get('format_preset', '')

        if style_analysis:
            summary = style_analysis.get('style_summary', 'custom') if isinstance(style_analysis, dict) else 'custom'
            print(f"[Production] Using style analysis: {summary}")
        else:
            print(f"[Production] No style analysis — using default cinematic style")

        # Check for creative direction
        creative_direction = data.get('creative_direction')
        if creative_direction:
            dir_summary = creative_direction.get('direction_summary', '')[:80]
            print(f"[Production] Using creative direction: {dir_summary}")

        # Check for cast definition
        cast = data.get('cast')
        if cast and cast.get('has_characters') and cast.get('cast'):
            print(f"[Production] Using cast: {len(cast['cast'])} characters")

        # Check for locations definition
        locations = data.get('locations')
        if locations and locations.get('has_locations') and locations.get('locations'):
            print(f"[Production] Using locations: {len(locations['locations'])} settings")

        # ── Streaming path: spawn worker, return task_id immediately ──
        if streaming:
            import uuid as _uuid
            import threading as _threading
            task_id = _uuid.uuid4().hex
            captured_uid = g.uid
            captured_api_key = g.api_key
            spine_data = _load_project_spine(project_id)
            task_ref = (db.collection('users').document(captured_uid)
                          .collection('production_tasks').document(task_id))
            # Root doc stays small (metadata only). Per-batch shot payloads live
            # in a subcollection so cumulative writes never approach Firestore's
            # 1 MiB doc size limit. final_table is written to the project doc,
            # not here.
            task_ref.set({
                'status': 'running',
                'project_id': project_id,
                'title': narration.get('title', 'Untitled'),
                'total_batches': None,
                'failed_batches': [],
                'created_at': SERVER_TIMESTAMP,
                'updated_at': SERVER_TIMESTAMP,
            })

            # Sentinel for cooperative cancellation. The cancel endpoint marks
            # task.status='cancelled'; the worker sees it on the next batch
            # callback and raises this so the outer handler skips terminal
            # commits (the cancel endpoint has already wiped state).
            class _GenerationCancelled(Exception):
                pass

            def _progress_cb(event):
                # Cooperative cancel check — only on batch-boundary events to
                # avoid per-event Firestore reads. The cancel endpoint wipes
                # shots/ + checkpoints immediately for UI; this check stops the
                # worker from re-writing the now-cancelled state.
                if event.get('type') in ('batch', 'batch_failed'):
                    try:
                        snap = task_ref.get()
                        if snap.exists and (snap.to_dict() or {}).get('status') == 'cancelled':
                            raise _GenerationCancelled('cancel requested')
                    except _GenerationCancelled:
                        raise
                    except Exception:
                        pass  # Don't kill the worker on transient Firestore errors.
                try:
                    if event.get('type') == 'stage' and event.get('total_batches'):
                        task_ref.update({
                            'total_batches': event['total_batches'],
                            'updated_at': SERVER_TIMESTAMP,
                        })
                    elif event.get('type') == 'batch':
                        # Each batch is its own doc (~30-60 KB max), keeping the
                        # root doc bounded even for very long scripts.
                        batch_idx = event['batch_idx']
                        task_ref.collection('batches').document(str(batch_idx)).set({
                            'batch_idx': batch_idx,
                            'shots': event['shots'],
                            'created_at': SERVER_TIMESTAMP,
                        })
                        update_fields = {'updated_at': SERVER_TIMESTAMP}
                        if event.get('total_batches'):
                            update_fields['total_batches'] = event['total_batches']
                        task_ref.update(update_fields)
                    elif event.get('type') == 'batch_failed':
                        task_ref.update({
                            'failed_batches': ArrayUnion([{
                                'batch_idx': event['batch_idx'],
                                'error': event['error'],
                            }]),
                            'updated_at': SERVER_TIMESTAMP,
                        })
                        # Mirror into task_state.errors[] so the UI's inline
                        # error log can surface the failure immediately and
                        # across reloads.
                        if project_id:
                            try:
                                fh.append_error(captured_uid, project_id, {
                                    'phase': 'batch',
                                    'batch': f"{event['batch_idx']}/{event.get('total_batches') or '?'}",
                                    'error': event['error'],
                                    'task_id': task_id,
                                })
                            except Exception as err_log_err:
                                print(f"[Production stream] error-log write failed: {err_log_err}")
                except Exception as cb_err:
                    print(f"[Production stream] progress write failed: {cb_err}")

            def _worker():
                try:
                    worker_result = generate_production_table(
                        narration_json=narration,
                        duration_minutes=duration_minutes,
                        style_analysis=style_analysis,
                        aspect_ratio=aspect_ratio,
                        api_key=captured_api_key,
                        pacing_tier=pacing_tier,
                        quality_mode=quality_mode,
                        creative_direction=creative_direction,
                        cast=cast,
                        format_preset=format_preset,
                        spine=spine_data,
                        locations=locations,
                        uid=captured_uid, project_id=project_id,
                        progress_callback=_progress_cb,
                    )
                    final_table = worker_result.get('production_table')
                    if final_table:
                        tmp_path = os.path.join(TMP_DIR, f"task_prod_{task_id}.json")
                        try:
                            with open(tmp_path, "w") as f:
                                json.dump(final_table, f)
                        except Exception as e:
                            print(f"[Production stream] Error writing tmp table: {e}")

                    if worker_result.get('error') == 'coverage_failure':
                        # Persist whatever shots we got into the shots/ subcollection
                        # so the partial table survives refresh. task_state flags
                        # the project as resumable; missing_beats is what's left.
                        if project_id and final_table:
                            _commit_production_table(
                                captured_uid, project_id, final_table,
                                task_state_patch={
                                    'active_task_id': task_id,
                                    'last_completed_phase': 'phase5_dp',
                                    'partial': True,
                                    'status': 'coverage_failure',
                                    'missing_beats': worker_result.get('missing_beats', []),
                                },
                            )
                        task_ref.update({
                            'status': 'coverage_failure',
                            'missing_beats': worker_result.get('missing_beats', []),
                            'updated_at': SERVER_TIMESTAMP,
                        })
                        return
                    if 'error' in worker_result:
                        if project_id:
                            try:
                                fh.write_checkpoint(captured_uid, project_id, 'task_state', {
                                    'active_task_id': task_id,
                                    'partial': True,
                                    'status': 'failed',
                                    'error': worker_result['error'],
                                })
                            except Exception as ck_err:
                                print(f"[Production] failure checkpoint error: {ck_err}")
                            try:
                                fh.append_error(captured_uid, project_id, {
                                    'phase': 'pipeline',
                                    'batch': '',
                                    'error': worker_result['error'],
                                    'task_id': task_id,
                                })
                            except Exception as err_log_err:
                                print(f"[Production] error-log write failed: {err_log_err}")
                        task_ref.update({
                            'status': 'failed',
                            'error': worker_result['error'],
                            'updated_at': SERVER_TIMESTAMP,
                        })
                        return

                    # Durable commit: shots → projects/{pid}/shots/ subcollection.
                    if project_id and final_table:
                        _commit_production_table(
                            captured_uid, project_id, final_table,
                            task_state_patch={
                                'active_task_id': task_id,
                                'last_completed_phase': 'phase5_dp',
                                'partial': False,
                                'status': 'complete',
                            },
                        )
                    task_ref.update({
                        'status': 'complete',
                        'updated_at': SERVER_TIMESTAMP,
                    })
                except _GenerationCancelled:
                    # User cancelled; the cancel endpoint already wiped shots/
                    # and pipeline_checkpoints/. Do nothing terminal here so
                    # we don't resurrect deleted state.
                    print(f"[Production stream] task {task_id} cancelled by user")
                    return
                except Exception as worker_err:
                    import traceback as _tb
                    print(f"[Production stream] worker exception: {worker_err}")
                    _tb.print_exc()
                    try:
                        task_ref.update({
                            'status': 'failed',
                            'error': str(worker_err),
                            'updated_at': SERVER_TIMESTAMP,
                        })
                    except Exception:
                        pass
                    if project_id:
                        try:
                            fh.append_error(captured_uid, project_id, {
                                'phase': 'worker',
                                'batch': '',
                                'error': str(worker_err),
                                'task_id': task_id,
                            })
                        except Exception:
                            pass

            _threading.Thread(target=_worker, daemon=True, name=f"prodtable-{task_id[:8]}").start()
            return jsonify({'task_id': task_id, 'streaming': True})

        # ── Legacy synchronous path (preserved for tests / fallback) ──
        result = generate_production_table(
            narration_json=narration,
            duration_minutes=duration_minutes,
            style_analysis=style_analysis,
            aspect_ratio=aspect_ratio,
            api_key=g.api_key,
            pacing_tier=pacing_tier,
            quality_mode=quality_mode,
            creative_direction=creative_direction,
            cast=cast,
            format_preset=format_preset,
            spine=_load_project_spine(project_id),
            locations=locations,
            uid=g.uid, project_id=project_id,
        )

        # Coverage failure: pass through the partial table + missing beats so the
        # UI can show a blocking modal with a targeted retry option (200 OK, not 500).
        if result.get('error') == 'coverage_failure':
            if project_id and result.get('production_table'):
                _commit_production_table(
                    g.uid, project_id, result['production_table'],
                    task_state_patch={
                        'last_completed_phase': 'phase5_dp',
                        'partial': True,
                        'status': 'coverage_failure',
                        'missing_beats': result.get('missing_beats', []),
                    },
                )
            return jsonify(result), 200

        if "error" in result:
            return jsonify({'error': result['error']}), 500

        # Durable commit: shots → projects/{pid}/shots/ subcollection.
        if project_id:
            _commit_production_table(
                g.uid, project_id, result.get('production_table', result),
                task_state_patch={
                    'last_completed_phase': 'phase5_dp',
                    'partial': False,
                    'status': 'complete',
                },
            )
            print(f"[Production] Committed shots subcollection for project {project_id}")

        # Save to .tmp
        if DEBUG_SAVE_TMP:
            save_dir = TMP_DIR
            if project_id:
                save_dir = os.path.join(TMP_DIR, project_id)
            os.makedirs(save_dir, exist_ok=True)
            title = narration.get('title', 'untitled')
            safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in title)[:50]
            pt_path = os.path.join(save_dir, f"production_table_{safe_title}.json")
            with open(pt_path, "w") as f:
                json.dump(result, f, indent=2)
            print(f"[Production] Saved to {pt_path}")

        return jsonify(result)

    except Exception as e:
        return safe_error_response(e)


@app.route('/api/production-task/<task_id>', methods=['GET'])
@require_auth
def production_task_poll_route(task_id):
    """Poll a streaming production-table task.
    Returns: { status, total_batches, batches_completed: [...], failed_batches: [...],
               missing_beats?, final_table?, error? }
    Status values: 'running' | 'complete' | 'coverage_failure' | 'failed'.
    """
    try:
        if not task_id or not task_id.replace('-', '').replace('_', '').isalnum():
            return jsonify({'error': 'Invalid task_id'}), 400
        task_ref = (db.collection('users').document(g.uid)
                      .collection('production_tasks').document(task_id))
        snap = task_ref.get()
        if not snap.exists:
            return jsonify({'error': 'Task not found'}), 404
        doc = snap.to_dict() or {}
        status = doc.get('status', 'running')

        # Per-batch shot payloads live in a subcollection (one doc per batch) to
        # keep the root doc under Firestore's 1 MiB size limit.
        batches_completed = []
        try:
            for bs in task_ref.collection('batches').stream():
                bdata = bs.to_dict() or {}
                if 'batch_idx' in bdata and 'shots' in bdata:
                    batches_completed.append({
                        'batch_idx': bdata['batch_idx'],
                        'shots': bdata['shots'],
                    })
            batches_completed.sort(key=lambda b: b.get('batch_idx', 0))
        except Exception as sub_err:
            print(f"[Production poll] batches subcollection read failed: {sub_err}")

        # On terminal states, hydrate final_table from tmp folder, or project doc.
        # NOTE: the .tmp file is local to the Cloud Run instance that ran the
        # worker. With multi-instance autoscaling, a poll can land on a
        # different instance and miss the file — Priority 2 (Firestore) is the
        # durable source. The tmp file is a fast-path for the same-instance
        # case and a safety net if project_id is missing from the task doc.
        final_table = None
        tmp_path = os.path.join(TMP_DIR, f"task_prod_{task_id}.json")
        if status in ('complete', 'coverage_failure'):
            # Priority 1: Check .tmp file saved by worker thread
            if os.path.exists(tmp_path):
                try:
                    with open(tmp_path, "r") as f:
                        final_table = json.load(f)
                except Exception as tmp_err:
                    print(f"[Production poll] tmp table read failed: {tmp_err}")

            # Priority 2: Fallback to project shots/ subcollection (durable home)
            if not final_table:
                proj_id = doc.get('project_id')
                if proj_id:
                    try:
                        shots = fh.read_shots(g.uid, proj_id)
                        if shots:
                            final_table = {'shots': shots, 'total_shots': len(shots)}
                    except Exception as proj_err:
                        print(f"[Production poll] subcollection read failed: {proj_err}")
                    # Priority 2b: legacy embedded field, if shots/ is empty
                    if not final_table:
                        try:
                            proj_snap = (db.collection('users').document(g.uid)
                                           .collection('projects').document(proj_id).get())
                            if proj_snap.exists:
                                legacy = (proj_snap.to_dict() or {}).get('production_data')
                                if isinstance(legacy, dict):
                                    final_table = legacy.get('production_table') or legacy
                        except Exception as proj_err:
                            print(f"[Production poll] legacy doc read failed: {proj_err}")

            # Best-effort cleanup: once we've hydrated final_table and the
            # task is terminal, the project doc is the source of truth.
            # The tmp file is no longer needed — delete it so files don't
            # accumulate on long-lived instances. Future polls (e.g. the
            # Download JSON button) still work via Priority 2.
            if final_table and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception as rm_err:
                    print(f"[Production poll] tmp cleanup failed: {rm_err}")

        return jsonify({
            'task_id': task_id,
            'status': status,
            'total_batches': doc.get('total_batches'),
            'batches_completed': batches_completed,
            'failed_batches': doc.get('failed_batches', []),
            'missing_beats': doc.get('missing_beats'),
            'final_table': final_table,
            'error': doc.get('error'),
            'project_id': doc.get('project_id'),
            'title': doc.get('title'),
        })
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/production-task/<task_id>/cancel', methods=['POST'])
@require_auth
@limiter.limit("200/hour")
def production_task_cancel_route(task_id):
    """Cancel an in-flight production task. **Full-wipe** semantics — clears
    the shots/ subcollection and pipeline_checkpoints/ so the user lands on a
    clean slate. The worker thread sees the status flip on its next batch
    callback and exits without writing any terminal state.

    Idempotent: cancelling a finished or already-cancelled task is harmless
    (no-op on the worker; cleanup runs to the same end state).
    """
    try:
        if not task_id or not task_id.replace('-', '').replace('_', '').isalnum():
            return jsonify({'error': 'Invalid task_id'}), 400
        task_ref = (db.collection('users').document(g.uid)
                      .collection('production_tasks').document(task_id))
        snap = task_ref.get()
        if not snap.exists:
            return jsonify({'error': 'Task not found'}), 404
        doc = snap.to_dict() or {}
        project_id = doc.get('project_id')

        # Flip task status first so the worker bails on its next checkpoint.
        try:
            task_ref.update({
                'status': 'cancelled',
                'updated_at': SERVER_TIMESTAMP,
            })
        except Exception as upd_err:
            print(f"[Cancel] task status update failed: {upd_err}")

        # Wipe the user-facing state. UI sees a clean slate immediately;
        # the worker thread's in-flight commits would land on already-wiped
        # state, and its cancel-check on the next batch callback exits cleanly.
        shots_cleared = 0
        checkpoints_cleared = 0
        if project_id:
            try:
                shots_cleared = fh.clear_shots(g.uid, project_id)
            except Exception as e:
                print(f"[Cancel] clear_shots error: {e}")
            try:
                checkpoints_cleared = fh.clear_checkpoints(g.uid, project_id)
            except Exception as e:
                print(f"[Cancel] clear_checkpoints error: {e}")

        return jsonify({
            'success': True,
            'status': 'cancelled',
            'shots_cleared': shots_cleared,
            'checkpoints_cleared': checkpoints_cleared,
        })
    except Exception as e:
        return safe_error_response(e)


# ─────────────────────────────────────────────────────────────────────────
# Agentic 5-stage production pipeline endpoints
# (See docs/agentic_5stage_pipeline_2026_05_25/plan.md)
# ─────────────────────────────────────────────────────────────────────────

def _validate_project_id(pid: str) -> bool:
    return bool(pid) and pid.replace('-', '').replace('_', '').isalnum()


@app.route('/api/production/run', methods=['POST'])
@require_auth
@limiter.limit("60/hour")
def agentic_production_run():
    """Kick off the 5-stage agentic pipeline for a project. Returns a task_id
    immediately; the UI polls /api/production/state for progress.
    """
    try:
        data = request.get_json() or {}
        project_id = (data.get('project_id') or '').strip()
        if not _validate_project_id(project_id):
            return jsonify({'error': 'project_id required'}), 400
        start_at = int(data.get('start_at') or 1)
        if start_at < 1 or start_at > 5:
            return jsonify({'error': 'start_at must be 1..5'}), 400

        # Wipe stale state if starting from scratch.
        if start_at == 1:
            try:
                fh.clear_production_stages(g.uid, project_id)
            except Exception as e:
                print(f"[agentic_run] clear_production_stages: {e}")
            # Seed pending stage docs so the UI renders 5 panels immediately.
            from agentic_schemas import STAGE_NAMES as _SN
            for n in range(1, 7):
                fh.write_production_stage(g.uid, project_id, n, {
                    'stage_number': n,
                    'stage_name': _SN[n],
                    'status': 'pending',
                })

        import uuid as _uuid
        import threading as _threading
        task_id = _uuid.uuid4().hex
        captured_uid = g.uid
        captured_api_key = g.api_key
        captured_pid = project_id

        from agentic_pipeline import run_pipeline_worker

        def _worker():
            try:
                run_pipeline_worker(
                    captured_uid, captured_pid, task_id,
                    captured_api_key, start_at=start_at,
                )
            except Exception as e:
                print(f"[agentic_worker] crash: {type(e).__name__}: {e}")

        _threading.Thread(
            target=_worker, daemon=True,
            name=f"agentic-{task_id[:8]}",
        ).start()

        return jsonify({
            'success': True,
            'task_id': task_id,
            'project_id': project_id,
        })
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/production/state', methods=['GET'])
@require_auth
@limiter.limit("600/hour")
def agentic_production_state():
    """Return all stage docs + flow_state + composed bible. Polled by UI."""
    try:
        project_id = (request.args.get('project_id') or '').strip()
        if not _validate_project_id(project_id):
            return jsonify({'error': 'project_id required'}), 400
        from agentic_pipeline import get_pipeline_state
        state = get_pipeline_state(g.uid, project_id)
        return jsonify({'success': True, **state})
    except Exception as e:
        return safe_error_response(e)


# Pause/Resume removed 2026-05-26: the pipeline is now gated stage-by-stage
# via Approve, so pausing between stages is the default state. To halt
# mid-stage, use /api/production/cancel.


@app.route('/api/production/cancel', methods=['POST'])
@require_auth
@limiter.limit("200/hour")
def agentic_production_cancel():
    """Full-wipe cancel: marks flow cancelled, clears production_stages/,
    shots/, and pipeline_checkpoints/. The worker bails on its next
    cooperative check.
    """
    try:
        data = request.get_json() or {}
        project_id = (data.get('project_id') or '').strip()
        if not _validate_project_id(project_id):
            return jsonify({'error': 'project_id required'}), 400

        # Flip flow state first so the worker exits early.
        try:
            fh.write_checkpoint(g.uid, project_id, 'agentic_flow', {
                'status': 'cancelled',
                'cancelled': True,
                'paused': False,
            })
        except Exception as e:
            print(f"[agentic_cancel] flow flip: {e}")

        stages_cleared = 0
        shots_cleared = 0
        checkpoints_cleared = 0
        try:
            stages_cleared = fh.clear_production_stages(g.uid, project_id)
        except Exception as e:
            print(f"[agentic_cancel] clear_production_stages: {e}")
        try:
            shots_cleared = fh.clear_shots(g.uid, project_id)
        except Exception as e:
            print(f"[agentic_cancel] clear_shots: {e}")
        try:
            checkpoints_cleared = fh.clear_checkpoints(g.uid, project_id)
        except Exception as e:
            print(f"[agentic_cancel] clear_checkpoints: {e}")

        # Also clear the production_table on the project doc so the Visuals
        # tab doesn't read stale shots after a cancel.
        try:
            db.collection('users').document(g.uid) \
              .collection('projects').document(project_id) \
              .set({'production_data': {}}, merge=True)
        except Exception as e:
            print(f"[agentic_cancel] clear production_data: {e}")

        return jsonify({
            'success': True,
            'stages_cleared': stages_cleared,
            'shots_cleared': shots_cleared,
            'checkpoints_cleared': checkpoints_cleared,
        })
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/production/stage/<int:stage_number>/approve', methods=['POST'])
@require_auth
@limiter.limit("300/hour")
def agentic_stage_approve(stage_number):
    """Approve a completed stage and advance the pipeline.

    Behavior:
      1. Mark this stage as 'approved'.
      2. Find the lowest stage in [1..5] whose status is pending/stale/error.
      3. If found, spawn a single-stage worker for that stage and return
         {success, advancing_to_stage, task_id}.
      4. If none found, the pipeline is complete — return success with no
         task_id.
    """
    try:
        if stage_number < 1 or stage_number > 6:
            return jsonify({'error': 'stage_number must be 1..6'}), 400
        data = request.get_json() or {}
        project_id = (data.get('project_id') or '').strip()
        if not _validate_project_id(project_id):
            return jsonify({'error': 'project_id required'}), 400
        existing = fh.read_production_stage(g.uid, project_id, stage_number) or {}
        if existing.get('status') not in ('complete', 'approved'):
            return jsonify({'error': 'stage is not complete'}), 400
        fh.write_production_stage(g.uid, project_id, stage_number, {
            'status': 'approved',
        })

        from agentic_pipeline import find_next_runnable_stage, run_pipeline_worker
        from datetime import datetime as _dt, timezone as _tz
        next_stage = find_next_runnable_stage(g.uid, project_id)
        if next_stage is None:
            # Pipeline fully complete (every stage approved or complete).
            try:
                fh.write_checkpoint(g.uid, project_id, 'agentic_flow', {
                    'status': 'complete',
                    'last_event_at': _dt.now(_tz.utc).isoformat(),
                })
            except Exception:
                pass
            return jsonify({'success': True, 'pipeline_complete': True})

        # Spawn worker for the next runnable stage.
        import uuid as _uuid
        import threading as _threading
        task_id = _uuid.uuid4().hex
        captured_uid = g.uid
        captured_api_key = g.api_key
        captured_pid = project_id
        captured_next = int(next_stage)

        def _worker():
            try:
                run_pipeline_worker(
                    captured_uid, captured_pid, task_id,
                    captured_api_key, start_at=captured_next,
                )
            except Exception as e:
                print(f"[agentic_approve] worker crash: {type(e).__name__}: {e}")

        _threading.Thread(
            target=_worker, daemon=True,
            name=f"agentic-approve-{task_id[:8]}",
        ).start()

        return jsonify({
            'success': True,
            'advancing_to_stage': captured_next,
            'task_id': task_id,
        })
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/production/stage/6/resume', methods=['POST'])
@require_auth
@limiter.limit("60/hour")
def agentic_stage6_resume():
    """Resume Stage 6 after a Cloud Run timeout or worker crash.

    The Stage 6 batched executor checkpoints completed batches in the
    stage doc's `completed_batches` field. This endpoint just spawns a
    fresh worker for Stage 6 — the executor reads the checkpoint and
    skips any batches that already wrote deltas, so the resumed run
    picks up at the next unfinished batch.
    """
    try:
        data = request.get_json() or {}
        project_id = (data.get('project_id') or '').strip()
        if not _validate_project_id(project_id):
            return jsonify({'error': 'project_id required'}), 400

        # Sanity: Stage 4 (blueprints) and Stage 5 (continuity brief) must
        # be complete for Stage 6 to resume meaningfully.
        s4 = fh.read_production_stage(g.uid, project_id, 4) or {}
        s5 = fh.read_production_stage(g.uid, project_id, 5) or {}
        if (s4.get('status') not in ('complete', 'approved')
                or s5.get('status') not in ('complete', 'approved')):
            return jsonify({'error': 'Stages 4 and 5 must be complete before resuming Stage 6'}), 400

        import uuid as _uuid
        import threading as _threading
        task_id = _uuid.uuid4().hex
        captured_uid = g.uid
        captured_api_key = g.api_key
        captured_pid = project_id

        from agentic_pipeline import run_pipeline_worker

        def _worker():
            try:
                run_pipeline_worker(
                    captured_uid, captured_pid, task_id,
                    captured_api_key, start_at=6,
                )
            except Exception as e:
                print(f"[agentic_resume6] crash: {type(e).__name__}: {e}")

        _threading.Thread(
            target=_worker, daemon=True,
            name=f"agentic-resume6-{task_id[:8]}",
        ).start()

        existing_stage6 = fh.read_production_stage(g.uid, project_id, 6) or {}
        return jsonify({
            'success': True,
            'task_id': task_id,
            'resumed_from_batch': len(existing_stage6.get('completed_batches') or []),
            'total_batches': existing_stage6.get('total_batches') or 0,
        })
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/production/stage/<int:stage_number>/edit', methods=['POST'])
@require_auth
@limiter.limit("600/hour")
def agentic_stage_edit(stage_number):
    """Persist user edits on a stage's output. Edits are dotted-path keys.
    Marks stages [stage_number+1..5] stale so the user knows to re-run.
    """
    try:
        if stage_number < 1 or stage_number > 6:
            return jsonify({'error': 'stage_number must be 1..6'}), 400
        data = request.get_json() or {}
        project_id = (data.get('project_id') or '').strip()
        user_edits = data.get('user_edits') or {}
        if not _validate_project_id(project_id):
            return jsonify({'error': 'project_id required'}), 400
        if not isinstance(user_edits, dict):
            return jsonify({'error': 'user_edits must be an object'}), 400
        existing = fh.read_production_stage(g.uid, project_id, stage_number) or {}
        merged_edits = dict(existing.get('user_edits') or {})
        merged_edits.update(user_edits)
        fh.write_production_stage(g.uid, project_id, stage_number, {
            'user_edits': merged_edits,
        })
        # Mark downstream stages stale so the UI can warn.
        if stage_number < 6:
            fh.mark_stages_stale(g.uid, project_id, stage_number + 1)
        return jsonify({'success': True, 'user_edits': merged_edits})
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/production/stage/<int:stage_number>/regenerate', methods=['POST'])
@require_auth
@limiter.limit("60/hour")
def agentic_stage_regenerate(stage_number):
    """Re-run a single stage with optional user feedback. Marks downstream
    stages stale. The worker runs ONLY this one stage and stops —
    downstream stages wait for explicit Approve clicks.
    """
    try:
        if stage_number < 1 or stage_number > 6:
            return jsonify({'error': 'stage_number must be 1..6'}), 400
        data = request.get_json() or {}
        project_id = (data.get('project_id') or '').strip()
        feedback = (data.get('feedback') or '').strip() or None
        if not _validate_project_id(project_id):
            return jsonify({'error': 'project_id required'}), 400

        # Reset the target stage to pending so the UI re-renders properly.
        fh.write_production_stage(g.uid, project_id, stage_number, {
            'status': 'pending',
            'error': None,
        })
        # Mark downstream stale.
        if stage_number < 6:
            fh.mark_stages_stale(g.uid, project_id, stage_number + 1)

        import uuid as _uuid
        import threading as _threading
        task_id = _uuid.uuid4().hex
        captured_uid = g.uid
        captured_api_key = g.api_key
        captured_pid = project_id
        captured_stage = stage_number
        captured_feedback = feedback

        from agentic_pipeline import run_pipeline_worker

        def _regen_worker():
            try:
                run_pipeline_worker(
                    captured_uid, captured_pid, task_id,
                    captured_api_key,
                    start_at=captured_stage,
                    feedback=captured_feedback,
                )
            except Exception as e:
                print(f"[agentic_regen] crash: {type(e).__name__}: {e}")

        _threading.Thread(
            target=_regen_worker, daemon=True,
            name=f"agentic-regen-{task_id[:8]}",
        ).start()

        return jsonify({'success': True, 'task_id': task_id,
                        'stage_number': stage_number, 'feedback': feedback})
    except Exception as e:
        return safe_error_response(e)


def _run_retry_beats(missing_beats, existing_table, project_id, api_key, uid,
                     duration_minutes, style_analysis, aspect_ratio, pacing_tier,
                     creative_direction, cast, format_preset, visual_brief, spine):
    """Core retry-beats logic, shared between the sync and streaming paths.

    Returns one of:
      { 'kind': 'success', 'production_table': {...} }
      { 'kind': 'coverage_failure', 'production_table': {...}, 'missing_beats': [...] }
      { 'kind': 'error', 'error': '...' }
    """
    from research_scriptwriter import (
        _generate_single_batch_6phase, _check_beat_coverage,
    )

    existing_shots = existing_table.get('shots', [])
    next_shot_num = len(existing_shots) + 1

    retry_narration = {
        'title': existing_table.get('title', 'Untitled'),
        'narration': [
            {'act': b.get('act', 'ACT 1'),
             'beat': b.get('beat', 'Beat'),
             'text': b.get('text', '')}
            for b in missing_beats
        ],
    }

    result = _generate_single_batch_6phase(
        retry_narration,
        duration_minutes=duration_minutes,
        style_analysis=style_analysis,
        aspect_ratio=aspect_ratio,
        api_key=api_key,
        shot_start_number=next_shot_num,
        batch_label="manual retry",
        pacing_tier=pacing_tier,
        creative_direction=creative_direction,
        cast=cast,
        format_preset=format_preset,
        visual_brief=visual_brief,
        spine=spine,
        uid=uid, project_id=project_id,
    )

    if 'error' in result:
        return {'kind': 'error', 'error': result['error']}

    new_shots = result.get('production_table', {}).get('shots', [])
    for s in new_shots:
        s['shot_number'] = str(next_shot_num)
        next_shot_num += 1

    merged_shots = existing_shots + new_shots
    still_missing = _check_beat_coverage(retry_narration['narration'], merged_shots)

    merged_table = {
        **existing_table,
        'shots': merged_shots,
        'total_shots': len(merged_shots),
    }
    merged_table.pop('batch_warning', None)
    merged_table.pop('failed_batches', None)

    if still_missing:
        return {'kind': 'coverage_failure',
                'production_table': merged_table,
                'missing_beats': still_missing}
    return {'kind': 'success', 'production_table': merged_table}


@app.route('/api/generate-production-table/retry-beats', methods=['POST'])
@require_auth
@limiter.limit("30/hour")
def retry_missing_beats_route():
    """
    Targeted retry for beats that the main production-table run failed to cover.
    Accepts: { project_id, missing_beats: [{act, beat, text}, ...],
               existing_table, style_analysis?, aspect_ratio?, pacing_tier?,
               creative_direction?, cast?, format_preset?, streaming? }
    If streaming=true, returns { task_id } immediately and writes progress to
    Firestore (poll via /api/production-task/<task_id>). Otherwise runs
    synchronously and returns the merged table directly.
    """
    try:
        data = request.json
        missing_beats = data.get('missing_beats') or []
        existing_table = data.get('existing_table') or {}
        project_id = data.get('project_id')
        streaming = bool(data.get('streaming', False))

        if not missing_beats:
            return jsonify({'error': 'No missing beats supplied'}), 400
            
        if not existing_table.get('shots') and project_id:
            try:
                shots = fh.read_shots(g.uid, project_id)
                if shots:
                    existing_table = {'shots': shots, 'total_shots': len(shots)}
                else:
                    # Fallback for any legacy project where the embedded
                    # production_data field hasn't been migrated yet.
                    proj_snap = db.collection('users').document(g.uid).collection('projects').document(project_id).get()
                    if proj_snap.exists:
                        legacy = (proj_snap.to_dict() or {}).get('production_data') or {}
                        if isinstance(legacy, dict):
                            existing_table = legacy.get('production_table') or legacy
            except Exception as e:
                print(f"[Retry] Error fetching existing table from project: {e}")
                
        if not existing_table or not existing_table.get('shots'):
            return jsonify({'error': 'No existing production table to extend. Please regenerate the full table.'}), 400

        common_kwargs = dict(
            missing_beats=missing_beats,
            existing_table=existing_table,
            project_id=project_id,
            duration_minutes=int(data.get('duration_minutes', 10)),
            style_analysis=data.get('style_analysis'),
            aspect_ratio=data.get('aspect_ratio', '16:9'),
            pacing_tier=data.get('pacing_tier', 'Standard'),
            creative_direction=data.get('creative_direction'),
            cast=data.get('cast'),
            format_preset=data.get('format_preset', ''),
            visual_brief=data.get('visual_brief'),
            spine=_load_project_spine(project_id),
        )

        # ── Streaming path: spawn worker, return task_id immediately ──
        # Previously this endpoint ran synchronously and we observed 654-759s
        # POST latencies. A refresh during that window orphaned the retry. Now
        # the worker runs in the background and the UI polls the same task
        # endpoint as the main production-table flow.
        if streaming:
            import uuid as _uuid
            import threading as _threading
            task_id = _uuid.uuid4().hex
            captured_uid = g.uid
            captured_api_key = g.api_key
            task_ref = (db.collection('users').document(captured_uid)
                          .collection('production_tasks').document(task_id))
            task_ref.set({
                'status': 'running',
                'project_id': project_id,
                'title': existing_table.get('title', 'Untitled'),
                'action': 'retry_beats',
                'missing_beats_count': len(missing_beats),
                'total_batches': 1,
                'failed_batches': [],
                'created_at': SERVER_TIMESTAMP,
                'updated_at': SERVER_TIMESTAMP,
            })

            def _retry_worker():
                try:
                    res = _run_retry_beats(
                        api_key=captured_api_key, uid=captured_uid,
                        **common_kwargs,
                    )
                    merged_table = res.get('production_table')
                    
                    if merged_table:
                        tmp_path = os.path.join(TMP_DIR, f"task_prod_{task_id}.json")
                        try:
                            with open(tmp_path, "w") as f:
                                json.dump(merged_table, f)
                        except Exception as e:
                            print(f"[Production retry] Error writing tmp table: {e}")

                    # Durable commit: merged shots → shots/ subcollection.
                    if project_id and merged_table:
                        is_partial = res['kind'] != 'success'
                        _commit_production_table(
                            captured_uid, project_id, merged_table,
                            task_state_patch={
                                'active_task_id': task_id,
                                'last_completed_phase': 'phase5_dp',
                                'partial': is_partial,
                                'status': res['kind'],
                                'missing_beats': res.get('missing_beats', []) if is_partial else [],
                            },
                        )

                    if res['kind'] == 'success':
                        task_ref.update({
                            'status': 'complete',
                            'updated_at': SERVER_TIMESTAMP,
                        })
                    elif res['kind'] == 'coverage_failure':
                        task_ref.update({
                            'status': 'coverage_failure',
                            'missing_beats': res.get('missing_beats', []),
                            'updated_at': SERVER_TIMESTAMP,
                        })
                    else:
                        task_ref.update({
                            'status': 'failed',
                            'error': res.get('error', 'Retry failed'),
                            'updated_at': SERVER_TIMESTAMP,
                        })
                except Exception as worker_err:
                    import traceback as _tb
                    print(f"[retry-beats stream] worker exception: {worker_err}")
                    _tb.print_exc()
                    try:
                        task_ref.update({
                            'status': 'failed',
                            'error': str(worker_err),
                            'updated_at': SERVER_TIMESTAMP,
                        })
                    except Exception:
                        pass

            _threading.Thread(target=_retry_worker, daemon=True,
                              name=f"retry-{task_id[:8]}").start()
            return jsonify({'task_id': task_id, 'streaming': True})

        # ── Legacy synchronous path (preserved for compatibility) ──
        res = _run_retry_beats(api_key=g.api_key, uid=g.uid, **common_kwargs)
        merged_table = res.get('production_table')

        if project_id and merged_table:
            is_partial = res['kind'] != 'success'
            _commit_production_table(
                g.uid, project_id, merged_table,
                task_state_patch={
                    'last_completed_phase': 'phase5_dp',
                    'partial': is_partial,
                    'status': res['kind'],
                    'missing_beats': res.get('missing_beats', []) if is_partial else [],
                },
            )

        if res['kind'] == 'error':
            return jsonify({'error': res['error'], 'missing_beats': missing_beats}), 500
        if res['kind'] == 'coverage_failure':
            return jsonify({
                'error': 'coverage_failure',
                'missing_beats': res['missing_beats'],
                'production_table': merged_table,
            }), 200
        return jsonify({'success': True, 'production_table': merged_table})

    except Exception as e:
        return safe_error_response(e)


# ────────────────────────────────────────────────────────────────
#  VISUALS TAB — IMAGE & VIDEO GENERATION
# ────────────────────────────────────────────────────────────────

@app.route('/api/latest-production-table', methods=['GET'])
@require_auth
@limiter.limit("200/hour")
def get_latest_production_table():
    """Return the most recently saved production table JSON.

    Priority: 1) Firestore project doc, 2) .tmp/{project_id}/ folder.
    Requires project_id to prevent cross-project contamination.
    """
    try:
        project_id = request.args.get('project_id')
        if not project_id:
            return jsonify({'error': 'project_id is required'}), 400

        # Priority 1a: shots/ subcollection (new home, no 1MB cap)
        try:
            shots = fh.read_shots(g.uid, project_id)
            if shots:
                pt = {'shots': shots, 'total_shots': len(shots)}
                print(f"[Visuals] Loaded {len(shots)} shots from subcollection for project {project_id}")
                return jsonify({'success': True, 'production_table': pt})
        except Exception as e:
            print(f"[Visuals] shots/ subcollection read failed: {e}")

        # Priority 1b: legacy embedded production_data field (pre-migration)
        try:
            project_ref = db.collection('users').document(g.uid).collection('projects').document(project_id)
            doc = project_ref.get()
            if doc.exists:
                proj_data = doc.to_dict()
                if proj_data.get('production_data'):
                    pd = proj_data['production_data']
                    pt = pd.get('production_table', pd) if isinstance(pd, dict) else pd
                    print(f"[Visuals] Loaded legacy production table from Firestore for project {project_id}")
                    return jsonify({'success': True, 'production_table': pt})
        except Exception as e:
            print(f"[Visuals] Firestore lookup failed, falling back to .tmp/: {e}")

        # Priority 2: .tmp/ folder scoped to project_id only
        search_dir = os.path.join(TMP_DIR, project_id)
        pattern = os.path.join(search_dir, "production_table_*.json")
        files = glob_module.glob(pattern)
        if not files:
            return jsonify({'error': 'No production table found. Generate one in Phase 3 first.'}), 404

        # Sort by modification time, most recent first
        latest = max(files, key=os.path.getmtime)
        with open(latest, "r") as f:
            data = json.load(f)

        # Unwrap if saved file has {success, production_table: {...}} structure
        pt = data.get('production_table', data) if isinstance(data, dict) else data

        print(f"[Visuals] Loaded latest production table from .tmp/: {os.path.basename(latest)}")
        return jsonify({'success': True, 'production_table': pt})

    except Exception as e:
        return safe_error_response(e)


@app.route('/api/refresh-project-urls', methods=['POST'])
@require_auth
@limiter.limit("400/hour")
def refresh_project_urls():
    """Re-sign every asset URL for a project so the UI works after the 4-hour expiry.

    Accepts: { project_id, blob_paths: [str], scene_ids: [str] }
    Returns: { blobs: {path: url}, scenes: {sid: url}, videos: {sid: url} }

    Direct blob_path → URL is used for assets where we persist the path
    (portraits, style refs, character images). Scene images/videos are matched
    by listing the project's storage prefix (we don't persist their blob_path).
    """
    try:
        if not bucket:
            return jsonify({'error': 'Firebase Storage not configured'}), 500

        data = request.json or {}
        project_id = data.get('project_id')
        blob_paths = data.get('blob_paths') or []
        scene_ids = data.get('scene_ids') or []

        blobs_out = {}
        for bp in blob_paths:
            if not isinstance(bp, str):
                continue
            if not (bp.startswith('references/') or bp.startswith('images/') or bp.startswith('videos/')):
                continue
            try:
                blob = bucket.blob(bp)
                if blob.exists():
                    url = _generate_signed_url(blob)
                    if url:
                        blobs_out[bp] = url
            except Exception as e:
                print(f"[Refresh] blob_path failed for {bp}: {e}")

        scenes_out = {}
        videos_out = {}
        if project_id and scene_ids:
            img_blobs = list(bucket.list_blobs(prefix=f"images/{project_id}/scene_"))
            vid_blobs = list(bucket.list_blobs(prefix=f"videos/{project_id}/scene_"))
            for sid in scene_ids:
                safe_id = str(sid).replace("/", "_").replace(" ", "_")
                prefix = f"scene_{safe_id}_"
                imgs = [b for b in img_blobs if b.name.split('/')[-1].startswith(prefix)]
                if imgs:
                    imgs.sort(key=lambda b: b.name)
                    url = _generate_signed_url(imgs[-1])
                    if url:
                        scenes_out[str(sid)] = url
                vids = [b for b in vid_blobs if b.name.split('/')[-1].startswith(prefix)]
                if vids:
                    vids.sort(key=lambda b: b.name)
                    url = _generate_signed_url(vids[-1])
                    if url:
                        videos_out[str(sid)] = url

        print(f"[Refresh] project={project_id} blobs={len(blobs_out)}/{len(blob_paths)} "
              f"scenes={len(scenes_out)}/{len(scene_ids)} videos={len(videos_out)}/{len(scene_ids)}")
        return jsonify({'blobs': blobs_out, 'scenes': scenes_out, 'videos': videos_out})

    except Exception as e:
        return safe_error_response(e)


@app.route('/api/visuals/sync-storage-images', methods=['POST'])
@require_auth
@limiter.limit("200/hour")
def visuals_sync_storage_images():
    """Scan Firebase Storage for orphaned images and link them back to project scenes.
    
    Accepts: { scene_ids: ["1", "2", ...] }
    Returns: { matches: { "1": "https://...", "2": "https://..." } }
    
    For each scene_id, searches for blobs matching 'images/scene_{id}_*' and returns
    the most recent one (by name/timestamp). This recovers images that were uploaded
    to Storage but whose URLs were never saved to the database (e.g., page refresh
    during batch generation).
    """
    try:
        if not bucket:
            return jsonify({'error': 'Firebase Storage not configured'}), 500

        data = request.json
        scene_ids = data.get('scene_ids', [])
        project_id = data.get('project_id')
        
        if not scene_ids:
            return jsonify({'matches': {}})

        matches = {}
        # List all blobs in images/ prefix (scoped by project if provided)
        search_prefix = f"images/{project_id}/scene_" if project_id else "images/scene_"
        all_blobs = list(bucket.list_blobs(prefix=search_prefix))

        for sid in scene_ids:
            safe_id = str(sid).replace("/", "_").replace(" ", "_")
            prefix = f"scene_{safe_id}_"
            # Find all blobs matching this scene
            scene_blobs = [b for b in all_blobs if b.name.split('/')[-1].startswith(prefix)]
            if scene_blobs:
                # Sort by name (contains timestamp) → last = most recent
                scene_blobs.sort(key=lambda b: b.name)
                latest = scene_blobs[-1]
                url = _generate_signed_url(latest)
                if url:
                    matches[str(sid)] = url

        print(f"[Sync] Found {len(matches)} orphaned images for {len(scene_ids)} scene IDs")
        return jsonify({'matches': matches})

    except Exception as e:
        return safe_error_response(e)


def _build_scene_history(folder, scene_ids, project_id):
    """Shared scanner for scene-image-history and scene-video-history.

    Looks for blobs at `{folder}/{project_id}/scene_{id}_{ts}.ext` (or legacy
    `{folder}/scene_*` when no project_id), groups by scene_id, returns
    {sid: [{url, timestamp, filename}, ...]} sorted newest-first.
    """
    history = {}
    all_blobs = (list(bucket.list_blobs(prefix=f"{folder}/{project_id}/scene_"))
                 if project_id
                 else list(bucket.list_blobs(prefix=f"{folder}/scene_")))

    def _entries(blobs, prefix):
        blobs.sort(key=lambda b: b.name, reverse=True)
        out = []
        for blob in blobs:
            filename = blob.name.split('/')[-1]
            ts_part = filename.replace(prefix, "").rsplit(".", 1)[0]
            try:
                timestamp = int(ts_part)
            except ValueError:
                timestamp = 0
            signed_url = _generate_signed_url(blob)
            if signed_url:
                out.append({
                    'url': signed_url,
                    'timestamp': timestamp,
                    'filename': filename,
                })
        return out

    for sid in scene_ids:
        safe_id = str(sid).replace("/", "_").replace(" ", "_")
        prefix = f"{safe_id}_" if safe_id.startswith("scene_") else f"scene_{safe_id}_"
        scene_blobs = [b for b in all_blobs if b.name.split('/')[-1].startswith(prefix)]
        if scene_blobs:
            seen = {}
            for b in scene_blobs:
                fn = b.name.split('/')[-1]
                if fn not in seen:
                    seen[fn] = b
            history[str(sid)] = _entries(list(seen.values()), prefix)
    return history


@app.route('/api/visuals/scene-image-history', methods=['POST'])
@require_auth
@limiter.limit("200/hour")
def visuals_scene_image_history():
    """Return ALL generated images per scene from Firebase Storage.

    Accepts: { scene_ids: ["1", "2", ...], project_id: "optional" }
    Returns: { history: { "1": [{url, timestamp, filename}, ...], "2": [...] } }

    Images are sorted newest-first. The timestamp is extracted from the filename
    pattern: scene_{safe_id}_{unix_timestamp}.{ext}
    """
    try:
        if not bucket:
            return jsonify({'error': 'Firebase Storage not configured'}), 500

        data = request.json or {}
        scene_ids = data.get('scene_ids', [])
        project_id = data.get('project_id')

        if not scene_ids:
            return jsonify({'history': {}})

        history = _build_scene_history('images', scene_ids, project_id)
        total = sum(len(v) for v in history.values())
        print(f"[History] Returned image history for {len(history)} scenes ({total} total images)")
        return jsonify({'history': history})

    except Exception as e:
        return safe_error_response(e)


@app.route('/api/visuals/scene-video-history', methods=['POST'])
@require_auth
@limiter.limit("200/hour")
def visuals_scene_video_history():
    """Return ALL generated videos per scene from Firebase Storage.

    Mirror of scene-image-history but for videos. Same filename pattern:
    `videos/{project_id}/scene_{id}_{ts}.mp4` — populated by _rehost_kie_results
    when the scene generates via Studio Engine video models.
    """
    try:
        if not bucket:
            return jsonify({'error': 'Firebase Storage not configured'}), 500

        data = request.json or {}
        scene_ids = data.get('scene_ids', [])
        project_id = data.get('project_id')

        if not scene_ids:
            return jsonify({'history': {}})

        history = _build_scene_history('videos', scene_ids, project_id)
        total = sum(len(v) for v in history.values())
        print(f"[History] Returned video history for {len(history)} scenes ({total} total videos)")
        return jsonify({'history': history})

    except Exception as e:
        return safe_error_response(e)


@app.route('/api/visuals/generate-image', methods=['POST'])
@require_auth
@limiter.limit("600/hour")
def visuals_generate_image():
    """Generate a single scene image using Gemini image models."""
    try:
        data = request.json
        scene_id = data.get('scene_id')
        prompt, err = validate_input(data, 'prompt', max_length=10000)
        if err:
            return jsonify({'error': err}), 400
        if not scene_id:
            return jsonify({'error': 'scene_id is required'}), 400

        model = data.get('model', 'gemini-3-pro-image-preview')
        aspect_ratio = data.get('aspect_ratio', '16:9')
        resolution = data.get('resolution', '2K')
        style_images = [r for r in (resolve_image_input(img) for img in data.get('style_images', []) if img) if r]
        characters = data.get('characters', [])
        # Resolve character image URLs to base64 (filter out any that fail to resolve)
        for char in (characters or []):
            if 'images' in char:
                char['images'] = [r for r in (resolve_image_input(img) for img in char['images'] if img) if r]
        character_images = [r for r in (resolve_image_input(img) for img in data.get('character_images', []) if img) if r]
        location_refs = data.get('location_refs', [])
        for loc in (location_refs or []):
            if 'images' in loc:
                loc['images'] = [r for r in (resolve_image_input(img) for img in loc['images'] if img) if r]
        additional_context = data.get('additional_context', '')
        style_mode = data.get('style_mode', 'art_only')

        char_count = len(characters) if characters else 0
        char_img_count = sum(len(c.get('images', [])) for c in characters) if characters else len(character_images or [])
        loc_count = len(location_refs) if location_refs else 0
        print(f"[Visuals] Generating image for scene {scene_id}: "
              f"{len(style_images or [])} style refs, {char_count} characters "
              f"({char_img_count} char images), {loc_count} locations, style_mode={style_mode}"
              f"{', context=' + repr(additional_context[:50]) if additional_context else ''}")
        project_id = data.get('project_id')
        result = generate_scene_image(
            prompt=prompt,
            model_name=model,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            style_images=style_images or None,
            characters=characters or None,
            character_images=character_images or None,
            location_refs=location_refs or None,
            additional_context=additional_context,
            style_mode=style_mode,
            scene_id=scene_id,
            api_key=g.api_key,
            uid=g.uid, project_id=project_id,
        )

        if "error" in result:
            return jsonify({'error': result['error']}), 500

        if result.get("success") and "local_path" in result:
            public_url = upload_to_storage(result["local_path"], "images", project_id=project_id)
            if public_url:
                result["image_url"] = public_url
            del result["local_path"]

        return jsonify(result)

    except Exception as e:
        return safe_error_response(e)


@app.route('/api/visuals/edit-image', methods=['POST'])
@require_auth
@limiter.limit("600/hour")
def visuals_edit_image():
    """Edit an existing scene image using Gemini's image-to-image capability."""
    try:
        data = request.json
        scene_id = data.get('scene_id')
        source_image = data.get('source_image')
        edit_prompt, err = validate_input(data, 'edit_prompt', max_length=5000)
        if err:
            return jsonify({'error': err}), 400
        if not scene_id:
            return jsonify({'error': 'scene_id is required'}), 400
        if not source_image:
            return jsonify({'error': 'source_image is required'}), 400

        # Resolve source image (signed URL → base64, or pass through if already base64)
        resolved_source = resolve_image_input(source_image)
        if not resolved_source:
            return jsonify({'error': 'Could not resolve source image (URL may be expired)'}), 400

        model = data.get('model', 'gemini-3-pro-image-preview')
        aspect_ratio = data.get('aspect_ratio', '16:9')

        project_id = data.get('project_id')
        print(f"[Visuals] Editing image for scene {scene_id} with {model}: {edit_prompt[:80]}")
        result = edit_scene_image(
            source_image_data=resolved_source,
            edit_prompt=edit_prompt,
            model_name=model,
            aspect_ratio=aspect_ratio,
            scene_id=scene_id,
            api_key=g.api_key,
            uid=g.uid, project_id=project_id,
        )

        if "error" in result:
            return jsonify({'error': result['error']}), 500

        if result.get("success") and "local_path" in result:
            public_url = upload_to_storage(result["local_path"], "images", project_id=project_id)
            if public_url:
                result["image_url"] = public_url
            del result["local_path"]

        return jsonify(result)

    except Exception as e:
        return safe_error_response(e)


@app.route('/api/visuals/generate-batch-images', methods=['POST'])
@require_auth
@limiter.limit("600/hour")
def visuals_generate_batch_images():
    """Generate images for multiple scenes in parallel."""
    try:
        data = request.json
        scenes = data.get('scenes', [])
        global_config = data.get('global_config', {})

        if not scenes:
            return jsonify({'error': 'No scenes provided'}), 400

        # Resolve any Storage URLs to base64 in global config (filter out failed resolves)
        if global_config.get('style_images'):
            global_config['style_images'] = [r for r in (resolve_image_input(img) for img in global_config['style_images'] if img) if r]
        if global_config.get('character_images'):
            global_config['character_images'] = [r for r in (resolve_image_input(img) for img in global_config['character_images'] if img) if r]
        for char in (global_config.get('characters') or []):
            if 'images' in char:
                char['images'] = [r for r in (resolve_image_input(img) for img in char['images'] if img) if r]
        # Also resolve per-scene characters
        for scene in scenes:
            for char in (scene.get('characters') or []):
                if 'images' in char:
                    char['images'] = [r for r in (resolve_image_input(img) for img in char['images'] if img) if r]

        api_key = g.api_key
        tracking_uid = g.uid
        batch_project_id = data.get('project_id')

        def generate_one(scene):
            sid = scene.get('scene_id')
            scene_characters = scene.get('characters') or global_config.get('characters')
            return generate_scene_image(
                prompt=scene.get('prompt', ''),
                model_name=scene.get('model') or global_config.get('model', 'gemini-3-pro-image-preview'),
                aspect_ratio=scene.get('aspect_ratio') or global_config.get('aspect_ratio', '16:9'),
                resolution=scene.get('resolution') or global_config.get('resolution', '2K'),
                style_images=global_config.get('style_images') or None,
                characters=scene_characters or None,
                character_images=global_config.get('character_images') or None,
                additional_context=global_config.get('additional_context', ''),
                style_mode=global_config.get('style_mode', 'art_only'),
                scene_id=sid,
                api_key=api_key,
                uid=tracking_uid, project_id=batch_project_id,
            )

        print(f"[Visuals] Batch generating {len(scenes)} scene images (max 5 parallel)")
        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(generate_one, s): s for s in scenes}
            for future in as_completed(futures):
                try:
                    res = future.result()
                    if res.get("success") and "local_path" in res:
                        project_id = data.get('project_id')
                        public_url = upload_to_storage(res["local_path"], "images", project_id=project_id)
                        if public_url:
                            res["image_url"] = public_url
                        del res["local_path"]
                    results.append(res)
                except Exception as exc:
                    scene = futures[future]
                    results.append({"error": str(exc), "scene_id": scene.get('scene_id')})

        # Sort results by scene_id for consistent ordering
        results.sort(key=lambda r: str(r.get('scene_id', '')))
        print(f"[Visuals] Batch complete: {sum(1 for r in results if r.get('success'))} succeeded, "
              f"{sum(1 for r in results if 'error' in r)} failed")

        return jsonify({'results': results})

    except Exception as e:
        return safe_error_response(e)


# KIE video model keys that support image-to-video
KIE_VIDEO_MODELS = {"kling-3.0", "kling-2.6", "sora-2", "grok-imagine-video", "wan-2.6", "hailuo-2.3", "midjourney-video", "seedance-2", "seedance-2-fast", "topaz-video-upscale"}


def _is_kie_video_model(model: str) -> bool:
    """Check if a model key is a KIE video model (not Veo)."""
    return model in KIE_VIDEO_MODELS


def _snap_kie_duration(model: str, duration: int) -> str:
    """Snap a duration to the nearest valid value for a KIE video model."""
    from kie_client import KIE_MODELS
    model_info = KIE_MODELS.get(model, {})
    allowed = model_info.get("durations", [])
    if not allowed:
        return str(duration)
    # Find closest allowed duration
    allowed_ints = [int(d) for d in allowed]
    closest = min(allowed_ints, key=lambda d: abs(d - duration))
    return str(closest)


@app.route('/api/visuals/start-animation', methods=['POST'])
@require_auth
@limiter.limit("60/hour")
def visuals_start_animation():
    """Start video animation for a single scene (Veo or KIE models)."""
    try:
        data = request.json
        scene_id = data.get('scene_id')
        image_url = data.get('image_url', '')
        prompt, err = validate_input(data, 'prompt', max_length=10000)
        if err:
            return jsonify({'error': err}), 400

        if not scene_id:
            return jsonify({'error': 'scene_id is required'}), 400

        model = data.get('model', 'veo-3.1-generate-preview')
        aspect_ratio = data.get('aspect_ratio', '16:9')
        duration = data.get('duration', 6)
        resolution = data.get('resolution', '720p')

        # ── Topaz Video Upscaler (video-to-video, no image upload) ──
        if model == 'topaz-video-upscale':
            if not g.kie_api_key:
                return jsonify({'error': 'Kie.ai API key is required for Topaz. Add it in Settings.'}), 400
            video_url = data.get('video_url', '')
            if not video_url:
                return jsonify({'error': 'video_url is required for Topaz upscaling (animate a scene first)'}), 400
            upscale_factor = str(data.get('upscale_factor', '2'))
            print(f"[Visuals/Topaz] Upscaling video for scene {scene_id} with factor={upscale_factor}")
            gen_result = kie_create_task(model, '', g.kie_api_key, video_url=video_url, upscale_factor=upscale_factor)
            if not gen_result.get('success'):
                return jsonify({'error': f"Topaz task creation failed: {gen_result.get('error', 'unknown')}"}), 500
            task_id = gen_result.get('taskId')
            return jsonify({
                'status': 'in_progress',
                'operation_name': f"kie:{task_id}",
                'scene_id': scene_id,
                'provider': 'kie',
            })

        # ── Seedance multi-reference params ──
        seedance_mode = data.get('seedance_mode', 'first_frame')
        generate_audio = data.get('generate_audio', True)
        last_frame_url = data.get('last_frame_url')
        ref_image_urls = data.get('ref_image_urls') or []
        ref_video_urls = data.get('ref_video_urls') or []
        ref_audio_urls = data.get('ref_audio_urls') or []

        is_multimodal = model in ('seedance-2', 'seedance-2-fast') and seedance_mode == 'multimodal'

        if not is_multimodal and not image_url:
            return jsonify({'error': 'image_url is required (generate an image first)'}), 400

        # ── KIE Video Models ──
        if _is_kie_video_model(model):
            if not g.kie_api_key:
                return jsonify({'error': 'Kie.ai API key is required for this model. Add it in Settings.'}), 400

            print(f"[Visuals/KIE] Starting animation for scene {scene_id} with model={model}, mode={seedance_mode}")

            # Step 1: Upload first-frame image to Kie.ai (skip for multimodal mode)
            kie_image_url = None
            if not is_multimodal and image_url:
                upload_result = kie_upload_image(image_url, g.kie_api_key)
                if not upload_result.get('success'):
                    return jsonify({'error': f"Failed to upload image to Kie.ai: {upload_result.get('error', 'unknown')}"}), 500
                kie_image_url = upload_result['url']

            # Step 2: Create generation task
            is_mj = model.startswith('midjourney-')
            snapped_duration = _snap_kie_duration(model, int(duration))
            task_params = {
                'aspect_ratio': aspect_ratio,
                'duration': snapped_duration,
                'resolution': resolution,
            }
            # Remove params not applicable to certain models
            if is_mj:
                task_params.pop('resolution', None)
                task_params.pop('duration', None)

            # ── Seedance-specific params ──
            if model in ('seedance-2', 'seedance-2-fast'):
                task_params['audio'] = generate_audio
                if seedance_mode == 'first_last_frame' and last_frame_url:
                    task_params['last_frame_url'] = last_frame_url
                elif seedance_mode == 'multimodal':
                    # Upload ref images to Kie.ai CDN; pass ref videos/audio directly
                    if ref_image_urls:
                        uploaded_refs = []
                        for img_url in ref_image_urls[:9]:
                            up = kie_upload_image(img_url, g.kie_api_key)
                            if up.get('success'):
                                uploaded_refs.append(up['url'])
                        task_params['ref_image_urls'] = uploaded_refs
                    if ref_video_urls:
                        task_params['ref_video_urls'] = [u for u in ref_video_urls[:3] if u]
                    if ref_audio_urls:
                        task_params['ref_audio_urls'] = [u for u in ref_audio_urls[:3] if u]

            print(f"[Visuals/KIE] Task params: {task_params}")

            image_args = [kie_image_url] if kie_image_url else None
            if is_mj:
                gen_result = kie_mj_create_task(model, prompt, g.kie_api_key,
                                                 image_urls=image_args, **task_params)
            else:
                gen_result = kie_create_task(model, prompt, g.kie_api_key,
                                             image_urls=image_args, **task_params)

            if not gen_result.get('success'):
                return jsonify({'error': f"KIE task creation failed: {gen_result.get('error', 'unknown')}"}), 500

            task_id = gen_result.get('taskId')
            print(f"[Visuals/KIE] Task created: {task_id}")

            return jsonify({
                'status': 'in_progress',
                'operation_name': f"kie:{task_id}",  # Prefix to distinguish from Veo operations
                'scene_id': scene_id,
                'provider': 'kie',
                'is_midjourney': is_mj,
            })

        # ── Veo Models (existing flow) ──
        # Resolve image URL to local file path
        image_path = ensure_local_image(image_url)
        if not image_path:
            return jsonify({'error': f'Image file could not be downloaded/resolved: {image_url}'}), 404

        print(f"[Visuals] Starting animation for scene {scene_id}")
        result = start_video_generation(
            image_path=image_path,
            prompt=prompt,
            model_name=model,
            aspect_ratio=aspect_ratio,
            duration=duration,
            resolution=resolution,
            scene_id=scene_id,
            api_key=g.api_key,
            uid=g.uid, project_id=data.get('project_id'),
        )

        if "error" in result:
            return jsonify({'error': result['error']}), 500

        return jsonify(result)

    except Exception as e:
        return safe_error_response(e)


@app.route('/api/visuals/poll-animation', methods=['POST'])
@require_auth
@limiter.limit("200/hour")
def visuals_poll_animation():
    """Poll a video animation operation for completion (Veo or KIE)."""
    try:
        data = request.json
        operation_name = data.get('operation_name')
        scene_id = data.get('scene_id')

        if not operation_name:
            return jsonify({'error': 'operation_name is required'}), 400

        # ── KIE Tasks (prefixed with "kie:") ──
        if operation_name.startswith("kie:"):
            if not g.kie_api_key:
                return jsonify({'error': 'Kie.ai API key not configured'}), 400

            task_id = operation_name[4:]  # Strip "kie:" prefix
            is_mj = data.get('is_midjourney', False)
            project_id = data.get('project_id')

            if is_mj:
                poll_result = kie_mj_poll_task(task_id, g.kie_api_key)
            else:
                poll_result = kie_poll_task(task_id, g.kie_api_key)

            status = poll_result.get('status', 'processing')

            if status == 'completed' and poll_result.get('result_urls'):
                # Download from Kie.ai and upload to Firebase Storage
                video_url = None
                for kie_url in poll_result['result_urls']:
                    local_path = kie_download_result(kie_url, task_id)
                    if local_path:
                        try:
                            firebase_url = upload_to_storage(local_path, "videos", project_id=project_id)
                            if firebase_url:
                                video_url = firebase_url
                                print(f"[Visuals/KIE] Video uploaded to Firebase: {firebase_url[:120]}")
                        finally:
                            try:
                                os.unlink(local_path)
                                os.rmdir(os.path.dirname(local_path))
                            except OSError:
                                pass
                    if not video_url:
                        video_url = kie_url  # Fallback to Kie URL (24hr expiry)

                return jsonify({
                    'status': 'completed',
                    'video_url': video_url,
                    'scene_id': scene_id,
                })

            elif status == 'failed':
                return jsonify({
                    'status': 'failed',
                    'error': poll_result.get('error', 'KIE video generation failed'),
                    'scene_id': scene_id,
                }), 500

            else:
                return jsonify({
                    'status': 'processing',
                    'progress': poll_result.get('progress'),
                    'scene_id': scene_id,
                })

        # ── Veo Operations (existing flow) ──
        result = poll_video_generation(
            operation_name=operation_name,
            scene_id=scene_id,
            api_key=g.api_key,
        )

        if result.get('status') == 'failed':
            return jsonify(result), 500

        project_id = data.get('project_id')
        if result.get('status') == 'completed' and "local_path" in result:
            public_url = upload_to_storage(result["local_path"], "videos", project_id=project_id)
            if public_url:
                result["video_url"] = public_url
            del result["local_path"]

        return jsonify(result)

    except Exception as e:
        return safe_error_response(e)


@app.route('/api/visuals/start-batch-animation', methods=['POST'])
@require_auth
@limiter.limit("60/hour")
def visuals_start_batch_animation():
    """Start video animation for multiple scenes (Veo or KIE, max 5 concurrent)."""
    try:
        data = request.json
        scenes = data.get('scenes', [])
        global_config = data.get('global_config', {})

        if not scenes:
            return jsonify({'error': 'No scenes provided'}), 400

        gemini_key = g.api_key
        kie_key = g.kie_api_key
        tracking_uid = g.uid
        batch_project_id = data.get('project_id')

        def start_one(scene):
            sid = scene.get('scene_id')
            image_url = scene.get('image_url', '')
            model = scene.get('model') or global_config.get('model', 'veo-3.1-generate-preview')
            ar = scene.get('aspect_ratio') or global_config.get('aspect_ratio', '16:9')
            dur = scene.get('duration', 6)
            res = scene.get('resolution') or global_config.get('resolution', '720p')

            if _is_kie_video_model(model):
                if not kie_key:
                    return {"error": "Kie.ai API key required for this model", "scene_id": sid}
                # Upload image to Kie.ai
                upload_result = kie_upload_image(image_url, kie_key)
                if not upload_result.get('success'):
                    return {"error": f"Image upload failed: {upload_result.get('error')}", "scene_id": sid}

                is_mj = model.startswith('midjourney-')
                snapped_dur = _snap_kie_duration(model, int(dur))
                task_params = {'aspect_ratio': ar, 'duration': snapped_dur, 'resolution': res}
                if is_mj:
                    task_params.pop('resolution', None)
                    task_params.pop('duration', None)

                if is_mj:
                    gen_result = kie_mj_create_task(model, scene.get('prompt', ''), kie_key,
                                                     image_urls=[upload_result['url']], **task_params)
                else:
                    gen_result = kie_create_task(model, scene.get('prompt', ''), kie_key,
                                                 image_urls=[upload_result['url']], **task_params)

                if not gen_result.get('success'):
                    return {"error": f"Task creation failed: {gen_result.get('error')}", "scene_id": sid}

                return {
                    'status': 'in_progress',
                    'operation_name': f"kie:{gen_result['taskId']}",
                    'scene_id': sid,
                    'provider': 'kie',
                    'is_midjourney': is_mj,
                }
            else:
                # Veo flow
                image_path = ensure_local_image(image_url)
                if not image_path:
                    return {"error": f"Image could not be resolved: {image_url}", "scene_id": sid}
                return start_video_generation(
                    image_path=image_path,
                    prompt=scene.get('prompt', ''),
                    model_name=model,
                    aspect_ratio=ar,
                    duration=dur,
                    resolution=res,
                    scene_id=sid,
                    api_key=gemini_key,
                    uid=tracking_uid, project_id=batch_project_id,
                )

        print(f"[Visuals] Batch starting animation for {len(scenes)} scenes (max 5 parallel)")
        operations = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(start_one, s): s for s in scenes}
            for future in as_completed(futures):
                try:
                    operations.append(future.result())
                except Exception as exc:
                    scene = futures[future]
                    operations.append({"error": str(exc), "scene_id": scene.get('scene_id')})

        operations.sort(key=lambda r: str(r.get('scene_id', '')))
        started = sum(1 for o in operations if o.get('status') == 'in_progress')
        print(f"[Visuals] Batch animation: {started} started, {len(operations) - started} failed")

        return jsonify({'operations': operations})

    except Exception as e:
        return safe_error_response(e)


@app.route('/video/<path:filename>')
def serve_video_file(filename):
    """Serve generated videos (local fallback when Storage upload fails)."""
    return send_from_directory(VIDEO_DIR, filename)


@app.route('/api/download-asset', methods=['GET'])
@require_auth
@limiter.limit("200/hour")
def download_asset():
    """Proxy download for Firebase Storage files.
    Fetches the file from the given URL and serves it as a download.
    This avoids CORS issues when downloading from Firebase Storage.
    """
    try:
        url = request.args.get('url', '')
        filename = request.args.get('filename', 'download')

        if not url:
            return jsonify({'error': 'url parameter is required'}), 400

        # Validate URL against allowlist (SSRF protection)
        try:
            validate_url(url)
        except ValueError as ve:
            return jsonify({'error': 'Invalid download URL'}), 400

        # Fetch the file
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            file_data = response.read()
            content_type = response.headers.get('Content-Type', 'application/octet-stream')

        return send_file(
            io.BytesIO(file_data),
            mimetype=content_type,
            as_attachment=True,
            download_name=filename,
        )

    except Exception as e:
        return safe_error_response(e)


@app.route('/api/visuals/download-all', methods=['GET'])
@require_auth
@limiter.limit("200/hour")
def download_all_assets():
    """Download all generated assets for a specific project as a zip file.
    Streams the zip to avoid loading everything into memory at once."""
    try:
        from flask import Response

        project_id = request.args.get('project_id')
        mode = request.args.get('mode', 'active')  # 'active' or 'all'
        if not project_id:
            return jsonify({'error': 'project_id is required'}), 400

        # Verify user owns this project
        project_doc = db.collection('users').document(g.uid).collection('projects').document(project_id).get()
        if not project_doc.exists:
            return jsonify({'error': 'Project not found'}), 404

        if not bucket:
            return jsonify({'error': 'Storage not configured'}), 500

        # Collect blob references first (lightweight — no downloads yet)
        image_blobs = list(bucket.list_blobs(prefix=f"images/{project_id}/"))
        video_blobs = list(bucket.list_blobs(prefix=f"videos/{project_id}/"))
        audio_blobs = list(bucket.list_blobs(prefix=f"audio/{project_id}/"))

        # If 'active' mode, keep only the latest image per scene
        if mode == 'active':
            scene_latest = {}
            for blob in image_blobs:
                fname = blob.name.split('/')[-1]
                if not fname.startswith('scene_'):
                    continue
                # Extract scene id: scene_{id}_{timestamp}.ext
                parts = fname.rsplit('_', 1)
                scene_key = parts[0] if len(parts) > 1 else fname
                if scene_key not in scene_latest or blob.name > scene_latest[scene_key].name:
                    scene_latest[scene_key] = blob
            image_blobs = list(scene_latest.values())

        total = len(image_blobs) + len(video_blobs) + len(audio_blobs)
        print(f"[Download] Building zip for project {project_id}: "
              f"{len(image_blobs)} images, {len(video_blobs)} videos, "
              f"{len(audio_blobs)} audio files (mode={mode})")

        # Build zip in memory but download blobs one at a time to reduce peak memory
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_STORED) as zf:  # STORED = no compression (faster, images already compressed)
            for blob in image_blobs:
                fname = blob.name.split('/')[-1]
                try:
                    data = blob.download_as_bytes()
                    zf.writestr(f"images/{fname}", data)
                except Exception as e:
                    print(f"[Download] Failed to download {blob.name}: {e}")

            for blob in video_blobs:
                fname = blob.name.split('/')[-1]
                try:
                    data = blob.download_as_bytes()
                    zf.writestr(f"videos/{fname}", data)
                except Exception as e:
                    print(f"[Download] Failed to download {blob.name}: {e}")

            for blob in audio_blobs:
                fname = blob.name.split('/')[-1]
                try:
                    data = blob.download_as_bytes()
                    zf.writestr(f"audio/{fname}", data)
                except Exception as e:
                    print(f"[Download] Failed to download {blob.name}: {e}")

        buffer.seek(0)
        print(f"[Download] Zip ready: {buffer.getbuffer().nbytes / 1024 / 1024:.1f} MB")

        # Get project title for filename
        project_data = project_doc.to_dict()
        title = project_data.get('title', 'project')
        safe_title = ''.join(c if c.isalnum() or c in ('-', '_', ' ') else '' for c in title)[:50].strip()
        zip_name = f"{safe_title}.zip" if safe_title else f"project_{project_id}.zip"

        return send_file(
            buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=zip_name,
        )

    except Exception as e:
        return safe_error_response(e)


# ────────────────────────────────────────────────────────────────
#  USAGE / COST DASHBOARD
# ────────────────────────────────────────────────────────────────

# Admin UIDs allowed to read (and later write) config/gemini_pricing.
# Seeded from ADMIN_UIDS env var, comma-separated.
_ADMIN_UIDS = set(filter(None, (os.environ.get('ADMIN_UIDS', '').split(','))))


def _parse_date_range(args):
    """Return (start_iso, end_iso) as YYYY-MM-DD strings.

    Defaults to last 30 days. Caps range at 366 days to protect read cost.
    """
    end_str = args.get('end')
    start_str = args.get('start')
    today = datetime.now().strftime('%Y-%m-%d')
    end = end_str or today
    if start_str:
        start = start_str
    else:
        start_dt = datetime.strptime(end, '%Y-%m-%d') - timedelta(days=30)
        start = start_dt.strftime('%Y-%m-%d')

    # Validate formats + sanity range.
    try:
        s_dt = datetime.strptime(start, '%Y-%m-%d')
        e_dt = datetime.strptime(end, '%Y-%m-%d')
    except ValueError:
        raise ValueError('start/end must be YYYY-MM-DD')
    if e_dt < s_dt:
        raise ValueError('end must be >= start')
    if (e_dt - s_dt).days > 366:
        raise ValueError('range must be <= 366 days')
    return start, end


def _list_rollups(uid, start, end):
    """Fetch all daily rollup docs for uid between start..end inclusive."""
    docs_ref = db.collection('users').document(uid).collection('cost_rollups')
    # Document IDs are the YYYY-MM-DD so we can range-query by id.
    snaps = docs_ref.where('day', '>=', start).where('day', '<=', end).stream()
    out = []
    for snap in snaps:
        data = snap.to_dict() or {}
        data.setdefault('day', snap.id)
        out.append(data)
    out.sort(key=lambda d: d.get('day', ''))
    return out


@app.route('/api/usage/account', methods=['GET'])
@require_auth
@limiter.limit("600/hour")
def usage_account():
    """Account-wide cost totals + by-tool / by-project breakdown for a date range."""
    try:
        start, end = _parse_date_range(request.args)
        rollups = _list_rollups(g.uid, start, end)

        total_usd = 0.0
        by_tool, by_project, by_model = {}, {}, {}

        def _merge(dst, src, keys=('calls', 'cost_usd', 'in_tokens', 'out_tokens',
                                   'cached_tokens', 'images', 'tts_chars', 'video_seconds')):
            for name, bucket in (src or {}).items():
                entry = dst.setdefault(name, {})
                for k in keys:
                    v = bucket.get(k)
                    if isinstance(v, (int, float)):
                        entry[k] = entry.get(k, 0) + v

        for doc in rollups:
            total_usd += float(doc.get('total_usd', 0) or 0)
            _merge(by_tool, doc.get('by_tool') or {})
            _merge(by_project, doc.get('by_project') or {})
            _merge(by_model, doc.get('by_model') or {})

        return jsonify({
            'start': start,
            'end': end,
            'days': len(rollups),
            'total_usd': round(total_usd, 6),
            'by_tool': by_tool,
            'by_project': by_project,
            'by_model': by_model,
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/usage/trend', methods=['GET'])
@require_auth
@limiter.limit("600/hour")
def usage_trend():
    """Ordered daily series for the trend chart.

    Query: ?days=30 (default) or explicit ?start=&end=. Missing days are
    filled with zeros so the chart doesn't have gaps.
    """
    try:
        if request.args.get('start') or request.args.get('end'):
            start, end = _parse_date_range(request.args)
        else:
            days = min(max(int(request.args.get('days', 30)), 1), 366)
            end_dt = datetime.now()
            start_dt = end_dt - timedelta(days=days - 1)
            start = start_dt.strftime('%Y-%m-%d')
            end = end_dt.strftime('%Y-%m-%d')

        rollups = {d['day']: d for d in _list_rollups(g.uid, start, end)}

        series = []
        cursor = datetime.strptime(start, '%Y-%m-%d')
        end_dt = datetime.strptime(end, '%Y-%m-%d')
        while cursor <= end_dt:
            day = cursor.strftime('%Y-%m-%d')
            doc = rollups.get(day, {})
            by_tool = doc.get('by_tool') or {}
            tool_costs = {t: round(float((by_tool.get(t) or {}).get('cost_usd', 0) or 0), 6)
                          for t in ('text', 'image', 'imagen', 'tts', 'veo')}
            series.append({
                'day': day,
                'total_usd': round(float(doc.get('total_usd', 0) or 0), 6),
                'by_tool': tool_costs,
            })
            cursor += timedelta(days=1)

        return jsonify({'start': start, 'end': end, 'series': series})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/usage/project/<project_id>', methods=['GET'])
@require_auth
@limiter.limit("600/hour")
def usage_project(project_id):
    """Per-project breakdown: totals + last 100 events."""
    try:
        start, end = _parse_date_range(request.args)
        if not project_id or '/' in project_id:
            return jsonify({'error': 'invalid project_id'}), 400

        rollups = _list_rollups(g.uid, start, end)

        total_usd = 0.0
        by_tool = {}
        for doc in rollups:
            bp = (doc.get('by_project') or {}).get(project_id) or {}
            total_usd += float(bp.get('cost_usd', 0) or 0)

        # Recent events for this project (from the cost_events collection)
        events_ref = (
            db.collection('users').document(g.uid).collection('cost_events')
              .where('project_id', '==', project_id)
              .where('day', '>=', start).where('day', '<=', end)
              .limit(100)
        )
        events = []
        for snap in events_ref.stream():
            data = snap.to_dict() or {}
            # Serialize timestamp to ISO if present
            ts = data.get('ts')
            if hasattr(ts, 'isoformat'):
                data['ts'] = ts.isoformat()
            # Aggregate by_tool from events (rollups don't slice per project × tool)
            tool = data.get('tool', 'unknown')
            bucket = by_tool.setdefault(tool, {'calls': 0, 'cost_usd': 0.0})
            bucket['calls'] += 1
            bucket['cost_usd'] += float(data.get('cost_usd', 0) or 0)
            events.append(data)

        # Sort events newest first by day+ts
        events.sort(key=lambda e: (e.get('day', ''), str(e.get('ts', ''))), reverse=True)

        return jsonify({
            'project_id': project_id,
            'start': start,
            'end': end,
            'total_usd': round(total_usd, 6),
            'by_tool': {k: {**v, 'cost_usd': round(v['cost_usd'], 6)} for k, v in by_tool.items()},
            'events': events,
            'event_count': len(events),
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/admin/pricing', methods=['GET'])
@require_auth
@limiter.limit("60/hour")
def admin_pricing():
    """Read-only: return current pricing doc. Gated by ADMIN_UIDS."""
    try:
        if g.uid not in _ADMIN_UIDS:
            return jsonify({'error': 'forbidden'}), 403
        import pricing as _pricing
        return jsonify({'pricing': _pricing.load_pricing(force=True)})
    except Exception as e:
        return safe_error_response(e)


if __name__ == '__main__':
    os.makedirs(GENERATED_DIR, exist_ok=True)
    os.makedirs(AUDIO_DIR, exist_ok=True)
    os.makedirs(VIDEO_DIR, exist_ok=True)
    os.makedirs(TMP_DIR, exist_ok=True)
    app.run(debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true', port=int(os.environ.get('PORT', 8080)))
