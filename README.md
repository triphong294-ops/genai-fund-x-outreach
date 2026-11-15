# GenAI Fund — AI & Robotics Builder Outreach Prototype

A working human-in-the-loop (HITL) outreach tool designed for **GenAI Fund** to discover AI and robotics builders/founders on X, extract verifiable evidence from their profiles and recent posts, draft grounded personalized DMs, and safely dispatch 1-on-1 messages with strict idempotency.

## Quick Setup (< 5 Minutes)

### Option A: Hosted Web App (Zero Setup)
Open the hosted Streamlit URL and enter your `GEMINI_API_KEY` (and optional X API v2 credentials) in the left sidebar.

### Option B: Run Locally
```bash
git clone [https://github.com/triphong294-ops/genai-fund-x-outreach.git] (https://github.com/triphong294-ops/genai-fund-x-outreach.git)
cd genai-fund-x-outreach
pip install -r requirements.txt
streamlit run app.py
