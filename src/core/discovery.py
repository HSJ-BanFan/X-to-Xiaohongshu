"""
推文自动发现模块

使用 twscrape 库按关键词搜索 X (Twitter) 上的高互动推文，
自动去重并输出候选 URL 列表。

包含 X 前端 JS 解析的 monkey patch（修复 unquoted keys 问题）。
"""

# ============================================================
# ⚠️ Monkey Patch — 必须在 import twscrape 之前执行！
# 修复 X 返回的 malformed JSON（unquoted keys），
# 否则 twscrape 会解析失败并锁定账号 15 分钟。
# 参考: https://github.com/vladkens/twscrape/issues/284
# ============================================================
import json
import re as _re


def _script_url(k: str, v: str):
    return f"https://abs.twimg.com/responsive-web/client-web/{k}.{v}.js"


def _patched_get_scripts_list(text: str):
    scripts = text.split('e=>e+"."+')[1].split('[e]+"a.js"')[0]

    try:
        for k, v in json.loads(scripts).items():
            yield _script_url(k, f"{v}a")
    except json.decoder.JSONDecodeError:
        # 修复 X 返回的 malformed JSON（unquoted keys）
        fixed_scripts = _re.sub(
            r'([,\{])(\s*)([\w]+_[\w_]+)(\s*):',
            r'\1\2"\3"\4:',
            scripts,
        )
        for k, v in json.loads(fixed_scripts).items():
            yield _script_url(k, f"{v}a")


try:
    from twscrape import xclid
    xclid.get_scripts_list = _patched_get_scripts_list
except Exception:
    pass  # twscrape 版本不同可能没有 xclid，跳过

# ============================================================
# 正常 imports
# ============================================================
import asyncio
import logging
import os
import random
from datetime import datetime

from config import (
    TWSCRAPE_USERNAME,
    TWSCRAPE_PASSWORD,
    TWSCRAPE_EMAIL,
    TWSCRAPE_EMAIL_PASSWORD,
    TWSCRAPE_COOKIES,
    DISCOVERY_NICHES,
    DISCOVERY_LIMIT_PER_NICHE,
    DISCOVERY_TOTAL_LIMIT,
    DISCOVERED_TWEETS_FILE,
    WHITELIST_ACCOUNTS,
    WHITELIST_ACCOUNTS_FILE,
)

logger = logging.getLogger(__name__)


class TweetDiscovery:
    """自动发现高质量推文"""

    def __init__(self, niches: list[str] = None, limit_per_niche: int = None):
        """
        Args:
            niches: 搜索关键词列表（X 高级搜索语法）。None 则使用 config 中的默认值。
            limit_per_niche: 每个 niche 最多抓取多少条。None 则使用 config 默认值。
        """
        self.niches = niches or DISCOVERY_NICHES
        self.limit = limit_per_niche or DISCOVERY_LIMIT_PER_NICHE
        self.total_limit = DISCOVERY_TOTAL_LIMIT
        self.discovered_file = DISCOVERED_TWEETS_FILE

    def _load_whitelist_accounts(self) -> set[str]:
        """加载白名单账号（配置列表 + 文件合并）"""
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

    def _load_discovered(self) -> set:
        """加载已发现的推文 URL 集合"""
        if os.path.exists(self.discovered_file):
            try:
                with open(self.discovered_file, "r", encoding="utf-8") as f:
                    return set(json.load(f))
            except (json.JSONDecodeError, Exception):
                pass
        return set()

    def _save_discovered(self, urls: set):
        """保存已发现的推文 URL"""
        os.makedirs(os.path.dirname(self.discovered_file) or ".", exist_ok=True)
        with open(self.discovered_file, "w", encoding="utf-8") as f:
            json.dump(sorted(urls), f, ensure_ascii=False, indent=2)

    async def _setup_api(self):
        """初始化 twscrape API 并添加账号"""
        from twscrape import API

        # 支持代理（非 TUN 模式时需要）
        from config import PROXY_URL
        api = API(proxy=PROXY_URL if PROXY_URL else None)

        if not TWSCRAPE_USERNAME:
            raise RuntimeError(
                "未配置 twscrape 账号信息！\n"
                "请在 config.py 中填写 TWSCRAPE_USERNAME / PASSWORD / EMAIL / EMAIL_PASSWORD / COOKIES"
            )

        # 添加账号（如果已存在则跳过）
        try:
            await api.pool.add_account(
                TWSCRAPE_USERNAME,
                TWSCRAPE_PASSWORD,
                TWSCRAPE_EMAIL,
                TWSCRAPE_EMAIL_PASSWORD,
                cookies=TWSCRAPE_COOKIES,
            )
        except Exception as e:
            logger.debug(f"添加账号时: {e}")

        # 重置限速锁定（解锁被 X 锁住的账号）
        await api.pool.reset_locks()
        await api.pool.login_all()

        return api

    async def discover(self) -> list[str]:
        """
        执行推文发现。

        Returns:
            新发现的推文 URL 列表（已去重）
        """
        logger.info("=" * 50)
        logger.info("🔍 开始自动发现推文...")
        logger.info(f"   共 {len(self.niches)} 个搜索 niche，本次运行最大总获取数: {self.total_limit} 条")
        logger.info("=" * 50)

        api = await self._setup_api()
        discovered = self._load_discovered()
        new_urls = []

        # 打乱 niches 的顺序，避免因为达到总上限导致总是忽略后排的 niches
        search_niches = list(self.niches)
        random.shuffle(search_niches)

        for idx, query in enumerate(search_niches, 1):
            if len(new_urls) >= self.total_limit:
                logger.info(f"🛑 已达到单次运行总获取上限 ({self.total_limit} 条)，结束关键词搜索。")
                break

            logger.info(f"[{idx}/{len(search_niches)}] 搜索: {query[:60]}...")
            count = 0
            try:
                async for tweet in api.search(query, limit=self.limit):
                    url = f"https://x.com/{tweet.user.username}/status/{tweet.id}"
                    if url not in discovered:
                        new_urls.append(url)
                        discovered.add(url)
                        count += 1
                        
                    if len(new_urls) >= self.total_limit:
                        break # 中断内部循环
            except Exception as e:
                logger.warning(f"   搜索出错: {e}")
                continue

            logger.info(f"   → 发现 {count} 条新推文，当前共 {len(new_urls)} 条")

            # 每搜完一个 niche 随机等 15~35 秒，降低触发限速的概率
            if idx < len(search_niches) and len(new_urls) < self.total_limit:
                wait = random.uniform(15, 35)
                logger.info(f"   ⏳ 冷却 {wait:.0f}s...")
                await asyncio.sleep(wait)

        # 搜索白名单账号的最新推文
        if len(new_urls) < self.total_limit:
            whitelist = self._load_whitelist_accounts()
            if whitelist:
                logger.info(f"📋 搜索 {len(whitelist)} 个白名单账号...")
                for handle in whitelist:
                    if len(new_urls) >= self.total_limit:
                        logger.info(f"🛑 达到总获取上限 ({self.total_limit} 条)，结束白名单搜索。")
                        break

                    query = f"from:{handle}"

                    logger.info(f"   白名单: @{handle}")
                    count = 0
                    try:
                        async for tweet in api.search(query, limit=self.limit):
                            url = f"https://x.com/{tweet.user.username}/status/{tweet.id}"
                            if url not in discovered:
                                new_urls.append(url)
                                discovered.add(url)
                                count += 1
                                
                            if len(new_urls) >= self.total_limit:
                                break
                    except Exception as e:
                        logger.warning(f"   搜索 @{handle} 出错: {e}")
                        continue
                        
                    logger.info(f"   → 发现 {count} 条新推文，当前共 {len(new_urls)} 条")
                    if len(new_urls) < self.total_limit:
                        wait = random.uniform(10, 25)
                        await asyncio.sleep(wait)

        # 保存去重记录
        self._save_discovered(discovered)

        logger.info(f"🎯 本轮共发现 {len(new_urls)} 条新推文")
        return new_urls

    def discover_sync(self) -> list[str]:
        """同步方式运行 discover（方便在非 async 上下文中调用）"""
        return asyncio.run(self.discover())

    def save_urls_to_file(self, urls: list[str], filepath: str = "urls.txt"):
        """将 URL 列表追加写入文件"""
        if not urls:
            logger.info("没有新推文需要保存")
            return

        with open(filepath, "a", encoding="utf-8") as f:
            for url in urls:
                f.write(url + "\n")

        logger.info(f"✅ {len(urls)} 条推文 URL 已追加到 {filepath}")


# --- 快速测试 ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    discovery = TweetDiscovery()
    urls = discovery.discover_sync()
    if urls:
        print(f"\n发现 {len(urls)} 条推文:")
        for u in urls:
            print(f"  {u}")
        discovery.save_urls_to_file(urls)
    else:
        print("没有发现新推文。")
