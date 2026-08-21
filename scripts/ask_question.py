#!/usr/bin/env python3
"""
Simple NotebookLM Question Interface (Native Chrome mode)
Launches a persistent browser instance and queries NotebookLM.

Implements hybrid auth approach:
- Persistent browser profile (user_data_dir) for fingerprint consistency
- Manual cookie injection from state.json for session cookies (Playwright bug workaround)
- Shared NotebookLMDriver and per-notebook serialization lock for maximum reliability.
"""

import argparse
import os
import re
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from patchright.sync_api import sync_playwright
from auth_manager import AuthManager
from config import (
    LOCK_TIMEOUT_SECONDS,
    FOLLOW_UP_REMINDER,
    resolve_notebook_url,
    DEFAULT_CDP_ENDPOINT,
)
from concurrency import (
    notebook_lock,
    register_queue,
    unregister_queue,
    setup_queue_signal_handlers,
    restore_signal_handlers,
)
from browser_utils import BrowserFactory
from notebooklm_driver import NotebookLMDriver


def ask_notebooklm(
    question: str,
    notebook_url: str,
    headless: bool = True
) -> str:
    """
    通过本地独立启动的浏览器向 NotebookLM 提问。
    """
    auth = AuthManager()

    if not auth.is_authenticated():
        print("⚠️ Not authenticated. Run: python auth_manager.py setup")
        return None

    print(f"💬 Asking: {question[:80]}...")
    print(f"📚 Notebook: {notebook_url}")

    my_pid = os.getpid()
    register_queue(notebook_url, my_pid)
    orig_sigint, orig_sigterm = setup_queue_signal_handlers(notebook_url, my_pid)

    playwright = None
    context = None
    page = None
    driver = NotebookLMDriver()

    try:
        # 使用按笔记本粒度的文件锁，防止本地多进程争抢 profile 或互相干扰
        with notebook_lock(notebook_url, timeout=LOCK_TIMEOUT_SECONDS):
            playwright = sync_playwright().start()

            # 启动持久化上下文
            context = BrowserFactory.launch_persistent_context(
                playwright,
                headless=headless
            )

            # 打开新页面
            page = context.new_page()
            print("  🌐 Opening notebook...")
            page.goto(notebook_url, wait_until="domcontentloaded", timeout=45000)

            # 校验是否重定向到了登录页
            try:
                page.wait_for_url(re.compile(r"^https://(notebook|notebooklm)\.google\.com/"), timeout=15000)
            except Exception:
                current_url = page.url
                if 'accounts.google.com' in current_url:
                    print("  ❌ Redirected to Google login - please re-authenticate")
                    return None

            # 执行核心问答流程
            answer = driver.ask(page, question, is_reused=False)

        if not answer:
            print("  ❌ Timeout or failed waiting for answer")
            return None

        print("  ✅ Got answer!")
        return answer + FOLLOW_UP_REMINDER

    except Exception as e:
        print(f"  ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

    finally:
        restore_signal_handlers(orig_sigint, orig_sigterm)
        unregister_queue(notebook_url, my_pid)

        if context:
            try:
                context.close()
            except Exception:
                pass

        if playwright:
            try:
                playwright.stop()
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description='Ask NotebookLM a question (Native mode)')
    parser.add_argument('--question', required=True, help='Question to ask')
    parser.add_argument('--notebook-url', help='NotebookLM notebook URL')
    parser.add_argument('--notebook-id', help='Notebook ID from library')
    parser.add_argument('--show-browser', action='store_true', help='Show browser window')
    parser.add_argument('--cdp-endpoint', default=DEFAULT_CDP_ENDPOINT, help='Ignored in native mode, kept for compatibility')

    args = parser.parse_args()

    notebook_url = resolve_notebook_url(args.notebook_id, args.notebook_url)
    if not notebook_url:
        print("❌ Must specify --notebook-url or --notebook-id (or set an active notebook)")
        return 1

    if not args.notebook_url and not args.notebook_id:
        print("📚 Using active notebook from library")

    answer = ask_notebooklm(
        question=args.question,
        notebook_url=notebook_url,
        headless=not args.show_browser
    )

    if answer:
        print("\n" + "=" * 60)
        print(f"Question: {args.question[:100]}")
        print("=" * 60)
        print()
        print(answer)
        print()
        print("=" * 60)
        return 0
    else:
        print("\n❌ Failed to get answer")
        return 1


if __name__ == "__main__":
    sys.exit(main())
