
from google import genai
from google.genai import types

print("--- types.Part fields ---")
try:
    print(types.Part.model_fields.keys())
except:
    print("No model_fields")

print("\n--- types.StyleReferenceImage fields ---")
try:
    print(types.StyleReferenceImage.model_fields.keys())
except:
    print("No model_fields")

print("\n--- types.SubjectReferenceImage fields ---")
try:
    print(types.SubjectReferenceImage.model_fields.keys())
except:
    print("No model_fields")
