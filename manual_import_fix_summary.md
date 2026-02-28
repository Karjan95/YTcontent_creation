# Summary of Actions: Fixing Manual Script Import & Shot Generation Limits

**Issue 1: "Narration locked (1 acts, 1 beats)" after pasting text**
When you pasted plain text into the manual script box, the system originally expected a JSON format. When JSON parsing naturally failed on plain text, the system attempted a fallback by wrapping your entire pasted text block into a single, massive "beat" so that the UI could proceed.

**Issue 2: Generating only 54 shots instead of ~176**
Because your entire script was packaged into exactly **1 beat**, our new backend parallel batching system (which triggers when there are >8 beats) didn't activate. The backend sent the entire script to Gemini in a single request. Generating 176 shots requires a massive JSON output, and Gemini hit its hard token limit (around 8,000 output tokens) midway through, truncating the output to 54 shots.

**The Fixes Implemented:**
1. **Frontend Plain Text Support (`ui/index.html`)**: 
   I explicitly updated the `importSceneBreakdown` function to officially support plain text pasting. If it detects that the input isn't JSON, it deliberately wraps it into a single raw text payload, providing a seamless user experience.

2. **Backend Smart Chunking (`execution/research_scriptwriter.py`)**: 
   I added a new chunk normalization pass right before the production table generation begins. The backend now inspects every single beat. If it sees a beat that is artificially massive (like a full pasted script exceeding 45 words), it automatically slices it up along sentence boundaries into smaller, safe sub-beats. 

**Result:**
Now, when you paste a giant wall of plain text, the frontend safely treats it as a single chunk, but the backend quietly slices it into ~20 smaller beats. This triggers the parallel batching system, which dispatches the job in safe chunks to Gemini, guaranteeing that all ~176 shots will be generated without hitting any API token limits!

---

### Summary of Actions: Implementing Pacing Tiers Feature

**Objective:** Give users granular control over the generated video's cut frequency (shots-per-minute). 

**The Implementation:**
1. **Frontend Pacing UI (`ui/index.html`)**: 
   I introduced a new "Pacing Style" dropdown to the Production Table interface. It features 5 distinct tiers: 
   - **Meditative** (~8.0s / 15 words)
   - **Relaxed** (~6.0s / 11 words)
   - **Standard** (~4.0s / 9 words)
   - **High Energy** (~2.0s / 5 words)
   - **Frenetic** (~1.2s / 3 words)

2. **Live Shot Estimation System**: 
   The frontend now proactively calculates and displays the `~Estimated Shots` required depending on the selected pacing tier and the length of the narration, instantly informing the user of the potential visual tempo and generation cost.

3. **Dynamic API Scaling (`execution/research_scriptwriter.py`)**: 
   To protect against Gemini's output token limits, the backend dynamically adjusts the `BEATS_PER_BATCH` configuration based on the pacing tier. For example, if the user selects *Frenetic* (which generates massive amounts of micro-shots rapidly accumulating JSON), the parallel batching system shrinks the batch chunk size from 8 down to 3 to keep Gemini safe. Conversely, *Meditative* combines beats into larger chunks of 12.

4. **Advanced Prompt Engineering (`execution/research_templates.py`)**: 
   The generation template now injects distinct cutting instructions depending on the tier. For the *Frenetic* prompt, it explicitly guides Gemini on how to perform "micro-cuts within single sentences" (e.g. splitting a 9-word sentence across 3 separate shots for rapid montage impact).

These backend and frontend integrations work in tandem to dynamically balance Gemini's hard token limitations against high-fidelity shot volume requests.
