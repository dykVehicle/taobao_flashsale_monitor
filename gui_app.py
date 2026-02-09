#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
淘宝闪购智能助手Agent - Windows桌面应用程序
带GUI界面，支持账号密码登录
"""

import os
import sys
import time
import threading
from datetime import datetime
from typing import Optional, List

# 确保依赖
def ensure_gui_dependencies():
    """安装GUI依赖"""
    import subprocess
    required = {
        'PyQt6': 'PyQt6',
        'cryptography': 'cryptography',
    }
    missing = []
    for import_name, package_name in required.items():
        try:
            __import__(import_name)
        except ImportError:
            missing.append(package_name)
    
    if missing:
        print(f"正在安装GUI依赖: {', '.join(missing)}...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-q"] + missing,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

ensure_gui_dependencies()

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QGroupBox, QFormLayout,
    QCheckBox, QSpinBox, QTabWidget, QMessageBox, QProgressBar,
    QStatusBar, QFrame, QScrollArea, QSplitter, QFileDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QIcon, QPalette, QColor, QTextCursor, QFontDatabase

from config_manager import ConfigManager, AppConfig
from shop_manager import ShopManager, ShopInfo
try:
    from version import get_version
except ImportError:
    # Fallback if version module is missing during dev or specific build contexts
    def get_version(): return "2.0"


class ShopLoadWorker(QThread):
    """门店列表加载线程（后台加载，避免UI卡死）"""
    finished_signal = pyqtSignal(bool, object)  # (success, shop_manager or error_msg)
    
    def __init__(self, shop_file: str, shop_manager: ShopManager):
        super().__init__()
        self.shop_file = shop_file
        self.shop_manager = shop_manager
    
    def run(self):
        try:
            success = self.shop_manager.load(self.shop_file)
            self.finished_signal.emit(success, self.shop_manager if success else "加载失败")
        except Exception as e:
            self.finished_signal.emit(False, str(e))


class MonitorWorker(QThread):
    """监控工作线程 - 支持多门店监控"""
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)
    login_required_signal = pyqtSignal()
    shop_result_signal = pyqtSignal(dict)  # 单个门店结果信号
    
    def __init__(self, config: AppConfig, profile_dir: str, auto_fill_login: bool = False, 
                 shops: List[ShopInfo] = None, check_interval: int = 30,
                 enable_parallel: bool = True, parallel_workers: int = 20,
                 only_open_shops: bool = False, retry_timeout_minutes: int = 30,
                 shop_manager = None):
        super().__init__()
        self.config = config
        self.profile_dir = profile_dir
        self.auto_fill_login = auto_fill_login
        self.shops = shops or []  # 门店列表
        self.retry_timeout_minutes = retry_timeout_minutes  # 重试超时时间
        self.check_interval = check_interval  # 监控间隔（分钟）
        self.enable_parallel = enable_parallel  # 是否启用并行监控
        self.parallel_workers = parallel_workers  # 并行worker数量
        self.only_open_shops = only_open_shops  # 只监控营业中的门店
        self.shop_manager = shop_manager  # 门店管理器（用于商品白名单过滤）
        self.running = True
        self.fetcher = None
        self.pw_monitor = None  # Playwright监控器
        self._is_cleaning_up = False
    
    def log(self, msg: str):
        if not self.running: return
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_signal.emit(f"[{timestamp}] {msg}")
    
    def run(self):
        try:
            from selenium_fetcher import SeleniumGoodsFetcher
            
            if not self.running: return
            self.log("正在初始化浏览器...")
            self.status_signal.emit("初始化中...")
            self.progress_signal.emit(10)
            
            # 创建抓取器
            self.fetcher = SeleniumGoodsFetcher(
                shop_id=self.config.shop_id,
                chain_id=self.config.chain_id,
                base_url=self.config.base_url,
                headless=self.config.headless,
                debug_port=self.config.debug_port,
                user_data_dir=self.profile_dir,
                browser_path=self.config.browser_path or None,
                auto_launch_browser=True,
            )
            
            if not self.running: return
            
            # 启动浏览器
            open_url = f"{self.config.base_url}/app/shop/{self.config.shop_id}/food#app.shop.food?path=management"
            self.log("正在查找浏览器...")
            self.progress_signal.emit(20)
            
            browser_path = self.fetcher._find_browser_executable()
            if browser_path:
                self.log(f"找到浏览器: {browser_path}")
            else:
                self.log("未找到浏览器，请检查是否安装了Chrome/Edge")
                self.error_signal.emit(
                    "无法找到浏览器！\n\n"
                    "请确保已安装以下浏览器之一：\n"
                    "• Microsoft Edge (Windows自带)\n"
                    "• Google Chrome\n"
                    "• Chromium\n\n"
                    "或在「高级设置」中手动指定浏览器路径"
                )
                return
            
            if not self.running: return
            self.log("正在启动浏览器...")
            if not self.fetcher.ensure_debug_browser(open_url=open_url):
                self.error_signal.emit(
                    "无法启动浏览器！\n\n"
                    f"浏览器路径: {browser_path}\n\n"
                    "可能的原因：\n"
                    "1. 浏览器正在被其他程序使用\n"
                    "2. 端口9222被占用\n"
                    "3. 权限不足\n\n"
                    "请尝试关闭所有浏览器窗口后重试"
                )
                return
            
            if not self.running: return
            self.log("浏览器已启动")
            self.progress_signal.emit(30)
            
            # 自动填充登录
            if self.auto_fill_login and self.config.taobao_username and self.config.taobao_password:
                if not self.running: return
                self.log("正在尝试自动登录...")
                self._try_auto_login()
            
            # 传递日志回调给 fetcher
            def log_callback(msg):
                if self.running:
                    self.log(msg)
            
            # 初始化Selenium驱动（多门店模式也需要）
            if not self.running: return
            self.log("正在初始化Selenium驱动...")
            if not self.fetcher._init_driver():
                self.error_signal.emit(
                    "无法初始化浏览器驱动！\n\n"
                    "请尝试：\n"
                    "1. 关闭所有浏览器窗口后重试\n"
                    "2. 检查是否有其他程序占用端口9222"
                )
                return
            self.log("✓ Selenium驱动初始化成功")
            
            # ========== 循环监控 ==========
            round_num = 1
            while self.running:
                if round_num > 1:
                    self.log(f"")
                    self.log(f"{'='*50}")
                    self.log(f"🔄 开始第 {round_num} 轮监控")
                    self.log(f"{'='*50}")
                
                # 多门店监控模式
                if self.shops:
                    self._run_multi_shop_monitor(log_callback)
                else:
                    # 单店铺模式（兼容旧逻辑）
                    self._run_single_shop_monitor(log_callback)
                
                if not self.running:
                    break
                
                # 倒计时等待下一轮
                interval_seconds = self.check_interval * 60
                self.log(f"")
                self.log(f"⏰ 下一轮监控将在 {self.check_interval} 分钟后开始")
                
                # 每秒更新倒计时
                remaining = interval_seconds
                while remaining > 0 and self.running:
                    mins = remaining // 60
                    secs = remaining % 60
                    if mins > 0:
                        self.status_signal.emit(f"⏳ 倒计时: {mins}分{secs:02d}秒")
                    else:
                        self.status_signal.emit(f"⏳ 倒计时: {secs}秒")
                    
                    time.sleep(1)
                    remaining -= 1
                
                round_num += 1
            
        except Exception as e:
            if self.running:
                self.error_signal.emit(f"监控出错: {str(e)}")
                import traceback
                self.log(f"错误详情: {traceback.format_exc()}")
        finally:
            if self.running:
                self._cleanup()
    
    def _run_multi_shop_monitor(self, log_callback):
        """多门店监控 - 支持串行和并行两种模式"""
        total_shops = len(self.shops)
        monitor_start_time = time.time()  # 记录总开始时间
        
        # 等待用户登录
        self.log("检查登录状态...")
        login_wait_start = time.time()
        login_timeout = 30 * 60  # 30分钟超时
        
        while self.running and self.fetcher._need_login():
            elapsed = time.time() - login_wait_start
            if elapsed > login_timeout:
                self.error_signal.emit("登录超时，请重新启动监控")
                return
            
            if elapsed < 5 or int(elapsed) % 30 == 0:  # 每30秒提示一次
                self.log(f"⏳ 请在浏览器中登录商家后台... (已等待 {int(elapsed)}秒)")
            time.sleep(2)
        
        if not self.running:
            return
        
        self.log("✓ 登录状态正常")
        
        # 设置日志回调
        self.fetcher._log_callback = log_callback
        
        # 先导航到商品管理页面
        self.log("导航到商品管理页面...")
        try:
            goods_url = f"{self.fetcher.base_url}/app/shop/{self.fetcher.shop_id}/food#app.shop.food?path=management"
            self.fetcher.driver.get(goods_url)
            time.sleep(5)
            self.log("✓ 已进入商品管理页面")
        except Exception as e:
            self.log(f"⚠ 导航失败: {e}")
        
        # 根据配置选择串行或并行模式
        if self.enable_parallel and self.parallel_workers > 1 and total_shops > 1:
            # 并行模式
            all_results = self._run_parallel_monitor(log_callback)
        else:
            # 串行模式（原有逻辑）
            all_results = self._run_serial_monitor(log_callback)
        
        # 完成处理
        if self.running and all_results:
            total_duration = time.time() - monitor_start_time
            all_results['total_duration'] = total_duration
            
            # 格式化总耗时
            if total_duration >= 60:
                duration_str = f"{int(total_duration // 60)}分{int(total_duration % 60)}秒"
            else:
                duration_str = f"{total_duration:.1f}秒"
            
            self.log(f"")
            self.log(f"{'='*50}")
            self.log(f"📊 多门店监控完成！")
            self.log(f"  ⏱ 总耗时: {duration_str}")
            self.log(f"  ✓ 监控成功: {all_results['shops_monitored']} 个门店")
            self.log(f"  ⏸ 跳过: {all_results['shops_skipped']} 个门店")
            self.log(f"  🔻 总计下架: {all_results['total_off_sale']} 个商品")
            self.log(f"  🔴 总计售罄: {all_results['total_sold_out']} 个商品")
            
            # 显示成功监控的门店
            if all_results['shop_results']:
                self.log(f"")
                self.log(f"✅ 成功监控的门店:")
                for sr in all_results['shop_results']:
                    short_name = sr.get('short_name', simplify_shop_name(sr.get('shop_name', '')))
                    off_count = len(sr.get('off_sale', []))
                    sold_count = len(sr.get('sold_out', []))
                    shop_dur = sr.get('duration', 0)
                    shop_status = sr.get('shop_status', '营业中')
                    status_text = "[营业]" if shop_status == "营业中" else f"[{shop_status}]"
                    self.log(f"   • {short_name} {status_text}: 下架{off_count}/售罄{sold_count} ({shop_dur:.1f}秒)")
            
            # 显示跳过的门店详情
            if all_results['skipped_shops']:
                self.log(f"")
                self.log(f"⏸ 跳过的门店列表:")
                for skip in all_results['skipped_shops']:
                    short_name = skip.get('short_name', simplify_shop_name(skip.get('name', '未知')))
                    skip_dur = skip.get('duration', 0)
                    status = skip.get('status', '')
                    reason = skip.get('reason', '未知原因')
                    if status:
                        self.log(f"   • {short_name} [{status}] - {reason} ({skip_dur:.1f}秒)")
                    else:
                        self.log(f"   • {short_name} - {reason}")
            
            self.log(f"{'='*50}")
            
            self.progress_signal.emit(100)
            self.status_signal.emit("完成")
            
            # 发送完成信号
            self.finished_signal.emit({
                'off_sale': [],
                'sold_out': [],
                'total': 0,
                'multi_shop': True,
                'all_results': all_results
            })
    
    def _run_parallel_monitor(self, log_callback):
        """并行监控模式 - 使用Playwright实现真正的并行"""
        try:
            from playwright_monitor import PlaywrightMonitor
        except ImportError as e:
            self.log(f"⚠ Playwright未安装，回退到串行模式")
            self.log(f"   请运行: pip install playwright && playwright install chromium")
            return self._run_serial_monitor(log_callback)
        
        self.log(f"")
        self.log(f"🚀 使用Playwright并行监控模式 (并行页面: {self.parallel_workers})")
        if self.only_open_shops:
            self.log(f"   ⏭ 只监控营业中的门店")
        
        try:
            # 创建Playwright并行监控器
            self.pw_monitor = PlaywrightMonitor(
                num_workers=self.parallel_workers,
                config=self.config,
                log_callback=log_callback,
                only_open_shops=self.only_open_shops,
                retry_timeout_minutes=self.retry_timeout_minutes,
                shop_manager=self.shop_manager,  # 传递门店管理器（用于商品白名单过滤）
            )
            
            # 定义发送通知的回调（包含耗时参数）
            # 始终发送通知，包括0商品时的正常状态鼓励消息
            def send_notification(shop, off_sale, sold_out, shop_status, duration=0):
                # 通知发送（企业微信 + WeChat）由 _send_shop_notification 内部判断：
                # - 企业微信：有 shop.webhook 才发送
                # - WeChat：由全局配置 enable_wechat_notification 决定
                self._send_shop_notification(shop, off_sale, sold_out, shop_status, duration)
            
            # 运行并行监控
            all_results = self.pw_monitor.run_parallel_monitor(
                shops=self.shops,
                send_notification_callback=send_notification,
            )
            
            # 检查是否所有门店都被跳过（说明Playwright安装失败）
            if all_results['shops_monitored'] == 0 and all_results['shops_skipped'] == len(self.shops):
                # 检查是否是因为Playwright未安装
                skip_reasons = [s.get('reason', '') for s in all_results.get('skipped_shops', [])]
                if any('Playwright' in r or '未安装' in r for r in skip_reasons):
                    self.log(f"")
                    self.log(f"⚠ Playwright不可用，自动回退到串行监控模式...")
                    return self._run_serial_monitor(log_callback)
            
            return all_results
        except Exception as e:
            self.log(f"⚠ Playwright监控出错: {e}")
            self.log(f"   回退到串行模式...")
            return self._run_serial_monitor(log_callback)
    
    def _run_serial_monitor(self, log_callback):
        """串行监控模式（原有逻辑）"""
        total_shops = len(self.shops)
        
        all_results = {
            'shops_monitored': 0,
            'shops_skipped': 0,
            'total_off_sale': 0,
            'total_sold_out': 0,
            'shop_results': [],
            'skipped_shops': [],
            'total_duration': 0,
        }
        
        self.log(f"")
        self.log(f"{'='*50}")
        self.log(f"开始多门店监控（串行模式），共 {total_shops} 个门店")
        self.log(f"{'='*50}")
        
        for idx, shop in enumerate(self.shops):
            if not self.running:
                break
            
            progress = 30 + int((idx / total_shops) * 60)
            short_name = simplify_shop_name(shop.name)
            
            self.progress_signal.emit(progress)
            self.status_signal.emit(f"监控中: {short_name} ({idx+1}/{total_shops})")
            
            shop_start_time = time.time()
            
            self.log(f"")
            self.log(f"┌{'─'*48}┐")
            self.log(f"│ [{idx+1}/{total_shops}] 正在监控: {short_name}")
            self.log(f"└{'─'*48}┘")
            
            # 切换门店
            self.log(f"   🔄 开始切换到门店: {short_name}")
            switch_result = self.fetcher.switch_shop(shop.name)
            
            if not switch_result['success']:
                shop_duration = time.time() - shop_start_time
                reason = switch_result.get('message', '未知原因')
                if not switch_result['is_open']:
                    self.log(f"   ⏸ 门店未营业，跳过: {reason} (耗时 {shop_duration:.1f}秒)")
                    all_results['skipped_shops'].append({
                        'name': shop.name,
                        'short_name': short_name,
                        'reason': reason,
                        'status': '未营业',
                        'duration': shop_duration
                    })
                else:
                    self.log(f"   ✗ 切换门店失败: {reason} (耗时 {shop_duration:.1f}秒)")
                    all_results['skipped_shops'].append({
                        'name': shop.name,
                        'short_name': short_name,
                        'reason': reason,
                        'status': '切换失败',
                        'duration': shop_duration
                    })
                all_results['shops_skipped'] += 1
                continue
            
            actual_shop_name = switch_result.get('shop_name', shop.name)
            self.log(f"   ✓ 门店切换成功: {actual_shop_name}")
            
            shop_status = "营业中"
            time.sleep(3)
            
            try:
                goods_list = self.fetcher.login_and_fetch(
                    auto_login=False,
                    wait_for_login=False,
                    login_timeout=60,
                    log_callback=log_callback,
                    skip_navigation=True,
                )
                
                off_sale = [g for g in goods_list if g.status == "OFF_SALE"]
                sold_out = [g for g in goods_list if g.status == "SOLD_OUT"]
                
                shop_duration = time.time() - shop_start_time
                
                shop_result = {
                    'shop': shop,
                    'shop_name': actual_shop_name,
                    'short_name': short_name,
                    'shop_status': shop_status,
                    'off_sale': off_sale,
                    'sold_out': sold_out,
                    'total': len(goods_list),
                    'success': True,
                    'duration': shop_duration
                }
                
                all_results['shops_monitored'] += 1
                all_results['total_off_sale'] += len(off_sale)
                all_results['total_sold_out'] += len(sold_out)
                all_results['shop_results'].append(shop_result)
                
                self.log(f"   ✓ 抓取完成: 下架 {len(off_sale)} 个, 售罄 {len(sold_out)} 个 (耗时 {shop_duration:.1f}秒)")
                
                # 发送通知：
                # - 企业微信：仅异常且配置了门店 webhook 才发
                # - WeChat：全局开关控制，可选“正常也发送”
                has_abnormal = len(off_sale) > 0 or len(sold_out) > 0
                should_send_wecom = has_abnormal and bool(shop.webhook)
                should_send_wechat = (
                    bool(getattr(self.config, 'enable_wechat_notification', False))
                    and (bool(getattr(self.config, 'wechat_send_normal', False)) or has_abnormal)
                )
                if should_send_wecom or should_send_wechat:
                    self._send_shop_notification(shop, off_sale, sold_out, shop_status, shop_duration, send_wecom=should_send_wecom)
                
                self.shop_result_signal.emit(shop_result)
                
            except Exception as e:
                self.log(f"   ✗ 抓取失败: {e}")
                all_results['shops_skipped'] += 1
        
        return all_results
    
    def _run_single_shop_monitor(self, log_callback):
        """单店铺监控（兼容旧逻辑）"""
        if not self.running: return
        self.log("开始抓取商品数据...")
        self.status_signal.emit("抓取中...")
        self.progress_signal.emit(50)
        
        goods_list = self.fetcher.login_and_fetch(
            auto_login=False,
            wait_for_login=True,
            login_timeout=30 * 60,
            log_callback=log_callback,
        )
        
        if not self.running: return
        self.progress_signal.emit(80)
        
        off_sale = [g for g in goods_list if g.status == "OFF_SALE"]
        sold_out = [g for g in goods_list if g.status == "SOLD_OUT"]
        
        result = {
            "off_sale": off_sale,
            "sold_out": sold_out,
            "total": len(goods_list),
        }
        
        if self.running:
            self.log(f"抓取完成！已下架: {len(off_sale)} 个, 已售罄: {len(sold_out)} 个")
            self.progress_signal.emit(100)
            self.status_signal.emit("完成")
            self.finished_signal.emit(result)
    
    def _send_shop_notification(
        self,
        shop: ShopInfo,
        off_sale_list,
        sold_out_list,
        shop_status: str = "营业中",
        duration: float = 0,
        send_wecom: bool = True,
    ):
        """发送单店通知（企业微信 + WeChat）"""
        import requests
        from selenium_fetcher import SeleniumGoodsFetcher
        from wechat_notifier import parse_targets, format_shop_message, send_to_targets
        
        # 企业微信通知
        if send_wecom and shop.webhook:
            try:
                # 生成消息（包含营业状态和耗时）
                try:
                    msg_body = SeleniumGoodsFetcher.format_wecom_markdown(
                        shop.name, off_sale_list, sold_out_list, shop_status, duration
                    )
                except:
                    text_msg = SeleniumGoodsFetcher.format_wecom_message(
                        shop.name, off_sale_list, sold_out_list, shop_status=shop_status
                    )
                    msg_body = {"msgtype": "text", "text": {"content": text_msg}}
                
                # 发送请求
                resp = requests.post(shop.webhook, json=msg_body, timeout=10)
                
                if resp.status_code == 200:
                    result = resp.json()
                    if result.get("errcode") == 0:
                        self.log(f"   📤 已发送企业微信通知到: {shop.name}")
                    else:
                        self.log(f"   ✗ 企业微信通知发送失败: {result.get('errmsg')}")
                else:
                    self.log(f"   ✗ 企业微信通知发送失败: HTTP {resp.status_code}")
                    
            except Exception as e:
                self.log(f"   ✗ 发送企业微信通知出错: {e}")
        
        # WeChat通知（wxauto）
        if self.config.enable_wechat_notification:
            try:
                targets = parse_targets(self.config.wechat_targets)
                if not targets:
                    return
                
                has_abnormal = len(off_sale_list) > 0 or len(sold_out_list) > 0
                message = format_shop_message(
                    shop.name, off_sale_list, sold_out_list, shop_status, duration
                )
                
                result = send_to_targets(
                    targets, message,
                    send_normal=self.config.wechat_send_normal,
                    has_abnormal=has_abnormal
                )
                
                if result['success_count'] > 0:
                    self.log(f"   💬 WeChat通知已发送到 {result['success_count']} 个目标")
                if result['failed_count'] > 0:
                    self.log(f"   ✗ WeChat通知发送失败: {result['failed_count']} 个目标")
                    if result.get('errors'):
                        for err in result['errors']:
                            self.log(f"      ✗ {err}")
                    elif result['failed_targets']:
                        self.log(f"      失败目标: {', '.join(result['failed_targets'])}")
                        
            except Exception as e:
                import traceback
                self.log(f"   ✗ 发送WeChat通知出错: {e}")
                self.log(f"      {traceback.format_exc()}")
    
    def _try_auto_login(self):
        """尝试自动填充登录表单"""
        if not self.running: return
        if not self.fetcher or not self.fetcher.driver:
            self.fetcher._init_driver()
        
        driver = self.fetcher.driver
        if not driver:
            return
        
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        try:
            time.sleep(3)
            if not self.running: return
            
            # 检查是否在登录页面
            if not self.fetcher._need_login():
                self.log("已检测到登录状态，无需重新登录")
                return
            
            self.log("检测到登录页面，尝试自动填充...")
            
            # 尝试找到用户名输入框
            username_selectors = [
                "input[name='fm-login-id']",
                "input[name='username']",
                "input[name='loginId']",
                "input[id='fm-login-id']",
                "input[placeholder*='账号']",
                "input[placeholder*='手机']",
                "input[placeholder*='邮箱']",
            ]
            
            username_input = None
            for selector in username_selectors:
                if not self.running: return
                try:
                    username_input = driver.find_element(By.CSS_SELECTOR, selector)
                    if username_input:
                        break
                except:
                    continue
            
            if username_input:
                username_input.clear()
                username_input.send_keys(self.config.taobao_username)
                self.log("已填充用户名")
            
            # 尝试找到密码输入框
            password_selectors = [
                "input[name='fm-login-password']",
                "input[name='password']",
                "input[type='password']",
                "input[id='fm-login-password']",
            ]
            
            password_input = None
            for selector in password_selectors:
                if not self.running: return
                try:
                    password_input = driver.find_element(By.CSS_SELECTOR, selector)
                    if password_input:
                        break
                except:
                    continue
            
            if password_input:
                password_input.clear()
                password_input.send_keys(self.config.taobao_password)
                self.log("已填充密码")
            
            # 尝试点击登录按钮
            login_button_selectors = [
                "button[type='submit']",
                "button[class*='login']",
                "input[type='submit']",
                "button:contains('登录')",
                ".fm-button",
            ]
            
            for selector in login_button_selectors:
                if not self.running: return
                try:
                    login_btn = driver.find_element(By.CSS_SELECTOR, selector)
                    if login_btn:
                        login_btn.click()
                        self.log("已点击登录按钮，请完成验证...")
                        break
                except:
                    continue
            
        except Exception as e:
            self.log(f"自动登录失败: {e}，请手动登录")
    
    def stop(self, close_browser: bool = False):
        """
        停止监控线程
        
        Args:
            close_browser: 是否关闭浏览器。
                          False = 暂停监控，保留浏览器（下次可快速恢复）
                          True = 完全停止，关闭浏览器（退出程序时使用）
        """
        if not self.running: return
        self.running = False
        
        if close_browser:
            self.log("正在停止并关闭浏览器...")
        else:
            self.log("正在暂停监控（浏览器保持运行）...")
        
        # 在独立线程中执行清理，防止阻塞GUI
        def force_stop():
            # 停止Playwright监控器
            if self.pw_monitor:
                try:
                    self.pw_monitor.stop(close_browser=close_browser)
                except:
                    pass
                if close_browser:
                    self.pw_monitor = None
            
            # 停止Selenium（Selenium暂时总是关闭，因为它是独立进程）
            if close_browser and self.fetcher:
                try:
                    # 尝试关闭浏览器驱动
                    if self.fetcher.driver:
                        # 尝试强制结束驱动进程
                        try:
                            if hasattr(self.fetcher.driver, 'service') and self.fetcher.driver.service.process:
                                # Windows: taskkill /F /PID <pid> /T
                                if os.name == 'nt':
                                    import subprocess
                                    pid = self.fetcher.driver.service.process.pid
                                    subprocess.run(
                                        f"taskkill /F /PID {pid} /T", 
                                        shell=True, 
                                        stdout=subprocess.DEVNULL, 
                                        stderr=subprocess.DEVNULL
                                    )
                        except:
                            pass
                        
                        try:
                            self.fetcher.driver.quit()
                        except:
                            pass
                except:
                    pass
        
        # 启动守护线程进行清理
        threading.Thread(target=force_stop, daemon=True).start()
    
    def stop_and_close_browser(self):
        """完全停止并关闭浏览器（退出程序时调用）"""
        self.stop(close_browser=True)
    
    def _cleanup(self):
        """清理资源"""
        if self._is_cleaning_up: return
        self._is_cleaning_up = True
        
        if self.fetcher:
            try:
                self.fetcher.close()
            except:
                pass
            self.fetcher = None


def simplify_shop_name(full_name: str) -> str:
    """
    简化门店名称，提取括号内的店名
    例如：阿狗手打·手作黑糖珍珠奶茶(松江樱花广场店) -> 松江樱花广场店
    """
    if '(' in full_name and ')' in full_name:
        # 提取最后一对括号中的内容
        start = full_name.rfind('(')
        end = full_name.rfind(')')
        if start < end:
            return full_name[start+1:end]
    elif '（' in full_name and '）' in full_name:
        # 中文括号
        start = full_name.rfind('（')
        end = full_name.rfind('）')
        if start < end:
            return full_name[start+1:end]
    return full_name


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.config_manager = ConfigManager()
        self.config = self.config_manager.config
        self.worker = None
        self.shop_manager = ShopManager()  # 门店管理器
        self.init_ui()
        self.load_config_to_ui()
        self._load_shop_list(silent=True)  # 静默加载门店列表（首次运行可能文件不存在）
    
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle(f"淘宝闪购智能助手Agent v{get_version()}")
        self.setMinimumSize(1150, 750)  # 增加默认尺寸，适应 Windows 缩放
        self.resize(1200, 800)
        
        # 设置样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f6fa;
                font-family: 'Microsoft YaHei', 'WenQuanYi Micro Hei', 'Noto Sans CJK SC', 'SimHei', 'Segoe UI', sans-serif;
            }
            QGroupBox {
                font-weight: bold;
                font-size: 13px; /* 稍微减小字体 */
                color: #2f3640;
                border: 1px solid #dcdde1;
                border-radius: 8px;
                margin-top: 10px;
                padding: 15px; /* 稍微减小内边距 */
                background-color: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 5px;
                background-color: #ffffff;
                color: #0097e6;
            }
            QLabel {
                color: #2f3640;
                font-size: 12px; /* 稍微减小字体 */
            }
            QLineEdit {
                padding: 5px 8px;
                min-height: 28px;
                border: 1px solid #dcdde1;
                border-radius: 6px;
                background-color: #f5f6fa;
                color: #2f3640;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 2px solid #0097e6;
                background-color: #ffffff;
            }
            QSpinBox {
                padding: 5px 30px 5px 8px; /* 右边留空间给箭头按钮 */
                min-height: 28px;
                min-width: 80px;
                border: 1px solid #dcdde1;
                border-radius: 6px;
                background-color: #f5f6fa;
                color: #2f3640;
                font-size: 13px;
            }
            QSpinBox:focus {
                border: 2px solid #0097e6;
                background-color: #ffffff;
            }
            /* SpinBox箭头按钮样式 */
            QSpinBox::up-button {
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 22px;
                height: 14px;
                border: none;
                border-left: 1px solid #dcdde1;
                border-top-right-radius: 5px;
                background-color: #ffffff;
            }
            QSpinBox::down-button {
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 22px;
                height: 14px;
                border: none;
                border-left: 1px solid #dcdde1;
                border-bottom-right-radius: 5px;
                background-color: #ffffff;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background-color: #e3f2fd;
            }
            QSpinBox::up-arrow {
                width: 8px;
                height: 8px;
            }
            QSpinBox::down-arrow {
                width: 8px;
                height: 8px;
            }
            QPushButton {
                padding: 8px 16px; /* 减小按钮内边距 */
                background-color: #0097e6;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px; /* 稍微减小字体 */
            }
            QPushButton:hover {
                background-color: #00a8ff;
            }
            QPushButton:pressed {
                background-color: #0084c9;
            }
            QPushButton:disabled {
                background-color: #b2bec3;
                color: #dfe6e9;
            }
            QPushButton#secondaryBtn {
                background-color: #ffffff;
                color: #2f3640;
                border: 1px solid #dcdde1;
            }
            QPushButton#secondaryBtn:hover {
                background-color: #f5f6fa;
                border: 1px solid #0097e6;
                color: #0097e6;
            }
            QCheckBox {
                color: #2f3640;
                font-size: 13px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid #dcdde1;
                background-color: #ffffff;
            }
            QCheckBox::indicator:checked {
                background-color: #0097e6;
                border-color: #0097e6;
            }
            QTextEdit {
                background-color: #ffffff;
                color: #2f3640;
                border: 1px solid #dcdde1;
                border-radius: 6px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 12px;
                padding: 10px;
            }
            QProgressBar {
                border: none;
                border-radius: 4px;
                background-color: #dcdde1;
                height: 6px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #0097e6;
                border-radius: 4px;
            }
            QTabWidget::pane {
                border: 1px solid #dcdde1;
                border-radius: 6px;
                background-color: #ffffff;
                top: -1px;
            }
            QTabBar::tab {
                background-color: #f5f6fa;
                color: #7f8fa6;
                padding: 12px 30px;
                margin-right: 4px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                border: 1px solid #dcdde1;
                border-bottom: none;
                font-weight: bold;
                font-size: 13px;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                color: #0097e6;
                border-bottom: 1px solid #ffffff;
            }
            QTabBar::tab:hover {
                background-color: #ffffff;
            }
            QStatusBar {
                background-color: #ffffff;
                color: #7f8fa6;
                border-top: 1px solid #dcdde1;
            }
        """)
        
        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(25, 25, 25, 25)
        
        # 标题
        title_label = QLabel("🛒 淘宝闪购智能助手Agent")
        title_label.setFont(QFont("Microsoft YaHei", 20, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #2f3640; margin-bottom: 5px;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)
        
        # 使用分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background-color: #dcdde1; }")
        main_layout.addWidget(splitter, 1)
        
        # 左侧配置面板
        left_panel = QWidget()
        left_panel.setMinimumWidth(400)  # 确保左侧面板不被过度压缩
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 15, 0)
        
        # Tab页
        tabs = QTabWidget()
        left_layout.addWidget(tabs)
        
        # --- 登录配置Tab ---
        login_tab = QWidget()
        login_layout = QVBoxLayout(login_tab)
        login_layout.setContentsMargins(25, 25, 25, 25)
        
        login_group = QGroupBox("📱 淘宝账号登录")
        login_form = QFormLayout(login_group)
        login_form.setSpacing(20)
        login_form.setContentsMargins(20, 25, 20, 20)
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("输入淘宝账号/手机号")
        login_form.addRow("账号:", self.username_input)
        
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("输入登录密码")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        login_form.addRow("密码:", self.password_input)
        
        self.remember_checkbox = QCheckBox("记住密码（加密存储）")
        login_form.addRow("", self.remember_checkbox)
        
        self.auto_login_checkbox = QCheckBox("启动时自动填充登录信息")
        login_form.addRow("", self.auto_login_checkbox)
        
        login_layout.addWidget(login_group)
        
        # 登录说明
        login_note = QLabel(
            "💡 提示: 首次登录需要在浏览器中完成验证。\n"
            "登录成功后，系统会保存登录状态，下次无需重复登录。"
        )
        login_note.setStyleSheet("""
            color: #7f8fa6; 
            font-size: 12px; 
            padding: 15px; 
            background-color: #f5f6fa; 
            border-radius: 8px;
            border: 1px solid #dcdde1;
        """)
        login_note.setWordWrap(True)
        login_layout.addWidget(login_note)
        
        login_layout.addStretch()
        tabs.addTab(login_tab, "🔐 登录")
        
        # --- 店铺配置Tab ---
        shop_scroll = QScrollArea()
        shop_scroll.setWidgetResizable(True)
        shop_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        shop_tab = QWidget()
        shop_layout = QVBoxLayout(shop_tab)
        shop_layout.setContentsMargins(25, 25, 25, 25)
        
        # 多门店配置
        multi_shop_group = QGroupBox("🏪 多门店监控配置")
        multi_shop_layout = QVBoxLayout(multi_shop_group)
        multi_shop_layout.setContentsMargins(20, 25, 20, 20)
        multi_shop_layout.setSpacing(10)
        
        # 门店列表文件选择（第一行：文件输入 + 选择按钮 + 加载按钮）
        shop_file_layout = QHBoxLayout()
        self.shop_file_input = QLineEdit()
        self.shop_file_input.setPlaceholderText("选择门店列表文件 (Excel/JSON)")
        # 默认路径会在 load_config_to_ui 中从配置加载
        shop_file_btn = QPushButton("选择")
        shop_file_btn.setObjectName("secondaryBtn")
        shop_file_btn.setFixedWidth(60)
        shop_file_btn.clicked.connect(self.select_shop_file)
        load_shops_btn = QPushButton("加载")
        load_shops_btn.setObjectName("secondaryBtn")
        load_shops_btn.setFixedWidth(60)
        load_shops_btn.clicked.connect(self._load_shop_list)
        shop_file_layout.addWidget(self.shop_file_input)
        shop_file_layout.addWidget(shop_file_btn)
        shop_file_layout.addWidget(load_shops_btn)
        multi_shop_layout.addLayout(shop_file_layout)
        
        # 门店数量和启用checkbox（同一行）
        info_layout = QHBoxLayout()
        self.shop_count_label = QLabel("已加载: 0 个门店")
        self.shop_count_label.setStyleSheet("color: #7f8fa6; font-size: 12px;")
        info_layout.addWidget(self.shop_count_label)
        info_layout.addStretch()
        self.multi_shop_checkbox = QCheckBox("启用多门店监控模式")
        self.multi_shop_checkbox.setChecked(True)
        info_layout.addWidget(self.multi_shop_checkbox)
        multi_shop_layout.addLayout(info_layout)
        
        # 门店列表预览（隐藏的，用于存储数据）
        self.shop_list_text = QTextEdit()
        self.shop_list_text.setReadOnly(True)
        self.shop_list_text.setVisible(False)  # 隐藏预览框，避免布局干涉
        
        shop_layout.addWidget(multi_shop_group)
        
        # 基础店铺配置（用于单店模式或默认店铺）
        shop_group = QGroupBox("🏠 默认店铺信息（单店模式）")
        shop_form = QFormLayout(shop_group)
        shop_form.setSpacing(15)
        shop_form.setContentsMargins(20, 20, 20, 15)
        
        self.chain_id_input = QLineEdit()
        self.chain_id_input.setPlaceholderText("连锁店ID")
        shop_form.addRow("连锁ID:", self.chain_id_input)
        
        self.shop_id_input = QLineEdit()
        self.shop_id_input.setPlaceholderText("门店ID")
        shop_form.addRow("门店ID:", self.shop_id_input)
        
        self.shop_name_input = QLineEdit()
        self.shop_name_input.setPlaceholderText("门店名称（仅用于显示）")
        shop_form.addRow("门店名称:", self.shop_name_input)
        
        shop_layout.addWidget(shop_group)
        
        # 通知配置
        notify_group = QGroupBox("📢 通知设置（单店模式使用）")
        notify_form = QFormLayout(notify_group)
        notify_form.setSpacing(15)
        notify_form.setContentsMargins(20, 20, 20, 15)
        
        self.webhook_input = QLineEdit()
        self.webhook_input.setPlaceholderText("企业微信机器人Webhook地址")
        notify_form.addRow("Webhook:", self.webhook_input)
        
        self.enable_notify_checkbox = QCheckBox("启用企业微信通知")
        notify_form.addRow("", self.enable_notify_checkbox)
        
        shop_layout.addWidget(notify_group)
        
        # WeChat通知配置（使用wxauto）
        wechat_group = QGroupBox("💬 WeChat通知设置（wxauto）")
        wechat_form = QFormLayout(wechat_group)
        wechat_form.setSpacing(15)
        wechat_form.setContentsMargins(20, 20, 20, 15)
        
        self.enable_wechat_checkbox = QCheckBox("启用WeChat通知")
        wechat_form.addRow("", self.enable_wechat_checkbox)
        
        self.wechat_targets_input = QTextEdit()
        self.wechat_targets_input.setPlaceholderText("输入WeChat目标（个人或群组名称）\n每行一个，例如：\n张三\n工作群\n测试群")
        self.wechat_targets_input.setMaximumHeight(100)
        wechat_form.addRow("目标列表:", self.wechat_targets_input)
        
        self.wechat_send_normal_checkbox = QCheckBox("发送正常状态消息")
        wechat_form.addRow("", self.wechat_send_normal_checkbox)
        
        # WeChat说明
        wechat_note = QLabel(
            "💡 提示: WeChat通知使用wxauto实现Windows桌面微信自动化。\n"
            "需要：1) Windows系统 2) 已安装微信PC版 3) 微信已登录\n"
            "目标名称需与微信中的联系人/群组名称完全一致。"
        )
        wechat_note.setStyleSheet("""
            color: #7f8fa6; 
            font-size: 11px; 
            padding: 10px; 
            background-color: #f5f6fa; 
            border-radius: 6px;
            border: 1px solid #dcdde1;
        """)
        wechat_note.setWordWrap(True)
        wechat_form.addRow("", wechat_note)
        
        shop_layout.addWidget(wechat_group)
        shop_layout.addStretch()
        shop_scroll.setWidget(shop_tab)
        tabs.addTab(shop_scroll, "🏪 店铺")
        
        # --- 高级设置Tab ---
        advanced_tab = QWidget()
        advanced_layout = QVBoxLayout(advanced_tab)
        advanced_layout.setContentsMargins(25, 25, 25, 25)
        
        browser_group = QGroupBox("🌐 浏览器设置")
        browser_form = QFormLayout(browser_group)
        browser_form.setSpacing(20)
        browser_form.setContentsMargins(20, 25, 20, 20)
        
        self.debug_port_spin = QSpinBox()
        self.debug_port_spin.setRange(1024, 65535)
        self.debug_port_spin.setValue(9222)
        browser_form.addRow("调试端口:", self.debug_port_spin)
        
        browser_path_layout = QHBoxLayout()
        self.browser_path_input = QLineEdit()
        self.browser_path_input.setPlaceholderText("留空自动检测")
        browser_path_btn = QPushButton("选择")
        browser_path_btn.setObjectName("secondaryBtn")
        browser_path_btn.setFixedWidth(70)
        browser_path_btn.clicked.connect(self.select_browser_path)
        browser_path_layout.addWidget(self.browser_path_input)
        browser_path_layout.addWidget(browser_path_btn)
        browser_form.addRow("浏览器路径:", browser_path_layout)
        
        self.headless_checkbox = QCheckBox("无头模式（后台运行，不显示浏览器窗口）")
        browser_form.addRow("", self.headless_checkbox)
        
        advanced_layout.addWidget(browser_group)
        
        monitor_group = QGroupBox("⏰ 监控设置")
        monitor_form = QFormLayout(monitor_group)
        monitor_form.setSpacing(20)
        monitor_form.setContentsMargins(20, 25, 20, 20)
        
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 1440)
        self.interval_spin.setValue(30)
        self.interval_spin.setSuffix(" 分钟")
        monitor_form.addRow("检查间隔:", self.interval_spin)
        
        # 并行监控设置（使用Playwright实现真正并行）
        parallel_layout = QHBoxLayout()
        self.parallel_checkbox = QCheckBox("启用Playwright并行监控")
        self.parallel_checkbox.setChecked(True)
        self.parallel_checkbox.setToolTip("使用Playwright在同一浏览器中打开多个页面并行监控\n所有页面共享登录状态，实现真正的并行")
        parallel_layout.addWidget(self.parallel_checkbox)
        
        self.parallel_workers_spin = QSpinBox()
        self.parallel_workers_spin.setRange(1, 10)
        self.parallel_workers_spin.setValue(5)
        self.parallel_workers_spin.setSuffix(" 个页面")
        self.parallel_workers_spin.setToolTip("并行页面数量\n建议：3-5个页面效果最佳")
        parallel_layout.addWidget(self.parallel_workers_spin)
        parallel_layout.addStretch()
        monitor_form.addRow("并行监控:", parallel_layout)
        
        # 门店筛选设置
        self.only_open_shops_checkbox = QCheckBox("只监控营业中的门店")
        self.only_open_shops_checkbox.setChecked(False)
        self.only_open_shops_checkbox.setToolTip("勾选后将跳过休息中/已下线的门店\n只监控正在营业的门店")
        monitor_form.addRow("门店筛选:", self.only_open_shops_checkbox)
        
        # 重试超时设置（多轮重试最大耗时）
        retry_timeout_layout = QHBoxLayout()
        self.retry_timeout_spinbox = QSpinBox()
        self.retry_timeout_spinbox.setRange(0, 120)
        self.retry_timeout_spinbox.setValue(30)
        self.retry_timeout_spinbox.setSuffix(" 分钟")
        self.retry_timeout_spinbox.setToolTip(
            "多轮重试的最大时间限制（0-120分钟）\n"
            "0 = 不重试，仅监控一轮\n"
            "对因操作失败跳过的门店会自动重试\n"
            "直到所有门店成功或超时\n"
            "建议：30分钟"
        )
        self.retry_timeout_spinbox.setFixedWidth(100)
        retry_timeout_layout.addWidget(self.retry_timeout_spinbox)
        retry_timeout_layout.addStretch()
        monitor_form.addRow("重试超时:", retry_timeout_layout)
        
        export_layout = QHBoxLayout()
        self.export_dir_input = QLineEdit()
        self.export_dir_input.setText("./exports")
        export_btn = QPushButton("选择")
        export_btn.setObjectName("secondaryBtn")
        export_btn.setFixedWidth(70)
        export_btn.clicked.connect(self.select_export_dir)
        export_layout.addWidget(self.export_dir_input)
        export_layout.addWidget(export_btn)
        monitor_form.addRow("导出目录:", export_layout)
        
        advanced_layout.addWidget(monitor_group)
        
        # 缓存管理
        cache_group = QGroupBox("🗑️ 缓存管理")
        cache_layout = QHBoxLayout(cache_group)
        cache_layout.setContentsMargins(20, 25, 20, 20)
        
        clear_cache_btn = QPushButton("清除登录缓存")
        clear_cache_btn.setObjectName("secondaryBtn")
        clear_cache_btn.setMinimumHeight(35)
        clear_cache_btn.clicked.connect(self.clear_cache)
        cache_layout.addWidget(clear_cache_btn)
        cache_layout.addStretch()
        
        advanced_layout.addWidget(cache_group)
        advanced_layout.addStretch()
        tabs.addTab(advanced_tab, "⚙️ 高级")
        
        splitter.addWidget(left_panel)
        
        # 右侧日志和控制面板
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(15, 0, 0, 0)
        
        # 控制按钮
        control_layout = QHBoxLayout()
        control_layout.setSpacing(15)
        
        self.start_btn = QPushButton("▶ 开始监控")
        self.start_btn.setMinimumHeight(50)
        self.start_btn.setStyleSheet("""
            QPushButton {
                font-size: 15px;
                background-color: #0097e6;
                border-radius: 8px;
            }
            QPushButton:hover { background-color: #00a8ff; }
            QPushButton:pressed { background-color: #0084c9; }
        """)
        self.start_btn.clicked.connect(self.start_monitor)
        control_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.setObjectName("secondaryBtn")
        self.stop_btn.setMinimumHeight(50)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                font-size: 15px;
                border-radius: 8px;
            }
        """)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_monitor)
        control_layout.addWidget(self.stop_btn)
        
        self.save_btn = QPushButton("💾 保存配置")
        self.save_btn.setObjectName("secondaryBtn")
        self.save_btn.setMinimumHeight(50)
        self.save_btn.setStyleSheet("""
            QPushButton {
                font-size: 15px;
                border-radius: 8px;
            }
        """)
        self.save_btn.clicked.connect(self.save_config)
        control_layout.addWidget(self.save_btn)
        
        right_layout.addLayout(control_layout)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        right_layout.addWidget(self.progress_bar)
        
        # 日志输出
        log_group = QGroupBox("📋 运行日志")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(15, 20, 15, 15)
        
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(300)
        log_layout.addWidget(self.log_output)
        
        clear_log_btn = QPushButton("清空日志")
        clear_log_btn.setObjectName("secondaryBtn")
        clear_log_btn.setFixedWidth(100)
        clear_log_btn.clicked.connect(lambda: self.log_output.clear())
        log_layout.addWidget(clear_log_btn, alignment=Qt.AlignmentFlag.AlignRight)
        
        right_layout.addWidget(log_group, 1)
        
        # 结果统计
        result_group = QGroupBox("📊 监控结果")
        result_layout = QHBoxLayout(result_group)
        result_layout.setContentsMargins(20, 20, 20, 20)
        
        self.off_sale_label = QLabel("已下架: 0")
        self.off_sale_label.setStyleSheet("color: #e84118; font-size: 16px; font-weight: bold;")
        result_layout.addWidget(self.off_sale_label)
        
        self.sold_out_label = QLabel("已售罄: 0")
        self.sold_out_label.setStyleSheet("color: #fbc531; font-size: 16px; font-weight: bold;")
        result_layout.addWidget(self.sold_out_label)
        
        self.total_label = QLabel("总计: 0")
        self.total_label.setStyleSheet("color: #44bd32; font-size: 16px; font-weight: bold;")
        result_layout.addWidget(self.total_label)
        
        right_layout.addWidget(result_group)
        
        splitter.addWidget(right_panel)
        splitter.setSizes([380, 520])
        
        # 状态栏
        self.statusBar().showMessage("就绪")
        
        # 初始日志
        self.log("淘宝闪购智能助手Agent已启动")
        self.log("请配置账号信息后点击「开始监控」")
    
    def load_config_to_ui(self):
        """将配置加载到UI"""
        self.username_input.setText(self.config.taobao_username)
        self.password_input.setText(self.config.taobao_password)
        self.remember_checkbox.setChecked(self.config.remember_password)
        self.auto_login_checkbox.setChecked(self.config.auto_login)
        
        self.chain_id_input.setText(self.config.chain_id)
        self.shop_id_input.setText(self.config.shop_id)
        self.shop_name_input.setText(self.config.shop_name)
        
        self.webhook_input.setText(self.config.wecom_webhook)
        self.enable_notify_checkbox.setChecked(self.config.enable_notification)
        
        # 加载WeChat通知配置
        self.enable_wechat_checkbox.setChecked(getattr(self.config, 'enable_wechat_notification', False))
        self.wechat_targets_input.setPlainText(getattr(self.config, 'wechat_targets', ''))
        self.wechat_send_normal_checkbox.setChecked(getattr(self.config, 'wechat_send_normal', False))
        
        self.debug_port_spin.setValue(self.config.debug_port)
        self.browser_path_input.setText(self.config.browser_path)
        self.headless_checkbox.setChecked(self.config.headless)
        self.interval_spin.setValue(self.config.check_interval)
        self.export_dir_input.setText(self.config.export_dir)
        
        # 加载并行监控配置
        self.parallel_checkbox.setChecked(getattr(self.config, 'enable_parallel', True))
        self.parallel_workers_spin.setValue(getattr(self.config, 'parallel_workers', 5))
        
        # 加载门店筛选配置
        self.only_open_shops_checkbox.setChecked(getattr(self.config, 'only_open_shops', False))
        
        # 加载重试超时配置（默认30分钟）
        self.retry_timeout_spinbox.setValue(getattr(self.config, 'retry_timeout_minutes', 30))
        
        # 加载上一次的门店列表路径
        if self.config.shop_list_file:
            self.shop_file_input.setText(self.config.shop_list_file)
        else:
            self.shop_file_input.setText("doc/门店列表_v2.xlsx")  # 默认路径
    
    def save_ui_to_config(self):
        """将UI值保存到配置"""
        self.config.taobao_username = self.username_input.text().strip()
        self.config.taobao_password = self.password_input.text()
        self.config.remember_password = self.remember_checkbox.isChecked()
        self.config.auto_login = self.auto_login_checkbox.isChecked()
        
        self.config.chain_id = self.chain_id_input.text().strip()
        self.config.shop_id = self.shop_id_input.text().strip()
        self.config.shop_name = self.shop_name_input.text().strip()
        
        self.config.wecom_webhook = self.webhook_input.text().strip()
        self.config.enable_notification = self.enable_notify_checkbox.isChecked()
        
        # 保存WeChat通知配置
        self.config.enable_wechat_notification = self.enable_wechat_checkbox.isChecked()
        self.config.wechat_targets = self.wechat_targets_input.toPlainText().strip()
        self.config.wechat_send_normal = self.wechat_send_normal_checkbox.isChecked()
        
        self.config.debug_port = self.debug_port_spin.value()
        self.config.browser_path = self.browser_path_input.text().strip()
        self.config.headless = self.headless_checkbox.isChecked()
        self.config.check_interval = self.interval_spin.value()
        self.config.export_dir = self.export_dir_input.text().strip()
        
        # 保存并行监控配置
        self.config.enable_parallel = self.parallel_checkbox.isChecked()
        self.config.parallel_workers = self.parallel_workers_spin.value()
        
        # 保存门店筛选配置
        self.config.only_open_shops = self.only_open_shops_checkbox.isChecked()
        
        # 保存重试超时配置
        self.config.retry_timeout_minutes = self.retry_timeout_spinbox.value()
    
    def save_config(self):
        """保存配置"""
        self.save_ui_to_config()
        if self.config_manager.save():
            self.log("✓ 配置已保存")
            self.statusBar().showMessage("配置已保存", 3000)
        else:
            self.log("✗ 配置保存失败")
    
    def log(self, msg: str):
        """添加日志"""
        self.log_output.append(msg)
        # 滚动到底部
        cursor = self.log_output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_output.setTextCursor(cursor)
    
    def start_monitor(self):
        """开始监控"""
        self.save_ui_to_config()
        
        # 检查是否使用多门店模式
        use_multi_shop = self.multi_shop_checkbox.isChecked() and len(self.shop_manager.shops) > 0
        
        if not use_multi_shop:
            # 单店模式：检查店铺ID
            if not self.config.chain_id or not self.config.shop_id:
                QMessageBox.warning(self, "提示", "请先配置店铺ID！\n或者启用多门店监控模式并加载门店列表。")
                return
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        
        self.log("=" * 50)
        if use_multi_shop:
            self.log(f"开始多门店监控模式，共 {len(self.shop_manager.shops)} 个门店...")
        else:
            self.log("开始单店监控...")
        self.statusBar().showMessage("监控中...")
        
        # 创建工作线程
        profile_dir = self.config_manager.get_profile_dir()
        shops = self.shop_manager.get_enabled_shops() if use_multi_shop else []
        
        self.worker = MonitorWorker(
            self.config,
            profile_dir,
            auto_fill_login=self.config.auto_login,
            shops=shops,
            check_interval=self.config.check_interval,  # 监控间隔（分钟）
            enable_parallel=getattr(self.config, 'enable_parallel', True),
            parallel_workers=getattr(self.config, 'parallel_workers', 20),
            only_open_shops=getattr(self.config, 'only_open_shops', False),
            retry_timeout_minutes=getattr(self.config, 'retry_timeout_minutes', 30),
            shop_manager=self.shop_manager,  # 传递门店管理器（用于商品白名单过滤）
        )
        
        self.worker.log_signal.connect(self.log)
        self.worker.status_signal.connect(lambda s: self.statusBar().showMessage(s))
        self.worker.progress_signal.connect(self.progress_bar.setValue)
        self.worker.finished_signal.connect(self.on_monitor_finished)
        self.worker.error_signal.connect(self.on_monitor_error)
        self.worker.shop_result_signal.connect(self.on_shop_result)
        
        self.worker.start()
    
    def stop_monitor(self):
        """停止监控（暂停，不关闭浏览器）"""
        if self.worker:
            self.worker.stop(close_browser=False)  # 暂停时不关闭浏览器
            # 不再阻塞等待，让 worker 的 force_stop 线程去处理
            # self.worker.wait(5000)
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.log("监控已暂停（浏览器保持运行）")
        self.statusBar().showMessage("已暂停")
    
    def on_shop_result(self, result: dict):
        """单个门店监控结果"""
        # 可以在这里更新UI显示单店结果
        pass
    
    def on_monitor_finished(self, result: dict):
        """监控完成"""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        
        # 检查是否是多门店监控结果
        if result.get('multi_shop'):
            all_results = result.get('all_results', {})
            total_off_sale = all_results.get('total_off_sale', 0)
            total_sold_out = all_results.get('total_sold_out', 0)
            shops_monitored = all_results.get('shops_monitored', 0)
            shops_skipped = all_results.get('shops_skipped', 0)
            skipped_shops = all_results.get('skipped_shops', [])
            
            self.off_sale_label.setText(f"已下架: {total_off_sale}")
            self.sold_out_label.setText(f"已售罄: {total_sold_out}")
            self.total_label.setText(f"门店: {shops_monitored}/{shops_monitored + shops_skipped}")
            
            # 发送监控总结到默认 webhook（单店模式使用的 webhook）和WeChat
            if self.config.enable_notification and self.config.wecom_webhook:
                self._send_multi_shop_summary(all_results)
            
            # WeChat通知（多门店总结）
            if self.config.enable_wechat_notification:
                self._send_wechat_multi_shop_summary(all_results)
            
            self.log("")
            self.log("=" * 50)
            self.statusBar().showMessage("多门店监控完成")
            return
        
        # 单店模式结果
        off_sale_list = result.get("off_sale", [])
        sold_out_list = result.get("sold_out", [])
        off_sale = len(off_sale_list)
        sold_out = len(sold_out_list)
        total = result.get("total", 0)
        
        self.off_sale_label.setText(f"已下架: {off_sale}")
        self.sold_out_label.setText(f"已售罄: {sold_out}")
        self.total_label.setText(f"总计: {total}")
        
        # 在日志中显示企业微信消息预览
        if off_sale > 0 or sold_out > 0:
            self.log("")
            self.log("┌─────────────────────────────────────────┐")
            self.log("│     📱 企业微信通知消息预览              │")
            self.log("└─────────────────────────────────────────┘")
            self.preview_wecom_message(off_sale_list, sold_out_list)
            self.log("")
        
        # 发送通知（企业微信 + WeChat）
        has_abnormal = off_sale > 0 or sold_out > 0
        wecom_enabled = bool(self.config.enable_notification and self.config.wecom_webhook)
        wechat_enabled = bool(getattr(self.config, 'enable_wechat_notification', False))
        wechat_send_normal = bool(getattr(self.config, 'wechat_send_normal', False))

        if has_abnormal:
            # 异常：任一通知渠道启用即可发送（send_wecom_notification 内部会分别判断）
            if wecom_enabled or wechat_enabled:
                self.send_wecom_notification(off_sale_list, sold_out_list)
        else:
            # 正常：仅当开启了“正常也发送”的 WeChat 通知时才推送
            if wechat_enabled and wechat_send_normal:
                self.send_wecom_notification(off_sale_list, sold_out_list)
            else:
                self.log("✅ 商品状态正常，无异常商品")
        
        self.log("=" * 50)
        self.statusBar().showMessage("监控完成")
    
    def preview_wecom_message(self, off_sale_list, sold_out_list):
        """在日志中预览企业微信消息"""
        from selenium_fetcher import SeleniumGoodsFetcher
        from datetime import datetime
        
        shop_name = self.config.shop_name or "未设置门店名"
        now = datetime.now().strftime("%m-%d %H:%M")
        off_count = len(off_sale_list)
        sold_count = len(sold_out_list)
        
        self.log(f"🔔 【商品状态提醒】")
        self.log(f"📍 {shop_name}")
        self.log(f"⏰ {now}")
        self.log("")
        
        if off_sale_list:
            self.log(f"🔻 已下架 ({off_count})")
            self.log("─" * 20)
            for i, g in enumerate(off_sale_list[:8], 1):
                name = g.goods_name[:15] + "..." if len(g.goods_name) > 15 else g.goods_name
                self.log(f"  {i}. {name}")
            if off_count > 8:
                self.log(f"  ... 等{off_count}个商品")
            self.log("")
        
        if sold_out_list:
            self.log(f"🔴 已售罄 ({sold_count})")
            self.log("─" * 20)
            for i, g in enumerate(sold_out_list[:8], 1):
                name = g.goods_name[:15] + "..." if len(g.goods_name) > 15 else g.goods_name
                self.log(f"  {i}. {name}")
            if sold_count > 8:
                self.log(f"  ... 等{sold_count}个商品")
            self.log("")
        
        self.log("─" * 20)
        self.log(f"📊 共 {off_count + sold_count} 个异常商品")
        self.log("💡 请及时处理")
    
    def send_wecom_notification(self, off_sale_list, sold_out_list):
        """发送企业微信通知 + WeChat通知"""
        import requests
        from selenium_fetcher import SeleniumGoodsFetcher
        from wechat_notifier import parse_targets, format_shop_message, send_to_targets
        
        shop_name = self.config.shop_name or "未设置门店名"
        has_abnormal = len(off_sale_list) > 0 or len(sold_out_list) > 0
        
        # 企业微信通知
        if self.config.enable_notification and self.config.wecom_webhook:
            try:
                # 生成精美消息（尝试 Markdown，如果失败则用文本）
                try:
                    msg_body = SeleniumGoodsFetcher.format_wecom_markdown(
                        shop_name, off_sale_list, sold_out_list
                    )
                except:
                    # 降级为纯文本
                    text_msg = SeleniumGoodsFetcher.format_wecom_message(
                        shop_name, off_sale_list, sold_out_list
                    )
                    msg_body = {"msgtype": "text", "text": {"content": text_msg}}
                
                # 发送请求
                resp = requests.post(
                    self.config.wecom_webhook,
                    json=msg_body,
                    timeout=10
                )
                
                if resp.status_code == 200:
                    result = resp.json()
                    if result.get("errcode") == 0:
                        self.log("✓ 企业微信通知发送成功！")
                    else:
                        self.log(f"✗ 企业微信通知发送失败: {result.get('errmsg')}")
                else:
                    self.log(f"✗ 企业微信通知发送失败: HTTP {resp.status_code}")
                    
            except Exception as e:
                self.log(f"✗ 发送企业微信通知出错: {e}")
        
        # WeChat通知（wxauto）
        if self.config.enable_wechat_notification:
            try:
                targets = parse_targets(self.config.wechat_targets)
                if not targets:
                    return
                
                message = format_shop_message(
                    shop_name, off_sale_list, sold_out_list
                )
                
                result = send_to_targets(
                    targets, message,
                    send_normal=self.config.wechat_send_normal,
                    has_abnormal=has_abnormal
                )
                
                if result['success_count'] > 0:
                    self.log(f"✓ WeChat通知已发送到 {result['success_count']} 个目标")
                if result['failed_count'] > 0:
                    self.log(f"✗ WeChat通知发送失败: {result['failed_count']} 个目标")
                    if result.get('errors'):
                        for err in result['errors']:
                            self.log(f"   ✗ {err}")
                    elif result['failed_targets']:
                        self.log(f"   失败目标: {', '.join(result['failed_targets'])}")
                        
            except Exception as e:
                import traceback
                self.log(f"✗ 发送WeChat通知出错: {e}")
                self.log(f"   {traceback.format_exc()}")
    
    def _simplify_skip_reason(self, reason: str) -> str:
        """简化跳过原因，避免显示完整错误信息"""
        if not reason:
            return "未知原因"
        
        # 常见原因简化映射
        simplify_map = {
            'Timeout': '页面加载超时',
            'timeout': '页面加载超时',
            '未找到门店下拉按钮': '门店切换失败',
            '未找到搜索框': '门店切换失败',
            '切换失败': '门店切换失败',
            '门店休息中': '门店休息中',
            '门店已下线': '门店已下线',
            '未营业': '门店未营业',
            'navigation': '页面导航失败',
            'PlaywrightMonitor': '监控超时',
        }
        
        # 检查是否匹配任何简化规则
        for key, simple in simplify_map.items():
            if key in reason:
                return simple
        
        # 如果原因太长，截取前20个字符
        if len(reason) > 20:
            return reason[:20] + '...'
        
        return reason
    
    def _send_multi_shop_summary(self, all_results: dict):
        """发送多门店监控总结到默认 webhook"""
        import requests
        from datetime import datetime
        
        try:
            now = datetime.now().strftime("%m-%d %H:%M")
            shops_monitored = all_results.get('shops_monitored', 0)
            shops_skipped = all_results.get('shops_skipped', 0)
            total_off_sale = all_results.get('total_off_sale', 0)
            total_sold_out = all_results.get('total_sold_out', 0)
            skipped_shops = all_results.get('skipped_shops', [])
            shop_results = all_results.get('shop_results', [])
            total_duration = all_results.get('total_duration', 0)
            
            total_shops = shops_monitored + shops_skipped
            
            # 格式化总耗时
            if total_duration >= 60:
                duration_str = f"{int(total_duration // 60)}分{int(total_duration % 60)}秒"
            else:
                duration_str = f"{total_duration:.0f}秒"
            
            # 构建 Markdown 消息
            md_lines = []
            md_lines.append(f"### 📊 多门店监控总结")
            md_lines.append(f"> 时间：{now}")
            md_lines.append(f"> 耗时：{duration_str}")
            md_lines.append(f"> 门店：{shops_monitored}/{total_shops}")
            md_lines.append("")
            
            # 统计信息
            md_lines.append(f"**📈 监控统计**")
            md_lines.append(f"> ✅ 成功监控：{shops_monitored} 个门店")
            md_lines.append(f"> ⏸ 跳过：{shops_skipped} 个门店")
            md_lines.append(f"> 🔻 总下架：{total_off_sale} 个商品")
            md_lines.append(f"> 🔴 总售罄：{total_sold_out} 个商品")
            md_lines.append("")
            
            # 成功监控的门店（增加营业状态）
            if shop_results:
                md_lines.append(f"**✅ 成功监控的门店**")
                for sr in shop_results:
                    off_count = len(sr.get('off_sale', []))
                    sold_count = len(sr.get('sold_out', []))
                    shop_dur = sr.get('duration', 0)
                    shop_status = sr.get('shop_status', '营业中')
                    short_name = sr.get('short_name', '')
                    if not short_name:
                        shop = sr.get('shop')
                        shop_name = shop.name if shop else sr.get('shop_name', '未知')
                        short_name = simplify_shop_name(shop_name)
                    # 营业状态文字
                    status_text = "[营业]" if shop_status == "营业中" else f"[{shop_status}]"
                    md_lines.append(f"> • {short_name} {status_text}: 下架{off_count}/售罄{sold_count} ({shop_dur:.0f}秒)")
                md_lines.append("")
            
            # 跳过的门店（精简显示，避免超过微信4096字符限制）
            if skipped_shops:
                md_lines.append(f"**⏸ 跳过的门店 ({len(skipped_shops)}个)**")
                
                # 简化跳过原因并按原因分组统计
                reason_count = {}
                for skip in skipped_shops:
                    raw_reason = skip.get('reason', '未知原因')
                    # 简化错误原因
                    simplified_reason = self._simplify_skip_reason(raw_reason)
                    reason_count[simplified_reason] = reason_count.get(simplified_reason, 0) + 1
                
                # 显示原因统计
                for reason, count in reason_count.items():
                    md_lines.append(f"> • {reason}: {count}个门店")
                
                # 如果跳过门店较少（<=8个），显示具体名称
                if len(skipped_shops) <= 8:
                    md_lines.append("> ---")
                    for skip in skipped_shops:
                        short_name = skip.get('short_name', '')
                        if not short_name:
                            short_name = simplify_shop_name(skip.get('name', '未知'))
                        md_lines.append(f"> {short_name}")
                
                md_lines.append("")
            
            md_lines.append(f"---")
            md_lines.append(f"💡 监控完成 | 详情请查看各门店通知")
            
            msg_body = {
                "msgtype": "markdown",
                "markdown": {"content": "\n".join(md_lines)}
            }
            
            # 发送请求
            resp = requests.post(
                self.config.wecom_webhook,
                json=msg_body,
                timeout=10
            )
            
            if resp.status_code == 200:
                result = resp.json()
                if result.get("errcode") == 0:
                    self.log("✓ 多门店监控总结已发送到默认 webhook")
                else:
                    self.log(f"✗ 总结发送失败: {result.get('errmsg')}")
            else:
                self.log(f"✗ 总结发送失败: HTTP {resp.status_code}")
                
        except Exception as e:
            self.log(f"✗ 发送监控总结出错: {e}")
    
    def _send_wechat_multi_shop_summary(self, all_results: dict):
        """发送多门店监控总结到WeChat"""
        from wechat_notifier import parse_targets, send_to_targets
        from datetime import datetime
        
        try:
            targets = parse_targets(self.config.wechat_targets)
            if not targets:
                return
            
            now = datetime.now().strftime("%m-%d %H:%M")
            shops_monitored = all_results.get('shops_monitored', 0)
            shops_skipped = all_results.get('shops_skipped', 0)
            total_off_sale = all_results.get('total_off_sale', 0)
            total_sold_out = all_results.get('total_sold_out', 0)
            total_duration = all_results.get('total_duration', 0)
            shop_results = all_results.get('shop_results', [])
            
            total_shops = shops_monitored + shops_skipped
            
            # 格式化总耗时
            if total_duration >= 60:
                duration_str = f"{int(total_duration // 60)}分{int(total_duration % 60)}秒"
            else:
                duration_str = f"{total_duration:.0f}秒"
            
            # 构建消息
            lines = []
            lines.append(f"📊 【多门店监控总结】")
            lines.append(f"⏰ {now}")
            lines.append(f"⏱ 耗时: {duration_str}")
            lines.append(f"🏪 门店: {shops_monitored}/{total_shops}")
            lines.append("")
            lines.append(f"✅ 成功监控: {shops_monitored} 个门店")
            lines.append(f"⏸ 跳过: {shops_skipped} 个门店")
            lines.append(f"🔻 总下架: {total_off_sale} 个商品")
            lines.append(f"🔴 总售罄: {total_sold_out} 个商品")
            lines.append("")
            
            # 成功监控的门店（最多显示10个）
            if shop_results:
                lines.append("✅ 成功监控的门店:")
                for sr in shop_results[:10]:
                    off_count = len(sr.get('off_sale', []))
                    sold_count = len(sr.get('sold_out', []))
                    shop_status = sr.get('shop_status', '营业中')
                    short_name = sr.get('short_name', '')
                    if not short_name:
                        shop = sr.get('shop')
                        shop_name = shop.name if shop else sr.get('shop_name', '未知')
                        short_name = simplify_shop_name(shop_name)
                    status_text = "[营业]" if shop_status == "营业中" else f"[{shop_status}]"
                    lines.append(f"  • {short_name} {status_text}: 下架{off_count}/售罄{sold_count}")
                if len(shop_results) > 10:
                    lines.append(f"  ... 等{len(shop_results)}个门店")
            
            lines.append("")
            lines.append("💡 详情请查看各门店通知")
            
            message = "\n".join(lines)
            
            # 发送到WeChat
            result = send_to_targets(
                targets, message,
                send_normal=self.config.wechat_send_normal,
                has_abnormal=(total_off_sale > 0 or total_sold_out > 0)
            )
            
            if result['success_count'] > 0:
                self.log(f"✓ WeChat多门店总结已发送到 {result['success_count']} 个目标")
            if result['failed_count'] > 0:
                self.log(f"✗ WeChat多门店总结发送失败: {result['failed_count']} 个目标")
                if result.get('errors'):
                    for err in result['errors']:
                        self.log(f"   ✗ {err}")
                elif result['failed_targets']:
                    self.log(f"   失败目标: {', '.join(result['failed_targets'])}")
                    
        except Exception as e:
            import traceback
            self.log(f"✗ 发送WeChat多门店总结出错: {e}")
            self.log(f"   {traceback.format_exc()}")
    
    def on_monitor_error(self, error: str):
        """监控出错"""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.log(f"✗ 错误: {error}")
        self.statusBar().showMessage("出错")
        QMessageBox.warning(self, "错误", error)
    
    def _load_shop_list(self, silent: bool = False):
        """
        加载门店列表（异步加载，避免UI卡死）
        
        Args:
            silent: 是否静默模式（不输出日志）
        """
        shop_file = self.shop_file_input.text().strip()
        if not shop_file:
            self.shop_count_label.setText("已加载: 0 个门店")
            self.shop_list_text.clear()
            return
        
        # 支持相对路径
        if not os.path.isabs(shop_file):
            # 获取应用目录
            import sys
            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))
            shop_file = os.path.join(base_dir, shop_file)
        
        if not os.path.exists(shop_file):
            # 文件不存在时，静默处理（可能是首次运行或Windows打包后）
            self.shop_count_label.setText("请选择门店列表文件")
            self.shop_list_text.clear()
            # 清空默认路径，避免误导
            if self.shop_file_input.text() == "doc/门店列表_v2.xlsx":
                self.shop_file_input.clear()
                self.shop_file_input.setPlaceholderText("请选择门店列表文件 (Excel)")
            return
        
        # 显示加载中状态
        self.shop_count_label.setText("正在加载...")
        self.shop_list_text.setText("加载门店列表中，请稍候...")
        
        # 保存silent参数供回调使用
        self._load_silent = silent
        self._load_shop_file = shop_file
        
        # 使用后台线程加载（避免UI卡死）
        self._shop_load_worker = ShopLoadWorker(shop_file, self.shop_manager)
        self._shop_load_worker.finished_signal.connect(self._on_shop_list_loaded)
        self._shop_load_worker.start()
    
    def _on_shop_list_loaded(self, success: bool, result):
        """门店列表加载完成回调"""
        silent = getattr(self, '_load_silent', False)
        shop_file = getattr(self, '_load_shop_file', '')
        
        if success:
            shops = self.shop_manager.shops
            self.shop_count_label.setText(f"已加载: {len(shops)} 个门店")
            
            # 显示门店列表预览（使用简化店名）
            preview_lines = []
            for i, shop in enumerate(shops[:10]):  # 只显示前10个
                status = "✓" if shop.enabled else "✗"
                short_name = simplify_shop_name(shop.name)
                preview_lines.append(f"{status} {short_name}")
            if len(shops) > 10:
                preview_lines.append(f"... 共 {len(shops)} 个门店")
            self.shop_list_text.setText("\n".join(preview_lines))
            
            # 在日志中打印简化的门店列表（非静默模式）
            if not silent:
                self.log(f"✓ 已加载 {len(shops)} 个门店:")
                for shop in shops:
                    short_name = simplify_shop_name(shop.name)
                    self.log(f"   • {short_name}")
                
                # 显示商品白名单信息
                whitelist_count = self.shop_manager.get_whitelist_count()
                if whitelist_count > 0:
                    self.log(f"✓ 已加载 {whitelist_count} 个商品白名单（仅通知白名单中的商品）")
            
            # 记录门店列表更新
            from datetime import datetime
            import json
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            old_file = self.config.shop_list_file
            old_time = self.config.shop_list_last_update
            
            # 保存历史记录
            try:
                history = json.loads(self.config.shop_list_history) if self.config.shop_list_history else []
            except:
                history = []
            
            if old_file and old_time and old_file != self.shop_file_input.text():
                history.append({
                    'file': old_file,
                    'time': old_time,
                    'shops': len(shops)
                })
                # 只保留最近5条历史
                history = history[-5:]
                self.config.shop_list_history = json.dumps(history, ensure_ascii=False)
            
            # 更新当前配置
            self.config.shop_list_file = self.shop_file_input.text()
            self.config.shop_list_last_update = now
            self.config_manager.save()
            
            if old_file and old_file != self.shop_file_input.text():
                self.log(f"   上一次: {old_file} ({old_time})")
        else:
            self.shop_count_label.setText("加载失败，请检查文件格式")
            self.shop_list_text.clear()
            if not silent:
                error_msg = result if isinstance(result, str) else "未知错误"
                self.log(f"⚠ 门店列表加载失败: {error_msg}")
    
    def select_shop_file(self):
        """选择门店列表文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择门店列表文件", "",
            "Excel文件 (*.xlsx *.xls);;JSON文件 (*.json);;所有文件 (*.*)"
        )
        if path:
            self.shop_file_input.setText(path)
            self._load_shop_list()
    
    def select_browser_path(self):
        """选择浏览器路径"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择浏览器", "",
            "可执行文件 (*.exe);;所有文件 (*.*)"
        )
        if path:
            self.browser_path_input.setText(path)
    
    def select_export_dir(self):
        """选择导出目录"""
        path = QFileDialog.getExistingDirectory(self, "选择导出目录")
        if path:
            self.export_dir_input.setText(path)
    
    def clear_cache(self):
        """清除缓存"""
        reply = QMessageBox.question(
            self, "确认",
            "确定要清除登录缓存吗？\n清除后需要重新登录。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self.config_manager.clear_login_cache():
                self.log("✓ 登录缓存已清除")
                QMessageBox.information(self, "提示", "缓存已清除，下次启动需重新登录")
            else:
                self.log("✗ 清除缓存失败")
    
    def closeEvent(self, event):
        """关闭窗口"""
        # 如果监控正在运行，完全停止并关闭浏览器
        if self.worker and self.worker.isRunning():
            self.worker.stop_and_close_browser()  # 退出程序时关闭浏览器
            self.worker.wait(3000)  # 等待最多3秒
        
        # 保存配置
        self.save_ui_to_config()
        self.config_manager.save()
        event.accept()
        
        # 强制退出整个进程，防止残留线程（如Selenium）阻塞导致无法关闭
        # 延时一点点确保配置保存完成
        QTimer.singleShot(100, lambda: os._exit(0))


def main():
    """主函数"""
    # 启用高 DPI 缩放
    if hasattr(Qt.ApplicationAttribute, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt.ApplicationAttribute, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    
    # 针对 Windows 的额外缩放设置
    if os.name == 'nt':
        os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # 设置统一字体
    font = None
    if os.name == 'nt':
        # Windows 下通常渲染较大，使用 9pt
        font = QFont("Microsoft YaHei", 9)
    else:
        # Linux/Mac 下尝试查找可用中文字体
        available_fonts = QFontDatabase.families()
        cn_fonts = ["WenQuanYi Micro Hei", "Noto Sans CJK SC", "Source Han Sans CN", "SimHei", "Droid Sans Fallback"]
        
        found_font = "sans-serif"
        for f in cn_fonts:
            if f in available_fonts:
                found_font = f
                break
                
        font = QFont(found_font, 10)
        
    app.setFont(font)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
