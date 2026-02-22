
from google import genai
from google.genai import types

print("--- types.ImageConfig fields ---")
try:
    print(types.ImageConfig.model_fields.keys())
except:
    print("No model_fields")

print("\n--- types.GenerateContentConfig fields ---")
try:
    print(types.GenerateContentConfig.model_fields.keys())
except:
    print("No model_fields")

print("\n--- types.StyleReferenceConfig fields ---")
try:
    print(types.StyleReferenceConfig.model_fields.keys())
except:
    print("No model_fields")

print("\n--- types.SubjectReferenceConfig fields ---")
try:
    print(types.SubjectReferenceConfig.model_fields.keys())
except:
    print("No model_fields")
