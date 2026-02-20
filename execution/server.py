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
                           generate_scene_image,
                           start_video_generation, poll_video_generation)
from research_templates import get_all_templates_metadata, get_template, build_research_queries, build_title_suggestions_prompt
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

        if not image_path or (isinstance(image_path, str) and image_path.startswith("Error")):
            return jsonify({'error': image_path or 'Image generation returned no result'}), 500

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

        if not audio_path or (isinstance(audio_path, str) and audio_path.startswith("Error")):
            return jsonify({'error': audio_path or 'TTS generation returned no result'}), 500

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
        research_model = data.get('research_model', 'fast')  # 'fast', 'deep', or 'deep_research_agent'

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
        os.makedirs(TMP_DIR, exist_ok=True)
        safe_topic = "".join(c if c.isalnum() or c in " -_" else "" for c in topic)[:50]
        dossier_path = os.path.join(TMP_DIR, f"research_{safe_topic}.md")
        with open(dossier_path, "w") as f:
            f.write(dossier)
        print(f"[Research] Dossier saved to {dossier_path}")

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
        topic = data.get('topic', '')
        template_id = data.get('template_id', 'educational_explainer')

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
        os.makedirs(TMP_DIR, exist_ok=True)
        safe_topic = "".join(c if c.isalnum() or c in " -_" else "" for c in topic)[:50]
        dossier_path = os.path.join(TMP_DIR, f"research_{safe_topic}_deep.md")
        with open(dossier_path, "w") as f:
            f.write(dossier)
        print(f"[Deep Research] Dossier saved to {dossier_path}")

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
        audience = data.get('audience', 'General')
        tone = data.get('tone', '')
        focus = data.get('focus', '')
        selected_title = data.get('selected_title', '')

        style_mode = data.get('style_mode', 'template')  # 'template' or 'transcript'
        style_transcript = data.get('style_transcript', '')

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
            print(f"[Narration] Style analysis complete.")

        print(f"[Narration] Generating narration for '{topic}' ({template_id}, {duration}min)")

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
            api_key=g.api_key,
        )

        if "error" in result:
            return jsonify({'error': result["error"]}), 500

        # Save narration to .tmp
        os.makedirs(TMP_DIR, exist_ok=True)
        safe_topic = "".join(c if c.isalnum() or c in " -_" else "" for c in topic)[:50]
        narration_path = os.path.join(TMP_DIR, f"narration_{safe_topic}.json")
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

        if not narration:
            return jsonify({'error': 'Narration is required. Generate narration first.'}), 400

        beats = narration.get('narration', [])
        print(f"[Production] Received narration: '{narration.get('title', 'Untitled')}' "
              f"({len(beats)} beats, {duration_minutes}min)")

        # Check for structured style analysis (from images or text)
        style_analysis = data.get('style_analysis')
        aspect_ratio = data.get('aspect_ratio', '16:9')

        if style_analysis:
            summary = style_analysis.get('style_summary', 'custom') if isinstance(style_analysis, dict) else 'custom'
            print(f"[Production] Using style analysis: {summary}")
        else:
            print(f"[Production] No style analysis — using default cinematic style")

        result = generate_production_table(
            narration_json=narration,
            duration_minutes=duration_minutes,
            style_analysis=style_analysis,
            aspect_ratio=aspect_ratio,
            api_key=g.api_key,
        )

        if "error" in result:
            return jsonify({'error': result['error']}), 500

        # Save to .tmp
        os.makedirs(TMP_DIR, exist_ok=True)
        title = narration.get('title', 'untitled')
        safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in title)[:50]
        pt_path = os.path.join(TMP_DIR, f"production_table_{safe_title}.json")
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
        pattern = os.path.join(TMP_DIR, "production_table_*.json")
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
        character_images = data.get('character_images', [])
        additional_context = data.get('additional_context', '')

        print(f"[Visuals] Generating image for scene {scene_id}")
        result = generate_scene_image(
            prompt=prompt,
            model_name=model,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            style_images=style_images or None,
            character_images=character_images or None,
            additional_context=additional_context,
            scene_id=scene_id,
            api_key=g.api_key,
        )

        if "error" in result:
            return jsonify({'error': result['error']}), 500

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
            return generate_scene_image(
                prompt=scene.get('prompt', ''),
                model_name=scene.get('model') or global_config.get('model', 'gemini-3-pro-image-preview'),
                aspect_ratio=scene.get('aspect_ratio') or global_config.get('aspect_ratio', '16:9'),
                resolution=scene.get('resolution') or global_config.get('resolution', '2K'),
                style_images=global_config.get('style_images') or None,
                character_images=global_config.get('character_images') or None,
                additional_context=global_config.get('additional_context', ''),
                scene_id=sid,
                api_key=api_key,
            )

        print(f"[Visuals] Batch generating {len(scenes)} scene images (max 5 parallel)")
        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(generate_one, s): s for s in scenes}
            for future in as_completed(futures):
                try:
                    results.append(future.result())
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
        filename = os.path.basename(image_url)
        image_path = os.path.join(GENERATED_DIR, filename)
        if not os.path.exists(image_path):
            return jsonify({'error': f'Image file not found: {filename}'}), 404

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
            filename = os.path.basename(image_url)
            image_path = os.path.join(GENERATED_DIR, filename)

            if not os.path.exists(image_path):
                return {"error": f"Image not found: {filename}", "scene_id": sid}

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
