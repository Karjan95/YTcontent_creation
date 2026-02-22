#!/usr/bin/env python3
"""Test script to reproduce the research error."""

import sys
sys.path.insert(0, 'execution')

from research_templates import get_template, build_research_queries

# Test with the same parameters from the screenshot
template_id = 'educational_explainer'
topic = 'why it is suck to be an influancer in 2026'

print(f"Testing with template_id={template_id}, topic={topic}")

# Get template
template = get_template(template_id)
print(f"\n1. Template found: {template is not None}")

# Build queries
queries = build_research_queries(template_id, topic)
print(f"\n2. Queries built: {len(queries)} queries")
for i, q in enumerate(queries):
    print(f"   Query {i}: {type(q).__name__} = {repr(q)}")

# Get analysis questions
analysis_questions = template["research_config"]["analysis_questions"]
print(f"\n3. Analysis questions: {len(analysis_questions)} questions")
for i, q in enumerate(analysis_questions):
    print(f"   Question {i}: {type(q).__name__} = {repr(q)}")

# Try to build the prompt (this is where the error occurs)
print("\n4. Building research prompt...")
try:
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

    print("SUCCESS! Prompt built successfully")
    print(f"\nPrompt length: {len(research_prompt)} chars")
    print(f"\nFirst 500 chars:\n{research_prompt[:500]}")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
