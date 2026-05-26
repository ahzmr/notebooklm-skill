#!/usr/bin/env python3
"""
CDP-based NotebookLM question interface.
Connects to existing Chrome/Edge via CDP (port 9222) instead of launching new browser.
支持并发：每个查询独占一个新标签页，通过文件锁序列化 new_page() 创建。
"""

import argparse
import fcntl
import json
import sys
import time
import re
import tempfile
import hashlib
from pathlib import Path
from contextlib import contextmanager

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from patchright.sync_api import sync_playwright
from config import QUERY_INPUT_SELECTORS, RESPONSE_SELECTORS, LIBRARY_FILE

FOLLOW_UP_REMINDER = (
    "\n\nEXTREMELY IMPORTANT: Is that ALL you need to know? "
    "You can always ask another question! Think about it carefully: "
    "before you reply to the user, review their original request and this answer. "
    "If anything is still unclear or missing, ask me another comprehensive question "
    "that includes all necessary context (since each question opens a new browser session)."
)

CDP_ENDPOINT = "http://localhost:9222"

_LOCK_DIR = Path(tempfile.gettempdir())


def _notebook_lock_file(notebook_url: str) -> Path:
    """按笔记本 URL 生成独立的锁文件路径。
    同一笔记本 → 同一把锁（串行）；不同笔记本 → 不同的锁（并行）。
    """
    url_hash = hashlib.md5(notebook_url.encode()).hexdigest()[:12]
    return _LOCK_DIR / f"notebooklm_nb_{url_hash}.lock"


@contextmanager
def _notebook_lock(notebook_url: str, timeout: int = 300):
    """按笔记本粒度的文件锁，覆盖整个问答流程（new_page → 提交 → 等答案 → 关闭页面）。

    为什么要覆盖整个问答流程：
      NotebookLM 同一笔记本的所有标签页共享同一个对话上下文。
      若两个进程并发向同一笔记本提交问题，问题和答案会交叉出现在同一聊天流里，
      导致每个进程抓到错误的答案。因此同一笔记本必须完全串行。

    不同笔记本之间完全并行，互不影响。
    """
    lock_file = _notebook_lock_file(notebook_url)
    lock_fh = open(lock_file, 'w')
    deadline = time.time() + timeout
    print(f"  🔒 Acquiring notebook lock [{lock_file.name}]...")
    while True:
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.time() >= deadline:
                lock_fh.close()
                raise TimeoutError(
                    f"等待笔记本锁超时（{timeout}s）——同一笔记本有其他查询正在进行，请稍后重试"
                )
            time.sleep(0.5)
    print(f"  🔓 Notebook lock acquired — running exclusively")
    try:
        yield
    finally:
        fcntl.flock(lock_fh, fcntl.LOCK_UN)
        lock_fh.close()
        print(f"  🔓 Notebook lock released")


def get_notebook_url(notebook_id: str) -> str:
    if LIBRARY_FILE.exists():
        with open(LIBRARY_FILE) as f:
            library = json.load(f)
        notebooks = library.get('notebooks', {})
        if isinstance(notebooks, dict):
            nb = notebooks.get(notebook_id)
            if nb:
                return nb.get('url')
        else:
            for nb in notebooks:
                if nb.get('id') == notebook_id:
                    return nb['url']
    return None


def ask_notebooklm_cdp(question: str, notebook_url: str, cdp_endpoint: str = CDP_ENDPOINT) -> str:
    print(f"💬 Asking: {question[:80]}...")
    print(f"📚 Notebook: {notebook_url}")

    playwright = None
    browser = None
    page = None

    try:
        playwright = sync_playwright().start()

        # 连接到已运行的浏览器（不关闭它，避免中断其他并发查询）
        print(f"  🔌 Connecting to browser via CDP ({cdp_endpoint})...")
        browser = playwright.chromium.connect_over_cdp(cdp_endpoint)

        # 获取已有的浏览器上下文
        contexts = browser.contexts
        if not contexts:
            print("  ❌ No browser context available")
            return None
        context = contexts[0]
        print(f"  ✓ Using existing browser context")
        print("  ✓ Using existing browser's Google session")

        # =====================================================================
        # 按笔记本粒度加锁，整个问答流程（new_page→提交→等答案→关闭）都在锁内。
        # 同一笔记本：完全串行（共享对话上下文，并发会导致答案交叉）
        # 不同笔记本：完全并行（锁文件按 URL hash 隔离）
        # =====================================================================
        with _notebook_lock(notebook_url, timeout=300):
            page = context.new_page()
            print("  🌐 Opening notebook...")
            page.goto(notebook_url, wait_until="domcontentloaded", timeout=45000)

            # Wait for NotebookLM to load
            try:
                page.wait_for_url(re.compile(r"^https://notebooklm\.google\.com/"), timeout=15000)
            except Exception:
                current_url = page.url
                if 'accounts.google.com' in current_url:
                    print("  ❌ Redirected to Google login - need re-authentication")
                    page.close()
                    return None

            # Wait for query input
            print("  ⏳ Waiting for query input...")
            query_element = None
            for selector in QUERY_INPUT_SELECTORS:
                try:
                    query_element = page.wait_for_selector(selector, timeout=10000, state="visible")
                    if query_element:
                        print(f"  ✓ Found input: {selector}")
                        break
                except Exception:
                    continue

            if not query_element:
                try:
                    query_element = page.wait_for_selector("textarea", timeout=5000, state="visible")
                    if query_element:
                        print("  ✓ Found textarea (fallback)")
                except Exception:
                    pass

            if not query_element:
                print("  ❌ Could not find query input")
                page.close()
                return None

            # Type question
            print("  ⌨️  Typing question...")
            query_element.click()
            time.sleep(0.3)
            query_element.fill(question)
            time.sleep(0.5)

            # Submit
            print("  📤 Submitting...")
            page.keyboard.press("Enter")
            time.sleep(1)

            # Wait for response
            print("  ⏳ Waiting for answer...")
            answer = None
            stable_count = 0
            last_text = None
            deadline = time.time() + 120

            while time.time() < deadline:
                try:
                    thinking = page.query_selector('div.thinking-message')
                    if thinking and thinking.is_visible():
                        time.sleep(1)
                        continue
                except Exception:
                    pass

                for selector in RESPONSE_SELECTORS:
                    try:
                        elements = page.query_selector_all(selector)
                        if elements:
                            latest = elements[-1]
                            text = latest.inner_text().strip()
                            if text and len(text) > 20:
                                if text == last_text:
                                    stable_count += 1
                                    if stable_count >= 3:
                                        answer = text
                                        break
                                else:
                                    stable_count = 0
                                    last_text = text
                    except Exception:
                        continue

                if answer:
                    break
                time.sleep(1)

            page.close()

        # 锁已释放，下一个对同一笔记本的查询可以开始了
        if not answer:
            print("  ❌ Timeout waiting for answer")
            return None

        print("  ✅ Got answer!")
        return answer + FOLLOW_UP_REMINDER

    except Exception as e:
        print(f"  ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

    finally:
        # ⚠️ page 已在锁内的 with 块中关闭；这里仅作保险兜底（异常提前退出时）。
        # 绝不调用 browser.close()——那会终止宿主 Chrome，断掉所有并发查询。
        # playwright.stop() 只停止本进程的 playwright 客户端，不影响远端浏览器，安全。
        if page and not page.is_closed():
            try:
                page.close()
            except Exception:
                pass
        if playwright:
            try:
                playwright.stop()
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description='Ask NotebookLM via CDP connection')
    parser.add_argument('--question', required=True, help='Question to ask')
    parser.add_argument('--notebook-url', help='NotebookLM notebook URL')
    parser.add_argument('--notebook-id', help='Notebook ID from library')
    parser.add_argument('--cdp-endpoint', default=CDP_ENDPOINT, help='CDP endpoint')
    args = parser.parse_args()

    notebook_url = args.notebook_url
    if not notebook_url and args.notebook_id:
        notebook_url = get_notebook_url(args.notebook_id)
        if not notebook_url:
            print(f"❌ Notebook '{args.notebook_id}' not found in library")
            return 1

    if not notebook_url:
        print("❌ Must specify --notebook-url or --notebook-id")
        return 1

    answer = ask_notebooklm_cdp(args.question, notebook_url, args.cdp_endpoint)

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
