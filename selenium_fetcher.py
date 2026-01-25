#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
淘宝闪购智能助手Agent - Selenium自动化抓取模块
通过浏览器自动化获取商品数据，解决Cookie/API问题
"""

import os
import json
import time
import logging
import pickle
import socket
import shutil
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class GoodsItem:
    """商品信息"""
    goods_id: str
    goods_name: str
    category: str
    price: float
    original_price: float
    stock: int
    status: str
    status_text: str
    
    def to_dict(self) -> Dict:
        return {
            "goods_id": self.goods_id,
            "goods_name": self.goods_name,
            "category": self.category,
            "price": self.price,
            "original_price": self.original_price,
            "stock": self.stock,
            "status": self.status,
            "status_text": self.status_text,
        }


class SeleniumGoodsFetcher:
    """使用Selenium抓取商品数据 - 饿了么连锁商家后台"""
    
    def _log(self, msg: str):
        """输出日志（同时输出到logger和GUI回调）"""
        logger.info(msg)
        if hasattr(self, '_log_callback') and self._log_callback:
            try:
                self._log_callback(msg)
            except:
                pass
    
    @staticmethod
    def _get_persistent_dir() -> str:
        """
        获取持久化目录（用于保存登录状态、cookies等）
        
        - 打包后的 EXE: 使用 EXE 所在目录
        - 开发模式: 使用脚本所在目录
        """
        import sys
        
        # 检查是否是 PyInstaller 打包的 EXE
        if getattr(sys, 'frozen', False):
            # 打包后的 EXE，使用 EXE 所在目录
            exe_dir = os.path.dirname(sys.executable)
            logger.info(f"检测到打包模式，EXE目录: {exe_dir}")
            return exe_dir
        else:
            # 开发模式，使用脚本所在目录
            script_dir = os.path.dirname(os.path.abspath(__file__))
            logger.info(f"检测到开发模式，脚本目录: {script_dir}")
            return script_dir
    
    def __init__(
        self,
        shop_id: str,
        chain_id: str = "",
        base_url: str = "https://melody.shop.ele.me",
        headless: bool = False,
        debug_port: int = 9222,
        user_data_dir: Optional[str] = None,
        browser_path: Optional[str] = None,
        auto_launch_browser: bool = True,
    ):
        """
        初始化
        
        Args:
            shop_id: 店铺ID
            chain_id: 连锁店ID（饿了么连锁商家后台需要）
            base_url: 商家后台基础URL
            headless: 是否无头模式（建议首次运行设为False以便登录）
            debug_port: Chromium/Chrome 远程调试端口（默认 9222）
            user_data_dir: Chromium/Chrome 用户数据目录（用于持久化登录态）
            browser_path: 浏览器可执行文件路径（可选，留空自动寻找）
            auto_launch_browser: 无法连接调试端口时，是否自动启动浏览器
        """
        self.shop_id = shop_id
        self.chain_id = chain_id
        self.base_url = base_url.rstrip("/")
        self.headless = headless
        self.debug_port = int(debug_port)
        self.browser_path = browser_path
        self.auto_launch_browser = auto_launch_browser
        self.driver = None
        
        # 获取持久化目录（打包后EXE使用EXE所在目录，开发时使用脚本目录）
        persistent_dir = self._get_persistent_dir()
        
        self.cookies_file = os.path.join(persistent_dir, f"cookies_{shop_id}.pkl")
        if user_data_dir:
            self.user_data_dir = os.path.abspath(user_data_dir)
        else:
            # 使用持久化目录，保证"登录一次，后续复用登录态"
            self.user_data_dir = os.path.join(persistent_dir, "chromium_profile")
        
        logger.info(f"登录状态保存目录: {self.user_data_dir}")
    
    def _is_debug_port_open(self) -> bool:
        """检查远程调试端口是否已监听"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                return s.connect_ex(("127.0.0.1", self.debug_port)) == 0
        except Exception:
            return False
    
    def _wait_for_debug_port(self, timeout: float = 15.0) -> bool:
        """等待远程调试端口可用"""
        start = time.time()
        while time.time() - start < timeout:
            if self._is_debug_port_open():
                return True
            time.sleep(0.5)
        return False
    
    def ensure_debug_browser(self, open_url: Optional[str] = None) -> bool:
        """
        确保调试浏览器已启动（用于复用登录态）
        
        Returns:
            是否可用（端口已监听或已成功启动）
        """
        if self._is_debug_port_open():
            return True
        if not self.auto_launch_browser:
            return False
        return self._launch_chrome_debug(open_url=open_url)
    
    def _find_browser_executable(self) -> str:
        """自动寻找 Chromium / Chrome / Edge 可执行文件"""
        import platform
        
        if self.browser_path and os.path.exists(self.browser_path):
            return self.browser_path
        
        # 优先从 PATH 查找 (Chrome 优先)
        candidates_in_path = [
            "chrome",
            "chrome.exe",
            "chromium",
            "chromium.exe",
            "msedge",
            "msedge.exe",
        ]
        for name in candidates_in_path:
            p = shutil.which(name)
            if p and os.path.exists(p):
                return p
        
        system = platform.system()
        candidates = []
        
        if system == "Windows":
            # 获取环境变量路径
            local_app_data = os.environ.get('LOCALAPPDATA', '')
            program_files = os.environ.get('PROGRAMFILES', r'C:\Program Files')
            program_files_x86 = os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)')
            user_profile = os.environ.get('USERPROFILE', '')
            
            candidates.extend([
                # Google Chrome（优先）
                os.path.join(program_files, 'Google', 'Chrome', 'Application', 'chrome.exe'),
                os.path.join(program_files_x86, 'Google', 'Chrome', 'Application', 'chrome.exe'),
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                # Microsoft Edge（备选）
                os.path.join(program_files, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
                os.path.join(program_files_x86, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            ])
            
            # 用户目录下的浏览器 (Chrome 优先)
            if local_app_data:
                candidates.extend([
                    os.path.join(local_app_data, 'Google', 'Chrome', 'Application', 'chrome.exe'),
                    os.path.join(local_app_data, 'Chromium', 'Application', 'chrome.exe'),
                ])
            
            # Chromium
            candidates.extend([
                os.path.join(program_files, 'Chromium', 'Application', 'chrome.exe'),
                os.path.join(program_files_x86, 'Chromium', 'Application', 'chrome.exe'),
                r"C:\Program Files\Chromium\Application\chrome.exe",
                r"C:\Program Files (x86)\Chromium\Application\chrome.exe",
            ])
            
        elif system == "Darwin":  # macOS (Chrome 优先)
            candidates.extend([
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            ])
        else:  # Linux (Chrome 优先)
            candidates.extend([
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/chromium-browser",
                "/usr/bin/chromium",
                "/snap/bin/chromium",
                "/usr/bin/microsoft-edge",
            ])
        
        for p in candidates:
            if p and os.path.exists(p):
                logger.info(f"找到浏览器: {p}")
                return p
        
        # 打印调试信息
        logger.warning("未找到浏览器，已检查以下路径:")
        for p in candidates[:10]:  # 只打印前10个
            logger.warning(f"  - {p} (存在: {os.path.exists(p) if p else False})")
        
        return ""
        
    def _is_edge_browser(self) -> bool:
        """检测当前使用的是否是Edge浏览器"""
        browser_exe = self._find_browser_executable()
        if browser_exe:
            return 'edge' in browser_exe.lower() or 'msedge' in browser_exe.lower()
        return False
    
    def _init_driver(self) -> bool:
        """连接到已运行的浏览器（远程调试模式），如果未运行则尝试启动
        
        Returns:
            bool: 是否成功连接
        """
        try:
            from selenium import webdriver
            
            is_edge = self._is_edge_browser()
            logger.info(f"检测到浏览器类型: {'Edge' if is_edge else 'Chrome/Chromium'}")
            
            if is_edge:
                # 使用Edge
                from selenium.webdriver.edge.options import Options
                options = Options()
                options.add_experimental_option("debuggerAddress", f"127.0.0.1:{self.debug_port}")
                
                try:
                    self.driver = webdriver.Edge(options=options)
                    self.driver.implicitly_wait(10)
                    logger.info("成功连接到Edge浏览器（远程调试）")
                    return True
                except Exception as e:
                    logger.info(f"未能连接到现有Edge实例: {e}")
                    logger.info("尝试自动启动Edge...")
                    if self.ensure_debug_browser():
                        self._wait_for_debug_port(timeout=20)
                        self.driver = webdriver.Edge(options=options)
                        self.driver.implicitly_wait(10)
                        logger.info("成功启动并连接到Edge浏览器（远程调试）")
                        return True
                    else:
                        raise Exception("无法自动启动Edge浏览器")
            else:
                # 使用Chrome/Chromium
                from selenium.webdriver.chrome.options import Options
                options = Options()
                options.add_experimental_option("debuggerAddress", f"127.0.0.1:{self.debug_port}")
                
                try:
                    self.driver = webdriver.Chrome(options=options)
                    self.driver.implicitly_wait(10)
                    logger.info("成功连接到Chrome浏览器（远程调试）")
                    return True
                except Exception as e:
                    logger.info(f"未能连接到现有Chrome实例: {e}")
                    logger.info("尝试自动启动Chrome...")
                    if self.ensure_debug_browser():
                        self._wait_for_debug_port(timeout=20)
                        self.driver = webdriver.Chrome(options=options)
                        self.driver.implicitly_wait(10)
                        logger.info("成功启动并连接到Chrome浏览器（远程调试）")
                        return True
                    else:
                        raise Exception("无法自动启动Chrome浏览器")
            
        except Exception as e:
            logger.error(f"连接浏览器失败: {e}")
            logger.error("请尝试手动运行以下命令启动浏览器（远程调试模式）:")
            browser_exe = self._find_browser_executable()
            if os.name == 'nt':  # Windows
                logger.error(
                    f'"{browser_exe}" --remote-debugging-port={self.debug_port} --user-data-dir="{self.user_data_dir}"'
                )
            else:
                logger.error(
                    f'"{browser_exe}" --remote-debugging-port={self.debug_port} --user-data-dir="{self.user_data_dir}"'
                )
            return False

    def _launch_chrome_debug(self, open_url: Optional[str] = None) -> bool:
        """尝试启动浏览器调试模式（Chromium/Chrome/Edge）"""
        import subprocess
        import platform
        
        browser_exe = self._find_browser_executable()
        if not browser_exe:
            logger.error("未找到 Chromium/Chrome/Edge 可执行文件")
            return False
            
        try:
            # 创建用户数据目录
            os.makedirs(self.user_data_dir, exist_ok=True)
            logger.info(f"用户数据目录: {self.user_data_dir}")
                
            cmd = [
                browser_exe,
                f"--remote-debugging-port={self.debug_port}",
                f"--user-data-dir={self.user_data_dir}",
                "--no-first-run",
                "--no-default-browser-check",
            ]
            
            # 如果是 root 用户（仅Linux），必须添加 --no-sandbox 参数
            if platform.system() != "Windows":
                try:
                    if os.geteuid() == 0:
                        cmd.append("--no-sandbox")
                        cmd.append("--disable-dev-shm-usage")  # 配合 no-sandbox 使用
                        logger.warning("检测到以 root 用户运行，已添加 --no-sandbox 参数")
                except AttributeError:
                    pass  # Windows没有geteuid
            
            # 基础参数
            cmd.extend([
                "--disable-infobars",
                "--disable-session-crashed-bubble",
                "--no-default-browser-check",
                "--check-for-update-interval=604800",
                "--disable-extensions",
                "--test-type",  # 消除 unsupported flag 警告
                "--ignore-certificate-errors",
                "--disable-gpu",  # 某些环境下有助于稳定性
                "--no-first-run"
            ])

            # 尝试移除"Chrome正在受到自动测试软件的控制"提示
            # 注意：这需要通过 experimental_options 设置，但在启动命令行中
            # 我们可以尝试添加 --disable-blink-features=AutomationControlled
            cmd.append("--disable-blink-features=AutomationControlled")
            
            if open_url:
                cmd.append(open_url)
            
            logger.info(f"正在启动浏览器: {browser_exe}")
            logger.info(f"启动命令: {' '.join(cmd)}")
            
            # Windows下使用不同的启动方式
            if platform.system() == "Windows":
                # 使用 shell=False 并设置 creationflags 避免显示命令行窗口
                CREATE_NO_WINDOW = 0x08000000
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=CREATE_NO_WINDOW
                )
                logger.info(f"浏览器进程已启动，PID: {process.pid}")
            else:
                subprocess.Popen(cmd)
            
            # 等待端口可用
            logger.info(f"等待端口 {self.debug_port} 可用...")
            if self._wait_for_debug_port(timeout=30):
                logger.info("浏览器启动成功！")
                return True
            else:
                logger.error(f"等待端口 {self.debug_port} 超时")
                return False
                
        except Exception as e:
            logger.error(f"启动浏览器失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    
    def login_and_fetch(
        self,
        auto_login: bool = False,
        wait_for_login: bool = True,
        login_timeout: int = 600,
        dump_debug: bool = False,
        log_callback = None,
    ) -> List[GoodsItem]:
        """
        登录并抓取商品
        
        Args:
            auto_login: 保留参数(兼容旧版)，当前逻辑主要复用浏览器登录态
            wait_for_login: 检测到未登录时，是否等待用户在浏览器内完成登录
            login_timeout: 等待登录最大秒数
            dump_debug: 是否保存页面截图和HTML（用于排查页面结构）
            log_callback: 日志回调函数，用于输出日志到GUI
            
        Returns:
            商品列表
        """
        # 保存日志回调
        self._log_callback = log_callback
        if not self.driver:
            self._init_driver()
        
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        try:
            # 访问饿了么商家后台 - 商品管理页面
            # 正确的URL格式: https://melody.shop.ele.me/app/shop/{shop_id}/food#app.shop.food?path=management
            goods_url = f"{self.base_url}/app/shop/{self.shop_id}/food#app.shop.food?path=management"
            self._log(f"正在访问商品管理页面...")
            self.driver.get(goods_url)
            
            # 等待页面加载
            self._log("等待页面加载...")
            time.sleep(5)
            
            # 检测登录状态 - 先尝试加载已保存的 cookies
            need_login = self._need_login()
            self._log(f"登录状态检测: {'需要登录' if need_login else '已登录'}")
            
            # 如果需要登录，先尝试加载保存的 cookies
            if need_login and os.path.exists(self.cookies_file):
                self._log("尝试加载保存的 cookies...")
                if self.load_cookies():
                    self.driver.refresh()
                    time.sleep(3)
                    need_login = self._need_login()
                    if not need_login:
                        self._log("✓ 使用保存的 cookies 登录成功！")
            
            # 如果仍未登录，等待用户在已打开的浏览器中完成登录（只需第一次）
            if wait_for_login and need_login:
                self._log(f"⚠ 请在浏览器窗口中完成登录/扫码（最多等待 {login_timeout//60} 分钟）...")
                start = time.time()
                while time.time() - start < login_timeout:
                    time.sleep(3)
                    try:
                        if not self._need_login():
                            self._log("✓ 已检测到登录完成")
                            self.save_cookies()
                            break
                    except Exception:
                        pass
                else:
                    raise Exception(f"等待登录超时（{login_timeout}秒），请确认已完成登录")
            
            # 浏览器已登录，直接开始抓取
            self._log("✓ 浏览器已连接，开始抓取...")
            
            # 等待商品列表加载
            self._log("等待商品列表加载...")
            time.sleep(3)
            
            # 打印当前URL
            self._log(f"当前页面: {self.driver.title}")
            
            # 调试：保存页面截图和HTML
            if dump_debug:
                self.driver.save_screenshot("debug_screenshot.png")
                with open("debug_page.html", "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)
                self._log("已保存调试文件")
            
            # 抓取所有商品
            self._log("开始抓取异常商品...")
            all_goods = self._fetch_all_pages()
            
            # 抓取成功后保存 cookies
            self.save_cookies()
            self._log(f"✓ 抓取完成，共 {len(all_goods)} 个异常商品")
            
            return all_goods
            
        except Exception as e:
            logger.error(f"抓取失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def save_cookies(self):
        """保存当前浏览器的 cookies 到文件"""
        if not self.driver:
            return
        try:
            cookies = self.driver.get_cookies()
            os.makedirs(os.path.dirname(self.cookies_file), exist_ok=True) if os.path.dirname(self.cookies_file) else None
            with open(self.cookies_file, 'wb') as f:
                pickle.dump(cookies, f)
            logger.info(f"已保存 {len(cookies)} 个 cookies 到: {self.cookies_file}")
        except Exception as e:
            logger.warning(f"保存 cookies 失败: {e}")
    
    def load_cookies(self) -> bool:
        """从文件加载 cookies 到浏览器"""
        if not self.driver:
            return False
        if not os.path.exists(self.cookies_file):
            logger.info(f"Cookies 文件不存在: {self.cookies_file}")
            return False
        try:
            with open(self.cookies_file, 'rb') as f:
                cookies = pickle.load(f)
            
            # 先访问目标域名（cookies 需要在同域下添加）
            current_url = self.driver.current_url
            if 'ele.me' not in current_url:
                self.driver.get(self.base_url)
                time.sleep(2)
            
            for cookie in cookies:
                try:
                    # 移除可能导致问题的字段
                    for key in ['expiry', 'sameSite']:
                        if key in cookie:
                            del cookie[key]
                    self.driver.add_cookie(cookie)
                except Exception as e:
                    logger.debug(f"添加 cookie 失败: {e}")
            
            logger.info(f"已加载 {len(cookies)} 个 cookies")
            return True
        except Exception as e:
            logger.warning(f"加载 cookies 失败: {e}")
            return False
    
    def _need_login(self) -> bool:
        """检查是否需要登录"""
        try:
            # 先用URL判断（比全文关键字更可靠）
            url = (self.driver.current_url or "").lower()
            login_url_keywords = [
                "login", "signin", "passport", "oauth", "auth",
                "account.taobao", "login.taobao", "login.ele.me",
                "account.ele.me", "uac.ele.me"
            ]
            if any(k in url for k in login_url_keywords):
                return True

            # 检查是否有登录相关元素
            page_source = self.driver.page_source
            # 饿了么商家后台登录相关的关键词
            login_indicators = [
                "请登录", "扫码登录", "login", "signin",
                "account.taobao", "login.taobao",
                "请使用手机号登录", "获取验证码", "密码登录"
            ]
            
            # 页面内包含登录关键词，且不是已经登录的状态
            for indicator in login_indicators:
                if indicator in page_source:
                    # 已登录的页面通常包含这些元素
                    logged_in_indicators = ["商品管理", "门店管理", "订单", "我的店铺", "退出登录"]
                    if not any(li in page_source for li in logged_in_indicators):
                        return True
            
            return False
        except:
            return True
    
    def switch_shop(self, shop_keyword: str, timeout: int = 30) -> dict:
        """
        切换到指定门店
        
        根据实际DOM结构流程：
        1. 点击 shopSwitcher 中的 clk-area 打开下拉菜单
        2. 在搜索框（placeholder="搜索店铺名称/ID"）中输入门店名称关键字
        3. 点击 li.cook-cascader-menu-item 中"营业中"的门店
        
        Args:
            shop_keyword: 门店名称关键字（用于搜索，如"闵行维璟"）
            timeout: 超时时间（秒）
            
        Returns:
            dict: {
                'success': bool,
                'shop_name': str,  # 实际切换到的门店名称
                'is_open': bool,   # 是否营业中
                'message': str     # 结果消息
            }
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        
        result = {
            'success': False,
            'shop_name': '',
            'is_open': False,
            'message': ''
        }
        
        if not self.driver:
            result['message'] = '浏览器未初始化'
            return result
        
        try:
            self._log(f"正在切换到门店: {shop_keyword}")
            
            # 先按ESC关闭可能已打开的下拉菜单
            try:
                body = self.driver.find_element(By.TAG_NAME, "body")
                body.send_keys(Keys.ESCAPE)
                time.sleep(1)
            except:
                pass
            
            # ========== 步骤1: 点击门店切换器打开下拉菜单 ==========
            js_click_dropdown = '''
                // 优先方法: 查找 shopSwitcher 中的 clk-area
                var switcher = document.querySelector('[class*="shopSwitcher"]');
                if (switcher) {
                    var clkArea = switcher.querySelector('[class*="clk-area"]');
                    if (clkArea) {
                        clkArea.click();
                        return {success: true, text: clkArea.innerText.substring(0, 50), method: 'clk-area'};
                    }
                    
                    var shopName = switcher.querySelector('[class*="shop-name"]');
                    if (shopName) {
                        shopName.click();
                        return {success: true, text: shopName.innerText.substring(0, 50), method: 'shop-name'};
                    }
                    
                    switcher.click();
                    return {success: true, text: switcher.innerText.substring(0, 50), method: 'switcher'};
                }
                
                // 备用方法: 查找顶部栏中的门店元素
                var allElements = document.querySelectorAll('*');
                for (var i = 0; i < allElements.length; i++) {
                    var el = allElements[i];
                    var text = (el.innerText || '').trim();
                    var rect = el.getBoundingClientRect();
                    var cls = (typeof el.className === 'string') ? el.className : '';
                    
                    if (rect.top >= 0 && rect.top < 80 &&
                        el.offsetWidth > 150 && el.offsetWidth < 400 &&
                        (text.indexOf('手打') !== -1 || text.indexOf('手作') !== -1) &&
                        text.indexOf('账号') === -1 &&
                        (cls.indexOf('clk') !== -1 || window.getComputedStyle(el).cursor === 'pointer')) {
                        
                        el.click();
                        return {success: true, text: text.substring(0, 50), method: 'fallback'};
                    }
                }
                
                return {success: false, message: '未找到门店切换器'};
            '''
            
            click_result = self.driver.execute_script(js_click_dropdown)
            if not click_result or not click_result.get('success'):
                result['message'] = '未找到门店下拉按钮'
                self._log(f"   步骤1: ✗ {result['message']}")
                return result
            
            self._log(f"   步骤1: ✓ 已点击下拉按钮 ({click_result.get('method', '')})")
            time.sleep(1.5)
            
            # ========== 步骤2: 在搜索框中输入关键字 ==========
            search_input = None
            try:
                # 优先使用 placeholder 精确匹配
                selectors = [
                    'input[placeholder*="搜索店铺"]',
                    'input[placeholder*="搜索"]',
                    'input[placeholder*="店铺"]',
                ]
                for selector in selectors:
                    try:
                        inputs = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        for inp in inputs:
                            if inp.is_displayed() and inp.is_enabled():
                                rect = self.driver.execute_script(
                                    "var r = arguments[0].getBoundingClientRect(); return {top: r.top};",
                                    inp
                                )
                                if rect['top'] > 30 and rect['top'] < 200:
                                    search_input = inp
                                    break
                    except:
                        continue
                    if search_input:
                        break
            except Exception as e:
                self._log(f"   查找搜索框出错: {e}")
            
            if search_input:
                search_input.clear()
                search_input.send_keys(shop_keyword)
                self._log(f"   步骤2: ✓ 已输入搜索关键字: {shop_keyword}")
            else:
                result['message'] = '未找到搜索框'
                self._log(f"   步骤2: ✗ {result['message']}")
                return result
            
            # ========== 步骤3: 点击搜索结果中"营业中"的门店 ==========
            # 使用精确选择器: li.cook-cascader-menu-item，带重试机制
            js_click_shop = f'''
                var items = document.querySelectorAll('li.cook-cascader-menu-item');
                var candidates = [];
                
                for (var i = 0; i < items.length; i++) {{
                    var item = items[i];
                    var text = (item.innerText || '').trim();
                    
                    if (text.indexOf('{shop_keyword}') === -1) continue;
                    
                    var isOpen = text.indexOf('营业中') !== -1;
                    var isClosed = text.indexOf('休息中') !== -1 || 
                                  text.indexOf('已下线') !== -1 ||
                                  text.indexOf('打烊') !== -1;
                    
                    var shopName = text.split('\\n')[0];
                    
                    candidates.push({{
                        el: item,
                        text: text,
                        shopName: shopName,
                        isOpen: isOpen,
                        isClosed: isClosed,
                        priority: isOpen ? 1 : (isClosed ? 3 : 2)
                    }});
                }}
                
                // 按优先级排序（营业中优先）
                candidates.sort(function(a, b) {{ return a.priority - b.priority; }});
                
                // 点击营业中的门店
                for (var i = 0; i < candidates.length; i++) {{
                    var c = candidates[i];
                    if (c.isOpen) {{
                        c.el.click();
                        return {{
                            success: true,
                            shop_name: c.shopName,
                            is_open: true,
                            total_found: candidates.length
                        }};
                    }}
                }}
                
                // 没有营业中的，返回信息
                if (candidates.length > 0) {{
                    var first = candidates[0];
                    return {{
                        success: false,
                        shop_name: first.shopName,
                        is_open: false,
                        is_closed: first.isClosed,
                        message: first.isClosed ? '门店休息中/已下线' : '未找到营业中的门店',
                        total_found: candidates.length
                    }};
                }}
                
                return {{
                    success: false,
                    message: '未找到匹配的门店',
                    total_found: 0
                }};
            '''
            
            # 带重试的等待搜索结果
            shop_result = None
            for retry in range(5):  # 最多等待5秒
                time.sleep(1)
                shop_result = self.driver.execute_script(js_click_shop)
                if shop_result and (shop_result.get('success') or shop_result.get('total_found', 0) > 0):
                    break
            
            if shop_result and shop_result.get('success'):
                result['success'] = True
                result['shop_name'] = shop_result.get('shop_name', '')
                result['is_open'] = True
                result['message'] = f"成功切换到: {result['shop_name']}"
                self._log(f"   步骤3: ✓ {result['message']}")
                time.sleep(2)  # 等待页面刷新
            else:
                result['shop_name'] = shop_result.get('shop_name', '') if shop_result else ''
                result['is_open'] = shop_result.get('is_open', False) if shop_result else False
                result['message'] = shop_result.get('message', '切换门店失败') if shop_result else '切换门店失败'
                self._log(f"   步骤3: ✗ {result['message']}")
                
                # 关闭下拉菜单
                try:
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                except:
                    try:
                        self.driver.find_element(By.TAG_NAME, 'body').click()
                    except:
                        pass
            
            return result
            
        except Exception as e:
            result['message'] = f'切换门店出错: {e}'
            self._log(f"   ✗ {result['message']}")
            import traceback
            self._log(f"   {traceback.format_exc()}")
            return result
    
    def get_current_shop_name(self) -> str:
        """获取当前门店名称"""
        if not self.driver:
            return ""
        
        try:
            js_get_shop = '''
                // 查找右上角的门店名称
                var allElements = document.querySelectorAll('*');
                for (var i = 0; i < allElements.length; i++) {
                    var el = allElements[i];
                    var text = (el.innerText || '').trim();
                    var rect = el.getBoundingClientRect();
                    var cls = (typeof el.className === 'string') ? el.className : '';
                    
                    // 顶部栏中的门店名称
                    if (rect.top > 0 && rect.top < 80 && rect.left > 300 &&
                        el.offsetWidth > 100 && el.offsetWidth < 400 &&
                        el.offsetHeight > 20 && el.offsetHeight < 60 &&
                        (text.indexOf('手打') !== -1 || text.indexOf('手作') !== -1) &&
                        text.indexOf('账号') === -1 &&
                        text.length < 50) {
                        return text.split('\\n')[0];
                    }
                }
                return '';
            '''
            return self.driver.execute_script(js_get_shop) or ""
        except:
            return ""
    
    def _click_menu_item(self, menu_name: str) -> bool:
        """点击左侧菜单项"""
        from selenium.webdriver.common.by import By
        
        try:
            # 使用 JavaScript 点击菜单
            js_script = f'''
                // 查找包含指定文字的菜单项
                var menuItems = document.querySelectorAll('[class*="menu-item"], [class*="menuItem"], [class*="cook-menu-item"], li');
                for (var i = 0; i < menuItems.length; i++) {{
                    var item = menuItems[i];
                    var text = (item.innerText || item.textContent || '').trim();
                    if (text === '{menu_name}' || text.indexOf('{menu_name}') === 0) {{
                        item.click();
                        return true;
                    }}
                }}
                
                // 备用：查找任何包含该文字的可点击元素
                var allElements = document.querySelectorAll('a, div, span');
                for (var i = 0; i < allElements.length; i++) {{
                    var el = allElements[i];
                    var text = (el.innerText || el.textContent || '').trim();
                    if (text === '{menu_name}') {{
                        el.click();
                        return true;
                    }}
                }}
                
                return false;
            '''
            result = self.driver.execute_script(js_script)
            if result:
                self._log(f"   ✓ 已点击菜单: {menu_name}")
                return True
            return False
        except Exception as e:
            return False
    
    def _switch_to_goods_iframe(self) -> bool:
        """切换到商品管理的iframe"""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        try:
            # 首先切回主文档
            self.driver.switch_to.default_content()
            
            # 尝试多种方式找到商品管理iframe
            iframe_selectors = [
                ("id", "app_shop_food"),  # 饿了么商家后台的商品管理iframe
                ("css", "iframe[src*='goods-manage']"),
                ("css", "iframe[src*='napos-goods']"),
                ("css", "iframe[id*='food']"),
                ("css", "iframe[id*='goods']"),
            ]
            
            for method, selector in iframe_selectors:
                try:
                    if method == "id":
                        iframe = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.ID, selector))
                        )
                    else:
                        iframe = WebDriverWait(self.driver, 3).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                    
                    if iframe:
                        self.driver.switch_to.frame(iframe)
                        self._log(f"✓ 已切换到iframe: {selector}")
                        time.sleep(1)  # 等待iframe内容加载
                        return True
                        
                except Exception as e:
                    continue
            
            # 如果上面都没找到，尝试直接用JavaScript获取
            try:
                iframe_info = self.driver.execute_script('''
                    var iframes = document.querySelectorAll('iframe');
                    var result = [];
                    for (var i = 0; i < iframes.length; i++) {
                        var iframe = iframes[i];
                        result.push({
                            id: iframe.id,
                            src: iframe.src,
                            visible: iframe.offsetWidth > 0 && iframe.offsetHeight > 0
                        });
                    }
                    return result;
                ''')
                
                self._log(f"   页面中发现 {len(iframe_info)} 个iframe:")
                for info in iframe_info:
                    visible_str = "可见" if info.get('visible') else "隐藏"
                    self._log(f"   - id=\"{info.get('id', '')}\" src=\"{info.get('src', '')[:50]}...\" [{visible_str}]")
                
                # 尝试切换到第一个可见的、包含goods相关URL的iframe
                for info in iframe_info:
                    if info.get('visible') and ('goods' in info.get('src', '').lower() or 'food' in info.get('id', '').lower()):
                        iframe_id = info.get('id')
                        if iframe_id:
                            iframe = self.driver.find_element(By.ID, iframe_id)
                            self.driver.switch_to.frame(iframe)
                            self._log(f"✓ 已切换到iframe (通过JS): {iframe_id}")
                            time.sleep(1)
                            return True
                
            except Exception as e:
                self._log(f"   获取iframe信息出错: {e}")
            
            # 没找到iframe，尝试重新导航到商品管理页面
            self._log("⚠ 未找到商品管理iframe，尝试重新导航...")
            
            try:
                goods_url = f"{self.base_url}/app/shop/{self.shop_id}/food#app.shop.food?path=management"
                self.driver.get(goods_url)
                time.sleep(5)  # 等待页面加载
                
                # 再次尝试找iframe
                for method, selector in iframe_selectors:
                    try:
                        if method == "id":
                            iframe = WebDriverWait(self.driver, 5).until(
                                EC.presence_of_element_located((By.ID, selector))
                            )
                        else:
                            iframe = WebDriverWait(self.driver, 3).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                            )
                        
                        if iframe:
                            self.driver.switch_to.frame(iframe)
                            self._log(f"✓ 重新导航后已切换到iframe: {selector}")
                            time.sleep(1)
                            return True
                    except:
                        continue
                        
            except Exception as nav_e:
                self._log(f"   重新导航失败: {nav_e}")
            
            self._log("⚠ 仍未找到商品管理iframe")
            return False
            
        except Exception as e:
            self._log(f"   切换iframe出错: {e}")
            return False
    
    def _fetch_all_pages(self) -> List[GoodsItem]:
        """抓取所有页面的商品 - 专门获取已下架和已售罄的商品"""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        all_goods = []
        
        # 设置隐式等待为较短时间，避免卡住
        self.driver.implicitly_wait(2)
        
        # 切换到商品管理 iframe
        iframe_switched = self._switch_to_goods_iframe()
        if not iframe_switched:
            self._log("⚠ 未能切换到商品管理iframe，尝试在主页面操作...")
        
        # 保存调试HTML（用于分析页面结构）
        try:
            debug_html_path = "debug_tabs_page.html"
            with open(debug_html_path, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            self._log(f"📄 已保存页面HTML到 {debug_html_path}")
        except Exception as e:
            self._log(f"   保存调试HTML失败: {e}")
        
        # 先分析页面上的标签结构
        self._analyze_tab_structure()
        
        # 要抓取的标签：已下架、已售罄
        tabs_to_fetch = [
            ("已下架", "OFF_SALE"),
            ("已售罄", "SOLD_OUT"),
        ]
        
        for tab_name, status_code in tabs_to_fetch:
            self._log(f"📂 正在点击 '{tab_name}' 标签...")
            
            try:
                tab_clicked = self._click_tab(tab_name)
                
                if tab_clicked:
                    self._log(f"   ✓ 成功点击 '{tab_name}'")
                    time.sleep(2)
                else:
                    self._log(f"   ⚠ 未能点击 '{tab_name}'，跳过")
                    continue
                
                # 抓取该标签下的所有商品
                goods_in_tab = self._fetch_goods_in_current_tab(status_code)
                all_goods.extend(goods_in_tab)
                self._log(f"   → '{tab_name}' 抓取到 {len(goods_in_tab)} 个商品")
                
            except Exception as e:
                self._log(f"   ✗ 抓取 '{tab_name}' 失败: {e}")
        
        # 切换回主文档
        try:
            self.driver.switch_to.default_content()
        except:
            pass
        
        # 恢复默认等待
        self.driver.implicitly_wait(10)
        
        return all_goods
    
    def _analyze_tab_structure(self):
        """分析页面上的标签结构，输出调试信息"""
        try:
            # 使用 JavaScript 分析页面上所有可能的标签元素
            js_analyze = '''
                var result = [];
                
                // 查找所有包含"已下架"、"已售罄"、"出售中"、"全部"文字的元素
                var keywords = ["已下架", "已售罄", "出售中", "全部", "待审核"];
                var allElements = document.querySelectorAll('*');
                
                for (var i = 0; i < allElements.length; i++) {
                    var el = allElements[i];
                    var text = el.innerText || el.textContent || '';
                    
                    // 只检查直接文本内容（避免父元素重复）
                    var directText = '';
                    for (var j = 0; j < el.childNodes.length; j++) {
                        if (el.childNodes[j].nodeType === 3) {
                            directText += el.childNodes[j].textContent;
                        }
                    }
                    
                    for (var k = 0; k < keywords.length; k++) {
                        if (text.indexOf(keywords[k]) !== -1 && text.length < 50) {
                            var info = {
                                tag: el.tagName,
                                class: el.className,
                                id: el.id,
                                text: text.substring(0, 30),
                                clickable: el.onclick !== null || el.tagName === 'BUTTON' || el.getAttribute('role') === 'tab'
                            };
                            // 避免重复
                            var isDup = false;
                            for (var m = 0; m < result.length; m++) {
                                if (result[m].class === info.class && result[m].text === info.text) {
                                    isDup = true;
                                    break;
                                }
                            }
                            if (!isDup && info.class) {
                                result.push(info);
                            }
                            break;
                        }
                    }
                }
                
                return result.slice(0, 20);  // 最多返回20个
            '''
            
            elements = self.driver.execute_script(js_analyze)
            
            if elements:
                self._log(f"🔍 发现 {len(elements)} 个可能的标签元素:")
                for el in elements[:10]:  # 只显示前10个
                    self._log(f"   - <{el.get('tag', '?')}> class=\"{el.get('class', '')[:50]}\" text=\"{el.get('text', '')}\"")
            else:
                self._log("🔍 未发现包含标签关键词的元素")
                
        except Exception as e:
            self._log(f"   分析标签结构出错: {e}")
    
    def _click_tab(self, tab_name: str) -> bool:
        """点击指定标签页 - 支持多种UI框架"""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.action_chains import ActionChains
        
        try:
            # 方法1: 通用JS方法 - 查找所有包含目标文字的可点击元素
            js_script = f'''
                var targetText = '{tab_name}';
                
                // 策略1: 查找各种tabs组件的tab按钮
                var tabSelectors = [
                    '.ant-tabs-tab-btn',      // Ant Design
                    '.cook-tabs-tab-btn',     // Cook UI (饿了么)
                    '[role="tab"]',           // ARIA标准
                    '.imsdk-tabs-tab',        // imsdk
                    '[class*="tabs-tab"]',    // 通用
                    '[class*="tab-btn"]',     // 通用
                    '[class*="TabItem"]',     // 驼峰命名
                    '[class*="tab-item"]',    // 短横线命名
                ];
                
                for (var s = 0; s < tabSelectors.length; s++) {{
                    var tabs = document.querySelectorAll(tabSelectors[s]);
                    for (var i = 0; i < tabs.length; i++) {{
                        var tab = tabs[i];
                        var text = (tab.innerText || tab.textContent || '').trim();
                        if (text.indexOf(targetText) === 0 || text === targetText) {{
                            tab.click();
                            return 'selector:' + tabSelectors[s];
                        }}
                    }}
                }}
                
                // 策略2: 查找任意包含目标文字的可点击元素
                var clickableSelectors = ['div', 'span', 'a', 'button', 'li'];
                for (var c = 0; c < clickableSelectors.length; c++) {{
                    var elements = document.querySelectorAll(clickableSelectors[c]);
                    for (var i = 0; i < elements.length; i++) {{
                        var el = elements[i];
                        var text = (el.innerText || el.textContent || '').trim();
                        // 精确匹配或以目标文字开头（如"已下架3"）
                        if ((text.indexOf(targetText) === 0 && text.length < targetText.length + 10) ||
                            text === targetText) {{
                            // 检查是否可见
                            var rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {{
                                // 检查class是否像标签
                                var cls = (typeof el.className === 'string') ? el.className : (el.className.baseVal || '');
                                if (cls.indexOf('tab') !== -1 || cls.indexOf('Tab') !== -1 ||
                                    cls.indexOf('panel') !== -1 || cls.indexOf('Panel') !== -1 ||
                                    el.getAttribute('role') === 'tab') {{
                                    el.click();
                                    return 'element:' + clickableSelectors[c] + '.' + cls.substring(0, 30);
                                }}
                            }}
                        }}
                    }}
                }}
                
                // 策略3: 最后尝试 - 查找任何包含文字的元素并点击
                var allEls = document.querySelectorAll('*');
                for (var i = 0; i < allEls.length; i++) {{
                    var el = allEls[i];
                    // 只检查直接文本
                    var directText = '';
                    for (var j = 0; j < el.childNodes.length; j++) {{
                        if (el.childNodes[j].nodeType === 3) {{
                            directText += el.childNodes[j].textContent.trim();
                        }}
                    }}
                    if (directText === targetText || directText.indexOf(targetText) === 0 && directText.length < targetText.length + 5) {{
                        var rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {{
                            el.click();
                            return 'direct:' + el.tagName + '.' + (el.className || '').substring(0, 30);
                        }}
                    }}
                }}
                
                return false;
            '''
            result = self.driver.execute_script(js_script)
            if result:
                self._log(f"   ✓ JS点击成功: {result}")
                return True
            
            self._log(f"   JS方法未找到目标，尝试XPath...")
            
            # 方法2: XPath查找（更宽泛）
            selectors = [
                # 各种tabs框架
                f"//*[contains(@class, 'tabs-tab')][contains(., '{tab_name}')]",
                f"//*[contains(@class, 'tab-btn')][contains(., '{tab_name}')]",
                f"//*[@role='tab'][contains(., '{tab_name}')]",
                # 包含panelTitle的div
                f"//div[contains(@class, 'panelTitle')][contains(., '{tab_name}')]",
                f"//div[contains(@class, 'Panel')][contains(., '{tab_name}')]",
                # 通用：任何包含文字的span/div且class含tab
                f"//span[contains(., '{tab_name}')][contains(@class, 'tab') or contains(@class, 'Tab')]",
                f"//div[contains(., '{tab_name}')][contains(@class, 'tab') or contains(@class, 'Tab')]",
                # 最宽泛：直接包含文字的元素
                f"//*[text()='{tab_name}']",
                f"//*[starts-with(text(), '{tab_name}')]",
            ]
            
            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    if elements:
                        self._log(f"   选择器 {selector[:60]}... 找到 {len(elements)} 个")
                    for elem in elements:
                        if elem.is_displayed():
                            try:
                                # 滚动到元素
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                                time.sleep(0.3)
                                elem.click()
                                self._log(f"   ✓ XPath点击成功")
                                return True
                            except:
                                try:
                                    ActionChains(self.driver).move_to_element(elem).click().perform()
                                    self._log(f"   ✓ ActionChains点击成功")
                                    return True
                                except:
                                    continue
                except Exception as e:
                    continue
            
            self._log(f"   ✗ 所有方法都未能找到 '{tab_name}' 标签")
            return False
            
        except Exception as e:
            self._log(f"   点击标签出错: {e}")
            return False
    
    def _fetch_goods_in_current_tab(self, status_code: str) -> List[GoodsItem]:
        """抓取当前标签下的所有商品 - 需要遍历所有分类"""
        all_goods = []
        
        # 获取左侧所有分类
        categories = self._get_all_categories()
        
        if not categories:
            # 如果没有分类，直接抓取当前页面
            self._log(f"   未发现分类列表，直接抓取当前页...")
            return self._fetch_goods_in_category(status_code)
        
        self._log(f"   发现 {len(categories)} 个分类")
        
        # 遍历每个分类
        for idx, (cat_name, cat_count) in enumerate(categories):
            if cat_count == 0:
                continue  # 跳过没有商品的分类
                
            self._log(f"   📁 [{idx+1}/{len(categories)}] 分类: {cat_name} ({cat_count}个)")
            
            # 点击分类
            if self._click_category(idx):
                time.sleep(1)
                
                # 抓取该分类下的商品
                goods_in_category = self._fetch_goods_in_category(status_code)
                
                # 去重（根据商品名称）
                existing_names = {g.goods_name for g in all_goods}
                new_goods = [g for g in goods_in_category if g.goods_name not in existing_names]
                
                all_goods.extend(new_goods)
                self._log(f"      → 抓取到 {len(new_goods)} 个商品")
        
        return all_goods
    
    def _get_all_categories(self) -> list:
        """获取左侧所有分类名称和商品数量"""
        try:
            js_script = '''
                var result = [];
                // 查找分类项 - 饿了么商家后台的分类列表
                var selectors = [
                    '[class*="groupItem__"]',
                    '[class*="categoryItem"]',
                    '[class*="category-item"]',
                    '[class*="menu-item"]',
                ];
                
                for (var s = 0; s < selectors.length; s++) {
                    var items = document.querySelectorAll(selectors[s]);
                    if (items.length > 0) {
                        for (var i = 0; i < items.length; i++) {
                            var item = items[i];
                            var text = (item.innerText || item.textContent || '').trim();
                            // 解析分类名和数量，如 "特色黑糖珍珠系列(1)"
                            var match = text.match(/^(.+?)\\s*[\\(（](\\d+)[\\)）]$/);
                            if (match) {
                                result.push({name: match[1], count: parseInt(match[2])});
                            } else if (text && text.length < 30) {
                                result.push({name: text, count: 0});
                            }
                        }
                        break;  // 找到就停止
                    }
                }
                return result;
            '''
            categories = self.driver.execute_script(js_script)
            
            if categories:
                return [(c['name'], c['count']) for c in categories]
            return []
            
        except Exception as e:
            self._log(f"   获取分类列表出错: {e}")
            return []
    
    def _click_category(self, index: int) -> bool:
        """点击指定索引的分类"""
        try:
            js_script = f'''
                var selectors = [
                    '[class*="groupItem__"]',
                    '[class*="categoryItem"]',
                    '[class*="category-item"]',
                    '[class*="menu-item"]',
                ];
                
                for (var s = 0; s < selectors.length; s++) {{
                    var items = document.querySelectorAll(selectors[s]);
                    if (items.length > {index}) {{
                        items[{index}].click();
                        return true;
                    }}
                }}
                return false;
            '''
            return self.driver.execute_script(js_script)
        except Exception as e:
            return False
    
    def _fetch_goods_in_category(self, status_code: str) -> List[GoodsItem]:
        """抓取当前分类下的所有商品（处理分页）"""
        all_goods = []
        page = 1
        
        while True:
            time.sleep(1)
            
            # 抓取当前页商品
            goods_on_page = self._parse_goods_from_page(status_code)
            
            if not goods_on_page:
                break
            
            all_goods.extend(goods_on_page)
            
            # 检查是否有下一页
            if not self._goto_next_page():
                break
            
            page += 1
            time.sleep(1)
            
            if page > 50:
                break
        
        return all_goods
    
    def _parse_goods_from_page(self, status_code: str = None) -> List[GoodsItem]:
        """解析当前页面的商品数据 - 针对饿了么商家后台"""
        from selenium.webdriver.common.by import By
        import re
        
        goods_list = []
        
        try:
            # 饿了么商家后台的商品行选择器（优先级从高到低）
            selectors = [
                # 精确匹配：商品行
                "[class*='tableRow__']",
                "[class*='style_tableRow']",
                # Ant Design 表格行
                "div[id][class*='Row']",  # 带id的Row（通常是商品）
                # 通用
                "[class*='goodsRow']",
                "[class*='goods-item']",
            ]
            
            rows = []
            
            for selector in selectors:
                try:
                    found = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if found:
                        # 过滤：必须包含价格或库存信息
                        valid_rows = []
                        for r in found:
                            text = r.text or ""
                            # 检查是否是商品行（包含价格和商品相关信息）
                            if len(text) > 20 and ('¥' in text or '库存' in text):
                                valid_rows.append(r)
                        
                        if valid_rows:
                            rows = valid_rows
                            self._log(f"      使用选择器: {selector}")
                            break
                except:
                    continue
            
            self._log(f"      找到 {len(rows)} 个商品行")
            
            for row in rows:
                try:
                    goods = self._parse_single_row(row, status_code)
                    if goods:
                        goods_list.append(goods)
                        self._log(f"      → {goods.goods_name}")
                except Exception as e:
                    continue
            
        except Exception as e:
            self._log(f"      解析商品失败: {e}")
        
        return goods_list
    
    def _parse_single_row(self, row, status_code: str = None) -> Optional[GoodsItem]:
        """解析单个商品行 - 针对饿了么商家后台"""
        from selenium.webdriver.common.by import By
        
        try:
            text = row.text
            if not text or len(text) < 5:
                return None
            
            # 尝试找到商品名称 - 饿了么后台特定选择器
            name = ""
            name_selectors = [
                # 饿了么后台精确选择器
                "[class*='goodsComNameDisplay']",
                "[class*='goodsTitleCom'] span",
                "[class*='goodsDetail'] [class*='name']",
                "[class*='goodsName']",
                # 通用选择器
                "[class*='name']",
                "[class*='title']",
                "[class*='Name']",
                "[class*='Title']",
            ]
            for sel in name_selectors:
                try:
                    name_elem = row.find_element(By.CSS_SELECTOR, sel)
                    name = name_elem.text.strip()
                    if name and len(name) > 2:
                        break
                except:
                    continue
            
            if not name:
                # 从文本中提取（跳过常见的非商品名文本）
                lines = text.split('\n')
                skip_keywords = ['¥', '库存', '月售', '编辑', '删除', '促销', '上架', '下架', '打包费']
                for line in lines:
                    line = line.strip()
                    if line and len(line) > 2 and not any(kw in line for kw in skip_keywords) and not line.isdigit():
                        name = line
                        break
            
            if not name:
                return None
            
            # 解析价格
            price = 0.0
            try:
                import re
                price_match = re.search(r'[¥￥]?\s*(\d+\.?\d*)', text)
                if price_match:
                    price = float(price_match.group(1))
            except:
                pass
            
            # 解析库存
            stock = 0
            try:
                import re
                stock_match = re.search(r'库存[:\s]*(\d+)', text)
                if stock_match:
                    stock = int(stock_match.group(1))
            except:
                pass
            
            # 使用传入的状态码，或从页面解析
            status = status_code if status_code else "在售"
            status_text_map = {
                "OFF_SALE": "已下架",
                "SOLD_OUT": "已售罄",
                "OUT_OF_STOCK": "缺货",
                "PAUSE": "暂停售卖",
                "NO_DELIVERY": "单点不送",
            }
            status_text = status_text_map.get(status, "在售")
            
            # 如果没有传入状态码，尝试从文本解析
            if not status_code:
                status_keywords = {
                    "已下架": ("已下架", "OFF_SALE"),
                    "下架": ("已下架", "OFF_SALE"),
                    "售罄": ("已售罄", "SOLD_OUT"),
                    "已售罄": ("已售罄", "SOLD_OUT"),
                    "缺货": ("缺货", "OUT_OF_STOCK"),
                    "暂停": ("暂停售卖", "PAUSE"),
                    "单点不送": ("单点不送", "NO_DELIVERY"),
                }
                
                for keyword, (status_txt, status_cd) in status_keywords.items():
                    if keyword in text:
                        status_text = status_txt
                        status = status_cd
                        break
            
            return GoodsItem(
                goods_id="",
                goods_name=name,
                category="",
                price=price,
                original_price=price,
                stock=stock,
                status=status,
                status_text=status_text
            )
            
        except Exception as e:
            logger.debug(f"解析行数据失败: {e}")
            return None
    
    def _goto_next_page(self) -> bool:
        """翻到下一页"""
        from selenium.webdriver.common.by import By
        from selenium.common.exceptions import NoSuchElementException
        
        try:
            # 尝试找到下一页按钮
            next_selectors = [
                ".ant-pagination-next:not(.ant-pagination-disabled)",
                "li[title='下一页']:not(.ant-pagination-disabled)",
                "[class*='next']:not([class*='disabled'])",
                "button[aria-label='next page']",
            ]
            
            for selector in next_selectors:
                try:
                    next_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if next_btn and next_btn.is_enabled():
                        next_btn.click()
                        return True
                except NoSuchElementException:
                    continue
                except:
                    continue
            
            return False
            
        except Exception as e:
            logger.debug(f"翻页失败: {e}")
            return False
    
    def get_statistics(self, goods_list: List[GoodsItem]) -> Dict:
        """获取统计信息"""
        stats = {
            "total": len(goods_list),
            "on_sale": 0,
            "off_sale": 0,
            "sold_out": 0,
            "out_of_stock": 0,
            "pause": 0,
            "other": 0,
        }
        
        for goods in goods_list:
            status = goods.status
            if status in ["在售", "ON_SALE"]:
                stats["on_sale"] += 1
            elif status in ["已下架", "OFF_SALE"]:
                stats["off_sale"] += 1
            elif status in ["已售罄", "SOLD_OUT"]:
                stats["sold_out"] += 1
            elif status in ["缺货", "OUT_OF_STOCK"]:
                stats["out_of_stock"] += 1
            elif status in ["暂停售卖", "PAUSE"]:
                stats["pause"] += 1
            else:
                stats["other"] += 1
        
        return stats
    
    def get_problematic_goods(self, goods_list: List[GoodsItem]) -> Dict[str, List[GoodsItem]]:
        """获取问题商品"""
        result = {
            "已下架": [],
            "已售罄": [],
            "缺货": [],
            "暂停售卖": [],
        }
        
        for goods in goods_list:
            if goods.status in ["已下架", "OFF_SALE"]:
                result["已下架"].append(goods)
            elif goods.status in ["已售罄", "SOLD_OUT"]:
                result["已售罄"].append(goods)
            elif goods.status in ["缺货", "OUT_OF_STOCK"]:
                result["缺货"].append(goods)
            elif goods.status in ["暂停售卖", "PAUSE"]:
                result["暂停售卖"].append(goods)
        
        return result
    
    def close(self):
        """关闭浏览器"""
        if self.driver:
            self.driver.quit()
            self.driver = None
    
    @staticmethod
    def format_wecom_message(
        shop_name: str,
        off_sale_goods: List[GoodsItem],
        sold_out_goods: List[GoodsItem],
        style: str = "elegant"
    ) -> str:
        """
        格式化精美的企业微信机器人消息
        
        Args:
            shop_name: 门店名称
            off_sale_goods: 已下架商品列表
            sold_out_goods: 已售罄商品列表
            style: 风格 ("elegant"=精简优雅, "detailed"=详细)
        
        Returns:
            格式化后的消息文本
        """
        now = datetime.now().strftime("%m-%d %H:%M")
        
        # 统计
        off_count = len(off_sale_goods)
        sold_count = len(sold_out_goods)
        total = off_count + sold_count
        
        # 如果没有异常商品
        if total == 0:
            return f"✅ 【{shop_name}】\n⏰ {now}\n\n商品状态正常，无异常商品 👍"
        
        # 精简风格的消息
        lines = []
        
        # 标题区
        lines.append(f"⚠️ 【商品异常提醒】")
        lines.append(f"📍 {shop_name}")
        lines.append(f"⏰ {now}")
        lines.append("")
        
        # 已下架商品
        if off_sale_goods:
            lines.append(f"🔻 已下架 ({off_count})")
            lines.append("─" * 16)
            for i, g in enumerate(off_sale_goods[:8], 1):
                name = g.goods_name[:12] + "..." if len(g.goods_name) > 12 else g.goods_name
                lines.append(f"  {i}. {name}")
            if off_count > 8:
                lines.append(f"  ... 等{off_count}个商品")
            lines.append("")
        
        # 已售罄商品
        if sold_out_goods:
            lines.append(f"🔴 已售罄 ({sold_count})")
            lines.append("─" * 16)
            for i, g in enumerate(sold_out_goods[:8], 1):
                name = g.goods_name[:12] + "..." if len(g.goods_name) > 12 else g.goods_name
                lines.append(f"  {i}. {name}")
            if sold_count > 8:
                lines.append(f"  ... 等{sold_count}个商品")
            lines.append("")
        
        # 底部统计
        lines.append("─" * 16)
        lines.append(f"📊 共 {total} 个异常商品")
        lines.append("💡 请及时处理")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_wecom_markdown(
        shop_name: str,
        off_sale_goods: List[GoodsItem],
        sold_out_goods: List[GoodsItem],
    ) -> dict:
        """
        格式化企业微信 Markdown 格式消息（更精美）
        
        Returns:
            企业微信机器人消息体 dict
        """
        now = datetime.now().strftime("%m-%d %H:%M")
        
        off_count = len(off_sale_goods)
        sold_count = len(sold_out_goods)
        total = off_count + sold_count
        
        if total == 0:
            content = f"### ✅ 商品状态正常\n" \
                      f"> 门店：{shop_name}\n" \
                      f"> 时间：{now}\n\n" \
                      f"无异常商品，一切正常 👍"
            return {
                "msgtype": "markdown",
                "markdown": {"content": content}
            }
        
        # 构建 Markdown 内容
        md_lines = []
        md_lines.append(f"### ⚠️ 商品异常提醒")
        md_lines.append(f"> 门店：<font color=\"info\">{shop_name}</font>")
        md_lines.append(f"> 时间：{now}")
        md_lines.append("")
        
        if off_sale_goods:
            md_lines.append(f"**🔻 已下架 ({off_count}个)**")
            for i, g in enumerate(off_sale_goods[:6], 1):
                name = g.goods_name[:15] + "..." if len(g.goods_name) > 15 else g.goods_name
                md_lines.append(f"> {i}. {name}")
            if off_count > 6:
                md_lines.append(f"> ... 共{off_count}个")
            md_lines.append("")
        
        if sold_out_goods:
            md_lines.append(f"**🔴 已售罄 ({sold_count}个)**")
            for i, g in enumerate(sold_out_goods[:6], 1):
                name = g.goods_name[:15] + "..." if len(g.goods_name) > 15 else g.goods_name
                md_lines.append(f"> {i}. <font color=\"warning\">{name}</font>")
            if sold_count > 6:
                md_lines.append(f"> ... 共{sold_count}个")
            md_lines.append("")
        
        md_lines.append(f"---")
        md_lines.append(f"📊 **共 {total} 个异常** | 💡 请及时处理")
        
        return {
            "msgtype": "markdown",
            "markdown": {"content": "\n".join(md_lines)}
        }

