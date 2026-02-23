#!/usr/bin/env python3
"""
X-to-XHS 启动入口

用法:
    python run.py https://x.com/user/status/1234567890
    python run.py --file urls.txt
    python run.py --scrape-only https://x.com/user/status/123
    python run.py --discover              # 自动发现推文
    python run.py --auto                  # 全自动模式
    python run.py --create "花生酱早餐"    # 从本地知识库生成
    python run.py --hybrid "花生酱早餐"    # 混合模式（Grok实时搜索+本地KB，最强）
    python run.py                         # 交互模式
"""

from src.pipeline import main

if __name__ == "__main__":
    main()
