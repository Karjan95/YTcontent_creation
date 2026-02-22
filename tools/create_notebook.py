import sys
import argparse
from notebooklm_mcp.auth import load_cached_tokens
from notebooklm_mcp.api_client import NotebookLMClient

def main():
    parser = argparse.ArgumentParser(description='Create a new NotebookLM notebook')
    parser.add_argument('--title', type=str, default='New Notebook', help='Title of the notebook')
    args = parser.parse_args()

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
    
    print(f"Creating notebook with title: '{args.title}'...")
    try:
        notebook = client.create_notebook(title=args.title)
        if notebook:
            print(f"\nSuccessfully created notebook!")
            print(f"Title: {notebook.title}")
            print(f"ID: {notebook.id}")
            print(f"URL: {notebook.url}")
        else:
            print("Failed to create notebook (returned None).")
            sys.exit(1)
            
    except Exception as e:
        print(f"Error creating notebook: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
