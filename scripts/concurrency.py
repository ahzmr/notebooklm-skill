#!/usr/bin/env python3
"""
Concurrency and Process Lifecycle Management for NotebookLM Skill
Handles per-notebook file locks, atomic queue registration, and process liveness inspection.
"""

import fcntl
import hashlib
import os
import signal
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Callable, Tuple

from config import LOCK_TIMEOUT_SECONDS

_LOCK_DIR = Path(tempfile.gettempdir())


def extract_notebook_uuid(url: str) -> str:
    """提取 NotebookLM URL 中的 notebook UUID 或主要标识"""
    import re
    m = re.search(r'/notebook/([a-zA-Z0-9_-]+)', url)
    return m.group(1) if m else url.rstrip('/')


def get_queue_dir(notebook_url: str) -> Path:
    """按笔记本 URL 生成专属的进程排队登记目录"""
    url_hash = hashlib.md5(notebook_url.encode()).hexdigest()[:12]
    qdir = _LOCK_DIR / f"notebooklm_queue_{url_hash}"
    qdir.mkdir(parents=True, exist_ok=True)
    return qdir


def register_queue(notebook_url: str, pid: Optional[int] = None) -> Path:
    """进程到达，原子创建属于自己的独立 PID 文件（入队登记，零写锁竞争）"""
    p = pid if pid is not None else os.getpid()
    qdir = get_queue_dir(notebook_url)
    pid_file = qdir / f"{p}.pid"
    try:
        pid_file.touch()
    except Exception:
        pass
    return pid_file


def unregister_queue(notebook_url: str, pid: Optional[int] = None):
    """进程结束或意外中断，删除自己的 PID 文件（出队注销）"""
    p = pid if pid is not None else os.getpid()
    qdir = get_queue_dir(notebook_url)
    pid_file = qdir / f"{p}.pid"
    try:
        pid_file.unlink(missing_ok=True)
    except Exception:
        pass


def has_alive_waiters(notebook_url: str, my_pid: Optional[int] = None) -> bool:
    """
    检查当前笔记本队列目录下是否还有其他存活的排队进程：
    1. 忽略排除当前进程自己 (my_pid)；
    2. 对目录下每一个剩余的 .pid 文件，通过 os.kill(pid, 0) 极速检查存活性；
    3. 若发现死进程文件（如被 kill -9 强杀），顺手清理；
    4. 返回是否存在至少 1 个真实存活的排队者。
    """
    current_pid = my_pid if my_pid is not None else os.getpid()
    qdir = get_queue_dir(notebook_url)
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


def get_lock_file(notebook_url: str) -> Path:
    """按笔记本 URL 生成独立的锁文件路径。
    同一笔记本 → 同一把锁（串行）；不同笔记本 → 不同的锁（并行）。
    """
    url_hash = hashlib.md5(notebook_url.encode()).hexdigest()[:12]
    return _LOCK_DIR / f"notebooklm_nb_{url_hash}.lock"


@contextmanager
def notebook_lock(notebook_url: str, timeout: int = LOCK_TIMEOUT_SECONDS):
    """按笔记本粒度的文件锁，覆盖整个问答流程。

    为什么要覆盖整个问答流程：
      NotebookLM 同一笔记本的所有标签页共享同一个对话上下文。
      若两个进程并发向同一笔记本提交问题，问题和答案会交叉出现在同一聊天流里，
      导致每个进程抓到错误的答案。因此同一笔记本必须完全串行。

    不同笔记本之间完全并行，互不影响。
    """
    lock_file = get_lock_file(notebook_url)
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
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_UN)
        except Exception:
            pass
        lock_fh.close()
        print(f"  🔓 Notebook lock released")


def setup_queue_signal_handlers(notebook_url: str, pid: Optional[int] = None) -> Tuple[Callable, Callable]:
    """注册信号捕获：若在排队等锁或执行中被终止（Ctrl+C/kill），主动清理自己的 PID 文件"""
    my_pid = pid if pid is not None else os.getpid()

    def _sig_handler(signum, frame):
        try:
            unregister_queue(notebook_url, my_pid)
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

    return orig_sigint, orig_sigterm


def restore_signal_handlers(orig_sigint, orig_sigterm):
    """恢复原有的信号处理器"""
    try:
        if orig_sigint:
            signal.signal(signal.SIGINT, orig_sigint)
        if orig_sigterm:
            signal.signal(signal.SIGTERM, orig_sigterm)
    except Exception:
        pass


class ActionPacer:
    """通用操作节流器：保证两次 UI 操作间隔至少大于 min_interval 秒（默认 0.3s）"""
    def __init__(self, min_interval: float = 0.3):
        self.min_interval = min_interval
        self.last_action_time = 0.0

    def pace(self, custom_interval: Optional[float] = None):
        interval = custom_interval if custom_interval is not None else self.min_interval
        now = time.time()
        elapsed = now - self.last_action_time
        if elapsed < interval:
            time.sleep(interval - elapsed)
        self.last_action_time = time.time()
