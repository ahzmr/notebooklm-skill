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
from collections import Counter
from contextlib import contextmanager

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from patchright.sync_api import sync_playwright
from config import (
    QUERY_INPUT_SELECTORS,
    USER_MESSAGE_SELECTORS,
    SUBMIT_BUTTON_SELECTORS,
    LIBRARY_FILE,
)

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

            # 按"用户问题原文"精确定位答案。
            # 关键背景：改版后 NotebookLM 的聊天消息在 DOM 里【不是按时间顺序排列】的，
            # 新提交的问答对可能插在历史中间，所以绝不能用"最后一个 DOM 元素"当最新答案。
            # 每个 .chat-message-pair 内是一问一答，因此唯一可靠的做法是：
            # 找到 user 气泡文本 == 本次问题的那个 pair，读取它配对的 bot 答案。
            # 这同时根治两个 bug：
            #   - 抓不到答案（答案不在 els[-1]）
            #   - 多会话互串（每个会话只认自己问题原文对应的答案）
            # 返回"与 q 完全相同的所有 pair 的答案文本列表"（一般只有 1 个；
            # 历史里若有完全相同的旧问题则可能多个，由调用方用 seen_before 排除）。
            def _exact_q_answers(q):
                try:
                    return page.evaluate(
                        """(q) => {
                            const nz = s => (s||'').replace(/\\s+/g,'');
                            const tq = nz(q);
                            const out = [];
                            document.querySelectorAll('.chat-message-pair').forEach(p => {
                                const u = p.querySelector('.from-user-message-card-content');
                                if (u && nz(u.innerText) === tq) {
                                    const a = p.querySelector('.to-user-container .message-text-content');
                                    out.push(a ? a.innerText.trim() : '');
                                }
                            });
                            return out;
                        }""",
                        q,
                    )
                except Exception:
                    return []

            # 统计当前已提交的"用户问题气泡"数量——提交成功的硬信号。
            def _count_user_msgs():
                for selector in USER_MESSAGE_SELECTORS:
                    try:
                        els = page.query_selector_all(selector)
                        if els:
                            return len(els)
                    except Exception:
                        continue
                return 0

            # 提交前先稍等历史加载，用 Counter 记录历史中与本次问题完全相同的旧答案计数。
            # Counter 差集（answers_now - answers_before）能精确识别新增的答案，
            # 即使新答案与旧答案文本完全一样也不会被误过滤。
            time.sleep(2)
            answers_before = Counter(a for a in _exact_q_answers(question) if a)

            # =====================================================================
            # 提交问题：必须确认"用户问题气泡数 +1"才算成功。
            # 改版后 fresh tab 偶发丢键（输入框带 autocomplete-trigger，Enter 可能被
            # 补全面板吞掉，或页面尚未完全就绪），仅靠 Enter 会静默失败导致空等超时。
            # 策略：填入→Enter→确认；未确认则兜底点击提交按钮 / 重新填入再试，最多 3 轮。
            # =====================================================================
            user_before = _count_user_msgs()
            submitted = False
            for attempt in range(1, 4):
                print(f"  ⌨️  Typing & submitting (attempt {attempt})...")
                page.bring_to_front()  # 多标签并发时，确保焦点/键盘事件作用于本标签
                query_element.click()
                time.sleep(0.3)
                # 输入框可能残留上次内容，先清空再填
                try:
                    query_element.fill("")
                except Exception:
                    pass
                query_element.fill(question)
                time.sleep(0.5)

                page.bring_to_front()
                page.keyboard.press("Enter")

                # 确认提交：等待用户气泡数增加（最多 ~6s）
                confirm_deadline = time.time() + 6
                while time.time() < confirm_deadline:
                    if _count_user_msgs() > user_before:
                        submitted = True
                        break
                    time.sleep(0.5)
                if submitted:
                    print("  📤 Submitted (confirmed).")
                    break

                # Enter 没生效——兜底点击提交按钮（输入框此时通常仍有文本）
                print("  ⚠️  Enter 未确认提交，尝试点击提交按钮...")
                clicked = False
                for btn_sel in SUBMIT_BUTTON_SELECTORS:
                    try:
                        btn = page.query_selector(btn_sel)
                        if btn and btn.is_visible():
                            btn.click()
                            clicked = True
                            break
                    except Exception:
                        continue
                if clicked:
                    confirm_deadline = time.time() + 6
                    while time.time() < confirm_deadline:
                        if _count_user_msgs() > user_before:
                            submitted = True
                            break
                        time.sleep(0.5)
                if submitted:
                    print("  📤 Submitted via button (confirmed).")
                    break
                # 本轮失败，下一轮重新填入再试

            if not submitted:
                print("  ❌ 多次尝试仍未能提交问题")
                page.close()
                return None

            # =====================================================================
            # 等待答案：用 Counter 差集找到本次新增的答案，等它稳定。
            # thinking 占位态（"Processing material…"）以省略号结尾，用 _is_thinking
            # 识别；但真实答案也可能以省略号结尾，因此不是直接过滤，而是要求更长的
            # 稳定期（6 次 vs 普通答案 3 次）来区分占位态和真答案。
            # =====================================================================
            print("  ⏳ Waiting for answer...")
            answer = None
            stable_count = 0
            last_text = None
            deadline = time.time() + 120

            def _is_thinking(t):
                return t.endswith("...") or t.endswith("…")

            while time.time() < deadline:
                answers_now = Counter(a for a in _exact_q_answers(question) if a)
                new_answers = list((answers_now - answers_before).elements())
                non_thinking = [a for a in new_answers if not _is_thinking(a)]
                text = non_thinking[-1] if non_thinking else (
                    new_answers[-1] if new_answers else None)

                if text:
                    if text == last_text:
                        stable_count += 1
                        threshold = 6 if _is_thinking(text) else 3
                        if stable_count >= threshold:
                            answer = text
                            break
                    else:
                        stable_count = 0
                        last_text = text

                time.sleep(1.5)

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
