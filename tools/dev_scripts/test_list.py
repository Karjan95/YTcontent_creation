import os
from dotenv import load_dotenv
load_dotenv(".env")
from google import genai
client = genai.Client()
for m in client.models.list():
    if "gemini-3" in m.name or "gemini-2" in m.name:
        print(m.name)
