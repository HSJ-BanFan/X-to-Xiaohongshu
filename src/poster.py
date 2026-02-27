"""
小红书发布模块

使用 undetected_chromedriver 操控 creator.xiaohongshu.com 发布笔记。
支持 Cookie 持久化登录，避免重复扫码。
"""

import json
import os
import time

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import XHS_COOKIES_FILE


def safe_find(driver, by, value, timeout=10, name="未知元素"):
    """安全查找元素，失败时自动保存截图和源码"""
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )
    except Exception as e:
        import time
        timestamp = int(time.time())
        screenshot_path = f"debug_screenshots/{name}_fail_{timestamp}.png"
        html_path = f"debug_screenshots/{name}_fail_{timestamp}.html"
        try:
            driver.save_screenshot(screenshot_path)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print(f"[XHS ERROR] 获取元素失败: {name}, 已保存现场: {screenshot_path}, {html_path}")
        except Exception as screen_e:
            print(f"[XHS ERROR] 保存现场截图失败: {screen_e}")
            
        print(f"[XHS ERROR] 元素 {name} 查找失败({by}={value})。可能原因：")
        print("1. 页面元素选择器已更改（例如页面改版）。")
        print("2. 页面加载异常缓慢或网络中断。")
        print("3. 被反爬验证码拦截或存在弹窗遮挡。")
        raise e


class XiaohongshuPoster:
    """小红书创作者平台自动发布"""

    CREATOR_URL = "https://creator.xiaohongshu.com"
    LOGIN_URL = "https://creator.xiaohongshu.com/login"
    PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish"

    def __init__(self, user_data_dir: str = "", profile: str = "Default"):
        """
        初始化浏览器实例。

        Args:
            user_data_dir: Chrome 用户数据目录路径。如果提供，复用已有 Chrome 登录态。
            profile: Chrome Profile 名称，默认 "Default"。
        """
        # cookies 文件路径使用 config 中的配置
        self.cookies_file = XHS_COOKIES_FILE

        options = uc.ChromeOptions()

        if user_data_dir and os.path.exists(user_data_dir):
            options.add_argument(f"--user-data-dir={user_data_dir}")
            options.add_argument(f"--profile-directory={profile}")
            print(f"[小红书] 使用 Chrome 用户数据目录: {user_data_dir} (Profile: {profile})")
        else:
            print("[小红书] 使用独立浏览器实例")

        # 降低被检测概率
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        
        # 强制让 Chrome 的内部通信绕过本地代理，防止和 TUN 或全局代理冲突导致 Bad Gateway
        options.add_argument("--proxy-bypass-list=127.0.0.1,localhost,::1")

        self.driver = uc.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 20)
        self._logged_in = False

    def _load_cookies(self) -> bool:
        """加载保存的 cookies"""
        if not os.path.exists(self.cookies_file):
            return False

        try:
            with open(self.cookies_file, "r", encoding="utf-8") as f:
                cookies = json.load(f)

            self.driver.get(self.CREATOR_URL)
            time.sleep(2)

            for cookie in cookies:
                # 移除可能导致问题的字段
                for key in ["sameSite", "httpOnly", "expiry", "storeId"]:
                    cookie.pop(key, None)
                try:
                    self.driver.add_cookie(cookie)
                except Exception:
                    pass

            return True
        except Exception as e:
            print(f"[小红书] 加载 cookies 失败: {e}")
            return False

    def _save_cookies(self):
        """保存当前 cookies"""
        try:
            # 确保 cookies 文件所在目录存在
            cookies_dir = os.path.dirname(self.cookies_file)
            if cookies_dir:
                os.makedirs(cookies_dir, exist_ok=True)

            cookies = self.driver.get_cookies()
            with open(self.cookies_file, "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            print("[小红书] Cookies 已保存")
        except Exception as e:
            print(f"[小红书] 保存 cookies 失败: {e}")

    def _is_logged_in(self) -> bool:
        """检查是否已登录"""
        current = self.driver.current_url
        # 如果不在登录页，说明已登录
        return "login" not in current

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
            self.driver.get(self.CREATOR_URL)
            time.sleep(3)
            if self._is_logged_in():
                print("[小红书] ✓ Cookies 登录成功")
                self._save_cookies()  # 刷新 cookies
                self._logged_in = True
                return
            else:
                print("[小红书] Cookies 已失效，清理...")
                self.driver.delete_all_cookies()

        # 手动扫码登录
        self.driver.get(self.LOGIN_URL)
        time.sleep(2)

        print("[小红书] ⚠ 请在浏览器中扫码登录！")
        print("[小红书] 等待登录完成...")

        # 每 3 秒检查一次是否已登录，最多等待 120 秒
        for _ in range(40):
            time.sleep(3)
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

        Args:
            title: 笔记标题（最多 20 字）
            content: 笔记正文
            images: 图片文件路径列表
            video: 视频文件路径（与 images 二选一）
            use_long_article: 是否使用"写长文"模式（代替无图片的图文模式）
            wait_before_publish: 发布前等待秒数，给用户时间审核
        """
        if not self._logged_in:
            self.login()

        print("[小红书] 开始发布笔记...")

        # 导航到发布页
        self.driver.get(self.PUBLISH_URL)
        time.sleep(3)

        # === 切换对应 Tab ===
        if use_long_article:
            print("[小红书] 切换到 写长文 发布模式...")
            try:
                # 切换"写长文" Tab
                tab = safe_find(self.driver, By.XPATH, "//*[contains(text(), '写长文')]", timeout=5, name="写长文Tab")
                self.driver.execute_script("arguments[0].click();", tab)
                time.sleep(2)
                
                # 长文界面需要点击"新的创作"按钮才能开始写
                try:
                    new_btn = safe_find(self.driver, By.XPATH, "//*[contains(text(), '新的创作')]", timeout=3, name="新的创作按钮")
                    self.driver.execute_script("arguments[0].click();", new_btn)
                    time.sleep(2)
                except Exception:
                    pass
            except Exception as e:
                print(f"[小红书] 切换写长文模式失败: {e}")
        elif video:
            print("[小红书] 切换到 视频 发布模式...")
            try:
                tab = safe_find(self.driver, By.XPATH, "//*[text()='上传视频' or text()='发布视频']", timeout=5, name="发布视频Tab")
                tab.click()
                time.sleep(1)
            except Exception:
                pass
        elif images:
            print("[小红书] 切换到 图文 发布模式...")
            try:
                # 使用 XPath 模糊匹配，并用 JS 点击以防被遮挡
                tab = safe_find(self.driver, By.XPATH, "//*[contains(text(), '图文')]", timeout=5, name="发布图文Tab")
                self.driver.execute_script("arguments[0].click();", tab)
                time.sleep(2)
            except Exception as e:
                print(f"[小红书] 切换图文 Tab 失败: {e}")

        # === 上传媒体 ===
        if video:
            self._upload_video(video)
        elif images:
            self._upload_images(images)
        elif use_long_article:
            print("[小红书] 长文模式，跳过媒体上传...")
        else:
            raise ValueError("必须提供图片或视频，或者启用使用长文模式")

        time.sleep(3)

        # === 填写标题 ===
        try:
            if use_long_article:
                # 长文的标题使用的是 textarea
                title_input = safe_find(self.driver, By.XPATH, "//textarea[contains(@class, 'd-text') or @placeholder='起个响亮的标题吧']", timeout=5, name="长文标题输入框")
                title_input.clear()
                # 使用 JS 赋值避免 BMP 字符（如 emoji）导致 ChromeDriver 崩溃
                self.driver.execute_script("""
                    arguments[0].value = arguments[1];
                    arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
                """, title_input, title)
            else:
                self._fill_title(title)
        except Exception as e:
            print(f"[小红书] 填写标题时发生问题: {e}")

        # === 填写正文 ===
        try:
            if use_long_article:
                # 长文内容框使用的是特殊的富文本编辑器 (Tiptap / ProseMirror)
                content_input = safe_find(self.driver, By.XPATH, "//*[@data-placeholder='粘贴到这里或输入文字'] | //div[contains(@class, 'ProseMirror')]", timeout=5, name="长文正文输入框")
                
                # 点击聚焦
                self.driver.execute_script("arguments[0].focus();", content_input)
                time.sleep(1)

                # 对于 ProseMirror 这种复杂的富文本编辑器，直接设置 innerHTML 可能会被 React 拦截清空。
                # 最稳定的方式是分割多段文本，使用 send_keys 模拟人类输入
                content_input.clear()
                
                # 为了防止表情导致 ChromeDriver 崩溃，或者大段文本输入慢，
                import re
                from selenium.webdriver.common.keys import Keys
                
                # 提取所有的 hashtags，支持过滤标点和[话题]后缀
                pattern = r'#([^\s#，。！？,。!?"\'\[\]]+)(?:\[话题\]#?)?'
                matches = list(re.finditer(pattern, content))
                
                # 从主文本中剔除所有 hashtags，连带前面的可能空格一起剔除
                main_content = re.sub(r'\s*' + pattern + r'\s*', ' ', content)
                
                # 剔除连续的多余空行
                main_content = re.sub(r'\n{3,}', '\n\n', main_content).strip()

                hashtags_to_type = []
                for m in matches:
                    tag_name = m.group(1)
                    if tag_name not in hashtags_to_type:
                        hashtags_to_type.append(tag_name)
                
                # 清空编辑器并用 JS 输入主内容
                html_content = main_content.replace('\n', '<br>')
                self.driver.execute_script("""
                    var editor = arguments[0];
                    var text = arguments[1];
                    editor.innerHTML = '<p>' + text + '</p>';
                    var event = new Event('input', { bubbles: true });
                    editor.dispatchEvent(event);
                """, content_input, html_content)
                time.sleep(1)
                
                # 为了确保光标正常，并让编辑器真正保存状态（防草稿丢失），敲击一个空格和一个退格
                content_input.send_keys(" ")
                time.sleep(0.5)
                content_input.send_keys("\\b")
                        
                if hashtags_to_type:
                     content_input.send_keys('\n\n')
                     for tag_name in hashtags_to_type:
                         safe_tag = "".join(c for c in tag_name if ord(c) <= 0xFFFF)
                         if safe_tag:
                             content_input.send_keys('#' + safe_tag)
                             time.sleep(1.0)
                             content_input.send_keys(Keys.ENTER)
                             time.sleep(0.5)
                             content_input.send_keys(' ')
                             time.sleep(0.2)

            else:
                self._fill_content(content)
        except Exception as e:
            print(f"[小红书] 填写正文时发生问题: {e}")

        time.sleep(2)

        # === 自动选取小红书推荐标签（在内容填充后，避免被 innerHTML 覆盖）===
        if not use_long_article:
            self._select_suggested_tags(max_tags=5)

        # === 等待用户审核 ===
        if wait_before_publish > 0:
            print(f"[小红书] 内容已填充，等待 {wait_before_publish} 秒用于审核...")
            print(f"[小红书] 如需取消发布，请在 {wait_before_publish} 秒内手动关闭浏览器")
            time.sleep(wait_before_publish)

        # === 点击发布 ===
        self._click_publish()
        print("[小红书] ✓ 笔记发布完成！")
        time.sleep(5)

    def _upload_images(self, image_paths: list[str]):
        """上传图片"""
        print(f"[小红书] 上传 {len(image_paths)} 张图片...")

        # 将路径转为绝对路径
        abs_paths = [os.path.abspath(p) for p in image_paths]

        try:
            # 查找上传 input
            upload_input = safe_find(self.driver, By.CSS_SELECTOR, "input[type='file']", timeout=20, name="图片上传input")
            
            # 强制添加 multiple 属性，防止报错 "element can not hold multiple files"
            self.driver.execute_script("arguments[0].setAttribute('multiple', 'multiple');", upload_input)
            
            # Selenium 的 send_keys 可以一次传多个文件，用 \n 分隔
            upload_input.send_keys("\n".join(abs_paths))
            print("[小红书] 图片已上传，等待处理...")
            time.sleep(5)
        except Exception as e:
            print(f"[小红书] 图片上传失败: {e}")
            raise

    def _upload_video(self, video_path: str):
        """上传视频"""
        print(f"[小红书] 上传视频: {video_path}")

        abs_path = os.path.abspath(video_path)

        try:
            upload_input = safe_find(self.driver, By.CSS_SELECTOR, "input[type='file']", timeout=20, name="视频上传input")
            upload_input.send_keys(abs_path)
            print("[小红书] 视频已上传，等待处理（可能需要较长时间）...")
            # 视频处理需要更多时间
            time.sleep(15)
        except Exception as e:
            print(f"[小红书] 视频上传失败: {e}")
            raise

    def _fill_title(self, title: str):
        """填写标题"""
        # 小红书标题限制 20 字
        title = title[:20]
        print(f"[小红书] 填写标题: {title}")

        try:
            # 尝试多种可能的标题输入选择器
            selectors = [
                "input.d-text",
                "#title-input",
                "input[placeholder*='标题']",
                ".title-input input",
                "input[maxlength='20']",
            ]

            title_input = None
            for sel in selectors:
                try:
                    title_input = safe_find(self.driver, By.CSS_SELECTOR, sel, timeout=5, name="常规标题输入框")
                    if title_input:
                        break
                except Exception:
                    continue

            if title_input:
                title_input.clear()
                # 使用 JS 赋值避免 BMP 字符导致 ChromeDriver 崩溃
                self.driver.execute_script("""
                    arguments[0].value = arguments[1];
                    arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
                """, title_input, title)
            else:
                # 兜底：使用 JS 操作
                self.driver.execute_script("""
                    var inputs = document.querySelectorAll('input[type="text"]');
                    for (var i = 0; i < inputs.length; i++) {
                        if (inputs[i].maxLength <= 20 || inputs[i].placeholder.includes('标题')) {
                            inputs[i].value = arguments[0];
                            inputs[i].dispatchEvent(new Event('input', {bubbles: true}));
                            break;
                        }
                    }
                """, title)
        except Exception as e:
            print(f"[小红书] 标题填写失败: {e}")

    def _fill_content(self, content: str):
        """填写正文"""
        print(f"[小红书] 填写正文 ({len(content)} 字)...")

        try:
            # 正文使用 Quill 编辑器
            selectors = [
                ".ql-editor",
                "#post-content .ql-editor",
                "[contenteditable='true']",
            ]

            editor = None
            for sel in selectors:
                try:
                    editor = safe_find(self.driver, By.CSS_SELECTOR, sel, timeout=5, name="常规正文输入框")
                    if editor:
                        break
                except Exception:
                    continue

            if editor:
                import re
                import time
                from selenium.webdriver.common.keys import Keys
                
                # 提取所有的 hashtags，支持过滤标点和[话题]后缀
                pattern = r'#([^\s#，。！？,。!?"\'\[\]]+)(?:\[话题\]#?)?'
                matches = list(re.finditer(pattern, content))
                
                # 从主文本中剔除所有 hashtags，连带前面的可能空格一起剔除
                main_content = re.sub(r'\s*' + pattern + r'\s*', ' ', content)
                
                # 剔除连续的多余空行（将 3 个以上的换行替换为 2 个）
                main_content = re.sub(r'\n{3,}', '\n\n', main_content).strip()

                hashtags_to_type = []
                for m in matches:
                    tag_name = m.group(1)
                    if tag_name not in hashtags_to_type:
                        hashtags_to_type.append(tag_name)

                # 清空编辑器并用 JS 输入主内容，避免 ChromeDriver 的 BMP emoji 报错
                html_content = main_content.replace('\n', '<br>')
                
                self.driver.execute_script("""
                    var editor = arguments[0];
                    var text = arguments[1];
                    editor.innerHTML = text;
                    editor.focus();
                    // 触发 input 事件以让 React/Vue 抓取到内容
                    var event = new Event('input', { bubbles: true });
                    editor.dispatchEvent(event);
                """, editor, html_content)

                time.sleep(1)

                # 将光标移动到文本末尾并输入真正的标签
                if hashtags_to_type:
                    self.driver.execute_script("""
                        var editor = arguments[0];
                        var range = document.createRange();
                        var sel = window.getSelection();
                        if (editor.childNodes.length > 0) {
                            range.setStartAfter(editor.lastChild);
                        } else {
                            range.setStart(editor, 0);
                        }
                        range.collapse(true);
                        sel.removeAllRanges();
                        sel.addRange(range);
                        editor.focus();
                    """, editor)
                    
                    # 补充换行
                    editor.send_keys('\n\n')
                    time.sleep(0.5)

                    for tag_name in hashtags_to_type:
                        # 过滤非 BMP 字符（表情），防止 send_keys 崩溃
                        safe_tag = "".join(c for c in tag_name if ord(c) <= 0xFFFF)
                        if safe_tag:
                            editor.send_keys('#' + safe_tag) 
                            time.sleep(1.0) # 等待联想菜单出现
                            editor.send_keys(Keys.ENTER) # 按回车选中
                            time.sleep(0.5)
                            editor.send_keys(' ')
                            time.sleep(0.2)

            else:
                print("[小红书] 无法找到正文编辑器")
        except Exception as e:
            print(f"[小红书] 正文填写失败: {e}")

    def _click_publish(self):
        """点击发布按钮"""
        print("[小红书] 点击发布...")

        try:
            selectors = [
                "button.publishBtn",
                ".d-button.publishBtn",
                "button[class*='publish']",
                # 按文本查找
                "//button[contains(text(), '发布')]",
            ]

            for sel in selectors:
                try:
                    if sel.startswith("//"):
                        btn = safe_find(self.driver, By.XPATH, sel, timeout=5, name="发布按钮_XPATH")
                    else:
                        btn = safe_find(self.driver, By.CSS_SELECTOR, sel, timeout=5, name="发布按钮_CSS")
                    btn.click()
                    return
                except Exception:
                    continue

            # 兜底
            self.driver.execute_script("""
                var btns = document.querySelectorAll('button');
                for (var i = 0; i < btns.length; i++) {
                    if (btns[i].textContent.includes('发布')) {
                        btns[i].click();
                        break;
                    }
                }
            """)
        except Exception as e:
            print(f"[小红书] 点击发布按钮失败: {e}")
            raise

    def _select_suggested_tags(self, max_tags: int = 5):
        """
        自动点选小红书根据图片/视频内容推荐的标签。
        这些标签在上传媒体后出现在内容编辑区下方。
        """
        print(f"[小红书] 尝试选取推荐标签（最多 {max_tags} 个）...")

        try:
            # 等一会让推荐标签加载出来
            time.sleep(3)

            # 获取推荐标签元素
            # 小红书推荐标签通常是内容区下方可点击的 span/div，文本以 # 开头
            tag_elements = self.driver.execute_script("""
                // 策略1: 查找标签容器中的可点击元素
                var tags = [];

                // 查找所有包含 # 开头文本的可点击元素
                var allElements = document.querySelectorAll(
                    '.tag-item, .topic-item, [class*="tag"], [class*="topic"], [class*="hashtag"]'
                );
                allElements.forEach(function(el) {
                    var text = el.textContent.trim();
                    if (text.startsWith('#') && text.length > 1 && text.length < 30) {
                        tags.push(el);
                    }
                });

                // 策略2: 兜底——在底部区域找所有 # 开头的小元素
                if (tags.length === 0) {
                    var candidates = document.querySelectorAll('span, div, a, button');
                    candidates.forEach(function(el) {
                        var text = el.textContent.trim();
                        var rect = el.getBoundingClientRect();
                        // 只要文本以 # 开头、长度合理、位于页面下半部分
                        if (text.startsWith('#') && text.length > 1 && text.length < 30
                            && rect.height > 0 && rect.height < 50
                            && el.children.length === 0) {
                            tags.push(el);
                        }
                    });
                }

                return tags;
            """)

            if not tag_elements:
                print("[小红书] 未发现推荐标签，跳过")
                return

            selected = 0
            for tag_el in tag_elements:
                if selected >= max_tags:
                    break
                try:
                    tag_text = tag_el.text.strip()
                    self.driver.execute_script("arguments[0].click();", tag_el)
                    selected += 1
                    print(f"[小红书]   ✓ 选中标签: {tag_text}")
                    time.sleep(0.5)
                except Exception:
                    continue

            if selected > 0:
                print(f"[小红书] 共选中 {selected} 个推荐标签")
            else:
                print("[小红书] 推荐标签点击失败，跳过")

        except Exception as e:
            print(f"[小红书] 选取推荐标签时出错（不影响发布）: {e}")

    def close(self):
        """关闭浏览器"""
        try:
            self._save_cookies()
            self.driver.quit()
            print("[小红书] 浏览器已关闭")
        except Exception:
            pass


# --- 快速测试 ---
if __name__ == "__main__":
    poster = XiaohongshuPoster()
    poster.login()
    print("登录成功，10 秒后关闭浏览器...")
    time.sleep(10)
    poster.close()
