#!/usr/bin/env python3
"""Test the actual Gemini API call to see where the error occurs."""

import sys
import os
sys.path.insert(0, 'execution')

from dotenv import load_dotenv
load_dotenv()

from gemini_client import generate_content
from research_templates import get_template, build_research_queries

# Test with educational_explainer
template_id = 'educational_explainer'
topic = 'why it is suck to be an influancer in 2026'
use_search = True
model_name = "gemini-2.5-pro"

# Build the prompt exactly as the server does
queries = build_research_queries(template_id, topic)
template = get_template(template_id)
analysis_questions = template["research_config"]["analysis_questions"]

research_prompt = f"""You are a world-class research analyst. Conduct thorough research on the following topic.

TOPIC: {topic}

RESEARCH LAYERS (investigate each one):
{chr(10).join(f'{i+1}. {q}' for i, q in enumerate(queries))}

ANALYSIS QUESTIONS (answer each one with specific facts, names, numbers, dates):
{chr(10).join(f'{i+1}. {q}' for i, q in enumerate(analysis_questions))}

Return a JSON object:
{{
  "results": [
    {{"question": "the analysis question", "answer": "detailed answer with specifics"}}
  ],
  "key_facts": ["fact1", "fact2", ...],
  "sources_mentioned": ["source1", "source2", ...],
  "summary": "2-3 paragraph executive summary of all findings"
}}

Be as specific as possible — include names, dates, amounts, percentages. No vague language.
Return ONLY the JSON."""

print("Prompt built successfully")
print(f"Prompt length: {len(research_prompt)} chars")
print(f"Prompt type: {type(research_prompt)}")
print("\nCalling Gemini API...")

try:
    result = generate_content(research_prompt, model_name=model_name, use_search=use_search)
    print(f"\nSUCCESS!")
    print(f"Result type: {type(result)}")
    print(f"Result length: {len(result)} chars")
    print(f"\nFirst 200 chars:\n{result[:200]}")
except Exception as e:
    print(f"\nERROR: {e}")
    import traceback
    traceback.print_exc()
