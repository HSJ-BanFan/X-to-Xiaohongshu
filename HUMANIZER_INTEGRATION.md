# Humanizer-zh 集成指南

## ✅ 已完成的工作

### 1. 新增文件
- `src/ai/humanizer_rules.py` - 24 种 AI 写作痕迹检测规则
- `examples/humanizer_usage.py` - 使用示例

### 2. 修改文件
- `src/ai/prompts.py` - 新增 `HUMANIZE_PROMPT_V2`（增强版人性化提示词）
- `src/ai/generator.py` - `generate_natural_xhs_note()` 函数已使用新的提示词

---

## 🚀 使用方法

### 方式一：使用现有自然写作流程（推荐）

```python
from src.ai.generator import generate_natural_xhs_note

title, content = generate_natural_xhs_note(
    original_text="你的原始素材",
    rag_examples="可选的知识库参考"
)
```

这个函数现在使用增强版的 humanizer-zh 规则进行三步处理：
1. 生成初稿
2. **使用 humanizer-zh 规则去 AI 味** ← 已增强
3. 自检优化

### 方式二：标准流程 + Humanizer

```python
from src.ai.generator import generate_xhs_content
from src.ai.prompts import HUMANIZE_PROMPT_V2

# 1. 先生成内容
title, content = generate_xhs_content(tweet_text, author_name, media_count)

# 2. 使用 HUMANIZE_PROMPT_V2 优化（调用 LLM）
```

### 方式三：本地快速检查（不调用 LLM）

```python
from src.ai.humanizer_rules import AI_PATTERNS

# 检查高频 AI 词
ai_words = AI_PATTERNS["ai_buzzwords"]["keywords"]
# 检查夸大词汇
promo_words = AI_PATTERNS["exaggerated_significance"]["keywords"]
```

---

## 📊 Humanizer-zh 核心功能

### 检测的 24 种 AI 痕迹

| 类别 | 检测内容 |
|------|---------|
| **内容模式** | 夸大象征意义、知名度过度强调、肤浅分析、宣传语言、模糊归因、公式化挑战部分 |
| **语言语法** | AI 高频词、系动词回避、否定式排比、三段式法则、同义词循环、虚假范围 |
| **风格问题** | 破折号过度、粗体过度、内联标题、表情符号过度 |
| **交流痕迹** | 聊天机器人语气、免责声明、填充短语、过度限定、通用积极结尾 |

### 改进示例

**原文（AI 味）：**
> 🚀 重磅！OpenAI掌门人奥特曼又放大招了，此外，这标志着AI行业的新格局...

**优化后（更自然）：**
> OpenAI最近又在融资了，这一轮据说要融百亿。消息传出来，投资圈又热闹起来了。

---

## 🔧 进阶配置

### 调整温度参数

在 `generator.py` 中修改：

```python
# 人性化步骤 - 温度可以调低一点，让输出更稳定
natural_json = llm_call(humanize_prompt, temperature=0.6)  # 原来是 0.7

# 反思步骤 - 温度低一些，更严格
final_json_str = llm_call(reflect_prompt, temperature=0.3)  # 原来是 0.5
```

### 添加质量评分

```python
from src.ai.humanizer_rules import QUALITY_RUBRIC

# 在生成后添加评分步骤
score_prompt = QUALITY_RUBRIC + "\n\n请对以下文本评分：" + content
```

---

## 📝 注意事项

1. **Token 消耗**：使用 humanizer 会增加一次 LLM 调用，注意控制成本
2. **响应时间**：三步流程会比单步慢，可以添加缓存
3. **效果验证**：建议对比使用前后的内容，观察是否真的更自然
4. **小红书适配**：humanizer-zh 会去除过多表情符号，如果需要保留小红书风格，可以在最后一步添加回去

---

## 🎯 下一步建议

1. **测试对比**：用同样的素材分别用新旧流程生成，对比效果
2. **批量处理**：如果效果好，可以批量处理历史内容
3. **自定义规则**：根据小红书平台特点，在 `humanizer_rules.py` 中添加特定规则
4. **监控质量**：记录生成内容的互动数据，验证人性化效果

---

## 📚 参考

- 原项目：https://github.com/op7418/humanizer-zh
- 维基百科 AI 写作特征：https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing
