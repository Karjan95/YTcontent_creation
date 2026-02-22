import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Insert the execution directory to the path so we can import server
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../execution')))

@pytest.fixture(autouse=True, scope="session")
def mock_firebase_and_auth():
    """Mock firebase_admin initialization and firestore to avoid actual calls."""
    with patch('firebase_admin.initialize_app') as mock_init, \
         patch('firebase_admin.firestore.client') as mock_firestore, \
         patch('firebase_admin.auth.verify_id_token') as mock_verify:
        
        # Mock Firestore db
        mock_db = MagicMock()
        mock_firestore.return_value = mock_db
        
        # Mock token verification
        mock_verify.return_value = {'uid': 'test-user-id'}
        
        # Mock user's gemini key request
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {'gemini_api_key': 'test-gemini-key'}
        
        # Mock db.collection().document().get()
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        yield mock_firestore

@pytest.fixture
def client(mock_firebase_and_auth):
    """Provides a mocked Flask test client."""
    from server import app
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client
