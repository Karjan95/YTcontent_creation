# Gemini Studio — AI Content Creation Platform

## Project Overview

Full-stack AI-powered video production app: research → scriptwriting → visual production.
Users authenticate via Firebase, provide their own Gemini API key (encrypted at rest), and create projects that auto-save to Firestore.

## References

See @README.md for project intro and local setup instructions.
See @AGENTS.md for the 3-layer architecture (directive → orchestration → execution) and operating principles.
See @requirements.txt for Python dependencies.
See @Dockerfile for container build.
See @deploy.sh and @deploy_staging.sh for Cloud Run deployment.

### Directives (SOPs)
- @directives/research_and_scriptwriting.md — Research & script pipeline
- @directives/gemini_interaction.md — Gemini API usage patterns
- @directives/fix_parallel_projects.md — Parallel project handling

### Changelogs & Docs
- @docs/ — All changelogs and session summaries (17 files)
- @QA_Test_Plan.md — QA test plan

## Tech Stack

- **Backend:** Flask 3.1.2 + Gunicorn (Python 3.10)
- **AI Engine:** Google Gemini API (`google-genai`) — text, image (Imagen 4 / Gemini Pro Image), video (Veo 3.1), TTS (30+ voices)
- **Database:** Firestore (projects, dossiers, settings) + Firebase Storage (media)
- **Auth:** Firebase Authentication (Google OAuth)
- **Security:** Fernet encryption for API keys, Flask-Limiter for rate limiting
- **Frontend:** Single-page vanilla HTML/CSS/JS (no framework), Firebase client SDK
- **Deployment:** Docker → Google Cloud Run (`us-central1`)

## Full Project Tree

```
.
├── CLAUDE.md                 # ← You are here
├── AGENTS.md                 # 3-layer architecture instructions (mirrored to GEMINI.md)
├── GEMINI.md                 # Same as AGENTS.md (for Gemini/other AI environments)
├── README.md                 # Project intro and local setup
├── QA_Test_Plan.md           # QA testing plan
├── SKILL_SkillCreator.md     # Skill creation template
│
├── execution/                # ── Backend Python modules ──
│   ├── server.py             # Flask app — 42 API routes, @require_auth middleware (2,246 lines)
│   ├── gemini_client.py      # Gemini API wrapper — image/TTS/video generation (1,299 lines)
│   ├── research_scriptwriter.py  # Script generation pipeline (765 lines)
│   ├── research_templates.py # All prompts, templates, audience/tone definitions (3,005 lines)
│   ├── youtube_utils.py      # YouTube transcript analysis
│   ├── debug_items.py        # Debug utilities
│   ├── debug_youtube.py      # YouTube debug scripts
│   ├── debug_youtube_v2.py
│   ├── test_genai_simple.py  # Quick genai sanity check
│   └── test_server_logic.py  # Server logic unit tests
│
├── ui/                       # ── Frontend ──
│   ├── index.html            # Entire SPA — all tabs, modals, JS logic (~7,001 lines)
│   └── style.css             # CSS variables, animations, Space Grotesk font
│
├── tests/                    # ── Test suite (pytest) ──
│   ├── conftest.py           # Shared fixtures (mock Firebase, Firestore, Gemini)
│   ├── pytest.ini            # Pytest config
│   ├── test_api_workflows.py # API integration tests
│   ├── test_ui_workflows.py  # Frontend workflow tests
│   ├── test_production_batching.py  # Batch processing tests
│   ├── test_research.py      # Research pipeline tests
│   ├── test_deep_research.py # Deep research tests
│   ├── test_all_templates.py # Template validation
│   ├── test_gemini_call.py   # Gemini API call tests
│   └── test_list*.py         # Model listing tests
│
├── directives/               # ── SOPs (3-layer architecture) ──
│   ├── research_and_scriptwriting.md  # Research + script pipeline directive
│   ├── gemini_interaction.md          # Gemini API interaction directive
│   └── fix_parallel_projects.md       # Parallel project handling
│
├── docs/                     # ── Changelogs & session summaries ──
│   ├── changelog_3phase_style.md
│   ├── changelog_creative_direction.md
│   ├── changelog_dynamic_wardrobe_expressions_2026_03_04.md
│   ├── changelog_edit_fixes_model_pricing_cancel_2026_03_03.md
│   ├── changelog_history_and_download_fixes.md
│   ├── changelog_image_history_and_downloads.md
│   ├── changelog_image_history_edit_ratelimits_2026_03_02.md
│   ├── changelog_reference_image_persistence.md
│   ├── changelog_script_ui_and_prompts.md
│   ├── changelog_vibe_architecture.md
│   ├── changelog_visual_style_overhaul.md
│   ├── bugfix_image_history_and_downloads_2026_03_02.md
│   ├── fix_visuals_persistence_on_refresh_2026_03_02.md
│   ├── manual_import_fix_summary.md
│   ├── session_summary_character_intelligence_2026_03_04.md
│   └── dual_layer_style_guide.md
│
├── tools/                    # ── Utility scripts ──
│   ├── create_notebook.py
│   ├── inspect_genai*.py     # GenAI introspection utilities
│   ├── verify_notebooklm.py
│   └── n8n-mcp-server/      # N8N MCP integration (TypeScript)
│       ├── index.ts
│       ├── package.json
│       └── tsconfig.json
│
├── .agent/skills/            # ── Agent skill definitions ──
│   ├── chief-of-staff/
│   ├── code-reviewer/
│   ├── critical-thinker/
│   ├── environment-setup-guide/
│   ├── math-stats-expert/
│   ├── mcp-builder/
│   ├── project-manager/
│   ├── qa-engineer/
│   └── ui-ux-pro-max/
│
├── generated_images/         # Local image cache (gitignored)
├── generated_audio/          # Local audio cache (gitignored)
├── .tmp/                     # Temp processing files (gitignored)
│
├── Dockerfile                # python:3.10-slim, gunicorn, Cloud Run compatible
├── deploy.sh                 # Production deployment → Cloud Run
├── deploy_staging.sh         # Staging deployment → Cloud Run
├── run_server.sh             # Local server launcher
├── requirements.txt          # Python dependencies
├── firebase-service-account.json  # Firebase credentials (gitignored in deploy)
├── .env                      # Environment variables (never commit)
├── .dockerignore
├── .gcloudignore
└── .gitignore
```

## Key Architecture

**Auth flow:** Firebase ID token → `@require_auth` decorator → decrypt user API key from Firestore → Gemini calls

**3-Phase Production Pipeline (Max Quality mode):**
1. **Director** — scene cuts, duration, emotion
2. **Storyboard Artist** — visual descriptions, shot composition
3. **Director of Photography** — final image/video generation prompts

**State:** Auto-save with 2s debounce to Firestore. Projects include all tabs, settings, and media references.

## Build & Run

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python execution/server.py
# OR with gunicorn
gunicorn --bind :8080 --workers 1 --threads 8 execution.server:app

# Run tests
pytest tests/

# Deploy
./deploy.sh            # Production (content-creation-app)
./deploy_staging.sh    # Staging (content-creation-app-staging)
```

## Environment Variables

```
GEMINI_API_KEY=         # Fallback server key
ENCRYPTION_KEY=         # Fernet key for API key encryption
GOOGLE_CLOUD_PROJECT=   # GCP project ID (gen-lang-client-0854991687)
ENVIRONMENT=            # staging | production
```

Never commit `.env`, service account JSON, or plaintext secrets.

## Coding Conventions

- **Python:** snake_case, module-level constants for pacing/costs/templates
- **JavaScript:** camelCase
- **Error handling:** Retry with exponential backoff for 503/429 (max 3 attempts), safe error responses (no sensitive data)
- **Routes:** All in `server.py`, business logic separated into other modules
- **Prompts:** All prompt templates live in `research_templates.py`
- **Rate limits:** Per-user (not IP): research 30/hr, images 600/hr, TTS 60/hr, video 60/hr

## Important Patterns

- User API keys are Fernet-encrypted in Firestore, decrypted per-request
- Firebase Storage uses signed URLs with 4-hour expiration
- Image generation supports 6 models with different cost/quality tradeoffs
- Production table generation has Fast mode (1 call) and Max Quality (3 sequential calls)
- Character Intelligence System manages cast identity, wardrobe (locked vs story-driven), and expressions (dynamic vs neutral)
- Visual Style system uses 1-4 reference images with style lock modes (full, art_only, loose)

## Cloud Run Deployment

- **Project:** `gen-lang-client-0854991687`
- **Region:** `us-central1`
- **Timeout:** 3600s (long-running generation ops)
- **Auth:** Unauthenticated ingress (Firebase handles auth)
- Docker: `python:3.10-slim`, Gunicorn, port via `$PORT`

## Testing

- Framework: pytest + pytest-mock + pytest-flask
- Tests mock Firebase auth, Firestore, and Gemini API calls
- Key test files: `test_api_workflows.py`, `test_research.py`, `test_production_batching.py`, `test_all_templates.py`

## Content Pipeline (User Journey)

1. **Research** — Select template (10+ types) → enter topic → AI does deep web research → structured dossier
2. **Script** — AI suggests titles → select audience (12 profiles) & tone (15+ tones) → generate narration (acts/beats) → edit/regenerate
3. **Production** — Define visual style → configure cast → generate production table (3-phase) → shot-by-shot prompts
4. **Visuals** — Generate images (batch/individual) → edit with prompts → animate with Veo → download all as zip

## Key API Route Groups

| Group | Prefix | Examples |
|-------|--------|---------|
| Auth/Config | `/api/` | `save-api-key`, `check-api-key` |
| Research | `/api/research` | `research`, `research/poll`, `templates` |
| Scripting | `/api/` | `generate-script`, `regenerate-beat`, `suggest-titles` |
| Style | `/api/` | `analyze-style-images`, `suggest-cast`, `expand-creative-direction` |
| Visuals | `/api/visuals/` | `generate-image`, `edit-image`, `start-animation`, `download-all` |
| Projects | `/api/projects` | CRUD + `dossiers` |
