"""
测试 humanizer 集成效果
直接运行: python test_humanizer.py
"""
import sys
sys.path.insert(0, '.')

from src.ai.generator import generate_xhs_content

test_content = """AI一键排版公众号！自媒体编辑教程
自媒体人福音！手动调排版太累？试试AI工具，输入纯文本秒变精美文章，支持手机预览，一键复制粘贴公众号后台。免费无套路，效率翻倍

为什么选AI排版？
1. 节省时间：从1小时缩到1分钟，专注内容创作。
2. 美观专业：自动加标题、段落、图片占位，媲美设计师。
3. 兼容完美：HTML样式直复制公众号/Word，无乱码。

超简单3步上手
1. 打开工具，粘贴你的文章文本（随便写都行）。
2. 点击生成，实时预览手机效果，调字体/间距。
3. 一键复制，全带样式导入公众号发布！

实用Tips
新手别忘加关键词：prompt里写"公众号风格+分段+emoji"。
视频党：结合AI生成字幕，文章插视频超吸睛。
进阶：用多代理模式，自动优化标题/配图建议。

自媒体起飞，就差这一步！试完评论你的收获，快去薅羊毛，提升笔记颜值。"""

print("=" * 60)
print("测试 Humanizer 增强版生成")
print("=" * 60)
print("原始内容（已去除表情符号避免编码问题）")
print("=" * 60)
print("正在生成（启用 humanizer）...")
print("=" * 60)

try:
    title, content = generate_xhs_content(
        tweet_text=test_content,
        author_name="测试用户",
        media_count=3
    )

    print("\n生成成功！")
    print(f"\n标题: {title}")
    print(f"\n内容:\n{content}")

    # 简单统计
    print("\n" + "=" * 60)
    print("统计信息:")
    print(f"- 标题字数: {len(title)}")
    print(f"- 内容字数: {len(content)}")

except Exception as e:
    print(f"\n生成失败: {e}")
    import traceback
    traceback.print_exc()
