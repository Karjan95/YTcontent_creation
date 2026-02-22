# QA Test Plan: Content Creation App Workflows

## 1. Context and Scope
This document outlines the Quality Assurance strategy and the automated test framework for the Content Creation App. 
The application allows users to research topics, generate narrations/scripts, and create production tables (multimedia prompts) utilizing Gemini models alongside Firebase for persistence.

### Critical Flows Identified
1. **Research Workflow (Phase 1):** User provides a topic/template -> App generates a comprehensive research dossier.
2. **Narration Workflow (Phase 2):** User refines dossier and selects audience/tone/format -> App generates a voiceover script/narration.
3. **Production Table Workflow (Phase 3):** User provides the narration -> App breaks it down into scenes, analyzes the visual style, generates prompts, and creates media (TTS/image/video).
4. **Project Persistence Flow:** User creates a new project -> Project state auto-saves to Firebase Firestore -> User can retrieve and delete projects.
5. **Configuration Flow:** User logs in via Firebase Auth -> User sets and persists their custom Gemini API Key.

## 2. Testing Strategy

### 2.1 Pytest - API & Logic Testing (Integration level)
- Mock external dependencies: Firebase ID token validation, Firebase Firestore calls, and `google-genai` network calls.
- Validate Flask routing, JSON payload parsing, and error handling.
- Verify that successive internal logic pipelines correctly pass context from Research -> Narration -> Production Table.

### 2.2 Playwright - End-to-End (E2E) UI Testing
- Test the frontend interactions (`ui/index.html`).
- Step through the UI tabs: `Phase 1: Research` -> `Phase 2: Narration` -> `Phase 3: Production Table`.
- Validate DOM state changes, active tabs, inputs handling, and correct rendering of generated Markdown/JSON content.
- Ensure the API keys modal and tone/audience options render correctly.

## 3. Execution Setup

The following tools and frameworks have been integrated:
- **Pytest**: Running API and mock tests.
- **pytest-mock**: For mocking external dependency calls inside Pytest.
- **pytest-flask**: For easier app client abstractions.
- **Playwright**: For headless browser E2E workflows.

To run the Pytest workflow tests locally:
```bash
pip install -r requirements.txt
pip install pytest pytest-mock pytest-playwright
playwright install chromium
python -m pytest tests/test_api_workflows.py -v
```

## 4. Test Case Definitions

### API Test Cases (Included in `tests/test_api_workflows.py`)
| Test ID | Title | Description | Expected Result |
|---------|-------|-------------|-----------------|
| API-001 | Auth Key Override | Verify that if a user provides an authorization header, it mocks token verify successfully. | HTTP 200 on basic protected routes |
| API-002 | List Options | Retrieve script options (Tone, Audiences, Formats) via `GET /api/script-options` | Returns JSON of predefined profiles |
| API-003 | Full Script Workflow | Simulates Research -> Title generation -> Narration -> Production Table flow. | Expected JSON structure returned payload at each step |
| API-004 | Projects Save/Load | Tests `POST /api/projects`, `GET /api/projects/<id>` | Project IDs match, data successfully retrieved |
