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
    # 0. GENERAL DEEP DIVE (New Default for Deep Research)
    # ─────────────────────────────────────────────────────────────
    "general_deep_dive": {
        "metadata": {
            "name": "General Deep Dive",
            "icon": "🌐",
            "description": "Comprehensive, fact-based research on any topic. Neutral, detailed, and exhaustive.",
            "best_for": "Deep research on any subject without a specific angle",
            "example_topics": [
                "The history of coffee",
                "SpaceX Starship development",
                "Causes of the French Revolution"
            ]
        },
        "research_config": {
            "mode": "deep",
            "search_layers": [
                {"name": "Overview & History", "query_template": "{topic} history background overview origin timeline key facts"},
                {"name": "How It Works / Details", "query_template": "{topic} detailed explanation mechanism process specifics technical details"},
                {"name": "Impact & Significance", "query_template": "{topic} impact importance significance why it matters statistics data"},
                {"name": "Key Perspectives", "query_template": "{topic} expert opinions different viewpoints controversy debate analysis"},
                {"name": "Future Outlook", "query_template": "{topic} future trends predictions next steps upcoming developments"}
            ],
            "min_sources": 12,
            "source_types": {
                "encyclopedic": 2,
                "news_reports": 4,
                "expert_analysis": 3,
                "official_documents": 3
            },
            "analysis_questions": [
                "What is the comprehensive definition and history of this topic?",
                "Who are the key figures, organizations, or entities involved?",
                "What are the most important facts, dates, and statistics?",
                "How does this work, or what is the detailed mechanism/process?",
                "What is the global or local impact of this topic?",
                "What are the main arguments or perspectives surrounding this?"
            ]
        },
        "script_config": {
            "system_prompt": (
                "You are a skilled documentary writer and researcher. "
                "Create a comprehensive, balanced, and engaging script about this topic.\n\n"
                "CRITICAL RULES:\n"
                "- Focus on accuracy, clarity, and depth\n"
                "- Quote specific facts and sources\n"
                "- Maintain a neutral but engaging tone\n"
                "- Each row = 3-5 sec of screen time\n"
            ),
            "story_structure": {
                "acts": [
                    {
                        "name": "INTRODUCTION",
                        "percentage": 15,
                        "beats": ["The Hook", "Topic Definition", "Significance Statement", "Roadmap of the Video"]
                    },
                    {
                        "name": "BACKGROUND & CONTEXT",
                        "percentage": 25,
                        "beats": ["Origins/History", "Key Context", "The 'Before' State", "Turning Point"]
                    },
                    {
                        "name": "CORE ANALYSIS",
                        "percentage": 40,
                        "beats": [
                            "Key Mechanism/Event 1", "Detailed Explanation",
                            "Key Mechanism/Event 2", "Evidence/Data Point",
                            "Expert Perspective", "Counter-Perspective or Complication"
                        ]
                    },
                    {
                        "name": "CONCLUSION & FUTURE",
                        "percentage": 20,
                        "beats": ["Summary of Main Points", "Current Status", "Future Outlook", "Final Thought/Question"]
                    }
                ],
                "hook_types": ["Did You Know?", "Direct Question", "Bold Statement", "Story Anecdote", "Statistic"],
                "emotional_beats": {
                    "curiosity": 3,
                    "clarity": 3,
                    "awe": 1,
                    "reflection": 1
                }
            },
            "pacing_guide": {
                5: 70,
                10: 140,
                15: 210,
                20: 280
            }
        }
    },

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


def build_title_suggestions_prompt(template_id: str, topic: str, dossier: str,
                                    audience: str = "General") -> str:
    """
    Build prompt for generating 5 YouTube title suggestions.
    Each title represents a genuinely different narrative angle.
    """
    template = TEMPLATES.get(template_id)
    template_name = template['metadata']['name'] if template else template_id

    prompt = f"""You are a YouTube content strategist who specializes in crafting viral, click-worthy titles.

Based on the research below, generate exactly 5 YouTube video title options for this topic.
Each title must represent a GENUINELY DIFFERENT narrative angle — not just rephrasing the same idea.

TOPIC: {topic}
TEMPLATE STYLE: {template_name}
TARGET AUDIENCE: {audience}

═══════ RESEARCH SUMMARY ═══════
{dossier[:3000]}

═══════ REQUIREMENTS ═══════
For each title:
- Make it compelling, specific, and click-worthy for YouTube
- Each title must tell the story from a DIFFERENT angle (e.g., villain's perspective vs victim's perspective, chronological vs impact-first, personal story vs systemic analysis)
- Include a 1-2 sentence description explaining the hook type and what makes this angle unique
- Vary the approaches: use different hook styles (question, bold claim, mystery, number-based, emotional)
- Keep titles under 80 characters
- No clickbait — titles must be honest to the content
- Consider the target audience ({audience}) when crafting the angle and language

Return ONLY a JSON array:
[
  {{"title": "The YouTube Title", "description": "Opens with a shocking statistic about X, then explores the human cost angle"}},
  {{"title": "Another Title Option", "description": "Uses a direct question hook, focuses on the investigation angle"}},
  ...
]

Return exactly 5 items. Return ONLY the JSON array."""

    return prompt


def build_tone_suggestion_prompt(template_id: str, selected_title: str,
                                  audience: str = "General") -> str:
    """
    Build prompt for auto-suggesting the best tone for a given title + audience.
    """
    template = TEMPLATES.get(template_id)
    template_name = template['metadata']['name'] if template else template_id

    emotional_context = ""
    if template:
        emo_beats = template["script_config"]["story_structure"].get("emotional_beats", {})
        emotional_context = ", ".join(beat.replace('_', ' ') for beat in emo_beats.keys())

    prompt = f"""Based on the video title and audience below, suggest the single best tone for the narration.

TITLE: {selected_title}
AUDIENCE: {audience}
TEMPLATE STYLE: {template_name}
TEMPLATE EMOTIONAL BEATS: {emotional_context}

Available tones: Investigative, Conversational, Confrontational, Neutral, Educational, Entertaining

Pick the ONE tone that best matches the title's implied narrative angle and the target audience.
Explain briefly why this tone works.

Return ONLY a JSON object:
{{"suggested_tone": "Tone Name", "reasoning": "1-2 sentence explanation of why this tone fits"}}

Return ONLY the JSON."""

    return prompt


def build_script_prompt(template_id: str, topic: str, research_dossier: str,
                        duration_minutes: int = 10, audience: str = "General",
                        tone: str = "", focus: str = "", style_guide: str = None,
                        selected_title: str = None) -> str:
    """
    PHASE 1: Build prompt for the creative narration.
    
    Asks Gemini to write a flowing, compelling narration organized by acts/beats.
    No word-count limits, no timestamps — pure storytelling.
    The output feeds into production (build_production_prompt) for shot splitting and visual prompts.
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
    
    title_instruction = ""
    title_format = '"title": "Compelling video title"'
    if selected_title:
        title_instruction = f"VIDEO TITLE (USE EXACTLY): {selected_title}"
        title_format = f'"title": "{selected_title}"'

    prompt = f"""{system_prompt}

═══════ ASSIGNMENT ═══════
TOPIC: {topic}
LENGTH: {duration_minutes} minutes (~{total_words} words of narration)
AUDIENCE: {audience}
TONE: {tone or ('Match the Style Guide' if style_guide else 'As appropriate for the template')}
{f'FOCUS: {focus}' if focus else ''}
{title_instruction}

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
  {title_format},
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


def build_beat_regeneration_prompt(template_id: str, topic: str,
                                    research_dossier: str,
                                    full_narration: dict,
                                    target_beat_indices: list,
                                    target_act: str = None,
                                    mode: str = "restyle",
                                    audience: str = "General",
                                    tone: str = "",
                                    duration_minutes: int = 10) -> str:
    """
    Build prompt for regenerating specific beats or an entire act.

    Args:
        template_id: Template being used
        topic: Video topic
        research_dossier: Full research text (will be truncated for context)
        full_narration: The complete narration JSON {title, narration: [...]}
        target_beat_indices: List of beat indices to regenerate (0-based)
        target_act: If set, regenerate all beats in this act
        mode: 'restyle' (same facts, different style) or 'reimagine' (different facts/angle)
        audience: Target audience
        tone: Narration tone
        duration_minutes: Video length for pacing reference
    """
    template = TEMPLATES.get(template_id)
    template_name = template['metadata']['name'] if template else template_id
    beats = full_narration.get("narration", [])

    # Resolve target indices
    if target_act:
        target_beat_indices = [i for i, b in enumerate(beats) if b.get("act") == target_act]

    if not target_beat_indices:
        return "Error: No beats to regenerate."

    # Collect target beats and surrounding context (3 before, 3 after)
    min_idx = max(0, min(target_beat_indices) - 3)
    max_idx = min(len(beats), max(target_beat_indices) + 4)
    context_beats = beats[min_idx:max_idx]

    target_text = ""
    context_text = ""
    for i, beat in enumerate(context_beats):
        real_idx = min_idx + i
        marker = " <<<TARGET>>>" if real_idx in target_beat_indices else ""
        entry = f"[Beat {real_idx}] Act: {beat.get('act', '')} | Beat: {beat.get('beat', '')}{marker}\n{beat.get('text', beat.get('narration', ''))}\n"
        context_text += entry + "\n"
        if real_idx in target_beat_indices:
            target_text += entry + "\n"

    # Truncate dossier to keep prompt reasonable
    dossier_excerpt = research_dossier[:4000]

    if mode == "restyle":
        mode_instruction = """RESTYLE MODE — Rewrite these beats with:
- SAME factual content and information
- DIFFERENT phrasing, rhythm, vocabulary, and sentence structure
- A fresh stylistic approach — change the energy, vary sentence lengths, use different rhetorical devices
- Keep the same narrative flow and transitions to surrounding beats"""
    else:
        mode_instruction = """REIMAGINE MODE — Create new beats that:
- Cover a DIFFERENT angle or aspect from the research dossier
- Use DIFFERENT facts, examples, or data points than the current version
- Maintain the same act/beat role in the story structure
- Flow naturally from the preceding beat and into the following beat"""

    prompt = f"""You are a scriptwriter editing a narration for a YouTube video.

TOPIC: {topic}
TEMPLATE: {template_name}
AUDIENCE: {audience}
TONE: {tone or 'Match the surrounding beats'}
VIDEO LENGTH: {duration_minutes} minutes

{mode_instruction}

═══════ RESEARCH DOSSIER (for reference) ═══════
{dossier_excerpt}

═══════ SURROUNDING CONTEXT (for flow) ═══════
{context_text}

═══════ BEATS TO REGENERATE ═══════
{target_text}

═══════ REQUIREMENTS ═══════
- Return ONLY the regenerated beats (not the surrounding context)
- Each beat must flow naturally from the beat before it and into the beat after it
- Maintain approximately the same word count per beat (±20%)
- Every fact must come from the research dossier
- Write as spoken narration — compelling, vivid, conversational
- Return {len(target_beat_indices)} beat(s)

═══════ OUTPUT FORMAT ═══════
Return a JSON array:
[
  {{"act": "ACT NAME", "beat": "Beat Name", "text": "The regenerated narration text..."}},
  ...
]

Return ONLY the JSON array. Begin."""

    return prompt


# ═══════════════════════════════════════════════════════════════════
#  PHASE 3: PRODUCTION TABLE
# ═══════════════════════════════════════════════════════════════════

# Default cinematic prompt schema (used when no style analysis is provided)
DEFAULT_PROMPT_SCHEMA = {
    "always_include": ["shot_size", "subject", "arrangement", "background", "mood"],
    "include": ["lighting", "lighting_direction", "camera_lens", "camera_aperture",
                 "dof", "film_stock", "color_restriction", "output_style",
                 "room_objects", "made_out_of"],
    "exclude": [],
}

# Maps schema field keys to prompt bracket instructions
_FIELD_TO_PROMPT = {
    "shot_size":           ("[SHOT SIZE]", "Camera framing: wide, medium, close-up, extreme close-up"),
    "subject":             ("[SUBJECT: detailed physical description, age, features, wardrobe]", "Full character/object description"),
    "arrangement":         ("[POSE/ACTION], [EXPRESSION]", "Body position, gesture, facial expression, camera angle relative to subject"),
    "background":          ("[BACKGROUND/ENVIRONMENT: specific location, key visual details]", "Setting and backdrop"),
    "mood":                ("[MOOD: emotional atmosphere]", "The feeling this frame should evoke"),
    "lighting":            ("[LIGHTING: quality, setup, softness/hardness]", "Overall lighting approach"),
    "lighting_direction":  ("[LIGHTING DIRECTION: key light position, fill, color temperature]", "Technical lighting specs"),
    "camera_lens":         ("[CAMERA LENS: focal length in mm]", "e.g., 35mm, 85mm, 200mm"),
    "camera_aperture":     ("[APERTURE: f-stop]", "e.g., f/1.4, f/2.8, f/8"),
    "dof":                 ("[DEPTH OF FIELD]", "Shallow bokeh vs deep focus"),
    "film_stock":          ("[FILM STOCK/TEXTURE]", "Grain, analog feel, digital clean"),
    "color_restriction":   ("[COLOR PALETTE: primary and accent colors]", "Color rules and restrictions"),
    "output_style":        ("[STYLE/AESTHETIC: overall look]", "e.g., photorealistic 8k, watercolor, pixel art, cel animation"),
    "room_objects":        ("[PROPS/OBJECTS in scene]", "Important items visible in frame"),
    "made_out_of":         ("[MATERIAL/TEXTURE of subject]", "What the subject is made of or looks like"),
    "tags":                ("[AESTHETIC TAGS]", "Keyword descriptors for the overall feel"),
}


def _build_prompt_format_instructions(schema: dict, aspect_ratio: str) -> str:
    """
    Build the PROMPT FORMATS section dynamically based on the approved schema.
    Only includes fields that are in always_include + include, and explicitly
    tells the AI NOT to use excluded fields.
    """
    always = schema.get("always_include", [])
    include = schema.get("include", [])
    exclude = schema.get("exclude", [])
    active_fields = always + include

    # Build first frame template lines
    first_frame_lines = []
    for field in active_fields:
        if field in _FIELD_TO_PROMPT:
            bracket, _ = _FIELD_TO_PROMPT[field]
            first_frame_lines.append(bracket)

    first_frame_template = "\n".join(first_frame_lines)
    first_frame_template += f"\n[ASPECT RATIO: {aspect_ratio}]"
    first_frame_template += "\n--\nExclude: [specific exclusions for this scene]"

    # Build last frame template (mirrors first frame with END state)
    last_frame_lines = []
    for field in active_fields:
        if field in _FIELD_TO_PROMPT:
            bracket, _ = _FIELD_TO_PROMPT[field]
            if field == "arrangement":
                last_frame_lines.append("[END POSE/ACTION], [END EXPRESSION]")
            elif field in ("subject", "background", "lighting", "lighting_direction",
                           "color_restriction", "output_style", "film_stock", "mood"):
                last_frame_lines.append(f"[SAME {bracket.strip('[]').split(':')[0]}]")
            else:
                last_frame_lines.append(bracket)

    last_frame_template = "\n".join(last_frame_lines)
    last_frame_template += f"\n[ASPECT RATIO: {aspect_ratio}]"
    last_frame_template += "\n--\nExclude: [specific exclusions]"

    # Build Veo template
    veo_lines = ["[Shot size] of [subject] [TRANSITIONAL ACTION — what happens between first and last frame] in [background]."]
    if "lighting" in active_fields or "lighting_direction" in active_fields:
        veo_lines.append("Lighting: [conditions, any changes].")
    veo_lines.append("Camera: [movement type, speed, motivation].")
    veo_lines.append("Audio: [ambient], [SFX], [dialogue if any].")
    if "output_style" in active_fields:
        veo_lines.append("Style: [aesthetic reference].")
    veo_lines.append("--")
    veo_lines.append("negative prompt: no text overlays, no watermarks, no logos, [scene-specific exclusions]")
    veo_template = "\n".join(veo_lines)

    # Build exclusion warning
    exclusion_warning = ""
    if exclude:
        excluded_names = []
        for field in exclude:
            if field in _FIELD_TO_PROMPT:
                _, desc = _FIELD_TO_PROMPT[field]
                excluded_names.append(f"{field} ({desc})")
            else:
                excluded_names.append(field)
        exclusion_warning = f"""
⚠️ EXCLUDED FIELDS — Do NOT include these in your prompts:
{chr(10).join('- ' + name for name in excluded_names)}
These fields are NOT relevant for the current visual style. Including them will produce bad results."""

    # Build field reference guide
    field_guide_lines = []
    for field in active_fields:
        if field in _FIELD_TO_PROMPT:
            bracket, desc = _FIELD_TO_PROMPT[field]
            field_guide_lines.append(f"  - {field}: {desc}")

    return f"""═══════ PROMPT FORMATS ═══════

ACTIVE PROMPT FIELDS for this style:
{chr(10).join(field_guide_lines)}
{exclusion_warning}

FIRST FRAME PROMPT format (for image generation):
```
{first_frame_template}
```

LAST FRAME PROMPT format (must preserve identity — same subject, wardrobe, environment):
```
{last_frame_template}
```

VEO 3.1 VIDEO PROMPT format:
```
{veo_template}
```"""


def build_production_prompt(narration_json: dict, duration_minutes: int = 10,
                            style_analysis: dict = None,
                            aspect_ratio: str = "16:9") -> str:
    """
    Build prompt for the unified Production Table with dynamic style support.

    Takes raw narration beats and instructs Gemini to:
      1. Creatively split narration into shots (using narrative/emotional logic)
      2. Generate visual direction per shot
      3. Generate first-frame, last-frame, and Veo 3.1 prompts using the approved schema

    Args:
        narration_json: Narration object {title, narration: [{act, beat, text}, ...]}
        duration_minutes: Target video length
        style_analysis: Structured style dict {style_summary, style_intent, prompt_schema}
        aspect_ratio: Video aspect ratio (Veo hardware constraint)
    """
    # Extract narration beats
    beats = narration_json.get("narration", [])
    title = narration_json.get("title", "Untitled")
    hook_type = narration_json.get("hook_type", "")

    # Format narration beats for the prompt
    narration_text = ""
    for i, beat in enumerate(beats):
        act = beat.get("act", "")
        beat_name = beat.get("beat", "")
        text = beat.get("text", beat.get("narration", ""))
        narration_text += f"\n[BEAT {i+1}] Act: {act} | Beat: {beat_name}\n{text}\n"

    # Speech pacing constants
    WORDS_PER_SECOND = 2.5
    total_words = sum(len(b.get("text", b.get("narration", "")).split()) for b in beats)
    estimated_shots = max(1, int(total_words / (WORDS_PER_SECOND * 3.5)))

    # Build visual style section from structured style analysis
    if style_analysis and isinstance(style_analysis, dict):
        intent = style_analysis.get("style_intent", {})
        schema = style_analysis.get("prompt_schema", DEFAULT_PROMPT_SCHEMA)
        style_summary = style_analysis.get("style_summary", "Custom style")

        visual_style_section = f"""═══════ VISUAL STYLE & CREATIVE DIRECTION ═══════
Style: {style_summary}
Detail Level: {intent.get('detail_level', 'Standard')}
Scene Complexity: {intent.get('scene_complexity', 'Standard')}
Camera Language: {intent.get('camera_language', 'Standard cinematography')}
Lighting Approach: {intent.get('lighting_instruction', 'As appropriate')}
Subject Framing: {intent.get('subject_framing', 'Varied')}
Writing Style: {intent.get('writing_style', 'Descriptive')}
Color Palette: {intent.get('color_palette', 'As appropriate')}
Texture: {intent.get('texture', 'As appropriate')}
Default Mood: {intent.get('mood_default', 'As appropriate')}

⚠️ CRITICAL STYLE RULES:
- MATCH the style description above in EVERY prompt you write.
- If Detail Level is 'Minimalist', keep prompts short and simple. Do NOT add cinematic details.
- If Scene Complexity is 'Empty Backgrounds', do NOT describe detailed environments.
- If Writing Style is 'Concise', use short direct sentences. No flowery language.
- Do NOT hallucinate details that contradict the style (e.g., don't add '4k photorealistic' to a cartoon style).
- Follow the Camera Language instructions — if it says 'simple flat framing', do NOT use lens mm or DOF.

⚠️ STORY SCENE RULES (CRITICAL):
- The style describes HOW CHARACTERS ARE RENDERED, not the scene setting.
- Characters must be placed in STORY-APPROPRIATE ENVIRONMENTS (forests, houses, streets, etc.) — not studio backdrops.
- Environments should be rendered in the SAME visual style as the characters.
- Each prompt must depict WHAT IS HAPPENING in the narration at that moment.
- Characters must be DOING things (actions from the story), NOT posing statically for display.
- NEVER describe the scene as "product photography", "studio showcase", or "display figure"."""
    else:
        schema = DEFAULT_PROMPT_SCHEMA
        style_summary = "Cinematic (default)"
        visual_style_section = """═══════ VISUAL STYLE & CREATIVE DIRECTION ═══════
Style: Cinematic Drama (default — no custom style provided)
Detail Level: High Detail
Scene Complexity: Complex Environments
Camera Language: Use cinematic wide angles, depth of field, and motivated camera movement
Lighting Approach: Dramatic, motivated lighting with attention to direction and quality
Subject Framing: Varied — match the emotional beat
Writing Style: Descriptive and technical
Color Palette: Neutral with motivated accents
Texture: Cinematic film grain
Default Mood: As appropriate for the narrative"""

    # Build dynamic prompt format instructions from schema
    prompt_formats = _build_prompt_format_instructions(schema, aspect_ratio)

    prompt = f"""You are a professional production team creating a VIDEO that tells a STORY:
1. THE DIRECTOR — story, emotion, performance, pacing, editorial decisions
2. THE STORYBOARD ARTIST — visual sequence, composition, shot flow
3. THE DIRECTOR OF PHOTOGRAPHY — camera, lighting, visual style (adapted to the style guide)

Your job has TWO parts:
A) CREATIVELY SPLIT the narration into production shots
B) CREATE production prompts (first-frame, last-frame, Veo 3.1) for each shot — these must depict STORY SCENES, not static character showcases

═══════ PROJECT INFO ═══════
Title: {title}
Hook Type: {hook_type}
Duration: {duration_minutes} minutes
Total Narration Words: ~{total_words}
Estimated Shots: ~{estimated_shots}
Aspect Ratio: {aspect_ratio}

{visual_style_section}

═══════ NARRATION TO SPLIT ═══════
⚠️ USE THESE EXACT WORDS — DO NOT REWRITE, PARAPHRASE, OR DROP ANY TEXT ⚠️
{narration_text}

═══════ CREATIVE SCENE CUTTING ═══════

You are making CREATIVE EDITORIAL DECISIONS about where to cut. This is NOT a mechanical word-count exercise.

CONSIDER THESE FACTORS WHEN DECIDING WHERE TO CUT:
1. NARRATIVE BEATS: Cut when the idea shifts, a new claim begins, or a new subject is introduced
2. EMOTIONAL SHIFTS: Cut when the emotion changes (curiosity → surprise, tension → release)
3. VISUAL LOGIC: Cut when the visual should change (new location, new subject, new angle)
4. DRAMATIC TIMING: Use shorter shots (4s) for high-impact moments, longer shots (6-8s) for contemplation
5. BREATHING ROOM: Not every cut must align with a word boundary — consider dramatic pauses

For each shot, explain your cutting decision in the "cutting_rationale" field.

GUIDELINES (flexible, not rigid):
- Target 5-15 words per shot, but allow 3-4 words for dramatic emphasis shots
- Average speech rate is ~{WORDS_PER_SECOND} words/sec — use this to ESTIMATE duration
- Duration MUST be exactly 4s, 6s, or 8s (Veo hardware constraint)
- EVERY word from the narration must appear in exactly one shot's script_beat
- Each shot = ONE visual moment = ONE camera setup
- Split sentences at natural pause points (commas, periods, em-dashes, semicolons)

EXAMPLE of creative cutting:
  Original: "Imagine a world where your word is law, your wealth immense, and your enemies silenced."

  CREATIVE split:
  Shot 1 | 4s | "Imagine a world where your word is law," | rationale: "Opening invitation — wide establishing shot"
  Shot 2 | 4s | "your wealth immense," | rationale: "Brief flash of opulence — CUT for impact"
  Shot 3 | 4s | "and your enemies silenced." | rationale: "Dark turn — new visual beat, shift in tone"

═══════ STORY-GROUNDED VISUALS (CRITICAL) ═══════

⚠️ THIS IS A VIDEO THAT TELLS A STORY. Every shot must depict what is HAPPENING in the narration. ⚠️

RULES FOR VISUAL DIRECTION:
1. READ THE NARRATION TEXT for each shot. What is it describing? That is what the visual MUST show.
   - Narration: "she walked into the dark forest" → Visual: character walking into a dense, dark forest
   - Narration: "the old woman handed her a red cap" → Visual: an elderly woman extending a small red cap toward a young girl
   - Narration: "the wolf watched from behind the trees" → Visual: menacing eyes glowing between dark tree trunks

2. BACKGROUNDS MUST COME FROM THE STORY, not from the reference images.
   - If the story takes place in a forest → the background is a forest (rendered in the visual style)
   - If the story takes place in a cottage → the background is a cottage interior
   - NEVER default to "studio backdrop", "seamless gray background", or "clean background" unless the story explicitly takes place there

3. CHARACTERS MUST BE DOING THINGS, not posing.
   - They walk, run, talk, reach, hold objects, react, look around
   - Each shot should capture a MOMENT IN TIME from the narrative
   - Show the character's RELATIONSHIP to their environment

4. VARY YOUR SHOTS — tell the story visually:
   - Establishing shots: show the WORLD (wide shots of locations)
   - Character shots: show REACTIONS and EMOTIONS (medium/close-up)
   - Detail shots: show IMPORTANT OBJECTS or ACTIONS (close-up/macro)
   - Transition shots: show MOVEMENT between locations or moments

5. VISUAL CONSISTENCY across shots:
   - Same character should look the SAME in every shot (clothing, features, proportions)
   - Environments should be consistent within the same story location
   - The visual STYLE stays the same throughout (per the style guide)

═══════ VEO 3.1 TECHNICAL CONSTRAINTS ═══════

DURATION: Only 4s, 6s, or 8s per clip. Maximum 8 seconds.
- Simple motion (expression change, subtle shift) → 4s
- Moderate motion (gesture, slow pan) → 6s
- Complex motion (walk, full camera move) → 8s

RESOLUTION & ASPECT:
- 16:9: 1920x1080 | 9:16: 1080x1920
- First & Last frame MUST match exactly

ACHIEVABLE MOTION (within timeframe):
- Subtle weight shifts (4s), head turns (4s), hand gestures (4-6s)
- Standing to sitting (6-8s), walking few steps (4-8s)
- Subtle camera push/pull (4-8s), pan up to 90 degrees (6-8s)
- Challenging: 90 degree orbit, multi-part actions (8s, simplify)
- Impossible: location changes, day-to-night, wardrobe changes, 180+ degree camera moves

FRAME COMPATIBILITY (MUST MATCH between first & last frame):
- Subject: identical features, build, face
- Wardrobe: exact same clothing
- Environment: same location, same visible elements
- Style: same aesthetic
- Aspect ratio: identical

{prompt_formats}

═══════ OUTPUT FORMAT ═══════

Return a JSON object with this EXACT structure:
{{{{
  "title": "{title}",
  "aspect_ratio": "{aspect_ratio}",
  "style_summary": "Brief summary of the visual style applied",
  "total_shots": <number>,
  "shots": [
    {{{{
      "shot_number": "1",
      "timestamp": "00:00-00:04",
      "script_beat": "The exact narration text for this shot (5-15 words)",
      "act": "ACT 1",
      "beat": "Hook",
      "duration": "4s",
      "visual": "Brief visual description for this moment",
      "emotion": "Curiosity",
      "directors_intent": "What the audience should feel",
      "cutting_rationale": "Why the cut happens here (narrative shift, emotion change, visual logic, etc.)",
      "first_frame_prompt": "Full structured first frame prompt using the approved schema fields",
      "last_frame_prompt": "Full structured last frame prompt using the approved schema fields",
      "veo_prompt": "Full Veo 3.1 video prompt"
    }}}}
  ],
  "continuity_notes": [
    {{{{
      "from_shot": "1",
      "to_shot": "2",
      "visual_bridge": "How these connect visually",
      "audio_bridge": "Sound continuity",
      "potential_issue": "If any"
    }}}}
  ],
  "production_notes": {{{{
    "challenging_shots": ["Any shots needing extra iterations"],
    "recommended_workflow": "Suggested order of generation",
    "post_production": "Color grading, audio sweetening, transitions"
  }}}}
}}}}

═══════════════════════════════════════════════════════
CRITICAL RULES (MUST FOLLOW EXACTLY):
═══════════════════════════════════════════════════════
1. Use the EXACT narration words in script_beat. Do not paraphrase or rewrite.
2. Every word from the narration must appear in exactly one shot's script_beat.
3. Each script_beat: 5-15 words (3-4 allowed for dramatic emphasis).
4. Timestamps must be sequential. Use word count as a guide, not a rigid formula.
5. Every shot duration MUST be exactly 4s, 6s, or 8s for Veo compatibility.
6. First and last frame prompts MUST describe the SAME subject, wardrobe, and environment.
7. The only difference between frames should be pose, expression, and camera position.
8. Maintain visual continuity across ALL shots.
9. Be SPECIFIC in prompts — no vague descriptions.
10. Apply the visual style CONSISTENTLY: {style_summary}. Use ONLY the prompt fields specified in the schema above.
11. Include a cutting_rationale for every shot explaining the editorial decision.
12. EVERY SHOT MUST DEPICT A STORY MOMENT — characters doing things in story environments. NEVER use "studio backdrop" or "seamless background."
13. Backgrounds MUST match what the narration describes (forest, cottage, path, etc.), rendered in the visual style.
14. Characters must be ACTING (walking, talking, reacting, holding objects) — NOT posing for display.

⚠️⚠️⚠️ JSON SYNTAX VALIDATION ⚠️⚠️⚠️
CRITICAL: You MUST generate VALID JSON with correct syntax:
1. Every field MUST end with a comma EXCEPT the last field in an object
2. All string values MUST be properly escaped (use \\" for quotes, \\\\ for backslashes)
3. Do NOT put commas after the last field in an object
4. ALWAYS put a comma after every object in the "shots" array EXCEPT the last one
5. Check your JSON is valid before returning it

Return ONLY the JSON. Begin."""

    return prompt
