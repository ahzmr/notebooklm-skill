"""
Configuration for NotebookLM Skill
Centralizes constants, selectors, and paths
"""

from pathlib import Path

# Paths
SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
BROWSER_STATE_DIR = DATA_DIR / "browser_state"
BROWSER_PROFILE_DIR = BROWSER_STATE_DIR / "browser_profile"
STATE_FILE = BROWSER_STATE_DIR / "state.json"
AUTH_INFO_FILE = DATA_DIR / "auth_info.json"
LIBRARY_FILE = DATA_DIR / "library.json"

# NotebookLM Selectors (按实用性和优先级排序，常用在首位，保底兼容在后)
QUERY_INPUT_SELECTORS = [
    "textarea.query-box-input",  # Primary (Angular 核心输入框类名)
    'textarea[aria-label="查询框"]',  # 中文
    'textarea[aria-label="Input for queries"]',  # 英文
    'textarea[aria-label="Feld für Anfragen"]',  # 德文
    "textarea",  # 通用保底
]

RESPONSE_SELECTORS = [
    ".to-user-container .message-text-content",  # Primary
    "[data-message-author='bot']",
    "[data-message-author='assistant']",
]

# 用户已提交问题的气泡（用于"确认问题真的发出去了"）
USER_MESSAGE_SELECTORS = [
    ".from-user-message-card-content",  # Primary (当前实测用户卡片内容类名)
    ".from-user-container",
    "[data-message-author='user']",
]

# 聊天框提交按钮（优先使用与语言无关的样式类/属性，再使用各语言 aria-label）
SUBMIT_BUTTON_SELECTORS = [
    "button.actions-enter-button",  # Primary (当前实测提交按钮类名)
    "button[type='submit']",
    "button[aria-label='提交']",
    "button[aria-label='Submit']",
    "button[aria-label='Send']",
    "button[aria-label='发送']",
]

# Browser Configuration
BROWSER_ARGS = [
    '--disable-blink-features=AutomationControlled',  # Patches navigator.webdriver
    '--disable-dev-shm-usage',
    '--no-sandbox',
    '--no-first-run',
    '--no-default-browser-check',
]

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

# Timeouts
LOGIN_TIMEOUT_MINUTES = 10
QUERY_TIMEOUT_SECONDS = 120
PAGE_LOAD_TIMEOUT = 30000
