# X-to-XHS 自动搬运工具

从 X (Twitter) 帖子自动抓取图文/视频内容，处理后一键发布到小红书。支持**全自动发现推文 + AI 评分 + 定时调度**。

## 功能

- 🔗 输入 X/Twitter 帖子链接，自动提取文本、图片、视频
- 🖼️ 图片自动适配小红书最佳比例 (3:4 / 1080×1440)
- 🔒 图片自动加微噪声，防止 MD5 查重限流
- 🌐 可选翻译功能（Google / DeepL）
- 📝 AI 自动生成小红书爆款标题和正文
- 🤖 Selenium 自动发布到小红书创作者平台
- 📂 支持单条 / 批量 / 仅抓取 / 交互模式
- 💾 批量模式自动断点续传 + 随机间隔防封号
- 🔍 **自动发现推文** — 基于 twscrape 按关键词搜索高互动推文（支持自定义 niche）
- 📊 **AI 爆款评分** — LLM 自动评估推文搬运到小红书的爆款潜力（1-10 分，仅供参考）
- ⏰ **全自动调度** — APScheduler 定时运行：发现 → 评分 → 抓取 → 发布

## 快速开始

### 1. 安装依赖

> **注意**：twscrape 需要 Python >= 3.10

```bash
pip install -r requirements.txt
```

### 2. 配置

复制配置模板并修改：

```bash
cp config.example.py config.py
```

编辑 `config.py`，按需填写：

| 配置项 | 说明 |
|--------|------|
| `X_COOKIES_FILE` | X 的 cookies 文件路径（Guest Token 失效时需要） |
| `CHROME_USER_DATA_DIR` | 复用已有 Chrome 登录态（推荐） |
| `LLM_API_KEY` | 填入后自动开启 AI 文案改写 + 爆款评分 |
| `TWSCRAPE_USERNAME` | X 账号用户名（用于自动发现推文） |
| `TWSCRAPE_PASSWORD` | X 账号密码 |
| `TWSCRAPE_EMAIL` | 账号绑定邮箱 |
| `TWSCRAPE_COOKIES` | 浏览器 cookies 字符串（`auth_token=xxx; ct0=yyy`） |
| `DISCOVERY_NICHES` | 搜索关键词列表（支持 X 高级搜索语法） |

所有配置项均支持通过环境变量覆盖。

### 3. 运行

```bash
# 单条推文
python run.py https://x.com/user/status/1234567890

# 批量处理
python run.py --file urls.txt

# 仅抓取，不发布
python run.py https://x.com/user/status/1234567890 --scrape-only

# 自动发现推文（搜索爆款推文并保存到 urls.txt）
python run.py --discover

# 全自动模式（定时：发现 → 评分 → 抓取 → 发布）
python run.py --auto

# 交互模式（不传参直接运行）
python run.py
```

首次运行时，小红书创作者平台会打开登录页，请用手机扫码登录。之后 cookies 会被缓存，下次自动登录。

### 典型工作流

```bash
# 第一步：自动发现推文
python run.py --discover
# → 搜索 7 个 niche，发现 70 条高互动推文，保存到 urls.txt

# 第二步：处理并发布
python run.py --file urls.txt
# → 逐条抓取、AI 评分、生成文案、发布到小红书

# 或者一步到位：全自动模式
python run.py --auto
# → 每 4 小时自动执行一轮（可在 config.py 中调整间隔）
```

## 项目结构

```
xhs/
├── run.py                    # 启动入口
├── config.py                 # 用户配置
├── config.example.py         # 配置模板
├── requirements.txt
│
├── src/                      # 核心代码
│   ├── pipeline.py           #   主流程（CLI 解析 + 流程编排）
│   ├── scraper.py            #   X 数据抓取（GraphQL + syndication 双重回退）
│   ├── poster.py             #   小红书自动发布（undetected_chromedriver）
│   ├── ai_generator.py       #   AI 文案生成 + 爆款评分
│   ├── discovery.py          #   推文自动发现（twscrape 搜索）
│   ├── scheduler.py          #   全自动调度器（APScheduler）
│   └── utils.py              #   工具函数（图片处理、URL 解析）
│
├── data/                     # 运行时数据（cookies 等，已 gitignore）
├── media/                    # 下载的媒体文件
└── _debug/                   # 调试文件
```

## 自定义搜索关键词

在 `config.py` 中修改 `DISCOVERY_NICHES` 列表，支持 X 高级搜索语法：

```python
DISCOVERY_NICHES = [
    # 宠物
    'cute cat OR cute dog filter:images min_faves:100 lang:en',
    # 美景
    'sunset OR sunrise OR "golden hour" filter:images min_faves:200',
    # 美食
    '"cafe aesthetic" OR "what I eat in a day" filter:media min_faves:50',
    # 自定义...
]
```

常用搜索语法：
- `filter:images` — 仅含图片
- `filter:media` — 含图片或视频
- `min_faves:100` — 最低 100 赞
- `lang:en` — 英文推文
- `since:2024-01-01` — 时间范围

## X Cookies 获取方法

如果 Guest Token 无法使用，需要从浏览器导出 X 的 cookies：

1. 安装浏览器插件 [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally) 或 [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor)
2. 登录 x.com
3. 导出 cookies 为 JSON 格式，保存为 `data/x_cookies.json`

## ⚠️ 注意事项

- 小红书对自动化操作有反爬检测，建议使用 `CHROME_USER_DATA_DIR` 复用真实浏览器 profile
- 不要使用无头浏览器 (headless) 模式
- 批量模式默认每条间隔 30~90 秒随机延迟，可通过 `BATCH_DELAY_MIN` / `BATCH_DELAY_MAX` 调整
- twscrape 使用 X 内部 API，单账号搜索频繁会触发 15 分钟限速，建议配合多账号使用
- 本工具仅供学习交流，请遵守各平台使用规则
