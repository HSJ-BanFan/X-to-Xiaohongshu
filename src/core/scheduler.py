"""
全自动调度器

使用 APScheduler 实现周期性自动运行：
  发现推文 → AI 评分 → 抓取/处理 → 发布到小红书

用法:
    from src.core.scheduler import AutoScheduler
    scheduler = AutoScheduler()
    scheduler.start()  # 阻塞运行
"""

import logging
import random
import signal
import sys
import time

from apscheduler.schedulers.blocking import BlockingScheduler

from config import (
    SCHEDULER_INTERVAL_MINUTES,
    SCHEDULER_MAX_POSTS_PER_RUN,
    BATCH_DELAY_MIN,
    BATCH_DELAY_MAX,
    X_COOKIES_FILE,
    X_BEARER_TOKEN,
    CHROME_USER_DATA_DIR,
    CHROME_PROFILE,
    MEDIA_DIR,
    AI_SCORING_ENABLED,
)

logger = logging.getLogger(__name__)


class AutoScheduler:
    """全自动调度：发现 → 评分 → 抓取 → 发布"""

    def __init__(self, interval_minutes: int = None, max_posts: int = None):
        self.interval = interval_minutes or SCHEDULER_INTERVAL_MINUTES
        self.max_posts = max_posts or SCHEDULER_MAX_POSTS_PER_RUN
        self._scheduler = BlockingScheduler()

    def _run_cycle(self):
        """执行一个完整的自动化周期"""
        import os
        from src.core.discovery import TweetDiscovery
        from src.automation.scraper import XScraper
        from src.automation.poster import XiaohongshuPoster

        logger.info("=" * 60)
        logger.info("🤖 自动化周期开始")
        logger.info("=" * 60)

        # 1. 发现推文
        try:
            discovery = TweetDiscovery()
            urls = discovery.discover_sync()
        except Exception as e:
            logger.error(f"推文发现失败: {e}", exc_info=True)
            return

        if not urls:
            logger.info("本轮没有发现新推文，跳过")
            return

        # 限制每轮处理数量
        if len(urls) > self.max_posts:
            logger.info(f"发现 {len(urls)} 条，本轮最多处理 {self.max_posts} 条")
            urls = urls[: self.max_posts]

        # 2. AI 评分（仅打分，不过滤）
        if AI_SCORING_ENABLED:
            from src.ai.generator import score_tweet_potential
            logger.info("📊 预评分推文...")
            for url in urls:
                try:
                    # 这里我们只有 URL，暂时用 URL 本身做简单标记；
                    # 实际评分会在 pipeline 中 scrape 之后进行
                    pass
                except Exception:
                    pass

        # 3. 抓取 + 处理 + 发布
        os.makedirs(MEDIA_DIR, exist_ok=True)
        cookies_file = X_COOKIES_FILE if os.path.exists(X_COOKIES_FILE) else None
        bearer = X_BEARER_TOKEN if X_BEARER_TOKEN else None
        scraper = XScraper(cookies_file=cookies_file, bearer_token=bearer)

        poster = XiaohongshuPoster(
            user_data_dir=CHROME_USER_DATA_DIR,
            profile=CHROME_PROFILE,
        )

        try:
            # 延迟导入避免循环引用
            from src.core.pipeline import process_single_tweet

            for idx, url in enumerate(urls, 1):
                logger.info(f"[自动处理] {idx}/{len(urls)}: {url}")
                try:
                    process_single_tweet(url, scraper, poster, scrape_only=False)
                except Exception as e:
                    logger.error(f"处理失败: {e}", exc_info=True)
                    continue

                # 随机延迟
                if idx < len(urls):
                    delay = random.uniform(BATCH_DELAY_MIN, BATCH_DELAY_MAX)
                    logger.info(f"等待 {delay:.0f}s...")
                    time.sleep(delay)

            logger.info(f"🎉 自动化周期完成，处理了 {len(urls)} 条推文")

        finally:
            poster.close()

    def start(self):
        """启动调度器（阻塞运行）"""
        logger.info(f"🚀 全自动模式启动！每 {self.interval} 分钟运行一次")
        logger.info(f"   每轮最多处理 {self.max_posts} 条推文")
        logger.info("   按 Ctrl+C 停止\n")

        # 立即执行一次
        self._run_cycle()

        # 设置定时任务
        self._scheduler.add_job(
            self._run_cycle,
            "interval",
            minutes=self.interval,
            id="auto_cycle",
            name="X-to-XHS 自动化周期",
        )

        # 优雅退出 (仅类 Unix 系统支持部分信号，Windows下使用 try-except 足矣)
        if sys.platform != "win32":
            def _graceful_shutdown(signum, frame):
                logger.info("\n⛔ 收到退出信号，正在关闭调度器...")
                self._scheduler.shutdown(wait=False)
                sys.exit(0)

            signal.signal(signal.SIGINT, _graceful_shutdown)
            signal.signal(signal.SIGTERM, _graceful_shutdown)

        try:
            self._scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("调度器已停止")


# --- 快速测试 ---
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    scheduler = AutoScheduler()
    scheduler.start()
