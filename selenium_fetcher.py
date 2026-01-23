#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
淘宝闪购商品监控工具 - Selenium自动化抓取模块
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
    """使用Selenium抓取商品数据"""
    
    def __init__(
        self,
        shop_id: str,
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
            headless: 是否无头模式（建议首次运行设为False以便登录）
            debug_port: Chromium/Chrome 远程调试端口（默认 9222）
            user_data_dir: Chromium/Chrome 用户数据目录（用于持久化登录态）
            browser_path: 浏览器可执行文件路径（可选，留空自动寻找）
            auto_launch_browser: 无法连接调试端口时，是否自动启动浏览器
        """
        self.shop_id = shop_id
        self.headless = headless
        self.debug_port = int(debug_port)
        self.browser_path = browser_path
        self.auto_launch_browser = auto_launch_browser
        self.driver = None
        self.cookies_file = f"./cookies_{shop_id}.pkl"
        if user_data_dir:
            self.user_data_dir = os.path.abspath(user_data_dir)
        else:
            # 默认放在项目目录下，保证“登录一次，后续复用登录态”
            self.user_data_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "chromium_profile",
            )
    
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
        
        # 优先从 PATH 查找
        candidates_in_path = [
            "chromium",
            "chromium.exe",
            "chrome",
            "chrome.exe",
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
            candidates.extend([
                # Chromium (常见路径)
                r"C:\Program Files\Chromium\Application\chrome.exe",
                r"C:\Program Files (x86)\Chromium\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Chromium\Application\chrome.exe"),
                # Google Chrome
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
                # Microsoft Edge（Chromium内核）
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            ])
        elif system == "Darwin":  # macOS
            candidates.extend([
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            ])
        else:  # Linux
            candidates.extend([
                "/usr/bin/chromium-browser",
                "/usr/bin/chromium",
                "/usr/bin/google-chrome",
                "/usr/bin/microsoft-edge",
            ])
        
        for p in candidates:
            if p and os.path.exists(p):
                return p
        
        return ""
        
    def _init_driver(self):
        """连接到已运行的Chrome浏览器（远程调试模式），如果未运行则尝试启动"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            
            options = Options()
            # 连接到已运行的Chrome浏览器（调试端口9222）
            options.add_experimental_option("debuggerAddress", f"127.0.0.1:{self.debug_port}")
            
            try:
                self.driver = webdriver.Chrome(options=options)
                self.driver.implicitly_wait(10)
                logger.info("成功连接到浏览器（远程调试）")
            except Exception:
                logger.info("未能连接到现有浏览器实例，尝试自动启动 Chromium/Chrome...")
                if self.ensure_debug_browser():
                    # 启动后再次尝试连接
                    self._wait_for_debug_port(timeout=20)
                    self.driver = webdriver.Chrome(options=options)
                    self.driver.implicitly_wait(10)
                    logger.info("成功启动并连接到浏览器（远程调试）")
                else:
                    raise Exception("无法自动启动浏览器，请手动启动远程调试浏览器")
            
        except Exception as e:
            logger.error(f"连接Chrome浏览器失败: {e}")
            logger.error("请尝试手动运行以下命令启动浏览器（远程调试模式）:")
            if os.name == 'nt':  # Windows
                logger.error(
                    f'chrome.exe --remote-debugging-port={self.debug_port} --user-data-dir="{self.user_data_dir}"'
                )
            else:
                logger.error(
                    f"google-chrome --remote-debugging-port={self.debug_port} --user-data-dir={self.user_data_dir}"
                )
            raise

    def _launch_chrome_debug(self, open_url: Optional[str] = None) -> bool:
        """尝试启动浏览器调试模式（Chromium/Chrome/Edge）"""
        import subprocess
        
        browser_exe = self._find_browser_executable()
        if not browser_exe:
            logger.error("未找到 Chromium/Chrome/Edge 可执行文件")
            return False
            
        try:
            # 创建用户数据目录
            os.makedirs(self.user_data_dir, exist_ok=True)
                
            cmd = [
                browser_exe,
                f"--remote-debugging-port={self.debug_port}",
                f"--user-data-dir={self.user_data_dir}",
                "--no-first-run",
                "--no-default-browser-check",
            ]
            if open_url:
                cmd.append(open_url)
            
            logger.info(f"正在启动浏览器: {' '.join(cmd)}")
            subprocess.Popen(cmd)
            return self._wait_for_debug_port(timeout=20)
        except Exception as e:
            logger.error(f"启动浏览器失败: {e}")
            return False

    
    def login_and_fetch(
        self,
        auto_login: bool = False,
        wait_for_login: bool = True,
        login_timeout: int = 600,
        dump_debug: bool = False,
    ) -> List[GoodsItem]:
        """
        登录并抓取商品
        
        Args:
            auto_login: 保留参数(兼容旧版)，当前逻辑主要复用浏览器登录态
            wait_for_login: 检测到未登录时，是否等待用户在浏览器内完成登录
            login_timeout: 等待登录最大秒数
            dump_debug: 是否保存页面截图和HTML（用于排查页面结构）
            
        Returns:
            商品列表
        """
        if not self.driver:
            self._init_driver()
        
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        try:
            # 访问商品管理页面
            goods_url = f"https://napos-goods-pc.faas.ele.me/single/goods-manage?shopId={self.shop_id}"
            logger.info(f"正在访问: {goods_url}")
            self.driver.get(goods_url)
            
            # 等待页面加载
            time.sleep(5)
            
            # 如未登录，等待用户在已打开的浏览器中完成登录（只需第一次）
            if wait_for_login and self._need_login():
                logger.warning(
                    f"检测到可能未登录，请在已打开的浏览器窗口中完成登录/扫码（最多等待 {login_timeout} 秒）..."
                )
                start = time.time()
                while time.time() - start < login_timeout:
                    time.sleep(3)
                    try:
                        if not self._need_login():
                            logger.info("已检测到登录完成，继续抓取")
                            break
                    except Exception:
                        # 页面可能在跳转，忽略一次
                        pass
                else:
                    raise Exception(f"等待登录超时（{login_timeout}秒），请确认已完成登录")
            
            # 浏览器已登录，直接开始抓取
            print("\n已连接到登录的浏览器，开始抓取...")
            
            # 等待商品列表加载
            logger.info("等待商品列表加载...")
            time.sleep(3)
            
            # 调试：保存页面截图和HTML
            if dump_debug:
                self.driver.save_screenshot("debug_screenshot.png")
                with open("debug_page.html", "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)
                logger.info("已保存调试截图: debug_screenshot.png 和 debug_page.html")
            
            # 打印当前URL
            logger.info(f"当前URL: {self.driver.current_url}")
            logger.info(f"页面标题: {self.driver.title}")
            
            # 抓取所有商品
            all_goods = self._fetch_all_pages()
            
            return all_goods
            
        except Exception as e:
            logger.error(f"抓取失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _need_login(self) -> bool:
        """检查是否需要登录"""
        try:
            # 先用URL判断（比全文关键字更可靠）
            url = (self.driver.current_url or "").lower()
            if any(k in url for k in ["login", "signin", "passport", "oauth", "auth", "account.taobao", "login.taobao"]):
                return True

            # 检查是否有登录相关元素
            page_source = self.driver.page_source
            # 注意：不要用“登录”这个过于泛化的关键词，容易误判
            login_indicators = ["请登录", "扫码登录", "login", "signin", "account.taobao", "login.taobao"]
            
            for indicator in login_indicators:
                if indicator in page_source and "商品管理" not in page_source:
                    return True
            
            return False
        except:
            return True
    
    def _fetch_all_pages(self) -> List[GoodsItem]:
        """抓取所有页面的商品 - 专门获取已下架和已售罄的商品"""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException, NoSuchElementException
        
        all_goods = []
        
        # 要抓取的标签：已下架、已售罄
        tabs_to_fetch = [
            ("已下架", "OFF_SALE"),
            ("已售罄", "SOLD_OUT"),
        ]
        
        for tab_name, status_code in tabs_to_fetch:
            logger.info(f"正在点击 '{tab_name}' 标签...")
            
            try:
                # 找到并点击标签
                tab_clicked = False
                tab_selectors = [
                    f"//span[contains(text(), '{tab_name}')]/ancestor::div[contains(@class, 'tab')]",
                    f"//div[contains(text(), '{tab_name}')]",
                    f"//*[contains(text(), '{tab_name}')]",
                ]
                
                for selector in tab_selectors:
                    try:
                        tabs = self.driver.find_elements(By.XPATH, selector)
                        for tab in tabs:
                            if tab_name in tab.text:
                                tab.click()
                                tab_clicked = True
                                logger.info(f"成功点击 '{tab_name}' 标签")
                                time.sleep(3)  # 等待页面加载
                                break
                        if tab_clicked:
                            break
                    except Exception as e:
                        continue
                
                if not tab_clicked:
                    logger.warning(f"未能点击 '{tab_name}' 标签，尝试直接获取")
                
                # 抓取该标签下的所有商品
                goods_in_tab = self._fetch_goods_in_current_tab(status_code)
                all_goods.extend(goods_in_tab)
                logger.info(f"'{tab_name}' 标签下抓取到 {len(goods_in_tab)} 个商品")
                
            except Exception as e:
                logger.error(f"抓取 '{tab_name}' 标签失败: {e}")
        
        logger.info(f"共抓取到 {len(all_goods)} 个异常商品（已下架+已售罄）")
        return all_goods
    
    def _fetch_goods_in_current_tab(self, status_code: str) -> List[GoodsItem]:
        """抓取当前标签下的所有商品"""
        all_goods = []
        page = 1
        
        while True:
            logger.info(f"正在抓取第 {page} 页...")
            time.sleep(2)
            
            # 抓取当前页商品
            goods_on_page = self._parse_goods_from_page(status_code)
            
            if not goods_on_page:
                logger.info("当前页没有找到商品，结束抓取")
                break
            
            all_goods.extend(goods_on_page)
            logger.info(f"第 {page} 页抓取到 {len(goods_on_page)} 个商品")
            
            # 检查是否有下一页
            if not self._goto_next_page():
                break
            
            page += 1
            time.sleep(2)
            
            if page > 50:
                logger.warning("已抓取50页，停止")
                break
        
        return all_goods
    
    def _parse_goods_from_page(self, status_code: str = None) -> List[GoodsItem]:
        """解析当前页面的商品数据"""
        from selenium.webdriver.common.by import By
        
        goods_list = []
        
        try:
            # 尝试多种选择器找到商品行
            selectors = [
                "tr[class*='ant-table-row']",
                "div[class*='goods-item']",
                "div[class*='goodsItem']",
                "div[class*='product-item']",
                ".ant-table-tbody tr",
                "[class*='tableRow']",
                "[class*='rowContainer']",  # 新增
            ]
            
            rows = []
            for selector in selectors:
                try:
                    rows = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if rows:
                        logger.info(f"使用选择器 '{selector}' 找到 {len(rows)} 行")
                        break
                except:
                    continue
            
            if not rows:
                # 尝试通过XPath
                try:
                    rows = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'ant-checkbox-wrapper')]/ancestor::div[contains(@class, 'Row') or contains(@class, 'row')]")
                except:
                    pass
            
            for row in rows:
                try:
                    goods = self._parse_single_row(row, status_code)
                    if goods:
                        goods_list.append(goods)
                except Exception as e:
                    logger.debug(f"解析单行失败: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"解析页面商品失败: {e}")
        
        return goods_list
    
    def _parse_single_row(self, row, status_code: str = None) -> Optional[GoodsItem]:
        """解析单个商品行"""
        from selenium.webdriver.common.by import By
        
        try:
            text = row.text
            if not text or len(text) < 5:
                return None
            
            # 尝试找到商品名称
            name = ""
            name_selectors = [
                "[class*='name']",
                "[class*='title']",
                "[class*='Name']",
                "[class*='Title']",
            ]
            for sel in name_selectors:
                try:
                    name_elem = row.find_element(By.CSS_SELECTOR, sel)
                    name = name_elem.text.strip()
                    if name:
                        break
                except:
                    continue
            
            if not name:
                # 从文本中提取
                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    if line and len(line) > 2 and not line.startswith('¥') and not line.isdigit():
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


def main():
    """测试抓取"""
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    shop_id = "1303549223"  # 默认店铺ID
    
    if len(sys.argv) > 1:
        shop_id = sys.argv[1]
    
    print(f"开始抓取店铺 {shop_id} 的商品...")
    
    fetcher = SeleniumGoodsFetcher(shop_id=shop_id, headless=False)
    
    try:
        goods_list = fetcher.login_and_fetch(auto_login=False)
        
        if goods_list:
            stats = fetcher.get_statistics(goods_list)
            problems = fetcher.get_problematic_goods(goods_list)
            
            print("\n" + "=" * 60)
            print("商品统计")
            print("=" * 60)
            print(f"总商品数: {stats['total']}")
            print(f"在售: {stats['on_sale']}")
            print(f"已下架: {stats['off_sale']}")
            print(f"已售罄: {stats['sold_out']}")
            print(f"缺货: {stats['out_of_stock']}")
            print("=" * 60)
            
            for status_name, goods in problems.items():
                if goods:
                    print(f"\n{status_name}商品 ({len(goods)}个):")
                    for i, g in enumerate(goods[:10], 1):
                        print(f"  {i}. {g.goods_name}")
        else:
            print("未抓取到商品数据")
            
    finally:
        fetcher.close()


if __name__ == "__main__":
    main()

