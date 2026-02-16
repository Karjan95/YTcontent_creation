# Content Creation Project

An AI-powered content creation tool that automates research, scriptwriting, and media generation using Google Gemini.

## Setup

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Environment Variables**
   Create a `.env` file in the root directory with your API keys:
   ```
   GEMINI_API_KEY=your_gemini_api_key
   ```

## Running the Server

Start the server using the provided script:

```bash
sh run_server.sh
```

Or manually:

```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)/execution
python3 execution/server.py
```

Access the UI at http://localhost:8080.
