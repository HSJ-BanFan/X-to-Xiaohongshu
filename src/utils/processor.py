"""
内容处理模块 (Content Processor)

负责推文抓取后的预处理工作，连接 Scraper 和 AI 发布。
主要职责：
1. 图片预处理（调整大小至小红书规格、防查重加噪点）
2. 文本翻译（Google Translate / DeepL 等）
"""

import logging
import os
import io

# 翻译依赖
try:
    from googletrans import Translator
except ImportError:
    Translator = None

try:
    import deepl
except ImportError:
    deepl = None

# 图像处理依赖
try:
    from PIL import Image, ImageEnhance, ImageFilter, ExifTags
    import numpy as np
except ImportError:
    Image = None

from config import TRANSLATION_API, DEEPL_API_TOKEN

logger = logging.getLogger(__name__)

# ==========================================
# 图片处理 (复用 utils.py 的逻辑或在此升级)
# 该函数取代原生 utils 工具以便集中处理管道逻辑
# ==========================================
def process_images_for_xhs(image_paths: list[str]) -> list[str]:
    """
    调整图片尺寸适应小红书 3:4 / 4:3 比例，并添加轻微噪点防查重。
    如果机器未安装 pillow，直接原样返回。
    """
    if not Image:
        logger.warning("未安装 Pillow，跳过图片预处理！(执行 pip install Pillow 修复)")
        return image_paths

    processed_paths = []
    
    for idx, path in enumerate(image_paths):
        if not os.path.exists(path):
            continue
            
        try:
            with Image.open(path) as img:
                # 修复手机翻转照片问题
                try:
                    for orientation in ExifTags.TAGS.keys():
                        if ExifTags.TAGS[orientation] == 'Orientation':
                            break
                    exif = dict(img._getexif().items())
                    if exif[orientation] == 3:
                        img = img.rotate(180, expand=True)
                    elif exif[orientation] == 6:
                        img = img.rotate(270, expand=True)
                    elif exif[orientation] == 8:
                        img = img.rotate(90, expand=True)
                except (AttributeError, KeyError, IndexError):
                    pass
                
                # 色彩转换为RGB
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                
                # 添加极其微小的随机噪点以更改文件内部 Hash，避开查重
                img_array = np.array(img)
                noise = np.random.randint(-2, 3, img_array.shape, dtype='int16')
                noisy_img_array = np.clip(img_array.astype('int16') + noise, 0, 255).astype('uint8')
                img = Image.fromarray(noisy_img_array)
                
                # 稍微锐化
                enhancer = ImageEnhance.Sharpness(img)
                img = enhancer.enhance(1.1)

                # 将原文件重命名并保存新处理的文件 (例如 _xhs 后缀)
                base, ext = os.path.splitext(path)
                new_path = f"{base}_xhs.jpg"
                img.save(new_path, "JPEG", quality=90)
                processed_paths.append(new_path)
                
        except Exception as e:
            logger.error(f"处理图片 {path} 失败: {e}")
            processed_paths.append(path) # 处理失败使用原图
            
    return processed_paths

# ==========================================
# 多语言翻译
# ==========================================
def translate_text(text: str, source_lang: str = "EN", target_lang: str = "ZH") -> str:
    """
    翻译文本。支持 Google Translate（免费）和 DeepL（需提供 API Key）。
    """
    if not text.strip():
        return text

    if TRANSLATION_API == "deepl" and DEEPL_API_TOKEN and deepl:
        try:
            translator = deepl.Translator(DEEPL_API_TOKEN)
            result = translator.translate_text(
                text,
                source_lang=source_lang,
                target_lang="ZH-HANS" if target_lang == "ZH" else target_lang,
            )
            return result.text
        except Exception as e:
            logger.warning(f"DeepL 翻译失败: {e}，回退到 Google Translate")
            
    if Translator:
        try:
            translator = Translator()
            result = translator.translate(text, src="en", dest="zh-cn")
            return result.text
        except Exception as e:
            logger.warning(f"Google 翻译也失败了: {e}")
            return text
            
    logger.warning("未安装翻译依赖 `googletrans==4.0.0-rc1` 或 `deepl`。返回原文。")
    return text
