"""
灏忕孩涔﹀彂甯冩ā鍧?
浣跨敤 undetected_chromedriver 鎿嶆帶 creator.xiaohongshu.com 鍙戝竷绗旇銆?鏀寔 Cookie 鎸佷箙鍖栫櫥褰曪紝閬垮厤閲嶅鎵爜銆?"""

import json
import os
import time

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import XHS_COOKIES_FILE


class XiaohongshuPoster:
    """灏忕孩涔﹀垱浣滆€呭钩鍙拌嚜鍔ㄥ彂甯?""

    CREATOR_URL = "https://creator.xiaohongshu.com"
    LOGIN_URL = "https://creator.xiaohongshu.com/login"
    PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish"

    def __init__(self, user_data_dir: str = "", profile: str = "Default"):
        """
        鍒濆鍖栨祻瑙堝櫒瀹炰緥銆?
        Args:
            user_data_dir: Chrome 鐢ㄦ埛鏁版嵁鐩綍璺緞銆傚鏋滄彁渚涳紝澶嶇敤宸叉湁 Chrome 鐧诲綍鎬併€?            profile: Chrome Profile 鍚嶇О锛岄粯璁?"Default"銆?        """
        # cookies 鏂囦欢璺緞浣跨敤 config 涓殑閰嶇疆
        self.cookies_file = XHS_COOKIES_FILE

        options = uc.ChromeOptions()

        if user_data_dir and os.path.exists(user_data_dir):
            options.add_argument(f"--user-data-dir={user_data_dir}")
            options.add_argument(f"--profile-directory={profile}")
            print(f"[灏忕孩涔 浣跨敤 Chrome 鐢ㄦ埛鏁版嵁鐩綍: {user_data_dir} (Profile: {profile})")
        else:
            print("[灏忕孩涔 浣跨敤鐙珛娴忚鍣ㄥ疄渚?)

        # 闄嶄綆琚娴嬫鐜?        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        
        # 寮哄埗璁?Chrome 鐨勫唴閮ㄩ€氫俊缁曡繃鏈湴浠ｇ悊锛岄槻姝㈠拰 TUN 鎴栧叏灞€浠ｇ悊鍐茬獊瀵艰嚧 Bad Gateway
        options.add_argument("--proxy-bypass-list=127.0.0.1,localhost,::1")

        self.driver = uc.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 20)
        self._logged_in = False

    def _load_cookies(self) -> bool:
        """鍔犺浇淇濆瓨鐨?cookies"""
        if not os.path.exists(self.cookies_file):
            return False

        try:
            with open(self.cookies_file, "r", encoding="utf-8") as f:
                cookies = json.load(f)

            self.driver.get(self.CREATOR_URL)
            time.sleep(2)

            for cookie in cookies:
                # 绉婚櫎鍙兘瀵艰嚧闂鐨勫瓧娈?                for key in ["sameSite", "httpOnly", "expiry", "storeId"]:
                    cookie.pop(key, None)
                try:
                    self.driver.add_cookie(cookie)
                except Exception:
                    pass

            return True
        except Exception as e:
            print(f"[灏忕孩涔 鍔犺浇 cookies 澶辫触: {e}")
            return False

    def _save_cookies(self):
        """淇濆瓨褰撳墠 cookies"""
        try:
            # 纭繚 cookies 鏂囦欢鎵€鍦ㄧ洰褰曞瓨鍦?            cookies_dir = os.path.dirname(self.cookies_file)
            if cookies_dir:
                os.makedirs(cookies_dir, exist_ok=True)

            cookies = self.driver.get_cookies()
            with open(self.cookies_file, "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            print("[灏忕孩涔 Cookies 宸蹭繚瀛?)
        except Exception as e:
            print(f"[灏忕孩涔 淇濆瓨 cookies 澶辫触: {e}")

    def _is_logged_in(self) -> bool:
        """妫€鏌ユ槸鍚﹀凡鐧诲綍"""
        current = self.driver.current_url
        # 濡傛灉涓嶅湪鐧诲綍椤碉紝璇存槑宸茬櫥褰?        return "login" not in current

    def login(self):
        """
        鐧诲綍灏忕孩涔﹀垱浣滆€呭钩鍙般€?
        浼樺厛浣跨敤淇濆瓨鐨?cookies锛屽け璐ュ垯绛夊緟鎵嬪姩鎵爜鐧诲綍銆?        """
        if self._logged_in:
            return

        print("[灏忕孩涔 灏濊瘯鐧诲綍...")

        # 灏濊瘯 cookies 鐧诲綍
        if self._load_cookies():
            self.driver.get(self.CREATOR_URL)
            time.sleep(3)
            if self._is_logged_in():
                print("[灏忕孩涔 鉁?Cookies 鐧诲綍鎴愬姛")
                self._save_cookies()  # 鍒锋柊 cookies
                self._logged_in = True
                return
            else:
                print("[灏忕孩涔 Cookies 宸插け鏁堬紝娓呯悊...")
                self.driver.delete_all_cookies()

        # 鎵嬪姩鎵爜鐧诲綍
        self.driver.get(self.LOGIN_URL)
        time.sleep(2)

        print("[灏忕孩涔 鈿?璇峰湪娴忚鍣ㄤ腑鎵爜鐧诲綍锛?)
        print("[灏忕孩涔 绛夊緟鐧诲綍瀹屾垚...")

        # 姣?3 绉掓鏌ヤ竴娆℃槸鍚﹀凡鐧诲綍锛屾渶澶氱瓑寰?120 绉?        for _ in range(40):
            time.sleep(3)
            if self._is_logged_in():
                print("[灏忕孩涔 鉁?鎵爜鐧诲綍鎴愬姛")
                self._save_cookies()
                self._logged_in = True
                return

        raise TimeoutError("[灏忕孩涔 鐧诲綍瓒呮椂锛岃鍦?120 绉掑唴瀹屾垚鎵爜")

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
        鍙戝竷绗旇鍒板皬绾功銆?
        Args:
            title: 绗旇鏍囬锛堟渶澶?20 瀛楋級
            content: 绗旇姝ｆ枃
            images: 鍥剧墖鏂囦欢璺緞鍒楄〃
            video: 瑙嗛鏂囦欢璺緞锛堜笌 images 浜岄€変竴锛?            use_long_article: 鏄惁浣跨敤"鍐欓暱鏂?妯″紡锛堜唬鏇挎棤鍥剧墖鐨勫浘鏂囨ā寮忥級
            wait_before_publish: 鍙戝竷鍓嶇瓑寰呯鏁帮紝缁欑敤鎴锋椂闂村鏍?        """
        if not self._logged_in:
            self.login()

        print("[灏忕孩涔 寮€濮嬪彂甯冪瑪璁?..")

        # 瀵艰埅鍒板彂甯冮〉
        self.driver.get(self.PUBLISH_URL)
        time.sleep(3)

        # === 鍒囨崲瀵瑰簲 Tab ===
        if use_long_article:
            print("[灏忕孩涔 鍒囨崲鍒?鍐欓暱鏂?鍙戝竷妯″紡...")
            try:
                # 鍒囨崲"鍐欓暱鏂? Tab
                tab = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, "//*[contains(text(), '鍐欓暱鏂?)]"))
                )
                self.driver.execute_script("arguments[0].click();", tab)
                time.sleep(2)
                
                # 闀挎枃鐣岄潰闇€瑕佺偣鍑?鏂扮殑鍒涗綔"鎸夐挳鎵嶈兘寮€濮嬪啓
                try:
                    new_btn = WebDriverWait(self.driver, 3).until(
                        EC.presence_of_element_located((By.XPATH, "//*[contains(text(), '鏂扮殑鍒涗綔')]"))
                    )
                    self.driver.execute_script("arguments[0].click();", new_btn)
                    time.sleep(2)
                except Exception:
                    pass
            except Exception as e:
                print(f"[灏忕孩涔 鍒囨崲鍐欓暱鏂囨ā寮忓け璐? {e}")
        elif video:
            print("[灏忕孩涔 鍒囨崲鍒?瑙嗛 鍙戝竷妯″紡...")
            try:
                tab = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//*[text()='涓婁紶瑙嗛' or text()='鍙戝竷瑙嗛']"))
                )
                tab.click()
                time.sleep(1)
            except Exception:
                pass
        elif images:
            print("[灏忕孩涔 鍒囨崲鍒?鍥炬枃 鍙戝竷妯″紡...")
            try:
                # 浣跨敤 XPath 妯＄硦鍖归厤锛屽苟鐢?JS 鐐瑰嚮浠ラ槻琚伄鎸?                tab = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, "//*[contains(text(), '鍥炬枃')]"))
                )
                self.driver.execute_script("arguments[0].click();", tab)
                time.sleep(2)
            except Exception as e:
                print(f"[灏忕孩涔 鍒囨崲鍥炬枃 Tab 澶辫触: {e}")

        # === 涓婁紶濯掍綋 ===
        if video:
            self._upload_video(video)
        elif images:
            self._upload_images(images)
        elif use_long_article:
            print("[灏忕孩涔 闀挎枃妯″紡锛岃烦杩囧獟浣撲笂浼?..")
        else:
            raise ValueError("蹇呴』鎻愪緵鍥剧墖鎴栬棰戯紝鎴栬€呭惎鐢ㄤ娇鐢ㄩ暱鏂囨ā寮?)

        time.sleep(3)

        # === 濉啓鏍囬 ===
        try:
            if use_long_article:
                # 闀挎枃鐨勬爣棰樹娇鐢ㄧ殑鏄?textarea
                title_input = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, "//textarea[contains(@class, 'd-text') or @placeholder='璧蜂釜鍝嶄寒鐨勬爣棰樺惂']"))
                )
                title_input.clear()
                # 浣跨敤 JS 璧嬪€奸伩鍏?BMP 瀛楃锛堝 emoji锛夊鑷?ChromeDriver 宕╂簝
                self.driver.execute_script("""
                    arguments[0].value = arguments[1];
                    arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
                """, title_input, title)
            else:
                self._fill_title(title)
        except Exception as e:
            print(f"[灏忕孩涔 濉啓鏍囬鏃跺彂鐢熼棶棰? {e}")

        # === 濉啓姝ｆ枃 ===
        try:
            if use_long_article:
                # 闀挎枃鍐呭妗嗕娇鐢ㄧ殑鏄壒娈婄殑瀵屾枃鏈紪杈戝櫒 (Tiptap / ProseMirror)
                content_input = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, "//*[@data-placeholder='绮樿创鍒拌繖閲屾垨杈撳叆鏂囧瓧'] | //div[contains(@class, 'ProseMirror')]"))
                )
                
                # 鐐瑰嚮鑱氱劍
                self.driver.execute_script("arguments[0].focus();", content_input)
                time.sleep(1)

                # 瀵逛簬 ProseMirror 杩欑澶嶆潅鐨勫瘜鏂囨湰缂栬緫鍣紝鐩存帴璁剧疆 innerHTML 鍙兘浼氳 React 鎷︽埅娓呯┖銆?                # 鏈€绋冲畾鐨勬柟寮忔槸鍒嗗壊澶氭鏂囨湰锛屼娇鐢?send_keys 妯℃嫙浜虹被杈撳叆
                content_input.clear()
                
                # 涓轰簡闃叉琛ㄦ儏瀵艰嚧 ChromeDriver 宕╂簝锛屾垨鑰呭ぇ娈垫枃鏈緭鍏ユ參锛?                # 鎴戜滑鍙互鐢?JS 璧嬪€?+ send_keys 娣峰悎锛屾垨鑰呰繃婊ゆ帀杩囦簬搴曞眰鐨勫瓧绗?                # 杩欓噷鍏堝皢鏂囨湰璐村叆
                html_content = content.replace('\n', '<br>')
                self.driver.execute_script("""
                    var editor = arguments[0];
                    var text = arguments[1];
                    editor.innerHTML = '<p>' + text + '</p>';
                    var event = new Event('input', { bubbles: true });
                    editor.dispatchEvent(event);
                """, content_input, html_content)
                time.sleep(1)
                
                # 涓轰簡纭繚鍏夋爣姝ｅ父锛屽苟璁╃紪杈戝櫒鐪熸淇濆瓨鐘舵€侊紙闃茶崏绋夸涪澶憋級锛屾暡鍑讳竴涓┖鏍煎拰涓€涓€€鏍?                content_input.send_keys(" ")
                time.sleep(0.5)
                content_input.send_keys("\\b")
                
                # 瑙﹀彂涓€涓?hashtags 澶勭悊
                import re
                from selenium.webdriver.common.keys import Keys
                
                pattern = r'#([^\s#锛屻€傦紒锛?銆??"\'\[\]]+)(?:\[璇濋\]#?)?'
                matches = list(re.finditer(pattern, content))
                
                hashtags_to_type = []
                for m in matches:
                    if m.group(1) not in hashtags_to_type:
                        hashtags_to_type.append(m.group(1))
                        
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
            print(f"[灏忕孩涔 濉啓姝ｆ枃鏃跺彂鐢熼棶棰? {e}")

        time.sleep(2)

        # === 鑷姩閫夊彇灏忕孩涔︽帹鑽愭爣绛撅紙鍦ㄥ唴瀹瑰～鍏呭悗锛岄伩鍏嶈 innerHTML 瑕嗙洊锛?==
        if not use_long_article:
            self._select_suggested_tags(max_tags=5)

        # === 绛夊緟鐢ㄦ埛瀹℃牳 ===
        if wait_before_publish > 0:
            print(f"[灏忕孩涔 鍐呭宸插～鍏咃紝绛夊緟 {wait_before_publish} 绉掔敤浜庡鏍?..")
            print(f"[灏忕孩涔 濡傞渶鍙栨秷鍙戝竷锛岃鍦?{wait_before_publish} 绉掑唴鎵嬪姩鍏抽棴娴忚鍣?)
            time.sleep(wait_before_publish)

        # === 鐐瑰嚮鍙戝竷 ===
        self._click_publish()
        print("[灏忕孩涔 鉁?绗旇鍙戝竷瀹屾垚锛?)
        time.sleep(5)

    def _upload_images(self, image_paths: list[str]):
        """涓婁紶鍥剧墖"""
        print(f"[灏忕孩涔 涓婁紶 {len(image_paths)} 寮犲浘鐗?..")

        # 灏嗚矾寰勮浆涓虹粷瀵硅矾寰?        abs_paths = [os.path.abspath(p) for p in image_paths]

        try:
            # 鏌ユ壘涓婁紶 input
            upload_input = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']"))
            )
            
            # 寮哄埗娣诲姞 multiple 灞炴€э紝闃叉鎶ラ敊 "element can not hold multiple files"
            self.driver.execute_script("arguments[0].setAttribute('multiple', 'multiple');", upload_input)
            
            # Selenium 鐨?send_keys 鍙互涓€娆′紶澶氫釜鏂囦欢锛岀敤 \n 鍒嗛殧
            upload_input.send_keys("\n".join(abs_paths))
            print("[灏忕孩涔 鍥剧墖宸蹭笂浼狅紝绛夊緟澶勭悊...")
            time.sleep(5)
        except Exception as e:
            print(f"[灏忕孩涔 鍥剧墖涓婁紶澶辫触: {e}")
            raise

    def _upload_video(self, video_path: str):
        """涓婁紶瑙嗛"""
        print(f"[灏忕孩涔 涓婁紶瑙嗛: {video_path}")

        abs_path = os.path.abspath(video_path)

        try:
            upload_input = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']"))
            )
            upload_input.send_keys(abs_path)
            print("[灏忕孩涔 瑙嗛宸蹭笂浼狅紝绛夊緟澶勭悊锛堝彲鑳介渶瑕佽緝闀挎椂闂达級...")
            # 瑙嗛澶勭悊闇€瑕佹洿澶氭椂闂?            time.sleep(15)
        except Exception as e:
            print(f"[灏忕孩涔 瑙嗛涓婁紶澶辫触: {e}")
            raise

    def _fill_title(self, title: str):
        """填写标题"""
        title = title[:20]
        print(f"[小红书] 填写标题: {title}")
        try:
            # 兼容新版 UI：带有 .d-input 父级和 placeholder 的 input.d-text
            title_input = self.page.locator(".d-input input.d-text, input[placeholder*='标题'], input.d-text").first
            title_input.wait_for(timeout=5000)
            title_input.fill(title)
        except Exception as e:
            print(f"[小红书] 标题填写失败: {e}")
            raise RuntimeError(f"标题填写失败，找不到标题输入框: {e}")

    def _fill_content(self, content: str):
        """濉啓姝ｆ枃"""
        print(f"[灏忕孩涔 濉啓姝ｆ枃 ({len(content)} 瀛?...")

        try:
                except Exception:
                    continue

            if editor:
                import re
                import time
                from selenium.webdriver.common.keys import Keys
                
                # 鎻愬彇鎵€鏈夌殑 hashtags锛屾敮鎸佽繃婊ゆ爣鐐瑰拰[璇濋]鍚庣紑
                pattern = r'#([^\s#锛屻€傦紒锛?銆??"\'\[\]]+)(?:\[璇濋\]#?)?'
                matches = list(re.finditer(pattern, content))
                
                # 浠庝富鏂囨湰涓墧闄ゆ墍鏈?hashtags
                main_content = content
                hashtags_to_type = []
                for m in matches:
                    full_match = m.group(0)
                    tag_name = m.group(1)
                    main_content = main_content.replace(full_match, '')
                    if tag_name not in hashtags_to_type:
                        hashtags_to_type.append(tag_name)
                main_content = main_content.strip()

                # 娓呯┖缂栬緫鍣ㄥ苟鐢?JS 杈撳叆涓诲唴瀹癸紝閬垮厤 ChromeDriver 鐨?BMP emoji 鎶ラ敊
                html_content = main_content.replace('\n', '<br>')
                
                self.driver.execute_script("""
                    var editor = arguments[0];
                    var text = arguments[1];
                    editor.innerHTML = text;
                    editor.focus();
                    // 瑙﹀彂 input 浜嬩欢浠ヨ React/Vue 鎶撳彇鍒板唴瀹?                    var event = new Event('input', { bubbles: true });
                    editor.dispatchEvent(event);
                """, editor, html_content)

                time.sleep(1)

                # 灏嗗厜鏍囩Щ鍔ㄥ埌鏂囨湰鏈熬骞惰緭鍏ョ湡姝ｇ殑鏍囩
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
                    
                    # 琛ュ厖鎹㈣
                    editor.send_keys('\n\n')
                    time.sleep(0.5)

                    for tag_name in hashtags_to_type:
                        # 杩囨护闈?BMP 瀛楃锛堣〃鎯咃級锛岄槻姝?send_keys 宕╂簝
                        safe_tag = "".join(c for c in tag_name if ord(c) <= 0xFFFF)
                        if safe_tag:
                            editor.send_keys('#' + safe_tag) 
                            time.sleep(1.0) # 绛夊緟鑱旀兂鑿滃崟鍑虹幇
                            editor.send_keys(Keys.ENTER) # 鎸夊洖杞﹂€変腑
                            time.sleep(0.5)
                            editor.send_keys(' ')
                            time.sleep(0.2)

            else:
                print("[灏忕孩涔 鏃犳硶鎵惧埌姝ｆ枃缂栬緫鍣?)
        except Exception as e:
            print(f"[灏忕孩涔 姝ｆ枃濉啓澶辫触: {e}")

    def _click_publish(self):
        """鐐瑰嚮鍙戝竷鎸夐挳"""
        print("[灏忕孩涔 鐐瑰嚮鍙戝竷...")

        try:
            selectors = [
                "button.publishBtn",
                ".d-button.publishBtn",
                "button[class*='publish']",
                # 鎸夋枃鏈煡鎵?                "//button[contains(text(), '鍙戝竷')]",
            ]

            for sel in selectors:
                try:
                    if sel.startswith("//"):
                        btn = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, sel))
                        )
                    else:
                        btn = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                        )
                    btn.click()
                    return
                except Exception:
                    continue

            # 鍏滃簳
            self.driver.execute_script("""
                var btns = document.querySelectorAll('button');
                for (var i = 0; i < btns.length; i++) {
                    if (btns[i].textContent.includes('鍙戝竷')) {
                        btns[i].click();
                        break;
                    }
                }
            """)
        except Exception as e:
            print(f"[灏忕孩涔 鐐瑰嚮鍙戝竷鎸夐挳澶辫触: {e}")
            raise

    def _select_suggested_tags(self, max_tags: int = 5):
        """
        鑷姩鐐归€夊皬绾功鏍规嵁鍥剧墖/瑙嗛鍐呭鎺ㄨ崘鐨勬爣绛俱€?        杩欎簺鏍囩鍦ㄤ笂浼犲獟浣撳悗鍑虹幇鍦ㄥ唴瀹圭紪杈戝尯涓嬫柟銆?        """
        print(f"[灏忕孩涔 灏濊瘯閫夊彇鎺ㄨ崘鏍囩锛堟渶澶?{max_tags} 涓級...")

        try:
            # 绛変竴浼氳鎺ㄨ崘鏍囩鍔犺浇鍑烘潵
            time.sleep(3)

            # 鑾峰彇鎺ㄨ崘鏍囩鍏冪礌
            # 灏忕孩涔︽帹鑽愭爣绛鹃€氬父鏄唴瀹瑰尯涓嬫柟鍙偣鍑荤殑 span/div锛屾枃鏈互 # 寮€澶?            tag_elements = self.driver.execute_script("""
                // 绛栫暐1: 鏌ユ壘鏍囩瀹瑰櫒涓殑鍙偣鍑诲厓绱?                var tags = [];

                // 鏌ユ壘鎵€鏈夊寘鍚?# 寮€澶存枃鏈殑鍙偣鍑诲厓绱?                var allElements = document.querySelectorAll(
                    '.tag-item, .topic-item, [class*="tag"], [class*="topic"], [class*="hashtag"]'
                );
                allElements.forEach(function(el) {
                    var text = el.textContent.trim();
                    if (text.startsWith('#') && text.length > 1 && text.length < 30) {
                        tags.push(el);
                    }
                });

                // 绛栫暐2: 鍏滃簳鈥斺€斿湪搴曢儴鍖哄煙鎵炬墍鏈?# 寮€澶寸殑灏忓厓绱?                if (tags.length === 0) {
                    var candidates = document.querySelectorAll('span, div, a, button');
                    candidates.forEach(function(el) {
                        var text = el.textContent.trim();
                        var rect = el.getBoundingClientRect();
                        // 鍙鏂囨湰浠?# 寮€澶淬€侀暱搴﹀悎鐞嗐€佷綅浜庨〉闈笅鍗婇儴鍒?                        if (text.startsWith('#') && text.length > 1 && text.length < 30
                            && rect.height > 0 && rect.height < 50
                            && el.children.length === 0) {
                            tags.push(el);
                        }
                    });
                }

                return tags;
            """)

            if not tag_elements:
                print("[灏忕孩涔 鏈彂鐜版帹鑽愭爣绛撅紝璺宠繃")
                return

            selected = 0
            for tag_el in tag_elements:
                if selected >= max_tags:
                    break
                try:
                    tag_text = tag_el.text.strip()
                    self.driver.execute_script("arguments[0].click();", tag_el)
                    selected += 1
                    print(f"[灏忕孩涔   鉁?閫変腑鏍囩: {tag_text}")
                    time.sleep(0.5)
                except Exception:
                    continue

            if selected > 0:
                print(f"[灏忕孩涔 鍏遍€変腑 {selected} 涓帹鑽愭爣绛?)
            else:
                print("[灏忕孩涔 鎺ㄨ崘鏍囩鐐瑰嚮澶辫触锛岃烦杩?)

        except Exception as e:
            print(f"[灏忕孩涔 閫夊彇鎺ㄨ崘鏍囩鏃跺嚭閿欙紙涓嶅奖鍝嶅彂甯冿級: {e}")

    def close(self):
        """鍏抽棴娴忚鍣?""
        try:
            self._save_cookies()
            self.driver.quit()
            print("[灏忕孩涔 娴忚鍣ㄥ凡鍏抽棴")
        except Exception:
            pass


# --- 蹇€熸祴璇?---
if __name__ == "__main__":
    poster = XiaohongshuPoster()
    poster.login()
    print("鐧诲綍鎴愬姛锛?0 绉掑悗鍏抽棴娴忚鍣?..")
    time.sleep(10)
    poster.close()
