#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright并行监控模块 - 使用单浏览器多页面实现真正的并行监控
"""

import os
import sys
import asyncio
import logging
import time
import subprocess
from typing import List, Dict, Optional, Callable, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 修复PyInstaller打包后Playwright找不到浏览器的问题
# Playwright浏览器默认安装在用户目录，但打包后的exe会查找错误的路径
def _setup_playwright_browsers_path():
    """设置Playwright浏览器路径环境变量"""
    if 'PLAYWRIGHT_BROWSERS_PATH' not in os.environ:
        # Windows默认安装路径
        if sys.platform == 'win32':
            default_path = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'ms-playwright')
        else:
            default_path = os.path.expanduser('~/.cache/ms-playwright')
        
        if os.path.exists(default_path):
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = default_path
            logger.info(f"设置PLAYWRIGHT_BROWSERS_PATH={default_path}")

# 在模块加载时就设置环境变量
_setup_playwright_browsers_path()


def ensure_playwright_browsers(log_callback=None):
    """
    确保Playwright浏览器已安装
    如果未安装，自动下载安装chromium
    """
    def log(msg):
        logger.info(msg)
        if log_callback:
            try:
                log_callback(msg)
            except:
                pass
    
    try:
        # 检查playwright是否可用
        from playwright.sync_api import sync_playwright
        
        # 直接尝试启动浏览器来检测是否已安装
        try:
            log("   正在检测Playwright浏览器...")
            with sync_playwright() as p:
                # 尝试启动浏览器（最可靠的检测方式）
                browser = p.chromium.launch(headless=True)
                browser.close()
                log("✓ Playwright浏览器已安装")
                return True
        except Exception as e:
            error_msg = str(e)
            log(f"   检测结果: {error_msg[:150]}")  # 显示详细错误
            
            # 检查是否是"未安装"相关的错误
            error_lower = error_msg.lower()
            if 'executable' in error_lower or 'not found' in error_lower or 'install' in error_lower:
                logger.info(f"Playwright浏览器未安装，开始自动安装...")
            else:
                # 其他错误可能是已安装但有其他问题，直接返回True让后续代码处理
                log(f"   Playwright检测异常，尝试继续使用...")
                return True
        
        # 自动安装chromium
        log("📦 正在安装Playwright浏览器（首次运行需要，约需2-5分钟）...")
        log("   下载约150MB，请确保网络畅通...")
        
        # Windows下隐藏命令行窗口
        creationflags = 0
        if sys.platform == 'win32':
            creationflags = subprocess.CREATE_NO_WINDOW
        
        # 优先使用playwright内置的driver来安装（打包exe中sys.executable不可用）
        try:
            from playwright._impl._driver import compute_driver_executable
            driver_executable = compute_driver_executable()
            
            if driver_executable and os.path.exists(driver_executable):
                log(f"   使用Playwright内置安装器...")
                result = subprocess.run(
                    [driver_executable, 'install', 'chromium'],
                    timeout=600,  # 10分钟超时
                    capture_output=True,
                    creationflags=creationflags,
                )
                
                if result.returncode == 0:
                    log("✓ Playwright浏览器安装成功！")
                    return True
                else:
                    stderr = result.stderr.decode('utf-8', errors='ignore') if result.stderr else ''
                    log(f"⚠ 安装失败: {stderr[:200]}")
        except subprocess.TimeoutExpired:
            log("⚠ 安装超时（10分钟），请检查网络")
        except Exception as e:
            logger.warning(f"内置安装器失败: {e}")
        
        # 备用方法：如果不是打包环境，尝试用python -m playwright
        if not getattr(sys, 'frozen', False):
            try:
                log("   尝试备用安装方式...")
                result = subprocess.run(
                    [sys.executable, '-m', 'playwright', 'install', 'chromium'],
                    timeout=600,
                    capture_output=True,
                    creationflags=creationflags,
                )
                
                if result.returncode == 0:
                    log("✓ Playwright浏览器安装成功！")
                    return True
            except Exception as e:
                logger.warning(f"备用安装方法也失败: {e}")
        
        log("⚠ 自动安装失败，将使用串行模式")
        return False
        
    except ImportError:
        log("⚠ Playwright未安装")
        return False
    except Exception as e:
        log(f"⚠ 检查Playwright时出错: {e}")
        return False


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


@dataclass
class ShopResult:
    """单个门店的监控结果"""
    shop_name: str
    short_name: str
    success: bool
    off_sale: List[GoodsItem] = None
    sold_out: List[GoodsItem] = None
    duration: float = 0
    error: str = ""
    skipped: bool = False
    skip_reason: str = ""
    shop_status: str = "营业中"


class PlaywrightMonitor:
    """
    Playwright并行监控器
    
    使用单个浏览器的多个页面实现真正的并行监控：
    - 所有页面共享同一个登录状态
    - 使用asyncio实现真正的并发操作
    """
    
    def __init__(
        self,
        num_workers: int = 5,
        config = None,
        log_callback: Callable = None,
        only_open_shops: bool = False,
        retry_timeout_minutes: int = 10,  # 重试超时时间（分钟）
    ):
        self.num_workers = num_workers
        self.parallel_workers = num_workers  # 兼容两种命名
        self.config = config
        self.log_callback = log_callback
        self.only_open_shops = only_open_shops  # 只监控营业中的门店
        self.retry_timeout_minutes = retry_timeout_minutes  # 重试超时时间
        self.browser = None
        self.context = None
        self.running = True
        self._shop_switch_lock = None  # 门店切换锁（在异步环境中初始化）
        
    def log(self, msg: str):
        """输出日志"""
        logger.info(msg)
        if self.log_callback:
            try:
                self.log_callback(msg)
            except:
                pass
    
    def _simplify_shop_name(self, full_name: str) -> str:
        """简化门店名称"""
        import re
        if not full_name:
            return "未知"
        
        prefixes = ['阿狗手打·手作黑糖珍珠奶茶', '阿狗手打·手作', '阿狗手打·黑糖珍珠奶茶', '阿狗黑糖珍珠奶茶']
        name = full_name
        for prefix in prefixes:
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        
        name = re.sub(r'[（(](.*?)[）)]', r'\1', name)
        name = name.strip()
        
        return name if name else full_name
    
    async def _get_current_shop_name(self, page) -> str:
        """获取当前页面显示的门店名称"""
        try:
            # 使用JavaScript获取门店名称，更可靠
            js_code = '''
                (() => {
                    // 方法1: 从shopSwitcher获取
                    let switcher = document.querySelector('.shopSwitcher .clk-area');
                    if (switcher) {
                        let text = switcher.innerText || switcher.textContent;
                        if (text && text.includes('(')) return text.trim();
                    }
                    
                    // 方法2: 从包含"阿狗"的元素获取
                    let allElements = document.querySelectorAll('*');
                    for (let el of allElements) {
                        let text = el.innerText || el.textContent || '';
                        // 匹配门店名称格式：包含品牌名和括号
                        if (text.includes('阿狗手打') && text.includes('(') && text.includes('店)')) {
                            // 提取完整门店名称
                            let match = text.match(/阿狗手打[^\\n]+\\([^)]+店\\)/);
                            if (match) return match[0].trim();
                        }
                    }
                    
                    // 方法3: 从页面标题获取
                    if (document.title && document.title.includes('(')) {
                        return document.title.trim();
                    }
                    
                    return '';
                })()
            '''
            current_shop = await page.evaluate(js_code)
            if current_shop:
                self.log(f"   📍 当前页面门店: {current_shop[:50]}...")
            return current_shop or ''
        except Exception as e:
            self.log(f"   ⚠ 获取当前门店名称失败: {e}")
            return ''
    
    async def _verify_shop_switched(self, page, target_shop_name: str) -> Tuple[bool, str]:
        """验证是否成功切换到目标门店，返回 (是否成功, 当前门店名称)"""
        try:
            short_name = self._simplify_shop_name(target_shop_name)
            current_shop = await self._get_current_shop_name(page)
            
            if not current_shop:
                self.log(f"   ⚠ 无法获取当前门店名称，验证失败")
                return False, ''
            
            # 提取当前门店的简短名称进行比较
            current_short = self._simplify_shop_name(current_shop)
            
            self.log(f"   🔍 验证门店: 目标[{short_name}] vs 当前[{current_short}]")
            
            # 严格匹配：目标门店简称必须与当前门店简称相同
            if short_name == current_short:
                self.log(f"   ✓ 门店验证通过")
                return True, current_shop
            
            # 如果简称不完全匹配，检查是否包含关键字
            # 从目标门店名称提取关键字（去掉通用部分）
            target_keywords = short_name.replace('店', '')
            current_keywords = current_short.replace('店', '')
            
            if target_keywords and target_keywords in current_keywords:
                self.log(f"   ✓ 门店关键字匹配通过")
                return True, current_shop
            
            self.log(f"   ✗ 门店验证失败: 期望[{short_name}], 实际[{current_short}]")
            return False, current_shop
        except Exception as e:
            self.log(f"   ⚠ 门店验证异常: {e}")
            return False, ''
    
    async def _switch_shop(self, page, shop_name: str) -> dict:
        """切换到指定门店"""
        try:
            short_name = self._simplify_shop_name(shop_name)
            
            # 步骤1: 点击门店切换器打开下拉框
            dropdown_selectors = [
                '.shopSwitcher .clk-area',
                '[class*="shopSwitcher"] [class*="clk-area"]',
                '.shopSwitcher',
            ]
            
            clicked = False
            for selector in dropdown_selectors:
                try:
                    elem = page.locator(selector).first
                    if await elem.is_visible(timeout=2000):
                        await elem.click()
                        clicked = True
                        break
                except:
                    continue
            
            if not clicked:
                return {'success': False, 'reason': '未找到门店下拉按钮'}
            
            await asyncio.sleep(2)
            
            # 步骤2: 在搜索框中输入关键字
            search_selectors = [
                'input[placeholder*="搜索店铺"]',
                'input[placeholder*="搜索"]',
                '.cook-cascader input',
            ]
            
            search_input = None
            for selector in search_selectors:
                try:
                    elem = page.locator(selector).first
                    if await elem.is_visible(timeout=2000):
                        search_input = elem
                        break
                except:
                    continue
            
            if not search_input:
                return {'success': False, 'reason': '未找到搜索框'}
            
            await search_input.fill('')
            await search_input.fill(shop_name)
            await asyncio.sleep(3)  # 搜索后多等待，让下拉列表完全加载
            
            # 步骤3: 点击搜索结果并检测门店状态
            result_selectors = [
                f'.cook-cascader-dropdown li:has-text("{short_name}")',
                f'li[class*="option"]:has-text("{short_name}")',
                f'div[class*="option"]:has-text("{short_name}")',
            ]
            
            shop_status = '营业中'
            for selector in result_selectors:
                try:
                    elem = page.locator(selector).first
                    if await elem.is_visible(timeout=2000):
                        # 检查门店状态（休息中/已下线/已打烊/未营业）
                        elem_text = await elem.inner_text()
                        if any(kw in elem_text for kw in ['休息中', '已下线', '已打烊', '未营业', '暂停营业']):
                            if '已下线' in elem_text:
                                shop_status = '已下线'
                            elif '已打烊' in elem_text or '未营业' in elem_text or '暂停营业' in elem_text:
                                shop_status = '已打烊'
                            else:
                                shop_status = '休息中'
                        await elem.click()
                        await asyncio.sleep(3)
                        
                        # 验证切换是否成功
                        verified, current_shop = await self._verify_shop_switched(page, shop_name)
                        if verified:
                            return {'success': True, 'shop_status': shop_status, 'verified': True}
                        else:
                            current_short = self._simplify_shop_name(current_shop) if current_shop else '未知'
                            return {'success': False, 'reason': f'门店切换验证失败，当前是[{current_short}]', 'shop_status': shop_status}
                except:
                    continue
            
            # 备用：按Enter键
            await search_input.press('Enter')
            await asyncio.sleep(3)
            
            # 验证切换是否成功
            verified, current_shop = await self._verify_shop_switched(page, shop_name)
            if verified:
                return {'success': True, 'shop_status': shop_status, 'verified': True}
            else:
                current_short = self._simplify_shop_name(current_shop) if current_shop else '未知'
                return {'success': False, 'reason': f'门店切换验证失败，当前是[{current_short}]', 'shop_status': shop_status}
            
        except Exception as e:
            return {'success': False, 'reason': str(e)}
    
    async def _analyze_tab_structure(self, frame) -> list:
        """分析页面上的标签结构，输出调试信息并返回找到的元素"""
        try:
            js_script = '''
                (() => {
                    var result = [];
                    var keywords = ["已下架", "已售罄", "出售中", "全部", "待审核", "促销", "单点不送", "套餐"];
                    var allElements = document.querySelectorAll('*');
                    
                    for (var i = 0; i < allElements.length; i++) {
                        var el = allElements[i];
                        var text = (el.innerText || el.textContent || '').trim();
                        
                        // 只检查直接文本内容（避免父元素重复）
                        for (var k = 0; k < keywords.length; k++) {
                            if (text.indexOf(keywords[k]) !== -1 && text.length < 30) {
                                var rect = el.getBoundingClientRect();
                                if (rect.width > 0 && rect.height > 0) {
                                    var info = {
                                        tag: el.tagName,
                                        cls: (el.className || '').substring(0, 50),
                                        text: text.substring(0, 20),
                                        size: Math.round(rect.width) + 'x' + Math.round(rect.height)
                                    };
                                    // 避免重复
                                    var isDup = false;
                                    for (var m = 0; m < result.length; m++) {
                                        if (result[m].text === info.text) {
                                            isDup = true;
                                            break;
                                        }
                                    }
                                    if (!isDup) {
                                        result.push(info);
                                    }
                                    break;
                                }
                            }
                        }
                    }
                    return result.slice(0, 15);
                })()
            '''
            elements = await frame.evaluate(js_script)
            
            if elements:
                self.log(f"🔍 页面标签分析: 找到 {len(elements)} 个标签")
                for el in elements[:5]:
                    self.log(f"   • {el.get('text', '')} <{el.get('tag', '')}>")
            else:
                self.log("🔍 未发现标签元素，可能在iframe中...")
            
            return elements
        except Exception as e:
            logger.warning(f"分析标签结构出错: {e}")
            return []
    
    async def _ensure_goods_page(self, page) -> bool:
        """确保页面在商品管理页面，如果不是则导航过去"""
        try:
            current_url = page.url.lower()
            
            # 检查是否在商品管理页面
            if 'food' in current_url or 'management' in current_url:
                return True
            
            # 不在商品管理页面，需要导航
            logger.info(f"页面不在商品管理页面({current_url[:50]}...)，正在导航...")
            
            # 构建商品管理页面URL
            base_url = self.config.base_url if self.config else "https://e.taobao.com"
            shop_id = self.config.shop_id if self.config else ""
            goods_url = f"{base_url}/app/shop/{shop_id}/food#app.shop.food?path=management"
            
            await page.goto(goods_url, wait_until='load', timeout=60000)
            await asyncio.sleep(3)
            
            return True
        except Exception as e:
            logger.error(f"导航到商品管理页面失败: {e}")
            return False
    
    async def _fetch_goods(self, page) -> tuple:
        """抓取当前页面的商品数据"""
        off_sale_list = []
        sold_out_list = []
        
        try:
            # 先等待页面稳定
            await asyncio.sleep(2)
            
            # 找到商品管理iframe - 这是关键！商品数据在iframe中
            target_frame = None
            
            # 方法1: 通过frames列表查找
            try:
                for frame in page.frames:
                    frame_url = frame.url.lower()
                    # 商品管理iframe的URL通常包含这些关键词
                    if any(kw in frame_url for kw in ['food', 'management', 'goods', 'product']):
                        target_frame = frame
                        logger.info(f"找到商品管理iframe: {frame_url[:80]}")
                        break
            except Exception as e:
                logger.warning(f"通过frames查找iframe失败: {e}")
            
            # 方法2: 如果方法1失败，尝试frame_locator
            if not target_frame:
                try:
                    iframe_selectors = [
                        'iframe#app_shop_food',
                        'iframe[name="app_shop_food"]',
                        'iframe[src*="food"]',
                        'iframe[src*="management"]',
                    ]
                    for selector in iframe_selectors:
                        try:
                            fl = page.frame_locator(selector)
                            if await fl.locator('body').count() > 0:
                                # frame_locator找到了，但我们需要实际的frame对象
                                # 通过evaluate获取iframe的src，然后匹配frames
                                iframe_src = await page.evaluate(f'''
                                    (() => {{
                                        const iframe = document.querySelector('{selector}');
                                        return iframe ? iframe.src : null;
                                    }})()
                                ''')
                                if iframe_src:
                                    for frame in page.frames:
                                        if iframe_src in frame.url or frame.url in iframe_src:
                                            target_frame = frame
                                            logger.info(f"通过frame_locator找到iframe: {frame.url[:80]}")
                                            break
                                break
                        except:
                            continue
                except Exception as e:
                    logger.warning(f"通过frame_locator查找失败: {e}")
            
            # 收集所有可能的操作目标（主页面 + 所有iframe）
            all_frames = [page] + list(page.frames)
            
            # 首先在主页面分析标签结构
            self.log(f"   📋 分析页面结构（共{len(all_frames)}个frame）...")
            main_elements = await self._analyze_tab_structure(page)
            
            # 如果主页面没找到标签，在iframe中搜索
            work_frame = page
            if not main_elements or not any('下架' in str(el.get('text', '')) for el in main_elements):
                self.log(f"   🔍 主页面未找到标签，搜索iframe...")
                for frame in page.frames:
                    if frame == page:
                        continue
                    try:
                        frame_elements = await self._analyze_tab_structure(frame)
                        if frame_elements and any('下架' in str(el.get('text', '')) for el in frame_elements):
                            work_frame = frame
                            self.log(f"   ✓ 在iframe中找到标签")
                            break
                    except:
                        continue
            
            # 点击"已下架"标签并抓取
            self.log(f"   📂 点击'已下架'标签...")
            clicked = await self._click_tab_in_frame(work_frame, "已下架")
            if clicked:
                self.log(f"   ✓ 点击成功，等待加载...")
                await asyncio.sleep(3)
                off_sale_list = await self._parse_goods_from_frame(work_frame, "OFF_SALE")
                self.log(f"   → 已下架: {len(off_sale_list)} 个商品")
            else:
                self.log(f"   ✗ 点击失败，尝试其他frame...")
                # 在所有frame中尝试点击
                for frame in all_frames:
                    if frame == work_frame:
                        continue
                    try:
                        clicked = await self._click_tab_in_frame(frame, "已下架")
                        if clicked:
                            await asyncio.sleep(3)
                            off_sale_list = await self._parse_goods_from_frame(frame, "OFF_SALE")
                            self.log(f"   → 在其他frame中找到，已下架: {len(off_sale_list)} 个")
                            work_frame = frame  # 更新工作frame
                            break
                    except:
                        continue
            
            # 点击"已售罄"标签并抓取
            self.log(f"   📂 点击'已售罄'标签...")
            clicked = await self._click_tab_in_frame(work_frame, "已售罄")
            if clicked:
                self.log(f"   ✓ 点击成功，等待加载...")
                await asyncio.sleep(3)
                sold_out_list = await self._parse_goods_from_frame(work_frame, "SOLD_OUT")
                self.log(f"   → 已售罄: {len(sold_out_list)} 个商品")
            else:
                self.log(f"   ✗ 点击失败，尝试其他frame...")
                for frame in all_frames:
                    if frame == work_frame:
                        continue
                    try:
                        clicked = await self._click_tab_in_frame(frame, "已售罄")
                        if clicked:
                            await asyncio.sleep(3)
                            sold_out_list = await self._parse_goods_from_frame(frame, "SOLD_OUT")
                            self.log(f"   → 在其他frame中找到，已售罄: {len(sold_out_list)} 个")
                            break
                    except:
                        continue
            
        except Exception as e:
            logger.error(f"抓取商品出错: {e}")
            import traceback
            traceback.print_exc()
        
        return off_sale_list, sold_out_list
    
    async def _click_tab_in_frame(self, frame, tab_name: str) -> bool:
        """在指定frame中点击标签页"""
        try:
            js_script = f'''
                (() => {{
                    var targetText = '{tab_name}';
                    console.log('正在查找标签: ' + targetText);
                    
                    // 策略1: 使用常见的tab组件选择器
                    var tabSelectors = [
                        '.ant-tabs-tab-btn',
                        '.cook-tabs-tab-btn',
                        '[role="tab"]',
                        '[class*="tabs-tab"]',
                        '[class*="tab-btn"]',
                        '[class*="panelTitle"]',
                        '[class*="TabItem"]',
                        '[class*="tabItem"]',
                        '[class*="tab-item"]',
                        '[class*="filterItem"]',
                        '[class*="filter-item"]',
                    ];
                    
                    for (var s = 0; s < tabSelectors.length; s++) {{
                        var tabs = document.querySelectorAll(tabSelectors[s]);
                        for (var i = 0; i < tabs.length; i++) {{
                            var text = tabs[i].innerText || tabs[i].textContent || '';
                            if (text.indexOf(targetText) >= 0) {{
                                console.log('策略1找到: ' + tabSelectors[s] + ' text=' + text);
                                tabs[i].click();
                                return 'selector:' + tabSelectors[s];
                            }}
                        }}
                    }}
                    
                    // 策略2: 查找包含目标文字的任意元素（最宽松）
                    var allEls = document.querySelectorAll('*');
                    var candidates = [];
                    for (var i = 0; i < allEls.length; i++) {{
                        var el = allEls[i];
                        var text = (el.innerText || el.textContent || '').trim();
                        // 匹配 "已下架" 或 "已下架5" 或 "已下架 5" 等格式
                        if (text.indexOf(targetText) === 0 && text.length <= targetText.length + 10) {{
                            var rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0 && rect.width < 200) {{
                                // 优先选择较小的元素（更精确）
                                candidates.push({{el: el, size: rect.width * rect.height, text: text}});
                            }}
                        }}
                    }}
                    
                    // 按元素大小排序，优先点击最小的（最精确的）
                    if (candidates.length > 0) {{
                        candidates.sort((a, b) => a.size - b.size);
                        var best = candidates[0];
                        console.log('策略2找到: ' + best.el.tagName + ' text=' + best.text + ' size=' + best.size);
                        best.el.click();
                        return 'element:' + best.el.tagName;
                    }}
                    
                    // 策略3: 使用XPath精确查找以目标文字开头的元素
                    var xpath = "//*[starts-with(normalize-space(text()), '" + targetText + "')]";
                    var result = document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
                    for (var i = 0; i < result.snapshotLength; i++) {{
                        var el = result.snapshotItem(i);
                        var rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {{
                            console.log('策略3(XPath)找到: ' + el.tagName);
                            el.click();
                            return 'xpath:' + el.tagName;
                        }}
                    }}
                    
                    console.log('未找到标签: ' + targetText);
                    return false;
                }})()
            '''
            result = await frame.evaluate(js_script)
            if result:
                logger.info(f"点击标签'{tab_name}'成功: {result}")
            else:
                logger.warning(f"未找到标签'{tab_name}'")
            return bool(result)
        except Exception as e:
            logger.error(f"点击标签'{tab_name}'失败: {e}")
            return False
    
    async def _parse_goods_from_frame(self, frame, status_code: str) -> List[GoodsItem]:
        """从指定frame解析商品列表，包括遍历所有分类子页面"""
        all_goods = []
        seen_names = set()
        
        try:
            # 首先检查是否有左侧分类列表（子页面）
            categories = await self._get_category_list(frame)
            
            if categories and len(categories) > 1:
                # 有多个分类，需要遍历每个分类
                logger.info(f"发现 {len(categories)} 个分类子页面")
                for idx, cat in enumerate(categories):
                    cat_name = cat.get('name', '')
                    cat_count = cat.get('count', 0)
                    
                    if cat_count > 0:
                        # 点击该分类
                        clicked = await self._click_category(frame, cat_name, idx)
                        if clicked:
                            await asyncio.sleep(1)  # 等待内容加载
                            
                            # 解析当前分类下的商品
                            goods = await self._parse_current_page_goods(frame)
                            for item in goods:
                                name = item.get('name', '').strip()
                                if name and name not in seen_names:
                                    seen_names.add(name)
                                    all_goods.append(GoodsItem(
                                        goods_id=str(len(all_goods)),
                                        goods_name=name,
                                        category=cat_name,
                                        price=0,
                                        original_price=0,
                                        stock=0,
                                        status=status_code,
                                        status_text="已下架" if status_code == "OFF_SALE" else "已售罄",
                                    ))
                            logger.info(f"  分类'{cat_name}': 获取到 {len(goods)} 个商品")
            else:
                # 没有分类或只有一个分类，直接解析当前页面
                goods = await self._parse_current_page_goods(frame)
                for i, item in enumerate(goods):
                    name = item.get('name', '').strip()
                    if name and name not in seen_names:
                        seen_names.add(name)
                        all_goods.append(GoodsItem(
                            goods_id=str(i),
                            goods_name=name,
                            category="",
                            price=0,
                            original_price=0,
                            stock=0,
                            status=status_code,
                            status_text="已下架" if status_code == "OFF_SALE" else "已售罄",
                        ))
            
            logger.info(f"共解析到 {len(all_goods)} 个商品 ({status_code})")
                    
        except Exception as e:
            logger.error(f"解析商品出错: {e}")
        
        return all_goods
    
    async def _get_category_list(self, frame) -> list:
        """获取左侧分类列表"""
        try:
            js_script = '''
                (() => {
                    var categories = [];
                    
                    // 查找左侧分类列表容器
                    var categorySelectors = [
                        '[class*="category"]',
                        '[class*="leftTree"]',
                        '[class*="sideMenu"]',
                        '[class*="treeNode"]',
                        '[class*="menuItem"]',
                        '.ant-tree-treenode',
                        '[class*="TreeNode"]',
                    ];
                    
                    // 方法1: 查找包含数字的分类项（如"特色黑糖珍珠系列(1)"）
                    var allElements = document.querySelectorAll('*');
                    for (var i = 0; i < allElements.length; i++) {
                        var el = allElements[i];
                        var text = (el.innerText || el.textContent || '').trim();
                        
                        // 匹配 "xxx(数字)" 或 "xxx (数字)" 格式
                        var match = text.match(/^(.+?)\\s*[\\(（](\\d+)[\\)）]$/);
                        if (match && text.length < 30) {
                            var rect = el.getBoundingClientRect();
                            // 分类项通常在左侧，宽度不会太大
                            if (rect.width > 30 && rect.width < 300 && rect.height > 10 && rect.height < 50) {
                                var name = match[1].trim();
                                var count = parseInt(match[2]) || 0;
                                
                                // 检查是否已存在
                                var exists = false;
                                for (var j = 0; j < categories.length; j++) {
                                    if (categories[j].name === name) {
                                        exists = true;
                                        break;
                                    }
                                }
                                if (!exists && count > 0) {
                                    categories.push({
                                        name: name,
                                        count: count,
                                        text: text
                                    });
                                }
                            }
                        }
                    }
                    
                    return categories;
                })()
            '''
            categories = await frame.evaluate(js_script)
            return categories or []
        except Exception as e:
            logger.warning(f"获取分类列表失败: {e}")
            return []
    
    async def _click_category(self, frame, category_name: str, index: int) -> bool:
        """点击指定分类"""
        try:
            js_script = f'''
                (() => {{
                    var targetName = '{category_name}';
                    var allElements = document.querySelectorAll('*');
                    
                    for (var i = 0; i < allElements.length; i++) {{
                        var el = allElements[i];
                        var text = (el.innerText || el.textContent || '').trim();
                        
                        // 匹配分类名（带数字或不带）
                        if (text.indexOf(targetName) === 0 && text.length < 30) {{
                            var rect = el.getBoundingClientRect();
                            if (rect.width > 30 && rect.width < 300 && rect.height > 10 && rect.height < 50) {{
                                el.click();
                                return true;
                            }}
                        }}
                    }}
                    return false;
                }})()
            '''
            result = await frame.evaluate(js_script)
            return bool(result)
        except Exception as e:
            logger.warning(f"点击分类'{category_name}'失败: {e}")
            return False
    
    async def _parse_current_page_goods(self, frame) -> list:
        """解析当前页面显示的商品列表"""
        try:
            js_script = '''
                (() => {
                    var goods = [];
                    
                    // 商品行选择器（按优先级排列）
                    var rowSelectors = [
                        '[class*="tableRow__"]',
                        '[class*="style_tableRow"]',
                        '.ant-table-row',
                        'tr[data-row-key]',
                        '[class*="goodsRow"]',
                        '[class*="goods-item"]',
                        '[class*="goodsItem"]',
                        'div[id][class*="Row"]',
                    ];
                    
                    for (var s = 0; s < rowSelectors.length; s++) {
                        var rows = document.querySelectorAll(rowSelectors[s]);
                        if (rows.length > 0) {
                            for (var i = 0; i < rows.length; i++) {
                                var row = rows[i];
                                
                                // 尝试多种方式获取商品名称
                                var nameEl = row.querySelector('[class*="goodsName"]') || 
                                            row.querySelector('[class*="name"]') ||
                                            row.querySelector('[class*="title"]') ||
                                            row.querySelector('[class*="Name"]') ||
                                            row.querySelector('[class*="Title"]') ||
                                            row.querySelector('td:nth-child(2)');
                                
                                if (nameEl) {
                                    var name = (nameEl.innerText || nameEl.textContent || '').trim();
                                    // 清理名称：去除换行和多余空格
                                    name = name.replace(/\\s+/g, ' ').trim();
                                    // 过滤掉太短或太长的
                                    if (name && name.length > 1 && name.length < 100) {
                                        // 避免重复
                                        var exists = false;
                                        for (var j = 0; j < goods.length; j++) {
                                            if (goods[j].name === name) {
                                                exists = true;
                                                break;
                                            }
                                        }
                                        if (!exists) {
                                            goods.push({name: name});
                                        }
                                    }
                                }
                            }
                            if (goods.length > 0) break;
                        }
                    }
                    
                    return goods;
                })()
            '''
            
            return await frame.evaluate(js_script) or []
        except Exception as e:
            logger.error(f"解析当前页面商品出错: {e}")
            return []
    
    async def _check_page_health(self, page, page_id: int) -> bool:
        """
        检测页面是否健康（未崩溃）
        返回True表示页面健康，False表示页面崩溃或无响应
        """
        try:
            # 方法1: 尝试获取页面URL（最快的检测方式）
            url = page.url
            if not url:
                logger.warning(f"[P{page_id}] 页面URL为空")
                return False
            
            # 方法2: 尝试执行简单的JavaScript（检测页面是否响应）
            try:
                result = await asyncio.wait_for(
                    page.evaluate("() => document.readyState"),
                    timeout=10.0
                )
                if result not in ['loading', 'interactive', 'complete']:
                    logger.warning(f"[P{page_id}] 页面状态异常: {result}")
                    return False
            except asyncio.TimeoutError:
                logger.warning(f"[P{page_id}] 页面无响应（JavaScript执行超时）")
                return False
            except Exception as e:
                error_msg = str(e).lower()
                # 检测常见的崩溃错误信息
                crash_keywords = ['crash', 'target closed', 'page closed', 
                                  'execution context', 'destroyed', 'detached',
                                  'not connected', 'connection closed']
                if any(kw in error_msg for kw in crash_keywords):
                    logger.warning(f"[P{page_id}] 检测到页面崩溃: {e}")
                    return False
                raise
            
            # 方法3: 检测页面标题是否包含崩溃关键词
            try:
                title = await page.title()
                crash_titles = ['崩溃', 'crash', 'aw, snap', '喔唷']
                if any(ct in title.lower() for ct in crash_titles):
                    logger.warning(f"[P{page_id}] 页面标题显示崩溃: {title}")
                    return False
            except:
                pass
            
            return True
            
        except Exception as e:
            logger.warning(f"[P{page_id}] 页面健康检测失败: {e}")
            return False
    
    async def _recover_page(self, context, page, page_id: int, goods_url: str) -> tuple:
        """
        恢复崩溃的页面
        返回 (new_page, success)
        """
        self.log(f"[P{page_id}] 🔄 正在恢复页面...")
        
        try:
            # 尝试关闭旧页面（可能会失败，忽略错误）
            try:
                await page.close()
            except:
                pass
            
            # 创建新页面
            new_page = await context.new_page()
            
            # 导航到商品管理页面
            await new_page.goto(goods_url, wait_until='load', timeout=60000)
            await asyncio.sleep(3)
            
            # 验证新页面是否健康
            if await self._check_page_health(new_page, page_id):
                self.log(f"[P{page_id}] ✓ 页面恢复成功")
                return new_page, True
            else:
                self.log(f"[P{page_id}] ✗ 页面恢复后仍不健康")
                return new_page, False
                
        except Exception as e:
            self.log(f"[P{page_id}] ✗ 页面恢复失败: {e}")
            return page, False
    
    async def _refresh_page(self, page, page_id: int) -> bool:
        """
        刷新页面并等待加载完成
        返回True表示刷新成功
        """
        try:
            self.log(f"[P{page_id}] 🔄 正在刷新页面...")
            await page.reload(wait_until='load', timeout=60000)
            await asyncio.sleep(3)
            
            if await self._check_page_health(page, page_id):
                self.log(f"[P{page_id}] ✓ 页面刷新成功")
                return True
            else:
                self.log(f"[P{page_id}] ✗ 页面刷新后仍不健康")
                return False
        except Exception as e:
            self.log(f"[P{page_id}] ✗ 页面刷新失败: {e}")
            return False

    async def _switch_shop_with_lock(
        self,
        page,
        shop,
        page_id: int,
    ) -> Tuple[bool, dict]:
        """
        串行切换门店（使用锁保护）
        
        Returns:
            (是否成功, switch_result字典)
        """
        short_name = self._simplify_shop_name(shop.name)
        max_retries = 2
        
        if self._shop_switch_lock:
            self.log(f"[P{page_id}] 🔒 等待门店切换锁...")
            async with self._shop_switch_lock:
                self.log(f"[P{page_id}] 🔓 获得锁，开始切换到: {short_name}")
                
                # 切换门店（带重试机制）
                for attempt in range(max_retries + 1):
                    switch_result = await self._switch_shop(page, shop.name)
                    
                    if switch_result['success']:
                        if attempt > 0:
                            self.log(f"[P{page_id}] ✓ 第{attempt+1}次尝试切换成功")
                        self.log(f"[P{page_id}] 🔓 释放锁")
                        return True, switch_result
                    
                    last_reason = switch_result.get('reason', '切换失败')
                    
                    if attempt < max_retries:
                        self.log(f"[P{page_id}] 🔄 切换失败({last_reason})，第{attempt+2}次尝试...")
                        await self._ensure_goods_page(page)
                        await asyncio.sleep(2)
                    else:
                        self.log(f"[P{page_id}] ✗ 切换失败(重试{max_retries}次): {last_reason}")
                        self.log(f"[P{page_id}] 🔓 释放锁")
                        return False, {'reason': f"切换失败(重试{max_retries}次): {last_reason}"}
        else:
            # 无锁模式
            for attempt in range(max_retries + 1):
                switch_result = await self._switch_shop(page, shop.name)
                
                if switch_result['success']:
                    if attempt > 0:
                        self.log(f"[P{page_id}] ✓ 第{attempt+1}次尝试切换成功")
                    return True, switch_result
                
                last_reason = switch_result.get('reason', '切换失败')
                
                if attempt < max_retries:
                    self.log(f"[P{page_id}] 🔄 切换失败({last_reason})，第{attempt+2}次尝试...")
                    await self._ensure_goods_page(page)
                    await asyncio.sleep(2)
                else:
                    return False, {'reason': f"切换失败(重试{max_retries}次): {last_reason}"}
        
        return False, {'reason': '未知错误'}
    
    async def _fetch_goods_parallel(
        self,
        page,
        shop,
        page_id: int,
        switch_result: dict,
        shop_start: float,
        send_notification_callback: Callable = None,
    ) -> ShopResult:
        """
        并行抓取商品数据（无需锁）
        """
        short_name = self._simplify_shop_name(shop.name)
        shop_status = switch_result.get('shop_status', '营业中')
        
        try:
            # 确保页面在商品管理页面
            await self._ensure_goods_page(page)
            
            # 抓取商品数据
            self.log(f"[P{page_id}] 📦 开始抓取: {short_name}")
            off_sale, sold_out = await self._fetch_goods(page)
            
            duration = time.time() - shop_start
            self.log(f"[P{page_id}] ✓ {short_name}: 下架{len(off_sale)} 售罄{len(sold_out)} ({duration:.1f}秒)")
            
            # 发送通知
            if send_notification_callback and (off_sale or sold_out):
                try:
                    send_notification_callback(shop, off_sale, sold_out, shop_status, duration)
                except Exception as e:
                    self.log(f"[P{page_id}] 通知发送失败: {e}")
            
            return ShopResult(
                shop_name=shop.name,
                short_name=short_name,
                success=True,
                off_sale=off_sale,
                sold_out=sold_out,
                duration=duration,
                shop_status=shop_status,
            )
        except Exception as e:
            return ShopResult(
                shop_name=shop.name,
                short_name=short_name,
                success=False,
                error=str(e),
                skipped=True,
                skip_reason=str(e),
                duration=time.time() - shop_start,
            )

    async def _monitor_single_shop(
        self,
        page,
        shop,
        page_id: int,
        send_notification_callback: Callable = None,
    ) -> ShopResult:
        """监控单个门店（完整流程：切换+抓取，用于单页面串行模式）"""
        shop_start = time.time()
        short_name = self._simplify_shop_name(shop.name)
        
        try:
            self.log(f"[P{page_id}] 正在监控: {short_name}")
            
            # 阶段1：串行切换门店
            success, switch_result = await self._switch_shop_with_lock(page, shop, page_id)
            
            if not success:
                return ShopResult(
                    shop_name=shop.name,
                    short_name=short_name,
                    success=False,
                    skipped=True,
                    skip_reason=switch_result.get('reason', '切换失败'),
                    duration=time.time() - shop_start,
                )
            
            shop_status = switch_result.get('shop_status', '营业中')
            
            # 检查门店营业状态
            if self.only_open_shops and shop_status != '营业中':
                self.log(f"[P{page_id}] ⏭ {short_name}: {shop_status}，跳过")
                return ShopResult(
                    shop_name=shop.name,
                    short_name=short_name,
                    success=True,
                    skipped=True,
                    skip_reason=f"门店{shop_status}",
                    duration=time.time() - shop_start,
                    shop_status=shop_status,
                )
            
            # 阶段2：抓取数据
            return await self._fetch_goods_parallel(
                page, shop, page_id, switch_result, shop_start, send_notification_callback
            )
            
        except Exception as e:
            return ShopResult(
                shop_name=shop.name,
                short_name=short_name,
                success=False,
                error=str(e),
                skipped=True,
                skip_reason=str(e),
                duration=time.time() - shop_start,
            )
    
    async def _monitor_batch_parallel(
        self,
        worker_pages: List,
        batch_shops: List,
        send_notification_callback: Callable = None,
    ) -> List[ShopResult]:
        """
        批次并行监控：串行切换门店 + 并行抓取数据
        
        工作流程：
        1. 阶段1 - 串行切换：所有页面依次切换到各自的目标门店（使用锁）
        2. 阶段2 - 并行抓取：所有页面同时抓取数据（无需锁）
        3. 等待所有页面完成后返回结果
        """
        results = []
        batch_size = len(batch_shops)
        
        self.log(f"")
        self.log(f"📋 批次处理: {batch_size} 个门店")
        
        # 记录每个页面的任务信息
        page_tasks = []  # [(page, shop, page_id, shop_start, switch_result)]
        
        # ========== 阶段1：串行切换所有门店 ==========
        self.log(f"🔄 阶段1: 串行切换门店...")
        for i, shop in enumerate(batch_shops):
            page_id = i % len(worker_pages)
            page = worker_pages[page_id]
            short_name = self._simplify_shop_name(shop.name)
            shop_start = time.time()
            
            self.log(f"[P{page_id}] 正在切换到: {short_name}")
            
            # 串行切换门店（使用锁）
            success, switch_result = await self._switch_shop_with_lock(page, shop, page_id)
            
            if not success:
                results.append(ShopResult(
                    shop_name=shop.name,
                    short_name=short_name,
                    success=False,
                    skipped=True,
                    skip_reason=switch_result.get('reason', '切换失败'),
                    duration=time.time() - shop_start,
                ))
            else:
                shop_status = switch_result.get('shop_status', '营业中')
                
                # 检查门店营业状态
                if self.only_open_shops and shop_status != '营业中':
                    self.log(f"[P{page_id}] ⏭ {short_name}: {shop_status}，跳过")
                    results.append(ShopResult(
                        shop_name=shop.name,
                        short_name=short_name,
                        success=True,
                        skipped=True,
                        skip_reason=f"门店{shop_status}",
                        duration=time.time() - shop_start,
                        shop_status=shop_status,
                    ))
                else:
                    # 记录任务，稍后并行抓取
                    page_tasks.append((page, shop, page_id, shop_start, switch_result))
        
        if not page_tasks:
            return results
        
        # ========== 阶段2：并行抓取所有数据 ==========
        self.log(f"📦 阶段2: 并行抓取数据 ({len(page_tasks)} 个门店)...")
        
        fetch_tasks = []
        for page, shop, page_id, shop_start, switch_result in page_tasks:
            task = asyncio.create_task(
                self._fetch_goods_parallel(
                    page, shop, page_id, switch_result, shop_start, send_notification_callback
                )
            )
            fetch_tasks.append(task)
        
        # 等待所有抓取任务完成
        fetch_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
        
        for result in fetch_results:
            if isinstance(result, Exception):
                self.log(f"⚠ 抓取异常: {result}")
            else:
                results.append(result)
        
        self.log(f"✓ 批次完成: 成功 {sum(1 for r in results if r.success)} / 总计 {len(results)}")
        
        return results

    async def _monitor_single_shop_legacy(
        self,
        page,
        shop,
        page_id: int,
        send_notification_callback: Callable = None,
    ) -> ShopResult:
        """监控单个门店（旧版完整流程，保留兼容）"""
        shop_start = time.time()
        short_name = self._simplify_shop_name(shop.name)
        
        try:
            self.log(f"[P{page_id}] 正在监控: {short_name}")
            
            # 切换门店
            success, switch_result = await self._switch_shop_with_lock(page, shop, page_id)
            
            if not success:
                return ShopResult(
                    shop_name=shop.name,
                    short_name=short_name,
                    success=False,
                    skipped=True,
                    skip_reason=switch_result.get('reason', '切换失败'),
                    duration=time.time() - shop_start,
                )
            
            shop_status = switch_result.get('shop_status', '营业中')
            
            if self.only_open_shops and shop_status != '营业中':
                self.log(f"[P{page_id}] ⏭ {short_name}: {shop_status}，跳过")
                return ShopResult(
                    shop_name=shop.name,
                    short_name=short_name,
                    success=True,
                    skipped=True,
                    skip_reason=f"门店{shop_status}",
                    duration=time.time() - shop_start,
                    shop_status=shop_status,
                )
            
            # 抓取数据
            return await self._fetch_goods_parallel(
                page, shop, page_id, switch_result, shop_start, send_notification_callback
            )
            
        except Exception as e:
            return ShopResult(
                shop_name=shop.name,
                short_name=short_name,
                success=False,
                error=str(e),
                skipped=True,
                skip_reason=str(e),
                duration=time.time() - shop_start,
            )
    
    async def _old_monitor_single_shop(
        self,
        page,
        shop,
        page_id: int,
        send_notification_callback: Callable = None,
    ) -> ShopResult:
        """旧版监控单个门店（保留备用）"""
        shop_start = time.time()
        short_name = self._simplify_shop_name(shop.name)
        max_retries = 2
        
        try:
            self.log(f"[P{page_id}] 正在监控: {short_name}")
            
            # 切换门店
            for attempt in range(max_retries + 1):
                switch_result = await self._switch_shop(page, shop.name)
                
                if switch_result['success']:
                    if attempt > 0:
                        self.log(f"[P{page_id}] ✓ 第{attempt+1}次尝试切换成功")
                    break
                
                last_reason = switch_result.get('reason', '切换失败')
                
                if attempt < max_retries:
                    self.log(f"[P{page_id}] 🔄 切换失败({last_reason})，第{attempt+2}次尝试...")
                    await self._ensure_goods_page(page)
                    await asyncio.sleep(2)
                else:
                    return ShopResult(
                        shop_name=shop.name,
                        short_name=short_name,
                        success=False,
                        skipped=True,
                        skip_reason=f"切换失败(重试{max_retries}次): {last_reason}",
                        duration=time.time() - shop_start,
                    )
            
            shop_status = switch_result.get('shop_status', '营业中')
            
            if self.only_open_shops and shop_status != '营业中':
                self.log(f"[P{page_id}] ⏭ {short_name}: {shop_status}，跳过")
                return ShopResult(
                    shop_name=shop.name,
                    short_name=short_name,
                    success=True,
                    skipped=True,
                    skip_reason=f"门店{shop_status}",
                    duration=time.time() - shop_start,
                    shop_status=shop_status,
                )
            
            await self._ensure_goods_page(page)
            off_sale, sold_out = await self._fetch_goods(page)
            
            duration = time.time() - shop_start
            self.log(f"[P{page_id}] ✓ {short_name}: 下架{len(off_sale)} 售罄{len(sold_out)} ({duration:.1f}秒)")
            
            # 发送通知（包含耗时信息）
            if send_notification_callback and (off_sale or sold_out):
                try:
                    send_notification_callback(shop, off_sale, sold_out, shop_status, duration)
                except Exception as e:
                    self.log(f"[P{page_id}] 通知发送失败: {e}")
            
            return ShopResult(
                shop_name=shop.name,
                short_name=short_name,
                success=True,
                off_sale=off_sale,
                sold_out=sold_out,
                duration=duration,
                shop_status=switch_result.get('shop_status', '营业中'),
            )
            
        except Exception as e:
            return ShopResult(
                shop_name=shop.name,
                short_name=short_name,
                success=False,
                error=str(e),
                skipped=True,
                skip_reason=str(e),
                duration=time.time() - shop_start,
            )
    
    async def _run_parallel_async(
        self,
        shops: List,
        send_notification_callback: Callable = None,
    ) -> Dict:
        """
        异步监控所有门店
        
        注意：淘宝商家后台的门店切换是会话级别的（服务端存储），
        不是标签页级别的。因此使用锁来串行切换门店，避免互相干扰。
        """
        
        # 初始化门店切换锁（必须在异步环境中创建）
        self._shop_switch_lock = asyncio.Lock()
        
        # 确保Playwright浏览器已安装
        if not ensure_playwright_browsers(self.log_callback):
            self.log("✗ Playwright浏览器未安装，无法使用并行监控")
            return {
                'shops_monitored': 0,
                'shops_skipped': len(shops),
                'total_off_sale': 0,
                'total_sold_out': 0,
                'shop_results': [],
                'skipped_shops': [{'name': s.name, 'reason': 'Playwright未安装'} for s in shops],
                'total_duration': 0,
            }
        
        from playwright.async_api import async_playwright
        
        total_shops = len(shops)
        
        self.log(f"")
        self.log(f"{'='*50}")
        self.log(f"🚀 启动Playwright监控（批次并行模式）")
        self.log(f"   门店总数: {total_shops}")
        self.log(f"   并行页面: {self.parallel_workers}")
        self.log(f"   模式: 串行切换门店 + 并行抓取数据")
        self.log(f"{'='*50}")
        
        all_results = {
            'shops_monitored': 0,
            'shops_skipped': 0,
            'total_off_sale': 0,
            'total_sold_out': 0,
            'shop_results': [],
            'skipped_shops': [],
            'total_duration': 0,
        }
        
        monitor_start = time.time()
        
        try:
            async with async_playwright() as p:
                # 启动浏览器
                self.log(f"   正在启动浏览器...")
                
                # 获取持久化目录
                persistent_dir = self._get_persistent_dir()
                user_data_dir = os.path.join(persistent_dir, 'playwright_profile')
                
                # 使用持久化上下文（保存登录状态）
                self.context = await p.chromium.launch_persistent_context(
                    user_data_dir,
                    headless=False,
                    args=['--disable-blink-features=AutomationControlled'],
                    viewport={'width': 1280, 'height': 800},
                )
                
                self.log(f"   ✓ 浏览器启动成功")
                
                # 获取或创建第一个页面用于登录
                pages = self.context.pages
                if not pages:
                    main_page = await self.context.new_page()
                else:
                    main_page = pages[0]
                
                # 导航到商品管理页面
                base_url = self.config.base_url if self.config else "https://e.taobao.com"
                shop_id = self.config.shop_id if self.config else ""
                goods_url = f"{base_url}/app/shop/{shop_id}/food#app.shop.food?path=management"
                
                self.log(f"   正在导航到商品管理页面...")
                # 使用load而非networkidle，避免超时
                await main_page.goto(goods_url, wait_until='load', timeout=60000)
                await asyncio.sleep(5)  # 等待页面JS渲染
                
                # 检查登录状态
                if await self._need_login(main_page):
                    self.log(f"")
                    self.log(f"   ⚠ 首次使用需要登录！")
                    self.log(f"   请在弹出的Playwright浏览器窗口中完成登录")
                    self.log(f"   登录后程序会自动继续...")
                    self.log(f"")
                    # 等待用户登录（最多10分钟）
                    for i in range(120):
                        await asyncio.sleep(5)
                        if not await self._need_login(main_page):
                            self.log(f"   ✓ 检测到登录成功！")
                            break
                        if i % 12 == 0 and i > 0:  # 每分钟提示一次
                            self.log(f"   等待登录中... ({i//12}分钟)")
                    
                    if await self._need_login(main_page):
                        self.log(f"   ✗ 登录超时（10分钟），请重试")
                        return all_results
                else:
                    self.log(f"   ✓ 登录状态正常")
                
                # ========== 创建多个页面用于批次并行 ==========
                worker_pages = [main_page]  # 第一个页面已经准备好
                num_workers = min(self.parallel_workers, total_shops)
                
                self.log(f"   正在创建 {num_workers} 个并行页面...")
                for i in range(1, num_workers):
                    try:
                        new_page = await self.context.new_page()
                        await new_page.goto(goods_url, wait_until='load', timeout=60000)
                        await asyncio.sleep(2)
                        worker_pages.append(new_page)
                    except Exception as e:
                        self.log(f"   ⚠ 创建页面 {i} 失败: {e}")
                
                self.log(f"   ✓ 已创建 {len(worker_pages)} 个并行页面")
                
                # ========== 批次并行处理门店 ==========
                # 策略：串行切换门店 + 并行抓取数据
                batch_size = len(worker_pages)
                batch_num = 0
                
                self.log(f"")
                
                for batch_start in range(0, total_shops, batch_size):
                    if not self.running:
                        break
                    
                    batch_num += 1
                    batch_end = min(batch_start + batch_size, total_shops)
                    batch_shops = shops[batch_start:batch_end]
                    
                    self.log(f"{'='*50}")
                    self.log(f"📋 批次 {batch_num}: 门店 {batch_start+1}-{batch_end} / {total_shops}")
                    self.log(f"{'='*50}")
                    
                    # ========== 阶段1：串行切换门店（一个接一个） ==========
                    self.log(f"🔄 阶段1: 串行切换门店...")
                    switch_tasks = []  # [(page_id, page, shop, shop_start, switch_result)]
                    
                    for i, shop in enumerate(batch_shops):
                        if not self.running:
                            break
                        
                        page_id = i % len(worker_pages)
                        page = worker_pages[page_id]
                        short_name = self._simplify_shop_name(shop.name)
                        shop_start = time.time()
                        
                        self.log(f"[P{page_id}] 正在切换到: {short_name}")
                        
                        # 串行切换门店（使用锁）
                        success, switch_result = await self._switch_shop_with_lock(page, shop, page_id)
                        
                        if not success:
                            all_results['shops_skipped'] += 1
                            all_results['skipped_shops'].append({
                                'name': shop.name,
                                'short_name': short_name,
                                'reason': switch_result.get('reason', '切换失败'),
                                'status': '',
                                'duration': time.time() - shop_start,
                            })
                        else:
                            shop_status = switch_result.get('shop_status', '营业中')
                            
                            # 检查门店营业状态
                            if self.only_open_shops and shop_status != '营业中':
                                self.log(f"[P{page_id}] ⏭ {short_name}: {shop_status}，跳过")
                                all_results['shops_skipped'] += 1
                                all_results['skipped_shops'].append({
                                    'name': shop.name,
                                    'short_name': short_name,
                                    'reason': f"门店{shop_status}",
                                    'status': shop_status,
                                    'duration': time.time() - shop_start,
                                })
                            else:
                                # 记录任务，稍后并行抓取
                                switch_tasks.append((page_id, page, shop, shop_start, switch_result))
                    
                    if not switch_tasks:
                        continue
                    
                    # ========== 阶段2：并行抓取数据 ==========
                    self.log(f"📦 阶段2: 并行抓取数据 ({len(switch_tasks)} 个门店)...")
                    
                    fetch_coroutines = []
                    for page_id, page, shop, shop_start, switch_result in switch_tasks:
                        coro = self._fetch_goods_parallel(
                            page, shop, page_id, switch_result, shop_start, send_notification_callback
                        )
                        fetch_coroutines.append(coro)
                    
                    # 等待所有抓取任务完成
                    fetch_results = await asyncio.gather(*fetch_coroutines, return_exceptions=True)
                    
                    # 处理结果
                    for result in fetch_results:
                        if isinstance(result, Exception):
                            self.log(f"⚠ 抓取异常: {result}")
                        elif result.success:
                            all_results['shops_monitored'] += 1
                            all_results['total_off_sale'] += len(result.off_sale or [])
                            all_results['total_sold_out'] += len(result.sold_out or [])
                            all_results['shop_results'].append({
                                'shop_name': result.shop_name,
                                'short_name': result.short_name,
                                'off_sale': result.off_sale,
                                'sold_out': result.sold_out,
                                'duration': result.duration,
                                'shop_status': result.shop_status,
                            })
                        else:
                            all_results['shops_skipped'] += 1
                            all_results['skipped_shops'].append({
                                'name': result.shop_name,
                                'short_name': result.short_name,
                                'reason': result.skip_reason,
                                'status': result.shop_status if result.shop_status != '营业中' else '',
                                'duration': result.duration,
                            })
                    
                    self.log(f"✓ 批次 {batch_num} 完成")
                
                # ========== 多遍轮巡：批次并行重试因操作原因失败的门店 ==========
                retry_reasons = ['切换失败', '验证失败', '未找到门店', '页面异常', '超时']
                retry_round = 0
                retry_timeout_seconds = self.retry_timeout_minutes * 60
                
                while self.running:
                    # 检查是否超时
                    elapsed = time.time() - monitor_start
                    if elapsed >= retry_timeout_seconds:
                        self.log(f"⏱ 总耗时已达 {self.retry_timeout_minutes} 分钟，停止重试")
                        break
                    
                    # 收集需要重试的门店（排除因门店状态跳过的）
                    retry_shops = []
                    for skip_info in all_results['skipped_shops']:
                        reason = skip_info.get('reason', '')
                        # 如果是操作原因导致的失败，加入重试列表
                        if any(r in reason for r in retry_reasons):
                            shop_name = skip_info.get('name', '')
                            # 找到对应的shop对象
                            for shop in shops:
                                if shop.name == shop_name:
                                    retry_shops.append(shop)
                                    break
                    
                    if not retry_shops:
                        break  # 没有需要重试的门店
                    
                    retry_round += 1
                    remaining_time = int(retry_timeout_seconds - elapsed)
                    self.log(f"")
                    self.log(f"{'='*50}")
                    self.log(f"🔄 第 {retry_round} 轮重试：{len(retry_shops)} 个失败门店 (剩余 {remaining_time//60}分{remaining_time%60}秒)")
                    self.log(f"{'='*50}")
                    
                    # 从skipped_shops中移除要重试的门店
                    retry_shop_names = {shop.name for shop in retry_shops}
                    all_results['skipped_shops'] = [
                        s for s in all_results['skipped_shops'] 
                        if s.get('name', '') not in retry_shop_names
                    ]
                    all_results['shops_skipped'] -= len(retry_shops)
                    
                    # 检查页面健康状态并恢复
                    for page_id, page in enumerate(worker_pages):
                        try:
                            if not await self._check_page_health(page, page_id):
                                self.log(f"[P{page_id}] ⚠ 重试前检测到页面异常，尝试恢复...")
                                if not await self._refresh_page(page, page_id):
                                    new_page, _ = await self._recover_page(
                                        self.context, page, page_id, goods_url
                                    )
                                    worker_pages[page_id] = new_page
                            else:
                                await self._ensure_goods_page(page)
                        except:
                            pass
                    
                    await asyncio.sleep(2)
                    
                    # 批次并行重试
                    retry_batch_size = len(worker_pages)
                    for retry_batch_start in range(0, len(retry_shops), retry_batch_size):
                        if not self.running:
                            break
                        
                        # 检查超时
                        if time.time() - monitor_start >= retry_timeout_seconds:
                            self.log(f"⏱ 重试超时，取消剩余任务")
                            # 将剩余门店标记为跳过
                            for remaining_shop in retry_shops[retry_batch_start:]:
                                all_results['shops_skipped'] += 1
                                all_results['skipped_shops'].append({
                                    'name': remaining_shop.name,
                                    'short_name': self._simplify_shop_name(remaining_shop.name),
                                    'reason': f"重试超时",
                                    'status': '',
                                    'duration': 0,
                                })
                            break
                        
                        retry_batch_end = min(retry_batch_start + retry_batch_size, len(retry_shops))
                        retry_batch = retry_shops[retry_batch_start:retry_batch_end]
                        
                        self.log(f"🔄 重试批次: {retry_batch_start+1}-{retry_batch_end} / {len(retry_shops)}")
                        
                        # 阶段1：串行切换门店
                        retry_switch_tasks = []
                        for i, shop in enumerate(retry_batch):
                            page_id = i % len(worker_pages)
                            page = worker_pages[page_id]
                            short_name = self._simplify_shop_name(shop.name)
                            shop_start = time.time()
                            
                            self.log(f"[P{page_id}] 🔄 重试切换到: {short_name}")
                            
                            success, switch_result = await self._switch_shop_with_lock(page, shop, page_id)
                            
                            if not success:
                                all_results['shops_skipped'] += 1
                                all_results['skipped_shops'].append({
                                    'name': shop.name,
                                    'short_name': short_name,
                                    'reason': switch_result.get('reason', '切换失败'),
                                    'status': '',
                                    'duration': time.time() - shop_start,
                                })
                            else:
                                shop_status = switch_result.get('shop_status', '营业中')
                                if self.only_open_shops and shop_status != '营业中':
                                    self.log(f"[P{page_id}] ⏭ {short_name}: {shop_status}，跳过")
                                    all_results['shops_skipped'] += 1
                                    all_results['skipped_shops'].append({
                                        'name': shop.name,
                                        'short_name': short_name,
                                        'reason': f"门店{shop_status}",
                                        'status': shop_status,
                                        'duration': time.time() - shop_start,
                                    })
                                else:
                                    retry_switch_tasks.append((page_id, page, shop, shop_start, switch_result))
                        
                        if retry_switch_tasks:
                            # 阶段2：并行抓取数据
                            self.log(f"📦 并行抓取 {len(retry_switch_tasks)} 个门店...")
                            
                            retry_fetch_coroutines = []
                            for page_id, page, shop, shop_start, switch_result in retry_switch_tasks:
                                coro = self._fetch_goods_parallel(
                                    page, shop, page_id, switch_result, shop_start, send_notification_callback
                                )
                                retry_fetch_coroutines.append(coro)
                            
                            retry_fetch_results = await asyncio.gather(*retry_fetch_coroutines, return_exceptions=True)
                            
                            for result in retry_fetch_results:
                                if isinstance(result, Exception):
                                    self.log(f"⚠ 重试抓取异常: {result}")
                                elif result.success:
                                    self.log(f"✓ 重试成功: {result.short_name}")
                                    all_results['shops_monitored'] += 1
                                    all_results['total_off_sale'] += len(result.off_sale or [])
                                    all_results['total_sold_out'] += len(result.sold_out or [])
                                    all_results['shop_results'].append({
                                        'shop_name': result.shop_name,
                                        'short_name': result.short_name,
                                        'off_sale': result.off_sale,
                                        'sold_out': result.sold_out,
                                        'duration': result.duration,
                                        'shop_status': result.shop_status,
                                    })
                                else:
                                    self.log(f"✗ 重试失败: {result.short_name}")
                                    all_results['shops_skipped'] += 1
                                    all_results['skipped_shops'].append({
                                        'name': result.shop_name,
                                        'short_name': result.short_name,
                                        'reason': result.skip_reason,
                                        'status': result.shop_status if result.shop_status != '营业中' else '',
                                        'duration': result.duration,
                                    })
                    
                    self.log(f"🔄 第 {retry_round} 轮重试完成")
                
                all_results['total_duration'] = time.time() - monitor_start
                
        except Exception as e:
            self.log(f"✗ Playwright监控出错: {e}")
            import traceback
            traceback.print_exc()
        
        return all_results
    
    async def _need_login(self, page) -> bool:
        """检查是否需要登录"""
        try:
            url = page.url.lower()
            login_keywords = ['login', 'signin', 'passport']
            if any(kw in url for kw in login_keywords):
                return True
            
            # 检查页面内容
            content = await page.content()
            if '请登录' in content or '立即登录' in content:
                return True
            
            return False
        except:
            return True
    
    def _get_persistent_dir(self) -> str:
        """获取持久化目录"""
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        else:
            return os.path.dirname(os.path.abspath(__file__))
    
    def run_parallel_monitor(
        self,
        shops: List,
        send_notification_callback: Callable = None,
    ) -> Dict:
        """
        运行并行监控（同步入口）
        """
        # 在新的事件循环中运行异步代码
        try:
            # Windows下需要设置事件循环策略
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                return loop.run_until_complete(
                    self._run_parallel_async(shops, send_notification_callback)
                )
            finally:
                loop.close()
        except Exception as e:
            self.log(f"✗ 运行并行监控出错: {e}")
            return {
                'shops_monitored': 0,
                'shops_skipped': len(shops),
                'total_off_sale': 0,
                'total_sold_out': 0,
                'shop_results': [],
                'skipped_shops': [{'name': s.name, 'reason': str(e)} for s in shops],
                'total_duration': 0,
            }
    
    def stop(self, close_browser: bool = True):
        """
        停止监控
        
        Args:
            close_browser: 是否关闭浏览器
                          False = 只停止监控任务，保留浏览器
                          True = 停止监控并关闭浏览器
        """
        self.running = False
        
        # 只有在需要关闭浏览器时才执行关闭操作
        if close_browser and self.context:
            try:
                # 使用asyncio关闭
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(self.context.close())
                    else:
                        asyncio.run(self.context.close())
                except:
                    pass
            except:
                pass
            self.context = None
