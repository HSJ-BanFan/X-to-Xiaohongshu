# X-to-XHS 自动搬运工具

从 X (Twitter) 帖子自动抓取图文/视频内容，处理后一键发布到小红书。

## 功能

- 🔗 输入 X/Twitter 帖子链接，自动提取文本、图片、视频
- 🖼️ 图片自动适配小红书最佳比例 (3:4 / 1080×1440)
- 🔒 图片自动加微噪声，防止 MD5 查重限流
- 🌐 可选翻译功能（Google / DeepL）
- 📝 AI 自动生成小红书爆款标题和正文
- 🤖 Selenium 自动发布到小红书创作者平台
- 📂 支持单条 / 批量 / 仅抓取 / 交互模式
- 💾 批量模式自动断点续传 + 随机间隔防封号

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

复制配置模板并修改：

```bash
cp config.example.py config.py
```

编辑 `config.py`，按需填写：
- `X_COOKIES_FILE` — 如果 Guest Token 失效，需要提供 X 的 cookies（存放在 `data/` 目录）
- `CHROME_USER_DATA_DIR` — 复用已有 Chrome 登录态（推荐）
- `LLM_API_KEY` — 填入后自动开启 AI 文案改写

所有配置项均支持通过环境变量覆盖。

### 3. 运行

```bash
# 单条推文
python run.py https://x.com/user/status/1234567890

# 批量处理
python run.py --file urls.txt

# 仅抓取，不发布
python run.py https://x.com/user/status/1234567890 --scrape-only

# 交互模式（不传参直接运行）
python run.py
```

首次运行时，小红书创作者平台会打开登录页，请用手机扫码登录。之后 cookies 会被缓存，下次自动登录。

## 项目结构

```
xhs/
├── run.py                    # 启动入口
├── config.py                 # 用户配置
├── config.example.py         # 配置模板
├── requirements.txt
│
├── src/                      # 核心代码
│   ├── pipeline.py           #   主流程
│   ├── scraper.py            #   X 数据抓取（GraphQL + syndication 双重回退）
│   ├── poster.py             #   小红书自动发布（undetected_chromedriver）
│   ├── ai_generator.py       #   AI 文案生成
│   └── utils.py              #   工具函数（图片处理、URL 解析）
│
├── data/                     # 运行时数据（cookies 等，已 gitignore）
├── media/                    # 下载的媒体文件
└── _debug/                   # 调试文件
```

## X Cookies 获取方法

如果 Guest Token 无法使用，需要从浏览器导出 X 的 cookies：

1. 安装浏览器插件 [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally) 或 [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor)
2. 登录 x.com
3. 导出 cookies 为 JSON 格式，保存为 `data/x_cookies.json`

## ⚠️ 注意事项

- 小红书对自动化操作有反爬检测，建议使用 `CHROME_USER_DATA_DIR` 复用真实浏览器 profile
- 不要使用无头浏览器 (headless) 模式
- 批量模式默认每条间隔 30~90 秒随机延迟，可通过 `BATCH_DELAY_MIN` / `BATCH_DELAY_MAX` 调整
- 本工具仅供学习交流，请遵守各平台使用规则
