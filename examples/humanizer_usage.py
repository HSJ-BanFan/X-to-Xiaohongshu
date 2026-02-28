"""
Humanizer-zh 集成使用示例

本文件展示如何在项目中使用增强的 humanizer 功能
"""

# ==========================================
# 方式 1: 使用增强版自然写作流程（推荐）
# ==========================================

from src.ai.generator import generate_natural_xhs_note

# 示例：生成一篇低网感的小红书笔记
title, content = generate_natural_xhs_note(
    original_text="""OpenAI最近又在融资了，据说这一轮要融百亿美金，目标是搞出AGI。
    消息一出，投资圈又热闹起来了。今年前几个月，AI领域的融资总额已经超过千亿。""",
    rag_examples=""
)

print(f"标题: {title}")
print(f"内容:\n{content}")


# ==========================================
# 方式 2: 在标准流程后添加 humanizer 步骤
# ==========================================

from src.ai.generator import generate_xhs_content
from src.ai.prompts import HUMANIZE_PROMPT_V2, get_json_structure_instruction
import requests
import json

# 先生成标准内容
title, content = generate_xhs_content(
    tweet_text="你的原始推文内容",
    author_name="作者名",
    media_count=3
)

# 然后用 humanizer-zh 规则优化
def humanize_with_llm(title: str, content: str) -> tuple[str, str]:
    """使用增强版 humanizer 规则优化内容"""

    draft = json.dumps({"title": title, "content": content}, ensure_ascii=False)
    prompt = HUMANIZE_PROMPT_V2.format(draft=draft)

    # 调用你的 LLM API
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "你是一个输出纯 JSON 的 API 服务器。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "response_format": {"type": "json_object"}
    }

    response = requests.post(f"{LLM_BASE_URL}/chat/completions",
                           headers=headers, json=payload)
    result = response.json()
    reply = result["choices"][0]["message"]["content"]

    # 解析结果
    data = json.loads(reply)
    return data.get("title", title), data.get("content", content)


# ==========================================
# 方式 3: 批量处理已生成的内容
# ==========================================

from src.ai.humanizer_rules import AI_PATTERNS, QUICK_CHECKLIST

def quick_ai_check(text: str) -> list[str]:
    """
    快速检查文本中的 AI 痕迹（本地规则检测，不调用 LLM）
    返回发现的问题列表
    """
    issues = []

    # 检查高频 AI 词汇
    ai_words = AI_PATTERNS["ai_buzzwords"]["keywords"]
    found_words = [w for w in ai_words if w in text]
    if found_words:
        issues.append(f"发现 AI 高频词: {', '.join(found_words)}")

    # 检查三段式
    import re
    if re.search(r"\w+、\w+和\w+[，。]", text):
        issues.append("可能存在强行三项并列（三段式法则）")

    # 检查表情符号过度使用
    emojis = AI_PATTERNS["emoji_overuse"]["keywords"]
    emoji_count = sum(text.count(e) for e in emojis)
    if emoji_count > 3:
        issues.append(f"表情符号过多（{emoji_count}个），建议保留1-2个")

    # 检查夸大词汇
    promo_words = AI_PATTERNS["exaggerated_significance"]["keywords"]
    found_promo = [w for w in promo_words if w in text]
    if found_promo:
        issues.append(f"发现夸大/宣传性词汇: {', '.join(found_promo)}")

    return issues


# 使用示例
text = """🚀 重磅！OpenAI掌门人奥特曼又放大招了！此外，这标志着AI行业的新格局..."""
issues = quick_ai_check(text)
print("检测到的问题:")
for issue in issues:
    print(f"  - {issue}")


# ==========================================
# 方式 4: 质量评分
# ==========================================

from src.ai.humanizer_rules import QUALITY_RUBRIC

def evaluate_quality(text: str) -> dict:
    """
    返回质量评分提示词，可以发给 LLM 进行评估
    """
    prompt = f"""
{QUALITY_RUBRIC}

请对以下文本进行质量评分：

{text}

输出格式：
{{
    "directness": 8,
    "rhythm": 7,
    "trust": 9,
    "authenticity": 8,
    "conciseness": 7,
    "total": 39,
    "suggestions": "改进建议..."
}}
"""
    return prompt


# ==========================================
# 配置建议
# ==========================================

"""
1. 在 config.py 中添加配置：

# Humanizer 设置
HUMANIZER_ENABLED = True  # 是否启用增强版人性化
HUMANIZER_TEMPERATURE = 0.7  # 人性化步骤的温度
HUMANIZER_MAX_TOKENS = 2000  # 最大输出长度

2. 在 pipeline 中集成：

修改 src/core/pipeline.py，在内容生成后添加 humanizer 步骤：

if config.HUMANIZER_ENABLED:
    from src.ai.generator import humanize_with_llm
    title, content = humanize_with_llm(title, content)

3. 日志记录：

建议记录每次 humanizer 的输入输出，用于质量分析：

logger.info(f"Humanizer 输入: {original_content[:100]}...")
logger.info(f"Humanizer 输出: {humanized_content[:100]}...")
"""
