---
name: notebooklm
description: Use this skill to query your Google NotebookLM (now rebranded "Gemini Notebook") notebooks directly from Claude Code, OpenCode, or any other Agent Skills-compatible tool, for source-grounded, citation-backed answers from Gemini. Browser automation, library management, persistent auth. Drastically reduced hallucinations through document-only responses.
---

# NotebookLM Research Assistant Skill

Interact with Google NotebookLM — renamed "Gemini Notebook" by Google on 2026-07-16, same product and URLs, new name — to query documentation with Gemini's source-grounded answers. Each question runs in an isolated browser session/tab, retrieves the answer exclusively from your uploaded documents, and closes.

## When to Use This Skill

Trigger when user:
- Mentions NotebookLM or Gemini Notebook explicitly (either name — same product)
- Shares a notebook URL (`https://notebook.google.com/notebook/...` or the legacy `https://notebooklm.google.com/notebook/...`)
- Asks to query their notebooks/documentation
- Wants to add documentation to NotebookLM library
- Uses phrases like "ask my NotebookLM", "ask my Gemini Notebook", "check my docs", "query my notebook"

## ⚠️ CRITICAL: Add Command - Smart Discovery

When user wants to add a notebook without providing details:

**SMART ADD (Recommended)**: Query the notebook first to discover its content:
```bash
# Step 1: Query the notebook about its content
python scripts/run.py ask_question.py --question "What is the content of this notebook? What topics are covered? Provide a complete overview briefly and concisely" --notebook-url "[URL]"

# Step 2: Use the discovered information to add it
python scripts/run.py notebook_manager.py add --url "[URL]" --name "[Based on content]" --description "[Based on content]" --topics "[Based on content]"
```

**MANUAL ADD**: If user provides all details:
- `--url` - The NotebookLM URL
- `--name` - A descriptive name
- `--description` - What the notebook contains (REQUIRED!)
- `--topics` - Comma-separated topics (REQUIRED!)

NEVER guess or use generic descriptions! If details missing, use Smart Add to discover them.

## Critical: Always Use run.py Wrapper

**NEVER call scripts directly. ALWAYS use `python scripts/run.py [script]`:**

```bash
# ✅ CORRECT - Always use run.py:
python scripts/run.py auth_manager.py status
python scripts/run.py notebook_manager.py list
python scripts/run.py ask_question.py --question "..."

# ❌ WRONG - Never call directly:
python scripts/auth_manager.py status  # Fails without venv!
```

The `run.py` wrapper automatically:
1. Creates `.venv` if needed
2. Installs all dependencies
3. Activates environment
4. Executes script properly

## Core Workflow

### Step 1: Check Environment

`run.py` auto-selects the query backend by detecting whether a local Chrome is available. **The primary environment is Docker (CDP mode); Mac/native is the secondary fallback.**

| Environment | Detected when | Backend | Auth |
|-------------|---------------|---------|------|
| **Docker / container (PRIMARY)** | no local Chrome | `ask_cdp.py` — attaches to the **host** browser via CDP on `localhost:9222` | reuses the host browser's logged-in Google session |
| Mac / native Linux (secondary) | Chrome installed locally | `ask_question.py` — launches its own browser | saved auth via `auth_manager.py` |

#### Primary: Docker / container (CDP mode)

In Docker there is no local Chrome, so `run.py` routes every query to `ask_cdp.py`, which attaches to a Chromium-based browser running **on the host** and reuses its Google session — no separate login step is needed.

**Prerequisite — keep a host browser running in the background with remote debugging.** Start it once on the host and leave it running so the skill can attach at any time:
```bash
# On the host terminal (run once, keep it alive in the background):
open -a "Microsoft Edge" --args --remote-debugging-port=9222
# or:  open -a "Google Chrome" --args --remote-debugging-port=9222
```

**Verify the bridge from inside the container before querying:**
```bash
curl -s http://localhost:9222/json/version   # should return browser version JSON
```
If this returns nothing, the host browser is not running with `--remote-debugging-port=9222` (see Troubleshooting). If it connects but redirects to a Google login, log in manually in the host browser once.

#### Secondary: Mac / native Linux (local browser)

Only when Chrome is installed in the same environment as the skill. `run.py` then uses `ask_question.py`, which launches its own browser using saved auth. Check auth status first:
```bash
python scripts/run.py auth_manager.py status
# If not authenticated:
python scripts/run.py auth_manager.py setup
```

### Step 2: Manage Notebook Library

```bash
# List all notebooks
python scripts/run.py notebook_manager.py list

# BEFORE ADDING: Ask user for metadata if unknown!
# "What does this notebook contain?"
# "What topics should I tag it with?"

# Add notebook to library (ALL parameters are REQUIRED!)
python scripts/run.py notebook_manager.py add \
  --url "https://notebooklm.google.com/notebook/..." \
  --name "Descriptive Name" \
  --description "What this notebook contains" \  # REQUIRED - ASK USER IF UNKNOWN!
  --topics "topic1,topic2,topic3"  # REQUIRED - ASK USER IF UNKNOWN!

# Search notebooks by topic
python scripts/run.py notebook_manager.py search --query "keyword"

# Set active notebook (debugging convenience only — always pass --notebook-id
# explicitly instead of relying on this, especially when asking multiple
# notebooks concurrently; see "Concurrency" below)
python scripts/run.py notebook_manager.py activate --id notebook-id

# Remove notebook
python scripts/run.py notebook_manager.py remove --id notebook-id
```

### Quick Workflow
1. Check library: `python scripts/run.py notebook_manager.py list`
2. Ask question: `python scripts/run.py ask_question.py --question "..." --notebook-id ID`

> `ask_question.py` is automatically redirected to `ask_cdp.py` (CDP mode) by `run.py` whenever no local Chrome is present (i.e. in Docker).

### Step 3: Ask Questions

```bash
# Recommended: always specify --notebook-id explicitly
python scripts/run.py ask_question.py --question "..." --notebook-id notebook-id

# Query with notebook URL directly
python scripts/run.py ask_question.py --question "..." --notebook-url "https://..."

# Basic query (uses active notebook if set) — debugging convenience only,
# avoid this form when asking multiple notebooks concurrently
python scripts/run.py ask_question.py --question "Your question here"

# Custom CDP endpoint (if browser is not on localhost:9222)
python scripts/run.py ask_cdp.py --question "..." --notebook-id ID --cdp-endpoint "http://HOST:9222"
```

### Concurrency: You Can Always Ask in Parallel

The contract is simple: **callers may always fire off multiple questions in parallel — the implementation decides internally whether to actually run them concurrently or queue them.**

| Situation | What actually happens |
|-----------|------------------------|
| CDP mode + different notebooks | Runs truly in parallel (verified stable) |
| CDP mode + same notebook | Auto-queued and serialized, with hot-tab handoff to the next waiter |
| Native/local browser mode | Everything is auto-serialized globally (shared Chrome profile — not yet adapted for parallelism) |

**When a task spans multiple notebooks** (cross-notebook research, comparing notebooks, etc.), proactively fire one background call per notebook instead of asking sequentially:

```bash
# Fire all notebooks in parallel, each logging to its own file
python scripts/run.py ask_cdp.py --question "Q1..." --notebook-id "notebook-a" > /tmp/nb_a.log 2>&1 &
python scripts/run.py ask_cdp.py --question "Q2..." --notebook-id "notebook-b" > /tmp/nb_b.log 2>&1 &
wait
# Then read each log and synthesize
```

Multiple questions to the *same* notebook don't need any special handling either — fire them the same way; the lock queues them automatically. Always pass `--notebook-id` (or `--notebook-url`) explicitly rather than relying on the active notebook, so parallel calls can't be confused about which notebook they belong to.

## Follow-Up Mechanism (CRITICAL)

Every NotebookLM answer ends with: **"EXTREMELY IMPORTANT: Is that ALL you need to know?"**

**Required Claude Behavior:**
1. **STOP** - Do not immediately respond to user
2. **ANALYZE** - Compare answer to user's original request
3. **IDENTIFY GAPS** - Determine if more information needed
4. **ASK FOLLOW-UP** - If gaps exist, immediately ask:
   ```bash
   python scripts/run.py ask_question.py --question "Follow-up with context..."
   ```
5. **REPEAT** - Continue until information is complete
6. **SYNTHESIZE** - Combine all answers before responding to user

## Script Reference

### Authentication Management (`auth_manager.py`)
```bash
python scripts/run.py auth_manager.py setup    # Initial setup (browser visible)
python scripts/run.py auth_manager.py status   # Check authentication
python scripts/run.py auth_manager.py reauth   # Re-authenticate (browser visible)
python scripts/run.py auth_manager.py clear    # Clear authentication
```

### Notebook Management (`notebook_manager.py`)
```bash
python scripts/run.py notebook_manager.py add --url URL --name NAME --description DESC --topics TOPICS
python scripts/run.py notebook_manager.py list
python scripts/run.py notebook_manager.py search --query QUERY
python scripts/run.py notebook_manager.py activate --id ID
python scripts/run.py notebook_manager.py remove --id ID
python scripts/run.py notebook_manager.py stats
```

### Question Interface (`ask_question.py`)
```bash
python scripts/run.py ask_question.py --question "..." [--notebook-id ID] [--notebook-url URL] [--show-browser]
```

### Data Cleanup (`cleanup_manager.py`)
```bash
python scripts/run.py cleanup_manager.py                    # Preview cleanup
python scripts/run.py cleanup_manager.py --confirm          # Execute cleanup
python scripts/run.py cleanup_manager.py --preserve-library # Keep notebooks
```

## Environment Management

The virtual environment is automatically managed:
- First run creates `.venv` automatically
- Dependencies install automatically
- Chrome installs automatically for the native/secondary backend — skipped entirely on first run if no local Chrome is found, since CDP mode then connects to the host browser instead
- Everything isolated in skill directory

Manual setup (only if automatic fails):
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
python -m patchright install chromium
```

## Data Storage

All data stored in the skill's `data/` directory (in Docker this is the bind-mounted skill path on the host):
- `library.json` - Notebook metadata
- `auth_info.json` - Authentication status
- `browser_state/` - Browser cookies and session

**Security:** Protected by `.gitignore`, never commit to git.

## Configuration

Optional `.env` file in skill directory:
```env
HEADLESS=false           # Browser visibility
SHOW_BROWSER=false       # Default browser display
STEALTH_ENABLED=true     # Human-like behavior
TYPING_WPM_MIN=160       # Typing speed
TYPING_WPM_MAX=240
DEFAULT_NOTEBOOK_ID=     # Default notebook
```

## Decision Flow

```
User mentions NotebookLM
    ↓
Check/Add notebook → python scripts/run.py notebook_manager.py list/add
    ↓
Ask question → python scripts/run.py ask_question.py --question "..." --notebook-id ID
    ↓  run.py auto-detects backend:
    ↓     Docker (no local Chrome, PRIMARY) → ask_cdp.py → host browser on :9222
    ↓     Mac/native (Chrome installed)     → ask_question.py → own browser
    ↓
See "Is that ALL you need?" → Ask follow-ups until complete
    ↓
Synthesize and respond to user
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `curl localhost:9222` returns nothing | Start Chrome/Edge on the host with `--remote-debugging-port=9222` (Docker/CDP mode depends on it) |
| CDP connects but redirected to Google login | Host browser not logged in to Google — log in manually in the open browser |
| ModuleNotFoundError | Use `run.py` wrapper |
| Rate limit (50/day) | Wait or switch Google account |
| Need auth-based launch (no CDP) | Use `ask_question.py` directly: `python scripts/ask_question.py ...` (bypasses redirect) |
| Notebook not found | Check with `notebook_manager.py list` |

## Best Practices

1. **Always use run.py** - Handles environment automatically and routes to CDP in Docker
2. **Keep the host browser running** - In Docker/CDP mode (the primary setup) the skill attaches to the existing logged-in browser on `localhost:9222`; leave it running in the background
3. **Always specify --notebook-id** - Don't rely on the implicit active notebook, especially when asking multiple notebooks concurrently
4. **Parallelize across notebooks** - When a task spans multiple notebooks, fire one background call per notebook instead of asking sequentially (see "Concurrency" above)
5. **Follow-up questions** - Don't stop at first answer
6. **Include context** - Each question opens a new tab; include relevant context
7. **Synthesize answers** - Combine multiple responses before replying to user

## Limitations

- Requires a Chrome/Edge instance running with `--remote-debugging-port=9222` on the host (Docker/CDP mode)
- Rate limits on free Google accounts (50 queries/day)
- Manual upload required (user must add docs to NotebookLM)
- Browser overhead (few seconds per question)

## Resources (Skill Structure)

**Important directories and files:**

- `scripts/` - All automation scripts (ask_question.py, notebook_manager.py, etc.)
- `data/` - Local storage for authentication and notebook library
- `references/` - Extended documentation:
  - `api_reference.md` - Detailed API documentation for all scripts
  - `troubleshooting.md` - Common issues and solutions
  - `usage_patterns.md` - Best practices and workflow examples
- `.venv/` - Isolated Python environment (auto-created on first run)
- `.gitignore` - Protects sensitive data from being committed
