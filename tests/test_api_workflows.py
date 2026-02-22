import json
import pytest
from unittest.mock import patch, MagicMock

class TestAPIWorkflows:

    def get_auth_headers(self):
        return {
            'Authorization': 'Bearer test-id-token',
            'Content-Type': 'application/json'
        }

    def test_get_script_options(self, client):
        """Test retrieving static script options."""
        response = client.get('/api/script-options', headers=self.get_auth_headers())
        assert response.status_code == 200
        data = json.loads(response.data)
        
        # Check if basic keys are returned
        assert 'audiences' in data
        assert 'tones' in data
        assert 'format_presets' in data
        assert len(data['audiences']) > 0

    @patch('server.generate_content')
    def test_research_workflow(self, mock_generate_content, client):
        """Phase 1: Research Workflow Test 
        Sends a topic and gets a research dossier JSON response.
        """
        # Mock Gemini returned research findings JSON
        mock_gemini_json = json.dumps({
            "results": [{"question": "What is AI?", "answer": "Artificial Intelligence is..."}],
            "key_facts": ["AI was coined in 1956"],
            "sources_mentioned": ["Source A"],
            "summary": "AI is intelligence demonstrated by machines."
        })
        mock_generate_content.return_value = f"```json\n{mock_gemini_json}\n```"

        payload = {
            "topic": "Artificial Intelligence",
            "template_id": "educational_explainer",
            "research_model": "fast"
        }
        
        response = client.post('/api/research', 
                               data=json.dumps(payload),
                               headers=self.get_auth_headers())
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'dossier' in data
        assert len(data['key_facts']) == 1

    @patch('research_scriptwriter.generate_content')
    def test_narration_workflow(self, mock_generate_content, client):
        """Phase 2: Narration / Script Generation Test.
        Uses research dossier to generate narration script.
        """
        mock_gemini_response = json.dumps({
            "beats": [
                {"id": 1, "topic": "Intro", "narrator": "Welcome to AI", "details": "Hook"}
            ]
        })
        mock_generate_content.return_value = f"```json\n{mock_gemini_response}\n```"

        payload = {
            "topic": "Artificial Intelligence",
            "template_id": "educational_explainer",
            "dossier": "Research Dossier Text",
            "tone": "Formal",
            "audience": "General",
            "format": "long_form",
            "viewer_outcome": "inform"
        }
        
        response = client.post('/api/generate-script',
                               data=json.dumps(payload),
                               headers=self.get_auth_headers())
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'narration' in data

    @patch('research_scriptwriter.generate_content')
    def test_production_table_workflow(self, mock_generate_content, client):
        """Phase 3: Production Table Generation Test.
        Uses narration script to generate prompts.
        """
        mock_gemini_response = json.dumps({
            "shots": [
                {
                    "scene": "1",
                    "visuals": "A robot analyzing data",
                    "narration": "Welcome to AI",
                    "camera": "Pan right",
                    "image_prompt": "hyperrealistic robot data analysis center",
                    "video_prompt": "camera pan robot",
                    "notes": "Fast pacing"
                }
            ]
        })
        mock_generate_content.return_value = f"```json\n{mock_gemini_response}\n```"

        payload = {
            "topic": "Artificial Intelligence",
            "template_id": "educational_explainer",
            "narration": {
                "title": "Welcome to AI",
                "narration": [{"act": "Intro", "beat": 1, "text": "Narrator: Welcome to AI"}]
            },
            "duration_minutes": 10
        }

        response = client.post('/api/generate-production-table',
                               data=json.dumps(payload),
                               headers=self.get_auth_headers())
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'production_table' in data
        assert "shots" in data['production_table']
