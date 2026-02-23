"""
X (Twitter) 数据抓取模块

策略:
1. 主方案: requests + X GraphQL API (TweetResultByRestId)
2. 媒体下载: yt-dlp
3. 回退: syndication.twitter.com embed API
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional

import requests
import yt_dlp

from .utils import parse_tweet_id, download_file


@dataclass
class TweetData:
    """推文结构化数据"""
    tweet_id: str = ""
    text: str = ""
    author: str = ""
    author_name: str = ""
    image_urls: list[str] = field(default_factory=list)
    video_urls: list[str] = field(default_factory=list)
    created_at: str = ""
    raw: dict = field(default_factory=dict, repr=False)


class XScraper:
    """X (Twitter) 内容抓取器"""

    # X 公开的 Bearer Token（Web App 使用的固定 token）
    PUBLIC_BEARER = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"

    GRAPHQL_URL = "https://x.com/i/api/graphql/0hWvDhmW8YQ-S_ib3azIrw/TweetResultByRestId"

    # GraphQL 查询参数
    FEATURES = {
        "creator_subscriptions_tweet_preview_api_enabled": True,
        "communities_web_enable_tweet_community_results_fetch": True,
        "c9s_tweet_anatomy_moderator_badge_enabled": True,
        "articles_preview_enabled": True,
        "responsive_web_edit_tweet_api_enabled": True,
        "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
        "view_counts_everywhere_api_enabled": True,
        "longform_notetweets_consumption_enabled": True,
        "responsive_web_twitter_article_tweet_consumption_enabled": True,
        "tweet_awards_web_tipping_enabled": False,
        "creator_subscriptions_quote_tweet_preview_enabled": False,
        "freedom_of_speech_not_reach_fetch_enabled": True,
        "standardized_nudges_misinfo": True,
        "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
        "rweb_video_timestamps_enabled": True,
        "longform_notetweets_rich_text_read_enabled": True,
        "longform_notetweets_inline_media_enabled": True,
        "rweb_tipjar_consumption_enabled": True,
        "responsive_web_graphql_exclude_directive_enabled": True,
        "verified_phone_label_enabled": False,
        "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
        "responsive_web_graphql_timeline_navigation_enabled": True,
        "responsive_web_enhance_cards_enabled": False,
    }

    FIELD_TOGGLES = {
        "withArticlePlainText": False,
        "withArticleRichContentState": False,
        "withAuxiliaryUserLabels": False,
    }

    def __init__(self, cookies_file: str = None, bearer_token: str = None):
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        self.session = requests.Session()
        self.session.verify = False  # 忽略 SSL 证书验证，防止本地代理抛出 SSLEOFError
        self.session.trust_env = False  # 忽略系统/环境代理配置，完全交给 Clash TUN 处理
        
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        })

        # 配置代理
        from config import PROXY_URL
        if PROXY_URL:
            self.session.proxies = {
                "http": PROXY_URL,
                "https": PROXY_URL,
            }

        self.bearer_token = bearer_token or self.PUBLIC_BEARER
        self.cookies_file = cookies_file
        self._guest_token = None
        self._ct0 = None

    def _activate_guest_token(self) -> str:
        """获取 Guest Token"""
        resp = self.session.post(
            "https://api.x.com/1.1/guest/activate.json",
            headers={"Authorization": f"Bearer {self.bearer_token}"},
        )
        resp.raise_for_status()
        token = resp.json().get("guest_token")
        if not token:
            raise RuntimeError("无法获取 Guest Token")
        self._guest_token = token
        return token

    def _load_cookies(self) -> bool:
        """从 cookies 文件加载认证信息"""
        if not self.cookies_file or not os.path.exists(self.cookies_file):
            return False

        try:
            with open(self.cookies_file, "r", encoding="utf-8") as f:
                cookies = json.load(f)

            # 支持两种格式: [{name, value, ...}] 或 {name: value}
            if isinstance(cookies, list):
                for c in cookies:
                    name = c.get("name", c.get("Name", ""))
                    value = c.get("value", c.get("Value", ""))
                    if name and value:
                        self.session.cookies.set(name, value, domain=".x.com")
            elif isinstance(cookies, dict):
                for name, value in cookies.items():
                    self.session.cookies.set(name, value, domain=".x.com")

            self._ct0 = self.session.cookies.get("ct0", domain=".x.com")
            return bool(self._ct0)
        except Exception as e:
            print(f"[警告] 加载 cookies 失败: {e}")
            return False

    def _build_auth_headers(self) -> dict:
        """构建认证请求头"""
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
        }

        if self._ct0:
            # 使用 cookies 认证
            headers["x-csrf-token"] = self._ct0
        elif self._guest_token:
            # 使用 Guest Token
            headers["x-guest-token"] = self._guest_token
        else:
            # 尝试获取 Guest Token
            try:
                self._activate_guest_token()
                headers["x-guest-token"] = self._guest_token
            except Exception:
                # 尝试加载 cookies
                if self._load_cookies():
                    headers["x-csrf-token"] = self._ct0
                else:
                    raise RuntimeError(
                        "无法认证 X API。请提供有效的 cookies 文件 (data/x_cookies.json) "
                        "或确保 Guest Token 可用。"
                    )

        return headers

    def _fetch_via_graphql(self, tweet_id: str) -> dict:
        """通过 GraphQL API 获取推文数据"""
        variables = {
            "tweetId": tweet_id,
            "withCommunity": False,
            "includePromotedContent": False,
            "withVoice": False,
        }

        params = {
            "variables": json.dumps(variables),
            "features": json.dumps(self.FEATURES),
            "fieldToggles": json.dumps(self.FIELD_TOGGLES),
        }

        headers = self._build_auth_headers()
        resp = self.session.get(self.GRAPHQL_URL, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def _fetch_via_syndication(self, tweet_id: str) -> dict:
        """回退方案：通过 syndication embed API 获取"""
        url = f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&lang=en&token=x"
        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.json()

    def _extract_tweet_text(self, result: dict) -> str:
        """从 GraphQL result 节点提取包含展开 URL 的完整文本 (支持 NoteTweet/长推文)"""
        legacy = result.get("legacy", {})
        text = legacy.get("full_text", "")
        entity_source = legacy.get("entities", {})

        # 检查是否为长推文 (NoteTweet)
        note_tweet_result = result.get("note_tweet", {}).get("note_tweet_results", {}).get("result", {})
        if note_tweet_result:
            text = note_tweet_result.get("text", text)
            entity_source = note_tweet_result.get("entity_set", entity_source)

        urls = entity_source.get("urls", [])
        media_entities = entity_source.get("media", [])
        
        # NoteTweet entity_set 似乎不包含 media，尝试回退到 legacy 的 media
        if not media_entities:
            media_entities = legacy.get("entities", {}).get("media", [])

        # 展开 URL
        for u in urls:
            text = text.replace(u.get("url", ""), u.get("expanded_url", ""))
        
        # 移除 t.co 媒体链接
        for m in media_entities:
            text = text.replace(m.get("url", ""), "").strip()

        return text

    def _parse_graphql_response(self, data: dict) -> TweetData:
        """解析 GraphQL 响应"""
        tweet_data = TweetData()

        try:
            result = data["data"]["tweetResult"]["result"]

            # 处理 tombstone（推文被删除或受限）
            if result.get("__typename") == "TweetTombstone":
                raise ValueError("此推文已被删除或受限，无法访问")

            # 处理 TweetWithVisibilityResults 包装
            if result.get("__typename") == "TweetWithVisibilityResults":
                result = result.get("tweet", result)

            tweet_data.raw = result

            # 基本信息
            legacy = result.get("legacy", {})
            core = result.get("core", {})
            user_results = core.get("user_results", {}).get("result", {})
            user_legacy = user_results.get("legacy", {})

            tweet_data.tweet_id = legacy.get("id_str", "")
            tweet_data.text = self._extract_tweet_text(result)
            tweet_data.author = user_legacy.get("screen_name", "")
            tweet_data.author_name = user_legacy.get("name", "")
            tweet_data.created_at = legacy.get("created_at", "")

            # 提取媒体
            extended_media = legacy.get("extended_entities", {}).get("media", [])
            for media in extended_media:
                media_type = media.get("type", "")
                if media_type == "photo":
                    # 取原图
                    url = media.get("media_url_https", "")
                    if url:
                        tweet_data.image_urls.append(f"{url}?format=jpg&name=orig")
                elif media_type in ("video", "animated_gif"):
                    variants = media.get("video_info", {}).get("variants", [])
                    # 选最高码率的 mp4
                    mp4_variants = [v for v in variants if v.get("content_type") == "video/mp4"]
                    if mp4_variants:
                        best = max(mp4_variants, key=lambda v: v.get("bitrate", 0))
                        tweet_data.video_urls.append(best["url"])

            # 提取被引用的推文 (Quote Tweet)
            quoted_result = result.get("quoted_status_result", {}).get("result", {})
            if quoted_result.get("__typename") == "TweetWithVisibilityResults":
                quoted_result = quoted_result.get("tweet", quoted_result)
            
            if quoted_result:
                quoted_text = self._extract_tweet_text(quoted_result)
                if quoted_text:
                    tweet_data.text += f"\n\n[引用推文]:\n{quoted_text}"

        except KeyError as e:
            raise ValueError(f"解析推文数据失败，字段缺失: {e}")

        return tweet_data

    def _parse_syndication_response(self, data: dict) -> TweetData:
        """解析 syndication API 响应"""
        tweet_data = TweetData()
        tweet_data.raw = data
        tweet_data.tweet_id = str(data.get("id_str", ""))
        tweet_data.text = data.get("text", "")
        tweet_data.created_at = data.get("created_at", "")

        user = data.get("user", {})
        tweet_data.author = user.get("screen_name", "")
        tweet_data.author_name = user.get("name", "")

        # syndication 的媒体在 mediaDetails 中
        for media in data.get("mediaDetails", []):
            if media.get("type") == "photo":
                url = media.get("media_url_https", "")
                if url:
                    tweet_data.image_urls.append(f"{url}?format=jpg&name=orig")
            elif media.get("type") == "video":
                variants = media.get("video_info", {}).get("variants", [])
                mp4s = [v for v in variants if v.get("content_type") == "video/mp4"]
                if mp4s:
                    best = max(mp4s, key=lambda v: v.get("bitrate", 0))
                    tweet_data.video_urls.append(best["url"])

        return tweet_data

    def scrape(self, url: str) -> TweetData:
        """
        抓取推文内容。

        Args:
            url: X/Twitter 推文 URL

        Returns:
            TweetData 结构化数据
        """
        tweet_id = parse_tweet_id(url)
        print(f"[X抓取] Tweet ID: {tweet_id}")

        # 策略 1: GraphQL API
        try:
            print("[X抓取] 尝试 GraphQL API...")
            data = self._fetch_via_graphql(tweet_id)
            tweet_data = self._parse_graphql_response(data)
            print(f"[X抓取] GraphQL 成功 — 作者: @{tweet_data.author}, "
                  f"图片: {len(tweet_data.image_urls)}, 视频: {len(tweet_data.video_urls)}")
            return tweet_data
        except Exception as e:
            print(f"[X抓取] GraphQL 失败: {e}")

        # 策略 2: Syndication API
        try:
            print("[X抓取] 尝试 Syndication API...")
            data = self._fetch_via_syndication(tweet_id)
            tweet_data = self._parse_syndication_response(data)
            print(f"[X抓取] Syndication 成功 — 作者: @{tweet_data.author}, "
                  f"图片: {len(tweet_data.image_urls)}, 视频: {len(tweet_data.video_urls)}")
            return tweet_data
        except Exception as e:
            print(f"[X抓取] Syndication 也失败了: {e}")

        raise RuntimeError(
            f"无法抓取推文 {url}。请检查:\n"
            "1. 推文 URL 是否正确且公开可访问\n"
            "2. 是否需要提供有效的 cookies 文件\n"
            "3. 网络连接是否正常（可能需要代理）"
        )

    def download_media(self, tweet_data: TweetData, output_dir: str) -> tuple[list[str], list[str]]:
        """
        下载推文中的媒体文件。

        Args:
            tweet_data: 抓取到的推文数据
            output_dir: 保存目录

        Returns:
            (image_paths, video_paths) 下载后的本地文件路径
        """
        os.makedirs(output_dir, exist_ok=True)
        image_paths = []
        video_paths = []

        # 下载图片
        for idx, img_url in enumerate(tweet_data.image_urls):
            ext = "jpg"
            save_path = os.path.join(output_dir, f"{tweet_data.tweet_id}_img_{idx}.{ext}")
            try:
                print(f"[下载] 图片 {idx + 1}/{len(tweet_data.image_urls)}: {save_path}")
                download_file(img_url, save_path)
                image_paths.append(save_path)
            except Exception as e:
                print(f"[下载] 图片下载失败: {e}")

        # 下载视频 (使用 yt-dlp 获取最佳质量)
        if tweet_data.video_urls:
            for idx, video_url in enumerate(tweet_data.video_urls):
                save_path = os.path.join(output_dir, f"{tweet_data.tweet_id}_vid_{idx}.mp4")
                try:
                    print(f"[下载] 视频 {idx + 1}/{len(tweet_data.video_urls)}")
                    # 直接下载已解析的视频 URL
                    download_file(video_url.split("?")[0] if "?" in video_url else video_url, save_path)
                    video_paths.append(save_path)
                except Exception as e:
                    print(f"[下载] 直接下载失败，尝试 yt-dlp: {e}")
                    try:
                        video_paths.extend(
                            self._download_via_ytdlp(
                                f"https://x.com/i/status/{tweet_data.tweet_id}",
                                output_dir,
                                tweet_data.tweet_id,
                            )
                        )
                    except Exception as e2:
                        print(f"[下载] yt-dlp 也失败了: {e2}")

        return image_paths, video_paths

    def _download_via_ytdlp(self, url: str, output_dir: str, tweet_id: str) -> list[str]:
        """使用 yt-dlp 下载视频"""
        output_template = os.path.join(output_dir, f"{tweet_id}_vid_%(autonumber)s.%(ext)s")
        ydl_opts = {
            "outtmpl": output_template,
            "format": "best[ext=mp4]/best",
            "quiet": True,
            "no_warnings": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        # 收集下载的文件
        downloaded = []
        if info:
            filename = ydl.prepare_filename(info)
            if os.path.exists(filename):
                downloaded.append(filename)

        return downloaded


# --- 快速测试 ---
if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else input("请输入 Tweet URL: ")
    scraper = XScraper()
    data = scraper.scrape(url)
    print(f"\n{'='*50}")
    print(f"作者: @{data.author} ({data.author_name})")
    print(f"时间: {data.created_at}")
    print(f"正文: {data.text}")
    print(f"图片: {data.image_urls}")
    print(f"视频: {data.video_urls}")
