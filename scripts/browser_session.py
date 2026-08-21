#!/usr/bin/env python3
"""
Browser Session Management for NotebookLM
Individual browser session for persistent NotebookLM conversations.
Leverages NotebookLMDriver for standardized DOM manipulation and answer verification.
"""

import time
import sys
from typing import Any, Dict
from pathlib import Path

from patchright.sync_api import BrowserContext, Page

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from notebooklm_driver import NotebookLMDriver
from config import QUERY_TIMEOUT_SECONDS


class BrowserSession:
    """
    Represents a single persistent browser session for NotebookLM

    Each session gets its own Page (tab) within a shared BrowserContext,
    allowing for contextual conversations where NotebookLM remembers
    previous messages.
    """

    def __init__(self, session_id: str, context: BrowserContext, notebook_url: str):
        self.id = session_id
        self.created_at = time.time()
        self.last_activity = time.time()
        self.message_count = 0
        self.notebook_url = notebook_url
        self.context = context
        self.page = None
        self.driver = NotebookLMDriver()

        self._initialize()

    def _initialize(self):
        """Initialize the browser session and navigate to NotebookLM"""
        print(f"🚀 Creating session {self.id}...")

        # Create new page (tab) in context
        self.page = self.context.new_page()
        print(f"  🌐 Navigating to NotebookLM...")

        try:
            self.page.goto(self.notebook_url, wait_until="domcontentloaded", timeout=45000)

            # Check if login is needed
            if "accounts.google.com" in self.page.url:
                raise RuntimeError("Authentication required. Please run auth_manager.py setup first.")

            # Wait for query input
            query_el, _ = self.driver.find_query_input(self.page, timeout_ms=10000)
            if not query_el:
                raise RuntimeError("NotebookLM query input not found during session initialization")

            print(f"✅ Session {self.id} ready!")

        except Exception as e:
            print(f"❌ Failed to initialize session: {e}")
            if self.page:
                try:
                    self.page.close()
                except Exception:
                    pass
            raise

    def ask(self, question: str, timeout: int = QUERY_TIMEOUT_SECONDS) -> Dict[str, Any]:
        """
        Ask a question in this persistent session.
        """
        try:
            self.last_activity = time.time()
            self.message_count += 1

            print(f"💬 [{self.id}] Asking: {question[:80]}...")

            answer = self.driver.ask(self.page, question, is_reused=True, timeout=timeout)

            if not answer:
                raise Exception("Empty or timeout response from NotebookLM")

            print(f"  ✅ Got response ({len(answer)} chars)")

            return {
                "status": "success",
                "question": question,
                "answer": answer,
                "session_id": self.id,
                "notebook_url": self.notebook_url
            }

        except Exception as e:
            print(f"  ❌ Error: {e}")
            return {
                "status": "error",
                "question": question,
                "error": str(e),
                "session_id": self.id
            }

    def reset(self):
        """Reset the chat by reloading the page"""
        print(f"🔄 Resetting session {self.id}...")

        self.page.reload(wait_until="domcontentloaded")
        self.driver.find_query_input(self.page, timeout_ms=10000)

        previous_count = self.message_count
        self.message_count = 0
        self.last_activity = time.time()

        print(f"✅ Session reset (cleared {previous_count} messages)")
        return previous_count

    def close(self):
        """Close this session and clean up resources"""
        print(f"🛑 Closing session {self.id}...")

        if self.page:
            try:
                self.page.close()
            except Exception as e:
                print(f"  ⚠️ Error closing page: {e}")

        print(f"✅ Session {self.id} closed")

    def get_info(self) -> Dict[str, Any]:
        """Get information about this session"""
        return {
            "id": self.id,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "age_seconds": time.time() - self.created_at,
            "inactive_seconds": time.time() - self.last_activity,
            "message_count": self.message_count,
            "notebook_url": self.notebook_url
        }

    def is_expired(self, timeout_seconds: int = 900) -> bool:
        """Check if session has expired (default: 15 minutes)"""
        return (time.time() - self.last_activity) > timeout_seconds


if __name__ == "__main__":
    print("Browser Session Module - Use ask_question.py / ask_cdp.py for main interface")
