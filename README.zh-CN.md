<div align="center">

# NotebookLM Claude Code Skill

**让 [Claude Code](https://github.com/anthropics/claude-code) 直接与 NotebookLM 对话，获得完全基于你上传文档的、有据可查的答案**

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-purple.svg)](https://www.anthropic.com/news/skills)
[![Based on](https://img.shields.io/badge/Based%20on-NotebookLM%20MCP-green.svg)](https://github.com/PleasePrompto/notebooklm-mcp)
[![GitHub](https://img.shields.io/github/stars/PleasePrompto/notebooklm-skill?style=social)](https://github.com/PleasePrompto/notebooklm-skill)

> 使用此技能可以直接在 Claude Code、OpenCode 或任何支持 Agent Skills 格式的工具中查询你的 Google NotebookLM（现已更名为"Gemini Notebook"）笔记本，获得 Gemini 提供的、有据可查、源自你文档的答案。内置浏览器自动化、库管理、持久化登录态，从上传文档以外的内容大幅减少幻觉。

[安装](#安装) • [快速开始](#快速开始) • [为什么选 NotebookLM](#为什么选-notebooklm而不是本地-rag) • [工作原理](#工作原理) • [MCP 版本](https://github.com/PleasePrompto/notebooklm-mcp)

[English](./README.md)

</div>

---

## 📣 NotebookLM 现已更名为 Gemini Notebook

**2026 年 7 月 16 日**，Google 把 NotebookLM 更名为 **Gemini Notebook**——还是同一个产品，同样的笔记本、同样的资料来源、同样的分享链接，只是换了个属于 Gemini 家族的新名字（旧的 `notebooklm.google.com` 链接会自动重定向继续可用，同时启用了新的 `notebook.google.com` 域名）。焕新更名，品质如初。

本技能的脚本名、目录名、技能标识符依旧沿用 `notebooklm` 这个名字（改名会破坏现有安装和笔记本库文件），并且对**两个域名**的链接都做了透明兼容——你不需要做任何改动。下文仍然沿用"NotebookLM"这个说法，遇到时按"NotebookLM / Gemini Notebook"理解即可。

---

## ⚠️ 重要提示：仅限本地运行（Claude Code、OpenCode 等）

**此技能仅能在支持 Agent Skills 格式、且拥有网络访问权限的本地 Agent 中使用——目前已确认可用的有 [Claude Code](https://github.com/anthropics/claude-code) 和 [OpenCode](https://opencode.ai/)（它读取的是同样的 `~/.claude/skills/` 和 `.claude/skills/` 路径）——无法在 Claude.ai 网页版中使用。**

网页版在沙盒环境中运行技能，没有网络访问权限，而本技能的浏览器自动化必须依赖网络访问。你必须在自己的机器上本地运行 Claude Code、OpenCode 等 Agent。

---

## 遇到的问题

当你让 [Claude Code](https://github.com/anthropics/claude-code)"搜索一下我本地的文档"时，实际发生的是：
- **消耗大量 token**：搜索文档意味着要反复读取多个文件
- **检索不准**：靠关键词搜索，容易漏掉文档之间的上下文和关联
- **产生幻觉**：找不到答案时，会编造看起来很像那么回事的 API
- **手动复制粘贴**：不停地在 NotebookLM 浏览器和编辑器之间切换

## 解决方案

这个 Claude Code Skill 让 [Claude Code](https://github.com/anthropics/claude-code) 直接与 [**NotebookLM**](https://notebooklm.google/) 对话——Google 基于 Gemini 2.5 打造的**源自文档的知识库**，能够完全基于你上传的文档给出经过整合、有依据的智能回答。

```
你的任务 → Claude 提问 NotebookLM → Gemini 整合出答案 → Claude 写出正确的代码
```

**告别复制粘贴**：Claude 直接在命令行里提问，直接拿到答案。它会通过自动追问不断深入理解，拿到具体的实现细节、边界情况和最佳实践。

---

## 为什么选 NotebookLM，而不是本地 RAG？

| 方案 | Token 成本 | 搭建耗时 | 幻觉风险 | 回答质量 |
|----------|------------|------------|----------------|----------------|
| **把文档喂给 Claude** | 🔴 很高（反复读多个文件） | 即时 | 有——会自行补全缺口 | 检索效果不稳定 |
| **网页搜索** | 🟡 中等 | 即时 | 高——来源不可靠 | 时好时坏 |
| **本地 RAG** | 🟡 中到高 | 数小时（做向量化、分块） | 中——检索会有缺口 | 取决于搭建方式 |
| **NotebookLM Skill** | 🟢 极低 | 5 分钟 | **极低**——完全基于源文档 | 专家级整合 |

### NotebookLM 好在哪里？

1. **Gemini 预先处理**：文档只需上传一次，立即获得专家级知识
2. **自然语言问答**：不只是检索——是真正的理解与整合
3. **多源关联**：能在 50+ 份文档之间建立联系
4. **有据可查**：每个回答都附带出处引用
5. **零基础设施**：不需要向量数据库、Embedding 或分块策略

---

## 安装

### 目前最简单的安装方式：

```bash
# 1. 创建 skills 目录（如果还没有的话）
mkdir -p ~/.claude/skills

# 2. 克隆本仓库
cd ~/.claude/skills
git clone https://github.com/PleasePrompto/notebooklm-skill notebooklm

# 3. 就这样，打开 Claude Code 说：
"What are my skills?"
```

首次使用该技能时，它会自动：
- 创建独立的 Python 环境（`.venv`）
- 安装所有依赖，包括 **Google Chrome**
- 用 Chrome（而不是 Chromium）配置浏览器自动化，以获得最高的可靠性
- 一切都封装在技能目录内部，不影响系统其他部分

**说明：** 之所以用真正的 Chrome 而不是 Chromium，是为了获得跨平台的一致性、稳定的浏览器指纹，以及更好的 Google 服务反检测效果

---

## 快速开始

### 1. 查看你的技能列表

在 Claude Code 里说：
```
"What skills do I have?"
```

Claude 会列出你已有的技能，其中包括 NotebookLM。

### 2. 完成 Google 认证（一次性）

```
"Set up NotebookLM authentication"
```
*会弹出一个 Chrome 窗口 → 用你的 Google 账号登录*

> 在 Docker/CDP 模式下不需要这一步——本技能会直接复用宿主机浏览器里已经登录的 Google 会话。详见下方[后端](#后端本地浏览器-vs-cdpdocker)一节。

### 3. 建立你的知识库

前往 [notebooklm.google.com](https://notebooklm.google.com) → 创建笔记本 → 上传你的文档：
- 📄 PDF、Google 文档、Markdown 文件
- 🔗 网站、GitHub 仓库
- 🎥 YouTube 视频
- 📚 一个笔记本可以放多个来源

分享：**⚙️ 分享 → 拥有链接的任何人 → 复制链接**

### 4. 添加到你的库

**方式 A：让 Claude 自己搞定（智能添加）**
```
"Query this notebook about its content and add it to my library: [你的链接]"
```
Claude 会自动查询这个笔记本了解其内容，然后带上合适的元数据把它加进去。

**方式 B：手动添加**
```
"Add this NotebookLM to my library: [你的链接]"
```
Claude 会询问名称和主题标签，然后保存以供后续使用。

### 5. 开始调研

```
"What does my React docs say about hooks?"
```

Claude 会自动选中正确的笔记本，直接从 NotebookLM 拿到答案。

---

## 工作原理

这是一个 **Claude Code Skill**——一个包含指令和脚本的本地文件夹，供 Claude Code 按需调用。与 [MCP Server 版本](https://github.com/PleasePrompto/notebooklm-mcp) 不同，它直接在 Claude Code 内运行，不需要额外启动一个服务器。

### 与 MCP Server 的主要区别

| 特性 | 本 Skill | MCP Server |
|---------|------------|------------|
| **协议** | Claude Skills | Model Context Protocol |
| **安装方式** | 克隆到 `~/.claude/skills` | `claude mcp add ...` |
| **会话** | 每次提问都是全新浏览器会话 | 持久化的聊天会话 |
| **兼容性** | Claude Code、OpenCode（仅限本地） | Claude Code、Codex、Cursor 等 |
| **实现语言** | Python | TypeScript |
| **分发方式** | Git clone | npm 包 |

### 目录结构

```
~/.claude/skills/notebooklm/
├── SKILL.md              # 给 Claude 的指令
├── scripts/              # Python 自动化脚本
│   ├── ask_question.py   # 查询 NotebookLM
│   ├── notebook_manager.py # 笔记本库管理
│   └── auth_manager.py   # Google 登录认证
├── .venv/                # 独立的 Python 环境（自动创建）
└── data/                 # 本地笔记本库
```

当你提到 NotebookLM 或发送一个笔记本链接时，Claude 会：
1. 加载技能指令
2. 运行对应的 Python 脚本
3. 打开浏览器，提出你的问题
4. 把答案直接返回给你
5. 用这份知识来帮你完成任务

---

## 核心功能

### **有据可查的回答**
NotebookLM 通过只依据你上传的文档来回答问题，大幅减少幻觉。如果信息不存在，它会表明不确定，而不是编造内容。

### **直接集成**
不需要在浏览器和编辑器之间复制粘贴。Claude 以编程方式直接提问并接收答案。

### **智能库管理**
保存带标签和描述的 NotebookLM 链接。Claude 会为你的任务自动选中正确的笔记本。

### **自动认证**
一次性完成 Google 登录，之后的会话都会保持登录状态。

### **自包含**
一切都运行在技能目录内，使用独立的 Python 环境，不需要任何全局安装。

### **拟人化自动化**
使用真实的打字速度和交互节奏，避免被识别为自动化行为。

---

## 常用指令

| 你说的话 | 会发生什么 |
|--------------|--------------|
| *"Set up NotebookLM authentication"* | 打开 Chrome 进行 Google 登录 |
| *"Add [link] to my NotebookLM library"* | 保存笔记本及其元数据 |
| *"Show my NotebookLM notebooks"* | 列出所有已保存的笔记本 |
| *"Ask my API docs about [topic]"* | 查询相关笔记本 |
| *"Use the React notebook"* | 设置当前激活的笔记本 |
| *"Clear NotebookLM data"* | 重新开始（保留库） |

---

## 真实案例

### 案例 1：查询车辆维修手册

**用户提问**："查一下我的铃木 GSR 600 维修手册，告诉我刹车油型号、机油规格和后桥扭矩。"

**Claude 自动执行**：
- 完成 NotebookLM 认证
- 就每一项规格提出完整的问题
- 在提示"是否已经了解全部所需信息？"时主动追问
- 给出准确的规格数据：DOT 4 刹车油、SAE 10W-40 机油、后桥扭矩 100 N·m

![NotebookLM 对话示例](images/example_notebookchat.png)

### 案例 2：不靠幻觉搭建功能

**你**："我要基于我的 n8n 笔记本，搭一个 Gmail 垃圾邮件过滤的 n8n 工作流。"

**Claude 的内部流程：**
```
→ 加载 NotebookLM 技能
→ 激活 n8n 笔记本
→ 提出完整的问题并持续追问
→ 综合多次查询的结果，整合出完整答案
```

**结果**：一次就跑通的工作流，不用调试编造出来的 API。

---

## 技术细节

### 核心技术
- **Patchright**：浏览器自动化库（基于 Playwright）
- **Python**：本技能的实现语言
- **反检测技巧**：拟人化的打字和交互节奏

说明：MCP Server 使用同一套 Patchright 库，但走的是 TypeScript/npm 生态。

### 后端：本地浏览器 vs. CDP（Docker）

`run.py` 会自动探测运行环境并选择对应的后端——无需手动配置：

| 环境 | 后端 | 方式 |
|-------------|---------|-----|
| 本地已安装 Chrome/Chromium（Mac、原生 Linux） | `ask_question.py` | 启动自己的持久化浏览器，使用已保存的登录态 |
| 本地无 Chrome（例如 Docker 容器）—— **主要支持的部署方式** | `ask_cdp.py` | 通过 Chrome DevTools Protocol 连接到已经运行在**宿主机**上的浏览器（`--remote-debugging-port=9222`），复用宿主机的登录会话 |

**在 Docker/CDP 模式下运行：** 在宿主机上保持一个开启远程调试的 Chromium 系浏览器在后台运行：

```bash
# 在宿主机上执行一次，让它在后台常驻：
open -a "Microsoft Edge" --args --remote-debugging-port=9222
# 或者：  open -a "Google Chrome" --args --remote-debugging-port=9222

# 在容器内部验证桥接是否畅通：
curl -s http://localhost:9222/json/version   # 应该返回浏览器版本信息 JSON
```

CDP 模式下不需要单独的认证步骤——它直接复用宿主机浏览器里已经登录好的 Google 会话。

**并发：** 调用方永远可以并行发起多个问答——由实现层决定到底是并行执行还是排队执行。CDP 模式下，问不同笔记本会真正并行，问同一个笔记本会自动排队（并复用热标签页）；本地模式下所有查询会全局自动串行，因为它们共享同一个浏览器 profile 目录。

具体的 Docker/CDP 搭建步骤、排障方法以及完整的并发契约见 `SKILL.md`。

### 依赖

- **patchright==1.55.2**：浏览器自动化
- **python-dotenv==1.0.0**：环境变量配置
- 首次使用时会自动安装到 `.venv`

### 数据存储

所有数据都保存在技能目录本地：

```
~/.claude/skills/notebooklm/data/
├── library.json       - 你的笔记本库及元数据
├── auth_info.json     - 认证状态信息
└── browser_state/     - 浏览器 Cookie 与会话数据
```

**重要安全提示：**
- `data/` 目录包含敏感的认证数据和你的个人笔记本信息
- 已通过 `.gitignore` 自动排除在 git 之外
- **切勿**手动提交或分享 `data/` 目录中的内容

### 会话模型

与 MCP Server 不同，本技能采用**无状态模型**：
- 每次提问都会打开一个全新的浏览器
- 提出问题、拿到答案
- 在回答末尾附加追问提示，鼓励 Claude 继续提问
- 立即关闭浏览器

这意味着：
- 没有持久化的聊天上下文
- 每次提问都是独立的
- 但你的笔记本库会一直保留
- **追问机制**：每个回答都会附带"是否已经了解全部所需信息？"，提示 Claude 进行全面的追问

在 CDP 模式下，如果针对**同一个**笔记本已经有其他查询在排队，浏览器标签页可能会在一次提问结束后短暂保留（这样下一个查询能直接复用，而不用重新打开）——但从 Claude 的角度看，每个问题依然是被独立提出、独立回答的。

对于需要多步骤的调研，Claude 会在需要时自动提出追问。

---

## 局限性

### 本技能自身的局限
- **仅限本地 Agent**（Claude Code、OpenCode 等） —— 在网页版中无法使用（沙盒限制）
- **没有会话持久性** —— 每次提问都是独立的
- **没有追问上下文** —— 无法引用"上一个回答"

### NotebookLM 自身的局限
- **速率限制** —— 免费版每天有查询次数上限
- **需要手动上传** —— 你必须先把文档上传到 NotebookLM
- **需要开启分享** —— 笔记本必须设置为可公开分享的链接

---

## 常见问题

**为什么在 Claude 网页版里用不了？**
网页版在没有网络访问权限的沙盒中运行技能。浏览器自动化需要网络访问才能连接到 NotebookLM。

**这个和 MCP Server 有什么不同？**
本技能是一个更简单的、基于 Python 的实现，直接以 Claude Skill 的形式运行。MCP Server 功能更丰富，拥有持久化会话，并且能配合多种工具使用（Codex、Cursor 等）。

**可以同时使用本技能和 MCP Server 吗？**
可以！它们服务于不同的场景。想要在 Claude Code 里快速集成就用本技能，想要持久化会话和多工具支持就用 MCP Server。

**如果 Chrome 崩溃了怎么办？**
执行：`"Clear NotebookLM browser data"`，然后重试。

**我的 Google 账号安全吗？**
Chrome 是在你自己的机器上本地运行的，你的凭据不会离开你的电脑。如果担心，建议使用专门的 Google 账号来做自动化。

---

## 故障排查

### 找不到技能
```bash
# 确认它在正确的位置
ls ~/.claude/skills/notebooklm/
# 应该能看到：SKILL.md、scripts/ 等
```

### 认证问题
说：`"Reset NotebookLM authentication"`

### 浏览器崩溃
说：`"Clear NotebookLM browser data"`

### 依赖问题
```bash
# 如需手动重新安装
cd ~/.claude/skills/notebooklm
rm -rf .venv
python -m venv .venv
source .venv/bin/activate  # Windows 下用 .venv\Scripts\activate
pip install -r requirements.txt
```

---

## 免责声明

这个工具通过自动化浏览器操作与 NotebookLM 交互，让你的工作流更高效。不过有几点友情提示：

**关于浏览器自动化：**
虽然我加入了一些拟人化的设计（真实的打字速度、自然的延迟、鼠标移动）让自动化行为看起来更自然，但我无法保证 Google 不会检测或标记自动化使用行为。建议使用专门的 Google 账号来做自动化，而不是你的主账号——就像做网页爬虫一样：大概率没事，但小心为上！

**关于命令行工具与 AI Agent：**
Claude Code、Codex 等 AI 驱动的命令行工具非常强大，但它们也会犯错。请谨慎、清醒地使用它们：
- 提交或部署前务必检查改动
- 先在安全的环境中测试
- 保留重要工作的备份
- 记住：AI Agent 是助手，不是绝对正确的神谕

我做这个工具最初是给自己用的，因为受够了在 NotebookLM 和编辑器之间来回复制粘贴。我把它分享出来，希望也能帮到别人，但对使用过程中可能出现的任何问题、数据丢失或账号问题，我概不负责。请自行判断、谨慎使用。

话虽如此，如果你遇到问题或有疑问，欢迎在 GitHub 上提 issue，我很乐意帮忙排查！

---

## 致谢

本技能的灵感来自我做的 [**NotebookLM MCP Server**](https://github.com/PleasePrompto/notebooklm-mcp)，是它作为 Claude Code Skill 的另一种实现：
- 两者都使用 Patchright 做浏览器自动化（MCP 用 TypeScript，Skill 用 Python）
- Skill 版本直接在 Claude Code 中运行，不依赖 MCP 协议
- 无状态设计，专为 Skill 架构做了优化

如果你需要：
- **持久化会话** → 使用 [MCP Server](https://github.com/PleasePrompto/notebooklm-mcp)
- **多工具支持**（Codex、Cursor） → 使用 [MCP Server](https://github.com/PleasePrompto/notebooklm-mcp)
- **在 Claude Code 里快速集成** → 使用本技能

---

## 一句话总结

**没有这个技能时**：在浏览器里用 NotebookLM → 复制答案 → 粘贴进 Claude → 复制下一个问题 → 再切回浏览器……

**有了这个技能**：Claude 直接调研 → 立刻拿到答案 → 写出正确的代码

告别复制粘贴的循环。直接在 Claude Code 里获得准确、有据可查的答案。

```bash
# 30 秒内开始使用
cd ~/.claude/skills
git clone https://github.com/PleasePrompto/notebooklm-skill notebooklm
# 打开 Claude Code，说："What are my skills?"
```

---

<div align="center">

作为 Claude Code Skill，改编自我的 [NotebookLM MCP Server](https://github.com/PleasePrompto/notebooklm-mcp)

让你直接在 Claude Code 里完成有据可查、基于文档的调研

</div>
