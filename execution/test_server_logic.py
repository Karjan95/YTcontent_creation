
import sys
import os
import json
sys.path.insert(0, os.path.abspath('execution'))

from server import app

def test_research_endpoint():
    print("Setting up test client...")
    client = app.test_client()
    
    payload = {
        "topic": "debug logic test",
        "template_id": "educational_explainer",
        "research_model": "deep"
    }
    
    print(f"Sending POST to /api/research with payload: {payload}")
    try:
        response = client.post('/api/research', 
                              data=json.dumps(payload),
                              content_type='application/json')
        
        print(f"Response status: {response.status_code}")
        print(f"Response data: {response.data.decode('utf-8')[:500]}")
    except Exception as e:
        print(f"EXCEPTION: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_research_endpoint()
