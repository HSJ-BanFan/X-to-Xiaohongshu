"""
X-to-XHS 主流程

从 X (Twitter) 抓取帖子内容，处理后发布到小红书。

用法:
    python run.py https://x.com/user/status/1234567890
    python run.py --file urls.txt
    python run.py https://x.com/user/status/1234567890 --scrape-only
"""

import argparse
import json
import logging
import os
import random
import sys
import time

# 强制终端输出 UTF-8，防止部分终端在打印 Emoji 时由于默认 gbk 编码报错崩溃
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from config import (
    X_COOKIES_FILE,
    X_BEARER_TOKEN,
    CHROME_USER_DATA_DIR,
    CHROME_PROFILE,
    XHS_WAIT_BEFORE_PUBLISH,
    BATCH_DELAY_MIN,
    BATCH_DELAY_MAX,
    ENABLE_TRANSLATION,
    TRANSLATION_API,
    DEEPL_API_TOKEN,
    MEDIA_DIR,
)
from .scraper import XScraper
from .poster import XiaohongshuPoster
from .utils import process_images_for_xhs

# ==========================================
# 日志配置
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("x_to_xhs.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ==========================================
# 断点续传
# ==========================================
PROCESSED_FILE = "processed_urls.json"


def _load_processed() -> set:
    """加载已成功处理的 URL 集合"""
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def _save_processed(urls: set):
    """保存已成功处理的 URL 集合"""
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(urls), f, ensure_ascii=False, indent=2)


def translate_text(text: str, source_lang: str = "EN", target_lang: str = "ZH") -> str:
    """
    翻译文本（可选功能）。

    支持 Google Translate（免费）和 DeepL。
    """
    if not text.strip():
        return text

    if TRANSLATION_API == "deepl" and DEEPL_API_TOKEN:
        try:
            import deepl
            translator = deepl.Translator(DEEPL_API_TOKEN)
            result = translator.translate_text(
                text,
                source_lang=source_lang,
                target_lang="ZH-HANS" if target_lang == "ZH" else target_lang,
            )
            return result.text
        except Exception as e:
            logger.warning(f"DeepL 翻译失败: {e}，回退到 Google Translate")

    # Google Translate（免费方案，使用 googletrans 库）
    try:
        from googletrans import Translator
        translator = Translator()
        result = translator.translate(text, src="en", dest="zh-cn")
        return result.text
    except Exception as e:
        logger.warning(f"Google 翻译也失败了: {e}")
        return text


def generate_xhs_title(text: str) -> str:
    """
    从推文正文中生成小红书标题（最多 20 字）。

    策略：取第一句话或前 20 个字。
    """
    import re
    text = re.sub(r'https?://\S+', '', text).strip()

    sentences = re.split(r'[。！？\n.!?]', text)
    first_sentence = sentences[0].strip() if sentences else text

    if len(first_sentence) <= 20:
        return first_sentence or "分享"

    return first_sentence[:20]


def process_single_tweet(
    tweet_url: str,
    scraper: XScraper,
    poster: XiaohongshuPoster = None,
    scrape_only: bool = False,
):
    """处理单条推文"""
    logger.info(f"{'='*60}")
    logger.info(f"[处理] {tweet_url}")
    logger.info(f"{'='*60}")

    # 1. 抓取推文数据
    tweet_data = scraper.scrape(tweet_url)

    logger.info(f"作者: @{tweet_data.author} ({tweet_data.author_name})")
    logger.info(f"正文: {tweet_data.text[:100]}{'...' if len(tweet_data.text) > 100 else ''}")
    logger.info(f"图片: {len(tweet_data.image_urls)} 张")
    logger.info(f"视频: {len(tweet_data.video_urls)} 个")

    # 2. 下载媒体
    media_subdir = os.path.join(MEDIA_DIR, tweet_data.tweet_id)
    image_paths, video_paths = scraper.download_media(tweet_data, media_subdir)

    use_long_article = False
    if not image_paths and not video_paths:
        logger.info("推文没有图片或视频，将使用小红书【写长文】模式发布...")
        use_long_article = True

    # 3. 图片预处理（resize + 加噪声）
    if image_paths and not use_long_article:
        logger.info("图片预处理（调整尺寸 + 防查重）...")
        image_paths = process_images_for_xhs(image_paths)

    # 4. 翻译文案（可选）
    text = tweet_data.text
    if ENABLE_TRANSLATION:
        logger.info("翻译文案...")
        text = translate_text(text)
        logger.info(f"翻译结果: {text[:100]}{'...' if len(text) > 100 else ''}")

    # 5. 生成标题与正文 (AI 改写或提取首句)
    from config import LLM_API_KEY

    has_text = bool(text and text.strip())

    if not has_text:
        # 纯图片/视频推文，没有文字内容
        logger.info("原推文无文本内容，使用简洁默认文案")
        title = "分享"
        content = f"via @{tweet_data.author}" if tweet_data.author else ""
    elif LLM_API_KEY:
        from .ai_generator import generate_xhs_content
        ai_title, ai_content = generate_xhs_content(text, tweet_data.author_name)
        if ai_title and ai_content:
            title = ai_title
            content = ai_content
        else:
            title = generate_xhs_title(text)
            content = text
    else:
        title = generate_xhs_title(text)
        content = text

    logger.info(f"小红书标题: {title}")

    # 6. 添加来源标注（如果开启）
    from config import ENABLE_AUTHOR_ATTRIBUTION
    if ENABLE_AUTHOR_ATTRIBUTION and tweet_data.author and has_text:
        content += f"\n\nvia @{tweet_data.author}"

    if scrape_only:
        logger.info("仅抓取模式，不发布到小红书")
        logger.info(f"  标题: {title}")
        logger.info(f"  正文: {content}")
        logger.info(f"  图片: {image_paths}")
        logger.info(f"  视频: {video_paths}")
        return

    # 7. 发布到小红书
    if poster is None:
        logger.error("未初始化小红书发布器")
        return

    poster.login()

    if video_paths:
        poster.post_note(
            title=title,
            content=content,
            video=video_paths[0],
            wait_before_publish=XHS_WAIT_BEFORE_PUBLISH,
        )
    elif use_long_article:
        poster.post_note(
            title=title,
            content=content,
            use_long_article=True,
            wait_before_publish=XHS_WAIT_BEFORE_PUBLISH,
        )
    elif image_paths:
        poster.post_note(
            title=title,
            content=content,
            images=image_paths,
            wait_before_publish=XHS_WAIT_BEFORE_PUBLISH,
        )

    logger.info("✓ 发布成功！")


def main():
    parser = argparse.ArgumentParser(
        description="X-to-XHS: 从 X (Twitter) 搬运内容到小红书",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run.py https://x.com/elonmusk/status/123456
  python run.py --file urls.txt
  python run.py https://x.com/user/status/123 --scrape-only
  python run.py --file urls.txt --no-resume
        """,
    )

    parser.add_argument("url", nargs="?", help="X/Twitter 推文 URL")
    parser.add_argument("--file", "-f", help="包含多个推文 URL 的文本文件（每行一个）")
    parser.add_argument("--scrape-only", "-s", action="store_true", help="仅抓取数据，不发布到小红书")
    parser.add_argument("--cookies", default=X_COOKIES_FILE, help="X cookies 文件路径")
    parser.add_argument("--no-resume", action="store_true", help="禁用断点续传，重新处理所有 URL")

    args = parser.parse_args()

    # 初始化目录和抓取器
    os.makedirs(MEDIA_DIR, exist_ok=True)
    cookies_file = args.cookies if os.path.exists(args.cookies) else None
    bearer = X_BEARER_TOKEN if X_BEARER_TOKEN else None
    scraper = XScraper(cookies_file=cookies_file, bearer_token=bearer)

    # 收集要处理的初始 URL
    urls = []
    interactive_mode = False
    
    if args.url:
        urls.append(args.url)
    elif args.file:
        if not os.path.exists(args.file):
            logger.error(f"文件不存在: {args.file}")
            sys.exit(1)
        with open(args.file, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    else:
        interactive_mode = True

    # 断点续传：过滤已处理的 URL
    processed_urls = set()
    if urls and not args.no_resume:
        processed_urls = _load_processed()
        pending = [u for u in urls if u not in processed_urls]
        skipped = len(urls) - len(pending)
        if skipped > 0:
            logger.info(f"断点续传：跳过 {skipped} 条已处理的 URL")
        urls = pending

    # 启动小红书发布器
    poster = None
    if not args.scrape_only:
        poster = XiaohongshuPoster(
            user_data_dir=CHROME_USER_DATA_DIR,
            profile=CHROME_PROFILE,
        )

    try:
        # 处理预加载的 URLs
        if urls:
            logger.info(f"共 {len(urls)} 条推文待处理")
            for idx, url in enumerate(urls, 1):
                logger.info(f"[进度] {idx}/{len(urls)}")
                try:
                    process_single_tweet(url, scraper, poster, args.scrape_only)
                    processed_urls.add(url)
                    _save_processed(processed_urls)
                except Exception as e:
                    logger.error(f"处理失败: {e}", exc_info=True)
                    continue

                # 批量模式随机延迟（防封号），最后一条不等
                if idx < len(urls):
                    delay = random.uniform(BATCH_DELAY_MIN, BATCH_DELAY_MAX)
                    logger.info(f"等待 {delay:.0f}s 后处理下一条...")
                    time.sleep(delay)

            logger.info(f"批量处理完毕，共 {len(urls)} 条")

        # 交互模式
        if interactive_mode:
            logger.info("======= 交互模式就绪 =======")
            logger.info("贴入 X/Twitter 链接并按回车处理。输入 'q' 或 'exit' 退出程序。")
            while True:
                try:
                    url = input("\n请输入推文 URL: ").strip()
                    if not url:
                        continue
                    if url.lower() in ['q', 'quit', 'exit']:
                        break
                    process_single_tweet(url, scraper, poster, args.scrape_only)
                except KeyboardInterrupt:
                    logger.info("正在退出...")
                    break
                except Exception as e:
                    logger.error(f"处理发生异常: {e}", exc_info=True)

    finally:
        if poster:
            poster.close()
            
    logger.info("程序已结束。")
