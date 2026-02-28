import os
import sys
import io
import json
import glob as glob_module
import zipfile
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, render_template, request, jsonify, send_from_directory, send_file, g
import traceback
import firebase_admin
from firebase_admin import credentials, auth, firestore

# Ensure the execution directory is in the Python path
sys.path.insert(0, os.path.dirname(__file__))
from gemini_client import (generate_image_content, generate_tts, generate_content,
                           analyze_style_from_images, analyze_style_from_text,
                           expand_creative_direction, refine_creative_direction,
                           generate_scene_image,
                           start_video_generation, poll_video_generation)
from research_templates import (get_all_templates_metadata, get_template, build_research_queries,
                                build_title_suggestions_prompt, AUDIENCE_PROFILES, TONE_DEFINITIONS,
                                FORMAT_PRESETS, VIEWER_OUTCOMES)
from research_scriptwriter import build_research_dossier, generate_narration, generate_production_table, auto_suggest_tone, regenerate_beats, start_deep_research, poll_deep_research
from youtube_utils import get_transcript, analyze_style

# Paths relative to this script's location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
UI_DIR = os.path.join(PROJECT_DIR, "ui")
GENERATED_DIR = os.path.join(PROJECT_DIR, "generated_images")
AUDIO_DIR = os.path.join(PROJECT_DIR, "generated_audio")
VIDEO_DIR = os.path.join(PROJECT_DIR, "generated_videos")
TMP_DIR = os.path.join(PROJECT_DIR, ".tmp")
DEBUG_SAVE_TMP = os.environ.get('DEBUG_SAVE_TMP', 'true').lower() == 'true'

# ── Firebase Initialization ──
SERVICE_ACCOUNT_PATH = os.path.join(PROJECT_DIR, "firebase-service-account.json")
try:
    with open(SERVICE_ACCOUNT_PATH) as f:
        _service_acc = json.load(f)
        _project_id = _service_acc.get("project_id", "gen-lang-client-0854991687")
except Exception:
    _project_id = "gen-lang-client-0854991687"

bucket_name = f"{_project_id}.firebasestorage.app"

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

def upload_to_storage(local_path, remote_folder, project_id=None):
    """Uploads a local file to Firebase Storage and returns the public URL."""
    if not bucket or not os.path.exists(local_path):
        return None
    try:
        filename = os.path.basename(local_path)
        path_prefix = f"{remote_folder}/{project_id}" if project_id else remote_folder
        blob = bucket.blob(f"{path_prefix}/{filename}")
        blob.upload_from_filename(local_path)
        blob.make_public()
        return blob.public_url
    except Exception as e:
        print(f"[Storage] Failed to upload {local_path}: {e}")
        return None

import urllib.request

def ensure_local_image(image_url):
    """Ensure the image exists locally. If remote, download it."""
    filename = image_url.split("/")[-1].split("?")[0]
    image_path = os.path.join(GENERATED_DIR, filename)
    if not os.path.exists(image_path):
        if image_url.startswith("http"):
            try:
                print(f"[Storage] Downloading missing local file from {image_url}")
                urllib.request.urlretrieve(image_url, image_path)
            except Exception as e:
                print(f"[Storage] Failed to download {image_url}: {e}")
                return None
        else:
            return None
    return image_path


app = Flask(__name__, static_url_path='', static_folder=UI_DIR, template_folder=UI_DIR)


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
            return jsonify({'error': f'Invalid auth token: {str(e)}'}), 401

        # Fetch user's Gemini API key from Firestore
        user_doc = db.collection('users').document(g.uid).get()
        if user_doc.exists:
            g.api_key = user_doc.to_dict().get('gemini_api_key')
        else:
            g.api_key = None

        # Fall back to server-side key if user hasn't set one
        if not g.api_key:
            g.api_key = os.getenv("GEMINI_API_KEY")

        return f(*args, **kwargs)
    return decorated


@app.route('/')
def index():
    return render_template('index.html')


# ────────────────────────────────────────────────────────────────
#  API KEY MANAGEMENT
# ────────────────────────────────────────────────────────────────

@app.route('/api/save-api-key', methods=['POST'])
@require_auth
def save_api_key():
    """Save or update the user's Gemini API key in Firestore."""
    try:
        data = request.json
        api_key = data.get('api_key', '').strip()

        if not api_key:
            return jsonify({'error': 'API key is required'}), 400

        db.collection('users').document(g.uid).set(
            {'gemini_api_key': api_key}, merge=True
        )

        return jsonify({'success': True})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/check-api-key', methods=['GET'])
@require_auth
def check_api_key():
    """Check if the authenticated user has a Gemini API key saved."""
    has_key = bool(g.api_key)
    return jsonify({'has_key': has_key})


# ────────────────────────────────────────────────────────────────
#  IMAGE GENERATION
# ────────────────────────────────────────────────────────────────

@app.route('/api/generate-image', methods=['POST'])
@require_auth
def generate_image_route():
    try:
        data = request.json
        prompt = data.get('prompt')
        model = data.get('model')  # optional: specific model selection
        if not prompt:
            return jsonify({'error': 'Prompt is required'}), 400

        print(f"Generating image for prompt: {prompt} (model: {model or 'auto'})")
        image_path = generate_image_content(prompt, model_name=model, api_key=g.api_key)

        if not image_path or (isinstance(image_path, str) and image_path.startswith("Error")):
            return jsonify({'error': image_path or 'Image generation returned no result'}), 500

        project_id = data.get('project_id')
        public_url = upload_to_storage(image_path, "images", project_id=project_id)
        image_url = public_url if public_url else f'/generated/{os.path.basename(image_path)}'

        return jsonify({'image_url': image_url})

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/generated/<path:filename>')
def serve_generated_file(filename):
    return send_from_directory(GENERATED_DIR, filename)


# ────────────────────────────────────────────────────────────────
#  TTS GENERATION
# ────────────────────────────────────────────────────────────────

@app.route('/api/generate-tts', methods=['POST'])
@require_auth
def generate_tts_route():
    try:
        data = request.json
        text = data.get('text')
        voice = data.get('voice', 'Kore')
        style_instructions = data.get('style_instructions', '')

        if not text:
            return jsonify({'error': 'Text is required'}), 400

        print(f"Generating TTS for text ({len(text)} chars), voice={voice}")
        audio_path = generate_tts(text, voice_name=voice, style_instructions=style_instructions, api_key=g.api_key)

        if not audio_path or (isinstance(audio_path, str) and audio_path.startswith("Error")):
            return jsonify({'error': audio_path or 'TTS generation returned no result'}), 500

        project_id = data.get('project_id')
        public_url = upload_to_storage(audio_path, "audio", project_id=project_id)
        audio_url = public_url if public_url else f'/audio/{os.path.basename(audio_path)}'

        return jsonify({'audio_url': audio_url})

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/audio/<path:filename>')
def serve_audio_file(filename):
    return send_from_directory(AUDIO_DIR, filename)


# ────────────────────────────────────────────────────────────────
#  STYLE ANALYSIS (VISION)
# ────────────────────────────────────────────────────────────────

@app.route('/api/analyze-style-images', methods=['POST'])
@require_auth
def analyze_style_images_route():
    """
    Analyze visual style from 1-4 uploaded images using Gemini Vision.
    Accepts: { images: [base64_data_uri_1, base64_data_uri_2, ...] }
    Returns: { style_analysis: {style_summary, style_intent, prompt_schema} }
    """
    try:
        data = request.json
        images = data.get('images', [])

        if not images or len(images) == 0:
            return jsonify({'error': 'At least one image is required'}), 400

        if len(images) > 4:
            return jsonify({'error': 'Maximum 4 images allowed'}), 400

        print(f"[Style Analysis] Analyzing {len(images)} images...")
        style_analysis = analyze_style_from_images(images, api_key=g.api_key)

        if not style_analysis or (isinstance(style_analysis, str) and style_analysis.startswith("Error")):
            return jsonify({'error': style_analysis or 'Style analysis returned no result'}), 500

        summary = style_analysis.get('style_summary', '') if isinstance(style_analysis, dict) else str(style_analysis)[:100]
        print(f"[Style Analysis] Complete: {summary}")
        return jsonify({
            'success': True,
            'style_analysis': style_analysis
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/analyze-style-text', methods=['POST'])
@require_auth
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

        print(f"[Style Analysis from Text] Analyzing: '{description[:80]}...'")
        style_analysis = analyze_style_from_text(description, api_key=g.api_key)

        if not style_analysis or (isinstance(style_analysis, str) and style_analysis.startswith("Error")):
            return jsonify({'error': style_analysis or 'Style analysis returned no result'}), 500

        summary = style_analysis.get('style_summary', '') if isinstance(style_analysis, dict) else str(style_analysis)[:100]
        print(f"[Style Analysis from Text] Complete: {summary}")
        return jsonify({
            'success': True,
            'style_analysis': style_analysis
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ────────────────────────────────────────────────────────────────
#  CREATIVE DIRECTION
# ────────────────────────────────────────────────────────────────

@app.route('/api/expand-creative-direction', methods=['POST'])
@require_auth
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
            api_key=g.api_key
        )

        if isinstance(result, str) and result.startswith("Error"):
            return jsonify({'error': result}), 500

        print(f"[Creative Direction] Expanded: {result.get('direction_summary', '')[:80]}")
        return jsonify({'success': True, 'creative_direction': result})

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/refine-creative-direction', methods=['POST'])
@require_auth
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
            api_key=g.api_key
        )

        if isinstance(result, str) and result.startswith("Error"):
            return jsonify({'error': result}), 500

        print(f"[Creative Direction] Refined: {result.get('direction_summary', '')[:80]}")
        return jsonify({'success': True, 'creative_direction': result})

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ────────────────────────────────────────────────────────────────
#  RESEARCH & SCRIPT WRITING
# ────────────────────────────────────────────────────────────────

@app.route('/api/templates', methods=['GET'])
@require_auth
def list_templates():
    """Return all available research/script templates."""
    return jsonify({'templates': get_all_templates_metadata()})


@app.route('/api/script-options', methods=['GET'])
@require_auth
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
        topic = data.get('topic', '').strip()
        template_id = data.get('template_id', 'educational_explainer')
        research_model = data.get('research_model', 'fast')  # 'fast', 'deep', or 'deep_research_agent'
        project_id = data.get('project_id')

        if not topic:
            return jsonify({'error': 'Topic is required'}), 400

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
        raw = generate_content(research_prompt, model_name=model_name, use_search=use_search, api_key=g.api_key)

        # Fallback: if Deep (Pro) failed, retry with Flash + Search
        if raw and raw.startswith("Error:") and model_name != "gemini-3-flash-preview":
            fallback_model = "gemini-3-flash-preview"
            print(f"[Research] Primary model failed. Falling back to {fallback_model} + Search...")
            raw = generate_content(research_prompt, model_name=fallback_model, use_search=True, api_key=g.api_key)

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
                project_ref.set({
                    'research_dossier': dossier,
                    'research_summary': research_data.get("summary", ""),
                    'research_key_facts': research_data.get("key_facts", []),
                    'research_sources': research_data.get("sources_mentioned", []),
                    'updated_at': firestore.SERVER_TIMESTAMP
                }, merge=True)
                print(f"[Research] Saved to project document {project_id}")
            except Exception as e:
                print(f"[Research] Warning: Failed to save to project document: {e}")

        # Save dossier to Firestore for persistence/reuse
        try:
            dossier_ref = db.collection('users').document(g.uid).collection('dossiers').document()
            dossier_ref.set({
                'topic': topic,
                'template_id': template_id,
                'template_name': template["metadata"]["name"],
                'dossier': dossier,
                'key_facts': research_data.get("key_facts", []),
                'sources': research_data.get("sources_mentioned", []),
                'summary': research_data.get("summary", ""),
                'created_at': firestore.SERVER_TIMESTAMP,
                'research_model': research_model
            })
            print(f"[Research] Dossier saved to Firestore: {dossier_ref.id}")
        except Exception as fs_err:
            print(f"[Research] Warning: Firestore save failed: {fs_err}")

        return jsonify({
            'success': True,
            'dossier': dossier,
            'key_facts': research_data.get("key_facts", []),
            'sources': research_data.get("sources_mentioned", []),
            'summary': research_data.get("summary", ""),
            'template_name': template["metadata"]["name"]
        })

    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"\n{'='*60}")
        print(f"[Research Error] Full traceback:")
        print(error_trace)
        print(f"{'='*60}\n")
        return jsonify({'error': str(e)}), 500


# ────────────────────────────────────────────────────────────────
#  PROJECTS API (PERSISTENCE)
# ────────────────────────────────────────────────────────────────

@app.route('/api/projects', methods=['GET'])
@require_auth
def list_projects():
    """List all saved projects for the user."""
    try:
        docs = db.collection('users').document(g.uid).collection('projects') \
                 .order_by('last_updated_at', direction=firestore.Query.DESCENDING).stream()
                 
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
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects', methods=['POST'])
@require_auth
def create_project():
    """Create a new empty project."""
    try:
        data = request.json or {}
        title = data.get('title', 'Untitled Project')
        
        project_ref = db.collection('users').document(g.uid).collection('projects').document()
        new_project = {
            'title': title,
            'topic': data.get('topic', ''),
            'settings': data.get('settings', {}),
            'research_dossier': data.get('research_dossier', ''),
            'narration_data': data.get('narration_data', None),
            'production_table': data.get('production_table', None),
            'created_at': firestore.SERVER_TIMESTAMP,
            'last_updated_at': firestore.SERVER_TIMESTAMP,
        }
        project_ref.set(new_project)
        
        return jsonify({
            'success': True,
            'project_id': project_ref.id,
            'project': new_project
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects/<project_id>', methods=['GET'])
@require_auth
def get_project(project_id):
    """Load a specific project's full state."""
    try:
        doc = db.collection('users').document(g.uid).collection('projects').document(project_id).get()
        if not doc.exists:
            return jsonify({'error': 'Project not found'}), 404

        project_data = doc.to_dict()
        project_data['id'] = doc.id
        # Convert Firestore timestamps to ISO strings for JSON serialization
        for key in ('created_at', 'last_updated_at'):
            if key in project_data and hasattr(project_data[key], 'isoformat'):
                project_data[key] = project_data[key].isoformat()
        return jsonify({'success': True, 'project': project_data})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects/<project_id>', methods=['PUT'])
@require_auth
def update_project(project_id):
    """Auto-save / Update a specific project."""
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        # Don't update timestamps provided from client, use server timestamp
        if 'last_updated_at' in data:
            del data['last_updated_at']
        if 'created_at' in data:
            del data['created_at']
            
        data['last_updated_at'] = firestore.SERVER_TIMESTAMP
        
        db.collection('users').document(g.uid).collection('projects').document(project_id).set(
            data, merge=True
        )
        return jsonify({'success': True})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects/<project_id>', methods=['DELETE'])
@require_auth
def delete_project(project_id):
    """Delete a specific project."""
    try:
        db.collection('users').document(g.uid).collection('projects').document(project_id).delete()
        return jsonify({'success': True})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/dossiers', methods=['GET'])
@require_auth
def list_dossiers():
    """List saved research dossiers for the current user."""
    try:
        docs = db.collection('users').document(g.uid).collection('dossiers') \
                 .order_by('created_at', direction=firestore.Query.DESCENDING) \
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
        traceback.print_exc()
        return jsonify({'dossiers': []})


@app.route('/api/dossiers/<dossier_id>', methods=['GET'])
@require_auth
def get_dossier(dossier_id):
    """Load a specific saved dossier."""
    try:
        doc = db.collection('users').document(g.uid).collection('dossiers').document(dossier_id).get()
        if not doc.exists:
            return jsonify({'error': 'Dossier not found'}), 404
        return jsonify(doc.to_dict())
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/research/poll', methods=['POST'])
@require_auth
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

        # Save to Firestore
        try:
            dossier_ref = db.collection('users').document(g.uid).collection('dossiers').document()
            dossier_ref.set({
                'topic': topic,
                'template_id': template_id,
                'template_name': template["metadata"]["name"] if template else template_id,
                'dossier': dossier,
                'key_facts': [],
                'sources': [],
                'summary': research_text[:500],
                'created_at': firestore.SERVER_TIMESTAMP,
                'research_model': 'deep_research_agent'
            })
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
                project_ref.set({
                    'research_dossier': dossier,
                    'research_summary': research_text[:500],
                    'research_key_facts': [],
                    'research_sources': [],
                    'updated_at': firestore.SERVER_TIMESTAMP
                }, merge=True)
                print(f"[Deep Research] Saved to project document {project_id}")
            except Exception as e:
                print(f"[Deep Research] Warning: Failed to save to project document: {e}")

        return jsonify({
            'status': 'completed',
            'dossier': dossier,
            'key_facts': [],
            'sources': [],
            'summary': research_text[:500],
            'template_name': template["metadata"]["name"] if template else template_id,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/suggest-titles', methods=['POST'])
@require_auth
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

        if not topic:
            return jsonify({'error': 'Topic is required'}), 400
        if not dossier:
            return jsonify({'error': 'Research dossier is required'}), 400

        prompt = build_title_suggestions_prompt(
            template_id=template_id,
            topic=topic,
            dossier=dossier,
            audience=audience,
        )

        print(f"[Titles] Generating 5 title suggestions for '{topic}' (audience: {audience})")
        raw = generate_content(prompt, model_name="gemini-3-flash-preview", api_key=g.api_key)

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
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/auto-suggest-tone', methods=['POST'])
@require_auth
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
        )

        print(f"[Tone] Suggested: {result.get('suggested_tone', '?')}")
        return jsonify({'success': True, **result})

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/generate-script', methods=['POST'])
@require_auth
def generate_script_route():
    """
    Generate narration from research results (acts/beats, no scene breakdown).
    Accepts: topic, template_id, dossier, duration_minutes, audience, tone, focus, selected_title
    Returns: { success, narration: { title, hook_type, narration: [...], ... } }
    """
    try:
        data = request.json
        topic = data.get('topic', '').strip()
        template_id = data.get('template_id', 'educational_explainer')
        dossier = data.get('dossier', '')
        duration = int(data.get('duration_minutes', 10))
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

        if not topic:
            return jsonify({'error': 'Topic is required'}), 400
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
        )

        if "error" in result:
            return jsonify({'error': result["error"]}), 500

        # Save to Project Firestore document
        if project_id:
            try:
                project_ref = db.collection('users').document(g.uid).collection('projects').document(project_id)
                project_ref.set({
                    'narration_data': result,
                    'updated_at': firestore.SERVER_TIMESTAMP
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
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/regenerate-beat', methods=['POST'])
@require_auth
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
        )

        if "error" in result:
            return jsonify({'error': result['error']}), 500

        print(f"[Regenerate] Got {len(result.get('beats', []))} regenerated beats")
        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/generate-production-table', methods=['POST'])
@require_auth
def generate_production_table_route():
    """
    PHASE 3: Generate production-ready prompts from narration.
    Accepts: narration (narration JSON with acts/beats), duration_minutes,
             plus optional style config fields or style_analysis.
    Returns: production table with split shots, first-frame, last-frame, and Veo prompts.
    """
    try:
        data = request.json
        narration = data.get('narration')
        duration_minutes = int(data.get('duration_minutes', 10))
        project_id = data.get('project_id')

        if not narration:
            return jsonify({'error': 'Narration is required. Generate narration first.'}), 400

        beats = narration.get('narration', [])
        print(f"[Production] Received narration: '{narration.get('title', 'Untitled')}' "
              f"({len(beats)} beats, {duration_minutes}min)")

        # Check for structured style analysis (from images or text)
        style_analysis = data.get('style_analysis')
        aspect_ratio = data.get('aspect_ratio', '16:9')
        pacing_tier = data.get('pacing_tier', 'Standard')
        quality_mode = data.get('quality_mode', 'fast')

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

        result = generate_production_table(
            narration_json=narration,
            duration_minutes=duration_minutes,
            style_analysis=style_analysis,
            aspect_ratio=aspect_ratio,
            api_key=g.api_key,
            pacing_tier=pacing_tier,
            quality_mode=quality_mode,
            creative_direction=creative_direction
        )

        if "error" in result:
            return jsonify({'error': result['error']}), 500

        # Save to Project Firestore document
        if project_id:
            try:
                project_ref = db.collection('users').document(g.uid).collection('projects').document(project_id)
                project_ref.set({
                    'production_data': result,
                    'updated_at': firestore.SERVER_TIMESTAMP
                }, merge=True)
                print(f"[Production] Saved to project document {project_id}")
            except Exception as e:
                print(f"[Production] Warning: Failed to save to project document: {e}")

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
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ────────────────────────────────────────────────────────────────
#  VISUALS TAB — IMAGE & VIDEO GENERATION
# ────────────────────────────────────────────────────────────────

@app.route('/api/latest-production-table', methods=['GET'])
@require_auth
def get_latest_production_table():
    """Return the most recently saved production table JSON from .tmp/."""
    try:
        project_id = request.args.get('project_id')
        search_dir = os.path.join(TMP_DIR, project_id) if project_id else TMP_DIR
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

        print(f"[Visuals] Loaded latest production table: {os.path.basename(latest)}")
        return jsonify({'success': True, 'production_table': pt})

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/visuals/sync-storage-images', methods=['POST'])
@require_auth
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
                # Ensure it's public and get the URL
                try:
                    latest.make_public()
                except Exception:
                    pass  # May already be public
                matches[str(sid)] = latest.public_url

        print(f"[Sync] Found {len(matches)} orphaned images for {len(scene_ids)} scene IDs")
        return jsonify({'matches': matches})

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/visuals/scene-image-history', methods=['POST'])
@require_auth
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

        data = request.json
        scene_ids = data.get('scene_ids', [])
        project_id = data.get('project_id')

        if not scene_ids:
            return jsonify({'history': {}})

        history = {}
        search_prefix = f"images/{project_id}/scene_" if project_id else "images/scene_"
        all_blobs = list(bucket.list_blobs(prefix=search_prefix))

        for sid in scene_ids:
            safe_id = str(sid).replace("/", "_").replace(" ", "_")
            prefix = f"scene_{safe_id}_"
            scene_blobs = [b for b in all_blobs if b.name.split('/')[-1].startswith(prefix)]

            if scene_blobs:
                # Sort by name (contains timestamp) descending -> newest first
                scene_blobs.sort(key=lambda b: b.name, reverse=True)
                entries = []
                for blob in scene_blobs:
                    try:
                        blob.make_public()
                    except Exception:
                        pass
                    filename = blob.name.split('/')[-1]
                    # Extract timestamp from filename: scene_{safe_id}_{timestamp}.{ext}
                    ts_part = filename.replace(f"scene_{safe_id}_", "").rsplit(".", 1)[0]
                    try:
                        timestamp = int(ts_part)
                    except ValueError:
                        timestamp = 0
                    entries.append({
                        'url': blob.public_url,
                        'timestamp': timestamp,
                        'filename': filename,
                    })
                history[str(sid)] = entries

        total_images = sum(len(v) for v in history.values())
        print(f"[History] Returned image history for {len(history)} scenes ({total_images} total images)")
        return jsonify({'history': history})

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/visuals/generate-image', methods=['POST'])
@require_auth
def visuals_generate_image():
    """Generate a single scene image using Gemini image models."""
    try:
        data = request.json
        scene_id = data.get('scene_id')
        prompt = data.get('prompt')

        if not prompt:
            return jsonify({'error': 'Prompt is required'}), 400
        if not scene_id:
            return jsonify({'error': 'scene_id is required'}), 400

        model = data.get('model', 'gemini-3-pro-image-preview')
        aspect_ratio = data.get('aspect_ratio', '16:9')
        resolution = data.get('resolution', '2K')
        style_images = data.get('style_images', [])
        characters = data.get('characters', [])
        character_images = data.get('character_images', [])
        additional_context = data.get('additional_context', '')
        style_mode = data.get('style_mode', 'art_only')

        char_count = len(characters) if characters else 0
        char_img_count = sum(len(c.get('images', [])) for c in characters) if characters else len(character_images or [])
        print(f"[Visuals] Generating image for scene {scene_id}: "
              f"{len(style_images or [])} style refs, {char_count} characters "
              f"({char_img_count} char images), style_mode={style_mode}"
              f"{', context=' + repr(additional_context[:50]) if additional_context else ''}")
        result = generate_scene_image(
            prompt=prompt,
            model_name=model,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            style_images=style_images or None,
            characters=characters or None,
            character_images=character_images or None,
            additional_context=additional_context,
            style_mode=style_mode,
            scene_id=scene_id,
            api_key=g.api_key,
        )

        if "error" in result:
            return jsonify({'error': result['error']}), 500

        project_id = data.get('project_id')
        if result.get("success") and "local_path" in result:
            public_url = upload_to_storage(result["local_path"], "images", project_id=project_id)
            if public_url:
                result["image_url"] = public_url
            del result["local_path"]

        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/visuals/generate-batch-images', methods=['POST'])
@require_auth
def visuals_generate_batch_images():
    """Generate images for multiple scenes in parallel."""
    try:
        data = request.json
        scenes = data.get('scenes', [])
        global_config = data.get('global_config', {})

        if not scenes:
            return jsonify({'error': 'No scenes provided'}), 400

        api_key = g.api_key

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
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/visuals/start-animation', methods=['POST'])
@require_auth
def visuals_start_animation():
    """Start Veo video animation for a single scene."""
    try:
        data = request.json
        scene_id = data.get('scene_id')
        image_url = data.get('image_url', '')
        prompt = data.get('prompt', '')

        if not scene_id:
            return jsonify({'error': 'scene_id is required'}), 400
        if not image_url:
            return jsonify({'error': 'image_url is required (generate an image first)'}), 400
        if not prompt:
            return jsonify({'error': 'Animation prompt is required'}), 400

        # Resolve image URL to local file path
        image_path = ensure_local_image(image_url)
        if not image_path:
            return jsonify({'error': f'Image file could not be downloaded/resolved: {image_url}'}), 404

        model = data.get('model', 'veo-3.1-generate-preview')
        aspect_ratio = data.get('aspect_ratio', '16:9')
        duration = data.get('duration', 6)
        resolution = data.get('resolution', '720p')

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
        )

        if "error" in result:
            return jsonify({'error': result['error']}), 500

        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/visuals/poll-animation', methods=['POST'])
@require_auth
def visuals_poll_animation():
    """Poll a Veo animation operation for completion."""
    try:
        data = request.json
        operation_name = data.get('operation_name')
        scene_id = data.get('scene_id')

        if not operation_name:
            return jsonify({'error': 'operation_name is required'}), 400

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
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/visuals/start-batch-animation', methods=['POST'])
@require_auth
def visuals_start_batch_animation():
    """Start Veo animation for multiple scenes (max 5 concurrent submissions)."""
    try:
        data = request.json
        scenes = data.get('scenes', [])
        global_config = data.get('global_config', {})

        if not scenes:
            return jsonify({'error': 'No scenes provided'}), 400

        api_key = g.api_key

        def start_one(scene):
            sid = scene.get('scene_id')
            image_url = scene.get('image_url', '')
            image_path = ensure_local_image(image_url)

            if not image_path:
                return {"error": f"Image could not be resolved: {image_url}", "scene_id": sid}

            return start_video_generation(
                image_path=image_path,
                prompt=scene.get('prompt', ''),
                model_name=scene.get('model') or global_config.get('model', 'veo-3.1-generate-preview'),
                aspect_ratio=scene.get('aspect_ratio') or global_config.get('aspect_ratio', '16:9'),
                duration=scene.get('duration', 6),
                resolution=scene.get('resolution') or global_config.get('resolution', '720p'),
                scene_id=sid,
                api_key=api_key,
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
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/video/<path:filename>')
def serve_video_file(filename):
    """Serve generated video files."""
    return send_from_directory(VIDEO_DIR, filename)


@app.route('/api/download-asset', methods=['GET'])
@require_auth
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

        # Only allow downloading from our Firebase Storage bucket
        if not (url.startswith('https://storage.googleapis.com/') or
                url.startswith('https://firebasestorage.googleapis.com/')):
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
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/visuals/download-all', methods=['GET'])
@require_auth
def download_all_assets():
    """Download all generated images and videos as a zip file."""
    try:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add images
            if os.path.exists(GENERATED_DIR):
                for fname in os.listdir(GENERATED_DIR):
                    if fname.startswith('scene_'):
                        fpath = os.path.join(GENERATED_DIR, fname)
                        zf.write(fpath, f"images/{fname}")

            # Add videos
            if os.path.exists(VIDEO_DIR):
                for fname in os.listdir(VIDEO_DIR):
                    if fname.startswith('scene_'):
                        fpath = os.path.join(VIDEO_DIR, fname)
                        zf.write(fpath, f"videos/{fname}")

        buffer.seek(0)
        return send_file(
            buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name='visuals_assets.zip',
        )

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    os.makedirs(GENERATED_DIR, exist_ok=True)
    os.makedirs(AUDIO_DIR, exist_ok=True)
    os.makedirs(VIDEO_DIR, exist_ok=True)
    os.makedirs(TMP_DIR, exist_ok=True)
    app.run(debug=True, port=8080)
