
from google import genai
from google.genai import types
import inspect

print("--- types.GenerateContentConfig ---")
for x in dir(types.GenerateContentConfig):
    if not x.startswith('_'):
        print(x)

print("\n--- types.ImageConfig ---")
for x in dir(types.ImageConfig):
    if not x.startswith('_'):
        print(x)

print("\n--- types.Part ---")
for x in dir(types.Part):
    if not x.startswith('_'):
        print(x)
