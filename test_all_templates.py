#!/usr/bin/env python3
"""Test all templates to find the problematic one."""

import sys
sys.path.insert(0, 'execution')

from research_templates import get_all_templates_metadata, get_template, build_research_queries

topic = 'test topic'

for template_meta in get_all_templates_metadata():
    template_id = template_meta['id']
    template = get_template(template_id)

    print(f"\n{'='*60}")
    print(f"Testing: {template_id}")
    print(f"{'='*60}")

    try:
        queries = build_research_queries(template_id, topic)
        analysis_questions = template["research_config"]["analysis_questions"]

        print(f"Queries ({len(queries)}):")
        for i, q in enumerate(queries):
            if not isinstance(q, str):
                print(f"  ❌ Query {i}: {type(q)} = {repr(q)}")
            else:
                print(f"  ✓ Query {i}: str")

        print(f"\nQuestions ({len(analysis_questions)}):")
        for i, q in enumerate(analysis_questions):
            if not isinstance(q, str):
                print(f"  ❌ Question {i}: {type(q)} = {repr(q)}")
            else:
                print(f"  ✓ Question {i}: str")

        # Try to build the prompt
        research_prompt = f"""You are a world-class research analyst.

TOPIC: {topic}

RESEARCH LAYERS:
{chr(10).join(f'{i+1}. {q}' for i, q in enumerate(queries))}

ANALYSIS QUESTIONS:
{chr(10).join(f'{i+1}. {q}' for i, q in enumerate(analysis_questions))}"""

        print(f"\n✅ {template_id}: SUCCESS")

    except Exception as e:
        print(f"\n❌ {template_id}: ERROR - {e}")
        import traceback
        traceback.print_exc()
