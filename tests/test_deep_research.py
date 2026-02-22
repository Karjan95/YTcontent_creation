#!/usr/bin/env python3
import requests
import json
import sys

print("Testing deep research mode...")

try:
    response = requests.post(
        'http://localhost:8080/api/research',
        headers={'Content-Type': 'application/json'},
        json={
            'topic': 'why it is suck to be an influancer in 2026',
            'template_id': 'educational_explainer',
            'research_model': 'deep'
        },
        timeout=60
    )

    print(f"Status code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print("✓ Research SUCCESS!")
        print(f"Summary length: {len(data.get('summary', ''))}")
        print(f"Key facts: {len(data.get('key_facts', []))}")
    else:
        print("✗ Research FAILED!")
        print(f"Response: {response.text[:500]}")

except requests.exceptions.Timeout:
    print("✗ Request TIMED OUT after 60 seconds")
except Exception as e:
    print(f"✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
