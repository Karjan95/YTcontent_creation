
import os
import sys
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load env vars
load_dotenv(os.path.join(os.getcwd(), '.env'))

def get_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found")
        sys.exit(1)
    return genai.Client(api_key=api_key)

def test_simple_generation():
    print("\n--- Testing Simple Generation ---")
    try:
        client = get_client()
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents="Say hello"
        )
        print("Success:", response.text)
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()

def test_search_generation():
    print("\n--- Testing Generation with Search ---")
    try:
        client = get_client()
        
        # Exact config from gemini_client.py
        config = types.GenerateContentConfig()
        config.tools = [types.Tool(google_search=types.GoogleSearch())]
        
        print("Calling generate_content with search...")
        response = client.models.generate_content(
            model="gemini-2.0-flash", # Using flash for speed, but behaves same for tools usually
            contents="What is the latest news about Gemini AI?",
            config=config
        )
        print("Success!")
        print("Response text length:", len(response.text) if response.text else 0)
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_simple_generation()
    test_search_generation()
