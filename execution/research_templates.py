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
    "short_form": {
        "label": "⚡ Short Form (5-7 min)",
        "duration_minutes": 5,
        "pacing_instruction": "Every sentence must earn its place. Fast cuts. No long explanations. Get in, make your point, get out. Ruthlessly cut anything that doesn't serve the hook or the payoff.",
    },
    "standard": {
        "label": "📺 Standard (10-12 min)",
        "duration_minutes": 10,
        "pacing_instruction": "Standard YouTube pacing. Build tension, allow beats to breathe. Include character moments and supporting evidence. Balance depth with momentum.",
    },
    "deep_dive": {
        "label": "📖 Deep Dive (18-22 min)",
        "duration_minutes": 20,
        "pacing_instruction": "Documentary pacing. Long scenes, rich detail, full character arcs. Take your time building atmosphere. Include extended quotes, multiple perspectives, and layered arguments.",
    },
    "custom": {
        "label": "🔢 Custom",
        "duration_minutes": None,  # user provides
        "pacing_instruction": "Adapt pacing naturally to the specified duration.",
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
            "pacing_guide": {
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
            "pacing_guide": {
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
                        custom_audience: str = "", custom_tone: str = "") -> str:
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

    # ── Resolve Format Preset (pacing intent) ──
    pacing_instruction = ""
    if format_preset and format_preset in FORMAT_PRESETS:
        preset = FORMAT_PRESETS[format_preset]
        if preset["duration_minutes"]:
            duration_minutes = preset["duration_minutes"]
        pacing_instruction = preset["pacing_instruction"]

    # Word-count target based on speech pacing
    total_words = int(duration_minutes * 60 * 2.5)  # ~2.5 words/sec

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

    prompt = f"""{system_prompt}

═══════ ASSIGNMENT ═══════
TOPIC: {topic}
LENGTH: {duration_minutes} minutes (~{total_words} words of narration){pacing_block}
{audience_block}
{tone_block}
{title_instruction}

═══════ RESEARCH DOSSIER ═══════
{research_dossier}
{style_section}{focus_block}{outcome_block}
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
