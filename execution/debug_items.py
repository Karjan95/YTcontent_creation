
from youtube_transcript_api import YouTubeTranscriptApi

try:
    api = YouTubeTranscriptApi()
    res = api.fetch("dQw4w9WgXcQ")
    print("Type of result:", type(res))
    print("First item:", res[0])
    print("Type of first item:", type(res[0]))
except Exception as e:
    print(f"Error: {e}")
