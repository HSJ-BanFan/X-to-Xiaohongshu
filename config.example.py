# ============================================================
# X-to-XHS 配置文件模板
# 复制此文件为 config.py 并填入你的实际值
# 所有配置项均支持环境变量覆盖（优先级：环境变量 > config.py 值）
# ============================================================

import os

# --- X (Twitter) 设置 ---
# 可选：从浏览器导出的 cookies JSON 文件路径
# 如果 Guest Token 失效，需要提供此文件来认证
X_COOKIES_FILE = os.getenv("X_COOKIES_FILE", "data/x_cookies.json")

# 可选：如果你有 X 开发者 API Bearer Token
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN", "")

# --- 小红书设置 ---
# 小红书 Cookies 存放路径
XHS_COOKIES_FILE = os.getenv("XHS_COOKIES_FILE", "data/xiaohongshu_cookies.json")

# Chrome 用户数据目录路径，用于复用已有登录态
# Windows 默认路径: C:\Users\<用户名>\AppData\Local\Google\Chrome\User Data
# 留空则使用独立的浏览器实例（首次需扫码登录）
CHROME_USER_DATA_DIR = os.getenv("CHROME_USER_DATA_DIR", "")

# Chrome Profile 名称（默认 "Default"）
CHROME_PROFILE = os.getenv("CHROME_PROFILE", "Default")

# 发布前等待秒数（给你人工审核内容的时间）
XHS_WAIT_BEFORE_PUBLISH = int(os.getenv("XHS_WAIT_BEFORE_PUBLISH", "30"))

# 批量模式下每条推文之间的随机等待范围（秒），用于防封号
BATCH_DELAY_MIN = int(os.getenv("BATCH_DELAY_MIN", "30"))
BATCH_DELAY_MAX = int(os.getenv("BATCH_DELAY_MAX", "90"))

# 是否在小红书笔记末尾自动添加 "📎 来源: @作者名 (X/Twitter)"
# 建议默认关闭，以免小红书限流外部平台引流
ENABLE_AUTHOR_ATTRIBUTION = os.getenv("ENABLE_AUTHOR_ATTRIBUTION", "").lower() in ("1", "true", "yes")

# --- 翻译设置（可选，未使用大模型时生效）---
ENABLE_TRANSLATION = os.getenv("ENABLE_TRANSLATION", "").lower() in ("1", "true", "yes")
# 翻译引擎: "google" (免费) 或 "deepl" (需要 API key)
TRANSLATION_API = os.getenv("TRANSLATION_API", "google")
DEEPL_API_TOKEN = os.getenv("DEEPL_API_TOKEN", "")

# --- 媒体设置 ---
# 下载媒体文件的目录
MEDIA_DIR = os.getenv("MEDIA_DIR", "media")

# --- 重写内容设置 (AI 大模型生成) ---
# 填入 API Key 即可开启 AI 自动重写小红书爆款文案
# 支持任何兼容 OpenAI 接口格式的模型（如 DeepSeek, Kimi, ChatGPT 等）
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
