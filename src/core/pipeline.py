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
    AI_SCORING_ENABLED,
    QUALITY_FILTER_ENABLED,
    MIN_FAVORITES,
    MIN_RETWEETS,
    REQUIRE_MEDIA,
    WHITELIST_ACCOUNTS,
    WHITELIST_ACCOUNTS_FILE,
    KB_AUTO_INGEST,
    KB_RETRIEVE_COUNT,
    HYBRID_MODE_ENABLED,
    HYBRID_MODE_ENABLED,
    GROK_API_KEY,
    ENABLE_TOPIC_POOL_LEARNING,
)
from src.automation.scraper import XScraper
from src.automation.poster import XiaohongshuPoster
from src.utils.processor import process_images_for_xhs, translate_text
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


def _load_whitelist() -> set[str]:
    """加载白名单账号（配置列表 + 文件合并，统一小写）"""
    whitelist = {a.lower().lstrip("@") for a in WHITELIST_ACCOUNTS}
    if os.path.exists(WHITELIST_ACCOUNTS_FILE):
        try:
            with open(WHITELIST_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    handle = line.strip().lstrip("@")
                    if handle and not handle.startswith("#"):
                        whitelist.add(handle.lower())
        except Exception:
            pass
    return whitelist


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
    ingest_only: bool = False,
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
    logger.info(f"❤️ {tweet_data.favorite_count}  🔁 {tweet_data.retweet_count}  💬 {tweet_data.reply_count}")

    # AI 爆款评分（仅供参考，不过滤）
    if AI_SCORING_ENABLED:
        from src.ai.generator import score_tweet_potential
        media_count = len(tweet_data.image_urls) + len(tweet_data.video_urls)
        score, reason = score_tweet_potential(tweet_data.text, media_count)
        if score > 0:
            logger.info(f"📊 AI 爆款评分: {score}/10 — {reason}")
        else:
            logger.info(f"📊 AI 评分跳过: {reason}")

    # 质量过滤（白名单账号不受限制）
    if QUALITY_FILTER_ENABLED:
        whitelist = _load_whitelist()
        is_whitelisted = tweet_data.author.lower() in whitelist
        if not is_whitelisted:
            if REQUIRE_MEDIA and not tweet_data.image_urls and not tweet_data.video_urls:
                logger.info("⏭ 跳过: 无媒体内容")
                return
            if tweet_data.favorite_count < MIN_FAVORITES:
                logger.info(f"⏭ 跳过: 点赞 {tweet_data.favorite_count} < {MIN_FAVORITES}")
                return
            if tweet_data.retweet_count < MIN_RETWEETS:
                logger.info(f"⏭ 跳过: 转发 {tweet_data.retweet_count} < {MIN_RETWEETS}")
                return
        else:
            logger.info("✅ 白名单账号，跳过质量过滤")

    # 自动入库到知识库
    if KB_AUTO_INGEST:
        try:
            from src.ai.knowledge_base import KnowledgeBase
            kb = KnowledgeBase()
            kb.add_tweet(tweet_data)
        except Exception as e:
            logger.debug(f"知识库入库跳过: {e}")

    if ingest_only:
        logger.info("仅入库模式，不继续处理")
        return

    # 提取并保存主题池
    topic = ""
    if has_text := bool(tweet_data.text and tweet_data.text.strip()):
        from src.ai.generator import extract_topic_from_tweet
        topic = extract_topic_from_tweet(tweet_data.text)
        
        if ENABLE_TOPIC_POOL_LEARNING and topic:
            from src.core.topic_manager import TopicManager
            tm = TopicManager()
            if tm.add_topic(topic):
                logger.info(f"💾 主题「{topic}」已收录到主题库")

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

    # 5. 生成标题与正文
    from config import LLM_API_KEY

    has_text = bool(text and text.strip())
    title = ""
    content = ""

    if not has_text:
        # 纯图片/视频推文，没有文字内容 → 也可以走混合模式（Grok搜同类图片帖灵感）
        if HYBRID_MODE_ENABLED and GROK_API_KEY:
            logger.info("原推文无文本，使用混合模式根据媒体类型生成文案")
            from src.ai.generator import generate_hybrid_note
            fallback_topic = "生活美学 日常分享"
            title, content = generate_hybrid_note(fallback_topic)
        if not title:
            logger.info("原推文无文本内容，使用简洁默认文案")
            title = "分享"
            content = f"via @{tweet_data.author}" if tweet_data.author else ""

    elif HYBRID_MODE_ENABLED and GROK_API_KEY:
        # ===== 移花接木模式 =====
        # 用推文的真实图片 + Grok 搜同类爆款生成全新原创文案
        from src.ai.generator import generate_hybrid_note

        logger.info(f"🔄 移花接木模式：推文图片 + Grok 搜「{topic}」爆款灵感")

        # 尝试从本地 KB 补充灵感
        inspirations = None
        try:
            from src.ai.knowledge_base import KnowledgeBase
            kb = KnowledgeBase()
            if kb.stats().get("total_items", 0) > 0:
                inspirations = kb.retrieve(topic, n_results=KB_RETRIEVE_COUNT)
                if inspirations:
                    logger.info(f"📚 本地 KB 补充 {len(inspirations)} 条灵感")
        except Exception:
            pass

        ai_title, ai_content = generate_hybrid_note(topic, inspirations)
        if ai_title and ai_content:
            title = ai_title
            content = ai_content
        else:
            # 混合模式失败，回退到旧的改写模式
            logger.warning("混合模式失败，回退到 DeepSeek 改写")
            from src.ai.generator import generate_xhs_content
            ai_title, ai_content = generate_xhs_content(text, tweet_data.author_name)
            if ai_title and ai_content:
                title = ai_title
                content = ai_content

    elif LLM_API_KEY:
        # 旧模式：DeepSeek 直接改写
        from src.ai.generator import generate_xhs_content
        ai_title, ai_content = generate_xhs_content(text, tweet_data.author_name, media_count=len(image_paths) + len(video_paths))
        if ai_title and ai_content:
            title = ai_title
            content = ai_content

    # 兜底
    if not title:
        title = generate_xhs_title(text)
    if not content:
        content = text

    logger.info(f"小红书标题: {title}")

    # 6. 硬截断以防小红书发布报错（小红书上限 1000 字，这里截断至 950 字留余量）
    if len(content) > 950:
        logger.warning(f"AI 生成内容长度超限 ({len(content)} 字)，进行硬截断防报错")
        content = content[:950]

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
        description="X-to-XHS: 从 X (Twitter) 内容到小红书原创笔记",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run.py https://x.com/elonmusk/status/123456
  python run.py --file urls.txt
  python run.py --scrape-only https://x.com/user/status/123
  python run.py --ingest --file urls.txt       # 批量入库到知识库
  python run.py --create "花生酱减脂早餐"         # 从知识库生成原创笔记
  python run.py --kb-stats                      # 查看知识库状态
  python run.py --random-hybrid                 # 从主题库随机抽取主题进行混合生成
        """,
    )

    parser.add_argument("url", nargs="?", help="X/Twitter 推文 URL")
    parser.add_argument("--file", "-f", help="包含多个推文 URL 的文本文件（每行一个）")
    parser.add_argument("--scrape-only", "-s", action="store_true", help="仅抓取数据，不发布到小红书")
    parser.add_argument("--cookies", default=X_COOKIES_FILE, help="X cookies 文件路径")
    parser.add_argument("--no-resume", action="store_true", help="禁用断点续传，重新处理所有 URL")
    parser.add_argument("--discover", action="store_true", help="自动发现推文并保存到 urls.txt（不抓取不发布）")
    parser.add_argument("--auto", action="store_true", help="全自动模式: 定时发现 → 评分 → 抓取 → 发布")
    parser.add_argument("--ingest", action="store_true", help="入库模式: 抓取推文并存入知识库（不发布）")
    parser.add_argument("--create", metavar="TOPIC", help="原创模式: 从知识库生成原创笔记")
    parser.add_argument("--style", default="生活化、温暖、接地气", help="原创笔记写作风格")
    parser.add_argument("--kb-stats", action="store_true", help="查看知识库统计信息")
    parser.add_argument(
        "--hybrid", metavar="TOPIC",
        help="混合模式: Grok 实时搜索 + 本地知识库 → 原创笔记（最强）",
    )
    parser.add_argument("--random-hybrid", action="store_true", help="随机混合模式: 从主题库随机抽取主题并生成图文")

    args = parser.parse_args()

    # === 知识库统计 ===
    if args.kb_stats:
        from src.ai.knowledge_base import KnowledgeBase
        kb = KnowledgeBase()
        stats = kb.stats()
        print(f"\n{'='*40}")
        print(f"📚 知识库统计")
        print(f"{'='*40}")
        print(f"  总条目: {stats['total_items']}")
        print(f"  数据库: {stats['db_path']}")
        print(f"  嵌入模型: {stats['embedding_model']}")
        if stats.get('top_authors'):
            print(f"  作者数: {stats['unique_authors']}")
            print(f"  Top 作者:")
            for author, cnt in stats['top_authors']:
                print(f"    @{author}: {cnt} 条")
        # === 主题库统计 ===
        try:
            from src.core.topic_manager import TopicManager
            tm = TopicManager()
            tm_stats = tm.get_stats()
            print(f"\n{'='*40}")
            print(f"🎯 主题库统计")
            print(f"{'='*40}")
            print(f"  已收录主题数: {tm_stats['total_topics']}")
        except Exception as e:
            print(f"无法加载主题库统计: {e}")
            
        return

    # === 原创生成模式 ===
    if args.create:
        from src.ai.knowledge_base import KnowledgeBase
        from src.ai.generator import generate_original_note

        kb = KnowledgeBase()
        topic = args.create

        logger.info(f"🎨 原创模式：主题「{topic}」，风格「{args.style}」")
        inspirations = kb.retrieve(topic, n_results=KB_RETRIEVE_COUNT)

        if not inspirations:
            logger.error("知识库为空！请先用 --ingest --file urls.txt 入库推文")
            return

        title, content = generate_original_note(topic, inspirations, args.style)

        if title and content:
            print(f"\n{'='*50}")
            print(f"📝 原创笔记")
            print(f"{'='*50}")
            print(f"标题: {title}")
            print(f"\n{content}")
            print(f"{'='*50}")
            if not args.scrape_only:
                poster = XiaohongshuPoster(
                    user_data_dir=CHROME_USER_DATA_DIR, profile_dir=CHROME_PROFILE
                )
                logger.info("准备发布原创笔记...")
                poster.post_note(
                    title=title,
                    content=content,
                    images=[],
                    wait_before_publish=XHS_WAIT_BEFORE_PUBLISH,
                )
                logger.info("✓ 原创笔记发布成功！")
            else:
                logger.info("提示: 去掉 --scrape-only 可直接发布到小红书")
        else:
            logger.error("原创生成失败")
        return

    # === 混合模式（Grok 实时 + 本地 KB）===
    if args.hybrid or args.random_hybrid:
        from src.ai.generator import generate_hybrid_note

        if args.random_hybrid:
            from src.core.topic_manager import TopicManager
            tm = TopicManager()
            topic = tm.get_random_topic()
            if not topic:
                logger.error("主题库为空！无法随机选择主题")
                return
            logger.info(f"🎲 随机抽取主题: 「{topic}」")
        else:
            topic = args.hybrid

        logger.info(f"🔄 混合模式：主题「{topic}」，风格「{args.style}」")

        # 尝试从本地 KB 获取灵感（可选, 没有也没关系）
        inspirations = []
        try:
            from src.ai.knowledge_base import KnowledgeBase
            kb = KnowledgeBase()
            stats = kb.stats()
            if stats.get("total_items", 0) > 0:
                inspirations = kb.retrieve(topic, n_results=KB_RETRIEVE_COUNT)
                logger.info(f"📚 本地知识库贡献 {len(inspirations)} 条灵感")
            else:
                logger.info("📚 本地知识库为空，仅使用 Grok 实时搜索")
        except Exception as e:
            logger.info(f"📚 知识库不可用（{e}），仅使用 Grok 实时搜索")

        title, content = generate_hybrid_note(
            topic, inspirations or None, args.style
        )

        if title and content:
            print(f"\n{'='*50}")
            print(f"📝 混合模式原创笔记")
            print(f"{'='*50}")
            print(f"标题: {title}")
            print(f"\n{content}")
            print(f"{'='*50}")
            if not args.scrape_only:
                poster = XiaohongshuPoster(
                    user_data_dir=CHROME_USER_DATA_DIR, profile_dir=CHROME_PROFILE
                )
                logger.info("准备发布混合模式笔记...")
                poster.post_note(
                    title=title,
                    content=content,
                    images=[],
                    wait_before_publish=XHS_WAIT_BEFORE_PUBLISH,
                )
                logger.info("✓ 混合模式发布成功！")
            else:
                logger.info("提示: 去掉 --scrape-only 即可自动发布到小红书")
        else:
            logger.error("混合模式生成失败，请检查 GROK_API_KEY 配置")
        return

    # === 自动发现模式 ===
    if args.discover:
        from src.core.discovery import TweetDiscovery
        logger.info("🔍 自动发现模式：搜索推文并保存到 urls.txt")
        discovery = TweetDiscovery()
        urls = discovery.discover_sync()
        if urls:
            discovery.save_urls_to_file(urls)
            logger.info(f"发现完成！共 {len(urls)} 条新推文，已保存到 urls.txt")
            logger.info("下一步: python run.py --file urls.txt")
        else:
            logger.info("没有发现新推文")
        return

    # === 全自动模式 ===
    if args.auto:
        from src.core.scheduler import AutoScheduler
        logger.info("🤖 全自动模式启动")
        scheduler = AutoScheduler()
        scheduler.start()
        return

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
                    process_single_tweet(
                        url, scraper, poster,
                        scrape_only=args.scrape_only,
                        ingest_only=getattr(args, 'ingest', False),
                    )
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
