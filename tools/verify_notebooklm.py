
import sys
from notebooklm_mcp.auth import load_cached_tokens
from notebooklm_mcp.api_client import NotebookLMClient

def main():
    print("Loading cached tokens...")
    tokens = load_cached_tokens()
    if not tokens:
        print("Error: No cached tokens found. Please run 'notebooklm-mcp-auth' first.")
        sys.exit(1)
    
    print("Initializing NotebookLM client...")
    client = NotebookLMClient(
        cookies=tokens.cookies,
        csrf_token=tokens.csrf_token,
        session_id=tokens.session_id
    )
    
    print("Fetching notebooks...")
    try:
        notebooks = client.list_notebooks()
        print(f"\nSuccessfully found {len(notebooks)} notebooks:")
        for nb in notebooks:
            print(f"- {nb.title} (ID: {nb.id})")
    except Exception as e:
        print(f"Error fetching notebooks: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
