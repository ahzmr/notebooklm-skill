# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.5.0] - 2026-08-21

### Added
- **Native-mode global lock** (`config.NATIVE_GLOBAL_LOCK_KEY`, wrapped around `ask_question.py`'s per-notebook lock) - makes "callers may always ask in parallel" a uniform contract across both backends: CDP mode runs different notebooks truly in parallel (already stable), while native/local mode now safely auto-serializes *all* queries regardless of notebook, since concurrent launches previously contended for the same shared Chrome profile directory

### Changed
- **Concurrency docs rewritten as a contract, not a mechanism explanation** (`SKILL.md`) - callers no longer need to reason about locks/queues/hot-tabs themselves; a single table states what happens per mode, plus explicit guidance to fire one background call per notebook when a task spans multiple notebooks
- **`--notebook-id` promoted to the recommended default** in examples across `SKILL.md`; the active-notebook shortcut (`notebook_manager.py activate`) is now documented as a debugging convenience only, since relying on it is unsafe once calls are fired concurrently
- **Rebrand acknowledged: NotebookLM is now "Gemini Notebook"** (Google, 2026-07-16) - `SKILL.md` trigger phrases and description now recognize both names and both URL domains (`notebook.google.com` and legacy `notebooklm.google.com`); `README.md`/`README.zh-CN.md` lead with a rebrand callout. The skill's own name, scripts, and folder stay `notebooklm` for backward compatibility — only user-facing docs and triggers changed
- **README environment docs caught up with CDP mode**: `README.md`/`README.zh-CN.md`'s "Backends" section previously only had a two-row table with no setup detail; it now includes the host-browser launch command, the `curl localhost:9222/json/version` bridge check, and a summary of the parallel/serialize concurrency contract, so a reader doesn't have to open `SKILL.md` just to understand Docker/CDP mode
- **Compatibility broadened beyond Claude Code**: `README.md`/`README.zh-CN.md` now document that OpenCode (which reads the same `~/.claude/skills/` / `.claude/skills/` paths) also runs this skill; the "Local Claude Code Only" warning is now "Local Use Only" and names both agents

### Fixed
- **`references/api_reference.md` "Parallel Queries" example** used `ask_question.py` (native mode) to demonstrate concurrent queries across notebooks — this would actually contend on the shared Chrome profile directory and is not safe. Fixed to use `ask_cdp.py`, with a note on when each mode auto-parallelizes vs. auto-serializes

## [1.4.0] - 2026-08-21

### Added
- **CDP mode (`ask_cdp.py`)** - Connects to an existing Chrome/Edge on the host via `--remote-debugging-port=9222` instead of launching a browser, for environments (e.g. Docker) with no local Chrome
  - `run.py` auto-detects whether a local Chrome/Chromium is present and routes to `ask_cdp.py` when it isn't
- **`NotebookLMDriver`** (`notebooklm_driver.py`) - Single shared driver for DOM interaction, submit-and-confirm, and answer-stability detection, now used by `ask_cdp.py`, `ask_question.py`, and `browser_session.py` alike
- **Per-notebook concurrency control** (`concurrency.py`)
  - Per-notebook file lock fully serializes queries against the same notebook (shared chat context) while different notebooks run in parallel
  - CDP mode keeps one dedicated tab per notebook (tagged via `window.name`) and hands it off to a queued successor process instead of closing/reopening it every time
  - `ask_question.py` (native mode) now also serializes through the same per-notebook lock

### Changed
- Notebook URL resolution (`--notebook-url` / `--notebook-id` / active notebook) centralized in `config.resolve_notebook_url()`, shared by both `ask_cdp.py` and `ask_question.py`
- First-time setup now skips installing a local Chrome for Patchright when no local Chrome/Chromium/Edge is detected (`run.py` passes `--skip-browser-install` to `setup_environment.py`) — CDP mode never launches its own browser, so the install was wasted work and could fail needlessly in restricted containers

### Removed
- `browser_utils.StealthUtils` (dead code, no longer used now that `NotebookLMDriver` handles submission everywhere) and the dead `scripts/__init__.py` venv-bootstrap path (was never actually triggered by `run.py`)

## [1.3.0] - 2025-11-21

### Added
- **Modular Architecture** - Refactored codebase for better maintainability
  - New `config.py` - Centralized configuration (paths, selectors, timeouts)
  - New `browser_utils.py` - BrowserFactory and StealthUtils classes
  - Cleaner separation of concerns across all scripts

### Changed
- **Timeout increased to 120 seconds** - Long queries no longer timeout prematurely
  - `ask_question.py`: 30s → 120s
  - `browser_session.py`: 30s → 120s
  - Resolves Issue #4

### Fixed
- **Thinking Message Detection** - Fixed incomplete answers showing placeholder text
  - Now waits for `div.thinking-message` element to disappear before reading answer
  - Answers like "Reviewing the content..." or "Looking for answers..." no longer returned prematurely
  - Works reliably across all languages and NotebookLM UI changes

- **Correct CSS Selectors** - Updated to match current NotebookLM UI
  - Changed from `.response-content, .message-content` to `.to-user-container .message-text-content`
  - Consistent selectors across all scripts

- **Stability Detection** - Improved answer completeness check
  - Now requires 3 consecutive stable polls instead of 1 second wait
  - Prevents truncated responses during streaming

## [1.2.0] - 2025-10-28

### Added
- Initial public release
- NotebookLM integration via browser automation
- Session-based conversations with Gemini 2.5
- Notebook library management
- Knowledge base preparation tools
- Google authentication with persistent sessions
