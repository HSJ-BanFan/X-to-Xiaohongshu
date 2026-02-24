"""
小红书发布模块 (Playwright 版)

使用 playwright 操控 creator.xiaohongshu.com 发布笔记，
彻底解决非 BMP 字符 (Emoji) 导致 ChromeDriver 崩溃的问题，并且完美适配小红书的富文本排版。
"""

import json
import os
import re
from playwright.sync_api import sync_playwright

from config import XHS_COOKIES_FILE


class XiaohongshuPoster:
    """小红书创作者平台自动发布"""

    CREATOR_URL = "https://creator.xiaohongshu.com"
    LOGIN_URL = "https://creator.xiaohongshu.com/login"
    PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish"

    def __init__(self, user_data_dir: str = "", profile: str = "Default"):
        """
        初始化浏览器实例。

        Args:
            user_data_dir: Chrome 用户数据目录路径。
            profile: Profile 文件名（暂时在使用 playwright 时不直接用独立 profile 参数，而是随文件夹）。
        """
        self.cookies_file = XHS_COOKIES_FILE
        self._playwright = sync_playwright().start()

        args = [
            "--disable-blink-features=AutomationControlled",
            "--proxy-bypass-list=127.0.0.1,localhost,::1"
        ]

        print("[小红书] 正在启动 Playwright 浏览器...")
        
        # 为了更好地防封我们优先尝试调用系统 Chrome，退而可用自带 Chromium
        try:
            if user_data_dir and os.path.exists(user_data_dir):
                print(f"[小红书] 使用 Chrome 用户数据目录: {user_data_dir}")
                self.context = self._playwright.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    channel="chrome",
                    headless=False,
                    args=args,
                    color_scheme="light",
                    viewport={"width": 1280, "height": 800}
                )
            else:
                self.browser = self._playwright.chromium.launch(
                    channel="chrome",
                    headless=False,
                    args=args
                )
                self.context = self.browser.new_context(viewport={"width": 1280, "height": 800})
        except Exception as e:
            print(f"[小红书] 启动系统 Chrome 失败，回退到默认 Chromium: {e}")
            if user_data_dir and os.path.exists(user_data_dir):
                self.context = self._playwright.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=False,
                    args=args,
                    color_scheme="light",
                    viewport={"width": 1280, "height": 800}
                )
            else:
                self.browser = self._playwright.chromium.launch(
                    headless=False, 
                    args=args
                )
                self.context = self.browser.new_context(viewport={"width": 1280, "height": 800})

        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        # 绕过部分检测
        self.page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self._logged_in = False

    def _load_cookies(self) -> bool:
        """加载保存的 cookies"""
        if not os.path.exists(self.cookies_file):
            return False

        try:
            with open(self.cookies_file, "r", encoding="utf-8") as f:
                cookies = json.load(f)

            valid_cookies = []
            for c in cookies:
                cookie = {
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c["domain"],
                    "path": c.get("path", "/"),
                }
                valid_cookies.append(cookie)

            self.context.add_cookies(valid_cookies)
            return True
        except Exception as e:
            print(f"[小红书] 加载 cookies 失败: {e}")
            return False

    def _save_cookies(self):
        """保存当前 cookies"""
        try:
            cookies_dir = os.path.dirname(self.cookies_file)
            if cookies_dir:
                os.makedirs(cookies_dir, exist_ok=True)

            cookies = self.context.cookies()
            with open(self.cookies_file, "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            print("[小红书] Cookies 已保存")
        except Exception as e:
            print(f"[小红书] 保存 cookies 失败: {e}")

    def _is_logged_in(self) -> bool:
        """检查是否已登录"""
        return "login" not in self.page.url

    def login(self):
        """
        登录小红书创作者平台。
        优先使用保存的 cookies，失败则等待手动扫码登录。
        """
        if self._logged_in:
            return

        print("[小红书] 尝试登录...")

        # 尝试 cookies 登录
        if self._load_cookies():
            self.page.goto(self.CREATOR_URL)
            self.page.wait_for_timeout(3000)
            if self._is_logged_in():
                print("[小红书] ✓ Cookies 登录成功")
                self._save_cookies()
                self._logged_in = True
                return
            else:
                print("[小红书] Cookies 已失效，清理...")
                self.context.clear_cookies()

        # 手动扫码登录
        self.page.goto(self.LOGIN_URL)
        self.page.wait_for_timeout(2000)

        print("[小红书] ⚠ 请在浏览器中扫码登录！")
        print("[小红书] 等待登录完成...")

        # 每 3 秒检查一次是否已登录，最多等待 120 秒
        for _ in range(40):
            self.page.wait_for_timeout(3000)
            if self._is_logged_in():
                print("[小红书] ✓ 扫码登录成功")
                self._save_cookies()
                self._logged_in = True
                return

        raise TimeoutError("[小红书] 登录超时，请在 120 秒内完成扫码")

    def post_note(
        self,
        title: str,
        content: str,
        images: list[str] = None,
        video: str = None,
        use_long_article: bool = False,
        wait_before_publish: int = 30,
    ):
        """
        发布笔记到小红书。
        """
        if not self._logged_in:
            self.login()

        print("[小红书] 开始发布笔记...")
        self.page.goto(self.PUBLISH_URL)
        self.page.wait_for_timeout(3000)

        # === 切换对应 Tab 并上传媒体/处理长文 ===
        if use_long_article:
            self._process_long_article(title, content)
        elif video:
            print("[小红书] 切换到 视频 发布模式...")
            try:
                self.page.locator("text='上传视频'").first.click()
            except:
                try:
                    self.page.locator("text='发布视频'").first.click()
                except:
                    pass
            self.page.wait_for_timeout(1000)
            self._upload_video(video)
        elif images:
            print("[小红书] 切换到 图文 发布模式...")
            try:
                # 首先尝试精准匹配，然后更宽泛匹配
                tab = self.page.locator("text='图文'").first
                if not tab.is_visible(timeout=3000):
                    tab = self.page.locator(".tab-item:has-text('图文')").first
                if tab.is_visible():
                    tab.click()
                elif use_long_article == False:
                     print("[小红书] 警告: 未找到独立的图文Tab，假设当前已在图文发布页")
                self.page.wait_for_timeout(2000)
            except Exception as e:
                print(f"[小红书] 切换图文 Tab 失败: {e}")
            self._upload_images(images)
        else:
            raise ValueError("必须提供图片或视频，或者启用使用长文模式")

        self.page.wait_for_timeout(3000)

        # === 填写标题 ===
        try:
            self._fill_title(title)
        except Exception as e:
            print(f"[小红书] 填写标题时发生问题: {e}")

        # === 填写正文 ===
        try:
            # 去除标题，只保留正文内容。因为对于长文，通常标题会显示在生成的图片上，正文仅用于描述。
            # 为了保证描述里有 hashtag 等信息，直接传 content（包含正文和标签）。
            self._fill_content(content)
        except Exception as e:
            print(f"[小红书] 填写正文时发生问题: {e}")

        self.page.wait_for_timeout(2000)

        # === 自动选取小红书推荐标签 ===
        self._select_suggested_tags(max_tags=5)

        # === 等待用户审核 ===
        if wait_before_publish > 0:
            print(f"[小红书] 内容已填充，等待 {wait_before_publish} 秒用于审核...")
            print(f"[小红书] 如需取消发布，请在 {wait_before_publish} 秒内手动关闭浏览器")
            self.page.wait_for_timeout(wait_before_publish * 1000)

        # === 点击发布 ===
        self._click_publish()
        print("[小红书] ✓ 笔记发布完成！")
        self.page.wait_for_timeout(5000)

    def _upload_images(self, image_paths: list[str]):
        """上传图片"""
        print(f"[小红书] 上传 {len(image_paths)} 张图片...")
        abs_paths = [os.path.abspath(p) for p in image_paths]
        try:
            file_input = self.page.locator("input[type='file']").first
            # 强制多选
            file_input.evaluate("el => el.setAttribute('multiple', 'multiple')")
            file_input.set_input_files(abs_paths)
            print("[小红书] 图片已上传，等待处理...")
            self.page.wait_for_timeout(5000)
        except Exception as e:
            print(f"[小红书] 图片上传失败: {e}")
            raise RuntimeError(f"图片上传失败: {e}")

    def _upload_video(self, video_path: str):
        """上传视频"""
        print(f"[小红书] 上传视频: {video_path}")
        abs_path = os.path.abspath(video_path)
        try:
            file_input = self.page.locator("input[type='file']").first
            file_input.set_input_files(abs_path)
            print("[小红书] 视频已上传，等待处理（可能需要较长时间）...")
            self.page.wait_for_timeout(15000)
        except Exception as e:
            print(f"[小红书] 视频上传失败: {e}")
            raise RuntimeError(f"视频上传失败: {e}")

    def _process_long_article(self, title: str, content: str):
        """处理写长文的四个阶段：创建、编辑、排版、下一步"""
        print("[小红书] 切换到 写长文 发布模式...")
        try:
            self.page.locator("text='写长文'").first.click()
            self.page.wait_for_timeout(2000)
            # 点击新的创作
            new_btn = self.page.locator("text='新的创作'")
            if new_btn.is_visible():
                new_btn.first.click()
                self.page.wait_for_timeout(2000)
        except Exception as e:
            print(f"[小红书] 切换写长文模式失败: {e}")
            raise RuntimeError(f"切换写长文模式失败: {e}")

        # 填写长文编辑器
        print("[小红书] 填写长文内容...")
        try:
            # 1. 独立填写标题
            title_input = self.page.locator("[placeholder*='标题']").first
            if title_input.is_visible():
                title_input.fill(title)
                
            # 2. 填写正文
            editor = self.page.locator(".ProseMirror, [data-placeholder='粘贴到这里或输入文字']").first
            editor.click()
            self.page.keyboard.press("Control+A")
            self.page.keyboard.press("Backspace")
            self.page.keyboard.insert_text(content)
            self.page.wait_for_timeout(1000)
        except Exception as e:
            print(f"[小红书] 填写长文编辑器失败: {e}")
            raise RuntimeError(f"填写长文编辑器失败: {e}")

        # 点击一键排版
        print("[小红书] 正在一键排版...")
        try:
            btn = self.page.get_by_text("一键排版").last
            if btn.is_visible():
                btn.click()
            else:
                self.page.evaluate("""
                    const els = Array.from(document.querySelectorAll('*'));
                    const target = els.find(el => el.textContent && el.textContent.includes('一键排版'));
                    if (target) target.click();
                """)
            self.page.wait_for_timeout(8000) # 等待排版页面加载和渲染
        except Exception as e:
            print(f"[小红书] 点击一键排版失败: {e}")
            raise RuntimeError(f"点击一键排版失败: {e}")

        # 点击下一步
        print("[小红书] 排版完成，进入下一步（回到标准发布页）...")
        try:
            next_btn = self.page.get_by_text("下一步").last
            if next_btn.is_visible():
                next_btn.click()
            else:
                self.page.evaluate("""
                    const els = Array.from(document.querySelectorAll('*'));
                    const target = els.find(el => el.textContent && el.textContent.trim() === '下一步');
                    if (target) target.click();
                """)
            # 下一步后可能比较慢加载标准发布界面
            self.page.wait_for_timeout(5000)
        except Exception as e:
            print(f"[小红书] 点击下一步失败: {e}")
            raise RuntimeError(f"点击下一步失败: {e}")


    def _fill_title(self, title: str):
        """填写标题"""
        title = title[:20]
        print(f"[小红书] 填写标题: {title}")
        try:
            # 兼容新版 UI：带有 .d-input 父级和 placeholder 的 input.d-text
            selectors = [
                ".d-input input.d-text",
                "input[placeholder*='标题']",
                "input.d-text",
                ".title-input input",
                "input[type='text'][maxlength='20']"
            ]
            title_input = None
            for sel in selectors:
                try:
                    loc = self.page.locator(sel).first
                    if loc.is_visible(timeout=2000):
                        title_input = loc
                        break
                except Exception:
                    continue

            if title_input:
                title_input.fill(title)
            else:
                print("[小红书] 警告: 未发现标准标题输入框可见，尝试使用 JS 强制输入...")
                self.page.evaluate("""(t) => {
                    const inputs = Array.from(document.querySelectorAll('input[type="text"], input'));
                    const titleInput = inputs.find(i => 
                        (i.placeholder && i.placeholder.includes('标题')) || 
                        i.maxLength === 20 ||
                        i.className.includes('title')
                    );
                    if (titleInput) {
                        titleInput.value = t;
                        titleInput.dispatchEvent(new Event('input', {bubbles: true}));
                    }
                }""", title)
        except Exception as e:
            print(f"[小红书] 标题填写失败: {e}")
            raise RuntimeError(f"标题填写失败，找不到标题输入框: {e}")

    def _fill_content(self, content: str):
        """填写正文描述，提取标签并处理Emoji"""
        print(f"[小红书] 填写正文描述 ({len(content)} 字)...")
        try:
            # 提取 hashtag
            pattern = r'#([^\s#，。！？,。!?"\'\[\]]+)(?:\[话题\]#?)?'
            matches = list(re.finditer(pattern, content))
            
            main_content = content
            hashtags_to_type = []
            for m in matches:
                full_match = m.group(0)
                tag_name = m.group(1)
                main_content = main_content.replace(full_match, '')
                if tag_name not in hashtags_to_type:
                    hashtags_to_type.append(tag_name)
            
            main_content = main_content.strip()

            # 兼容新版 UI：嵌套的富文本编辑器 .editor-content .tiptap.ProseMirror
            selectors = [
                ".editor-content .ProseMirror",
                ".ql-editor",
                "#post-content .ql-editor",
                "[contenteditable='true']"
            ]
            editor = None
            for sel in selectors:
                try:
                    loc = self.page.locator(sel).first
                    if loc.is_visible(timeout=2000):
                        editor = loc
                        break
                except Exception:
                    continue

            if editor:
                # 聚焦并清空
                editor.click()
                self.page.keyboard.press("Control+A")
                self.page.keyboard.press("Backspace")
                
                # 使用 Playwright 的 insert_text (安全且完美兼容各种 Emoji 和富文本排版)
                self.page.keyboard.insert_text(main_content)
                self.page.wait_for_timeout(1000)
            else:
                print("[小红书] 警告: 未发现标准正文输入框可见，尝试使用 JS 强制聚焦输入...")
                self.page.evaluate("""() => {
                    const eds = document.querySelectorAll('[contenteditable="true"], .ProseMirror, .ql-editor');
                    if (eds.length > 0) {
                        eds[0].focus();
                        eds[0].innerHTML = "";
                    }
                }""")
                self.page.keyboard.insert_text(main_content)
                self.page.wait_for_timeout(1000)

            # 输入话题
            if hashtags_to_type:
                self.page.keyboard.press("Enter")
                self.page.keyboard.press("Enter")
                for tag in hashtags_to_type:
                    # 键入 # 和标签名字
                    self.page.keyboard.insert_text(f"#{tag}")
                    self.page.wait_for_timeout(1500)  # 等待小红书的联想弹窗加载
                    self.page.keyboard.press("Enter")
                    self.page.wait_for_timeout(500)
                    self.page.keyboard.insert_text(" ")

        except Exception as e:
            print(f"[小红书] 正文填写失败: {e}")
            raise RuntimeError(f"正文填写失败，找不到正文输入框: {e}")

    def _click_publish(self):
        """点击发布按钮"""
        print("[小红书] 点击发布...")
        try:
            # 尝试几种常见的发布按钮定位
            selectors = [
                "button:has-text('发布')", 
                ".publishBtn", 
                "button[class*='publish']",
                ".submit",
                "//button[contains(text(), '发布')]"
            ]
            
            clicked = False
            for sel in selectors:
                try:
                    btn = self.page.locator(sel).first
                    if btn.is_visible(timeout=1000):
                        btn.click()
                        clicked = True
                        break
                except Exception:
                    continue
                    
            if not clicked:
                # 兜底：用 evaluate 强行查找并点击
                clicked = self.page.evaluate("""() => {
                    const btns = Array.from(document.querySelectorAll('button, .d-button'));
                    const publishBtn = btns.find(b => b.textContent && b.textContent.includes('发布'));
                    if (publishBtn) {
                        publishBtn.click();
                        return true;
                    }
                    return false;
                }""")
            
            if not clicked:
                raise RuntimeError("未找到包含'发布'字样的按钮")
                
        except Exception as e:
            print(f"[小红书] 点击发布按钮失败: {e}")
            raise RuntimeError(f"点击发布按钮失败: {e}")

    def _select_suggested_tags(self, max_tags: int = 5):
        """自动点选推荐标签"""
        print(f"[小红书] 尝试选取推荐标签（最多 {max_tags} 个）...")
        self.page.wait_for_timeout(3000)
        try:
            # 找到底下可能包含 # 开头的标签元素
            tags_loc = self.page.locator(".tag-item, .topic-item, [class*='tag'], [class*='topic'], [class*='hashtag']")
            count = tags_loc.count()
            selected = 0
            
            for i in range(count):
                if selected >= max_tags:
                    break
                loc = tags_loc.nth(i)
                text = loc.text_content() or ""
                if text.strip().startswith("#"):
                    loc.click()
                    selected += 1
                    print(f"[小红书]   ✓ 选中标签: {text.strip()}")
                    self.page.wait_for_timeout(500)
            
            if selected == 0:
                print("[小红书] 未匹配到推荐标签")
        except Exception as e:
            print(f"[小红书] 选取推荐标签出错: {e}")

    def close(self):
        """关闭浏览器"""
        try:
            self._save_cookies()
            if hasattr(self, 'context'):
                self.context.close()
            if hasattr(self, 'browser') and self.browser:
                self.browser.close()
            if hasattr(self, '_playwright'):
                self._playwright.stop()
            print("[小红书] 浏览器已关闭")
        except Exception:
            pass

if __name__ == "__main__":
    # 快速测试
    poster = XiaohongshuPoster()
    poster.login()
    print("登录成功，10 秒后关闭...")
    import time
    time.sleep(10)
    poster.close()
