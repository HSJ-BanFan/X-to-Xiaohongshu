import json
import logging
import time
import requests

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 5  # 秒


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
