"""
工具函数：URL 解析、图片处理、文件下载
"""

import os
import re
import urllib3

import requests
from PIL import Image, ImageFilter
import random

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def parse_tweet_id(url: str) -> str:
    """
    从各种格式的 X/Twitter URL 中提取 Tweet ID。

    支持的格式:
    - https://x.com/user/status/1234567890
    - https://twitter.com/user/status/1234567890
    - https://x.com/user/status/1234567890?s=20
    - https://mobile.twitter.com/user/status/1234567890
    - https://vxtwitter.com/user/status/1234567890
    - https://fxtwitter.com/user/status/1234567890
    """
    pattern = r'(?:x\.com|twitter\.com|mobile\.twitter\.com|vxtwitter\.com|fxtwitter\.com)/\w+/status/(\d+)'
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    raise ValueError(f"无法从 URL 中提取 Tweet ID: {url}")


def resize_for_xhs(image_path: str, output_path: str = None, target_ratio: float = 3 / 4) -> str:
    """
    将图片调整为小红书最佳比例 (3:4, 1080×1440)。

    策略：在不裁剪内容的前提下，通过添加模糊背景填充来达到目标比例。
    """
    if output_path is None:
        output_path = image_path

    img = Image.open(image_path)
    width, height = img.size
    current_ratio = width / height

    # 目标尺寸
    target_width = 1080
    target_height = 1440

    if abs(current_ratio - target_ratio) < 0.05:
        # 比例接近，直接 resize
        img = img.resize((target_width, target_height), Image.LANCZOS)
    elif current_ratio > target_ratio:
        # 图片太宽（横图），上下添加模糊背景
        new_width = target_width
        new_height = int(new_width / current_ratio)
        img_resized = img.resize((new_width, new_height), Image.LANCZOS)

        # 创建模糊背景
        bg = img.resize((target_width, target_height), Image.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=30))

        # 居中放置
        y_offset = (target_height - new_height) // 2
        bg.paste(img_resized, (0, y_offset))
        img = bg
    else:
        # 图片太高（竖图），左右添加模糊背景
        new_height = target_height
        new_width = int(new_height * current_ratio)
        img_resized = img.resize((new_width, new_height), Image.LANCZOS)

        bg = img.resize((target_width, target_height), Image.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=30))

        x_offset = (target_width - new_width) // 2
        bg.paste(img_resized, (x_offset, 0))
        img = bg

    img.save(output_path, "JPEG", quality=95)
    return output_path


def add_noise(image_path: str, output_path: str = None, intensity: int = 3) -> str:
    """
    向图片添加极微小的随机噪声，使 MD5 不同于原图。
    不影响肉眼观感。
    """
    if output_path is None:
        output_path = image_path

    img = Image.open(image_path).convert("RGB")
    pixels = img.load()
    width, height = img.size

    # 随机修改少量像素点
    num_pixels = max(10, (width * height) // 500)
    for _ in range(num_pixels):
        x = random.randint(0, width - 1)
        y = random.randint(0, height - 1)
        r, g, b = pixels[x, y]
        r = max(0, min(255, r + random.randint(-intensity, intensity)))
        g = max(0, min(255, g + random.randint(-intensity, intensity)))
        b = max(0, min(255, b + random.randint(-intensity, intensity)))
        pixels[x, y] = (r, g, b)

    img.save(output_path, "JPEG", quality=95)
    return output_path


def download_file(url: str, save_path: str, headers: dict = None) -> str:
    """下载文件到本地。"""
    _headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    if headers:
        _headers.update(headers)

    session = requests.Session()
    session.trust_env = False

    response = session.get(
        url,
        headers=_headers,
        stream=True,
        timeout=60,
        verify=False,
    )
    response.raise_for_status()

    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    with open(save_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    return save_path


def process_images_for_xhs(image_paths: list[str]) -> list[str]:
    """
    批量处理图片：resize + 加噪声。
    处理后的图片保存到原目录下的 _processed 子目录，不覆盖原图。
    返回处理后的图片路径列表。
    """
    if not image_paths:
        return []

    first_dir = os.path.dirname(image_paths[0])
    processed_dir = os.path.join(first_dir, "_processed")
    os.makedirs(processed_dir, exist_ok=True)

    processed = []
    for path in image_paths:
        basename = os.path.basename(path)
        out_path = os.path.join(processed_dir, basename)
        resize_for_xhs(path, out_path)
        add_noise(out_path)
        processed.append(out_path)
    return processed
