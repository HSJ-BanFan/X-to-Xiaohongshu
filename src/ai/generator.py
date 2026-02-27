import json
import logging
import re
import time
import requests
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


def classify_content(tweet_text: str, media_count: int) -> str:
    """
    判断内容类型以选择对应的小红书模版。
    """
    if not LLM_API_KEY:
        return "DEFAULT"

    from src.ai.prompts import get_classification_prompt
    prompt = get_classification_prompt(tweet_text, media_count)

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "You are a JSON-only content classifier."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"}
    }

    session = requests.Session()
    session.trust_env = False
    try:
        resp = session.post(f"{LLM_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=20)
        resp.raise_for_status()
        
        reply_text = resp.json()["choices"][0]["message"]["content"].strip()
        data = json.loads(reply_text)
        category = data.get("category", "DEFAULT").upper()
        
        # 兼容性检查
        valid_categories = ["TUTORIAL", "REVIEW", "LIFESTYLE", "NEWS", "DEFAULT"]
        if category not in valid_categories:
            category = "DEFAULT"
            
        logger.info(f"🧠 内容类型识别为: {category}")
        return category
    except Exception as e:
        logger.warning(f"内容分类失败: {e}，回退到 DEFAULT 模板")
        return "DEFAULT"


def generate_xhs_content(tweet_text: str, author_name: str, media_count: int = 0) -> tuple[str, str]:
    """
    使用 LLM 根据推文原文生成小红书风格的标题和正文。
    返回: (title, content)
    """
    if not LLM_API_KEY:
        logger.warning("未配置 LLM_API_KEY，跳过 AI 生成，返回原文。")
        return "", tweet_text

    logger.info(f"正在调用 {LLM_MODEL} 生成小红书文案...")

    # 先做内容分类
    content_type = classify_content(tweet_text, media_count)
    
    # 获取具体的生成 Prompt
    from src.ai.prompts import get_generation_prompt, get_json_structure_instruction
    base_prompt = get_generation_prompt(content_type, tweet_text)
    json_instruction = get_json_structure_instruction()
    full_prompt = base_prompt + "\n\n" + json_instruction

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "你是一个输出纯 JSON 的 API 服务器。不要输出任何多余说明，不要加Markdown。"},
            {"role": "user", "content": full_prompt}
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

    # --- 内容分类与加载模板 ---
    content_type = classify_content(topic, 0)
    from src.ai.prompts import get_generation_prompt, get_json_structure_instruction
    
    base_prompt = get_generation_prompt(content_type, "（无基础素材，请参考下方灵感重写）")
    json_instruction = get_json_structure_instruction()

    prompt = f"""小红书原创模式写作指令：

目前用户给定写作主题: 「{topic}」
所选输出排版风格: {content_type}
要求的特定写作基调: {style}

以下是从公开网络分享中检索到的 {len(inspirations)} 条相关灵感素材（仅供参考，严禁直接翻译或复制！）：
---
{context}
---

请严格基于以上灵感和主题要求，创作一篇**完全原创**的小红书笔记。

【排版与核心禁忌要求】（来自系统配置）：
{base_prompt}
（注意：必须遵循 {style} 的语气。）

{json_instruction}
"""

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
            title = data.get("title", "")[:20]
            content = data.get("content", "")
            # 排版清理
            content = content.replace('\\n', '\n')
            content = re.sub(r'\n{3,}', '\n\n', content).strip()
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
    local_section = ""
    if inspirations:
        parts = []
        for i, insp in enumerate(inspirations, 1):
            t = insp.get("text", "")[:300]
            likes = insp.get("favorite_count", 0)
            parts.append(f"本地灵感{i}（❤️{likes}）:\n{t}")
        local_context = "\n\n".join(parts)
        local_section = f"""
以下是由本地知识库检索到的 {len(inspirations)} 条相关素材（仅供参考，严禁直接复制或翻译）：
---
{local_context}
---
"""

    # --- 内容分类与加载模板 ---
    content_type = classify_content(topic, 0)
    from src.ai.prompts import get_generation_prompt, get_json_structure_instruction
    
    # 获取特定排版基底
    base_prompt = get_generation_prompt(content_type, "（无基础素材，请你实时搜索补充）")
    json_instruction = get_json_structure_instruction()

    # --- 构建最终 Prompt ---
    full_prompt = f"""小红书混合模式写作指令：

目前用户给定写作主题: 「{topic}」
所选输出排版风格: {content_type}

{local_section}

【操作步骤】：
1. 请先根据主题「{topic}」搜索 X/Twitter 上的 6-8 条最新高质量相关帖子（要求：高赞、时间近、英文/中文均可）。
2. 然后结合所搜索出的素材，以及可能的以上本地素材，严格按照下方的【排版与禁忌要求】，创作一篇**完全原创**的小红书图文笔记。

【排版与禁忌要求】（来自系统配置）：
{base_prompt}

{json_instruction}
"""

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
                    "你是一个输出纯 JSON 的高级内容生成与搜索代理。"
                    "请使用搜索工具获取最新 X/Twitter 帖子作为灵感，然后严格按照用户要求的 JSON 格式输出结果。"
                ),
            },
            {"role": "user", "content": full_prompt},
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
            title = data.get("title", "")[:20]
            content = data.get("content", "")
            # 排版清理
            content = content.replace('\\n', '\n')
            content = re.sub(r'\n{3,}', '\n\n', content).strip()
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

def generate_natural_xhs_note(original_text: str, rag_examples: str = "") -> tuple[str, str]:
    """
    低网感真实感写作方法（Two-Stage Humanize + Self Reflection）
    
    Args:
        original_text: 原文素材内容
        rag_examples: 检索到的相关知识库参考资料等
    
    Returns:
        (title, content)
    """
    if not LLM_API_KEY:
        logger.warning("未配置 LLM_API_KEY，跳过 AI 生成，返回原文。")
        return "", original_text

    logger.info(f"正在调用 {LLM_MODEL} 生成【低网感/自然版】小红书文案...")

    from src.ai.prompts import PERSONA, STYLE_CONSTRAINT, FEW_SHOT_EXAMPLES, HUMANIZE_PROMPT, REFLECT_PROMPT, get_json_structure_instruction

    # 1. 第一步：生成初稿 (draft)
    json_instruction = get_json_structure_instruction()
    full_prompt = f"{PERSONA}\n\n{STYLE_CONSTRAINT}\n\n参考样本：\n{FEW_SHOT_EXAMPLES}\n\n素材：\n{original_text}\n{rag_examples}\n\n{json_instruction}"
    
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    
    session = requests.Session()
    session.trust_env = False
    
    def llm_call(prompt_text, temperature=0.7):
        payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": "你是一个输出纯 JSON 的 API 服务器。不要输出任何多余说明，不要加Markdown。"},
                {"role": "user", "content": prompt_text}
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"}
        }
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = session.post(f"{LLM_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=60)
                resp.raise_for_status()
                reply = resp.json()["choices"][0]["message"]["content"].strip()
                if reply.startswith("```json"): reply = reply[7:]
                if reply.startswith("```"): reply = reply[3:]
                if reply.endswith("```"): reply = reply[:-3]
                return reply.strip()
            except Exception as e:
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                else:
                    logger.error(f"LLM调用失败: {e}")
                    return "{}"
        return "{}"

    # 第一步: 生成初稿
    logger.info("  -> [1/3] 生成初稿中...")
    draft_json = llm_call(full_prompt, temperature=0.7)
    
    # 第二步：去AI味
    logger.info("  -> [2/3] 进行去AI味改写...")
    humanize_prompt = HUMANIZE_PROMPT.format(draft=draft_json) + f"\n\n{json_instruction}"
    natural_json = llm_call(humanize_prompt, temperature=0.7)
    
    # 第三步：自检
    logger.info("  -> [3/3] 终稿自检自纠...")
    reflect_prompt = REFLECT_PROMPT.format(text=natural_json) + f"\n\n{json_instruction}"
    final_json_str = llm_call(reflect_prompt, temperature=0.5)

    try:
        import re
        data = json.loads(final_json_str)
        title = data.get("title", "")[:20]
        content = data.get("content", "")
        # 排版清理
        content = content.replace('\\n', '\n')
        content = re.sub(r'\n{3,}', '\n\n', content).strip()
        logger.info(f"✅ 【低网感/自然版】生成完毕！标题: {title}")
        return title, content
    except Exception as e:
        logger.error(f"解析最终 JSON 失败: {e}")
        return "", original_text
