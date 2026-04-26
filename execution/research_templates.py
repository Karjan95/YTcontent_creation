"""
Research & Script Writing Templates
====================================
Each template defines:
- research_config: How NotebookLM should research the topic
- script_config: How Gemini should write the script
- metadata: Display info for the UI
"""

import json

# ═══════════════════════════════════════════════════════════════════
#  AUDIENCE PROFILES — Behavioral instructions per audience type
# ═══════════════════════════════════════════════════════════════════
AUDIENCE_PROFILES = {
    "general": {
        "label": "🌍 General Public",
        "vocabulary": "Simple, everyday language. Avoid jargon. If a technical term is unavoidable, immediately explain it with an analogy.",
        "assumed_knowledge": "Assume zero prior knowledge. Explain everything from scratch.",
        "analogies": "Use pop culture references, everyday objects, and common experiences (cooking, driving, sports).",
        "formality": "Casual and conversational. Talk like a smart friend explaining over coffee.",
    },
    "young_adults": {
        "label": "🧑‍💻 Young Adults (18-30)",
        "vocabulary": "Modern, internet-native language. Use slang sparingly but naturally. Meme-aware but not cringy.",
        "assumed_knowledge": "Assume basic digital literacy and awareness of current trends. Don't over-explain social media or tech basics.",
        "analogies": "Reference streaming shows, gaming, social media, startup culture, and internet phenomena.",
        "formality": "Very casual. Direct address ('you', 'your'). Short sentences. Energy-first.",
    },
    "teens": {
        "label": "🎮 Teens (13-17)",
        "vocabulary": "Simple, high-energy language. Use relatable school/social media references. Avoid condescension.",
        "assumed_knowledge": "Assume familiarity with TikTok, YouTube, gaming, and school life. Don't assume deeper historical or political context.",
        "analogies": "Reference video games, social media trends, school situations, and popular YouTubers/streamers.",
        "formality": "Super casual. Fast-paced. Every sentence must feel exciting or surprising.",
    },
    "professionals": {
        "label": "💼 Business / Professionals",
        "vocabulary": "Industry-standard terminology. Use business vocabulary naturally (ROI, stakeholders, margins, runway).",
        "assumed_knowledge": "Assume familiarity with business concepts, market dynamics, and corporate structure.",
        "analogies": "Use market comparisons, case studies, and business strategy metaphors.",
        "formality": "Professional but not stiff. Think Bloomberg or Harvard Business Review tone.",
    },
    "tech_savvy": {
        "label": "⚙️ Tech-Savvy / Developers",
        "vocabulary": "Technical jargon welcome. Use precise engineering terms without excessive explanation.",
        "assumed_knowledge": "Assume deep familiarity with software, hardware, APIs, algorithms, and system architecture.",
        "analogies": "Reference code patterns, system design, open source projects, and engineering trade-offs.",
        "formality": "Direct and precise. No fluff. Dense information. Think Hacker News or ArsTechnica.",
    },
    "academic": {
        "label": "🎓 Academic / Researchers",
        "vocabulary": "Scholarly vocabulary. Use discipline-specific terminology. Cite methodologies and frameworks by name.",
        "assumed_knowledge": "Assume graduate-level understanding. Reference theories, studies, and academic debates directly.",
        "analogies": "Reference published research, peer-reviewed studies, and established theoretical models.",
        "formality": "Formal and evidence-based. Every claim should reference its source. Nuanced and cautious with conclusions.",
    },
    "curious_beginners": {
        "label": "🌱 Curious Beginners",
        "vocabulary": "Extremely simple language. Define every concept. Use the '5-year-old test' — if a 5-year-old wouldn't understand a word, replace it.",
        "assumed_knowledge": "Assume absolutely nothing. Build understanding from the ground up, brick by brick.",
        "analogies": "Use the simplest possible everyday analogies (water flowing, building blocks, cooking recipes).",
        "formality": "Warm and encouraging. Patient. Celebrate complexity: 'This is where it gets really cool...'",
    },
    "skeptics": {
        "label": "🤨 Skeptics / Critical Thinkers",
        "vocabulary": "Precise and evidence-heavy. Avoid emotional language. Use hedge words appropriately ('the evidence suggests', 'according to').",
        "assumed_knowledge": "Assume high intelligence but active distrust. They will fact-check you.",
        "analogies": "Reference primary sources, methodology, sample sizes, and peer review. Acknowledge uncertainty.",
        "formality": "Measured and transparent. Show your reasoning. Acknowledge counter-evidence proactively.",
    },
    "entertainment_seekers": {
        "label": "🎪 Entertainment Seekers",
        "vocabulary": "Vivid, dramatic, and colorful language. Use powerful verbs and sensory details.",
        "assumed_knowledge": "Assume moderate general knowledge but low patience for dry facts. They want a SHOW.",
        "analogies": "Reference movies, TV shows, celebrity culture, viral moments, and dramatic historical events.",
        "formality": "Highly informal. Dramatic. Use cliffhangers, rhetorical questions, and emotional peaks constantly.",
    },
    "parents_families": {
        "label": "👨‍👩‍👧‍👦 Parents / Families",
        "vocabulary": "Clear, responsible language. Avoid graphic content unless the topic demands it. Practical and actionable.",
        "assumed_knowledge": "Assume general education but high concern for safety, health, and practical implications.",
        "analogies": "Reference family life, child development, household decisions, and community impact.",
        "formality": "Warm and trustworthy. Empathetic. Focus on practical takeaways and actionable advice.",
    },
    "policy_makers": {
        "label": "🏛️ Policy Makers / Civic Leaders",
        "vocabulary": "Policy-specific terminology. Reference legislation, regulations, constitutional frameworks, and precedents.",
        "assumed_knowledge": "Assume deep familiarity with government processes, legislative procedures, and policy analysis.",
        "analogies": "Reference historical legislation, international policy comparisons, and cost-benefit frameworks.",
        "formality": "Formal, neutral, and evidence-driven. Present multiple perspectives fairly. Focus on actionable implications.",
    },
}


# ═══════════════════════════════════════════════════════════════════
#  TONE DEFINITIONS — Behavioral anchoring for each tone
# ═══════════════════════════════════════════════════════════════════
TONE_DEFINITIONS = {
    # ── Core Tones ──
    "investigative": {
        "label": "🔍 Investigative",
        "sentence_style": "Short, punchy, declarative. Build suspense through fragments and strategic pauses.",
        "rhetorical_devices": "Rhetorical questions, dramatic reveals, foreshadowing, and 'follow the money' framing.",
        "emotional_stance": "Skeptical but fair. Let the evidence speak. Build toward an undeniable conclusion.",
        "forbidden": "Do NOT editorialize or preach. Present evidence and let the viewer connect the dots.",
    },
    "conversational": {
        "label": "💬 Conversational",
        "sentence_style": "Natural, flowing sentences. Mix short and long. Use contractions freely. Sounds like a smart friend talking.",
        "rhetorical_devices": "Direct address ('you', 'we'), thought experiments, 'imagine this' scenarios, casual asides.",
        "emotional_stance": "Warm, relatable, genuinely curious. Share your thought process out loud.",
        "forbidden": "Do NOT sound like a textbook or a news anchor. Never be stiff or overly formal.",
    },
    "educational": {
        "label": "🎓 Educational",
        "sentence_style": "Clear, structured sentences. Build complexity gradually. Use signposting ('First...', 'The key thing is...', 'Here's why that matters...').",
        "rhetorical_devices": "Analogies, step-by-step breakdowns, 'before/after' framing, Socratic questions.",
        "emotional_stance": "Patient, encouraging, and intellectually excited. Make the viewer feel smart, not stupid.",
        "forbidden": "Do NOT condescend. Never say 'simply' or 'obviously'. Avoid information dumps.",
    },
    "neutral": {
        "label": "⚖️ Neutral / Objective",
        "sentence_style": "Balanced, measured sentences. Present facts without adjectives that imply judgment.",
        "rhetorical_devices": "On one hand / on the other hand. Direct quoting. Attribution to sources.",
        "emotional_stance": "Completely impartial. Present all sides equally. Your personal opinion is invisible.",
        "forbidden": "Do NOT use loaded language, emotional appeals, or imply which side is 'correct'.",
    },
    "entertaining": {
        "label": "🎪 Entertaining",
        "sentence_style": "High-energy, varied rhythm. Mix punchy one-liners with flowing descriptions. Keep it fast.",
        "rhetorical_devices": "Callbacks, running jokes, pop culture references, dramatic irony, cliffhangers.",
        "emotional_stance": "Fun-first. Every sentence should make the viewer want to hear the next one.",
        "forbidden": "Do NOT sacrifice accuracy for laughs. Never be boring or predictable.",
    },
    "confrontational": {
        "label": "⚔️ Confrontational",
        "sentence_style": "Direct, aggressive, unapologetic. Short sentences. Declarative. Use 'you' and 'they' frequently.",
        "rhetorical_devices": "Calling out hypocrisy, challenge framing, 'let me be clear' energy, receipts and evidence.",
        "emotional_stance": "Righteous anger controlled by facts. Channel frustration into precise arguments.",
        "forbidden": "Do NOT make ad hominem attacks. Anger must be backed by evidence, not emotion alone.",
    },

    # ── Emotional / Cinematic Tones ──
    "dark_and_ominous": {
        "label": "🌑 Dark & Ominous",
        "sentence_style": "Slow, heavy sentences. Long pauses between ideas. Build dread gradually. Use sentence fragments for impact.",
        "rhetorical_devices": "Foreshadowing, ominous imagery, 'what they didn't know was...' reveals, countdown framing.",
        "emotional_stance": "Foreboding. Something terrible is coming and the viewer can feel it before you say it.",
        "forbidden": "Do NOT rush. The power is in the slow build. Never break the atmosphere with humor.",
    },
    "empathetic_and_personal": {
        "label": "💛 Empathetic & Personal",
        "sentence_style": "Soft, reflective sentences. Use 'we' and 'us' frequently. Allow silences. Poetic when appropriate.",
        "rhetorical_devices": "Personal anecdotes, sensory details, 'put yourself in their shoes' framing, quiet revelations.",
        "emotional_stance": "Deeply human. Vulnerability is strength. Make the viewer FEEL before they think.",
        "forbidden": "Do NOT be preachy or manipulative. Empathy must feel earned and authentic.",
    },
    "inspirational": {
        "label": "✨ Inspirational",
        "sentence_style": "Building, crescendo-style sentences. Start small and escalate. Use parallel structure for emphasis.",
        "rhetorical_devices": "Hero's journey framing, overcoming-the-odds narratives, call to action, future-casting.",
        "emotional_stance": "Uplifting and empowering. The viewer should feel motivated and capable by the end.",
        "forbidden": "Do NOT be naive or dismissive of real obstacles. Inspiration must be grounded in reality.",
    },
    "reflective_philosophical": {
        "label": "🧘 Reflective / Philosophical",
        "sentence_style": "Thoughtful, meandering sentences. Allow ideas to unfold. Use questions more than statements.",
        "rhetorical_devices": "Thought experiments, paradoxes, open-ended questions, 'what does it mean to...' framing.",
        "emotional_stance": "Contemplative and unhurried. Invite the viewer to think rather than telling them what to think.",
        "forbidden": "Do NOT provide easy answers. The beauty is in the question itself.",
    },
    "urgent_breaking": {
        "label": "🚨 Urgent / Breaking News",
        "sentence_style": "Rapid-fire, staccato sentences. Lead with the most critical fact. Every word must justify its existence.",
        "rhetorical_devices": "Countdown framing, 'as of right now' updates, severity escalation, 'here's what we know' structure.",
        "emotional_stance": "Alert and focused. Controlled urgency — never hysteria. Respect the viewer's time.",
        "forbidden": "Do NOT speculate without labeling it. Never pad with filler. Cut to the point immediately.",
    },

    # ── Combo / Personality Tones ──
    "sarcastic_evil": {
        "label": "😈 Sarcastic / Villain Energy",
        "sentence_style": "Dripping with irony. Use understatement for maximum impact. Mock absurdity with a straight face.",
        "rhetorical_devices": "Dramatic irony, mock praise, 'oh, it gets worse' escalation, theatrical villain monologue energy.",
        "emotional_stance": "Darkly amused by human stupidity. You've seen the worst and you're not surprised anymore.",
        "forbidden": "Do NOT punch down at vulnerable people. Sarcasm targets the powerful, the corrupt, and the absurd.",
    },
    "explicit_humorous": {
        "label": "🤬 Explicit / Dark Comedy",
        "sentence_style": "Raw, unfiltered, brutally honest. Profanity is a spice — use it for impact, not filler. Say the thing everyone is thinking.",
        "rhetorical_devices": "Absurdist comparisons, shock humor, 'let's be real for a second' pivots, comedic rage.",
        "emotional_stance": "Cathartic anger meets gallows humor. The world is on fire and we're roasting marshmallows.",
        "forbidden": "Do NOT use slurs or target marginalized groups. Profanity attacks systems and stupidity, not people.",
    },
    "dry_wit": {
        "label": "🍸 Dry Wit / Deadpan",
        "sentence_style": "Understated, matter-of-fact. The humor is in what you DON'T say. Let absurdity speak for itself.",
        "rhetorical_devices": "Litotes (understatement), anticlimactic reveals, ironic juxtaposition, perfectly timed pauses.",
        "emotional_stance": "Coolly detached. Observing the chaos with a raised eyebrow and a glass of wine.",
        "forbidden": "Do NOT try too hard. The moment you explain the joke, you've killed it.",
    },
    "hype_energy": {
        "label": "🔥 Hype / High-Energy",
        "sentence_style": "FAST. LOUD. EXCLAMATORY. Short bursts. Staccato rhythm. Every sentence is a headline.",
        "rhetorical_devices": "Superlatives, 'you won't believe' energy, countdown reveals, challenge framing.",
        "emotional_stance": "Pure adrenaline. The viewer should feel like they're on a roller coaster.",
        "forbidden": "Do NOT sustain this for too long without a breather. Peaks need valleys to feel high.",
    },
    "noir_storyteller": {
        "label": "🕵️ Noir Storyteller",
        "sentence_style": "First-person inner monologue style. Past tense. World-weary. Rain-soaked metaphors. Jazz undertones.",
        "rhetorical_devices": "Hardboiled metaphors, moral ambiguity, 'it was the kind of deal that...' framing, inner conflict.",
        "emotional_stance": "Cynical but secretly romantic. Searching for truth in a world that doesn't reward it.",
        "forbidden": "Do NOT break character. The noir frame must hold from first word to last.",
    },
    "wholesome_warm": {
        "label": "☀️ Wholesome / Warm",
        "sentence_style": "Gentle, flowing sentences. Paint word-pictures. Use soft, warm vocabulary. Comforting rhythm.",
        "rhetorical_devices": "Personal stories, gratitude framing, finding beauty in details, hopeful 'what if' scenarios.",
        "emotional_stance": "Genuinely kind. See the best in people. Celebrate small victories.",
        "forbidden": "Do NOT be saccharine or fake. Warmth must feel real, not performative.",
    },
    "chaotic_unhinged": {
        "label": "🤪 Chaotic / Unhinged",
        "sentence_style": "Stream of consciousness. Tangents that somehow land. Energy shifts without warning. Controlled chaos.",
        "rhetorical_devices": "Non-sequiturs that secretly make sense, meta-commentary, breaking the fourth wall, absurdist logic.",
        "emotional_stance": "Unpredictable genius. The viewer doesn't know where you're going but they can't look away.",
        "forbidden": "Do NOT lose the thread entirely. The chaos must serve the story. Random ≠ funny.",
    },
}


# ═══════════════════════════════════════════════════════════════════
#  FORMAT PRESETS — Duration + pacing intent bundles
# ═══════════════════════════════════════════════════════════════════
FORMAT_PRESETS = {
    "micro": {
        "label": "🎯 Micro (30-60 sec)",
        "duration_minutes": 1,
        "pacing_instruction": (
            "This is a 30-60 second piece. Every single word must hit. "
            "No setup, no preamble. Open with the most compelling statement. "
            "One core idea only. End with an unforgettable punchline or revelation. "
            "Think TikTok, Reels, Shorts — maximum density, zero filler."
        ),
        "auto_pacing_tier": "High Energy",
        "shot_range": (4, 8),
    },
    "quick_take": {
        "label": "⚡ Quick Take (1-3 min)",
        "duration_minutes": 2,
        "pacing_instruction": (
            "This is a 1-3 minute punchy explainer. Get to the point in the first sentence. "
            "Two ideas maximum. No deep backstory. Use one killer example, one surprising fact. "
            "Keep momentum relentless — if a sentence doesn't move the story forward, cut it."
        ),
        "auto_pacing_tier": "High Energy",
        "shot_range": (8, 20),
    },
    "short_form": {
        "label": "📱 Short Form (5-7 min)",
        "duration_minutes": 5,
        "pacing_instruction": "Every sentence must earn its place. Fast cuts. No long explanations. Get in, make your point, get out. Ruthlessly cut anything that doesn't serve the hook or the payoff.",
        "auto_pacing_tier": "Standard",
        "shot_range": (20, 40),
    },
    "standard": {
        "label": "📺 Standard (10-12 min)",
        "duration_minutes": 10,
        "pacing_instruction": "Standard YouTube pacing. Build tension, allow beats to breathe. Include character moments and supporting evidence. Balance depth with momentum.",
        "auto_pacing_tier": "Standard",
        "shot_range": None,
    },
    "deep_dive": {
        "label": "📖 Deep Dive (18-22 min)",
        "duration_minutes": 20,
        "pacing_instruction": "Documentary pacing. Long scenes, rich detail, full character arcs. Take your time building atmosphere. Include extended quotes, multiple perspectives, and layered arguments.",
        "auto_pacing_tier": "Relaxed",
        "shot_range": None,
    },
    "custom": {
        "label": "🔢 Custom",
        "duration_minutes": None,  # user provides
        "pacing_instruction": "Adapt pacing naturally to the specified duration.",
        "auto_pacing_tier": None,
        "shot_range": None,
    },
}


# ═══════════════════════════════════════════════════════════════════
#  VIEWER OUTCOMES — Engineers the ending of the script
# ═══════════════════════════════════════════════════════════════════
VIEWER_OUTCOMES = {
    "spark_debate": {
        "label": "💬 Spark a Debate",
        "instruction": "End on an open, provocative question. Do NOT resolve the tension. Leave the viewer arguing in the comments. The final line should be a question that has no easy answer.",
    },
    "teach_something": {
        "label": "🧠 Teach Something",
        "instruction": "End with a clear, memorable takeaway. The viewer must be able to explain the core concept to a friend immediately after watching. Summarize the 'one thing' they should remember.",
    },
    "inspire_action": {
        "label": "😤 Inspire Outrage / Action",
        "instruction": "End with a call to action. The viewer must feel morally compelled to share the video, sign a petition, change a behavior, or do something. Make inaction feel unacceptable.",
    },
    "emotional_resonance": {
        "label": "🎭 Create Emotional Resonance",
        "instruction": "End on a human moment. Forget the facts. The final 30 seconds is pure emotional payoff — a personal story, a quiet revelation, or a moment of beauty. Leave the viewer feeling something deep.",
    },
    "leave_in_awe": {
        "label": "🤯 Leave in Awe",
        "instruction": "End with the most mind-blowing fact or revelation saved for last. The viewer's jaw should drop. Build the entire script so this final moment lands with maximum impact.",
    },
    "challenge_beliefs": {
        "label": "🪞 Challenge Their Beliefs",
        "instruction": "End by turning the camera on the viewer. Force them to question their own assumptions, biases, or role in the problem. The final line should make them uncomfortable in a productive way.",
    },
    "entertain_pure": {
        "label": "😂 Pure Entertainment",
        "instruction": "End with a callback to the hook or a perfectly timed punchline. Leave them laughing, satisfied, and immediately wanting to watch another video. The ending should feel like a mic drop.",
    },
}


def _resolve_structure_for_duration(template: dict, format_preset: str, duration_minutes: int) -> dict:
    """Return the appropriate story structure for the given format/duration."""
    sc = template["script_config"]
    short_structures = sc.get("short_structures", {})

    # Direct preset match
    if format_preset in short_structures:
        return short_structures[format_preset]

    # Duration-based fallback for custom preset
    if format_preset == "custom" or not format_preset:
        if duration_minutes <= 1 and "micro" in short_structures:
            return short_structures["micro"]
        elif duration_minutes <= 3 and "quick_take" in short_structures:
            return short_structures["quick_take"]

    # Default: full structure
    return sc["story_structure"]


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
                {"name": "Historical Timeline & Origins", "query_template": "Search for the definitive history and origins of {topic}. Find a complete timeline of major milestones, key figures, and how it evolved over time."},
                {"name": "Technical Breakdown", "query_template": "Find highly detailed technical explanations and step-by-step breakdowns of exactly how {topic} works or operates."},
                {"name": "Statistics & Impact", "query_template": "Look up specific statistics, economic data points, numerical measurements, and global impact metrics regarding {topic}."},
                {"name": "Debates & Controversies", "query_template": "Search for diverse expert opinions, major controversies, and the primary arguments from opposite sides surrounding {topic}."},
                {"name": "Future Trajectory", "query_template": "Find predictions from industry experts about the future outlook, upcoming developments, and long-term implications of {topic}."}
            ],
            "min_sources": 12,
            "source_types": {
                "encyclopedic": 2,
                "news_reports": 4,
                "expert_analysis": 3,
                "official_documents": 3
            },
            "analysis_questions": [
                "Provide a comprehensive definition and full historical timeline of this topic. Start from the earliest origins and trace every major milestone up to the present day. Include specific dates, locations, and the names of key people at each stage. Write at least 3 detailed paragraphs covering: (a) origins and early history, (b) major turning points or breakthroughs, (c) modern evolution. DO NOT summarize — be exhaustive.",
                "Create detailed profiles of the 5-10 most important people, organizations, or entities involved in this topic. For each, provide: their full name, role, specific contributions or actions, approximate dates of involvement, and why they matter. Include at least 2 sentences per person/entity. Also mention any rivalries, collaborations, or conflicts between them.",
                "List at least 15-20 of the most important facts, dates, statistics, and data points related to this topic. Organize them into categories (e.g., financial data, scientific measurements, population figures, timeline dates, geographic data). Every number must be as specific as possible — use exact figures, not approximations. Include the source or context for each statistic.",
                "Explain in extreme detail how this works or what the mechanism/process is. Break it down into sequential steps or phases. Use sub-headings for each phase. For each step, explain: what happens, why it happens, what causes it, and what the consequences are. Include technical details that a knowledgeable viewer would appreciate. Write at least 4 paragraphs.",
                "Analyze the global and local impact of this topic in exhaustive detail. Cover at least 5 distinct areas of impact (e.g., economic, social, environmental, political, technological, cultural, health). For each area, provide specific examples with numbers, affected populations, and named locations. Include both positive and negative impacts. Write at least 3 paragraphs.",
                "Present all major arguments, perspectives, and debates surrounding this topic. For each perspective: (a) name the viewpoint and its main proponents, (b) list their 3 strongest arguments with supporting evidence, (c) list the main criticisms of this viewpoint. Include at least 3 distinct perspectives. Also identify points of consensus where most experts agree."
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
                        "beats": ["Cold Open: Hit the viewer with a paradox or shocking statistic", "The Pivot: Explain why everything they thought they knew is wrong", "The Stakes: Exactly what happens if we don't understand this", "The Thesis: A one-sentence distillation of the entire video"]
                    },
                    {
                        "name": "BACKGROUND & CONTEXT",
                        "percentage": 25,
                        "beats": ["The Unknown Origin: Frame the beginning as a mystery solved", "The World Before: Paint a vivid picture of the status quo", "The Disruption: The exact moment everything changed", "The Hidden Catalyst: The underlying factor no one talks about"]
                    },
                    {
                        "name": "CORE ANALYSIS",
                        "percentage": 40,
                        "beats": [
                            "The Core Mechanism: Break down exactly how it works with a concrete analogy", "The Crucial Evidence: Present the undeniable, mind-blowing data point",
                            "The Ripple Effect: Show the surprising secondary consequences", "The Consensus View: Summarize what the experts agree on",
                            "The Deepest Nuance: Explore the counter-perspective that complicates everything"
                        ]
                    },
                    {
                        "name": "CONCLUSION & FUTURE",
                        "percentage": 20,
                        "beats": ["The Synthesis: Bring the analysis together into a single revelation", "The Current Reality: Exactly where we stand today", "The Horizon: What the experts predict happens next", "The Final Question: Leave the viewer questioning their previous assumptions"]
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
            "short_structures": {
                "micro": {
                    "acts": [{
                        "name": "FULL PIECE",
                        "percentage": 100,
                        "beats": [
                            "The Hook: One shocking fact, paradox, or statistic that stops the scroll",
                            "The Core: The single most important insight — explained in one vivid analogy",
                            "The Payoff: A memorable punchline, twist, or mind-bending final thought"
                        ]
                    }],
                    "hook_types": ["Shocking Stat", "Bold Claim", "Direct Question"],
                    "emotional_beats": {"curiosity": 1, "awe": 1}
                },
                "quick_take": {
                    "acts": [
                        {
                            "name": "THE HOOK",
                            "percentage": 25,
                            "beats": [
                                "Attention Grab: Open with the most surprising or counter-intuitive angle",
                                "The Stakes: Why this matters to the viewer right now"
                            ]
                        },
                        {
                            "name": "THE SUBSTANCE",
                            "percentage": 50,
                            "beats": [
                                "The Core Mechanism: The one thing you need to understand — with a concrete analogy",
                                "The Evidence: One killer data point or example that makes it undeniable",
                                "The Nuance: The twist or counter-perspective that makes this interesting"
                            ]
                        },
                        {
                            "name": "THE PAYOFF",
                            "percentage": 25,
                            "beats": [
                                "The Takeaway: What this means for the viewer",
                                "The Closer: End with an unforgettable final thought or question"
                            ]
                        }
                    ],
                    "hook_types": ["Shocking Stat", "Bold Claim", "Direct Question", "What If"],
                    "emotional_beats": {"curiosity": 2, "clarity": 1, "awe": 1}
                }
            },
            "pacing_guide": {
                1: 15,
                2: 30,
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
                {"name": "The Initial Incident", "query_template": "Search for the initial reporting, factual timeline of events, and the exact scope of the scandal or fraud surrounding {topic}."},
                {"name": "Investigative Evidence", "query_template": "Find specific investigative journalism pieces, court documents, official audits, or whistleblower testimonies detailing the wrongdoing in {topic}."},
                {"name": "The Money Trail", "query_template": "Track the financial data, SEC filings, shell companies, profit margins, and exact monetary damages/losses associated with {topic}."},
                {"name": "Villain Profiles", "query_template": "Look up the personal backgrounds, net worths, direct quotes, and current legal statuses of the primary executives and perpetrators involved in {topic}."},
                {"name": "Systemic Failures", "query_template": "Search for expert analysis on the regulatory failures, loopholes, and systemic issues that allowed {topic} to occur."}
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
                "Create exhaustive profiles of all major 'villains' or wrongdoers involved. For each person: provide their full name, exact title/role, specific actions they took (with dates), how much they personally profited (exact dollar amounts where available), their current legal status, and any direct quotes that reveal their mindset. Include at least 3-5 individuals. Write 2+ paragraphs per person. Include any shell companies, pseudonyms, or aliases they used.",
                "Document the victims in comprehensive detail. Provide: (a) the total number of people affected (with demographic breakdowns if available), (b) the total financial losses (exact figures), (c) at least 3 specific individual victim stories with names, locations, and what happened to them, (d) long-term consequences on victims' lives (health, financial ruin, psychological impact), (e) any class-action lawsuits or victim advocacy groups that formed. Write at least 3 detailed paragraphs.",
                "Identify every whistleblower, investigator, journalist, or hero who tried to expose or stop this. For each: their full name, their role/position, exactly what they discovered, when they came forward, what evidence they presented, and what consequences they faced (retaliation, firing, legal threats, vindication). Include specific quotes from their testimony or reporting. Write at least 2 paragraphs per person.",
                "Construct a hyper-detailed chronological timeline from the very first warning signs to the present day. Include at least 15-20 specific dated entries. For each entry, describe: what happened, who was involved, what the immediate reaction was, and what it led to next. Mark the critical turning points. Include any ongoing investigations or pending legal actions.",
                "Follow the money trail in exhaustive detail. Map out: (a) total scale of money involved (revenue, profits, losses — exact figures), (b) the flow of money from source to destination (who paid whom), (c) any offshore accounts, shell companies, or money laundering schemes, (d) SEC filings, tax records, or financial disclosures that reveal the truth, (e) how the money was hidden and how it was eventually discovered. Include specific financial figures for every claim. Write at least 3 paragraphs.",
                "Analyze every systemic failure, enabler, and structural weakness that allowed this to happen. Cover: (a) regulatory failures — which agencies failed and why, (b) corporate governance gaps, (c) media failures — did journalists miss warning signs?, (d) political connections or lobbying that provided cover, (e) cultural or industry norms that normalized the behavior. For each failure, explain specifically how it could have been prevented. Write at least 3 paragraphs."
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
                        "beats": ["Cold Open: Drop the audience directly into the middle of the scandal", "Establish the facade: Describe the 'perfect' world before the cracks showed", "Reveal the true scale: Shock the audience with the financial or human cost", "Introduce the mastermind/villain: Establish who was pulling the strings"]
                    },
                    {
                        "name": "ACT 2 — The Unraveling",
                        "percentage": 60,
                        "beats": [
                            "The First Thread: Isolate the tiny mistake that began the downfall", "The Core Mechanism: Explain exactly how the fraud/scandal legally or technically functioned", "The Villain's Mindset: Quote them directly to show their justification",
                            "The Escalation: Detail how the scheme grew out of control", "The Human Cost: Tell a visceral, emotional story of a specific victim", 
                            "The Systemic Failure: Expose exactly which regulatory body or watchdogs looked the other way",
                            "The Whistleblower: Introduce the person who risked everything to expose it", "The Climax: The moment of absolute confrontation and collapse"
                        ]
                    },
                    {
                        "name": "ACT 3 — The Reckoning",
                        "percentage": 15,
                        "beats": ["The Aftermath: The exact legal and financial fate of the villains", "The Ongoing Damage: How the victims are surviving today", "The Lingering Problem: Why the systemic vulnerability still exists", "The Warning: What the audience must watch out for next time"]
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
            "short_structures": {
                "micro": {
                    "acts": [{
                        "name": "FULL PIECE",
                        "percentage": 100,
                        "beats": [
                            "The Crime: The scandal in one devastating sentence — name the villain, name the damage",
                            "The Proof: The single most damning piece of evidence or quote",
                            "The Punchline: What happened to them — or why they got away with it"
                        ]
                    }],
                    "hook_types": ["Statistic Shock", "Direct Address", "Result First"],
                    "emotional_beats": {"outrage": 1, "shocking_reveal": 1}
                },
                "quick_take": {
                    "acts": [
                        {
                            "name": "THE CRIME",
                            "percentage": 30,
                            "beats": [
                                "The Scandal: Drop the audience into the middle of it — names, numbers, scale",
                                "The Villain: Who did this and what was their justification"
                            ]
                        },
                        {
                            "name": "THE EVIDENCE",
                            "percentage": 45,
                            "beats": [
                                "The Mechanism: Exactly how the fraud or wrongdoing worked",
                                "The Human Cost: One specific victim's story that makes it real",
                                "The Systemic Failure: Which watchdog looked the other way and why"
                            ]
                        },
                        {
                            "name": "THE RECKONING",
                            "percentage": 25,
                            "beats": [
                                "The Aftermath: What happened to the villain",
                                "The Warning: Why this could happen again"
                            ]
                        }
                    ],
                    "hook_types": ["Statistic Shock", "Result First", "Contradiction"],
                    "emotional_beats": {"outrage": 1, "human_impact": 1, "shocking_reveal": 1}
                }
            },
            "pacing_guide": {
                1: 15,
                2: 35,
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
                {"name": "Core Fundamentals", "query_template": "Find the best simple analogies and fundamental textbook explanations for the core concept of {topic}."},
                {"name": "Advanced Mechanics", "query_template": "Search for advanced scientific papers or detailed technical breakdowns explaining the underlying mechanics and exact processes of {topic}."},
                {"name": "Debunking Myths", "query_template": "Look up the most common public misconceptions or myths about {topic} and the scientific evidence or facts that debunk them."},
                {"name": "Real-World Applications", "query_template": "Find specific real-world applications, recent breakthroughs, and tangible future implications resulting from {topic}."}
            ],
            "min_sources": 10,
            "source_types": {
                "educational_content": 3,
                "scientific_papers": 2,
                "expert_explanations": 3,
                "visual_references": 2
            },
            "analysis_questions": [
                "Provide a comprehensive, multi-layered explanation of this concept. Start with: (a) a simple 2-sentence explanation a 10-year-old could understand, (b) an everyday analogy that maps perfectly to how it works, (c) a more detailed technical explanation for curious adults, (d) the advanced/nuanced version that experts would appreciate. Each layer should build on the previous one. Write at least 4 paragraphs total.",
                "Break down the 5-7 key components, steps, or mechanisms that make this work. For each component: (a) name it clearly, (b) explain what it does and why it is necessary, (c) explain what would happen if this component failed or was removed, (d) provide a specific real-world analogy for this component. Organize as a numbered list with 3-4 sentences per component. Include any sub-processes or feedback loops between components.",
                "List and thoroughly debunk at least 5 common misconceptions about this topic. For each misconception: (a) state what people commonly believe, (b) explain why they believe it (what makes it intuitive or appealing), (c) explain in detail why it is wrong with specific evidence, (d) state the correct understanding. Write 2-3 sentences per misconception. Include misconceptions held by the general public AND by professionals in adjacent fields.",
                "Compile at least 8-10 of the most surprising, mind-blowing, or counter-intuitive facts about this topic. For each fact: state it clearly, explain why it is surprising, and provide the source or study that established it. Include scale comparisons (e.g., 'that's equivalent to...') to make abstract numbers tangible. Organize from most to least surprising.",
                "Describe at least 5 concrete real-world examples or applications that make this concept tangible. For each example: (a) describe the specific situation with names, places, and dates, (b) explain exactly how the concept applies, (c) describe the outcome or result. Include examples from different domains (medicine, technology, everyday life, nature, industry). Write 2-3 sentences per example.",
                "Document the latest developments, discoveries, or breakthroughs in this area from the past 2-3 years. For each development: (a) what was discovered or achieved, (b) who did it (specific researchers, institutions, or companies), (c) when it was published or announced, (d) why it matters and what it changes about our understanding. Include at least 3-5 recent developments. Also describe what the next major breakthrough is expected to be."
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
                        "beats": ["The Illusion: State a common belief that is entirely wrong", "The Reality Check: Reveal the mind-blowing truth", "The Personal Stakes: Explain exactly why this matters to the viewer's daily life or future"]
                    },
                    {
                        "name": "THE FOUNDATION — Build Understanding",
                        "percentage": 25,
                        "beats": ["The ELI5 Analogy: Compare the concept to a universally understood everyday object", "The Primary Component: Introduce the most important part of how it works", "The Visual Mental Model: Describe what it looks like in motion", "The Myth Bust: Dismantle the most common public misunderstanding directly"]
                    },
                    {
                        "name": "THE DEEP DIVE — How It Really Works",
                        "percentage": 40,
                        "beats": [
                            "The Next Layer: Add complexity to the earlier analogy without breaking it", "The Mechanical Steps: Walk through the exact process sequentially",
                            "The Tangible Example: Ground the theory in a specific historical or modern use-case", "The Nuance: Introduce the advanced concept that separates experts from novices",
                            "The 'Aha' Moment: Connect all previously mentioned concepts into a single realization"
                        ]
                    },
                    {
                        "name": "THE PAYOFF — So What?",
                        "percentage": 20,
                        "beats": ["The Real-World Capability: What this allows us to do right now", "The Frontier: What researchers are trying to do with this tomorrow", "The Ultimate Mind-Bender: Leave them with an awe-inspiring final fact", "The Call to Curiosity: Encourage them to question their world"]
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
            "short_structures": {
                "micro": {
                    "acts": [{
                        "name": "FULL PIECE",
                        "percentage": 100,
                        "beats": [
                            "The Myth: State the common belief that everyone gets wrong",
                            "The Truth: Reveal the actual answer with one killer analogy",
                            "The Mind-Blow: Leave them with the most counter-intuitive implication"
                        ]
                    }],
                    "hook_types": ["Wrong Assumption", "Surprising Stat", "What If Scenario"],
                    "emotional_beats": {"curiosity": 1, "aha_moment": 1}
                },
                "quick_take": {
                    "acts": [
                        {
                            "name": "THE QUESTION",
                            "percentage": 20,
                            "beats": [
                                "The Illusion: State what everyone thinks they know — and why it's wrong",
                                "The Promise: What the viewer will understand in the next 2 minutes"
                            ]
                        },
                        {
                            "name": "THE EXPLANATION",
                            "percentage": 55,
                            "beats": [
                                "The Analogy: Compare the concept to something universally understood",
                                "The Mechanism: Walk through how it actually works — step by step",
                                "The Surprise: The counter-intuitive fact that makes experts different from novices"
                            ]
                        },
                        {
                            "name": "THE PAYOFF",
                            "percentage": 25,
                            "beats": [
                                "The Application: One real-world example that makes it tangible",
                                "The Mind-Bender: End with an awe-inspiring implication"
                            ]
                        }
                    ],
                    "hook_types": ["Wrong Assumption", "Surprising Stat", "Scale Comparison"],
                    "emotional_beats": {"curiosity": 1, "aha_moment": 1, "wonder": 1}
                }
            },
            "pacing_guide": {
                1: 12,
                2: 25,
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
                {"name": "Official Specs", "query_template": "Search for the official specifications, pricing tiers, exact dimensions, hardware/software features, and release history of {topic}."},
                {"name": "Independent Benchmarks", "query_template": "Find independent benchmark tests, performance data, expert reviews, and real-world usage metrics for {topic}."},
                {"name": "Direct Competitors", "query_template": "Look up direct side-by-side comparisons between {topic} and its top 3 market competitors across key metrics."},
                {"name": "User Sentiment", "query_template": "Search for long-term user reviews, common complaints, Reddit discussions, and known defects regarding {topic}."}
            ],
            "min_sources": 10,
            "source_types": {
                "official_specs": 2,
                "expert_reviews": 3,
                "user_experiences": 3,
                "comparison_articles": 2
            },
            "analysis_questions": [
                "Provide an exhaustive specifications sheet for this product/technology. Include: (a) every key technical specification with exact numbers, (b) all pricing tiers and what each tier includes, (c) release dates and version history, (d) physical dimensions, weight, materials if applicable, (e) supported platforms, compatibility requirements, (f) warranty terms and return policies. Organize in a structured format. Be extremely specific — no 'approximately' or 'around'.",
                "Analyze the top 3-5 strengths of this product in deep detail. For each strength: (a) describe exactly what makes it good with specific metrics or benchmarks, (b) cite at least 2 expert reviewers (by name/publication) who highlighted this, (c) provide specific test results, measurements, or user data that support this, (d) explain how this strength compares to the same feature in competitors. Write 2-3 sentences per strength.",
                "Analyze the top 3-5 weaknesses, problems, or disappointments in deep detail. For each weakness: (a) describe the exact issue with specific examples, (b) explain how severely it affects the user experience, (c) cite expert reviewers who noted this problem, (d) describe whether the manufacturer has acknowledged or addressed it, (e) suggest workarounds if they exist. Write 2-3 sentences per weakness. Include both hardware/software issues and business/pricing concerns.",
                "Create a detailed head-to-head comparison with the top 3 direct competitors. For each competitor: (a) name and model, (b) price comparison, (c) side-by-side specs on at least 5 key metrics, (d) areas where the competitor wins, (e) areas where the reviewed product wins, (f) which expert reviewers recommend which product and why. Include specific benchmark numbers wherever possible.",
                "Compile a comprehensive analysis of real user feedback. Cover: (a) average rating across major platforms (Amazon, Reddit, specialized forums), (b) the top 5 most common praise points with example quotes, (c) the top 5 most common complaints with example quotes, (d) any widespread defects or reliability issues reported, (e) how user sentiment has changed over time (initial reception vs long-term ownership), (f) differences in feedback between casual users vs power users.",
                "Provide a complete total cost of ownership analysis. Include: (a) upfront purchase price for each tier, (b) ongoing costs (subscriptions, accessories, maintenance, consumables), (c) estimated lifespan and depreciation, (d) hidden costs most buyers don't anticipate. Then create clear buyer profiles: (a) the ideal buyer — who benefits most and why, (b) who should absolutely NOT buy this and why, (c) the best alternative for each 'should not buy' profile."
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
                        "beats": ["The Hot Take: Open with a bold, controversial statement about the product", "The Hype vs Reality: Address the expectations", "The Guarantee: Exactly what the viewer will know by the end of the video"]
                    },
                    {
                        "name": "OVERVIEW — What Is It?",
                        "percentage": 15,
                        "beats": ["The Core Identity: Define exactly what this is trying to be", "The Spec Highlights: The three numbers or features that actually matter", "The Cost Analysis: Break down the true price including hidden fees"]
                    },
                    {
                        "name": "DEEP DIVE — The Good, The Bad, The Ugly",
                        "percentage": 50,
                        "beats": [
                            "The Flagship Win: Deep dive into the absolute best feature with specific testing data", "The Daily Grind: Describe the frictionless joy (or pain) of using it daily",
                            "The Hidden Gem: A feature nobody talks about but everyone will use", "The Dealbreaker: Aggressively critique the biggest flaw with specific evidence",
                            "The Competitor Context: Compare it directly against its biggest rival on value", "The User Consensus: Synthesize long-term reviews from real buyers"
                        ]
                    },
                    {
                        "name": "THE VERDICT",
                        "percentage": 25,
                        "beats": ["The Perfect Buyer: Describe the exact person who must buy this right now", "The 'Do Not Buy': Describe the person who will waste their money on this", "The Better Alternative: What to buy if you fall into the 'Do Not Buy' camp", "The Final Score: A definitive, unambiguous recommendation"]
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
            "short_structures": {
                "micro": {
                    "acts": [{
                        "name": "FULL PIECE",
                        "percentage": 100,
                        "beats": [
                            "The Verdict: Give the recommendation immediately — buy, skip, or wait",
                            "The Reason: The single most important thing that justifies the verdict",
                            "The Caveat: The one catch or deal-breaker everyone should know"
                        ]
                    }],
                    "hook_types": ["Hot Take", "Bold Claim", "The One Thing"],
                    "emotional_beats": {"excitement": 1, "satisfaction": 1}
                },
                "quick_take": {
                    "acts": [
                        {
                            "name": "THE HOT TAKE",
                            "percentage": 20,
                            "beats": [
                                "The Verdict First: Open with the bold, unambiguous recommendation",
                                "The Context: What this competes against and what it costs"
                            ]
                        },
                        {
                            "name": "THE BREAKDOWN",
                            "percentage": 55,
                            "beats": [
                                "The Best Feature: The flagship capability with one specific test result",
                                "The Worst Flaw: The biggest disappointment — be brutally honest",
                                "The Competitor Check: How the direct rival compares on the thing that matters most"
                            ]
                        },
                        {
                            "name": "THE BOTTOM LINE",
                            "percentage": 25,
                            "beats": [
                                "The Perfect Buyer: Exactly who should buy this",
                                "The Skip: Who should save their money and buy what instead"
                            ]
                        }
                    ],
                    "hook_types": ["Hot Take", "Bold Claim", "Before/After"],
                    "emotional_beats": {"excitement": 1, "disappointment": 1, "satisfaction": 1}
                }
            },
            "pacing_guide": {
                1: 12,
                2: 25,
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
                {"name": "The Subject's Background", "query_template": "Search for comprehensive biographical profiles, early life history, formative experiences, and the family background of the subject of {topic}."},
                {"name": "The Turning Point", "query_template": "Find documentation, interviews, or articles discussing the specific inciting incident or major turning point in {topic}."},
                {"name": "The Deepest Struggles", "query_template": "Look up the specific obstacles, financial ruin, emotional rock-bottom moments, and major public failures experienced during {topic}."},
                {"name": "Allies and Rivals", "query_template": "Search for public quotes, relationship dynamics, and conflicts involving the friends, allies, and primary antagonists related to {topic}."},
                {"name": "Current Legacy", "query_template": "Find recent public statements, current status, measurable societal impact, and the lasting legacy of {topic}."}
            ],
            "min_sources": 12,
            "source_types": {
                "biographical_profiles": 3,
                "interviews_quotes": 3,
                "contextual_reporting": 3,
                "impact_analysis": 3
            },
            "analysis_questions": [
                "Build an exhaustive profile of the central character or subject. Include: (a) full name, date and place of birth, family background, and early childhood environment, (b) education, formative experiences, and early career, (c) personality traits — both strengths and flaws — with specific anecdotes that reveal their character, (d) their core motivation or driving force, (e) how people close to them describe them (include direct quotes if available), (f) any contradictions or complexities in their personality. Write at least 4 detailed paragraphs. Paint a vivid, three-dimensional portrait.",
                "Describe the inciting incident in cinematic, scene-level detail. Include: (a) the exact date, time, and location, (b) what was happening in their life immediately before this moment, (c) exactly what happened — step by step, minute by minute if possible, (d) their immediate emotional and physical reaction, (e) the first decision they made in response, (f) what they stood to lose by acting (or not acting). Include direct quotes, sensory details (what they saw, heard, felt), and the atmosphere of the moment. Write at least 3 paragraphs.",
                "Document every major obstacle, setback, and low point in exhaustive detail. For each obstacle: (a) describe exactly what happened with dates and specifics, (b) explain why it was so devastating — what it threatened to destroy, (c) how it affected them emotionally, physically, or financially, (d) how they initially responded (including moments of doubt, despair, or near-surrender), (e) what ultimately allowed them to push through. Include at least 4-5 distinct obstacles. Identify the single lowest point — the moment everything almost fell apart. Write at least 3 paragraphs.",
                "Create detailed profiles of every significant ally AND antagonist. For each person: (a) full name and their relationship to the subject, (b) their specific role — exactly what they did to help or hinder, (c) their own motivations for supporting or opposing the subject, (d) key moments or scenes involving this person, (e) direct quotes from them about the subject if available. Include at least 3 allies and 3 antagonists. Also describe any relationships that shifted (allies who became enemies or vice versa), and any betrayals or unexpected alliances. Write at least 3 paragraphs.",
                "Describe the climax or decisive moment in vivid, scene-level detail. Include: (a) the exact setting — date, location, atmosphere, (b) the buildup — what led to this specific moment, (c) the moment itself — what happened, what was said, what was decided, (d) the immediate aftermath — reactions from the subject, their allies, their opponents, the public, (e) why THIS moment (and not an earlier one) was the true turning point. Include direct quotes and sensory details. Write at least 3 paragraphs.",
                "Analyze the lasting impact and current status in comprehensive detail. Cover: (a) the measurable impact on the community, industry, or world — with specific statistics and data, (b) how the subject's life changed personally after the climax (relationships, health, wealth, public perception), (c) what legacy institutions, laws, movements, or cultural shifts resulted, (d) where they are right now — their current activities, age, location, public statements, (e) how they reflect on their journey today (include recent quotes), (f) what lessons their story offers and why it still resonates. Write at least 3 paragraphs."
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
                        "beats": ["In Media Res: Open on the subject's most vulnerable or dramatic moment", "The Origin: Trace back to their childhood environment and core wound", "The Status Quo: Establish what their normal life looked like", "The MacGuffin: Identify the one thing they wanted more than anything else"]
                    },
                    {
                        "name": "THE CALL — Something Breaks",
                        "percentage": 15,
                        "beats": ["The Shattered Reality: Describe the exact inciting incident with sensory detail", "The Impossible Dilemma: Lay out the terrible choices they faced", "Crossing the Threshold: The exact action they took that proved there was no going back"]
                    },
                    {
                        "name": "THE STRUGGLE — The Price of Change",
                        "percentage": 35,
                        "beats": [
                            "The First Escalation: The initial unexpected failure or obstacle", "The Small Victory: A moment of false hope before the storm", "The Adversary/Ally Intro: Reveal who is helping them and who is trying to stop them",
                            "The Deepest Valley: Describe the absolute rock-bottom moment of despair", "The Internal War: Their reaction to losing everything",
                            "The Rebirth: The profound realization that allowed them to stand back up"
                        ]
                    },
                    {
                        "name": "THE TRANSFORMATION — Who They Became",
                        "percentage": 15,
                        "beats": ["The Climax: The final confrontation or decisive moment", "The Ultimate Price: What they had to sacrifice to win (or the realization in defeat)", "The Metamorphosis: How their personality and worldview fundamentally changed"]
                    },
                    {
                        "name": "THE LEGACY — What It Means",
                        "percentage": 15,
                        "beats": ["The Current Reality: Exactly where they are and what they are doing today", "The Ripple Effect: The measurable impact they had on the world around them", "The Universal Truth: The core lesson their journey teaches us about humanity", "The Lingering Image: A powerful final thought or quote"]
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
            "short_structures": {
                "micro": {
                    "acts": [{
                        "name": "FULL PIECE",
                        "percentage": 100,
                        "beats": [
                            "The Moment: Drop into the most dramatic, pivotal scene — sensory detail, emotion",
                            "The Choice: What they decided to do and what it cost them",
                            "The Legacy: What changed because of that one decision"
                        ]
                    }],
                    "hook_types": ["In-Media-Res Scene", "A Single Detail", "Contrast (Then vs Now)"],
                    "emotional_beats": {"empathy": 1, "tension": 1}
                },
                "quick_take": {
                    "acts": [
                        {
                            "name": "THE SCENE",
                            "percentage": 25,
                            "beats": [
                                "In Media Res: Open on the most vulnerable or dramatic moment — make us feel it",
                                "The Setup: Who are they and why should we care"
                            ]
                        },
                        {
                            "name": "THE STRUGGLE",
                            "percentage": 50,
                            "beats": [
                                "The Turning Point: The exact moment everything changed",
                                "The Lowest Point: When they nearly gave up — what almost broke them",
                                "The Decision: What they chose to do when it mattered most"
                            ]
                        },
                        {
                            "name": "THE TRANSFORMATION",
                            "percentage": 25,
                            "beats": [
                                "The Outcome: What happened because of their choice",
                                "The Lesson: The universal truth their story teaches us"
                            ]
                        }
                    ],
                    "hook_types": ["In-Media-Res Scene", "Contrast (Then vs Now)", "Opening Dialogue"],
                    "emotional_beats": {"empathy": 2, "tension": 1, "triumph": 1}
                }
            },
            "pacing_guide": {
                1: 13,
                2: 28,
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
            "mode": "deep",
            "search_layers": [
                {"name": "Factual Timeline", "query_template": "Search for a hyper-detailed chronological timeline of exactly what happened regarding {topic}, including verified facts, dates, and names."},
                {"name": "Immediate Impact", "query_template": "Find data on the immediate economic, political, and social impact of {topic}, including specific dollar figures and affected demographics."},
                {"name": "Expert Perspectives", "query_template": "Look up the strongest arguments from at least 3 distinct political or expert perspectives debating the implications of {topic}."},
                {"name": "Historical Precedent", "query_template": "Search for specific historical events spanning the last 50 years that parallel {topic} and analyze how they played out."},
                {"name": "Overlooked Details", "query_template": "Find contrarian opinions, overlooked systemic failures, or nuanced context that mainstream coverage of {topic} is missing."}
            ],
            "min_sources": 8,
            "source_types": {
                "breaking_news": 3,
                "analysis_opinion": 3,
                "expert_reactions": 2
            },
            "analysis_questions": [
                "Provide a hyper-detailed factual account of exactly what happened. Include: (a) the precise sequence of events with specific dates and times, (b) every key person involved by full name and title, (c) exact quotes from official statements, press conferences, or social media posts, (d) verified numbers and data points, (e) what is still unconfirmed or disputed. Separate clearly between confirmed facts and unverified reports. Write at least 3 paragraphs.",
                "Analyze the immediate and downstream impact in exhaustive detail. Cover: (a) who is directly affected — number of people, specific demographics, named organizations, (b) economic impact with specific dollar figures, (c) political or regulatory consequences, (d) social and cultural ripple effects, (e) international reactions from specific countries or organizations. For each area of impact, provide concrete examples and data. Write at least 3 paragraphs.",
                "Present at least 4-5 distinct perspectives or arguments on this event. For each perspective: (a) name the viewpoint and identify specific public figures, pundits, or organizations who hold it, (b) list their 3 strongest arguments with specific evidence or quotes, (c) explain the emotional or ideological foundation of this view, (d) note the strongest counter-argument against it. Include perspectives from across the political/ideological spectrum. Write at least 2 paragraphs per perspective.",
                "Provide exhaustive historical context and precedent analysis. Include: (a) at least 3-5 specific historical events that parallel this situation, with dates and outcomes, (b) explain exactly how each parallel is similar and how it differs, (c) what lessons from history apply here, (d) longer-term trends (over decades) that led to this moment, (e) any cyclical patterns that experts have identified. Write at least 3 paragraphs.",
                "Identify at least 5 things that the mainstream narrative is getting wrong, overlooking, or oversimplifying. For each: (a) state the common belief or narrative, (b) explain what the actual nuance or missing context is, (c) cite specific data, expert opinions, or counter-evidence that most coverage misses, (d) explain why this misconception persists. Include perspectives from specialized experts that haven't gotten mainstream attention. Write at least 2 paragraphs.",
                "Provide detailed scenario analysis for what happens next. Present at least 3 distinct scenarios: (a) most likely outcome — probability estimate and supporting evidence, (b) best-case scenario — what would need to happen and how likely it is, (c) worst-case scenario — risks and warning signs to watch for, (d) wild card scenario — an unexpected development that could change everything. For each scenario, provide a specific timeline and name the key decision-makers involved. Write at least 3 paragraphs total."
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
                        "beats": ["The Explosive Opener: State the most shocking, indisputable fact immediately", "The Narrative Collapse: Why the mainstream headline is lying to you", "The Real Stakes: Why the viewer needs to stop scrolling and pay attention"]
                    },
                    {
                        "name": "THE CONTEXT — What Nobody's Telling You",
                        "percentage": 25,
                        "beats": ["The 60-Second Backstory: Speed-run the chronological history leading up to this", "The Hidden Power Dynamics: Reveal who the real players are behind the scenes", "The Precedent: Prove this has happened before by citing an exact historical parallel"]
                    },
                    {
                        "name": "THE TAKE — Here's What I Think",
                        "percentage": 40,
                        "beats": [
                            "The Core Argument: Deliver a bold, unambiguous thesis statement", "The Undeniable Proof: Back it up with a hard statistic or direct quote",
                            "The Steelman: Present the strongest counter-argument fairly", "The Takedown: Dismantle that counter-argument systematically",
                            "The Blindspot: Expose the nuance that everyone on Twitter/News is completely missing"
                        ]
                    },
                    {
                        "name": "THE PREDICTION — What Happens Next",
                        "percentage": 20,
                        "beats": ["The Brutal Reality: The most likely outcome over the next 6 months", "The Black Swan: The wild card event that could change everything", "The Actionable Advice: What the viewer should do or watch out for", "The Provocation: Ask a polarizing question to drive immediate debate in the comments"]
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
            "short_structures": {
                "micro": {
                    "acts": [{
                        "name": "FULL PIECE",
                        "percentage": 100,
                        "beats": [
                            "What Happened: The headline in one explosive sentence — name names",
                            "Why It Matters: The one implication nobody is talking about",
                            "The Take: Your bold, unambiguous prediction or verdict"
                        ]
                    }],
                    "hook_types": ["Breaking Statement", "Absurd Stat", "Calling Out"],
                    "emotional_beats": {"urgency": 1, "conviction": 1}
                },
                "quick_take": {
                    "acts": [
                        {
                            "name": "THE BOMB",
                            "percentage": 25,
                            "beats": [
                                "The Explosive Opener: The most shocking, indisputable fact — right now",
                                "The Real Stakes: Why the mainstream headline is wrong or incomplete"
                            ]
                        },
                        {
                            "name": "THE TAKE",
                            "percentage": 50,
                            "beats": [
                                "The Backstory: 30-second speed-run of how we got here",
                                "The Core Argument: Your bold thesis with one undeniable proof point",
                                "The Counter: The strongest opposing view — and why it falls apart"
                            ]
                        },
                        {
                            "name": "THE PREDICTION",
                            "percentage": 25,
                            "beats": [
                                "What Happens Next: The most likely outcome in the next 6 months",
                                "The Provocation: A polarizing question to drive engagement"
                            ]
                        }
                    ],
                    "hook_types": ["Breaking Statement", "Absurd Stat", "Prediction"],
                    "emotional_beats": {"urgency": 1, "conviction": 1, "surprise": 1}
                }
            },
            "pacing_guide": {
                1: 15,
                2: 32,
                5: 80,
                10: 160,
                15: 240,
                20: 320
            }
        }
    },

    # ─────────────────────────────────────────────────────────────
    # 6. POLITICAL DEEP DIVE (Impartial & Objective)
    # ─────────────────────────────────────────────────────────────
    "political_deep_dive": {
        "metadata": {
            "name": "Political Deep Dive",
            "icon": "🏛️",
            "description": "Objective, highly detailed analysis of policies, elections, geopolitical events, and legislation. Strictly neutral.",
            "best_for": "Elections, bills & laws, foreign policy, political scandals, sociological shifts",
            "example_topics": [
                "What is actually in the recent Infrastructure Bill?",
                "The history of US-China trade relations",
                "How lobbying shapes healthcare legislation"
            ]
        },
        "research_config": {
            "mode": "deep",
            "search_layers": [
                {"name": "The Core Issue", "query_template": "Search for the exact text, official summaries, and original stated goals of the policy, legislation, or geopolitical issue in {topic}."},
                {"name": "Historical Context", "query_template": "Find chronological historical precedents and track specifically how political party stances have shifted over decades regarding {topic}."},
                {"name": "Money & Power", "query_template": "Look up specific financial records, lobbying expenditures, PAC donations, and cost estimates related to {topic}."},
                {"name": "Demographics & Polling", "query_template": "Search for recent demographic polling data, public opinion surveys, and statistical breakdowns regarding support for {topic}."},
                {"name": "Opposing Perspectives", "query_template": "Find the strongest counter-arguments, conservative perspectives, progressive perspectives, and international reactions debating {topic}."}
            ],
            "min_sources": 15,
            "source_types": {
                "official_government_documents": 4,
                "independent_think_tanks": 3,
                "polling_data": 2,
                "financial_disclosures": 2,
                "journalistic_investigations": 4
            },
            "analysis_questions": [
                "Provide an exhaustive, entirely objective overview of the core issue or policy. Break down exactly what it is, what its stated goals are, and the specific mechanics of how it is supposed to work. Include specific dates, named entities, and exact definitions. Write at least 3 detailed paragraphs. Remain strictly neutral.",
                "Detail the comprehensive historical precedent and origins of this issue. Cover: (a) when this issue first arose, (b) similar past legislation or policies and whether they succeeded or failed, (c) how the major political parties or factions have shifted their stances over the past 20-50 years, (d) major turning points or crises that forced action. Write at least 3 paragraphs with chronological dates.",
                "Follow the money and power dynamics in extreme detail. Identify: (a) exactly who profits or benefits financially from this, (b) specific lobbying groups, PACs, or donors involved, (c) exact dollar amounts spent on lobbying, campaigns, or the policy itself (cost to taxpayers vs expected ROI), (d) any conflicts of interest among key decision-makers. Use specific names and exact financial figures. Write at least 3 paragraphs.",
                "Explain the exact text and specifics of any related legislation, treaties, or policies. What does the law actually say (as opposed to what politicians claim it says)? List: (a) the primary sponsors and their stated rationale, (b) 3-5 specific, actionable clauses or regulations contained within it, (c) loopholes or 'pork barrel' spending included, (d) implementation timelines. Write at least 3 paragraphs.",
                "Analyze public opinion, polling, and demographic support. Who supports this and who opposes it? Break down the data by: (a) age, (b) income bracket, (c) geographic location (urban vs rural), (d) political affiliation. Cite specific recent polls (including the polling organization and date). Explain why certain demographics lean the way they do based on sociological factors. Write at least 3 paragraphs.",
                "Present the best arguments from all major sides with absolute neutrality (STEELMAN the arguments). For each side (e.g., Progressive, Conservative, Libertarian, or specific national interests): (a) identify their primary philosophical argument, (b) cite their strongest specific evidence or data point, (c) name their most prominent spokespeople, (d) outline their primary fear or criticism of the opposing side. Give equal weight and paragraph length to at least 3 competing perspectives. Write at least 4 paragraphs."
            ]
        },
        "script_config": {
            "system_prompt": (
                "You are an elite, strictly impartial political correspondent and documentary writer. "
                "Produce a script that explains complex political or geopolitical issues with absolute neutrality.\n\n"
                "CRITICAL RULES:\n"
                "- You MUST remain aggressively objective. Do not tell the viewer what to think.\n"
                "- Steelman all arguments; treat every perspective with intellectual respect.\n"
                "- Focus heavily on who is paying and who is profiting.\n"
                "- Never use emotionally manipulative language to favoring a political side.\n"
                "- Each row = 3-5 sec of screen time\n"
            ),
            "story_structure": {
                "acts": [
                    {
                        "name": "THE STATUS QUO",
                        "percentage": 15,
                        "beats": ["The Cold Open: Ground the abstract policy in a tangible, shocking real-world example", "The Defining Fact: State exactly what this policy/event is without any partisan spin", "The Real Stakes: Explain why this affects the viewer's life, wallet, or freedom"]
                    },
                    {
                        "name": "HOW WE GOT HERE",
                        "percentage": 25,
                        "beats": ["The Historical Root: Trace the origin back to its inception decades ago", "The Catalyst: Identify the specific crisis or moment that forced the current action", "The Power Shift: Describe exactly how the opposing sides formed their modern stances"]
                    },
                    {
                        "name": "THE MECHANICS & THE MONEY",
                        "percentage": 35,
                        "beats": [
                            "The Legislative Reality: Break down exactly what the bill/law says, circumventing political rhetoric", "The Profit Motive: Follow the money to reveal exactly who benefits financially",
                            "The Hidden Loophole: Expose the 'pork barrel' spending or unintended consequences", "The Donor Influence: Name the specific lobbying groups pushing this",
                            "The Demographic Divide: Analyze the exact polling data to show who supports this and why"
                        ]
                    },
                    {
                        "name": "THE PERSPECTIVES",
                        "percentage": 15,
                        "beats": ["The Primary Advocate: Steelman the absolute strongest argument FOR the issue", "The Primary Opponent: Steelman the absolute strongest argument AGAINST the issue", "The Overlooked Angle: Introduce a third perspective or collateral damage victim ignored by both sides"]
                    },
                    {
                        "name": "THE HORIZON",
                        "percentage": 10,
                        "beats": ["The Next Steps: The immediate procedural or political actions that will follow", "The Societal Shift: The long-term consequences of this becoming the new normal", "The Final Objective Thought: Leave the viewer with a neutral, lingering truth"]
                    }
                ],
                "hook_types": ["Historical Parallel", "Follow the Money", "The Hidden Detail", "Data Point", "Direct Contrast"],
                "emotional_beats": {
                    "clarity": 4,
                    "insight": 3,
                    "objectivity": 2,
                    "revelation": 1
                }
            },
            "short_structures": {
                "micro": {
                    "acts": [{
                        "name": "FULL PIECE",
                        "percentage": 100,
                        "beats": [
                            "The Fact: The one policy detail or political event everyone needs to know — stated neutrally",
                            "The Money: Who profits and who pays — follow the money in one sentence",
                            "The Objective Truth: The neutral, lingering implication that both sides would rather you didn't think about"
                        ]
                    }],
                    "hook_types": ["Follow the Money", "Data Point", "The Hidden Detail"],
                    "emotional_beats": {"clarity": 1, "revelation": 1}
                },
                "quick_take": {
                    "acts": [
                        {
                            "name": "THE ISSUE",
                            "percentage": 25,
                            "beats": [
                                "The Cold Open: Ground the abstract policy in a tangible, real-world example",
                                "The Real Stakes: Why this affects the viewer's life, wallet, or freedom"
                            ]
                        },
                        {
                            "name": "THE MECHANICS",
                            "percentage": 50,
                            "beats": [
                                "The Reality: What the law or policy actually says — not what politicians claim",
                                "The Money Trail: Who profits and who pays — specific numbers",
                                "The Steelman: The strongest argument from each side — presented neutrally"
                            ]
                        },
                        {
                            "name": "THE HORIZON",
                            "percentage": 25,
                            "beats": [
                                "What Happens Next: The immediate procedural or political actions that will follow",
                                "The Neutral Truth: An objective final thought that makes the viewer think"
                            ]
                        }
                    ],
                    "hook_types": ["Follow the Money", "Historical Parallel", "Data Point"],
                    "emotional_beats": {"clarity": 2, "insight": 1, "revelation": 1}
                }
            },
            "pacing_guide": {
                1: 15,
                2: 32,
                5: 75,
                10: 150,
                15: 225,
                20: 300
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


def _format_structured_claims_block(structured: dict, max_claims: int = 40,
                                     max_sources: int = 30) -> str:
    """Render a structured research object as a CLAIMS/SOURCES block for prompts.

    Returns empty string if `structured` is missing or has no claims.
    Output shape:

        ═══════ CLAIMS (cite via [s1], [s2]…) ═══════
        [c1] Claim text [s1][s2]
        [c2] Claim text [s3]
        ...

        ═══════ SOURCES ═══════
        [s1] Title — Publisher (url) | "quote excerpt"
        [s2] ...
    """
    if not structured or not isinstance(structured, dict):
        return ""
    claims = structured.get("claims") or []
    sources = structured.get("sources") or []
    if not claims:
        return ""

    lines = ["", "═══════ CLAIMS (cite via [s1], [s2]…) ═══════"]
    for c in claims[:max_claims]:
        cid = c.get("id", "")
        text = c.get("text", "").strip()
        src_ids = c.get("source_ids") or []
        cite_tags = "".join(f"[{sid}]" for sid in src_ids)
        lines.append(f"[{cid}] {text} {cite_tags}".rstrip())

    if sources:
        lines.append("")
        lines.append("═══════ SOURCES ═══════")
        for s in sources[:max_sources]:
            sid = s.get("id", "")
            title = s.get("title") or "(untitled)"
            publisher = s.get("publisher", "")
            url = s.get("url", "")
            quote = s.get("quote", "")
            line = f"[{sid}] {title}"
            if publisher:
                line += f" — {publisher}"
            if url:
                line += f" ({url})"
            if quote:
                line += f' | "{quote[:180]}"'
            lines.append(line)

    return "\n".join(lines) + "\n"


def _format_spine_block(spine: dict, max_claims: int = 40) -> str:
    """Render a Narrative Spine object as a SPINE block for prompts.

    Returns empty string if `spine` is missing or has no key_claims.
    Output shape:

        ═══════ NARRATIVE SPINE (cite via [k1], [k2]…) ═══════
        Logical flow: k1 → k4 → k2 → ...
        [k1] (primary) Claim text [s1][s4]
        [k2] (supporting) Claim text [s3]
        ...
    """
    if not spine or not isinstance(spine, dict):
        return ""
    claims = spine.get("key_claims") or []
    if not claims:
        return ""

    flow = spine.get("logical_flow") or [c.get("id", "") for c in claims]
    by_id = {c.get("id"): c for c in claims if c.get("id")}
    ordered = [by_id[k] for k in flow if k in by_id][:max_claims]
    # Append any claims not in flow (defensive)
    seen = {c.get("id") for c in ordered}
    for c in claims:
        if c.get("id") not in seen:
            ordered.append(c)
            if len(ordered) >= max_claims:
                break

    lines = ["", "═══════ NARRATIVE SPINE (cite via [k1], [k2]…) ═══════"]
    if flow:
        lines.append("Logical flow: " + " → ".join(flow[:max_claims]))
    for c in ordered:
        kid = c.get("id", "")
        text = (c.get("text") or "").strip()
        importance = c.get("importance") or "supporting"
        src_ids = c.get("source_ids") or []
        cite_tags = "".join(f"[{sid}]" for sid in src_ids)
        lines.append(f"[{kid}] ({importance}) {text} {cite_tags}".rstrip())

    source_map = spine.get("source_map") or {}
    if source_map:
        lines.append("")
        lines.append("═══════ SOURCES ═══════")
        for sid, s in list(source_map.items())[:30]:
            title = s.get("title") or "(untitled)"
            publisher = s.get("publisher", "")
            url = s.get("url", "")
            quote = s.get("quote", "")
            line = f"[{sid}] {title}"
            if publisher:
                line += f" — {publisher}"
            if url:
                line += f" ({url})"
            if quote:
                line += f' | "{quote[:180]}"'
            lines.append(line)

    return "\n".join(lines) + "\n"


def build_spine_extraction_prompt(topic: str, research_dossier: str,
                                   structured: dict = None) -> str:
    """Build the prompt that extracts a Narrative Spine from a research dossier.

    The spine is a ranked, source-bound outline that downstream consumers
    (script gen, beat regen, production prompts) consume to keep facts and
    citations stable across the pipeline.
    """
    structured_block = _format_structured_claims_block(structured) if structured else ""

    return f"""You are a narrative architect for documentary video.

Your job: read the research dossier below and extract a NARRATIVE SPINE — a ranked,
source-bound outline of the most important claims and the order they should unfold
in a video narration.

═══════ TOPIC ═══════
{topic}

═══════ RESEARCH DOSSIER ═══════
{research_dossier}
{structured_block}
═══════ TASK ═══════
1. Identify 8 to 18 KEY CLAIMS — atomic, verifiable statements drawn ONLY from the dossier.
   - Do NOT invent facts. Every claim must trace to text in the dossier (or to a source
     listed in the CLAIMS/SOURCES block above when present).
2. Rank each claim by importance:
   - "primary"     — load-bearing facts the narrative cannot be told without (~3-5 of these)
   - "supporting"  — context, evidence, examples that strengthen primaries
   - "color"       — anecdotes, quotes, figures of speech that add texture
3. Define the LOGICAL FLOW — the order these claims should appear in the narration
   (a list of claim ids). Build a story arc: hook → context → escalation → payoff.
4. Bind every claim to its sources. If a CLAIMS/SOURCES block was provided above,
   reuse those `s1`, `s2`, … ids. Otherwise mint sources from URLs found in the dossier
   text (use ids `s1`, `s2`, …).

═══════ OUTPUT FORMAT ═══════
Return ONLY a JSON object with this exact shape:
{{
  "version": 1,
  "topic": {json.dumps(topic)},
  "key_claims": [
    {{
      "id": "k1",
      "text": "Atomic claim text (one sentence).",
      "importance": "primary",
      "source_ids": ["s1", "s4"]
    }},
    ...
  ],
  "logical_flow": ["k1", "k4", "k2", ...],
  "source_map": {{
    "s1": {{"url": "https://...", "title": "Page title", "publisher": "", "quote": ""}},
    ...
  }}
}}

CRITICAL RULES:
- Use the prefix "k" for claim ids (k1, k2, …) and "s" for source ids (s1, s2, …).
- Every id in `logical_flow` MUST appear in `key_claims`.
- Every id in `source_ids` MUST appear in `source_map`.
- Aim for 3-5 primary claims; the rest split between supporting and color.
- Do not include any prose outside the JSON. Begin."""


def build_spine_rerank_prompt(spine: dict, title: str = "",
                               audience: str = "", tone: str = "",
                               format_preset: str = "") -> str:
    """Build the prompt that re-ranks an existing spine for a chosen story angle.

    Same set of claims (ids and text preserved), but `importance` and
    `logical_flow` are recomputed to serve the chosen title / audience / tone.
    Cheap second pass: no new facts, just a different lens on the same dossier.
    """
    spine_block = _format_spine_block(spine) if spine else ""
    angle_lines = []
    if title:
        angle_lines.append(f"TITLE: {title}")
    if audience:
        angle_lines.append(f"AUDIENCE: {audience}")
    if tone:
        angle_lines.append(f"TONE: {tone}")
    if format_preset:
        angle_lines.append(f"FORMAT: {format_preset}")
    angle_block = "\n".join(angle_lines) or "(no angle specified — use the topic implied by the spine)"

    claim_ids = [c.get("id") for c in (spine.get("key_claims") or []) if c.get("id")]

    return f"""You are re-ranking a Narrative Spine for a specific story angle.

The spine's claims are FIXED — you may not add, remove, or rewrite any claim text.
Your only job is to:
  1. Reassign each claim's `importance` (primary | supporting | color) for the chosen angle
  2. Reorder `logical_flow` so the narration leads with what matters MOST for this angle

═══════ ANGLE ═══════
{angle_block}

═══════ CURRENT SPINE ═══════
{spine_block}
═══════ TASK ═══════
For the angle above, decide:
  - PRIMARY (3-5 of them): the load-bearing claims this specific story cannot be told without
  - SUPPORTING: context and evidence that strengthens the primaries for THIS angle
  - COLOR: anecdotes that add texture but aren't essential

Reorder `logical_flow` so the story unfolds well: hook → context → escalation → payoff
relative to the chosen TITLE.

═══════ OUTPUT FORMAT ═══════
Return ONLY a JSON object with this exact shape (no other fields):
{{
  "key_claims": [
    {{"id": "k1", "importance": "primary"}},
    {{"id": "k4", "importance": "supporting"}}
  ],
  "logical_flow": ["k4", "k1"]
}}

CRITICAL RULES:
- Use exactly these claim ids and no others: {claim_ids}
- Every id must appear in `key_claims` exactly once
- `logical_flow` must contain the same set of ids as `key_claims`
- 3-5 claims must be marked "primary"
- Begin."""


def build_spine_suggest_edits_prompt(spine: dict, title: str = "",
                                      audience: str = "") -> str:
    """Build the prompt that asks the AI to propose targeted spine improvements.

    The AI returns a small list of suggested changes (re-rank, importance, or
    text polish) with a one-sentence rationale each. The UI lets the user apply
    or reject each suggestion individually.
    """
    spine_block = _format_spine_block(spine) if spine else ""
    angle_lines = []
    if title:
        angle_lines.append(f"TITLE: {title}")
    if audience:
        angle_lines.append(f"AUDIENCE: {audience}")
    angle_block = "\n".join(angle_lines) or "(no angle specified — improve the spine for general clarity and arc)"

    claim_ids = [c.get("id") for c in (spine.get("key_claims") or []) if c.get("id")]

    return f"""You are a narrative coach reviewing a Narrative Spine and proposing IMPROVEMENTS.

═══════ ANGLE ═══════
{angle_block}

═══════ CURRENT SPINE ═══════
{spine_block}
═══════ TASK ═══════
Propose between 0 and 5 targeted suggestions that would make this spine tell a stronger story.
Each suggestion is ONE of these kinds:
  - "reorder"     : move a claim to a new position in logical_flow
  - "importance"  : change a claim's importance (primary | supporting | color)
  - "edit_text"   : rewrite a claim's text to be clearer (no new facts)

Be conservative: only propose changes that genuinely improve the story. If the spine is
already strong, return an empty list with a one-line note.

═══════ OUTPUT FORMAT ═══════
Return ONLY a JSON object:
{{
  "suggestions": [
    {{
      "kind": "reorder",
      "claim_id": "k4",
      "new_position": 0,
      "rationale": "Lead with the surprising fact — strongest hook for this title."
    }},
    {{
      "kind": "importance",
      "claim_id": "k7",
      "new_importance": "primary",
      "rationale": "This claim directly answers the title's question."
    }},
    {{
      "kind": "edit_text",
      "claim_id": "k2",
      "new_text": "Reactor cores reach 300°C under normal operation.",
      "rationale": "More specific number = more credible."
    }}
  ],
  "overall_note": "1-2 sentence summary, or 'spine looks strong' if no changes."
}}

CRITICAL RULES:
- Use ONLY claim ids that exist above: {claim_ids}
- For "reorder", `new_position` is 0-based
- For "edit_text", keep the same factual content; only improve clarity/precision
- Maximum 5 suggestions. Quality over quantity.
- Return ONLY the JSON. Begin."""


def _top_claim_texts(structured: dict, limit: int = 20) -> str:
    """Render the top claim texts as a bulleted list, for cases where we want
    a compact claims-only summary (e.g. title suggestions). Returns "" when empty."""
    if not structured or not isinstance(structured, dict):
        return ""
    claims = structured.get("claims") or []
    if not claims:
        return ""
    top = claims[:limit]
    return "\n".join(f"- {c.get('text', '').strip()}" for c in top if c.get('text'))


def build_title_suggestions_prompt(template_id: str, topic: str, dossier: str,
                                    audience: str = "General",
                                    structured: dict = None) -> str:
    """
    Build prompt for generating 5 YouTube title suggestions.
    Each title represents a genuinely different narrative angle.
    """
    template = TEMPLATES.get(template_id)
    template_name = template['metadata']['name'] if template else template_id

    # When a structured research object is available, prefer its top claims over
    # the truncated markdown blob — they're denser and carry source attribution.
    claims_summary = _top_claim_texts(structured, limit=20) if structured else ""
    research_block = (f"TOP FACTUAL CLAIMS:\n{claims_summary}"
                      if claims_summary else dossier[:3000])

    prompt = f"""You are a YouTube content strategist who specializes in crafting viral, click-worthy titles.

Based on the research below, generate exactly 5 YouTube video title options for this topic.
Each title must represent a GENUINELY DIFFERENT narrative angle — not just rephrasing the same idea.

TOPIC: {topic}
TEMPLATE STYLE: {template_name}
TARGET AUDIENCE: {audience}

═══════ RESEARCH SUMMARY ═══════
{research_block}

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
    Dynamically pulls available tones from TONE_DEFINITIONS.
    """
    template = TEMPLATES.get(template_id)
    template_name = template['metadata']['name'] if template else template_id

    emotional_context = ""
    if template:
        emo_beats = template["script_config"]["story_structure"].get("emotional_beats", {})
        emotional_context = ", ".join(beat.replace('_', ' ') for beat in emo_beats.keys())

    # Build available tones list dynamically from TONE_DEFINITIONS
    tones_list = "\n".join(f"- {k}: {v['label']} — {v['emotional_stance']}" for k, v in TONE_DEFINITIONS.items())

    prompt = f"""Based on the video title and audience below, suggest the single best tone for the narration.

TITLE: {selected_title}
AUDIENCE: {audience}
TEMPLATE STYLE: {template_name}
TEMPLATE EMOTIONAL BEATS: {emotional_context}

Available tones (pick ONE by its ID):
{tones_list}

Pick the ONE tone whose emotional stance best matches the title's implied narrative angle and the target audience.
Explain briefly why this tone works.

Return ONLY a JSON object:
{{"suggested_tone": "tone_id_from_list", "reasoning": "1-2 sentence explanation of why this tone fits"}}

Return ONLY the JSON."""

    return prompt


def build_script_prompt(template_id: str, topic: str, research_dossier: str,
                        duration_minutes: int = 10, audience: str = "general",
                        tone: str = "", focus: str = "", style_guide: str = None,
                        selected_title: str = None, format_preset: str = "",
                        viewer_outcome: str = "", style_blend_mode: str = "clone",
                        custom_audience: str = "", custom_tone: str = "",
                        structured: dict = None, spine: dict = None) -> str:
    """
    PHASE 1: Build prompt for the creative narration.
    
    Asks Gemini to write a flowing, compelling narration organized by acts/beats.
    Now uses behavioral instruction blocks from AUDIENCE_PROFILES, TONE_DEFINITIONS,
    FORMAT_PRESETS, and VIEWER_OUTCOMES to maximally constrain the AI's output.

    style_blend_mode:
        'clone': Style Guide overrides everything (tone, audience ignored). Pure imitation.
        'blend': Style Guide provides structure/pacing, user's tone + audience remain active.
    """
    template = TEMPLATES.get(template_id)
    if not template:
        return f"Write a {duration_minutes}-minute video script about: {topic}"

    sc = template["script_config"]

    # ── Resolve Format Preset (pacing intent) — must happen before structure resolution ──
    pacing_instruction = ""
    if format_preset and format_preset in FORMAT_PRESETS:
        preset = FORMAT_PRESETS[format_preset]
        if preset["duration_minutes"]:
            duration_minutes = preset["duration_minutes"]
        pacing_instruction = preset["pacing_instruction"]

    # Word-count target based on speech pacing
    total_words = int(duration_minutes * 60 * 2.5)  # ~2.5 words/sec

    # ── Resolve story structure (adaptive for short-form) ──
    structure = _resolve_structure_for_duration(template, format_preset, duration_minutes)

    # Build act descriptions
    acts_text = ""
    for act in structure["acts"]:
        beats_str = ", ".join(act["beats"])
        acts_text += f"\n### {act['name']} ({act['percentage']}% of total)\nBeats: {beats_str}\n"

    # Build emotional beats requirement
    emo_text = ", ".join(
        f"{count}+ {beat.replace('_', ' ').title()}" for beat, count in structure["emotional_beats"].items()
    )

    # ── Short-Form Constraints ──
    short_form_block = ""
    if format_preset in ("micro", "quick_take"):
        short_form_block = (
            f"\n══════════ SHORT-FORM CONSTRAINTS ══════════\n"
            f"This is a SHORT-FORM video ({duration_minutes} minute{'s' if duration_minutes != 1 else ''}, ~{total_words} words).\n"
            f"CRITICAL RULES FOR SHORT CONTENT:\n"
            f"- Do NOT use multi-paragraph beats. Each beat = 1-3 sentences MAX.\n"
            f"- Do NOT include transitions between beats. Jump-cut from idea to idea.\n"
            f"- Do NOT build gradual context. Start with the payoff, then explain.\n"
            f"- The hook must land in the FIRST sentence, not the first paragraph.\n"
            f"- Total narration MUST be approximately {total_words} words. Do NOT exceed this.\n"
        )
        if format_preset == "micro":
            short_form_block += (
                f"- This is a MICRO piece (30-60 seconds). ONE idea. THREE beats. That's it.\n"
                f"- Write like a social media post that became a voiceover. Dense, punchy, done.\n"
            )

    # ── Resolve Audience Profile ──
    if audience == "custom" and custom_audience:
        audience_block = (
            f"AUDIENCE: ✏️ Custom — \"{custom_audience}\"\n"
            f"AUDIENCE ADAPTATION RULES:\n"
            f"- The user described their audience as: \"{custom_audience}\"\n"
            f"- Infer the appropriate vocabulary level, assumed knowledge, analogy style, and formality from this description.\n"
            f"- Write as if you are speaking directly to this specific group of people.\n"
            f"- Match their cultural references, language complexity, and expectations."
        )
    else:
        audience_key = audience.lower().replace(" ", "_").replace("/", "_")
        audience_profile = AUDIENCE_PROFILES.get(audience_key)
        if audience_profile:
            audience_block = (
                f"AUDIENCE: {audience_profile['label']}\n"
                f"AUDIENCE ADAPTATION RULES:\n"
                f"- Vocabulary: {audience_profile['vocabulary']}\n"
                f"- Assumed Knowledge: {audience_profile['assumed_knowledge']}\n"
                f"- Analogies & References: {audience_profile['analogies']}\n"
                f"- Formality: {audience_profile['formality']}"
            )
        else:
            audience_block = f"AUDIENCE: {audience}\nAdjust vocabulary and complexity to match this audience."

    # ── Resolve Tone Definition ──
    if tone == "custom" and custom_tone:
        tone_block = (
            f"TONE: ✏️ Custom — \"{custom_tone}\"\n"
            f"TONE INSTRUCTIONS:\n"
            f"- The user described the vibe they want as: \"{custom_tone}\"\n"
            f"- Infer the appropriate sentence style, rhetorical devices, emotional stance, and any forbidden elements from this description.\n"
            f"- Fully commit to this voice. Do not water it down or mix in generic narration.\n"
            f"- If the description references a specific creator, podcast, or show, channel that energy."
        )
    else:
        tone_key = tone.lower().replace(" ", "_").replace("/", "_").replace("&", "and") if tone else ""
        tone_def = TONE_DEFINITIONS.get(tone_key)
        if tone_def:
            tone_block = (
                f"TONE: {tone_def['label']}\n"
                f"TONE INSTRUCTIONS:\n"
                f"- Sentence Style: {tone_def['sentence_style']}\n"
                f"- Rhetorical Devices: {tone_def['rhetorical_devices']}\n"
                f"- Emotional Stance: {tone_def['emotional_stance']}\n"
                f"- FORBIDDEN: {tone_def['forbidden']}"
            )
        elif tone:
            tone_block = f"TONE: {tone}\nAdapt your writing style to match this tone."
        elif style_guide:
            tone_block = "TONE: Match the Style Guide exactly."
        else:
            tone_block = "TONE: As appropriate for the template."

    # ── Resolve Focus (prioritization filter) ──
    focus_block = ""
    if focus:
        focus_block = (
            f"\n═══════ FOCUS LENS ═══════\n"
            f"PRIMARY FOCUS: {focus}\n"
            f"FOCUS INSTRUCTIONS:\n"
            f"- This is your PRIMARY LENS. Every section of the script must connect back to this focus angle.\n"
            f"- When you have multiple facts to choose from, ALWAYS prioritize the ones most relevant to this focus.\n"
            f"- Your hook, your climax, and your conclusion must all directly address this focus.\n"
            f"- If a fact from the dossier doesn't relate to this focus, either skip it or briefly mention it and move on.\n"
        )

    # ── Resolve Viewer Outcome (ending engineer) ──
    outcome_block = ""
    if viewer_outcome and viewer_outcome in VIEWER_OUTCOMES:
        outcome = VIEWER_OUTCOMES[viewer_outcome]
        outcome_block = (
            f"\n═══════ DESIRED VIEWER OUTCOME ═══════\n"
            f"ENDING GOAL: {outcome['label']}\n"
            f"ENDING INSTRUCTIONS: {outcome['instruction']}\n"
            f"The ENTIRE script must build toward this ending. Every act should subtly set up the final payoff.\n"
        )

    # ── Resolve Pacing Intent ──
    pacing_block = ""
    if pacing_instruction:
        pacing_block = f"\nPACING INTENT: {pacing_instruction}"
    if short_form_block:
        pacing_block += short_form_block

    # ── Handle Style Guide (clone vs blend) ──
    system_prompt = sc['system_prompt']
    style_section = ""
    
    if style_guide:
        if style_blend_mode == "blend":
            # BLEND MODE: Style Guide → structure/pacing only. User's tone + audience stay active.
            system_prompt = (
                "You are a versatile scriptwriter. "
                "You have TWO sources of creative direction and must use BOTH:\n\n"
                "SOURCE 1 — STYLE GUIDE (from a reference transcript):\n"
                "- Use it for: STRUCTURE, PACING, HOOK STYLE, SCENE TRANSITIONS, SENTENCE RHYTHM\n"
                "- This tells you HOW to organize and pace the script\n\n"
                "SOURCE 2 — USER'S SELECTED SETTINGS (Tone, Audience, Viewer Outcome):\n"
                "- Use them for: EMOTIONAL STANCE, VOCABULARY LEVEL, RHETORICAL DEVICES, ENDING STRATEGY\n"
                "- These tell you HOW to write and WHO you're speaking to\n\n"
                "PRIORITY RULES:\n"
                "- If the Style Guide says 'fast paced, punchy sentences' → FOLLOW that pacing\n"
                "- If the User's Tone says 'Sarcastic / Villain Energy' → FOLLOW that emotional layer\n"
                "- If the User's Audience says 'use pop culture references' → FOLLOW that vocabulary\n"
                "- Structure comes from the Style Guide. Voice comes from the User's settings.\n"
            )
            style_section = f"\n═══════ STYLE GUIDE (USE FOR STRUCTURE & PACING) ═══════\n{style_guide}\n"
        else:
            # CLONE MODE (default): Style Guide overrides everything. Pure imitation.
            system_prompt = (
                "You are a chameleon scriptwriter. "
                "Your goal is to replicate the EXACT style, tone, and structure of a specific YouTube creator "
                "based on the provided Style Guide, while using the Research Dossier for factual content.\n\n"
                "CRITICAL RULES:\n"
                "- IGNORE the default template tone if it conflicts with the Style Guide\n"
                "- ADOPT the vocabulary, pacing, and hook style defined below\n"
            )
            style_section = f"\n═══════ CUSTOM STYLE GUIDE (MIMIC THIS) ═══════\n{style_guide}\n"
            # In clone mode, suppress the user's tone and audience blocks
            audience_block = "AUDIENCE: As defined by the Style Guide"
            tone_block = "TONE: Match the Style Guide exactly."
    
    title_instruction = ""
    title_format = '"title": "Compelling video title"'
    if selected_title:
        title_instruction = f"VIDEO TITLE (USE EXACTLY): {selected_title}"
        title_format = f'"title": "{selected_title}"'

    # When a structured research object is available, append its CLAIMS + SOURCES
    # block under the dossier. The block gives the model stable [sN] citation handles.
    structured_block = _format_structured_claims_block(structured) if structured else ""
    if structured_block:
        system_prompt = (
            system_prompt.rstrip() +
            "\n\nWhen a claim comes from the research, reference the source id inline like [s3]."
        )

    # When a Narrative Spine is available, inject it after the structured block.
    # The spine pre-ranks claims and defines the narrative order, so the model can
    # bind each beat to specific [kN] ids instead of inventing structure from scratch.
    spine_block = _format_spine_block(spine) if spine else ""
    if spine_block:
        system_prompt = (
            system_prompt.rstrip() +
            "\n\nA Narrative Spine has been provided below. Each beat MUST cite the spine "
            "claim ids it covers via a `claim_ids` field. Every PRIMARY claim must appear "
            "in at least one beat. Follow the logical_flow order unless a stronger creative "
            "case justifies reordering."
        )
        # Spine-aware beats include claim_ids; legacy path omits it.
        beat_schema_extra = ',\n      "claim_ids": ["k1", "k4"]'
        sources_field = '"claim_ids_used": ["k1", "k2", "k3"]'
    else:
        beat_schema_extra = ""
        sources_field = '"sources_used": ["source1", "source2"]'

    prompt = f"""{system_prompt}

═══════ ASSIGNMENT ═══════
TOPIC: {topic}
LENGTH: {duration_minutes} minutes (~{total_words} words of narration){pacing_block}
{audience_block}
{tone_block}
{title_instruction}

═══════ RESEARCH DOSSIER ═══════
{research_dossier}
{structured_block}{spine_block}{style_section}{focus_block}{outcome_block}
═══════ STORY STRUCTURE (SCAFFOLDING) ═══════
{acts_text}

═══════ REQUIREMENTS ═══════
- Target approximately {total_words} words of narration (for {duration_minutes} minutes at natural speaking pace)
- Required emotional beats: {emo_text}
- Hook types to choose from: {', '.join(structure['hook_types'])}
- Every fact, name, number must come from the research above
- NO placeholder text — be specific
- Write ONLY the narration — the words a narrator would speak
- CRITICAL DIRECTING RULE: Do NOT just blindly copy the basic beat names from the Story Structure above. You are the Director. Invent your own highly specific, active, and cinematic beats that perfectly match the actual facts in the dossier. (e.g. Instead of a beat called "The Hook", name your beat something active like "Cold Open: The Paradox of X")
- Organize into Acts, but you dictate the exact dynamic beats.

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
      "text": "The full narration text for this beat. Write it as flowing prose — as many sentences as needed to fill the beat's share of the total duration. Be compelling, specific, and vivid. Use facts from the research dossier."{beat_schema_extra}
    }},
    {{
      "act": "ACT 1",
      "beat": "Context / Stakes",
      "text": "The narration for this beat..."{beat_schema_extra}
    }}
  ],
  {sources_field}
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
                                    duration_minutes: int = 10,
                                    structured: dict = None,
                                    spine: dict = None) -> str:
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
    target_claim_ids_per_beat = []
    context_text = ""
    for i, beat in enumerate(context_beats):
        real_idx = min_idx + i
        is_target = real_idx in target_beat_indices
        marker = " <<<TARGET>>>" if is_target else ""
        claim_tag = ""
        beat_claims = beat.get("claim_ids") or []
        if spine and beat_claims:
            claim_tag = f" | Claims: [{', '.join(beat_claims)}]"
        entry = (
            f"[Beat {real_idx}] Act: {beat.get('act', '')} | "
            f"Beat: {beat.get('beat', '')}{claim_tag}{marker}\n"
            f"{beat.get('text', beat.get('narration', ''))}\n"
        )
        context_text += entry + "\n"
        if is_target:
            target_text += entry + "\n"
            target_claim_ids_per_beat.append(beat_claims)

    # When a spine is available, feed the spine block instead of a truncated
    # dossier excerpt — this anchors regenerated beats to the same ranked claims
    # as the originals and prevents fact drift across regenerations.
    spine_block = _format_spine_block(spine) if spine else ""
    if spine_block:
        dossier_section = ""  # spine replaces dossier as the source-of-truth in regen
    else:
        # Legacy path: truncate dossier to keep prompt reasonable.
        dossier_excerpt = research_dossier[:4000]
        dossier_section = (
            "═══════ RESEARCH DOSSIER (for reference) ═══════\n"
            f"{dossier_excerpt}\n"
        )

    # Append structured claims/sources block when available so the regenerated
    # beat can cite the same source ids as the original script.
    structured_block = _format_structured_claims_block(structured, max_claims=25, max_sources=20) if structured else ""

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

    if spine_block:
        if mode == "restyle":
            spine_rule = (
                "- CLAIM ANCHOR: Each regenerated beat MUST carry the SAME claim_ids "
                "as its original (set equality). The facts come from those exact spine claims; "
                "only phrasing and structure may change."
            )
        else:
            spine_rule = (
                "- CLAIM ANCHOR: Each regenerated beat MUST cite spine claim_ids only. "
                "Pick claims of equal or higher importance than the originals. Do NOT cite ids that don't exist in the spine."
            )
        beat_schema_extra = ', "claim_ids": ["k1", "k4"]'
    else:
        spine_rule = ""
        beat_schema_extra = ""

    prompt = f"""You are a scriptwriter editing a narration for a YouTube video.

TOPIC: {topic}
TEMPLATE: {template_name}
AUDIENCE: {audience}
TONE: {tone or 'Match the surrounding beats'}
VIDEO LENGTH: {duration_minutes} minutes

{mode_instruction}

{dossier_section}{structured_block}{spine_block}═══════ SURROUNDING CONTEXT (for flow) ═══════
{context_text}

═══════ BEATS TO REGENERATE ═══════
{target_text}

═══════ REQUIREMENTS ═══════
- Return ONLY the regenerated beats (not the surrounding context)
- Each beat must flow naturally from the beat before it and into the beat after it
- Maintain approximately the same word count per beat (±20%)
- Every fact must come from the research above
- Write as spoken narration — compelling, vivid, conversational
- Return {len(target_beat_indices)} beat(s)
{spine_rule}

═══════ OUTPUT FORMAT ═══════
Return a JSON array:
[
  {{"act": "ACT NAME", "beat": "Beat Name", "text": "The regenerated narration text..."{beat_schema_extra}}},
  ...
]

Return ONLY the JSON array. Begin."""

    return prompt


# ═══════════════════════════════════════════════════════════════════
#  PHASE 3: PRODUCTION TABLE
# ═══════════════════════════════════════════════════════════════════

# Speech pacing constant
WORDS_PER_SECOND = 2.5

# Pacing instructions per tier (used by both single-call and 3-phase pipeline)
PACING_INSTRUCTIONS = {
    "Meditative": (
        "PACING TARGET: ~6-8 seconds per shot.\n"
        "CRITICAL CUTTING RULE: Do NOT cut frequently. Let the narrator speak full, multi-sentence paragraphs "
        "over a single, highly-detailed, evolving visual. Combine smaller beats into single, long-held shots. "
        "Focus the visual prompts on deep atmosphere and mood rather than rapid action."
    ),
    "Relaxed": (
        "PACING TARGET: ~4-6 seconds per shot.\n"
        "CRITICAL CUTTING RULE: Use longer takes. Allow for complete thoughts to finish before cutting to a new visual. "
        "Prioritize smooth narrative flow over frequent angle changes."
    ),
    "Standard": (
        "PACING TARGET: ~3-4 seconds per shot.\n"
        "CRITICAL CUTTING RULE: Use standard documentary or cinematic pacing. Cut when sentences end or when "
        "the visual subject matter clearly shifts."
    ),
    "High Energy": (
        "PACING TARGET: ~2 seconds per shot.\n"
        "CRITICAL CUTTING RULE: Keep the pacing fast. Cut often, even mid-paragraph, if there is a natural pause "
        "or a shift in the tone. Use varied camera angles to keep the visual momentum high."
    ),
    "Frenetic": (
        "PACING TARGET: ~1-2 seconds per shot.\n"
        "CRITICAL CUTTING RULE: You must perform frequent micro-cuts *within* single sentences. To do this, "
        "break long sentences into smaller text fragments across multiple shots. Keep visuals rapidly evolving "
        "even if the core subject remains the same. Do not worry about strict physical continuity between "
        "every micro-shot; focus on dynamic, montage-style visual energy."
    )
}

# Words per shot target for each pacing tier
WORDS_PER_SHOT_TARGETS = {
    "Meditative": 15,
    "Relaxed": 11,
    "Standard": 9,
    "High Energy": 5,
    "Frenetic": 3
}

# Default cinematic prompt schema (used when no style analysis is provided)
DEFAULT_PROMPT_SCHEMA = {
    "always_include": ["shot_size", "subject", "expression", "wardrobe", "arrangement", "background", "photography", "mood"],
    "include": ["lighting", "lighting_direction", "camera_lens", "camera_aperture",
                 "dof", "film_stock", "color_restriction", "output_style",
                 "room_objects", "made_out_of"],
    "exclude": [],
}

# Maps schema field keys to prompt bracket instructions
_FIELD_TO_PROMPT = {
    "shot_size":           ("SHOT SIZE: [Framing: Close-up/Wide-shot/Medium-shot/Macro]", "Framing: Close-up/Wide-shot/Medium-shot/Macro"),
    "subject":             ("SUBJECT CORE: [Age, gender, body type, and overall character archetype]", "Age, gender, body type, and overall character archetype"),
    "expression":          ("FACIAL EXPRESSION: [Eyes, Mouth, Brows, Overall Energy]", "Highly granular breakdown of the character's acting/emotion (e.g. 'Doe eyes looking up, soft pout, faux innocent energy')"),
    "wardrobe":            ("WARDROBE & FIT: [Specific clothing items, materials, and EXACTLY how they fit/drape]", "Specific clothing items, materials, and EXACTLY how they fit/drape on the character"),
    "arrangement":         ("POSE/ACTION & RELATIONSHIPS: [Body language, posture, and spatial relationship to camera/environment]", "Body language, posture, and spatial relationship to camera/environment"),
    "background":          ("ENVIRONMENT DIORAMA: [Specific scene elements, time of day, and set dressing]", "Specific scene elements, time of day, and set dressing"),
    "photography":         ("CAMERA/PHOTOGRAPHY STYLE: [The philosophy of the shot (e.g., Casual iPhone selfie, Gritty documentary, Slick Hollywood cinematic)]", "The philosophy of the shot (e.g., 'Casual iPhone selfie', 'Gritty documentary', 'Slick Hollywood cinematic')"),
    "mood":                ("VIBE/ENERGY: [The contrast, the core emotion, the psychological weight]", "The 'whole game' of the shot — the contrast, the core emotion, the psychological weight"),
    
    # Technical fields (used only if photography style demands it)
    "lighting":            ("LIGHTING SOURCE & QUALITY: [Sunlight/Artificial/Mixed, and Hard/Soft/Diffused]", "Sunlight/Artificial/Mixed, and Hard/Soft/Diffused"),
    "lighting_direction":  ("LIGHTING DIRECTION & COLOR TEMP: [Top-down/Backlit/etc, and Warm/Cool/Neutral]", "Top-down/Backlit/etc, and Warm/Cool/Neutral"),
    "camera_lens":         ("LENS FX: [Specific lens distortions, focal length, or depth of field]", "Specific lens distortions, focal length, or depth of field"),
    "camera_aperture":     ("APERTURE: [f-stop]", "e.g., f/1.4, f/2.8, f/8"),
    "dof":                 ("DEPTH OF FIELD: [Shallow (blurry background) vs Deep (everything in focus)]", "Shallow (blurry background) vs Deep (everything in focus)"),
    "film_stock":          ("TEXTURE/IMPERFECTIONS: [Film grain, digital noise, dust, scratches, brush strokes]", "Film grain, digital noise, dust, scratches, brush strokes"),
    "color_restriction":   ("COLOR PALETTE: [Dominant colors, accents, and contrast logic]", "Dominant colors, accents, and contrast logic"),
    "output_style":        ("OUTPUT AESTHETIC: [Overall rendering pipeline (2D vector, Photoreal, 3D Render)]", "Overall rendering pipeline (2D vector, Photoreal, 3D Render)"),
    "room_objects":        ("PROMINENT OBJECTS: [Key items in Foreground/Background]", "Key items in Foreground/Background"),
    "made_out_of":         ("MATERIAL COMPOSITION: [Wood/Plastic/Skin/Fabric/etc]", "Wood/Plastic/Skin/Fabric/etc"),
    "tags":                ("AESTHETIC TAGS: [Keyword descriptors for the overall feel]", "Keyword descriptors for the overall feel"),
}


def _build_character_section(intent: dict) -> str:
    """Build the dual-layer rendering identity section (character + optional environment)."""
    character_desc = intent.get('character_description', '')
    environment_desc = intent.get('environment_description', '')
    rendering_split = intent.get('rendering_split', 'unified')

    if not character_desc and not environment_desc:
        return ""

    section = ""

    if character_desc:
        section += f"""
⚠️⚠️⚠️ CHARACTER RENDERING IDENTITY (MANDATORY) ⚠️⚠️⚠️
ALL characters in EVERY prompt MUST be described using this template:
"{character_desc}"

STRICT RULES:
- Do NOT use generic human terms like "man", "woman", "person", "young man", "elderly male", "girl", "boy".
- EVERY time a character appears in a prompt, describe them using the character rendering style above.
- If the narration says "a man walks in", write the CHARACTER DESCRIPTION walking in, NOT "a man walking in".
- Differentiate characters by clothing color, accessories, or size — NOT by realistic facial features.
- The character description defines the RENDERING STYLE. The narration defines WHAT THEY DO and WHERE."""

    if environment_desc and rendering_split == 'hybrid':
        char_short = character_desc[:80] if character_desc else 'the character style'
        section += f"""

⚠️⚠️⚠️ ENVIRONMENT RENDERING IDENTITY (MANDATORY — HYBRID STYLE) ⚠️⚠️⚠️
Environments and backgrounds MUST be rendered using this approach:
"{environment_desc}"

CRITICAL — DUAL-LAYER RENDERING RULES:
- Characters are rendered in ONE style (above) and environments in ANOTHER style (this section).
- Technical camera fields (APERTURE, DOF, LIGHTING) apply to the ENVIRONMENT/BACKGROUND, not to the character rendering.
- When writing APERTURE, DOF, LENS — describe how the ENVIRONMENT looks through that lens, not the character.
- The character exists IN the environment but is rendered as: {char_short}...
- Example: "APERTURE: f/2.8 — shallow depth of field on the background cityscape behind the stick figure"
- Example: "LIGHTING: Warm golden hour sunlight illuminating the detailed environment; the stick figure character is rendered with flat lighting as per character style"
- DO NOT apply photorealistic skin, fabric textures, or camera-specific rendering to the characters.
- DO NOT apply flat/minimalist rendering to the environments.
- Think of it like a 2D animated character composited into a richly rendered background."""
    elif environment_desc:
        section += f"""

ENVIRONMENT RENDERING:
Environments and backgrounds should be rendered as: "{environment_desc}"
Environments are rendered in the SAME overall visual style as the characters."""

    return section


def _build_cast_section(cast: dict, context: str = "storyboard") -> str:
    """Build a cast definition section for injection into prompts.

    Args:
        cast: Cast data dict {has_characters, cast: [{name, role, visual_identity, appears_in_beats, notes}]}
        context: 'storyboard' or 'dp' — controls instruction phrasing
    """
    if not cast or not cast.get('has_characters') or not cast.get('cast'):
        return ""

    cast_list = cast['cast']
    if not cast_list:
        return ""

    cast_entries = []
    for i, char in enumerate(cast_list, 1):
        name = char.get('name', f'Character {i}')
        role = char.get('role', 'Unspecified')
        visual = char.get('visual_identity', 'No visual identity defined')
        beats = char.get('appears_in_beats', [])
        notes = char.get('notes', '')
        beats_str = ', '.join(str(b) for b in beats) if isinstance(beats, list) else str(beats)

        entry = f"""  {i}. "{name}"
     Role: {role}
     Visual Identity: {visual}
     Appears in beats: {beats_str or 'various'}"""
        if notes:
            entry += f"\n     Notes: {notes}"
        cast_entries.append(entry)

    cast_text = "\n".join(cast_entries)

    if context == "storyboard":
        instructions = """USE THIS CAST LIST when designing each shot:
- When a character from the cast appears in a shot, reference them BY NAME.
- Use their "Visual Identity" to inform the "character_outfit" field.
- Each cast member must be VISUALLY CONSISTENT across all shots they appear in.
- If the wardrobe mode is "story_driven", the Visual Identity is the DEFAULT —
  you may deviate when the story demands it, but note WHY in continuity notes.
- If the wardrobe mode is "locked", the Visual Identity is FIXED — do not deviate."""
    else:  # dp
        instructions = """USE THIS CAST LIST when writing prompts:
- When a character from the cast appears, use their Visual Identity in the SUBJECT CORE field.
- Each cast member must look IDENTICAL across all shots — same visual features, same distinguishing elements.
- Combine the Character Rendering style (how to render) with the Cast Visual Identity (who to render)."""

    return f"""
═══════ CAST OF CHARACTERS ═══════
The following characters have been defined for this production.
{instructions}

{cast_text}
"""


def _build_creative_direction_section(creative_direction: dict, agent_role: str) -> str:
    """Build a creative direction preamble tailored to each agent's role.

    Args:
        creative_direction: The expanded creative direction dict
        agent_role: One of 'script_doctor', 'director', 'cinematographer', 'storyboard', 'continuity_supervisor', 'dp', 'combined'
    Returns:
        Prompt section string, or empty string if creative_direction is None.
    """
    if not creative_direction:
        return ""

    summary = creative_direction.get('direction_summary', '')
    video_format = creative_direction.get('video_format', '')
    visual_language = creative_direction.get('visual_language', '')
    narrative_approach = creative_direction.get('narrative_approach', '')
    pacing_philosophy = creative_direction.get('pacing_philosophy', '')
    world_building = creative_direction.get('world_building', '')
    character_approach = creative_direction.get('character_approach', '')
    tone_and_feel = creative_direction.get('tone_and_feel', '')

    # Common header
    section = f"""
═══════ CREATIVE DIRECTION (MANDATORY) ═══════
This video has a specific creative vision. ALL decisions must serve this direction:
"{summary}"

Video Format: {video_format}
Tone & Feel: {tone_and_feel}
"""

    if agent_role == 'script_doctor':
        section += f"""
YOUR VISUAL BRIEF must capture the creative essence of this direction:
- Visual Language: {visual_language}
- Narrative Approach: {narrative_approach}
- Tone & Feel: {tone_and_feel}
- Let these inform your metaphors, mood tags, and color suggestions.
"""
    elif agent_role == 'director':
        section += f"""
YOUR EDITORIAL DECISIONS must reflect this creative vision:
- Narrative Approach: {narrative_approach}
- Pacing Philosophy: {pacing_philosophy}
- When deciding WHERE to cut: consider the "{video_format}" format.
  For example, if this is an "explainer," cut at idea boundaries.
  If this is a "documentary," allow longer observational shots.
- Match your cutting rationale and camera_intent to the tone: "{tone_and_feel}"
"""
    elif agent_role == 'cinematographer':
        section += f"""
YOUR CAMERA TECHNIQUE must reflect this creative vision:
- Video Format: {video_format} — this affects camera language choices.
  Documentaries use more handheld and eye-level. Explainers use more static and structured.
- Pacing Philosophy: {pacing_philosophy}
- Tone & Feel: {tone_and_feel} — match your lighting_mood and lens_feel choices to this.
"""
    elif agent_role == 'storyboard':
        section += f"""
YOUR VISUAL COMPOSITIONS must reflect this creative vision:
- Visual Language: {visual_language}
- World Building: {world_building}
- Character Approach: {character_approach}
- When designing what each shot SHOWS: think about what a "{video_format}" looks like.
  For example, if this is a "stick figure explainer," scenes should be simple with one focal point.
  If this is a "documentary," scenes should feel observational and grounded.
"""
    elif agent_role == 'continuity_supervisor':
        section += f"""
VERIFY that the shot list maintains consistency with this creative vision:
- Visual Language: {visual_language}
- Tone & Feel: {tone_and_feel}
- Flag any shots that deviate from the approved creative direction.
"""
    elif agent_role in ('dp', 'combined'):
        section += f"""
YOUR PROMPTS must produce imagery consistent with this creative vision:
- Visual Language: {visual_language}
- World Building: {world_building}
- Character Approach: {character_approach}
- Narrative Approach: {narrative_approach}
- Every prompt should look like it belongs in a "{video_format}".
- The overall feel should be: {tone_and_feel}
"""

    return section


def _build_prompt_format_instructions(schema: dict, aspect_ratio: str,
                                      character_description: str = "",
                                      style_summary: str = "",
                                      environment_description: str = "",
                                      rendering_split: str = "unified") -> str:
    """
    Build the PROMPT FORMATS section dynamically based on the approved schema.
    Only includes fields that are in always_include + include, and explicitly
    tells the AI NOT to use excluded fields.

    When character_description is provided, the SUBJECT CORE field is overridden
    to embed the character rendering identity directly, preventing Gemini from
    defaulting to realistic human descriptions.

    When style_summary is provided, the OUTPUT AESTHETIC field is overridden
    to embed the actual style instead of letting Gemini default to "Photoreal".

    When rendering_split is "hybrid", environment-only fields (camera_aperture,
    dof, etc.) are annotated with "apply to ENVIRONMENT only" instructions.
    """
    always = schema.get("always_include", [])
    include = schema.get("include", [])
    exclude = schema.get("exclude", [])
    active_fields = always + include

    # Build field overrides based on style context
    field_overrides = {}
    if character_description:
        field_overrides["subject"] = (
            f"SUBJECT CORE: [{character_description} — differentiate characters by clothing color, accessories, or size ONLY. Do NOT use 'man', 'woman', 'person', or any realistic human descriptors]",
            f"Character rendered as: {character_description}"
        )
    if style_summary:
        field_overrides["output_style"] = (
            f"OUTPUT AESTHETIC: [{style_summary}]",
            f"Rendering style: {style_summary}"
        )

    # For hybrid styles, annotate environment-only fields so Gemini knows
    # these apply to the background, not the character rendering
    if rendering_split == 'hybrid' and environment_description:
        env_only_fields = ["camera_aperture", "dof", "camera_lens", "film_stock",
                           "lighting", "lighting_direction"]
        for field in env_only_fields:
            if field in active_fields and field not in field_overrides:
                if field in _FIELD_TO_PROMPT:
                    orig_bracket, orig_desc = _FIELD_TO_PROMPT[field]
                    label = orig_bracket.split(':')[0].strip()
                    field_overrides[field] = (
                        f"{label}: [ENVIRONMENT ONLY — describe how the background/environment looks, NOT the 2D character. {orig_desc}]",
                        f"{orig_desc} (environment layer only in hybrid style)"
                    )

    # Build first frame template lines
    first_frame_lines = []
    for field in active_fields:
        if field in field_overrides:
            bracket, _ = field_overrides[field]
            first_frame_lines.append(bracket)
        elif field in _FIELD_TO_PROMPT:
            bracket, _ = _FIELD_TO_PROMPT[field]
            first_frame_lines.append(bracket)

    first_frame_template = "\n".join(first_frame_lines)
    first_frame_template += f"\nASPECT RATIO: [{aspect_ratio}]"
    first_frame_template += "\n--\nExclude: [specific exclusions for this scene]"

    # Build last frame template (mirrors first frame with END state)
    last_frame_lines = []
    for field in active_fields:
        # Use overrides if available, otherwise default field definitions
        if field in field_overrides:
            bracket, _ = field_overrides[field]
        elif field in _FIELD_TO_PROMPT:
            bracket, _ = _FIELD_TO_PROMPT[field]
        else:
            continue
        label = bracket.split(':')[0].strip()

        if field == "arrangement":
            last_frame_lines.append(f"{label}: [END POSE/ACTION]")
        elif field == "expression":
            last_frame_lines.append(f"{label}: [END FACIAL EXPRESSION]")
        elif field in ("subject", "wardrobe", "background", "photography", "lighting", "lighting_direction",
                       "color_restriction", "output_style", "film_stock", "mood"):
            last_frame_lines.append(f"{label}: [SAME AS FIRST FRAME]")
        else:
            last_frame_lines.append(bracket)

    last_frame_template = "\n".join(last_frame_lines)
    last_frame_template += f"\nASPECT RATIO: [{aspect_ratio}]"
    last_frame_template += "\n--\nExclude: [specific exclusions]"

    # Build Veo template
    subject_hint = f"[character described using: {character_description[:80]}...]" if character_description else "[subject]"
    veo_lines = [f"[Shot size] of {subject_hint} [TRANSITIONAL ACTION — what happens between first and last frame] in [background]."]
    if "lighting" in active_fields or "lighting_direction" in active_fields:
        veo_lines.append("Lighting: [conditions, any changes].")
    veo_lines.append("Camera: [movement type, speed, motivation].")
    veo_lines.append("Audio: [ambient], [SFX], [dialogue if any].")
    if "output_style" in active_fields:
        style_hint = f"Style: {style_summary}." if style_summary else "Style: [aesthetic reference]."
        veo_lines.append(style_hint)
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
        if field in field_overrides:
            _, desc = field_overrides[field]
            field_guide_lines.append(f"  - {field}: {desc}")
        elif field in _FIELD_TO_PROMPT:
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
                            aspect_ratio: str = "16:9",
                            shot_start_number: int = 1,
                            pacing_tier: str = "Standard",
                            creative_direction: dict = None,
                            format_preset: str = "",
                            spine: dict = None) -> str:
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
        shot_start_number: The number to start shot numbering from (important for batching)
        pacing_tier: Pacing speed (Meditative, Relaxed, Standard, High Energy, Frenetic)
        format_preset: Format preset ID (micro, quick_take, short_form, standard, deep_dive)
        spine: Optional Narrative Spine — when present, each shot will carry a
            `claim_id` so source citations propagate to visuals.
    """
    # Extract narration beats
    beats = narration_json.get("narration", [])
    title = narration_json.get("title", "Untitled")
    hook_type = narration_json.get("hook_type", "")

    # Format narration beats for the prompt — append claim_ids when spine is in play
    narration_text = ""
    for i, beat in enumerate(beats):
        act = beat.get("act", "")
        beat_name = beat.get("beat", "")
        text = beat.get("text", beat.get("narration", ""))
        claim_tag = ""
        if spine:
            beat_claims = beat.get("claim_ids") or []
            if beat_claims:
                claim_tag = f" | Claims: [{', '.join(beat_claims)}]"
        narration_text += f"\n[BEAT {i+1}] Act: {act} | Beat: {beat_name}{claim_tag}\n{text}\n"

    # Use module-level pacing constants
    total_words = sum(len(b.get("text", b.get("narration", "")).split()) for b in beats)
    pacing_instruction = PACING_INSTRUCTIONS.get(pacing_tier, PACING_INSTRUCTIONS["Standard"])
    WORDS_PER_SHOT_TARGET = WORDS_PER_SHOT_TARGETS.get(pacing_tier, 9)

    estimated_shots = max(1, int(total_words / WORDS_PER_SHOT_TARGET))

    # Apply shot range cap from format preset
    if format_preset and format_preset in FORMAT_PRESETS:
        shot_range = FORMAT_PRESETS[format_preset].get("shot_range")
        if shot_range:
            min_shots, max_shots = shot_range
            estimated_shots = max(min_shots, min(max_shots, estimated_shots))

    # Build short-form cutting instruction
    short_form_cutting = ""
    if format_preset in ("micro", "quick_take"):
        sr = FORMAT_PRESETS[format_preset].get("shot_range", (4, 20))
        short_form_cutting = (
            f"\n⚠️ SHORT-FORM VIDEO — SHOT COUNT IS CRITICAL ⚠️\n"
            f"This is a {format_preset.replace('_', ' ')} video ({duration_minutes} min).\n"
            f"You MUST produce between {sr[0]} and {sr[1]} shots total.\n"
            f"- Do NOT over-split beats. Each shot should carry a complete visual idea.\n"
            f"- Prefer 4s shots for micro content, mix 4s/6s for quick_take.\n"
            f"- Every shot must be visually distinct — no redundant angles of the same subject.\n"
            f"- For micro: 1 beat = 1-2 shots max. For quick_take: 1 beat = 2-3 shots max.\n"
        )

    # Build visual style section from structured style analysis
    if style_analysis and isinstance(style_analysis, dict):
        intent = style_analysis.get("style_intent", {})
        schema = style_analysis.get("prompt_schema", DEFAULT_PROMPT_SCHEMA)
        style_summary = style_analysis.get("style_summary", "Custom style")

        character_section = _build_character_section(intent)
        env_desc = intent.get('environment_description', '')
        rendering_split = intent.get('rendering_split', 'unified')

        visual_style_section = f"""═══════ VISUAL STYLE & CREATIVE DIRECTION ═══════
⚠️ READ THIS SECTION CAREFULLY — IT CONTROLS HOW EVERY PROMPT IS WRITTEN ⚠️

MASTER STYLE: {style_summary}
Rendering Mode: {"HYBRID — characters and environments use DIFFERENT rendering" if rendering_split == "hybrid" else "UNIFIED — same rendering for everything"}

CHARACTER RENDERING: {intent.get('character_description', 'Standard')}
ENVIRONMENT RENDERING: {env_desc or 'Same as character rendering'}

Detail Level: {intent.get('detail_level', 'Standard')}
Scene Complexity: {intent.get('scene_complexity', 'Standard')}
Camera Language: {intent.get('camera_language', 'Standard cinematography')}
Lighting Approach: {intent.get('lighting_instruction', 'As appropriate')}
Subject Framing: {intent.get('subject_framing', 'Varied')}
Writing Style: {intent.get('writing_style', 'Descriptive')}
Color Palette: {intent.get('color_palette', 'As appropriate')}
Texture: {intent.get('texture', 'As appropriate')}
Default Mood: {intent.get('mood_default', 'As appropriate')}
{character_section}
⚠️ CRITICAL STYLE RULES:
- MATCH the style description above in EVERY prompt you write.
- If Detail Level is 'Minimalist', character descriptions should be short.{" Environment descriptions can still be rich because this is HYBRID mode." if rendering_split == "hybrid" else " Do NOT add cinematic details."}
- If Scene Complexity is 'Empty Backgrounds', do NOT describe detailed environments.
- If Writing Style is 'Concise', use short direct sentences. No flowery language.
- Do NOT hallucinate details that contradict the style (e.g., don't add '4k photorealistic' to a cartoon style).
- Follow the Camera Language instructions — if it says 'simple flat framing', do NOT use lens mm or DOF.
{"" if rendering_split != "hybrid" else f'''
⚠️ HYBRID RENDERING MODE — DUAL-LAYER RULES (CRITICAL):
- Characters: Use the CHARACTER RENDERING description above. Keep character rendering minimalist/simple.
- Environments: Use the ENVIRONMENT RENDERING description above. Environments CAN be detailed/cinematic.
- Technical camera fields (APERTURE, DOF, LIGHTING) describe the ENVIRONMENT, not the character.
- DO NOT write: "gritty documentary footage of a stick figure" or "photorealistic stick figure."
- DO NOT write: "a man standing in..." — ALWAYS use the character rendering template.
- INSTEAD write: "A [character per style] standing in a richly detailed [environment per style]."
- WRONG: "A man in a cinematic alleyway"
- WRONG: "A stick figure in a flat white void" (when environment style says rich/cinematic)
- RIGHT: "A stick figure character with circle head and dot eyes [character style] standing in a moody, rain-slicked alleyway with neon reflections and volumetric fog [environment style]"
'''}
⚠️ STORY SCENE RULES (CRITICAL):
- The style describes HOW CHARACTERS ARE RENDERED, not the scene setting.
- Characters must be placed in STORY-APPROPRIATE ENVIRONMENTS (forests, houses, streets, etc.) — not studio backdrops.
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
    # Pass character_description and style_summary so field templates embed them directly
    character_desc = ""
    env_desc_for_schema = ""
    rendering_split_for_schema = "unified"
    if style_analysis and isinstance(style_analysis, dict):
        intent_for_schema = style_analysis.get("style_intent", {})
        character_desc = intent_for_schema.get("character_description", "")
        env_desc_for_schema = intent_for_schema.get("environment_description", "")
        rendering_split_for_schema = intent_for_schema.get("rendering_split", "unified")
    prompt_formats = _build_prompt_format_instructions(
        schema, aspect_ratio,
        character_description=character_desc,
        style_summary=style_summary,
        environment_description=env_desc_for_schema,
        rendering_split=rendering_split_for_schema
    )

    # Build creative direction section for combined/fast mode
    creative_direction_section = _build_creative_direction_section(creative_direction, 'combined')

    # Spine block + per-shot claim_id schema additions (legacy single-call path)
    spine_block = _format_spine_block(spine) if spine else ""
    if spine_block:
        prod_claim_field = ',\n      "claim_id": "k1"'
        prod_claim_rule = (
            "\n15. CLAIM PROPAGATION: Every shot MUST carry a `claim_id` chosen from "
            "its parent beat's claim_ids (the [Claims: ...] tag on each [BEAT n] line). "
            "Pick the SINGLE best-fit claim id per shot. If the parent beat has no "
            "claim_ids, omit the field. The claim_id binds each visual to a specific "
            "research source via the spine."
        )
    else:
        prod_claim_field = ""
        prod_claim_rule = ""

    prompt = f"""You are a professional production team creating a VIDEO that tells a STORY:
1. THE DIRECTOR — story, emotion, performance, pacing, editorial decisions
2. THE STORYBOARD ARTIST — visual sequence, composition, shot flow
3. THE DIRECTOR OF PHOTOGRAPHY — camera, lighting, visual style (adapted to the style guide)

Your job has TWO parts:
A) CREATIVELY SPLIT the narration into production shots
B) CREATE production prompts (first-frame, last-frame, Veo 3.1) for each shot — these must depict STORY SCENES, not static character showcases
{creative_direction_section}
═══════ PROJECT INFO ═══════
Title: {title}
Hook Type: {hook_type}
Duration: {duration_minutes} minutes
Total Narration Words: ~{total_words}
Estimated Shots: ~{estimated_shots}
Aspect Ratio: {aspect_ratio}

{visual_style_section}
{spine_block}
═══════ NARRATION TO SPLIT ═══════
⚠️ USE THESE EXACT WORDS — DO NOT REWRITE, PARAPHRASE, OR DROP ANY TEXT ⚠️
{narration_text}

═══════ CREATIVE SCENE CUTTING ═══════

{pacing_instruction}
{short_form_cutting}
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

═══════ PER-SHOT STYLE COMPLIANCE CHECK ═══════
Before writing each shot's prompts, silently verify:
✓ Does the SUBJECT CORE use the character rendering template (not generic "man"/"woman"/"person")?
✓ Does the ENVIRONMENT match the story (not a studio/void unless the story is set there)?
✓ Does the CAMERA/PHOTOGRAPHY STYLE match the style guide (not defaulting to cinematic for a cartoon style)?
{"✓ Are technical camera fields (APERTURE, DOF, LIGHTING) applied to the environment only, not the character? (HYBRID mode)" if style_analysis and isinstance(style_analysis, dict) and style_analysis.get("style_intent", {}).get("rendering_split") == "hybrid" else ""}
✓ Does the overall prompt match the style summary: "{style_summary}"?
If any check fails, REWRITE the prompt before including it in the JSON.

═══════ OUTPUT FORMAT ═══════

Return a JSON object with this EXACT structure:
{{{{
  "title": "{title}",
  "aspect_ratio": "{aspect_ratio}",
  "style_summary": "Brief summary of the visual style applied",
  "total_shots": <number>,
  "shots": [
    {{{{
      "shot_number": "{shot_start_number}",
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
      "veo_prompt": "Full Veo 3.1 video prompt"{prod_claim_field}
    }}}}
  ],
  "continuity_notes": [
    {{{{
      "from_shot": "{shot_start_number}",
      "to_shot": "{shot_start_number + 1}",
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
14. Characters must be ACTING (walking, talking, reacting, holding objects) — NOT posing for display.{prod_claim_rule}

⚠️⚠️⚠️ JSON SYNTAX VALIDATION ⚠️⚠️⚠️
CRITICAL: You MUST generate VALID JSON with correct syntax:
1. Every field MUST end with a comma EXCEPT the last field in an object
2. All string values MUST be properly escaped (use \\" for quotes, \\\\ for backslashes)
3. Do NOT put commas after the last field in an object
4. ALWAYS put a comma after every object in the "shots" array EXCEPT the last one
5. Check your JSON is valid before returning it

Return ONLY the JSON. Begin."""

    return prompt


# ═══════════════════════════════════════════════════════════════════
#  SIX-PHASE PRODUCTION PIPELINE
# ═══════════════════════════════════════════════════════════════════


def build_script_doctor_prompt(narration_json: dict,
                                style_analysis: dict = None,
                                creative_direction: dict = None) -> str:
    """
    Phase 0 of 6: THE SCRIPT DOCTOR — Visual Brief.

    Reads the complete narration and distills a per-beat Visual Brief that serves
    as a shared creative compass for all downstream agents (Director, Cinematographer,
    Storyboard Artist, Continuity Supervisor, DP).

    Returns a prompt string. Output is a JSON Visual Brief.
    """
    beats = narration_json.get("narration", [])
    title = narration_json.get("title", "Untitled")

    # Format narration beats
    narration_text = ""
    for i, beat in enumerate(beats):
        act = beat.get("act", "")
        beat_name = beat.get("beat", "")
        text = beat.get("text", beat.get("narration", ""))
        narration_text += f"\n[BEAT {i+1}] Act: {act} | Beat: {beat_name}\n{text}\n"

    # Build context sections
    creative_direction_section = _build_creative_direction_section(creative_direction, 'script_doctor')

    style_context = ""
    if style_analysis and isinstance(style_analysis, dict):
        summary = style_analysis.get("style_summary", "")
        intent = style_analysis.get("style_intent", {})
        if summary:
            style_context = f"""
═══════ VISUAL STYLE CONTEXT ═══════
The production has an approved visual style: "{summary}"
Character rendering: {intent.get('character_description', 'Not specified')}
Environment rendering: {intent.get('environment_description', 'Not specified')}
Color palette: {intent.get('color_palette', 'Not specified')}
Mood: {intent.get('mood_default', 'Not specified')}
Your Visual Brief should COMPLEMENT this style, not contradict it.
"""

    prompt = f"""You are THE SCRIPT DOCTOR for a visual production. You read the complete narration and distill
a Visual Brief for each beat — a compact creative compass that every downstream specialist
(Director, Cinematographer, Storyboard Artist, Continuity Supervisor, DP) will reference.

Your Visual Brief does NOT describe specific shots, camera angles, or image prompts.
It captures the ESSENCE of each beat: the metaphors it evokes, the mood it carries,
the colors it suggests, the symbolic imagery it implies, and the point of view that
would best serve the storytelling.

Think like a mood board creator, not a cinematographer.
{creative_direction_section}
{style_context}
═══════ PROJECT ═══════
Title: {title}
Total Beats: {len(beats)}

═══════ FULL NARRATION ═══════
Read the ENTIRE narration first. Understand the complete arc before analyzing individual beats.
{narration_text}

═══════ YOUR TASK ═══════

STEP 1 — GLOBAL ANALYSIS (think before you write):
Before briefing individual beats, identify:
- What are the 2-3 RECURRING VISUAL MOTIFS that should thread through the entire piece?
- What is the overall COLOR ARC? (How should the palette evolve from opening to closing?)
- What is the EMOTIONAL THROUGHLINE? (The viewer's journey in 3-5 words)

STEP 2 — PER-BEAT VISUAL BRIEF:
For each beat in the narration, produce a compact brief (50-80 words total per beat):

1. "metaphors": What conceptual metaphors does this text evoke? Use concrete visual analogies.
   NOT film references. NOT "like a Kubrick film." Instead: "Time as erosion — sand wearing stone smooth."

2. "mood_atmosphere": 2-4 mood/atmosphere tags. Use evocative adjectives, not genre labels.
   Good: ["suffocating", "amber-lit", "ancient"]. Bad: ["thriller", "noir", "action"].

3. "color_palette_shift": How should the color feeling shift for this beat relative to the
   beats around it? Describe as a transition or state: "Deep indigo fading to amber" or
   "Stark white — clinical, sterile, blinding."

4. "symbolic_imagery": 1-2 concrete visual symbols that could represent the beat's core idea.
   These are SUGGESTIONS, not requirements. "Hourglass with sand flowing upward; cracked sundial."

5. "suggested_pov": What point of view would best serve this beat's emotional truth?
   "Intimate — as if whispering in the viewer's ear" or "Vast — the viewer is a speck observing."

6. "tone_keywords": 3-5 single-word tone descriptors that should infuse every visual decision
   for this beat. ["haunting", "reverent", "questioning"]

═══════ OUTPUT FORMAT ═══════

Return a JSON object:
{{{{
  "title": "{title}",
  "global_motifs": {{{{
    "recurring_symbols": ["symbol1", "symbol2", "symbol3"],
    "color_arc": "Description of how color evolves across the full piece",
    "emotional_throughline": "3-5 word summary of the viewer's emotional journey"
  }}}},
  "visual_brief": [
    {{{{
      "beat_number": 1,
      "act": "ACT 1",
      "beat": "The Hook",
      "metaphors": "Concrete visual metaphor for this beat's ideas",
      "mood_atmosphere": ["tag1", "tag2", "tag3"],
      "color_palette_shift": "How color shifts for this beat",
      "symbolic_imagery": "1-2 specific visual symbols",
      "suggested_pov": "Ideal perspective for emotional truth",
      "tone_keywords": ["word1", "word2", "word3"]
    }}}}
  ]
}}}}

═══════ RULES ═══════
1. Keep each beat's brief COMPACT — 50-80 words total across all fields. Downstream agents
   need creative direction, not essays.
2. Use mood board language, NOT film references. No "like Blade Runner" or "Spielbergian."
   Instead describe the actual mood: "rain-slicked neon reflections, lonely warmth."
3. Metaphors must be VISUAL and CONCRETE — something that can be drawn or photographed.
4. Color descriptions use natural language, not hex codes: "burnt sienna", "ice blue", "muted sage."
5. The brief must be INTERNALLY CONSISTENT — the global motifs should feel present in each beat.
6. Do NOT describe specific shots, camera angles, or compositions. That is not your job.

⚠️ Return ONLY valid JSON. No commentary. Begin."""

    return prompt


def build_cinematographer_prompt(director_shots: list,
                                  visual_brief: dict = None) -> str:
    """
    Phase 2 of 6: THE CINEMATOGRAPHER — Camera Language.

    Takes the Director's shot list (with camera intent) and the Visual Brief,
    translates intent into specific executable camera techniques from a 62-technique library.

    Does NOT change cuts, timing, or emotion. Does NOT design scene content.
    ONLY specifies HOW the camera sees each shot.
    """
    import json as _json
    formatted_shots = _json.dumps(director_shots, indent=2, ensure_ascii=False)

    # Build visual brief context
    visual_brief_section = ""
    if visual_brief:
        global_motifs = visual_brief.get("global_motifs", {})
        brief_entries = visual_brief.get("visual_brief", [])
        visual_brief_section = f"""═══════ VISUAL BRIEF (SHARED CONTEXT) ═══════
Global Motifs: {global_motifs.get('recurring_symbols', [])}
Color Arc: {global_motifs.get('color_arc', 'Not specified')}
Emotional Throughline: {global_motifs.get('emotional_throughline', 'Not specified')}

Per-beat briefs (use mood_atmosphere and tone_keywords to guide technique selection):
"""
        for entry in brief_entries:
            visual_brief_section += (
                f"  Beat {entry.get('beat_number', '?')}: "
                f"mood={entry.get('mood_atmosphere', [])}, "
                f"tone={entry.get('tone_keywords', [])}, "
                f"pov={entry.get('suggested_pov', 'N/A')}\n"
            )

    prompt = f"""You are THE CINEMATOGRAPHER for a video production. The Director has made all editorial
decisions — cuts, timing, emotion, and camera INTENT for each shot. Your job is to translate
that intent into specific, executable camera language.

You have a vocabulary of 62 techniques across 7 categories. For each shot, you select the
techniques that best serve the Director's intent and the Visual Brief's mood.

You do NOT change the Director's decisions (cuts, timing, script_beat, emotion, intent).
You do NOT design what appears in the shot (that is the Storyboard Artist's job).
You ONLY specify HOW the camera sees it: movement, angle, lens, composition, lighting mood,
depth/focus approach, and any visual storytelling technique.

{visual_brief_section}

═══════ YOUR TECHNIQUE LIBRARY ═══════

CAMERA MOVEMENT:
- Static / locked-off → Stability, contemplation, tension through stillness
- Dolly-in (push) → Building intimacy, approaching revelation, tightening grip
- Dolly-out (pull) → Revealing context, creating distance, expanding perspective
- Tracking shot (lateral) → Following movement, surveying a space, momentum
- Crane up → Elevating from personal to epic, transcendence, liberation
- Crane down → Descending into detail, grounding, focus narrowing
- Steadicam float → Dreamlike movement, fluid immersion, ghost-like observation
- Handheld → Urgency, chaos, raw emotion, immediacy, visceral presence
- Whip pan → Sudden shift, surprise, disorientation, energy burst
- Slow push-in → Dawning realization, creeping tension, subtle dread building
- Orbit / arc → Examining from all angles, heroic presentation, gravitas
- Zoom (optical) → Sudden focus shift, urgency without physical movement
- Tilt up/down → Revealing scale (up) or grounding detail (down)
- Boom shot → Vertical reveal, overhead perspective shift

CAMERA ANGLE:
- Eye level → Neutral, equality, documentary truth, connection
- Low angle → Power, dominance, heroism, threat — subject feels imposing
- High angle → Vulnerability, smallness, judgment — subject feels diminished
- Bird's eye / top-down → Patterns, god-like perspective, omniscience
- Worm's eye → Extreme power, surreal perspective, wonder
- Dutch angle → Unease, instability, psychological disturbance
- Over-the-shoulder → Conversation, confrontation, intimacy
- POV (point of view) → Subjective experience, immersion, total identification
- Profile / side-on → Objectivity, mythology, iconic quality

LENS FEEL:
- Wide-angle (14-24mm) → Expansive environments, epic scale, slight surrealism
- Standard (35-50mm) → Natural perception, documentary, truthful
- Telephoto (85-200mm) → Intimacy, compression, isolation, voyeuristic
- Macro → Texture, detail, small-world discovery
- Fisheye → Surreal distortion, paranoia, warped reality
- Anamorphic → Cinematic width, lens flares, epic scope
- Tilt-shift → Miniature effect, selective focus, toy-like wonder

COMPOSITION:
- Rule of thirds → Balanced, natural, pleasing
- Center frame / symmetry → Power, formality, intensity
- Golden ratio → Organic flow, subconscious harmony
- Leading lines → Directed focus, depth, journey
- Frame-within-frame → Isolation, layers of meaning, voyeurism
- Negative space → Loneliness, weight of emptiness, minimalism
- Foreground framing → Depth, immersion, peering through
- Diagonal composition → Energy, dynamic action, visual excitement
- Layered depth (fg/mg/bg) → Rich world-building, cinematic depth

LIGHTING MOOD:
- High-key → Optimism, clarity, openness, safety
- Low-key → Mystery, drama, tension, hidden information
- Rembrandt → Gravitas, human depth, timelessness
- Split lighting → Duality, moral ambiguity, internal conflict
- Silhouette → Mystery, iconic imagery, universal archetype
- Rim light / backlight → Ethereal glow, separation, otherworldly
- Practical lighting → Realism, warmth, authenticity
- Chiaroscuro → Extreme contrast, theatrical intensity
- Golden hour → Romance, nostalgia, fleeting beauty
- Motivated lighting → Visible source, believable world

VISUAL STORYTELLING:
- Contrast cut → Juxtaposing opposites for shock, irony, commentary
- Match cut → Connecting through visual similarity, continuity
- Visual callback → Repeating earlier composition with variation, payoff
- Reveal → Withholding then showing (pan, dolly, rack focus), surprise
- Conceal → Hiding through framing or obstruction, suspense
- Juxtaposition → Contrasting elements in same frame, tension
- Visual metaphor → Composition representing abstract ideas, subtext

DEPTH & FOCUS:
- Deep focus → Everything sharp, democratic framing, viewer chooses
- Shallow DOF → Isolating subject, romantic feel, laser focus
- Rack focus → Shifting attention fg/bg, dramatic shift, cause-and-effect
- Split diopter → Two planes sharp simultaneously, dual awareness
- Bokeh → Background dissolves to soft light, dreamy, romantic
- Pull focus through layers → Moving through depth planes, discovery

═══════ DIRECTOR'S SHOT LIST ═══════
{formatted_shots}

═══════ YOUR TASK ═══════

STEP 1 — READ THE EMOTIONAL ARC:
Review the Director's "emotional_arc_analysis" and each shot's "camera_intent" and "emotion."
Consider the Visual Brief's mood tags and tone keywords for each beat.

STEP 2 — SELECT TECHNIQUES:
For EACH shot, select techniques from your library. You must specify ALL of:

1. "camera_movement": One primary movement. Must serve the Director's camera_intent.
2. "camera_angle": One angle. Must serve the emotion and dramatic weight.
3. "lens_feel": One lens feel. Must match the intimacy/distance the intent demands.
4. "composition": One primary composition approach. Consider symbolic imagery from the Visual Brief.
5. "lighting_mood": One lighting mood. Must match the Visual Brief's mood_atmosphere tags.
6. "depth_focus": One depth/focus approach. Direct viewer attention appropriately.
7. "visual_storytelling_technique": One technique from Visual Storytelling, OR "none".
   Use sparingly — only 20-30% of shots should have one.

For each selection, include a brief (5-10 word) justification after a dash (—).

═══════ VARIETY RULES (MANDATORY) ═══════

- No MORE than 2 consecutive shots with the same camera_movement
- No MORE than 3 consecutive shots with the same camera_angle
- No MORE than 2 consecutive shots with the same lighting_mood
- The full shot list must use AT LEAST 4 different camera_movements,
  3 different camera_angles, and 3 different lighting_moods
- If the Director's intent is similar across adjacent shots, differentiate through
  lens_feel, composition, or depth_focus instead
- Think about RHYTHM: static-static needs a movement shot to break monotony;
  handheld-handheld needs a locked-off shot for the viewer to breathe

═══════ OUTPUT FORMAT ═══════

Return a JSON object:
{{{{
  "shots": [
    {{{{
      "shot_number": "<from Director>",
      "script_beat": "<from Director>",
      "duration": "<from Director>",
      "act": "<from Director>",
      "beat": "<from Director>",
      "emotion": "<from Director>",
      "directors_intent": "<from Director>",
      "camera_intent": "<from Director>",
      "cutting_rationale": "<from Director>",
      "emotional_arc_position": "<from Director>",

      "camera_movement": "Slow push-in — building toward the revelation",
      "camera_angle": "Eye level — honest, direct connection",
      "lens_feel": "Telephoto compression — isolating subject from chaos",
      "composition": "Center frame — subject commands full attention",
      "lighting_mood": "Low-key — truth lives in shadow",
      "depth_focus": "Shallow DOF — world falls away, only this matters",
      "visual_storytelling_technique": "Reveal — camera movement uncovers what was hidden"
    }}}}
  ]
}}}}

═══════ RULES ═══════
1. CARRY FORWARD every field from the Director's output exactly. Do NOT modify any.
2. Every technique selection must be FROM THE LIBRARY above. Do not invent techniques.
3. Each selection must include a brief justification after the dash (—).
4. Serve the Director's camera_intent — it is your primary constraint.
5. Use the Visual Brief's mood/atmosphere tags as secondary guide for lighting and composition.
6. Think about RHYTHM across the sequence, not just individual shots.

⚠️ Return ONLY valid JSON. No commentary. Begin."""

    return prompt


def build_continuity_supervisor_prompt(storyboard_shots: list,
                                        visual_brief: dict = None) -> str:
    """
    Phase 4 of 6: THE CONTINUITY SUPERVISOR — Quality Review.

    Reviews the complete shot list after Storyboard and auto-fixes:
    shot variety issues, flow problems, color consistency, and continuity errors.
    """
    import json as _json
    formatted_shots = _json.dumps(storyboard_shots, indent=2, ensure_ascii=False)

    # Build visual brief context for color checking
    visual_brief_section = ""
    if visual_brief:
        global_motifs = visual_brief.get("global_motifs", {})
        visual_brief_section = f"""═══════ VISUAL BRIEF (REFERENCE FOR COLOR/MOOD CHECKS) ═══════
Color Arc: {global_motifs.get('color_arc', 'Not specified')}
Emotional Throughline: {global_motifs.get('emotional_throughline', 'Not specified')}
Recurring Symbols: {global_motifs.get('recurring_symbols', [])}
"""
        brief_entries = visual_brief.get("visual_brief", [])
        for entry in brief_entries:
            visual_brief_section += (
                f"  Beat {entry.get('beat_number', '?')}: "
                f"color={entry.get('color_palette_shift', 'N/A')}, "
                f"mood={entry.get('mood_atmosphere', [])}\n"
            )

    prompt = f"""You are THE CONTINUITY SUPERVISOR for a video production. The Director, Cinematographer,
and Storyboard Artist have completed their work. You are the final quality check before
the DP writes generation prompts.

Your job is to review the COMPLETE shot list and flag + auto-fix:
1. SHOT VARIETY issues — repetitive sizes, angles, or movements
2. FLOW problems — jarring transitions, missing logic
3. COLOR CONSISTENCY — palette drift contradicting the Visual Brief
4. VISUAL CONTRAST — sequences lacking visual interest due to sameness
5. CONTINUITY ERRORS — character/environment inconsistencies

You have AUTHORITY to make targeted corrections. You do NOT redesign shots from scratch.
You make SURGICAL fixes and annotate WHY.

{visual_brief_section}

═══════ COMPLETE SHOT LIST ═══════
{formatted_shots}

═══════ YOUR REVIEW PROCESS ═══════

STEP 1 — SHOT SIZE VARIETY CHECK:
Scan the sequence of shot_size values across all shots.
RULE: No MORE than 2 consecutive shots with the SAME shot_size.
If you find 3+ consecutive same-size shots:
  - Change the MIDDLE shot(s) to a contrasting size
  - Annotate the change in "continuity_fix"

STEP 2 — CAMERA VARIETY CHECK:
Scan camera_movement and camera_angle across all shots.
RULE: No MORE than 2 consecutive shots with the same camera_movement.
RULE: No MORE than 3 consecutive shots with the same camera_angle.
If violated, suggest alternatives that still serve the Director's camera_intent.

STEP 3 — VISUAL FLOW CHECK:
Review adjacent shots for transition logic:
- Does the sequence of visuals make spatial sense?
- Are there abrupt location changes without an establishing visual?
- Does the emotional intensity match the shot language (close-ups for emotion, wides for context)?
If flow problems exist, suggest a fix in the visual description or add a transitional note.

STEP 4 — COLOR CONSISTENCY CHECK:
Reference the Visual Brief's color_palette_shift per beat and the global color_arc.
- Does each shot's lighting_mood align with the brief's color guidance?
- Are there sudden palette jumps that are not motivated by the narrative?
If inconsistencies exist, annotate which shots need palette adjustment.

STEP 5 — CONTINUITY CHECK:
For characters appearing in multiple shots:
- Is their outfit consistent (unless story-driven change is noted)?
- Is their visual description consistent?
For environments spanning multiple shots:
- Is the environment description consistent?
- Are time-of-day and lighting conditions consistent within a scene?

═══════ OUTPUT FORMAT ═══════

Return the COMPLETE shot list with corrections applied. For EACH shot, carry forward ALL
existing fields. ADD these fields:

1. "continuity_fix": If you changed anything, describe what and why.
   If no changes: "No issues — approved as-is."

2. "continuity_grade": One of:
   "A" (no issues),
   "B" (minor fix applied),
   "C" (significant fix applied),
   "F" (fundamental problem — flagged for review).

Return a JSON object:
{{{{
  "review_summary": {{{{
    "total_shots": 0,
    "shots_modified": 0,
    "variety_fixes": 0,
    "flow_fixes": 0,
    "color_fixes": 0,
    "continuity_fixes": 0,
    "overall_grade": "A"
  }}}},
  "shots": [
    {{{{
      "...all existing fields from storyboard...",
      "continuity_fix": "Changed shot_size from Medium to Wide — broke 3-shot Medium streak",
      "continuity_grade": "B"
    }}}}
  ]
}}}}

═══════ RULES ═══════
1. CARRY FORWARD every field from every shot. Do NOT remove fields.
2. When you modify a field, ALWAYS explain the change in "continuity_fix."
3. Prefer MINIMAL changes. If a shot is fine, leave it alone with grade "A".
4. Your fixes must still serve the Director's camera_intent and emotion.
5. Do NOT add first_frame_prompt, last_frame_prompt, or veo_prompt. That is the DP's job.
6. If you encounter a problem you cannot fix, grade it "F" and describe the issue.

⚠️ Return ONLY valid JSON. No commentary. Begin."""

    return prompt


def build_director_prompt(narration_json: dict, duration_minutes: int = 10,
                          shot_start_number: int = 1,
                          pacing_tier: str = "Standard",
                          creative_direction: dict = None,
                          format_preset: str = "",
                          visual_brief: dict = None,
                          spine: dict = None) -> str:
    """
    Phase 1 of 6: THE DIRECTOR — Editorial + Camera Intent.

    Makes cutting decisions AND expresses camera intent per shot.
    Upgraded from pure editorial to include emotional arc mapping
    and storytelling goals for the Cinematographer.

    When `spine` is provided, each shot must inherit a `claim_id` from
    its parent beat's claim_ids so source citations propagate to visuals.
    """
    beats = narration_json.get("narration", [])
    title = narration_json.get("title", "Untitled")
    hook_type = narration_json.get("hook_type", "")

    # Format narration beats — append claim_ids when spine present so the
    # Director can pick the best-fit id per shot.
    narration_text = ""
    for i, beat in enumerate(beats):
        act = beat.get("act", "")
        beat_name = beat.get("beat", "")
        text = beat.get("text", beat.get("narration", ""))
        claim_tag = ""
        if spine:
            beat_claims = beat.get("claim_ids") or []
            if beat_claims:
                claim_tag = f" | Claims: [{', '.join(beat_claims)}]"
        narration_text += f"\n[BEAT {i+1}] Act: {act} | Beat: {beat_name}{claim_tag}\n{text}\n"

    total_words = sum(len(b.get("text", b.get("narration", "")).split()) for b in beats)
    pacing_instruction = PACING_INSTRUCTIONS.get(pacing_tier, PACING_INSTRUCTIONS["Standard"])
    words_per_shot = WORDS_PER_SHOT_TARGETS.get(pacing_tier, 9)
    estimated_shots = max(1, int(total_words / words_per_shot))

    # Apply shot range cap from format preset
    short_form_cutting = ""
    if format_preset and format_preset in FORMAT_PRESETS:
        shot_range = FORMAT_PRESETS[format_preset].get("shot_range")
        if shot_range:
            min_shots, max_shots = shot_range
            estimated_shots = max(min_shots, min(max_shots, estimated_shots))
        if format_preset in ("micro", "quick_take"):
            sr = shot_range or (4, 20)
            short_form_cutting = (
                f"\n⚠️ SHORT-FORM VIDEO — SHOT COUNT IS CRITICAL ⚠️\n"
                f"This is a {format_preset.replace('_', ' ')} video ({duration_minutes} min).\n"
                f"You MUST produce between {sr[0]} and {sr[1]} shots total.\n"
                f"- Do NOT over-split beats. Each shot should carry a complete visual idea.\n"
                f"- Prefer 4s shots for micro content, mix 4s/6s for quick_take.\n"
            )

    # Build creative direction section for director
    creative_direction_section = _build_creative_direction_section(creative_direction, 'director')

    # Build visual brief context
    visual_brief_section = ""
    if visual_brief:
        global_motifs = visual_brief.get("global_motifs", {})
        visual_brief_section = f"""
═══════ VISUAL BRIEF (from Script Doctor) ═══════
Color Arc: {global_motifs.get('color_arc', 'Not specified')}
Emotional Throughline: {global_motifs.get('emotional_throughline', 'Not specified')}
Recurring Symbols: {global_motifs.get('recurring_symbols', [])}

Use this brief to inform your emotional pacing and camera intent decisions.
When the brief suggests a mood shift, consider matching it with a pacing change.
"""
        for entry in visual_brief.get("visual_brief", []):
            visual_brief_section += (
                f"  Beat {entry.get('beat_number', '?')}: "
                f"mood={entry.get('mood_atmosphere', [])}, "
                f"pov={entry.get('suggested_pov', 'N/A')}\n"
            )

    # Spine block + per-shot claim_id schema additions
    spine_block = _format_spine_block(spine) if spine else ""
    if spine_block:
        director_claim_field = ',\n      "claim_id": "k1"'
        director_claim_rule = (
            "\n10. CLAIM PROPAGATION: Every shot MUST carry a `claim_id` chosen from "
            "its parent beat's claim_ids (the [Claims: ...] tag on each [BEAT n] line). "
            "Pick the SINGLE best-fit claim id per shot. If the parent beat has no "
            "claim_ids, omit the field. The claim_id flows through Cinematographer, "
            "Storyboard, Continuity, and DP unchanged so visuals carry source citations."
        )
    else:
        director_claim_field = ""
        director_claim_rule = ""

    prompt = f"""You are THE DIRECTOR for a video production. Your job is editorial decision-making:
- WHERE to cut the narration into shots
- HOW LONG each shot lasts
- WHAT EMOTION each shot carries
- WHAT CAMERA INTENT each shot needs (the storytelling goal, not specific technique)

You are NOT a cinematographer. You do not pick specific lenses, angles, or movements.
You express INTENT: "this needs a slow reveal," "this needs claustrophobic intimacy,"
"pull back to show the enormity," "let the viewer lean in."

The Cinematographer will translate your intent into specific camera technique.
{creative_direction_section}
{visual_brief_section}{spine_block}═══════ PROJECT INFO ═══════
Title: {title}
Hook Type: {hook_type}
Duration: {duration_minutes} minutes
Total Narration Words: ~{total_words}
Estimated Shots: ~{estimated_shots}

═══════ NARRATION TO SPLIT ═══════
⚠️ USE THESE EXACT WORDS — DO NOT REWRITE, PARAPHRASE, OR DROP ANY TEXT ⚠️
{narration_text}

═══════ STEP 1: EMOTIONAL ARC MAPPING (THINK FIRST) ═══════

Before making ANY cuts, read the entire narration and map the emotional arc:
- Where is the TENSION PEAK? (Moment of highest dramatic intensity)
- Where are the BREATHING POINTS? (Moments of release or contemplation)
- Where are the TRANSITIONS? (Shifts between topics, moods, or energy levels)
- What is the overall SHAPE? (Building? Wavelike? Escalating staircase? U-shaped?)

Write your arc analysis in "emotional_arc_analysis" in the output.
Your cutting decisions MUST serve this arc — fast cuts at peaks, held shots at breathing points.

═══════ STEP 2: EDITORIAL DECISIONS ═══════

{pacing_instruction}
{short_form_cutting}
You are making CREATIVE EDITORIAL DECISIONS about where to cut. This is NOT a mechanical word-count exercise.

CONSIDER THESE FACTORS WHEN DECIDING WHERE TO CUT:
1. NARRATIVE BEATS: Cut when the idea shifts, a new claim begins, or a new subject is introduced
2. EMOTIONAL SHIFTS: Cut when the emotion changes (curiosity → surprise, tension → release)
3. VISUAL LOGIC: Cut when what the audience should SEE would naturally change
4. DRAMATIC TIMING: Use shorter shots (4s) for high-impact moments, longer shots (6-8s) for contemplation
5. BREATHING ROOM: Not every cut must align with a word boundary — consider dramatic pauses

GUIDELINES:
- Target 5-15 words per shot, but allow 3-4 words for dramatic emphasis shots
- Average speech rate is ~{WORDS_PER_SECOND} words/sec — use this to ESTIMATE duration
- Duration MUST be exactly 4s, 6s, or 8s (Veo hardware constraint)
- EVERY word from the narration must appear in exactly one shot's script_beat
- Split sentences at natural pause points (commas, periods, em-dashes, semicolons)

═══════ STEP 3: CAMERA INTENT ═══════

For EACH shot, write a "camera_intent" — the storytelling GOAL for how this shot should feel visually.
This is NOT a technique. It's the EMOTIONAL REASON for a camera choice.

GOOD camera_intent examples:
- "Slow reveal — start tight, then expand to show the scale of devastation"
- "Claustrophobic intimacy — the viewer is trapped in this moment with the subject"
- "Grand establishing — let the audience absorb the world before we dive in"
- "Punch cut — a jarring visual shift that mirrors the narrative shock"
- "Contemplative distance — observe from afar, let the weight settle"
- "Creeping approach — the viewer senses something before seeing it"

BAD camera_intent examples (too vague or too technical):
- "Wide shot" (that's a technique, not intent)
- "Show the scene" (too vague — show it HOW? WHY?)
- "Dolly-in with 85mm lens" (too specific — that's the Cinematographer's job)

═══════ EXAMPLE: MULTI-ACT PACING ═══════

ACT 1 (Setup — curiosity, world-building):
  Shot 1 | 6s | "In 1347, a ship arrived..." | intent: "Grand establishing — the viewer sees the scale"
  Shot 2 | 4s | "carrying death itself." | intent: "Tight punch — shock of the dark turn"

ACT 2 (Escalation — tension, revelation):
  Shot 5 | 4s | "No one understood why." | intent: "Intimate confusion — close, personal, lost"
  Shot 6 | 8s | "Until one physician dared to look closer." | intent: "Slow approach — anticipation"
  Shot 7 | 4s | "What he found changed everything." | intent: "The reveal — dramatic pause before payoff"

ACT 3 (Resolution — awe, reflection):
  Shot 12 | 8s | "And so began the age of modern medicine." | intent: "Wide pullback — sweep of consequence"
  Shot 13 | 6s | "A legacy born from horror." | intent: "Quiet close — let the weight settle"

Notice: ACT 1 mixes 6s (scene-setting) with 4s (punch). ACT 2 uses 8s for anticipation, 4s for reveals.
ACT 3 breathes with 8s and 6s. The RHYTHM creates the experience.

═══════ OUTPUT FORMAT ═══════

Return a JSON object:
{{{{
  "emotional_arc_analysis": {{{{
    "shape": "Description of the overall arc shape",
    "tension_peaks": ["Beat N (description)", "Beat M (description)"],
    "breathing_points": ["Beat N (description)"],
    "transitions": ["Beat N→M (what shifts)"]
  }}}},
  "shots": [
    {{{{
      "shot_number": "{shot_start_number}",
      "script_beat": "The exact narration text for this shot (5-15 words)",
      "duration": "4s",
      "act": "ACT 1",
      "beat": "Hook",
      "emotion": "Curiosity",
      "directors_intent": "What the audience should FEEL at this moment",
      "camera_intent": "The storytelling GOAL for how this shot should feel visually",
      "cutting_rationale": "Why the cut happens here",
      "emotional_arc_position": "Where this shot sits in the overall arc (e.g., 'Rising tension', 'Peak', 'Release')"{director_claim_field}
    }}}}
  ]
}}}}

═══════ CRITICAL RULES ═══════
1. Use the EXACT narration words in script_beat. Do not paraphrase or rewrite.
2. Every word from the narration must appear in exactly one shot's script_beat.
3. Each script_beat: 5-15 words (3-4 allowed for dramatic emphasis).
4. Every duration MUST be exactly 4s, 6s, or 8s.
5. Include a cutting_rationale for every shot.
6. Include a camera_intent for every shot — a storytelling goal, not a technique.
7. Include emotional_arc_position for every shot.
8. Fill in emotional_arc_analysis BEFORE the shots array.
9. Do NOT include visual descriptions, image prompts, or camera techniques.{director_claim_rule}

⚠️ Return ONLY valid JSON. No commentary. Begin."""

    return prompt


def build_storyboard_prompt(director_shots: list, narration_json: dict,
                            style_intent: dict = None,
                            creative_direction: dict = None,
                            cast: dict = None,
                            visual_brief: dict = None) -> str:
    """
    Phase 3 of 6: THE STORYBOARD ARTIST — Visual Composition.

    Takes the Cinematographer's shot list (with camera technique decisions) and designs
    what each shot LOOKS LIKE — layered visual compositions with foreground/midground/background,
    visual metaphor execution, and environmental storytelling.

    Also receives the full original narration for story arc context and the Visual Brief
    for mood/metaphor guidance.
    """
    import json as _json

    # Format the full narration for story arc context
    beats = narration_json.get("narration", [])
    full_narration_text = ""
    for i, beat in enumerate(beats):
        act = beat.get("act", "")
        beat_name = beat.get("beat", "")
        text = beat.get("text", beat.get("narration", ""))
        full_narration_text += f"\n[BEAT {i+1}] Act: {act} | Beat: {beat_name}\n{text}\n"

    # Format director's shot list as JSON
    formatted_shots = _json.dumps(director_shots, indent=2, ensure_ascii=False)

    # Build creative direction section for storyboard
    creative_direction_section = _build_creative_direction_section(creative_direction, 'storyboard')

    # Build cast section
    cast_section = _build_cast_section(cast, context='storyboard')

    # Build style direction section
    intent = style_intent or {}
    character_section = _build_character_section(intent)
    style_direction = f"""═══════ STYLE DIRECTION ═══════
Detail Level: {intent.get('detail_level', 'Standard')}
Scene Complexity: {intent.get('scene_complexity', 'Standard')}
Camera Language: {intent.get('camera_language', 'Standard cinematography')}
Lighting Approach: {intent.get('lighting_instruction', 'As appropriate')}
Subject Framing: {intent.get('subject_framing', 'Varied')}
Writing Style: {intent.get('writing_style', 'Descriptive')}
Color Palette: {intent.get('color_palette', 'As appropriate')}
Texture: {intent.get('texture', 'As appropriate')}
Default Mood: {intent.get('mood_default', 'As appropriate')}
{character_section}"""

    # Build wardrobe mode instructions
    wardrobe_mode = intent.get('wardrobe_mode', 'locked')
    character_desc = intent.get('character_description', '')

    # Common multi-subject and no-subject guidance (appended to both modes)
    wardrobe_edge_cases = """
HANDLING SPECIAL SHOT TYPES:
- NO CHARACTERS IN SHOT (drone shots, landscapes, equipment, vehicles, objects):
  Set "character_outfit" to "N/A — no characters in shot". Do NOT invent characters for these shots.
- MULTIPLE CHARACTERS IN SHOT: Describe ALL visible characters' clothing in one string.
  Format: "Character A: [outfit]; Character B: [outfit]" (e.g., "Officer: Navy dress whites with gold shoulder boards and commander's cap; Enlisted sailors: NWU Type III camouflage work uniforms").
- DIFFERENT SUBJECTS ACROSS SHOTS (documentary/explainer style): Each shot may feature
  entirely different people or subjects. Treat each shot independently — describe whoever
  is visible in THAT shot. Continuity only applies when the SAME character reappears."""

    if wardrobe_mode == 'story_driven':
        wardrobe_instructions = f"""═══════ WARDROBE MODE: STORY-DRIVEN ═══════
You MUST determine the appropriate outfit for each shot based on the story context.
- Read the full narration and environment for each beat.
- Choose clothing that fits the setting (e.g., lab coat in a lab, winter coat outdoors in snow, flight suit in a cockpit, dress uniform at a ceremony).
- KEEP the outfit CONSISTENT within the same scene/location for the SAME character — only change it when the setting clearly demands it.
- If the character description already mentions specific clothing, use that as the DEFAULT, but override it when the story environment requires different attire.
- If the character description has NO clothing details, invent a contextually appropriate outfit in Shot 1 and maintain it until the scene/location changes.
- In "character_outfit", write a specific, detailed description of what is worn in THIS shot.
{wardrobe_edge_cases}"""
    else:
        if character_desc:
            wardrobe_instructions = f"""═══════ WARDROBE MODE: LOCKED ═══════
The primary character's wardrobe is LOCKED to the master Character Description.
- Copy the wardrobe/clothing details from the character description into "character_outfit" for EVERY shot where that character appears.
- Do NOT change, adapt, or reinterpret the primary character's clothing across shots.
- If the character description does not mention clothing, set their outfit to "As described in character rendering style".
- Character Description for reference: "{character_desc[:200]}..."
{wardrobe_edge_cases}"""
        else:
            wardrobe_instructions = f"""═══════ WARDROBE MODE: LOCKED ═══════
The primary character's wardrobe is LOCKED.
- Since no specific clothing was described, invent a simple default outfit in Shot 1 (e.g., "plain white t-shirt and blue jeans") and copy it EXACTLY for EVERY subsequent shot where that character appears.
- Do NOT change the primary character's outfit across shots.
{wardrobe_edge_cases}"""

    # Build expression mode instructions
    expression_mode = intent.get('expression_mode', 'dynamic')

    # Common multi-subject and no-subject guidance for expressions
    expression_edge_cases = """
HANDLING SPECIAL SHOT TYPES:
- NO CHARACTERS IN SHOT (drone shots, landscapes, equipment, vehicles):
  Set "character_expression" to "N/A — no characters in shot".
- MULTIPLE CHARACTERS IN SHOT: Describe the PRIMARY/foreground character's expression.
  If multiple characters have distinct emotional states, describe both:
  "Commander: steely focus, narrowed eyes, set jaw; Recruit: wide-eyed awe, mouth slightly open"."""

    if expression_mode == 'dynamic':
        expression_instructions = f"""═══════ EXPRESSION MODE: DYNAMIC ═══════
You MUST define a specific facial expression for each shot based on the Director's "emotion" field.
- Translate each shot's "emotion" into concrete facial details: eyes (wide, narrowed, soft), mouth (smile, frown, open), brows (raised, furrowed, relaxed), overall energy.
- Expressions should EVOLVE across the video — track the emotional arc.
- Make expressions match the story beat (surprise at a reveal, determination during a challenge, joy at resolution).
- Write the expression in "character_expression" as a specific, actable description.
{expression_edge_cases}"""
    else:
        expression_instructions = f"""═══════ EXPRESSION MODE: LOCKED/NEUTRAL ═══════
Facial expressions are LOCKED to neutral throughout the video.
- Set "character_expression" to "Neutral expression" for EVERY shot that has characters.
- Do NOT vary expressions based on emotion or story beats.
{expression_edge_cases}"""

    # Build visual brief context for storyboard
    visual_brief_section = ""
    if visual_brief:
        global_motifs = visual_brief.get("global_motifs", {})
        visual_brief_section = f"""═══════ VISUAL BRIEF (from Script Doctor) ═══════
Recurring Symbols: {global_motifs.get('recurring_symbols', [])}
Color Arc: {global_motifs.get('color_arc', 'Not specified')}
Emotional Throughline: {global_motifs.get('emotional_throughline', 'Not specified')}

Use this brief to guide your visual compositions. When the brief suggests symbolic imagery,
find ways to incorporate it into your foreground/background layers. When it suggests a mood,
let that mood influence your environmental storytelling.

Per-beat guidance:
"""
        for entry in visual_brief.get("visual_brief", []):
            visual_brief_section += (
                f"  Beat {entry.get('beat_number', '?')}: "
                f"metaphor=\"{entry.get('metaphors', 'N/A')}\", "
                f"symbols=\"{entry.get('symbolic_imagery', 'N/A')}\", "
                f"mood={entry.get('mood_atmosphere', [])}\n"
            )

    prompt = f"""You are THE STORYBOARD ARTIST for a video production. The Director has decided the cuts
and camera intent. The Cinematographer has specified camera technique (movement, angle, lens,
composition approach, lighting mood, depth/focus). Your job is to design the CONTENT of each frame.

You think in terms of VISUAL STORYTELLING:
- Composition layers: foreground, midground, background — what occupies each?
- Visual metaphor execution: how do the Script Doctor's symbolic suggestions manifest?
- Character staging: where in the frame, doing what, relating to whom/what?
- Environmental storytelling: what does the location communicate beyond "setting"?

You do NOT change the Director's cuts, timing, or emotion.
You do NOT change the Cinematographer's camera technique decisions.
You do NOT write final image or video generation prompts.
You design the CONTENT of the frame — what the camera captures.

{creative_direction_section}
{visual_brief_section}
{style_direction}
{cast_section}
{wardrobe_instructions}

{expression_instructions}

═══════ FULL STORY CONTEXT ═══════
Read this ENTIRE script first to understand the complete story arc, themes, character journey,
locations, and tone BEFORE designing visuals for individual shots. This context is critical
for making wardrobe and expression decisions that serve the narrative:
{full_narration_text}

═══════ SHOT LIST (from Director + Cinematographer) ═══════
These shots include locked editorial AND camera technique decisions. Do NOT modify any existing fields.
{formatted_shots}

═══════ YOUR TASK ═══════

⚠️ STEP 1 — STORY ANALYSIS (DO THIS FIRST):
Before touching any individual shot, analyze the ENTIRE script holistically.
Fill in the "story_analysis" object in your output with:
- All distinct LOCATIONS/SETTINGS in the story (in order of appearance)
- The PRIMARY SUBJECTS: who or what is featured? Characters, objects, environments, or abstract concepts.
  - CHARACTERS: list each with when they appear and their baseline look
  - NO CHARACTERS: list primary VISUAL SUBJECTS (e.g., "Tectonic plates", "The Grand Canyon")
- The EMOTIONAL/TONAL ARC across the full video
- VISUAL TRANSITION POINTS: where major visual changes occur
This analysis is your PLAN. Every per-shot decision below must be consistent with it.

⚠️ STEP 2 — PER-SHOT FIELDS:
Using your story_analysis as reference, for EACH shot ADD these seven fields:

1. "visual": A 3-4 sentence LAYERED description of what this shot shows:
   - SENTENCE 1: The primary subject and their action (what is happening)
   - SENTENCE 2: The environment and atmospheric context (where, what conditions)
   - SENTENCE 3: Composition detail — what is in the foreground vs background,
     what draws the eye, what visual metaphor or symbolic element is present
   - SENTENCE 4 (optional): Any dynamic element — movement, change, interaction

   The Cinematographer has already specified camera_movement, camera_angle, lens_feel,
   composition approach, lighting_mood, and depth_focus for this shot. Your visual description
   should WORK WITH those decisions — describe content that serves the chosen technique.

   WEAK: "A man stands in a forest."
   STRONG: "A weathered explorer pauses mid-stride on a root-tangled trail, machete
   lowered to his side. Dense canopy filters jade-green light onto his sweat-streaked face.
   In the foreground, a spider's web stretches between two branches — a natural gate he
   must break through. Behind him, the path disappears into shadow."

2. "shot_size": One of: Extreme Wide, Wide, Medium Wide, Medium, Medium Close-Up,
   Close-Up, Extreme Close-Up, Macro. Choose based on the emotion, camera_angle,
   and the Cinematographer's composition approach.
   VARY your choices — no more than 2 consecutive shots at the same size.

3. "fg_mg_bg_layers": What occupies each depth plane in this shot:
   - "fg": Foreground element (can be "none" if nothing in foreground)
   - "mg": Midground / primary subject
   - "bg": Background element
   Example: {{"fg": "out-of-focus candle flame", "mg": "scientist hunched over microscope", "bg": "shelves of specimen jars"}}
   For shots with no depth layering: {{"fg": "none", "mg": "the primary subject", "bg": "the environment"}}

4. "visual_metaphor_execution": If the Visual Brief suggests symbolic imagery or metaphors
   for this beat, describe how you are visually executing it in this shot's composition.
   If no metaphor applies: "N/A — straightforward narrative shot."
   Example: "The Script Doctor suggested 'time as erosion.' Executed by placing a crumbling
   stone wall behind the subject, with sand visibly trickling from its cracks."

5. "character_outfit": What characters are wearing in THIS specific shot.
   Follow the WARDROBE MODE instructions above. Be specific.
   - No characters: "N/A — no characters in shot"
   - Multiple characters: describe each (e.g., "Officer: dress whites; Sailors: NWU camo")
   This field will be used directly by the DP.

6. "character_expression": The facial expression(s) in THIS specific shot.
   Follow the EXPRESSION MODE instructions above.
   - No characters: "N/A — no characters in shot"
   This field will be used directly by the DP.

7. "visual_continuity_notes": How this shot connects to the previous and next shot.
   What must stay consistent? Note subject, environment, lighting, wardrobe continuity.
   If a major visual transition occurred, note WHY.

CRITICAL RULES:
1. EVERY shot must depict what the narration describes. Read the script_beat carefully.
2. Characters must be DOING things (walking, talking, reacting), NOT posing statically.
3. No characters? Focus on environments, objects, processes, or phenomena from the narration.
4. Backgrounds come from the STORY, NOT "studio backdrops."
5. Vary shot sizes — no more than 2 consecutive shots at the same size.
6. Maintain visual consistency: same subjects look the same across shots.
7. Wardrobe/expression decisions are YOUR responsibility — the DP uses your choices directly.
8. Work WITH the Cinematographer's camera decisions — your visual content should serve the
   chosen camera_movement, composition, and lighting_mood. If the Cinematographer chose
   "foreground framing" as composition, make sure your fg_mg_bg_layers has a foreground element.
9. Do NOT add "first_frame_prompt", "last_frame_prompt", or "veo_prompt" fields.
10. CARRY FORWARD every existing field exactly as given. Do NOT modify any of them.

═══════ OUTPUT FORMAT ═══════

Return a JSON object. IMPORTANT: Fill in "story_analysis" FIRST, then use it as your guide for every shot.

Example A — CHARACTER-DRIVEN video (narrative, explainer with mascot):
{{
  "story_analysis": {{
    "locations": [
      {{"name": "The Lab", "shots": "1-5, 9-12", "description": "University research laboratory"}},
      {{"name": "The Beach", "shots": "6-8", "description": "Tropical beach flashback"}}
    ],
    "subjects": [
      {{"name": "The Scientist", "type": "character", "appears_in_shots": "1-12", "base_look": "Blue lab coat, round glasses"}},
      {{"name": "The Assistant", "type": "character", "appears_in_shots": "3-5, 10-12", "base_look": "Green scrubs"}}
    ],
    "tonal_arc": "Curiosity (Act 1) → Nostalgia (Act 2 flashback) → Triumph (Act 3)",
    "visual_transitions": [
      {{"at_shot": "6", "reason": "Location changes from lab to beach", "change": "Lab coat → casual beach clothes"}},
      {{"at_shot": "9", "reason": "Returns to lab", "change": "Beach clothes → lab coat returns"}}
    ]
  }},
  "shots": [...]
}}

Example B — NON-CHARACTER video (geography, nature, documentary, architecture):
{{
  "story_analysis": {{
    "locations": [
      {{"name": "Earth orbit", "shots": "1-3", "description": "Satellite view of Earth showing tectonic plates"}},
      {{"name": "Cross-section", "shots": "4-7", "description": "Animated geological cross-section of Earth's crust"}},
      {{"name": "Ocean floor", "shots": "8-12", "description": "Underwater volcanic vent at mid-ocean ridge"}}
    ],
    "subjects": [
      {{"name": "Tectonic plates", "type": "phenomenon", "appears_in_shots": "1-12", "base_look": "Massive rock formations with glowing fault lines"}},
      {{"name": "Volcanic vent", "type": "object", "appears_in_shots": "8-12", "base_look": "Black smoker chimney with superheated mineral plumes"}}
    ],
    "tonal_arc": "Wonder/scale (opening) → Scientific precision (middle) → Awe at raw power (climax)",
    "visual_transitions": [
      {{"at_shot": "4", "reason": "Zoom from space into cross-section diagram", "change": "Satellite view → illustrated cutaway"}},
      {{"at_shot": "8", "reason": "Dive into ocean to show real footage", "change": "Diagram → photorealistic underwater"}}
    ]
  }},
  "shots": [...]
}}

ACTUAL OUTPUT SCHEMA (use for both types):
{{
  "story_analysis": {{
    "locations": [{{"name": "...", "shots": "...", "description": "..."}}],
    "subjects": [{{"name": "...", "type": "character|object|phenomenon|environment", "appears_in_shots": "...", "base_look": "..."}}],
    "tonal_arc": "The viewer's emotional journey across the full video",
    "visual_transitions": [{{"at_shot": "...", "reason": "...", "change": "..."}}]
  }},
  "shots": [
    {{
      "shot_number": "<same as input>",
      "script_beat": "<same as input>",
      "duration": "<same as input>",
      "act": "<same as input>",
      "beat": "<same as input>",
      "emotion": "<same as input>",
      "directors_intent": "<same as input>",
      "camera_intent": "<same as input>",
      "cutting_rationale": "<same as input>",
      "emotional_arc_position": "<same as input>",
      "camera_movement": "<same as input>",
      "camera_angle": "<same as input>",
      "lens_feel": "<same as input>",
      "composition": "<same as input>",
      "lighting_mood": "<same as input>",
      "depth_focus": "<same as input>",
      "visual_storytelling_technique": "<same as input>",
      "visual": "3-4 sentence LAYERED description of what this shot shows",
      "shot_size": "Medium Close-Up",
      "fg_mg_bg_layers": {{"fg": "foreground element", "mg": "primary subject", "bg": "background"}},
      "visual_metaphor_execution": "How the Visual Brief's symbolism manifests here (or N/A)",
      "character_outfit": "Clothing for this shot (or 'N/A — no characters in shot')",
      "character_expression": "Expression for this shot (or 'N/A — no characters in shot')",
      "visual_continuity_notes": "What must stay consistent with adjacent shots"
    }}
  ]
}}

⚠️⚠️⚠️ JSON SYNTAX VALIDATION ⚠️⚠️⚠️
CRITICAL: You MUST generate VALID JSON with correct syntax:
1. Every field MUST end with a comma EXCEPT the last field in an object
2. All string values MUST be properly escaped
3. Do NOT put commas after the last field in an object
4. ALWAYS put a comma after every object in the "shots" array EXCEPT the last one

⚠️ Return ONLY valid JSON. No commentary. Begin."""

    return prompt


def build_script_structuring_prompt(raw_text: str, duration_minutes: int = 10) -> str:
    """
    Script Structurer — takes raw plain-text narration and breaks it into
    proper acts and beats, matching the narration JSON format used throughout the pipeline.
    """
    prompt = f"""You are a Script Structure Editor. You receive a raw, unstructured narration script
and your job is to break it into clean acts and beats — the same format a professional scriptwriter would produce.

═══════ RAW SCRIPT ═══════
{raw_text}

═══════ YOUR TASK ═══════
Analyze the full text above and split it into logical ACTS and BEATS.

RULES:
1. Read the ENTIRE script first to understand the narrative arc
2. Identify natural topic shifts, emotional turns, and structural transitions
3. Group related paragraphs/sentences into BEATS (each beat = one distinct narrative moment or topic)
4. Group beats into ACTS (each act = a major phase of the story — setup, development, climax, resolution, etc.)
5. The narration text within each beat must be the EXACT words from the original script — do NOT rewrite, summarize, or paraphrase. Copy word-for-word.
6. Every single word from the original script must appear in exactly one beat — nothing dropped, nothing duplicated
7. Give each act a clear name (e.g., "ACT 1: THE SETUP", "ACT 2: THE CONFLICT")
8. Give each beat a specific, descriptive name that reflects its content (e.g., "The Discovery", "Rising Stakes", "The Paradox Revealed")
9. Aim for 3-5 acts with 2-5 beats each, depending on script length
10. Target duration: approximately {duration_minutes} minutes

═══════ OUTPUT FORMAT ═══════
Return a JSON object with this EXACT structure:
{{
  "title": "Best-guess title based on the script content",
  "duration_minutes": {duration_minutes},
  "narration": [
    {{
      "act": "ACT 1: THE SETUP",
      "beat": "The Hook",
      "text": "Exact narration text for this beat, copied verbatim from the original."
    }},
    {{
      "act": "ACT 1: THE SETUP",
      "beat": "Setting the Stage",
      "text": "Exact narration text for this beat..."
    }},
    {{
      "act": "ACT 2: THE CONFLICT",
      "beat": "The Turning Point",
      "text": "Exact narration text for this beat..."
    }}
  ]
}}

CRITICAL:
- The text fields must contain the EXACT original words — you are STRUCTURING, not rewriting
- Every word from the input must appear in the output — no content may be dropped
- Return ONLY valid JSON. No commentary. Begin."""

    return prompt


def build_cast_suggestion_prompt(narration_json: dict, character_description: str = "",
                                 rendering_split: str = "unified",
                                 creative_direction: dict = None) -> str:
    """
    Casting Director — analyzes the finalized script and suggests a cast of characters/subjects.

    Reads the full narration and identifies all distinct characters, their roles, visual identity,
    and which beats they appear in. Returns structured cast data for user review.
    """
    import json as _json

    # Format the full narration
    beats = narration_json.get("narration", [])
    full_narration_text = ""
    for i, beat in enumerate(beats):
        act = beat.get("act", "")
        beat_name = beat.get("beat", "")
        text = beat.get("text", beat.get("narration", ""))
        full_narration_text += f"\n[BEAT {i+1}] Act: {act} | Beat: {beat_name}\n{text}\n"

    title = narration_json.get("title", "Untitled")

    # Build character rendering context
    rendering_context = ""
    if character_description:
        rendering_context = f"""═══════ CHARACTER RENDERING STYLE ═══════
All characters must be rendered in this style:
"{character_description}"

Your cast suggestions define WHO each character is WITHIN this rendering style.
- Do NOT describe photorealistic features if the style is cartoon/stick figure.
- Differentiate characters through: clothing color/style, accessories, size, headwear,
  props they carry — NOT through realistic facial features.
- The rendering style is the TEMPLATE. Your job is to make each character DISTINCT within it.
{"- This is HYBRID mode: characters use the style above, environments use a different (cinematic) style." if rendering_split == "hybrid" else ""}
"""
    else:
        rendering_context = """═══════ CHARACTER RENDERING STYLE ═══════
No specific rendering style has been defined. Describe characters naturally based on
what the script implies. You can use realistic descriptions, stylized descriptions,
or whatever best fits the story's tone.
"""

    # Build creative direction context for portrait prompts
    creative_direction_context = ""
    if creative_direction:
        cd_parts = []
        if creative_direction.get('visual_language'):
            cd_parts.append(f"Visual Language: {creative_direction['visual_language']}")
        if creative_direction.get('character_approach'):
            cd_parts.append(f"Character Approach: {creative_direction['character_approach']}")
        if cd_parts:
            creative_direction_context = f"""═══════ CREATIVE DIRECTION CONTEXT ═══════
{chr(10).join(cd_parts)}
Use this context when crafting portrait generation prompts — they should match the creative vision.
"""

    prompt = f"""You are THE CASTING DIRECTOR for a video production. The script has been finalized.
Your job is to read the entire script and identify every distinct character, creature, or
recurring visual subject that appears across the narrative.

For each one, you will suggest a visual identity that makes them immediately recognizable
and visually distinct from other characters.

{rendering_context}
{creative_direction_context}
═══════ PROJECT ═══════
Title: {title}

═══════ FULL SCRIPT ═══════
Read this ENTIRE script carefully. Pay attention to:
- Every person, character, creature, or personified concept mentioned
- Whether they appear once or recur across multiple beats
- Their role in the story (protagonist, antagonist, supporting, background)
- Any clothing, appearance, or personality clues the script gives
- Shots that have NO characters (landscapes, objects, abstract visuals)
{full_narration_text}

═══════ YOUR TASK ═══════

Analyze the script and output a cast list. For EACH distinct character or recurring subject:

1. "name": A short identifier (e.g., "The Scientist", "Hero", "Narrator Character", "The Robot")
2. "role": Their function in the story (e.g., "Protagonist — drives the discovery",
   "Antagonist — represents the obstacle", "Supporting — appears in flashbacks only")
3. "visual_identity": A specific, detailed description of how this character looks
   WITHIN the rendering style. Focus on what makes them VISUALLY DISTINCT from other characters.
   Include: clothing/outfit, accessories, size/proportions, any defining visual feature.
4. "appears_in_beats": Array of beat numbers where this character appears or is referenced.
5. "notes": Any casting notes (e.g., "Always carries a briefcase", "Gets progressively disheveled",
   "Same character as Hero but in flashback — younger version")
6. "portrait_prompts": An object with two keys for generating character reference images:
   - "face_closeup": A detailed image generation prompt for a HEAD AND SHOULDERS PORTRAIT of this character.
     Must describe: face shape, skin tone, hair color/style, eye color/shape, age range, neutral expression,
     and any defining accessories visible from chest up. Background should be plain/neutral.
     Format: "[RENDERING STYLE]. Head and shoulders portrait of [character description]. [specific facial features]. Neutral expression. Plain background."
   - "full_body": A detailed image generation prompt for a FULL BODY STANDING PORTRAIT of this character.
     Must describe: everything in the face closeup PLUS body build, height impression, full outfit, shoes, posture, and any props.
     Format: "[RENDERING STYLE]. Full body standing portrait of [character description]. [outfit details]. [pose/posture]. Plain background."
   IMPORTANT: Both prompts must produce CHARACTER REFERENCE images — neutral pose, plain background, no dramatic lighting.
   The goal is IDENTITY REFERENCE, not a cinematic shot. Incorporate the rendering style into both prompts.

IMPORTANT GUIDELINES:
- If the script has NO characters (e.g., geography explainer, nature documentary, abstract concepts):
  set "has_characters" to false and return an empty cast array. This is perfectly valid.
- If characters appear but are GENERIC/UNNAMED (e.g., "people walking", "a crowd"):
  only create cast entries for characters that RECUR or have narrative importance.
  Background crowds don't need cast entries.
- If the script mentions a narrator but they are VOICE-ONLY (never seen on screen):
  do NOT include them unless the visual style places the narrator character on screen.
- Look for IMPLIED characters: if the narration says "you discover a hidden lab", the "you"
  might be a character that needs a visual identity — or it might be camera-POV with no character.
  Use your judgment based on the overall script tone.

═══════ OUTPUT FORMAT ═══════

Return a JSON object:
{{
  "title": "{title}",
  "has_characters": true,
  "total_beats": {len(beats)},
  "cast": [
    {{
      "name": "The Scientist",
      "role": "Protagonist — the researcher making the breakthrough discovery",
      "visual_identity": "Wears a long blue lab coat over the body, round glasses perched on top of the head, always carries a clipboard tucked under one arm. Slightly taller than other characters.",
      "appears_in_beats": [1, 2, 3, 4, 5, 7, 8, 9, 10],
      "notes": "Central character — appears in most shots. Outfit may change in beach flashback (beats 6-8).",
      "portrait_prompts": {{
        "face_closeup": "Stick figure style. Head and shoulders portrait of The Scientist — large white circular head, dot eyes behind round glasses perched on the head, thin smile line. Neutral expression. Plain light gray background.",
        "full_body": "Stick figure style. Full body standing portrait of The Scientist — tall stick figure with large circular head, dot eyes, round glasses. Wearing a long blue lab coat, clipboard tucked under one arm. Relaxed standing pose. Plain light gray background."
      }}
    }},
    {{
      "name": "The Robot",
      "role": "Supporting — the scientist's creation, revealed in Act 2",
      "visual_identity": "Boxy metallic torso instead of organic body shape, antenna sticking up from the circular head, glowing blue dot eyes instead of standard dark dot eyes. Shorter and wider than The Scientist.",
      "appears_in_beats": [5, 6, 7, 8, 9, 10],
      "notes": "Non-human character. No clothing needed — the metallic body IS the visual identity.",
      "portrait_prompts": {{
        "face_closeup": "Stick figure style. Head and shoulders portrait of The Robot — circular metallic head with antenna on top, glowing blue dot eyes, boxy metallic neck/shoulders. Neutral expression. Plain light gray background.",
        "full_body": "Stick figure style. Full body standing portrait of The Robot — short and wide boxy metallic torso, circular head with antenna, glowing blue dot eyes. No clothing — metallic body. Standing upright. Plain light gray background."
      }}
    }}
  ],
  "casting_notes": "Brief summary of the visual differentiation strategy and any special considerations."
}}

For NON-CHARACTER videos, return:
{{
  "title": "{title}",
  "has_characters": false,
  "total_beats": {len(beats)},
  "cast": [],
  "casting_notes": "This script is a [geography/nature/architecture/etc.] explainer with no recurring characters. Visual subjects are environments and objects — no cast definition needed."
}}

⚠️⚠️⚠️ JSON SYNTAX VALIDATION ⚠️⚠️⚠️
CRITICAL: You MUST generate VALID JSON with correct syntax:
1. Every field MUST end with a comma EXCEPT the last field in an object
2. All string values MUST be properly escaped
3. "appears_in_beats" MUST be an array of integers, not a string

⚠️ Return ONLY valid JSON. No commentary. Begin."""

    return prompt


def build_dp_prompt(storyboard_shots: list, style_analysis: dict = None,
                    aspect_ratio: str = "16:9", title: str = "Untitled",
                    creative_direction: dict = None,
                    cast: dict = None,
                    visual_brief: dict = None) -> str:
    """
    Phase 5 of 6: THE DIRECTOR OF PHOTOGRAPHY — Final Prompt Writer.

    Takes the continuity-reviewed shots (with full visual + camera direction) and writes
    the final first_frame_prompt, last_frame_prompt, and veo_prompt for each shot.

    Upgraded with creative authority over lighting design, atmosphere, and texture.
    Uses the Visual Brief for mood-informed lighting and atmospheric choices.
    """
    import json as _json

    # Format storyboard shots as JSON
    formatted_shots = _json.dumps(storyboard_shots, indent=2, ensure_ascii=False)

    # Build visual style section (reuse pattern from build_production_prompt)
    if style_analysis and isinstance(style_analysis, dict):
        intent = style_analysis.get("style_intent", {})
        schema = style_analysis.get("prompt_schema", DEFAULT_PROMPT_SCHEMA)
        style_summary = style_analysis.get("style_summary", "Custom style")

        character_section = _build_character_section(intent)
        env_desc = intent.get('environment_description', '')
        rendering_split = intent.get('rendering_split', 'unified')

        visual_style_section = f"""═══════ VISUAL STYLE & CREATIVE DIRECTION ═══════
⚠️ READ THIS SECTION CAREFULLY — IT CONTROLS HOW EVERY PROMPT IS WRITTEN ⚠️

MASTER STYLE: {style_summary}
Rendering Mode: {"HYBRID — characters and environments use DIFFERENT rendering" if rendering_split == "hybrid" else "UNIFIED — same rendering for everything"}

CHARACTER RENDERING: {intent.get('character_description', 'Standard')}
ENVIRONMENT RENDERING: {env_desc or 'Same as character rendering'}

Detail Level: {intent.get('detail_level', 'Standard')}
Scene Complexity: {intent.get('scene_complexity', 'Standard')}
Camera Language: {intent.get('camera_language', 'Standard cinematography')}
Lighting Approach: {intent.get('lighting_instruction', 'As appropriate')}
Subject Framing: {intent.get('subject_framing', 'Varied')}
Writing Style: {intent.get('writing_style', 'Descriptive')}
Color Palette: {intent.get('color_palette', 'As appropriate')}
Texture: {intent.get('texture', 'As appropriate')}
Default Mood: {intent.get('mood_default', 'As appropriate')}
{character_section}
⚠️ CRITICAL STYLE RULES:
- MATCH the style description above in EVERY prompt you write.
- If Detail Level is 'Minimalist', character descriptions should be short.{" Environment descriptions can still be rich because this is HYBRID mode." if rendering_split == "hybrid" else " Do NOT add cinematic details."}
- If Scene Complexity is 'Empty Backgrounds', do NOT describe detailed environments.
- If Writing Style is 'Concise', use short direct sentences. No flowery language.
- Do NOT hallucinate details that contradict the style (e.g., don't add '4k photorealistic' to a cartoon style).
- Follow the Camera Language instructions — if it says 'simple flat framing', do NOT use lens mm or DOF.
{"" if rendering_split != "hybrid" else f'''
⚠️ HYBRID RENDERING MODE — DUAL-LAYER RULES (CRITICAL):
- Characters: Use the CHARACTER RENDERING description above. Keep character rendering minimalist/simple.
- Environments: Use the ENVIRONMENT RENDERING description above. Environments CAN be detailed/cinematic.
- Technical camera fields (APERTURE, DOF, LIGHTING) describe the ENVIRONMENT, not the character.
- DO NOT write: "gritty documentary footage of a stick figure" or "photorealistic stick figure."
- DO NOT write: "a man standing in..." — ALWAYS use the character rendering template.
- INSTEAD write: "A [character per style] standing in a richly detailed [environment per style]."
'''}
⚠️ STORY SCENE RULES (CRITICAL):
- The style describes HOW CHARACTERS ARE RENDERED, not the scene setting.
- Characters must be placed in STORY-APPROPRIATE ENVIRONMENTS — not studio backdrops.
- Each prompt must depict WHAT IS HAPPENING in the narration at that moment.
- Characters must be DOING things (actions from the story), NOT posing statically for display."""
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
    # Pass character_description and style_summary so field templates embed them directly
    character_desc = ""
    env_desc_for_schema = ""
    rendering_split_for_schema = "unified"
    if style_analysis and isinstance(style_analysis, dict):
        intent_for_schema = style_analysis.get("style_intent", {})
        character_desc = intent_for_schema.get("character_description", "")
        env_desc_for_schema = intent_for_schema.get("environment_description", "")
        rendering_split_for_schema = intent_for_schema.get("rendering_split", "unified")
    prompt_formats = _build_prompt_format_instructions(
        schema, aspect_ratio,
        character_description=character_desc,
        style_summary=style_summary,
        environment_description=env_desc_for_schema,
        rendering_split=rendering_split_for_schema
    )

    # Build creative direction section for DP
    creative_direction_section = _build_creative_direction_section(creative_direction, 'dp')
    cast_section = _build_cast_section(cast, context='dp')

    # Build visual brief context for DP
    dp_visual_brief_section = ""
    if visual_brief:
        global_motifs = visual_brief.get("global_motifs", {})
        dp_visual_brief_section = f"""═══════ VISUAL BRIEF (USE FOR LIGHTING & ATMOSPHERE) ═══════
Color Arc: {global_motifs.get('color_arc', 'Not specified')}
Emotional Throughline: {global_motifs.get('emotional_throughline', 'Not specified')}

Reference the mood_atmosphere and color_palette_shift for each beat when deciding:
- What color temperature to use for lighting
- What atmospheric effects to include (dust motes, fog, rain, heat shimmer)
- What overall mood the prompts should convey

"""
        for entry in visual_brief.get("visual_brief", []):
            dp_visual_brief_section += (
                f"  Beat {entry.get('beat_number', '?')}: "
                f"color=\"{entry.get('color_palette_shift', 'N/A')}\", "
                f"mood={entry.get('mood_atmosphere', [])}, "
                f"tone={entry.get('tone_keywords', [])}\n"
            )

    prompt = f"""You are THE DIRECTOR OF PHOTOGRAPHY for a video production. The Director chose cuts and
camera intent. The Cinematographer specified camera technique. The Storyboard Artist designed
visual compositions. The Continuity Supervisor verified quality. Your job is to write the
final generation prompts: first_frame_prompt, last_frame_prompt, and veo_prompt.

You are NOT a mechanical transcriber. You bring CREATIVE AUTHORITY over:
- LIGHTING DESIGN: Specify light source, direction, quality, color temperature, and how
  it sculpts the subject and environment. Don't just say "dramatic lighting."
- ATMOSPHERE & TEXTURE: Add environmental details that make the image feel real —
  dust motes, moisture, heat haze, lens artifacts, surface textures.
- PROMPT CRAFT: Translate visual descriptions into technically precise, generation-optimized
  prompt language that produces the best results from AI image/video models.

You do NOT change the cuts, timing, emotions, visual descriptions, or camera technique decisions.
You translate them into the best possible generation prompts.
{creative_direction_section}
{dp_visual_brief_section}
═══════ YOUR LIGHTING VOCABULARY ═══════

Use this vocabulary when writing LIGHTING fields. Be SPECIFIC — not "dramatic lighting."

Light Source: sun, overcast sky, window light, fluorescent tube, candle, campfire, neon sign,
  screen glow, streetlamp, car headlights, moonlight, bioluminescence, explosion flash
Light Quality: hard (sharp shadows), soft (diffused, wrapping), dappled (filtered through foliage),
  specular (bright highlights on glossy), diffused (flat, even, cloudy day)
Light Direction: front-lit (flat), side-lit (sculptural), back-lit (silhouette/rim),
  top-lit (overhead, theatrical), under-lit (horror, campfire), rim-lit (edge glow)
Color Temperature: warm candlelight, neutral daylight, cool overcast,
  mixed (warm practicals + cool ambient), motivated color (neon pink, toxic green)
Shadow Quality: crisp-edged (direct sun), soft gradient (overcast), deep black (noir), none (flat light)
Atmosphere: haze, fog, dust motes in light beams, rain on surfaces, steam, smoke,
  lens condensation, heat shimmer, morning mist, underwater caustics

═══════ PROJECT INFO ═══════
Title: {title}
Aspect Ratio: {aspect_ratio}

{visual_style_section}
{cast_section}
═══════ PRODUCTION SHOTS ═══════
Each shot has been through Director, Cinematographer, Storyboard Artist, and Continuity Supervisor.
Fields include: shot_number, script_beat, duration, emotion, directors_intent, camera_intent,
camera_movement, camera_angle, lens_feel, composition, lighting_mood, depth_focus,
visual_storytelling_technique, visual, shot_size, fg_mg_bg_layers, visual_metaphor_execution,
character_outfit, character_expression, visual_continuity_notes, continuity_fix, continuity_grade.

Use "visual" + "fg_mg_bg_layers" for WHAT to depict.
Use "camera_movement" + "camera_angle" + "lens_feel" for HOW the camera frames it.
Use "lighting_mood" + the Visual Brief's color guidance for LIGHTING decisions.
Use "emotion" + "directors_intent" for the MOOD of the prompts.
Use "shot_size" for framing.

⚠️ WARDROBE & EXPRESSION — USE STORYBOARD DECISIONS:
- For the WARDROBE & FIT field in your prompts, use the "character_outfit" value from each shot.
  The Storyboard Artist already decided what characters wear — do NOT invent your own.
- For the FACIAL EXPRESSION field in your prompts, use the "character_expression" value from each shot.
  The Storyboard Artist already decided the expression — do NOT override it.
- Copy these values faithfully into the structured prompt fields.
- If "character_outfit" or "character_expression" is "N/A — no characters in shot",
  OMIT the WARDROBE & FIT and FACIAL EXPRESSION fields from that shot's prompt entirely.
  Focus the prompt on the environment, objects, or landscape instead.

{formatted_shots}

{prompt_formats}

═══════ YOUR TASK ═══════

For EACH shot above, write these three fields using the prompt schema templates above:

1. "first_frame_prompt": Full structured first frame prompt using the active schema fields.
   Describe the SCENE from the "visual" field using the exact bracket format specified above.
   This is the starting state of the shot.

2. "last_frame_prompt": Full structured last frame prompt. SAME subject, wardrobe, and
   environment as first frame, but with END pose and END expression.
   Use [SAME AS FIRST FRAME] for unchanging fields.

3. "veo_prompt": Full Veo 3.1 video prompt describing the MOTION/TRANSITION between
   first and last frame. Include camera movement, audio, and action.

Also generate a "timestamp" field with sequential timestamps based on duration.

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
- Impossible: location changes, day-to-night, wardrobe changes, 180+ degree camera moves

FRAME COMPATIBILITY (MUST MATCH between first & last frame):
- Subject: identical features, build, face
- Wardrobe: exact same clothing
- Environment: same location, same visible elements
- Style: same aesthetic
- Aspect ratio: identical

═══════ PER-SHOT STYLE COMPLIANCE CHECK ═══════
Before writing each shot's prompts, silently verify:
✓ Does the SUBJECT CORE use the character rendering template (not generic "man"/"woman"/"person")?
✓ Does the ENVIRONMENT match the story (not a studio/void unless the story is set there)?
✓ Does the CAMERA/PHOTOGRAPHY STYLE match the style guide?
{"✓ Are technical camera fields (APERTURE, DOF, LIGHTING) applied to the environment only, not the character? (HYBRID mode)" if style_analysis and isinstance(style_analysis, dict) and style_analysis.get("style_intent", {}).get("rendering_split") == "hybrid" else ""}
✓ Does the overall prompt match the style summary: "{style_summary}"?
If any check fails, REWRITE the prompt before including it in the JSON.

═══════ OUTPUT FORMAT ═══════

Return a JSON object with this EXACT structure:
{{
  "title": "{title}",
  "aspect_ratio": "{aspect_ratio}",
  "style_summary": "{style_summary}",
  "total_shots": <number>,
  "shots": [
    {{
      "shot_number": "<from input>",
      "timestamp": "00:00-00:04",
      "script_beat": "<from input>",
      "act": "<from input>",
      "beat": "<from input>",
      "duration": "<from input>",
      "visual": "<from input>",
      "emotion": "<from input>",
      "directors_intent": "<from input>",
      "cutting_rationale": "<from input>",
      "shot_size": "<from input>",
      "character_outfit": "<from input>",
      "character_expression": "<from input>",
      "visual_continuity_notes": "<from input>",
      "first_frame_prompt": "Full structured first frame prompt using approved schema",
      "last_frame_prompt": "Full structured last frame prompt using approved schema",
      "veo_prompt": "Full Veo 3.1 video prompt with motion and audio"
    }}
  ],
  "continuity_notes": [
    {{
      "from_shot": "<N>",
      "to_shot": "<N+1>",
      "visual_bridge": "How these connect visually",
      "audio_bridge": "Sound continuity",
      "potential_issue": "If any"
    }}
  ],
  "production_notes": {{
    "challenging_shots": ["Any shots needing extra iterations"],
    "recommended_workflow": "Suggested order of generation",
    "post_production": "Color grading, audio sweetening, transitions"
  }}
}}

═══════════════════════════════════════════════════════
CRITICAL RULES:
═══════════════════════════════════════════════════════
1. Follow the prompt schema EXACTLY. Use only the active fields listed above.
2. Do NOT include excluded fields in your prompts.
3. Style must match: "{style_summary}". Apply it consistently to EVERY prompt.
4. First and last frame MUST describe the SAME subject, wardrobe, and environment.
5. The only difference between frames: pose, expression, and camera position.
6. CARRY FORWARD every existing field from the storyboard. Do NOT remove any.
7. Be SPECIFIC in prompts — no vague descriptions.
8. Backgrounds MUST match what the narration describes, rendered in the visual style.

⚠️⚠️⚠️ JSON SYNTAX VALIDATION ⚠️⚠️⚠️
CRITICAL: You MUST generate VALID JSON with correct syntax:
1. Every field MUST end with a comma EXCEPT the last field in an object
2. All string values MUST be properly escaped (use \\" for quotes, \\\\ for backslashes)
3. Do NOT put commas after the last field in an object
4. ALWAYS put a comma after every object in the "shots" array EXCEPT the last one
5. Check your JSON is valid before returning it

⚠️ Return ONLY valid JSON. No commentary. Begin."""

    return prompt
