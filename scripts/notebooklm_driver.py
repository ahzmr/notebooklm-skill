#!/usr/bin/env python3
"""
NotebookLM Page Driver
Encapsulates all DOM interactions, query submission, retry heuristics, and answer extraction.
Works uniformly across both CDP-connected tabs and locally launched browser pages.
"""

import re
import time
from collections import Counter
from typing import Optional, List, Tuple
from patchright.sync_api import Page, BrowserContext

from config import (
    QUERY_INPUT_SELECTORS,
    RESPONSE_SELECTORS,
    USER_MESSAGE_SELECTORS,
    SUBMIT_BUTTON_SELECTORS,
    QUERY_TIMEOUT_SECONDS,
)
from concurrency import extract_notebook_uuid, ActionPacer


class NotebookLMDriver:
    """High-reliability driver for interacting with NotebookLM UI"""

    def __init__(self, pacer: Optional[ActionPacer] = None):
        self.pacer = pacer or ActionPacer(min_interval=0.3)

    @staticmethod
    def get_or_create_managed_page(context: BrowserContext, notebook_url: str) -> Tuple[Page, bool]:
        """
        智能获取或新建专属托管的笔记本标签页：
        1. 专属所有权检查：使用浏览器原生的 window.name 持久化标签页标识，跨刷新/导航绝对不丢失；
        2. 严格跨笔记本隔离：只复用本笔记本的 Tab (tag == expected_tag)，绝不关闭或触碰其他笔记本的 Tab；
        3. 绝不触碰用户个人标签页（用户个人页 window.name 为空或不同）；
        4. 命中当前笔记本：激活并复用（热会话，耗时 ~0ms）；
        5. 未命中：冷启动新建 Tab，导航并设置 window.name 专属标记。
        返回: (page, is_reused)
        """
        nb_uuid = extract_notebook_uuid(notebook_url)
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
        try:
            page.evaluate(
                """(tag) => {
                    window.name = tag;
                }""",
                expected_tag,
            )
        except Exception:
            pass

        return page, False

    @staticmethod
    def wait_for_history_loaded(page: Page, timeout: float = 5.0):
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

    @staticmethod
    def find_query_input(page: Page, timeout_ms: int = 5000):
        """按优先级尝试配置的选择器查找输入框"""
        for selector in QUERY_INPUT_SELECTORS:
            try:
                element = page.wait_for_selector(selector, timeout=timeout_ms, state="visible")
                if element:
                    return element, selector
            except Exception:
                continue
        return None, None

    @staticmethod
    def count_user_messages(page: Page) -> int:
        """统计当前已提交的'用户问题气泡'数量——提交成功的硬信号"""
        for selector in USER_MESSAGE_SELECTORS:
            try:
                els = page.query_selector_all(selector)
                if els:
                    return len(els)
            except Exception:
                continue
        return 0

    @staticmethod
    def get_exact_answers(page: Page, question: str) -> List[str]:
        """
        按'用户问题原文'精确定位答案。
        关键背景：NotebookLM 聊天消息在 DOM 中可能乱序插入，每个 .chat-message-pair 内是一问一答。
        1. 匹配时清除空白、换行与末尾的 @ 来源标识等干扰符号。
        2. 优先提取 labs-tailwind-doc-viewer 内的正文；若无则从 message-text-content 中提取。
        3. 无论取自哪个来源，统一清理开头的"Thoughts / expand_more"思考折叠头
           （NotebookLM 新版 UI 会把折叠的思考块和最终答案渲染在同一个容器里）。
        4. 严格识别 thinking/searching 占位状态，确保只有完整回答才被捕获。
        """
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
                                    ansText = msgContent.innerText.trim();
                                }
                                ansText = ansText.replace(/^Thoughts\\s*\\n\\s*expand_more\\s*\\n?/i, '').trim();
                                out.push(ansText);
                            }
                        }
                    });
                    return out;
                }""",
                question,
            )
        except Exception:
            return []

    @staticmethod
    def is_thinking(text: Optional[str]) -> bool:
        """判定文本是否属于 NotebookLM 中间思考/检索占位状态"""
        if not text:
            return True
        s = text.strip()
        # 去除末尾的 expand_more / expand_less 思考图标文本
        s = re.sub(r'\s*(expand_more|expand_less)\s*$', '', s, flags=re.IGNORECASE).strip()
        if s.endswith("...") or s.endswith("…"):
            return True
        if len(s) < 80 and re.match(r'^(Defining|Searching|Reading|Processing|Thinking|已搜索|正在|思考)', s, re.IGNORECASE):
            return True
        return False

    def snapshot_answers(self, page: Page, question: str, max_rounds: int = 4) -> Counter:
        """
        对历史会话快照做稳定性校验：连续 2 次采样相同才采用，
        防止历史未完全加载时快照不准，导致 Counter 差集把旧答案误判为新答案。
        """
        prev_snap = None
        current_snap = Counter()
        for _ in range(max_rounds):
            current_snap = Counter(a for a in self.get_exact_answers(page, question) if a)
            if current_snap == prev_snap:
                break
            prev_snap = current_snap
            time.sleep(0.5)
        return current_snap

    def submit_query(self, page: Page, question: str, max_attempts: int = 3) -> bool:
        """
        提交问题：必须确认'用户问题气泡数 +1'才算成功。
        使用 ActionPacer 保证两次 UI 操作间隔 >= 0.3s，防止操作过频。
        策略：填入→Enter→确认；未确认则兜底点击提交按钮 / 重新填入再试，最多 max_attempts 轮。
        """
        user_before = self.count_user_messages(page)
        submitted = False
        query_element = None

        for attempt in range(1, max_attempts + 1):
            print(f"  ⌨️  Typing & submitting (attempt {attempt})...")
            try:
                page.bring_to_front()
            except Exception:
                pass

            # 每轮重新定位输入框：热 Tab 复用时若 SPA 路由跳转，旧 ElementHandle 会失效。
            query_element, sel = self.find_query_input(page, timeout_ms=2000)
            if not query_element:
                print("  ⚠️ 输入框暂不可见，稍候重试...")
                time.sleep(0.5)
                continue

            self.pacer.pace()
            try:
                query_element.click()
            except Exception:
                pass

            self.pacer.pace()
            try:
                query_element.fill("")
            except Exception:
                pass
            query_element.fill(question)

            self.pacer.pace()
            try:
                page.bring_to_front()
            except Exception:
                pass
            page.keyboard.press("Enter")

            # 快速确认提交：等待用户气泡数增加（每 0.1s 检查一次，最多 ~3s）
            confirm_deadline = time.time() + 3.0
            while time.time() < confirm_deadline:
                if self.count_user_messages(page) > user_before:
                    submitted = True
                    break
                time.sleep(0.1)

            if submitted:
                print("  📤 Submitted (confirmed).")
                return True

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
                            self.pacer.pace()
                            btn.click()
                            clicked = True
                            break
                except Exception:
                    continue

            if clicked:
                confirm_deadline = time.time() + 3.0
                while time.time() < confirm_deadline:
                    if self.count_user_messages(page) > user_before:
                        submitted = True
                        break
                    time.sleep(0.1)

            if submitted:
                print("  📤 Submitted via button (confirmed).")
                return True

        # 若全部尝试均未成功，清空残留文本
        if query_element:
            try:
                query_element.fill("")
            except Exception:
                pass

        return False

    def wait_for_answer(
        self,
        page: Page,
        question: str,
        answers_before: Counter,
        timeout: int = QUERY_TIMEOUT_SECONDS,
        stable_threshold: int = 3
    ) -> Optional[str]:
        """
        等待答案：用 Counter 差集找到本次新增的答案，等它稳定。
        必须等到真正的回答文本出现并稳定（连续 stable_threshold 次轮询约 1.5s 文本不变）才返回。
        """
        print("  ⏳ Waiting for answer...")
        answer = None
        stable_count = 0
        last_text = None
        deadline = time.time() + timeout

        while time.time() < deadline:
            answers_now = Counter(a for a in self.get_exact_answers(page, question) if a)
            new_answers = list((answers_now - answers_before).elements())
            non_thinking = [a for a in new_answers if not self.is_thinking(a)]

            # 只有出现非 thinking 的正式内容才进行稳定判定
            if non_thinking:
                text = non_thinking[-1]
                if text == last_text:
                    stable_count += 1
                    if stable_count >= stable_threshold:
                        answer = text
                        break
                else:
                    stable_count = 0
                    last_text = text
            else:
                # 还在 thinking/searching 阶段，重置稳定计数并继续等待
                stable_count = 0

            time.sleep(0.5)  # 0.5s 轮询等待，既能防止高频空转，又能更灵敏地捕获生成完毕状态

        return answer

    def ask(
        self,
        page: Page,
        question: str,
        is_reused: bool = False,
        timeout: int = QUERY_TIMEOUT_SECONDS
    ) -> Optional[str]:
        """
        完整的端到端问答交互流程：
        1. 检查/等待页面就绪与输入框可见；
        2. 快照历史回答（防旧答案误判）；
        3. 提交问题与重试；
        4. 等待答案生成稳定并返回。
        """
        # 1. 检查/等待输入框
        print("  ⏳ Waiting for query input...")
        timeout_ms = 3000 if is_reused else 8000
        query_element, sel = self.find_query_input(page, timeout_ms=timeout_ms)
        if not query_element:
            print("  ❌ Could not find query input")
            return None
        print(f"  ✓ Found input: {sel}")

        # 2. 智能等待历史会话加载完成
        if not is_reused:
            self.wait_for_history_loaded(page, timeout=10.0)

        # 3. 快照历史回答
        answers_before = self.snapshot_answers(page, question)

        # 4. 提交问题
        if not self.submit_query(page, question):
            print("  ❌ 多次尝试仍未能提交问题")
            return None

        # 5. 等待答案生成稳定
        answer = self.wait_for_answer(page, question, answers_before, timeout=timeout)
        return answer
