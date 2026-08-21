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
import os
import signal
import uuid
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


def _queue_dir_path(notebook_url: str) -> Path:
    """按笔记本 URL 生成专属的进程排队登记目录"""
    url_hash = hashlib.md5(notebook_url.encode()).hexdigest()[:12]
    qdir = _LOCK_DIR / f"notebooklm_queue_{url_hash}"
    qdir.mkdir(parents=True, exist_ok=True)
    return qdir


def _register_queue(notebook_url: str, pid: int = None) -> Path:
    """进程到达，原子创建属于自己的独立 PID 文件（入队登记，零写锁竞争）"""
    p = pid if pid is not None else os.getpid()
    qdir = _queue_dir_path(notebook_url)
    pid_file = qdir / f"{p}.pid"
    try:
        pid_file.touch()
    except Exception:
        pass
    return pid_file


def _unregister_queue(notebook_url: str, pid: int = None):
    """进程结束或意外中断，删除自己的 PID 文件（出队注销）"""
    p = pid if pid is not None else os.getpid()
    qdir = _queue_dir_path(notebook_url)
    pid_file = qdir / f"{p}.pid"
    try:
        pid_file.unlink(missing_ok=True)
    except Exception:
        pass


def _has_alive_waiters(notebook_url: str, my_pid: int = None) -> bool:
    """
    检查当前笔记本队列目录下是否还有其他存活的排队进程：
    1. 忽略排除当前进程自己 (my_pid)；
    2. 对目录下每一个剩余的 .pid 文件，通过 os.kill(pid, 0) 极速检查存活性；
    3. 若发现死进程文件（如被 kill -9 强杀），顺手清理；
    4. 返回是否存在至少 1 个真实存活的排队者。
    """
    current_pid = my_pid if my_pid is not None else os.getpid()
    qdir = _queue_dir_path(notebook_url)
    if not qdir.exists():
        return False

    alive_count = 0
    for f in list(qdir.glob("*.pid")):
        try:
            target_pid = int(f.stem)
            if target_pid == current_pid:
                continue
            # 探测进程存活性
            try:
                os.kill(target_pid, 0)
                alive_count += 1
            except OSError:
                # 进程已经死亡，清理死文件
                f.unlink(missing_ok=True)
        except Exception:
            pass

    return alive_count > 0


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


def get_notebook_url(notebook_id: str = None) -> str:
    if LIBRARY_FILE.exists():
        with open(LIBRARY_FILE) as f:
            library = json.load(f)
        notebooks = library.get('notebooks', {})
        target_id = notebook_id or library.get('active_notebook_id')
        if not target_id:
            return None
        if isinstance(notebooks, dict):
            nb = notebooks.get(target_id)
            if nb:
                return nb.get('url')
        else:
            for nb in notebooks:
                if nb.get('id') == target_id:
                    return nb['url']
    return None


class ActionPacer:
    """通用操作节流器：保证两次 UI 操作间隔至少大于 min_interval 秒（默认 0.3s）"""
    def __init__(self, min_interval: float = 0.3):
        self.min_interval = min_interval
        self.last_action_time = 0.0

    def pace(self, custom_interval: float = None):
        interval = custom_interval if custom_interval is not None else self.min_interval
        now = time.time()
        elapsed = now - self.last_action_time
        if elapsed < interval:
            time.sleep(interval - elapsed)
        self.last_action_time = time.time()


def _wait_for_history_loaded(page, timeout: float = 5.0):
    """
    智能等待历史会话加载完成：
    若检测到加载指示器 (mat-spinner / progressbar)，等待其从 DOM 中消失；
    若没有加载指示器，快速检查后直接返回。
    """
    deadline = time.time() + timeout
    has_seen_spinner = False
    while time.time() < deadline:
        try:
            is_spinning = page.evaluate("""() => {
                const spinners = document.querySelectorAll('mat-spinner, mat-progress-bar, [role="progressbar"]');
                for (const s of spinners) {
                    if (s && s.offsetParent !== null) return true;
                }
                return false;
            }""")
            if is_spinning:
                has_seen_spinner = True
                time.sleep(0.05)
                continue
            else:
                if has_seen_spinner:
                    time.sleep(0.1)
                break
        except Exception:
            break


def _extract_notebook_uuid(url: str) -> str:
    """提取 NotebookLM URL 中的 notebook UUID 或主要标识"""
    m = re.search(r'/notebook/([a-zA-Z0-9_-]+)', url)
    return m.group(1) if m else url.rstrip('/')


def _get_or_create_notebook_page(context, notebook_url: str):
    """
    智能获取或新建专属托管的笔记本标签页：
    1. 专属所有权检查：使用浏览器原生的 window.name 持久化标签页标识，跨刷新/导航绝对不丢失；
    2. 严格跨笔记本隔离：只复用本笔记本的 Tab (tag == expected_tag)，绝不关闭或触碰其他笔记本的 Tab；
    3. 绝不触碰用户个人标签页（用户个人页 window.name 为空或不同）；
    4. 命中当前笔记本：激活并复用（热会话，耗时 ~0ms）；
    5. 未命中：冷启动新建 Tab，导航并设置 window.name 专属标记。
    返回: (page, is_reused)
    """
    nb_uuid = _extract_notebook_uuid(notebook_url)
    expected_tag = f"__notebooklm_managed_{nb_uuid}"
    matched_page = None

    for p in list(context.pages):
        try:
            if p.is_closed():
                continue
            # 读取 window.name 标记
            tag = p.evaluate("() => window.name || ''")
            if tag == expected_tag:
                p.bring_to_front()
                matched_page = p
                break
        except Exception:
            continue

    if matched_page:
        return matched_page, True

    # 未找到专属托管页面，冷启动新建
    page = context.new_page()
    page.goto(notebook_url, wait_until="domcontentloaded", timeout=45000)

    # 注入专属所有权标记到 window.name (HTML5 标准跨导航持久化)
    page.evaluate(
        """(tag) => {
            window.name = tag;
        }""",
        expected_tag,
    )
    return page, False


def ask_notebooklm_cdp(question: str, notebook_url: str, cdp_endpoint: str = CDP_ENDPOINT) -> str:
    print(f"💬 Asking: {question[:80]}...")
    print(f"📚 Notebook: {notebook_url}")

    my_pid = os.getpid()

    # 1. 进程到达，立即在专属队列目录创建属于自己的 PID 文件（原子登记入队）
    _register_queue(notebook_url, my_pid)

    # 2. 注册信号捕获：若在排队等锁或执行中被终止（Ctrl+C/kill），主动清理自己的 PID 文件
    def _sig_handler(signum, frame):
        try:
            _unregister_queue(notebook_url, my_pid)
        except Exception:
            pass
        sys.exit(128 + signum)

    orig_sigint = signal.getsignal(signal.SIGINT)
    orig_sigterm = signal.getsignal(signal.SIGTERM)
    try:
        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)
    except Exception:
        pass

    playwright = None
    browser = None
    page = None

    try:
        # =====================================================================
        # 按笔记本粒度加锁，整个问答流程（提交→等答案）都在锁内。
        # 同一笔记本：完全串行（共享对话上下文，并发会导致答案交叉）
        # 不同笔记本：完全并行（锁文件按 URL hash 隔离）
        # =====================================================================
        with _notebook_lock(notebook_url, timeout=300):
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

            page, is_reused = _get_or_create_notebook_page(context, notebook_url)
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
                        page.close()
                        return None

            # Wait for query input (按优先级尝试配置的选择器)
            print("  ⏳ Waiting for query input...")
            query_element = None
            timeout_ms = 3000 if is_reused else 8000
            for selector in QUERY_INPUT_SELECTORS:
                try:
                    query_element = page.wait_for_selector(selector, timeout=timeout_ms, state="visible")
                    if query_element:
                        print(f"  ✓ Found input: {selector}")
                        break
                except Exception:
                    continue

            if not query_element:
                print("  ❌ Could not find query input")
                try:
                    page.close()
                except Exception:
                    pass
                return None

            # 按"用户问题原文"精确定位答案。
            # 关键背景：NotebookLM 聊天消息在 DOM 中可能乱序插入，每个 .chat-message-pair 内是一问一答。
            # 1. 匹配时清除空白、换行与末尾的 @ 来源标识等干扰符号。
            # 2. 优先提取 labs-tailwind-doc-viewer 内的正文；若无则从 message-text-content 中提取并清理思考头。
            # 3. 严格识别 thinking/searching 占位状态，确保只有完整回答才被捕获。
            def _exact_q_answers(q):
                try:
                    return page.evaluate(
                        """(q) => {
                            const clean = s => (s||'').replace(/[\\s@\\n\\r\\t]+/g,'');
                            const tq = clean(q);
                            const out = [];
                            document.querySelectorAll('.chat-message-pair').forEach(p => {
                                const u = p.querySelector('.from-user-message-card-content');
                                if (u) {
                                    const tu = clean(u.innerText);
                                    if (tu === tq || tu.startsWith(tq) || tq.startsWith(tu)) {
                                        const docViewer = p.querySelector('labs-tailwind-doc-viewer');
                                        const msgContent = p.querySelector('.to-user-container .message-text-content');
                                        let ansText = '';
                                        if (docViewer && docViewer.innerText.trim()) {
                                            ansText = docViewer.innerText.trim();
                                        } else if (msgContent && msgContent.innerText.trim()) {
                                            let raw = msgContent.innerText.trim();
                                            raw = raw.replace(/^Thoughts\\s*\\n\\s*expand_more\\s*\\n?/i, '').trim();
                                            ansText = raw;
                                        }
                                        out.push(ansText);
                                    }
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

            # 智能确认历史会话加载完成（冷启动时等待 spinner，复用热标签页时直接跳过）
            if not is_reused:
                _wait_for_history_loaded(page, timeout=10.0)
            # 对历史会话快照做稳定性校验：连续 2 次采样相同才采用，
            # 防止历史未完全加载时快照不准，导致 Counter 差集把旧答案误判为新答案。
            _prev_snap = None
            for _ in range(4):
                _snap = Counter(a for a in _exact_q_answers(question) if a)
                if _snap == _prev_snap:
                    break
                _prev_snap = _snap
                time.sleep(0.5)
            answers_before = _snap

            # =====================================================================
            # 提交问题：必须确认"用户问题气泡数 +1"才算成功。
            # 使用 ActionPacer 保证两次 UI 操作间隔 >= 0.3s，防止操作过频。
            # 策略：填入→Enter→确认；未确认则兜底点击提交按钮 / 重新填入再试，最多 3 轮。
            # =====================================================================
            pacer = ActionPacer(min_interval=0.3)
            user_before = _count_user_msgs()
            submitted = False

            for attempt in range(1, 4):
                print(f"  ⌨️  Typing & submitting (attempt {attempt})...")
                page.bring_to_front()  # 多标签并发时，确保焦点/键盘事件作用于本标签

                # 每轮重新定位输入框：热 Tab 复用时若 SPA 路由跳转，旧 ElementHandle 会失效。
                for selector in QUERY_INPUT_SELECTORS:
                    try:
                        fresh = page.wait_for_selector(selector, timeout=2000, state="visible")
                        if fresh:
                            query_element = fresh
                            break
                    except Exception:
                        continue

                pacer.pace()
                query_element.click()

                pacer.pace()
                try:
                    query_element.fill("")
                except Exception:
                    pass
                query_element.fill(question)

                pacer.pace()
                page.bring_to_front()
                page.keyboard.press("Enter")

                # 快速确认提交：等待用户气泡数增加（每 0.1s 检查一次，最多 ~3s）
                confirm_deadline = time.time() + 3.0
                while time.time() < confirm_deadline:
                    if _count_user_msgs() > user_before:
                        submitted = True
                        break
                    time.sleep(0.1)
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
                            is_disabled = page.evaluate(
                                "(b) => b.disabled || b.classList.contains('mat-mdc-button-disabled')",
                                btn
                            )
                            if not is_disabled:
                                pacer.pace()
                                btn.click()
                                clicked = True
                                break
                    except Exception:
                        continue
                if clicked:
                    confirm_deadline = time.time() + 3.0
                    while time.time() < confirm_deadline:
                        if _count_user_msgs() > user_before:
                            submitted = True
                            break
                        time.sleep(0.1)
                if submitted:
                    print("  📤 Submitted via button (confirmed).")
                    break
                # 本轮失败，下一轮重新填入再试

            if not submitted:
                print("  ❌ 多次尝试仍未能提交问题")
                # 无论冷/热 Tab 都清空输入框残留，避免下次复用时携带脏数据
                try:
                    query_element.fill("")
                except Exception:
                    pass
                if not is_reused:
                    page.close()
                return None

            # =====================================================================
            # 等待答案：用 Counter 差集找到本次新增的答案，等它稳定。
            # 必须等到真正的回答文本出现并稳定（连续 3 次轮询约 1.5s 文本不变）才返回。
            # =====================================================================
            print("  ⏳ Waiting for answer...")
            answer = None
            stable_count = 0
            last_text = None
            deadline = time.time() + 120

            def _is_thinking(t):
                if not t:
                    return True
                s = t.strip()
                # 去除末尾的 expand_more / expand_less 思考图标文本
                s = re.sub(r'\s*(expand_more|expand_less)\s*$', '', s, flags=re.IGNORECASE).strip()
                if s.endswith("...") or s.endswith("…"):
                    return True
                if len(s) < 80 and re.match(r'^(Defining|Searching|Reading|Processing|Thinking|已搜索|正在|思考)', s, re.IGNORECASE):
                    return True
                return False

            while time.time() < deadline:
                answers_now = Counter(a for a in _exact_q_answers(question) if a)
                new_answers = list((answers_now - answers_before).elements())
                non_thinking = [a for a in new_answers if not _is_thinking(a)]

                # 只有出现非 thinking 的正式内容才进行稳定判定
                if non_thinking:
                    text = non_thinking[-1]
                    if text == last_text:
                        stable_count += 1
                        if stable_count >= 3:
                            answer = text
                            break
                    else:
                        stable_count = 0
                        last_text = text
                else:
                    # 还在 thinking/searching 阶段，重置稳定计数并继续等待
                    stable_count = 0

                time.sleep(0.5)  # 0.5s 轮询等待，既能防止高频空转，又能更灵敏地捕获生成完毕状态
            # =====================================================================
            # 责任链转交判定（Directory-based Queue Inspection）：
            # 1. 首先注销本进程在队列目录下的 PID 文件；
            # 2. 检查队列目录下是否还有其他真实存活的排队进程：
            #    - 若有排队者：保留 Tab 不关闭，释放执行锁让排队者秒级复用！
            #    - 若无排队者（自己是最后一个离开的人）：由当前进程负责 page.close() 关门收尾！
            # =====================================================================
            _unregister_queue(notebook_url, my_pid)
            has_waiters = _has_alive_waiters(notebook_url, my_pid)
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
        # 恢复原有信号处理器
        try:
            signal.signal(signal.SIGINT, orig_sigint)
            signal.signal(signal.SIGTERM, orig_sigterm)
        except Exception:
            pass

        # 确保出队注销自己
        _unregister_queue(notebook_url, my_pid)

        # 异常兜底：若未正常移交且无人排队，确保关闭页面
        if page and not page.is_closed() and not _has_alive_waiters(notebook_url, my_pid):
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
    parser.add_argument('--cdp-endpoint', default=CDP_ENDPOINT, help='CDP endpoint')
    args = parser.parse_args()

    notebook_url = args.notebook_url
    if not notebook_url:
        if args.notebook_id:
            notebook_url = get_notebook_url(args.notebook_id)
            if not notebook_url:
                print(f"❌ Notebook '{args.notebook_id}' not found in library")
                return 1
        else:
            notebook_url = get_notebook_url()
            if notebook_url:
                print("📚 Using active notebook from library")

    if not notebook_url:
        print("❌ Must specify --notebook-url or --notebook-id (or set an active notebook)")
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
