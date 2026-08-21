<div align="center">

# NotebookLM Claude Code Skill

**Let [Claude Code](https://github.com/anthropics/claude-code) chat directly with NotebookLM for source-grounded answers based exclusively on your uploaded documents**

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-purple.svg)](https://www.anthropic.com/news/skills)
[![Based on](https://img.shields.io/badge/Based%20on-NotebookLM%20MCP-green.svg)](https://github.com/PleasePrompto/notebooklm-mcp)
[![GitHub](https://img.shields.io/github/stars/PleasePrompto/notebooklm-skill?style=social)](https://github.com/PleasePrompto/notebooklm-skill)

> Use this skill to query your Google NotebookLM (now rebranded "Gemini Notebook") notebooks directly from Claude Code, OpenCode, or any other tool that supports the Agent Skills format, for source-grounded, citation-backed answers from Gemini. Browser automation, library management, persistent auth. Drastically reduced hallucinations - answers only from your uploaded documents.

[Installation](#installation) • [Quick Start](#quick-start) • [Why NotebookLM](#why-notebooklm-not-local-rag) • [How It Works](#how-it-works) • [MCP Alternative](https://github.com/PleasePrompto/notebooklm-mcp)

[中文文档](./README.zh-CN.md)

</div>

---

## 📣 NotebookLM Is Now Gemini Notebook

On **July 16, 2026**, Google renamed NotebookLM to **Gemini Notebook** — same product, same notebooks, same sources, same shareable links, just a new name under the Gemini umbrella (existing `notebooklm.google.com` links keep working via redirect, alongside the new `notebook.google.com` domain). Rebranded, same great product.

This skill keeps its original `notebooklm` name for its scripts, folder, and skill identifier (renaming those would break existing installs and library files), and transparently handles URLs from **both** domains — nothing changes for you. The docs below still say "NotebookLM" throughout for that reason; read it as "NotebookLM / Gemini Notebook" wherever it appears.

---

## ⚠️ Important: Local Use Only (Claude Code, OpenCode, ...)

**This skill works ONLY with local, network-capable coding agents that support the Agent Skills format — confirmed working with [Claude Code](https://github.com/anthropics/claude-code) and [OpenCode](https://opencode.ai/) (which reads the same `~/.claude/skills/` and `.claude/skills/` paths) — NOT in the Claude.ai web UI.**

The web UI runs skills in a sandbox without network access, which this skill requires for browser automation. You must run a local agent like Claude Code or OpenCode on your own machine.

---

## The Problem

When you tell [Claude Code](https://github.com/anthropics/claude-code) to "search through my local documentation", here's what happens:
- **Massive token consumption**: Searching through documentation means reading multiple files repeatedly
- **Inaccurate retrieval**: Searches for keywords, misses context and connections between docs
- **Hallucinations**: When it can't find something, it invents plausible-sounding APIs
- **Manual copy-paste**: Switching between NotebookLM browser and your editor constantly

## The Solution

This Claude Code Skill lets [Claude Code](https://github.com/anthropics/claude-code) chat directly with [**NotebookLM**](https://notebooklm.google/) — Google's **source-grounded knowledge base** powered by Gemini 2.5 that provides intelligent, synthesized answers exclusively from your uploaded documents.

```
Your Task → Claude asks NotebookLM → Gemini synthesizes answer → Claude writes correct code
```

**No more copy-paste dance**: Claude asks questions directly and gets answers straight back in the CLI. It builds deep understanding through automatic follow-ups, getting specific implementation details, edge cases, and best practices.

---

## Why NotebookLM, Not Local RAG?

| Approach | Token Cost | Setup Time | Hallucinations | Answer Quality |
|----------|------------|------------|----------------|----------------|
| **Feed docs to Claude** | 🔴 Very high (multiple file reads) | Instant | Yes - fills gaps | Variable retrieval |
| **Web search** | 🟡 Medium | Instant | High - unreliable sources | Hit or miss |
| **Local RAG** | 🟡 Medium-High | Hours (embeddings, chunking) | Medium - retrieval gaps | Depends on setup |
| **NotebookLM Skill** | 🟢 Minimal | 5 minutes | **Minimal** - source-grounded only | Expert synthesis |

### What Makes NotebookLM Superior?

1. **Pre-processed by Gemini**: Upload docs once, get instant expert knowledge
2. **Natural language Q&A**: Not just retrieval — actual understanding and synthesis
3. **Multi-source correlation**: Connects information across 50+ documents
4. **Citation-backed**: Every answer includes source references
5. **No infrastructure**: No vector DBs, embeddings, or chunking strategies needed

---

## Installation

### The simplest installation ever:

```bash
# 1. Create skills directory (if it doesn't exist)
mkdir -p ~/.claude/skills

# 2. Clone this repository
cd ~/.claude/skills
git clone https://github.com/PleasePrompto/notebooklm-skill notebooklm

# 3. That's it! Open Claude Code and say:
"What are my skills?"
```

When you first use the skill, it automatically:
- Creates an isolated Python environment (`.venv`)
- Installs all dependencies including **Google Chrome**
- Sets up browser automation with Chrome (not Chromium) for maximum reliability
- Everything stays contained in the skill folder

**Note:** The setup uses real Chrome instead of Chromium for cross-platform reliability, consistent browser fingerprinting, and better anti-detection with Google services

---

## Quick Start

### 1. Check your skills

Say in Claude Code:
```
"What skills do I have?"
```

Claude will list your available skills including NotebookLM.

### 2. Authenticate with Google (one-time)

```
"Set up NotebookLM authentication"
```
*A Chrome window opens → log in with your Google account*

> In Docker/CDP mode this step isn't needed — the skill reuses whatever Google session is already logged into the host browser instead. See [Backends](#backends-local-browser-vs-cdp-docker) below.

### 3. Create your knowledge base

Go to [notebooklm.google.com](https://notebooklm.google.com) → Create notebook → Upload your docs:
- 📄 PDFs, Google Docs, markdown files
- 🔗 Websites, GitHub repos
- 🎥 YouTube videos
- 📚 Multiple sources per notebook

Share: **⚙️ Share → Anyone with link → Copy**

### 4. Add to your library

**Option A: Let Claude figure it out (Smart Add)**
```
"Query this notebook about its content and add it to my library: [your-link]"
```
Claude will automatically query the notebook to discover its content, then add it with appropriate metadata.

**Option B: Manual add**
```
"Add this NotebookLM to my library: [your-link]"
```
Claude will ask for a name and topics, then save it for future use.

### 5. Start researching

```
"What does my React docs say about hooks?"
```

Claude automatically selects the right notebook and gets the answer directly from NotebookLM.

---

## How It Works

This is a **Claude Code Skill** - a local folder containing instructions and scripts that Claude Code can use when needed. Unlike the [MCP server version](https://github.com/PleasePrompto/notebooklm-mcp), this runs directly in Claude Code without needing a separate server.

### Key Differences from MCP Server

| Feature | This Skill | MCP Server |
|---------|------------|------------|
| **Protocol** | Claude Skills | Model Context Protocol |
| **Installation** | Clone to `~/.claude/skills` | `claude mcp add ...` |
| **Sessions** | Fresh browser each question | Persistent chat sessions |
| **Compatibility** | Claude Code, OpenCode (local only) | Claude Code, Codex, Cursor, etc. |
| **Language** | Python | TypeScript |
| **Distribution** | Git clone | npm package |

### Architecture

```
~/.claude/skills/notebooklm/
├── SKILL.md              # Instructions for Claude
├── scripts/              # Python automation scripts
│   ├── ask_question.py   # Query NotebookLM
│   ├── notebook_manager.py # Library management
│   └── auth_manager.py   # Google authentication
├── .venv/                # Isolated Python environment (auto-created)
└── data/                 # Local notebook library
```

When you mention NotebookLM or send a notebook URL, Claude:
1. Loads the skill instructions
2. Runs the appropriate Python script
3. Opens a browser, asks your question
4. Returns the answer directly to you
5. Uses that knowledge to help with your task

---

## Core Features

### **Source-Grounded Responses**
NotebookLM significantly reduces hallucinations by answering exclusively from your uploaded documents. If information isn't available, it indicates uncertainty rather than inventing content.

### **Direct Integration**
No copy-paste between browser and editor. Claude asks and receives answers programmatically.

### **Smart Library Management**
Save NotebookLM links with tags and descriptions. Claude auto-selects the right notebook for your task.

### **Automatic Authentication**
One-time Google login, then authentication persists across sessions.

### **Self-Contained**
Everything runs in the skill folder with an isolated Python environment. No global installations.

### **Human-Like Automation**
Uses realistic typing speeds and interaction patterns to avoid detection.

---

## Common Commands

| What you say | What happens |
|--------------|--------------|
| *"Set up NotebookLM authentication"* | Opens Chrome for Google login |
| *"Add [link] to my NotebookLM library"* | Saves notebook with metadata |
| *"Show my NotebookLM notebooks"* | Lists all saved notebooks |
| *"Ask my API docs about [topic]"* | Queries the relevant notebook |
| *"Use the React notebook"* | Sets active notebook |
| *"Clear NotebookLM data"* | Fresh start (keeps library) |

---

## Real-World Examples

### Example 1: Workshop Manual Query

**User asks**: "Check my Suzuki GSR 600 workshop manual for brake fluid type, engine oil specs, and rear axle torque."

**Claude automatically**:
- Authenticates with NotebookLM
- Asks comprehensive questions about each specification
- Follows up when prompted "Is that ALL you need to know?"
- Provides accurate specifications: DOT 4 brake fluid, SAE 10W-40 oil, 100 N·m rear axle torque

![NotebookLM Chat Example](images/example_notebookchat.png)

### Example 2: Building Without Hallucinations

**You**: "I need to build an n8n workflow for Gmail spam filtering. Use my n8n notebook."

**Claude's internal process:**
```
→ Loads NotebookLM skill
→ Activates n8n notebook
→ Asks comprehensive questions with follow-ups
→ Synthesizes complete answer from multiple queries
```

**Result**: Working workflow on first try, no debugging hallucinated APIs.

---

## Technical Details

### Core Technology
- **Patchright**: Browser automation library (Playwright-based)
- **Python**: Implementation language for this skill
- **Stealth techniques**: Human-like typing and interaction patterns

Note: The MCP server uses the same Patchright library but via TypeScript/npm ecosystem.

### Backends: Local Browser vs. CDP (Docker)

`run.py` auto-detects the environment and picks a backend — no manual configuration needed:

| Environment | Backend | How |
|-------------|---------|-----|
| Chrome/Chromium installed locally (Mac, native Linux) | `ask_question.py` | Launches its own persistent browser with saved auth |
| No local Chrome (e.g. a Docker container) — **primary supported setup** | `ask_cdp.py` | Connects via Chrome DevTools Protocol to a browser already running on the **host** (`--remote-debugging-port=9222`), reusing its logged-in Google session |

**Running in Docker/CDP mode:** keep a Chromium-based browser running on the host with remote debugging enabled, and leave it open in the background:

```bash
# On the host (run once, keep it alive in the background):
open -a "Microsoft Edge" --args --remote-debugging-port=9222
# or:  open -a "Google Chrome" --args --remote-debugging-port=9222

# From inside the container, verify the bridge is reachable:
curl -s http://localhost:9222/json/version   # should return browser version JSON
```

No separate authentication step is needed in CDP mode — it just reuses whatever Google session is already logged in on the host browser.

**Concurrency:** callers can always fire off multiple questions in parallel — the implementation decides whether to actually run them concurrently or queue them. CDP mode runs queries against *different* notebooks truly in parallel and auto-queues queries against the *same* notebook (with hot-tab handoff); native/local mode auto-serializes everything globally, since every query there shares one browser profile directory.

See `SKILL.md` for the exact Docker/CDP setup steps, troubleshooting, and the full concurrency contract.

### Dependencies
- **patchright==1.55.2**: Browser automation
- **python-dotenv==1.0.0**: Environment configuration
- Automatically installed in `.venv` on first use

### Data Storage

All data is stored locally within the skill directory:

```
~/.claude/skills/notebooklm/data/
├── library.json       - Your notebook library with metadata
├── auth_info.json     - Authentication status info
└── browser_state/     - Browser cookies and session data
```

**Important Security Note:**
- The `data/` directory contains sensitive authentication data and personal notebooks
- It's automatically excluded from git via `.gitignore`
- NEVER manually commit or share the contents of the `data/` directory

### Session Model

Unlike the MCP server, this skill uses a **stateless model**:
- Each question opens a fresh browser
- Asks the question, gets the answer
- Adds a follow-up prompt to encourage Claude to ask more questions
- Closes the browser immediately

This means:
- No persistent chat context
- Each question is independent
- But your notebook library persists
- **Follow-up mechanism**: Each answer includes "Is that ALL you need to know?" to prompt Claude to ask comprehensive follow-ups

In CDP mode, the browser tab may briefly stay open after a question if another query for the *same* notebook is already queued up (so it can be reused instantly instead of reopened) — but from Claude's side, each question is still asked and answered independently.

For multi-step research, Claude automatically asks follow-up questions when needed.

---

## Limitations

### Skill-Specific
- **Local agents only** (Claude Code, OpenCode, ...) - Does not work in web UI (sandbox restrictions)
- **No session persistence** - Each question is independent
- **No follow-up context** - Can't reference "the previous answer"

### NotebookLM
- **Rate limits** - Free tier has daily query limits
- **Manual upload** - You must upload docs to NotebookLM first
- **Share requirement** - Notebooks must be shared publicly

---

## FAQ

**Why doesn't this work in the Claude web UI?**
The web UI runs skills in a sandbox without network access. Browser automation requires network access to reach NotebookLM.

**How is this different from the MCP server?**
This is a simpler, Python-based implementation that runs directly as a Claude Skill. The MCP server is more feature-rich with persistent sessions and works with multiple tools (Codex, Cursor, etc.).

**Can I use both this skill and the MCP server?**
Yes! They serve different purposes. Use the skill for quick Claude Code integration, use the MCP server for persistent sessions and multi-tool support.

**What if Chrome crashes?**
Run: `"Clear NotebookLM browser data"` and try again.

**Is my Google account secure?**
Chrome runs locally on your machine. Your credentials never leave your computer. Use a dedicated Google account if you're concerned.

---

## Troubleshooting

### Skill not found
```bash
# Make sure it's in the right location
ls ~/.claude/skills/notebooklm/
# Should show: SKILL.md, scripts/, etc.
```

### Authentication issues
Say: `"Reset NotebookLM authentication"`

### Browser crashes
Say: `"Clear NotebookLM browser data"`

### Dependencies issues
```bash
# Manual reinstall if needed
cd ~/.claude/skills/notebooklm
rm -rf .venv
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

---

## Disclaimer

This tool automates browser interactions with NotebookLM to make your workflow more efficient. However, a few friendly reminders:

**About browser automation:**
While I've built in humanization features (realistic typing speeds, natural delays, mouse movements) to make the automation behave more naturally, I can't guarantee Google won't detect or flag automated usage. I recommend using a dedicated Google account for automation rather than your primary account—think of it like web scraping: probably fine, but better safe than sorry!

**About CLI tools and AI agents:**
CLI tools like Claude Code, Codex, and similar AI-powered assistants are incredibly powerful, but they can make mistakes. Please use them with care and awareness:
- Always review changes before committing or deploying
- Test in safe environments first
- Keep backups of important work
- Remember: AI agents are assistants, not infallible oracles

I built this tool for myself because I was tired of the copy-paste dance between NotebookLM and my editor. I'm sharing it in the hope it helps others too, but I can't take responsibility for any issues, data loss, or account problems that might occur. Use at your own discretion and judgment.

That said, if you run into problems or have questions, feel free to open an issue on GitHub. I'm happy to help troubleshoot!

---

## Credits

This skill is inspired by my [**NotebookLM MCP Server**](https://github.com/PleasePrompto/notebooklm-mcp) and provides an alternative implementation as a Claude Code Skill:
- Both use Patchright for browser automation (TypeScript for MCP, Python for Skill)
- Skill version runs directly in Claude Code without MCP protocol
- Stateless design optimized for skill architecture

If you need:
- **Persistent sessions** → Use the [MCP Server](https://github.com/PleasePrompto/notebooklm-mcp)
- **Multiple tool support** (Codex, Cursor) → Use the [MCP Server](https://github.com/PleasePrompto/notebooklm-mcp)
- **Quick Claude Code integration** → Use this skill

---

## The Bottom Line

**Without this skill**: NotebookLM in browser → Copy answer → Paste in Claude → Copy next question → Back to browser...

**With this skill**: Claude researches directly → Gets answers instantly → Writes correct code

Stop the copy-paste dance. Start getting accurate, grounded answers directly in Claude Code.

```bash
# Get started in 30 seconds
cd ~/.claude/skills
git clone https://github.com/PleasePrompto/notebooklm-skill notebooklm
# Open Claude Code: "What are my skills?"
```

---

<div align="center">

Built as a Claude Code Skill adaptation of my [NotebookLM MCP Server](https://github.com/PleasePrompto/notebooklm-mcp)

For source-grounded, document-based research directly in Claude Code

</div>
