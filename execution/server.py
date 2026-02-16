import os
import sys
import json
from functools import wraps
from flask import Flask, render_template, request, jsonify, send_from_directory, g
import traceback
import firebase_admin
from firebase_admin import credentials, auth, firestore

# Ensure the execution directory is in the Python path
sys.path.insert(0, os.path.dirname(__file__))
from gemini_client import generate_image_content, generate_tts, generate_content, analyze_style_from_images
from research_templates import get_all_templates_metadata, get_template, build_research_queries
from research_scriptwriter import build_research_dossier, generate_script, generate_production_table, breakdown_narration
from youtube_utils import get_transcript, analyze_style

# Paths relative to this script's location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
UI_DIR = os.path.join(PROJECT_DIR, "ui")
GENERATED_DIR = os.path.join(PROJECT_DIR, "generated_images")
AUDIO_DIR = os.path.join(PROJECT_DIR, "generated_audio")
TMP_DIR = os.path.join(PROJECT_DIR, ".tmp")

# ── Firebase Initialization ──
SERVICE_ACCOUNT_PATH = os.path.join(PROJECT_DIR, "firebase-service-account.json")
if os.path.exists(SERVICE_ACCOUNT_PATH):
    cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
    firebase_admin.initialize_app(cred)
else:
    # Fall back to default credentials (e.g., on Cloud Run with GOOGLE_APPLICATION_CREDENTIALS)
    firebase_admin.initialize_app()

db = firestore.client()

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
        if not prompt:
            return jsonify({'error': 'Prompt is required'}), 400

        print(f"Generating image for prompt: {prompt}")
        image_path = generate_image_content(prompt, api_key=g.api_key)

        if image_path.startswith("Error"):
            return jsonify({'error': image_path}), 500

        return jsonify({'image_url': f'/generated/{os.path.basename(image_path)}'})

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

        if audio_path.startswith("Error"):
            return jsonify({'error': audio_path}), 500

        return jsonify({'audio_url': f'/audio/{os.path.basename(audio_path)}'})

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
    Returns: { style_analysis: "comprehensive style description..." }
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

        if style_analysis.startswith("Error"):
            return jsonify({'error': style_analysis}), 500

        print(f"[Style Analysis] Complete: {style_analysis[:100]}...")
        return jsonify({
            'success': True,
            'style_analysis': style_analysis
        })

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
        research_model = data.get('research_model', 'fast')  # 'fast' or 'deep'

        if not topic:
            return jsonify({'error': 'Topic is required'}), 400

        template = get_template(template_id)
        if not template:
            return jsonify({'error': f'Unknown template: {template_id}'}), 400

        # Configure model based on selection
        if research_model == 'deep':
            model_name = "gemini-2.5-pro"
            use_search = True
            print(f"[Research] Using DEEP mode: {model_name} + Google Search")
        else:
            model_name = "gemini-2.5-flash"
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

        # Use Gemini to do comprehensive research
        research_prompt = f"""You are a world-class research analyst. Conduct thorough research on the following topic.

TOPIC: {topic}

RESEARCH LAYERS (investigate each one):
{queries_text}

ANALYSIS QUESTIONS (answer each one with specific facts, names, numbers, dates):
{questions_text}

Return a JSON object:
{{
  "results": [
    {{"question": "the analysis question", "answer": "detailed answer with specifics"}}
  ],
  "key_facts": ["fact1", "fact2", ...],
  "sources_mentioned": ["source1", "source2", ...],
  "summary": "2-3 paragraph executive summary of all findings"
}}

Be as specific as possible — include names, dates, amounts, percentages. No vague language.
Return ONLY the JSON."""

        print(f"[Research] Sending research prompt to Gemini...")
        raw = generate_content(research_prompt, model_name=model_name, use_search=use_search, api_key=g.api_key)

        if raw.startswith("Error:"):
            return jsonify({'error': raw}), 500

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
        os.makedirs(TMP_DIR, exist_ok=True)
        safe_topic = "".join(c if c.isalnum() or c in " -_" else "" for c in topic)[:50]
        dossier_path = os.path.join(TMP_DIR, f"research_{safe_topic}.md")
        with open(dossier_path, "w") as f:
            f.write(dossier)
        print(f"[Research] Dossier saved to {dossier_path}")

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


@app.route('/api/generate-script', methods=['POST'])
@require_auth
def generate_script_route():
    """
    Generate a production-ready script from research results.
    Accepts: topic, template_id, dossier, duration_minutes, audience, tone, focus
    Returns: structured script (JSON)
    """
    try:
        data = request.json
        topic = data.get('topic', '').strip()
        template_id = data.get('template_id', 'educational_explainer')
        dossier = data.get('dossier', '')
        duration = int(data.get('duration_minutes', 10))
        audience = data.get('audience', 'General')
        tone = data.get('tone', '')
        focus = data.get('focus', '')

        style_mode = data.get('style_mode', 'template')  # 'template' or 'youtube'
        style_url = data.get('style_url', '')

        if not topic:
            return jsonify({'error': 'Topic is required'}), 400
        if not dossier:
            return jsonify({'error': 'Research dossier is required. Run research first.'}), 400

        style_guide = None
        if style_mode == 'youtube' and style_url:
            print(f"[Script] Analyzing style from YouTube URL: {style_url}")
            transcript, error = get_transcript(style_url)
            if error:
                print(f"[Script] Error fetching transcript: {error}")
                return jsonify({'error': f"Failed to fetch YouTube transcript: {error}"}), 400
            
            print(f"[Script] Transcript fetched ({len(transcript)} chars). Analyzing style...")
            style_guide = analyze_style(transcript, api_key=g.api_key)
            print(f"[Script] Style analysis complete.")

        print(f"[Script] Starting 2-phase pipeline for '{topic}' ({template_id}, {duration}min)")

        result = generate_script(
            topic=topic,
            template_id=template_id,
            research_dossier=dossier,
            duration_minutes=duration,
            audience=audience,
            tone=tone,
            focus=focus,
            style_guide=style_guide,
            api_key=g.api_key,
        )

        if "error" in result:
            return jsonify({'error': result["error"]}), 500

        # Save script to .tmp
        os.makedirs(TMP_DIR, exist_ok=True)
        safe_topic = "".join(c if c.isalnum() or c in " -_" else "" for c in topic)[:50]
        script_path = os.path.join(TMP_DIR, f"script_{safe_topic}.json")
        with open(script_path, "w") as f:
            json.dump(result, f, indent=2)
        print(f"[Script] Script saved to {script_path}")

        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/breakdown-script', methods=['POST'])
@require_auth
def breakdown_script_route():
    """
    PHASE 2 (Manual): Break down raw text into a timed scene table.
    Accepts: script_text, duration_minutes (optional)
    Returns: structured script (JSON)
    """
    try:
        data = request.json
        script_text = data.get('script_text', '').strip()
        duration = int(data.get('duration_minutes', 10))

        if not script_text:
            return jsonify({'error': 'Script text is required'}), 400

        print(f"[Script Breakdown] Starting breakdown for manual text ({len(script_text)} chars)")

        # 1. Construct a mock "narration_json" that matches Phase 1 output syntax
        narration_json = {
            "title": "Manual Script",
            "hook_type": "Manual",
            "summary": "Manually imported script text.",
            "duration_minutes": duration,
            "narration": [
                {
                    "act": "MANUAL IMPORT",
                    "beat": "Full Script",
                    "text": script_text
                }
            ]
        }
        
        # 2. Call the existing breakdown logic
        from research_scriptwriter import breakdown_narration  # Ensure imported
        
        # Use a longer duration if text is long, to allow for enough scenes
        # Approx 150 words/min = 2.5 words/sec.
        # If user didn't specify duration, estimate it from text length
        word_count = len(script_text.split())
        estimated_minutes = max(1, round(word_count / 150))
        if 'duration_minutes' not in data:
            print(f"[Script Breakdown] Estimated duration from text: {estimated_minutes} min")
            duration = estimated_minutes

        phase2 = breakdown_narration(
            narration_json=narration_json,
            duration_minutes=duration,
            api_key=g.api_key,
        )

        if "error" in phase2:
            return jsonify({'error': phase2["error"]}), 500

        result = phase2["script"]
        
        # Save to .tmp
        os.makedirs(TMP_DIR, exist_ok=True)
        script_path = os.path.join(TMP_DIR, f"script_manual_breakdown.json")
        with open(script_path, "w") as f:
            json.dump(result, f, indent=2)
        print(f"[Script Breakdown] Saved to {script_path}")

        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/generate-production-table', methods=['POST'])
@require_auth
def generate_production_table_route():
    """
    PHASE 3: Generate production-ready prompts from a scene breakdown.
    Accepts: scene_breakdown (Phase 2 output JSON), plus optional style config fields.
    Returns: production table with first-frame, last-frame, and Veo 3.1 video prompts.
    """
    try:
        data = request.json
        scene_breakdown = data.get('scene_breakdown')

        # DEBUG: Print what we received from frontend
        print(f"[Server DEBUG] Received scene_breakdown type: {type(scene_breakdown)}")
        print(f"[Server DEBUG] Received scene_breakdown keys: {scene_breakdown.keys() if isinstance(scene_breakdown, dict) else 'NOT A DICT'}")
        if isinstance(scene_breakdown, dict):
            print(f"[Server DEBUG] scene_breakdown['script'] exists: {'script' in scene_breakdown}")
            if 'script' in scene_breakdown:
                print(f"[Server DEBUG] scene_breakdown['script'] length: {len(scene_breakdown.get('script', []))}")

        if not scene_breakdown:
            return jsonify({'error': 'Scene breakdown is required. Run script generation first.'}), 400

        # Check for image-derived style analysis
        style_analysis = data.get('style_analysis')

        # Build style config from optional fields (only if no style_analysis)
        style_config = {}
        if not style_analysis:
            style_fields = ['genre', 'color_world', 'lighting', 'camera_personality',
                            'movement_style', 'aspect_ratio', 'image_model']
            for field in style_fields:
                if field in data and data[field]:
                    style_config[field] = data[field]

        print(f"[Production Table] Starting Phase 3 for '{scene_breakdown.get('title', 'Untitled')}'")
        if style_analysis:
            print(f"[Production Table] Using image-derived style analysis")
            print(f"[Production Table] Style: {style_analysis[:100]}...")
        elif style_config:
            print(f"[Production Table] Using manual style config: {style_config}")

        result = generate_production_table(
            scene_breakdown_json=scene_breakdown,
            style_config=style_config if style_config else None,
            style_analysis=style_analysis,
            api_key=g.api_key,
        )

        if "error" in result:
            return jsonify({'error': result['error']}), 500

        # Save to .tmp
        os.makedirs(TMP_DIR, exist_ok=True)
        title = scene_breakdown.get('title', 'untitled')
        safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in title)[:50]
        pt_path = os.path.join(TMP_DIR, f"production_table_{safe_title}.json")
        with open(pt_path, "w") as f:
            json.dump(result, f, indent=2)
        print(f"[Production Table] Saved to {pt_path}")

        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    os.makedirs(GENERATED_DIR, exist_ok=True)
    os.makedirs(AUDIO_DIR, exist_ok=True)
    os.makedirs(TMP_DIR, exist_ok=True)
    app.run(debug=True, port=8080)
