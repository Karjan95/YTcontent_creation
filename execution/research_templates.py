"""
Research & Script Writing Templates
====================================
Each template defines:
- research_config: How NotebookLM should research the topic
- script_config: How Gemini should write the script
- metadata: Display info for the UI
"""

import json

TEMPLATES = {

    # ─────────────────────────────────────────────────────────────
    # 1. INVESTIGATIVE EXPOSÉ
    # ─────────────────────────────────────────────────────────────
    "investigative_expose": {
        "metadata": {
            "name": "Investigative Exposé",
            "icon": "🔍",
            "description": "Scandals, fraud, corruption, dark truths. Multi-layer deep dive with villains, victims, and a dramatic arc.",
            "best_for": "Exposing wrongdoing, corporate scandals, systemic issues",
            "example_topics": [
                "Fast fashion's hidden labor exploitation",
                "The opioid crisis cover-up",
                "Crypto exchange fraud"
            ]
        },
        "research_config": {
            "mode": "deep",
            "search_layers": [
                {"name": "Surface", "query_template": "{topic} overview how it works history key players market size"},
                {"name": "Dark Side", "query_template": "{topic} scandal fraud lawsuit investigation whistleblower victims corruption"},
                {"name": "Money Trail", "query_template": "{topic} profits who benefits tax evasion shell companies SEC filings financial"},
                {"name": "Key People", "query_template": "{topic} CEO founder controversy lawsuit net worth criminal charges"},
                {"name": "Expert Analysis", "query_template": "{topic} ProPublica NYT investigation academic study congressional hearing ICIJ"}
            ],
            "min_sources": 15,
            "source_types": {
                "primary_documents": 3,
                "investigative_journalism": 3,
                "expert_academic": 2,
                "victim_accounts": 2,
                "news_coverage": 5
            },
            "analysis_questions": [
                "Who are the main villains — their names, roles, specific actions, and how much they profited?",
                "Who are the victims — how many, what were their losses, and what are their specific stories?",
                "Who tried to stop it — whistleblowers, investigators, journalists — and what happened to them?",
                "What is the complete timeline from origin to current consequences?",
                "Follow the money: who profits, who pays, how is it hidden, what is the total scale?",
                "What systemic failures or enablers allowed this to happen?"
            ]
        },
        "script_config": {
            "system_prompt": (
                "You are an elite investigative journalist and documentary scriptwriter. "
                "Create a professional video script with director-level production specs.\n\n"
                "CRITICAL RULES:\n"
                "- Include specific names, amounts, dates — no vague language\n"
                "- Follow 4-Second Rule (each row = 3-5 sec max)\n"
                "- Every claim must be sourced from the research\n"
            ),
            "story_structure": {
                "acts": [
                    {
                        "name": "ACT 1 — The Hook",
                        "percentage": 25,
                        "beats": ["Hook (never use dates)", "Establish the world", "Reveal the scale", "Introduce the players", "The crack that starts to show"]
                    },
                    {
                        "name": "ACT 2 — The Unraveling",
                        "percentage": 60,
                        "beats": [
                            "Revelation 1", "How it actually works", "The villain up close",
                            "Revelation 2", "Victim story (emotional)", "Revelation 3",
                            "The system that enables it", "Midpoint twist",
                            "The hero / whistleblower", "Confrontation moment"
                        ]
                    },
                    {
                        "name": "ACT 3 — The Reckoning",
                        "percentage": 15,
                        "beats": ["Villain's fate", "Victim update", "System status today", "The question for the viewer"]
                    }
                ],
                "hook_types": ["Question", "Contradiction", "Sound/Action", "Result First", "Statistic Shock", "Mystery", "Direct Address"],
                "emotional_beats": {
                    "outrage": 2,
                    "human_impact": 2,
                    "quiet_moment": 1,
                    "shocking_reveal": 1,
                    "hope": 1
                }
            },
            "stakeholder_map": ["2+ Villains", "2+ Victims", "1+ Heroes", "1+ Enablers", "2+ Experts"],
            "pacing_guide": {
                5: 75,
                10: 150,
                15: 225,
                20: 300
            }
        }
    },

    # ─────────────────────────────────────────────────────────────
    # 2. EDUCATIONAL EXPLAINER
    # ─────────────────────────────────────────────────────────────
    "educational_explainer": {
        "metadata": {
            "name": "Educational Explainer",
            "icon": "🎓",
            "description": "Break down complex topics into clear, engaging explanations using analogies, visuals, and progressive complexity.",
            "best_for": "Science, history, how things work, technology concepts",
            "example_topics": [
                "How does mRNA vaccine technology work",
                "The history of money from barter to bitcoin",
                "How black holes are formed"
            ]
        },
        "research_config": {
            "mode": "fast",
            "search_layers": [
                {"name": "Fundamentals", "query_template": "{topic} explained basics how it works definition simple explanation"},
                {"name": "Mechanics", "query_template": "{topic} detailed mechanism process steps science technology behind"},
                {"name": "Implications", "query_template": "{topic} impact significance future applications real world examples why it matters"}
            ],
            "min_sources": 10,
            "source_types": {
                "educational_content": 3,
                "scientific_papers": 2,
                "expert_explanations": 3,
                "visual_references": 2
            },
            "analysis_questions": [
                "What is the simplest, most accurate explanation of this concept? Use an everyday analogy.",
                "What are the 3-5 key components or steps that make this work?",
                "What are the most common misconceptions about this topic?",
                "What are the most mind-blowing or surprising facts about this?",
                "What real-world examples or applications make this tangible?",
                "What are the latest developments or discoveries in this area?"
            ]
        },
        "script_config": {
            "system_prompt": (
                "You are a world-class science communicator like Kurzgesagt or Veritasium. "
                "Create an engaging explanation video script that makes complex ideas accessible.\n\n"
                "CRITICAL RULES:\n"
                "- Start with the 'why should I care' hook\n"
                "- Use concrete analogies for every abstract concept\n"
                "- Build complexity gradually — never dump information\n"
                "- Each row = 3-5 sec of screen time\n"
            ),
            "story_structure": {
                "acts": [
                    {
                        "name": "THE HOOK — Why You Should Care",
                        "percentage": 15,
                        "beats": ["Surprising fact or question", "Why this matters to YOU", "What we'll discover"]
                    },
                    {
                        "name": "THE FOUNDATION — Build Understanding",
                        "percentage": 25,
                        "beats": ["The simple version (analogy)", "Core concept #1", "Visual demonstration", "Common misconception busted"]
                    },
                    {
                        "name": "THE DEEP DIVE — How It Really Works",
                        "percentage": 40,
                        "beats": [
                            "Core concept #2 (building on #1)", "The mechanism in detail",
                            "Real-world example", "Core concept #3",
                            "The 'aha moment'", "Expert insight or quote"
                        ]
                    },
                    {
                        "name": "THE PAYOFF — So What?",
                        "percentage": 20,
                        "beats": ["Real-world applications", "Future implications", "Mind-blowing final fact", "Call to curiosity"]
                    }
                ],
                "hook_types": ["Surprising Stat", "Wrong Assumption", "Scale Comparison", "Time Warp", "What If Scenario"],
                "emotional_beats": {
                    "curiosity": 3,
                    "aha_moment": 2,
                    "wonder": 2,
                    "surprise": 1
                }
            },
            "pacing_guide": {
                5: 60,
                10: 120,
                15: 180,
                20: 240
            }
        }
    },

    # ─────────────────────────────────────────────────────────────
    # 3. PRODUCT / TECH REVIEW
    # ─────────────────────────────────────────────────────────────
    "product_tech_review": {
        "metadata": {
            "name": "Product / Tech Review",
            "icon": "⚡",
            "description": "In-depth analysis of products, technology, or services with specs, comparisons, and a clear verdict.",
            "best_for": "Tech reviews, product comparisons, market analysis, startup breakdowns",
            "example_topics": [
                "Apple Vision Pro — one year later",
                "Is the Tesla Cybertruck actually worth it",
                "AI coding assistants compared: Cursor vs GitHub Copilot"
            ]
        },
        "research_config": {
            "mode": "fast",
            "search_layers": [
                {"name": "Specs & Features", "query_template": "{topic} specifications features details what's new official"},
                {"name": "Real-World Use", "query_template": "{topic} review hands-on experience real world problems issues"},
                {"name": "Competition", "query_template": "{topic} vs alternatives competitors comparison better than"},
                {"name": "Value & Verdict", "query_template": "{topic} worth it price value long term investment opinion expert review"}
            ],
            "min_sources": 10,
            "source_types": {
                "official_specs": 2,
                "expert_reviews": 3,
                "user_experiences": 3,
                "comparison_articles": 2
            },
            "analysis_questions": [
                "What are the exact specifications, pricing tiers, and key features?",
                "What do expert reviewers agree is the biggest strength?",
                "What do experts agree is the biggest weakness or disappointment?",
                "How does it compare to the top 2-3 competitors on key metrics?",
                "What are real users saying — common praise and complaints?",
                "What is the total cost of ownership and who should / shouldn't buy this?"
            ]
        },
        "script_config": {
            "system_prompt": (
                "You are a tech reviewer like MKBHD or Linus Tech Tips. "
                "Create an honest, detailed review script that helps viewers make informed decisions.\n\n"
                "CRITICAL RULES:\n"
                "- Lead with real experience, not spec sheets\n"
                "- Include specific numbers, benchmarks, prices\n"
                "- Fair comparison — acknowledge strengths of competitors\n"
                "- Each row = 3-5 sec of screen time\n"
            ),
            "story_structure": {
                "acts": [
                    {
                        "name": "THE HOOK — First Impression",
                        "percentage": 10,
                        "beats": ["Hot take opener", "Why this matters now", "What I'll cover"]
                    },
                    {
                        "name": "OVERVIEW — What Is It?",
                        "percentage": 15,
                        "beats": ["What it is and who it's for", "Key specs at a glance", "Price and availability"]
                    },
                    {
                        "name": "DEEP DIVE — The Good, The Bad, The Ugly",
                        "percentage": 50,
                        "beats": [
                            "Feature #1 deep dive", "Feature #2 deep dive",
                            "Feature #3 deep dive", "What surprised me",
                            "The biggest problem", "Competitor comparison moment"
                        ]
                    },
                    {
                        "name": "THE VERDICT",
                        "percentage": 25,
                        "beats": ["Who should buy this", "Who should NOT buy this", "Best alternatives", "Final score / recommendation", "What I'd change"]
                    }
                ],
                "hook_types": ["Bold Claim", "Before/After", "The One Thing", "Myth Bust", "Hot Take"],
                "emotional_beats": {
                    "excitement": 2,
                    "disappointment": 1,
                    "surprise": 1,
                    "satisfaction": 1
                }
            },
            "pacing_guide": {
                5: 60,
                10: 130,
                15: 195,
                20: 260
            }
        }
    },

    # ─────────────────────────────────────────────────────────────
    # 4. PERSONAL STORY / DOCUMENTARY
    # ─────────────────────────────────────────────────────────────
    "personal_story_documentary": {
        "metadata": {
            "name": "Personal Story / Documentary",
            "icon": "🎬",
            "description": "Character-driven narratives about real people, communities, or movements. Emotional storytelling with context.",
            "best_for": "Biographies, community profiles, social movements, human interest",
            "example_topics": [
                "Elon Musk: genius or con man?",
                "The town that banned smartphones for kids",
                "How one teacher changed a school district forever"
            ]
        },
        "research_config": {
            "mode": "deep",
            "search_layers": [
                {"name": "The Subject", "query_template": "{topic} story background origin who biography profile"},
                {"name": "The Context", "query_template": "{topic} context environment conditions society culture why how"},
                {"name": "The Arc", "query_template": "{topic} transformation change journey challenge struggle success failure turning point"},
                {"name": "The Legacy", "query_template": "{topic} impact legacy influence aftermath what happened next current status"}
            ],
            "min_sources": 12,
            "source_types": {
                "biographical_profiles": 3,
                "interviews_quotes": 3,
                "contextual_reporting": 3,
                "impact_analysis": 3
            },
            "analysis_questions": [
                "Who is the central character — what is their background, personality, and defining traits?",
                "What was the inciting incident — the moment everything changed?",
                "What obstacles did they face, and what were the lowest points?",
                "Who supported them and who opposed them? Name specific people.",
                "What was the climax — the decisive moment or achievement?",
                "What is the lasting impact, and where are they now?"
            ]
        },
        "script_config": {
            "system_prompt": (
                "You are a documentary filmmaker. "
                "Create a character-driven narrative script that makes viewers feel deeply connected to the subject.\n\n"
                "CRITICAL RULES:\n"
                "- Show don't tell — use scenes, dialogue, moments\n"
                "- Build empathy before revealing flaws\n"
                "- Include specific sensory details (what they wore, the room, the weather)\n"
                "- Each row = 3-5 sec of screen time\n"
            ),
            "story_structure": {
                "acts": [
                    {
                        "name": "THE WORLD — Before Everything Changed",
                        "percentage": 20,
                        "beats": ["A powerful scene/moment", "Who this person is", "Their ordinary world", "The thing they cared about most"]
                    },
                    {
                        "name": "THE CALL — Something Breaks",
                        "percentage": 15,
                        "beats": ["The inciting incident", "The impossible choice", "What they decided to do"]
                    },
                    {
                        "name": "THE STRUGGLE — The Price of Change",
                        "percentage": 35,
                        "beats": [
                            "First obstacle", "Small victory", "Allies appear",
                            "The deepest valley", "Opposition intensifies",
                            "The moment they almost gave up"
                        ]
                    },
                    {
                        "name": "THE TRANSFORMATION — Who They Became",
                        "percentage": 15,
                        "beats": ["The breakthrough", "The victory (or acceptance)", "How they changed"]
                    },
                    {
                        "name": "THE LEGACY — What It Means",
                        "percentage": 15,
                        "beats": ["Where they are now", "The ripple effects", "What we can learn", "Final image"]
                    }
                ],
                "hook_types": ["In-Media-Res Scene", "Contrast (Then vs Now)", "A Single Detail", "Opening Dialogue", "Quiet Moment"],
                "emotional_beats": {
                    "empathy": 3,
                    "tension": 2,
                    "heartbreak": 1,
                    "triumph": 1,
                    "reflection": 1
                }
            },
            "pacing_guide": {
                5: 65,
                10: 130,
                15: 200,
                20: 270
            }
        }
    },

    # ─────────────────────────────────────────────────────────────
    # 5. TRENDING NEWS / HOT TAKE
    # ─────────────────────────────────────────────────────────────
    "trending_news_hot_take": {
        "metadata": {
            "name": "Trending News / Hot Take",
            "icon": "🔥",
            "description": "Fast-paced commentary on current events, debates, or viral topics with a strong perspective and rapid pacing.",
            "best_for": "Breaking news analysis, viral stories, debate topics, opinion pieces",
            "example_topics": [
                "Why everyone is wrong about AI replacing jobs",
                "The TikTok ban — what actually happens next",
                "This new study just changed everything about diet science"
            ]
        },
        "research_config": {
            "mode": "fast",
            "search_layers": [
                {"name": "Breaking Facts", "query_template": "{topic} latest news facts details what happened when confirmed"},
                {"name": "Context & History", "query_template": "{topic} context background history why this matters precedent similar cases"},
                {"name": "Perspectives", "query_template": "{topic} opinion debate arguments for against expert reaction criticism support"}
            ],
            "min_sources": 8,
            "source_types": {
                "breaking_news": 3,
                "analysis_opinion": 3,
                "expert_reactions": 2
            },
            "analysis_questions": [
                "What exactly happened — verified facts only, with dates and names?",
                "What is the immediate impact and who is affected?",
                "What are the top 3 perspectives or arguments on this?",
                "What historical precedent or context makes this significant?",
                "What are people getting wrong or overlooking?",
                "What happens next — most likely scenarios?"
            ]
        },
        "script_config": {
            "system_prompt": (
                "You are a sharp, fast-paced news commentator like Johnny Harris or TLDR News. "
                "Create a script that informs AND has a clear perspective.\n\n"
                "CRITICAL RULES:\n"
                "- Open with energy — you have 3 seconds before they scroll away\n"
                "- Bold opinions backed by specific evidence\n"
                "- Address counter-arguments head-on\n"
                "- Each row = 3-5 sec of screen time\n"
            ),
            "story_structure": {
                "acts": [
                    {
                        "name": "THE BOMB — What Just Happened",
                        "percentage": 15,
                        "beats": ["Explosive opener", "The headline fact", "Why you should care RIGHT NOW"]
                    },
                    {
                        "name": "THE CONTEXT — What Nobody's Telling You",
                        "percentage": 25,
                        "beats": ["The backstory in 60 seconds", "The key players", "What led to this moment", "The hidden connection"]
                    },
                    {
                        "name": "THE TAKE — Here's What I Think",
                        "percentage": 40,
                        "beats": [
                            "My main argument", "Evidence point #1",
                            "Evidence point #2", "The counter-argument (steel-manned)",
                            "Why the counter-argument falls short",
                            "The thing everyone's missing"
                        ]
                    },
                    {
                        "name": "THE PREDICTION — What Happens Next",
                        "percentage": 20,
                        "beats": ["Most likely outcome", "Wild card scenario", "What to watch for", "Your turn — drop a comment"]
                    }
                ],
                "hook_types": ["Breaking Statement", "Pop Culture Parallel", "Absurd Stat", "Calling Out", "Prediction"],
                "emotional_beats": {
                    "urgency": 2,
                    "conviction": 2,
                    "surprise": 1,
                    "engagement": 1
                }
            },
            "pacing_guide": {
                5: 80,
                10: 160,
                15: 240,
                20: 320
            }
        }
    }
}


def get_template(template_id: str) -> dict:
    """Get a single template by ID."""
    return TEMPLATES.get(template_id)


def get_all_templates_metadata() -> list:
    """Return metadata for all templates (for UI display)."""
    return [
        {"id": tid, **t["metadata"]}
        for tid, t in TEMPLATES.items()
    ]


def build_research_queries(template_id: str, topic: str) -> list:
    """Build search queries from a template's layers for a given topic."""
    template = TEMPLATES.get(template_id)
    if not template:
        return [topic]
    queries = []
    for layer in template["research_config"]["search_layers"]:
        queries.append(layer["query_template"].format(topic=topic))
    return queries


def build_script_prompt(template_id: str, topic: str, research_dossier: str,
                        duration_minutes: int = 10, audience: str = "General",
                        tone: str = "", focus: str = "", style_guide: str = None) -> str:
    """
    PHASE 1: Build prompt for the creative narration.
    
    Asks Gemini to write a flowing, compelling narration organized by acts/beats.
    No word-count limits, no timestamps — pure storytelling.
    The output will be fed into Phase 2 (build_breakdown_prompt) for scene breakdown.
    """
    template = TEMPLATES.get(template_id)
    if not template:
        return f"Write a {duration_minutes}-minute video script about: {topic}"

    sc = template["script_config"]
    structure = sc["story_structure"]

    # Build act descriptions
    acts_text = ""
    for act in structure["acts"]:
        beats_str = ", ".join(act["beats"])
        acts_text += f"\n### {act['name']} ({act['percentage']}% of total)\nBeats: {beats_str}\n"

    # Build emotional beats requirement
    emo_text = ", ".join(
        f"{count}+ {beat.replace('_', ' ').title()}" for beat, count in structure["emotional_beats"].items()
    )

    # Word-count target based on speech pacing
    total_words = int(duration_minutes * 60 * 2.5)  # ~2.5 words/sec

    # Handle Style Guide Override
    system_prompt = sc['system_prompt']
    style_section = ""
    
    if style_guide:
        system_prompt = (
            "You are a chameleon scriptwriter. "
            "Your goal is to replicate the EXACT style, tone, and structure of a specific YouTube creator "
            "based on the provided Style Guide, while using the Research Dossier for factual content.\n\n"
            "CRITICAL RULES:\n"
            "- IGNORE the default template tone if it conflicts with the Style Guide\n"
            "- ADOPT the vocabulary, pacing, and hook style defined below\n"
        )
        style_section = f"\n═══════ CUSTOM STYLE GUIDE (MIMIC THIS) ═══════\n{style_guide}\n"
    
    prompt = f"""{system_prompt}

═══════ ASSIGNMENT ═══════
TOPIC: {topic}
LENGTH: {duration_minutes} minutes (~{total_words} words of narration)
AUDIENCE: {audience}
TONE: {tone or ('Match the Style Guide' if style_guide else 'As appropriate for the template')}
{f'FOCUS: {focus}' if focus else ''}

═══════ RESEARCH DOSSIER ═══════
{research_dossier}
{style_section}
═══════ STORY STRUCTURE ═══════
{acts_text}

═══════ REQUIREMENTS ═══════
- Target approximately {total_words} words of narration (for {duration_minutes} minutes at natural speaking pace)
- Required emotional beats: {emo_text}
- Hook types to choose from: {', '.join(structure['hook_types'])}
- Every fact, name, number must come from the research above
- NO placeholder text — be specific
- Write ONLY the narration — the words a narrator would speak
- Organize by Acts and Beats using the structure above

═══════ OUTPUT FORMAT ═══════
Return a JSON object with this structure:
{{
  "title": "Compelling video title",
  "hook_type": "Which hook type you chose",
  "summary": "1-paragraph summary of the script's narrative arc",
  "duration_minutes": {duration_minutes},
  "narration": [
    {{
      "act": "ACT 1",
      "beat": "Dramatic Hook",
      "text": "The full narration text for this beat. Write it as flowing prose — as many sentences as needed to fill the beat's share of the total duration. Be compelling, specific, and vivid. Use facts from the research dossier."
    }},
    {{
      "act": "ACT 1",
      "beat": "Context / Stakes",
      "text": "The narration for this beat..."
    }}
  ],
  "sources_used": ["source1", "source2"]
}}

CRITICAL: Write the narration as if you are speaking to the viewer. Make it compelling, vivid, conversational.
Each beat should flow naturally into the next. The narration should be a COMPLETE script — nothing left out.
Do NOT include timestamps, scene numbers, or visual directions. Just the spoken words.

Return ONLY the JSON. Begin."""

    return prompt


def build_breakdown_prompt(narration_json: dict, duration_minutes: int = 10,
                           template_id: str = "educational_explainer") -> str:
    """
    PHASE 2: Build prompt for the scene breakdown.

    Takes the Phase 1 narration output and asks Gemini to break it
    into timed scene rows with accurate speech pacing.
    """
    template = TEMPLATES.get(template_id)

    # Speech pacing constants
    WORDS_PER_SECOND = 2.5
    SECONDS_PER_SCENE_AVG = 3.5
    total_seconds = duration_minutes * 60
    target_scenes = int(total_seconds / SECONDS_PER_SCENE_AVG)

    # Extract the narration text from Phase 1 output
    narration_parts = []
    if isinstance(narration_json.get("narration"), list):
        for beat in narration_json["narration"]:
            act = beat.get("act", "")
            beat_name = beat.get("beat", "")
            text = beat.get("text", "")
            narration_parts.append(f"[{act} — {beat_name}]\n{text}")
    
    full_narration = "\n\n".join(narration_parts)
    title = narration_json.get("title", "Untitled")
    hook_type = narration_json.get("hook_type", "")
    summary = narration_json.get("summary", "")

    prompt = f"""You are a professional video editor and scene breakdown specialist.

Your job is to take a complete narration script and break it into a timed scene-by-scene
production table for video editing.

═══════ THE NARRATION SCRIPT ═══════

Title: {title}
Hook Type: {hook_type}
Duration: {duration_minutes} minutes
Summary: {summary}

--- FULL NARRATION ---
{full_narration}
--- END NARRATION ---

═══════ SPEECH PACING RULES ═══════

Average human speech rate: {WORDS_PER_SECOND} words per second.

HOW TO CREATE EACH SCENE ROW:
1. Take a SHORT phrase from the narration (5-15 words)
2. Count the words in that phrase
3. Calculate duration: words ÷ {WORDS_PER_SECOND} = seconds (round to nearest whole second)
4. Set timestamp: scene start = previous scene end
5. Assign a visual description for that moment
6. Tag the emotion the viewer should feel

RULES:
- Each narration cell MUST be 5-15 words. NEVER exceed 15 words.
- The narration must NOT be rewritten — use the EXACT words from the script above.
  You may split sentences at natural pause points (commas, periods, em-dashes, semicolons).
- Every single word from the narration must appear in exactly one scene row. No words dropped.
- Timestamps must be mathematically accurate: duration = word_count / {WORDS_PER_SECOND}
- Target approximately {target_scenes} scenes total.
- Each scene = ONE visual beat = ONE camera shot.

EXAMPLE:
  Original narration: "Imagine a world where your word is law, your wealth immense, and your enemies silenced. A life painted by Hollywood, of power and unquestioning loyalty."

  CORRECT breakdown:
  Scene 1 | 00:00-00:04 | "Imagine a world where your word is law," | 9 words | 3.6s ≈ 4s
  Scene 2 | 00:04-00:06 | "your wealth immense, and your enemies silenced." | 7 words | 2.8s ≈ 2s
  Scene 3 | 00:06-00:10 | "A life painted by Hollywood, of power and unquestioning loyalty." | 11 words | 4.4s ≈ 4s

═══════ VISUAL DIRECTION GUIDE ═══════

For each scene's "visual" field, describe what should appear on screen:
- Be specific: "Close-up of weathered hands counting cash" not "money shot"
- Match the emotional tone of the narration
- Think like a documentary editor: every cut has purpose
- Ensure visual continuity — each scene should connect logically to the next
- Use varied shot types: wide establishing, medium, close-up, detail, aerial, etc.

═══════ OUTPUT FORMAT ═══════

Return a JSON object with this EXACT structure:
{{
  "title": "{title}",
  "hook_type": "{hook_type}",
  "summary": "{summary}",
  "total_scenes": {target_scenes},
  "duration_minutes": {duration_minutes},
  "script": [
    {{
      "scene": 1,
      "timestamp": "00:00-00:04",
      "act": "ACT 1",
      "beat": "Dramatic Hook",
      "narration": "Imagine a world where your word is law,",
      "visual": "Dramatic slow-motion shot of a shadowy figure in a tailored suit, stepping through ornate double doors into a dimly lit room",
      "emotion": "Curiosity",
      "notes": ""
    }},
    {{
      "scene": 2,
      "timestamp": "00:04-00:06",
      "act": "ACT 1",
      "beat": "Dramatic Hook",
      "narration": "your wealth immense, and your enemies silenced.",
      "visual": "Quick montage: stacks of cash, gold watches, then a dark empty chair",
      "emotion": "Intrigue",
      "notes": ""
    }}
  ],
  "sources_used": {json.dumps(narration_json.get("sources_used", []))}
}}

CRITICAL REMINDERS:
- Use the EXACT narration words. Do not paraphrase or rewrite.
- Every word must appear in exactly one scene row.
- Timestamps must be sequential and mathematically based on word count.
- Each narration cell: 5-15 words maximum.

⚠️⚠️⚠️ JSON SYNTAX VALIDATION ⚠️⚠️⚠️
CRITICAL: You MUST generate VALID JSON with correct syntax:
1. Every field MUST end with a comma EXCEPT the last field in an object
2. All string values MUST be properly escaped (use \\" for quotes, \\\\ for backslashes)
3. Do NOT put commas after the last field in an object
4. ALWAYS put a comma after every object in the "script" array EXCEPT the last one
5. Check your JSON is valid before returning it

COMMON MISTAKES TO AVOID:
❌ "narration": "text"
    "visual": "text"  ← MISSING COMMA after narration
✅ "narration": "text",
    "visual": "text"

Return ONLY the JSON. Begin."""

    return prompt


# ═══════════════════════════════════════════════════════════════════
#  PHASE 3: PRODUCTION TABLE
# ═══════════════════════════════════════════════════════════════════

DEFAULT_STYLE_CONFIG = {
    "genre": "Cinematic Drama",
    "color_world": "Neutral",
    "lighting": "Natural / Available Light",
    "camera_personality": "Authoritative",
    "movement_style": "Subtle Movement",
    "aspect_ratio": "16:9",
    "image_model": "Generic",
}


def build_production_prompt(scene_breakdown_json: dict,
                            style_config: dict = None,
                            style_analysis: str = None) -> str:
    """
    PHASE 3: Build prompt for the Production Table.

    Takes the Phase 2 scene breakdown and either:
    - style_config: manual dropdown settings
    - style_analysis: AI-analyzed style from reference images (takes priority)

    Instructs Gemini to act as a 3-person creative team
    (Director + Storyboard Artist + Director of Photography)
    to produce first-frame prompts, last-frame prompts, and
    Veo 3.1 video prompts for every scene.
    """
    style = {**DEFAULT_STYLE_CONFIG, **(style_config or {})}

    # Extract scenes from breakdown
    scenes = scene_breakdown_json.get("script", [])
    title = scene_breakdown_json.get("title", "Untitled")
    duration = scene_breakdown_json.get("duration_minutes", 10)

    # Format the scene breakdown for the prompt
    scenes_text = ""
    for s in scenes:
        scenes_text += (
            f"Scene {s.get('scene', '?')} | {s.get('timestamp', '')} | "
            f"Act: {s.get('act', '')} | Beat: {s.get('beat', '')} | "
            f"Narration: \"{s.get('narration', '')}\" | "
            f"Visual: {s.get('visual', '')} | "
            f"Emotion: {s.get('emotion', '')}\n"
        )

    # Build visual style section based on source
    if style_analysis:
        # Use AI-analyzed style from reference images
        visual_style_section = f"""═══════ VISUAL STYLE (FROM REFERENCE IMAGES) ═══════
{style_analysis}

**IMPORTANT**: Apply this exact visual style to ALL prompts. Match the color palette, lighting, mood, composition, and aesthetic described above."""
    else:
        # Use manual settings from dropdowns
        visual_style_section = f"""═══════ VISUAL STYLE ═══════
Genre/Tone: {style['genre']}
Color World: {style['color_world']}
Lighting Philosophy: {style['lighting']}
Camera Personality: {style['camera_personality']}
Movement Style: {style['movement_style']}
Aspect Ratio: {style['aspect_ratio']}
Image Generation Model: {style['image_model']}"""

    prompt = f"""You are a professional film production team consisting of three creative roles:
1. THE DIRECTOR — story, emotion, performance, pacing
2. THE STORYBOARD ARTIST — visual sequence, composition, shot flow
3. THE DIRECTOR OF PHOTOGRAPHY — camera, lighting, lens, visual style

⚠️⚠️⚠️ CRITICAL INSTRUCTION ⚠️⚠️⚠️
Your job is to create PRODUCTION PROMPTS (first-frame, last-frame, Veo video prompts) for the EXACT scenes provided below.
- DO NOT create new scenes
- DO NOT rewrite or change the narration text
- DO NOT add your own creative ideas to the story
- USE ONLY the scenes and narration provided in the Scene Breakdown

Your ONLY job: take each scene's narration VERBATIM and create image/video prompts for it.

═══════ PROJECT INFO ═══════
Title: {title}
Duration: {duration} minutes
Total Scenes: {len(scenes)}

{visual_style_section}

═══════ SCENE BREAKDOWN (from Phase 2) ═══════
⚠️ USE THESE SCENES EXACTLY AS PROVIDED - DO NOT MODIFY THE NARRATION ⚠️
{scenes_text}

═══════ VEO 3.1 TECHNICAL CONSTRAINTS ═══════

DURATION: Only 4s, 6s, or 8s per clip. Maximum 8 seconds.
- Simple motion (expression change, subtle shift) → 4s
- Moderate motion (gesture, slow pan) → 6s
- Complex motion (walk, full camera move) → 8s

RESOLUTION & ASPECT:
- 16:9: 1920×1080 | 9:16: 1080×1920
- First & Last frame MUST match exactly

ACHIEVABLE MOTION (within timeframe):
✅ Subtle weight shifts (4s), head turns (4s), hand gestures (4-6s),
   standing to sitting (6-8s), walking few steps (4-8s),
   subtle camera push/pull (4-8s), pan up to 90° (6-8s)
⚠️ Challenging: 90° orbit, multi-part actions, running (8s, simplify)
❌ Impossible: location changes, day-to-night, wardrobe changes, 180°+ camera moves

FRAME COMPATIBILITY (MUST MATCH between first & last frame):
- Subject: identical features, build, face
- Wardrobe: exact same clothing
- Environment: same location, same visible elements
- Lighting direction: same key light position
- Color temperature: same balance
- Style: same color grade, same aesthetic
- Aspect ratio: identical

═══════ OUTPUT FORMAT ═══════

For each scene, produce a row in the production table.
You may merge very short scenes (< 3s) into a single shot if it makes visual sense.

⚠️ NOTE: The "script_beat" field will be filled in automatically from the input scenes.
You can leave it as an empty string "" or put a placeholder like "AUTO".
The system will programmatically insert the exact narration text after you generate the prompts.

FIRST FRAME PROMPT format (for image generation):
```
[SHOT SIZE] of [SUBJECT: age, gender, distinctive features, wardrobe], [POSE/ACTION], [EXPRESSION].
[ENVIRONMENT: specific location, key details].
[LIGHTING: key direction, quality, color temp, fill, practicals].
[CAMERA: angle, height, lens mm, DOF].
[STYLE: aesthetic, color grade, texture, film stock].
[TECHNICAL: {style['aspect_ratio']}, high resolution].
--
Exclude: [specific exclusions]
```

LAST FRAME PROMPT format (matching — must preserve identity):
```
[SHOT SIZE] of [IDENTICAL SUBJECT DESCRIPTION], [END POSE/ACTION], [END EXPRESSION].
[SAME ENVIRONMENT: note any changes].
[SAME LIGHTING: note any motivated shifts].
[CAMERA: end position if moved, same lens].
[SAME STYLE].
[SAME TECHNICAL].
--
Exclude: [specific exclusions]
```

VEO 3.1 VIDEO PROMPT format:
```
[Shot size] of [subject] [TRANSITIONAL ACTION — what happens between frames] in [environment].
Camera: [movement type, speed, motivation].
Lighting: [conditions, any changes].
Audio: [ambient], [SFX], [dialogue if any].
Style: [aesthetic reference].
--
negative prompt: no text overlays, no watermarks, no logos, [scene-specific exclusions]
```

Return a JSON object with this EXACT structure:
{{
  "title": "{title}",
  "aspect_ratio": "{style['aspect_ratio']}",
  "style_summary": "Brief summary of the visual style applied",
  "total_shots": <number>,
  "shots": [
    {{
      "shot_number": "1-A",
      "scene_refs": [1],
      "script_beat": "",
      "duration": "4s",
      "directors_intent": "What the audience should feel",
      "first_frame_prompt": "Full structured first frame prompt as specified above",
      "last_frame_prompt": "Full structured last frame prompt as specified above",
      "veo_prompt": "Full Veo 3.1 video prompt as specified above"
    }}
  ],
  "continuity_notes": [
    {{
      "from_shot": "1-A",
      "to_shot": "1-B",
      "visual_bridge": "How these connect visually",
      "audio_bridge": "Sound continuity",
      "potential_issue": "If any"
    }}
  ],
  "production_notes": {{
    "challenging_shots": ["Any shots needing extra iterations"],
    "recommended_workflow": "Suggested order of generation",
    "post_production": "Color grading, audio sweetening, transitions to add in edit"
  }}
}}

═══════════════════════════════════════════════════════
CRITICAL RULES (MUST FOLLOW EXACTLY):
═══════════════════════════════════════════════════════
1. **SCENE REFERENCES**: For each shot, include "scene_refs": [scene numbers] to indicate which scenes it covers.
   The system will automatically populate the "script_beat" field with the exact narration from those scenes.
   You can leave "script_beat" as an empty string "".

2. Every shot duration MUST be exactly 4s, 6s, or 8s.
- First and last frame prompts MUST describe the SAME subject, wardrobe, and environment.
- The only difference between frames should be pose, expression, and camera position.
- Maintain visual continuity across ALL shots — same subject appearance, consistent lighting direction.
- Be SPECIFIC in prompts — no vague descriptions. Describe exact clothing, exact colors, exact lighting.
- Apply the visual style CONSISTENTLY across all shots{": " + style['genre'] + ", " + style['color_world'] + " palette, " + style['lighting'] if not style_analysis else " as described in the reference images above"}.

Return ONLY the JSON. Begin."""

    return prompt
