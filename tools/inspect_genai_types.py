
from google import genai
from google.genai import types

print("Searching for 'Reference' or 'Style' in types...")
for x in dir(types):
    if "Reference" in x or "Style" in x:
        print(f"Found: {x}")
