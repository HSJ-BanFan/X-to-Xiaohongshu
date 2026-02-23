import json
import logging
import time
import requests

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 5  # 秒


def extract_topic_from_tweet(tweet_text: str) -> str:
    """
    从推文文本中提取核心主题关键词（2-5个词），
    用于喂给 Grok 实时搜索做灵感扩展。

    使用 LLM 提取；如果 LLM 不可用则截取前30字。
    """
    import re
    # 清理链接
    clean = re.sub(r'https?://\S+', '', tweet_text).strip()
    if not clean:
        return "生活分享"

    if not LLM_API_KEY:
        return clean[:30]

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "你是关键词提取器，只输出2-5个中文关键词，用空格分隔，不要任何其他内容。"},
            {"role": "user", "content": f"提取这段内容的核心主题关键词（适合小红书搜索的）：\n{clean[:500]}"},
        ],
        "temperature": 0.3,
        "max_tokens": 30,
    }

    session = requests.Session()
    session.trust_env = False
    try:
        resp = session.post(f"{LLM_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        keywords = resp.json()["choices"][0]["message"]["content"].strip()
        logger.info(f"🏷️ 提取主题关键词: {keywords}")
        return keywords
    except Exception as e:
        logger.debug(f"关键词提取失败: {e}，使用原文截取")
        return clean[:30]


def generate_xhs_content(tweet_text: str, author_name: str) -> tuple[str, str]:
    """
    使用 LLM 根据推文原文生成小红书风格的标题和正文。
    返回: (title, content)
    """
    if not LLM_API_KEY:
        logger.warning("未配置 LLM_API_KEY，跳过 AI 生成，返回原文。")
        return "", tweet_text

    logger.info(f"正在调用 {LLM_MODEL} 生成小红书文案...")

    prompt = f"""
    你是小红书资深文案写手。把以下素材改写成一篇原生风格的小红书图文笔记，让读者觉得这就是你自己的原创内容。

    素材（来自 {author_name}）：
    \"\"\"
    {tweet_text}
    \"\"\"

    铁律（违反任何一条即为失败）：
    1. 🚫【绝对禁止暴露来源】：正文中禁止出现"推文"、"原推"、"Twitter"、"X 平台"、"搬运"、"转载"、"翻译"、"原文是"等任何暗示内容并非原创的词汇。必须以第一人称写作，把内容当成自己的发现/经历来分享。
    2. 🚫【禁止套话】：禁止使用"姐妹们"、"家人们"、"宝子们"、"小仙女"等套话。
    3. 如果素材文字很少甚至只有一两个词，就围绕配图可能的主题写一段简短走心的分享即可，不要硬凑字数。
    4. 如果素材包含 http/https 链接，必须原样保留在正文中。
    5. 分段清晰，适度使用 Emoji。
    6. 结尾加一句互动引导。
    7. 结尾加 3-5 个 #话题标签（纯文字，格式如：#宠物 #日常）。

    【标题】：20字以内，有吸引力。
    【输出格式】：纯 JSON，不要 markdown 代码块：
    {{
        "title": "标题",
        "content": "正文"
    }}
    """

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "你是一个输出纯 JSON 的 API 服务器。不要输出任何多余的开头和结尾说明，不要使用 Markdown 代码块。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.85,
        "response_format": {"type": "json_object"}
    }

    last_error = None
    session = requests.Session()
    session.trust_env = False

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.post(
                f"{LLM_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            result = response.json()

            reply_text = result["choices"][0]["message"]["content"].strip()

            # 容错：如果模型还是加了 markdown
            if reply_text.startswith("```json"):
                reply_text = reply_text[7:]
            if reply_text.startswith("```"):
                reply_text = reply_text[3:]
            if reply_text.endswith("```"):
                reply_text = reply_text[:-3]

            data = json.loads(reply_text.strip())
            title = data.get("title", "")[:20]  # 强行截断 20 字
            content = data.get("content", "")

            logger.info("AI 文案生成完毕！")
            return title, content

        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                logger.warning(f"AI 生成第 {attempt} 次失败: {e}，{RETRY_DELAY}s 后重试...")
                time.sleep(RETRY_DELAY)
            else:
                logger.error(f"AI 生成最终失败（共 {MAX_RETRIES} 次尝试）: {last_error}")

    logger.info("退回原始文案拼接...")
    return "", tweet_text


def score_tweet_potential(tweet_text: str, media_count: int = 0) -> tuple[int, str]:
    """
    使用 LLM 评估推文在小红书的爆款潜力。

    仅供参考，不做过滤。返回: (score: 1-10, reason: 简短理由)
    """
    if not LLM_API_KEY:
        return 0, "未配置 LLM_API_KEY，跳过评分"

    prompt = f"""你是小红书内容运营专家。请评估以下推文搬运到小红书后的爆款潜力。

推文内容：
\"\"\"
{tweet_text}
\"\"\"
附带媒体数量：{media_count} 个图片/视频

评分标准（1-10 分）：
- 视觉吸引力（图片/视频质量潜力）
- 情感共鸣（是否能引发互动/收藏）
- 话题热度（是否契合小红书热门话题）
- 内容稀缺性（小红书上是否少见此类内容）

【输出格式】纯 JSON：
{{"score": 8, "reason": "简短理由"}}"""

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "你是一个输出纯 JSON 的 API 服务器。不要输出任何多余说明。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.5,
        "response_format": {"type": "json_object"},
    }

    session = requests.Session()
    session.trust_env = False

    try:
        response = session.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
        reply = result["choices"][0]["message"]["content"].strip()

        if reply.startswith("```"):
            reply = reply.strip("`").removeprefix("json").strip()

        data = json.loads(reply)
        score = int(data.get("score", 0))
        reason = data.get("reason", "")
        return score, reason

    except Exception as e:
        logger.warning(f"AI 评分失败: {e}")
        return 0, f"评分失败: {e}"


def generate_original_note(
    topic: str,
    inspirations: list[dict],
    style: str = "生活化、温暖、接地气",
) -> tuple[str, str]:
    """
    基于知识库灵感素材，生成完全原创的小红书笔记。

    Args:
        topic: 用户指定的主题（如"花生酱减脂早餐"）
        inspirations: 从知识库检索到的灵感素材 [{text, author, url, ...}, ...]
        style: 写作风格描述

    Returns:
        (title, content)
    """
    if not LLM_API_KEY:
        logger.error("未配置 LLM_API_KEY，无法生成原创内容")
        return "", ""

    # 构建灵感上下文
    context_parts = []
    for i, insp in enumerate(inspirations, 1):
        text = insp.get("text", "")[:300]  # 截断避免 prompt 过长
        likes = insp.get("favorite_count", 0)
        context_parts.append(f"灵感{i}（❤️{likes}）:\n{text}")

    context = "\n\n".join(context_parts)

    prompt = f"""你是一位专业的小红书生活博主，写作风格：{style}。
用户想发一篇主题为「{topic}」的笔记。

以下是从网络公开分享中检索到的 {len(inspirations)} 条相关灵感素材（仅供参考，严禁直接翻译或复制！）：
---
{context}
---

请基于以上灵感，创作一篇**完全原创**的小红书笔记：

铁律（违反任何一条即为失败）：
1. 🚫 必须100%原创，不得翻译、搬运、复制任何灵感素材的原文。你只是从中获取"灵感"和"思路"。
2. 必须以第一人称写作，把内容当成自己的真实经历/体验来分享。
3. 🚫 禁止出现"推文""Twitter""X平台""搬运""转载""翻译""国外博主"等暗示内容来源的词汇。
4. 🚫 禁止使用"姐妹们""家人们""宝子们""小仙女"等套话。
5. 标题：30字以内，有吸引力的爆款钩子。
6. 正文结构：痛点/场景引入 → 详细干货/过程 → 个人心得 → 互动引导。
7. 正文 300-800 字，分段清晰，适度 Emoji。
8. 结尾加 3-5 个 #话题标签。

【输出格式】纯 JSON，不要 markdown 代码块：
{{
    "title": "标题",
    "content": "正文（含话题标签）"
}}"""

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是一个输出纯 JSON 的 API 服务器。不要输出任何多余说明，不要使用 Markdown 代码块。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.9,  # 创意度更高
        "response_format": {"type": "json_object"},
    }

    logger.info(f"✍️ 正在生成原创笔记: 「{topic}」（基于 {len(inspirations)} 条灵感）...")

    session = requests.Session()
    session.trust_env = False

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.post(
                f"{LLM_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=90,  # 原创生成需要更长时间
            )
            response.raise_for_status()
            result = response.json()

            reply_text = result["choices"][0]["message"]["content"].strip()

            # 容错 markdown
            if reply_text.startswith("```json"):
                reply_text = reply_text[7:]
            if reply_text.startswith("```"):
                reply_text = reply_text[3:]
            if reply_text.endswith("```"):
                reply_text = reply_text[:-3]

            data = json.loads(reply_text.strip())
            title = data.get("title", "")[:30]
            content = data.get("content", "")

            logger.info(f"✅ 原创笔记生成完毕！标题: {title}")
            return title, content

        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                logger.warning(
                    f"原创生成第 {attempt} 次失败: {e}，{RETRY_DELAY}s 后重试..."
                )
                time.sleep(RETRY_DELAY)
            else:
                logger.error(
                    f"原创生成最终失败（共 {MAX_RETRIES} 次尝试）: {last_error}"
                )

    return "", ""


def generate_hybrid_note(
    topic: str,
    inspirations: list[dict] | None = None,
    style: str = "生活化、温暖、接地气",
) -> tuple[str, str]:
    """
    混合模式：Grok 实时搜索 + 本地知识库灵感 → 生成原创小红书笔记。

    流程:
      1. 调用 Grok API（with live_search 工具），实时搜索 X 上最新相关帖子
      2. 合并本地 KB 灵感（如果有）
      3. Grok 基于全部素材生成 100% 原创笔记

    Args:
        topic: 创作主题
        inspirations: 本地知识库检索的灵感素材（可为空，纯 Grok 模式）
        style: 写作风格

    Returns:
        (title, content)
    """
    from config import GROK_API_KEY, GROK_BASE_URL, GROK_MODEL

    if not GROK_API_KEY:
        logger.error("未配置 GROK_API_KEY，无法使用混合模式。请在 config.py 或环境变量中设置。")
        return "", ""

    # --- 构建本地灵感上下文 ---
    local_context = ""
    if inspirations:
        parts = []
        for i, insp in enumerate(inspirations, 1):
            text = insp.get("text", "")[:300]
            likes = insp.get("favorite_count", 0)
            parts.append(f"本地灵感{i}（❤️{likes}）:\n{text}")
        local_context = "\n\n".join(parts)

    # --- 构建 Prompt ---
    local_section = ""
    if local_context:
        local_section = f"""
以下是从本地灵感库中检索到的 {len(inspirations)} 条相关素材（仅供参考，严禁复制！）：
---
{local_context}
---
"""

    prompt = f"""你是顶级小红书生活博主，写作风格：{style}（温暖接地气、多emoji、实用干货、第一人称、300-800字）。

用户主题：{topic}
{local_section}
请你：
1. 先搜索 X/Twitter 上 6-8 条最新高质量相关帖子（要求：高赞、最近7天、英文/中文均可）
2. 结合搜索结果和上面的本地灵感（如有），创作一篇**100%原创**小红书笔记
3. 绝对不能直接复制/翻译任何素材原文，只从中获取灵感和思路

铁律：
- 🚫 禁止出现"推文""Twitter""X平台""搬运""转载""翻译""国外博主"
- 🚫 禁止"姐妹们""家人们""宝子们""小仙女"
- 必须第一人称，当成自己的真实经历分享
- 标题30字以内，有吸引力
- 正文300-800字，分段清晰，适度Emoji
- 结尾互动引导 + 3-5个 #话题标签

【输出格式】纯 JSON，不要 markdown 代码块：
{{"title": "标题", "content": "正文（含话题标签）"}}"""

    headers = {
        "Authorization": f"Bearer {GROK_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": GROK_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是专业小红书创作者助手，输出纯 JSON。"
                    "你可以使用搜索工具获取最新 X/Twitter 帖子作为灵感。"
                    "不要输出任何多余说明，不要使用 Markdown 代码块。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.9,
        "search_parameters": {
            "mode": "auto",
            "max_search_results": 8,
            "from_date": "",  # 让 Grok 自动决定
            "return_citations": True,
        },
    }

    logger.info(
        f"🔄 混合模式生成中: 「{topic}」"
        f"（Grok 实时搜索 + {len(inspirations) if inspirations else 0} 条本地灵感）..."
    )

    session = requests.Session()
    session.trust_env = False

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.post(
                f"{GROK_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,  # Grok 搜索+生成需要更长时间
            )
            response.raise_for_status()
            result = response.json()

            reply_text = result["choices"][0]["message"]["content"].strip()

            # 容错 markdown
            if reply_text.startswith("```json"):
                reply_text = reply_text[7:]
            if reply_text.startswith("```"):
                reply_text = reply_text[3:]
            if reply_text.endswith("```"):
                reply_text = reply_text[:-3]

            data = json.loads(reply_text.strip())
            title = data.get("title", "")[:30]
            content = data.get("content", "")

            logger.info(f"✅ 混合模式生成完毕！标题: {title}")
            return title, content

        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                logger.warning(
                    f"混合生成第 {attempt} 次失败: {e}，{RETRY_DELAY}s 后重试..."
                )
                time.sleep(RETRY_DELAY)
            else:
                logger.error(
                    f"混合生成最终失败（共 {MAX_RETRIES} 次尝试）: {last_error}"
                )

    return "", ""
