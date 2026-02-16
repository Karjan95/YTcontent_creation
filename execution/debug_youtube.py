
from youtube_transcript_api import YouTubeTranscriptApi

print("Attributes of YouTubeTranscriptApi:")
print(dir(YouTubeTranscriptApi))

try:
    print("\nTrying to fetch transcript for video ID 'dQw4w9WgXcQ'...")
    transcript = YouTubeTranscriptApi.get_transcript("dQw4w9WgXcQ")
    print("Success!")
except Exception as e:
    print(f"Error: {e}")
