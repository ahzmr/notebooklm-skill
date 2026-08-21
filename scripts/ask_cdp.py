#!/usr/bin/env python3
"""
CDP-based NotebookLM question interface.
Connects to existing Chrome/Edge via CDP (port 9222) instead of launching a new browser.
Supports high-concurrency: per-notebook serialization lock, atomic queue inspection,
and hot-session tab reuse across sequential requests.
"""

import argparse
import os
import re
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from patchright.sync_api import sync_playwright
from config import (
    DEFAULT_CDP_ENDPOINT,
    LOCK_TIMEOUT_SECONDS,
    FOLLOW_UP_REMINDER,
    resolve_notebook_url,
)
from concurrency import (
    notebook_lock,
    register_queue,
    unregister_queue,
    has_alive_waiters,
    setup_queue_signal_handlers,
    restore_signal_handlers,
)
from notebooklm_driver import NotebookLMDriver


def ask_notebooklm_cdp(
    question: str,
    notebook_url: str,
    cdp_endpoint: str = DEFAULT_CDP_ENDPOINT
) -> str:
    """
    通过 CDP 连接到外部浏览器进行问答。
    包含排队机制、按笔记本锁控制、专属 Tab 热复用与责任链收尾。
    """
    print(f"💬 Asking: {question[:80]}...")
    print(f"📚 Notebook: {notebook_url}")

    my_pid = os.getpid()

    # 1. 进程到达，立即在专属队列目录创建属于自己的 PID 文件（原子登记入队）
    register_queue(notebook_url, my_pid)

    # 2. 注册信号捕获：若在排队等锁或执行中被终止（Ctrl+C/kill），主动清理自己的 PID 文件
    orig_sigint, orig_sigterm = setup_queue_signal_handlers(notebook_url, my_pid)

    playwright = None
    browser = None
    page = None
    driver = NotebookLMDriver()

    try:
        # =====================================================================
        # 按笔记本粒度加锁，整个问答流程（提交→等答案）都在锁内。
        # 同一笔记本：完全串行（共享对话上下文，并发会导致答案交叉）
        # 不同笔记本：完全并行（锁文件按 URL hash 隔离）
        # =====================================================================
        with notebook_lock(notebook_url, timeout=LOCK_TIMEOUT_SECONDS):
            playwright = sync_playwright().start()

            # 在获得锁后连接 CDP，确保获取到宿主浏览器当前最新的实时标签页状态
            print(f"  🔌 Connecting to browser via CDP ({cdp_endpoint})...")
            browser = playwright.chromium.connect_over_cdp(cdp_endpoint)

            contexts = browser.contexts
            if not contexts:
                print("  ❌ No browser context available")
                return None
            context = contexts[0]
            print(f"  ✓ Using existing browser context")

            # 获取或新建专属托管页面
            page, is_reused = driver.get_or_create_managed_page(context, notebook_url)
            if is_reused:
                print("  ♻️  Reusing managed notebook tab (hot session)...")
            else:
                print("  🌐 Opening new notebook tab (cold start)...")
                # 冷启动新标签页时校验 URL 与登录态
                try:
                    page.wait_for_url(re.compile(r"^https://(notebook|notebooklm)\.google\.com/"), timeout=15000)
                except Exception:
                    current_url = page.url
                    if 'accounts.google.com' in current_url:
                        print("  ❌ Redirected to Google login - need re-authentication")
                        try:
                            page.close()
                        except Exception:
                            pass
                        return None

            # 执行核心问答流程
            answer = driver.ask(page, question, is_reused=is_reused)

            # =====================================================================
            # 责任链转交判定（Directory-based Queue Inspection）：
            # 1. 首先注销本进程在队列目录下的 PID 文件；
            # 2. 检查队列目录下是否还有其他真实存活的排队进程：
            #    - 若有排队者：保留 Tab 不关闭，释放执行锁让排队者秒级复用！
            #    - 若无排队者（自己是最后一个离开的人）：由当前进程负责 page.close() 关门收尾！
            # =====================================================================
            unregister_queue(notebook_url, my_pid)
            has_waiters = has_alive_waiters(notebook_url, my_pid)
            if has_waiters:
                print("  ⚡ Successor process is waiting in queue — keeping tab open for fast reuse.")
            else:
                print("  🗑️  No successor waiting — closing tab and cleaning session.")
                try:
                    if page and not page.is_closed():
                        page.close()
                except Exception:
                    pass

        # 锁已释放，下一个对同一笔记本的查询可以开始了
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
        # 恢复原有信号处理器
        restore_signal_handlers(orig_sigint, orig_sigterm)

        # 确保出队注销自己
        unregister_queue(notebook_url, my_pid)

        # 异常兜底：若未正常移交且无人排队，确保关闭页面
        if page and not page.is_closed() and not has_alive_waiters(notebook_url, my_pid):
            try:
                page.close()
            except Exception:
                pass

        # playwright.stop() 只停止本进程客户端连接，不关闭远端浏览器。
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
    parser.add_argument('--cdp-endpoint', default=DEFAULT_CDP_ENDPOINT, help='CDP endpoint')
    parser.add_argument('--show-browser', action='store_true', help='Ignored in CDP mode, kept for CLI compatibility')
    args = parser.parse_args()

    notebook_url = resolve_notebook_url(args.notebook_id, args.notebook_url)
    if not notebook_url:
        print("❌ Must specify --notebook-url or --notebook-id (or set an active notebook)")
        return 1

    if not args.notebook_url and not args.notebook_id:
        print("📚 Using active notebook from library")

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
