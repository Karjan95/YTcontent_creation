
from youtube_transcript_api import YouTubeTranscriptApi
import inspect

print("Attributes:", dir(YouTubeTranscriptApi))

if hasattr(YouTubeTranscriptApi, 'get_transcript'):
    print("Has get_transcript")
else:
    print("Missing get_transcript")

if hasattr(YouTubeTranscriptApi, 'list_transcripts'):
    print("Has list_transcripts")

if hasattr(YouTubeTranscriptApi, 'fetch'):
    print("Has fetch. Signature:", inspect.signature(YouTubeTranscriptApi.fetch))
    
    # Try static call?
    try:
        print("Call fetch statically...")
        YouTubeTranscriptApi.fetch("dQw4w9WgXcQ")
    except TypeError as e:
        print(f"Static fetch failed: {e}")
        # Try instance call
        try:
            print("Call fetch with instance...")
            api = YouTubeTranscriptApi()
            res = api.fetch("dQw4w9WgXcQ")
            print("Instance fetch success! Items:", len(res))
        except Exception as e2:
            print(f"Instance fetch failed: {e2}")

