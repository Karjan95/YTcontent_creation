import os
import re
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig
from gemini_client import generate_content

def extract_youtube_id(url: str) -> str:
    """Extracts video ID from various YouTube URL formats."""
    regex = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(regex, url)
    if match:
        return match.group(1)
    return None

def get_transcript(video_url: str) -> tuple:
    """Fetches the transcript of a YouTube video.

    Supports proxy configuration via YOUTUBE_PROXY_URL environment variable
    to work around YouTube IP blocking on cloud providers (AWS, GCP, Azure).

    Example: YOUTUBE_PROXY_URL=http://user:pass@proxy-host:port
    """
    video_id = extract_youtube_id(video_url)
    if not video_id:
        return None, "Invalid YouTube URL"

    # Check for proxy configuration
    # Supports single proxy or comma-separated list for rotation
    proxy_env = os.getenv("YOUTUBE_PROXY_URL")
    proxies = [p.strip() for p in proxy_env.split(",")] if proxy_env else []
    
    # If no proxies, try direct connection once
    if not proxies:
        proxies = [None]

    last_error = None
    
    for i, proxy_url in enumerate(proxies):
        try:
            if proxy_url:
                print(f"[YouTube] Attempt {i+1}/{len(proxies)} using proxy: ...{proxy_url[-10:]}")
                proxy_config = GenericProxyConfig(https_url=proxy_url)
                api = YouTubeTranscriptApi(proxy_config=proxy_config)
            else:
                print(f"[YouTube] Attempting direct connection (no proxy)...")
                api = YouTubeTranscriptApi()

            transcript = api.fetch(video_id)
            full_text = " ".join([snippet.text for snippet in transcript])
            return full_text, None

        except Exception as e:
            last_error = str(e)
            print(f"[YouTube] Attempt {i+1} failed: {last_error}")
            continue

    # If all attempts failed
    return None, (
        f"Failed to fetch transcript after trying {len(proxies)} configuration(s). "
        f"Last error: {last_error}. "
        f"Please check your YOUTUBE_PROXY_URL environment variable."
    )

def analyze_style(transcript_text: str, api_key: str = None) -> str:
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
    return generate_content(prompt, model_name="gemini-3-flash-preview", api_key=api_key)
