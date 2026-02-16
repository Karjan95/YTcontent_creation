import re
from youtube_transcript_api import YouTubeTranscriptApi
from gemini_client import generate_content

def extract_youtube_id(url: str) -> str:
    """Extracts video ID from various YouTube URL formats."""
    regex = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(regex, url)
    if match:
        return match.group(1)
    return None

def get_transcript(video_url: str) -> str:
    """Fetches the transcript of a YouTube video."""
    video_id = extract_youtube_id(video_url)
    if not video_id:
        return None, "Invalid YouTube URL"
    
    try:
        # Try standard static method (v0.6.x)
        if hasattr(YouTubeTranscriptApi, 'get_transcript'):
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            # Standard version returns dicts
            full_text = " ".join([item['text'] for item in transcript_list])
            return full_text, None
            
        # Try instance fetch method (v1.x found in environment)
        else:
            api = YouTubeTranscriptApi()
            transcript = api.fetch(video_id)
            # This version returns objects with .text attribute
            full_text = " ".join([item.text for item in transcript])
            return full_text, None

    except Exception as e:
        return None, str(e)

def analyze_style(transcript_text: str) -> str:
    """Analyzes the transcript to extract a style guide."""
    if not transcript_text:
        return "No transcript available."
    
    # Truncate if too long (Gemini 1.5 Pro/Flash handles long context well, but limit to save tokens/time if overkill)
    # 20k chars is plenty for style analysis (~3-4k words, 20-30 min video)
    truncated_text = transcript_text[:25000]

    prompt = f"""ANALYZE THE WRITING STYLE OF THIS YOUTUBE TRANSCRIPT.

TRANSCRIPT START:
{truncated_text}
TRANSCRIPT END

Your task is to extract a "Style DNA" for this creator so I can write a NEW script on a different topic in their exact style.

Analyze and output the following configuration for a script generator:

1. **System Prompt Persona**: Who are they? (e.g., "Fast-talking skeptic", "Calm explainer", "Dramatic storyteller").
2. **Structural Pattern**: How do they structure their videos? (Hook -> Intro -> Deep Dive -> ad read -> Conclusion?).
3. **Tone & Voice**: Keywords (e.g., "Sarcastic", "Earnest", "data-heavy").
4. **Signature Hooks**: What specific techniques do they use to hook viewers?
5. **Pacing**: How fast/dense is the information?
6. **Vocabulary**: Do they use slang? Technical jargon? Simple analogies?

Output this as a structured prompt instruction block that I can paste into an AI to generate a new script.
Format it as:
---
STYLE GUIDE: [Creator Name/Archetype]
SYSTEM PROMPT: [Instructions]
STRUCTURE: [Act breakdown]
TONE: [Keywords]
PACING: [Instructions]
---
"""
    return generate_content(prompt, model_name="gemini-2.5-flash")
