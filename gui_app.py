#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
淘宝闪购监控工具 - Windows桌面应用程序
带GUI界面，支持账号密码登录
"""

import os
import sys
import time
import threading
from datetime import datetime
from typing import Optional

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
try:
    from version import get_version
except ImportError:
    # Fallback if version module is missing during dev or specific build contexts
    def get_version(): return "1.0"



class MonitorWorker(QThread):
    """监控工作线程"""
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)
    login_required_signal = pyqtSignal()
    
    def __init__(self, config: AppConfig, profile_dir: str, auto_fill_login: bool = False):
        super().__init__()
        self.config = config
        self.profile_dir = profile_dir
        self.auto_fill_login = auto_fill_login
        self.running = True
        self.fetcher = None
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
            open_url = f"{self.config.base_url}/app/chain/{self.config.chain_id}/shop#app.chainshop.shop"
            self.log("正在查找浏览器...")
            self.progress_signal.emit(20)
            
            # 先检查是否能找到浏览器
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
            
            # 如果需要自动填充登录
            if self.auto_fill_login and self.config.taobao_username and self.config.taobao_password:
                if not self.running: return
                self.log("正在尝试自动登录...")
                self._try_auto_login()
            
            # 开始抓取
            if not self.running: return
            self.log("开始抓取商品数据...")
            self.status_signal.emit("抓取中...")
            self.progress_signal.emit(50)
            
            # 传递 running 标志给 fetcher（如果支持的话，需要修改 fetcher）
            # 目前只能在耗时操作后检查
            
            goods_list = self.fetcher.login_and_fetch(
                auto_login=False,
                wait_for_login=True,
                login_timeout=30 * 60,
            )
            
            if not self.running: return
            self.progress_signal.emit(80)
            
            # 统计结果
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
            
        except Exception as e:
            if self.running:
                self.error_signal.emit(f"监控出错: {str(e)}")
                import traceback
                self.log(f"错误详情: {traceback.format_exc()}")
        finally:
            # 如果是手动停止，清理工作由 force_stop 线程处理
            if self.running:
                self._cleanup()
    
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
    
    def stop(self):
        """停止线程"""
        if not self.running: return
        self.running = False
        self.log("正在停止...")
        
        # 在独立线程中执行清理，防止阻塞GUI
        def force_stop():
            if self.fetcher:
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


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.config_manager = ConfigManager()
        self.config = self.config_manager.config
        self.worker = None
        self.init_ui()
        self.load_config_to_ui()
    
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle(f"淘宝闪购监控工具 v{get_version()}")
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
            QLineEdit, QSpinBox {
                padding: 5px 8px; /* 减小内边距，防止遮挡按钮 */
                min-height: 28px; /* 增加最小高度 */
                border: 1px solid #dcdde1;
                border-radius: 6px;
                background-color: #f5f6fa;
                color: #2f3640;
                font-size: 13px;
            }
            QLineEdit:focus, QSpinBox:focus {
                border: 2px solid #0097e6;
                background-color: #ffffff;
            }
            /* 确保SpinBox按钮可见 */
            QSpinBox::up-button, QSpinBox::down-button {
                width: 20px;
                background-color: transparent;
                border: none;
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
        shop_tab = QWidget()
        shop_layout = QVBoxLayout(shop_tab)
        shop_layout.setContentsMargins(25, 25, 25, 25)
        
        shop_group = QGroupBox("🏪 店铺信息")
        shop_form = QFormLayout(shop_group)
        shop_form.setSpacing(20)
        shop_form.setContentsMargins(20, 25, 20, 20)
        
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
        notify_group = QGroupBox("📢 通知设置")
        notify_form = QFormLayout(notify_group)
        notify_form.setSpacing(20)
        notify_form.setContentsMargins(20, 25, 20, 20)
        
        self.webhook_input = QLineEdit()
        self.webhook_input.setPlaceholderText("企业微信机器人Webhook地址")
        notify_form.addRow("Webhook:", self.webhook_input)
        
        self.enable_notify_checkbox = QCheckBox("启用企业微信通知")
        notify_form.addRow("", self.enable_notify_checkbox)
        
        shop_layout.addWidget(notify_group)
        shop_layout.addStretch()
        tabs.addTab(shop_tab, "🏪 店铺")
        
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
        self.log("淘宝闪购监控工具已启动")
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
        
        self.debug_port_spin.setValue(self.config.debug_port)
        self.browser_path_input.setText(self.config.browser_path)
        self.headless_checkbox.setChecked(self.config.headless)
        self.interval_spin.setValue(self.config.check_interval)
        self.export_dir_input.setText(self.config.export_dir)
    
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
        
        self.config.debug_port = self.debug_port_spin.value()
        self.config.browser_path = self.browser_path_input.text().strip()
        self.config.headless = self.headless_checkbox.isChecked()
        self.config.check_interval = self.interval_spin.value()
        self.config.export_dir = self.export_dir_input.text().strip()
    
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
        
        if not self.config.chain_id or not self.config.shop_id:
            QMessageBox.warning(self, "提示", "请先配置店铺ID！")
            return
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        
        self.log("=" * 50)
        self.log("开始监控...")
        self.statusBar().showMessage("监控中...")
        
        # 创建工作线程
        profile_dir = self.config_manager.get_profile_dir()
        self.worker = MonitorWorker(
            self.config,
            profile_dir,
            auto_fill_login=self.config.auto_login
        )
        
        self.worker.log_signal.connect(self.log)
        self.worker.status_signal.connect(lambda s: self.statusBar().showMessage(s))
        self.worker.progress_signal.connect(self.progress_bar.setValue)
        self.worker.finished_signal.connect(self.on_monitor_finished)
        self.worker.error_signal.connect(self.on_monitor_error)
        
        self.worker.start()
    
    def stop_monitor(self):
        """停止监控"""
        if self.worker:
            self.worker.stop()
            # 不再阻塞等待，让 worker 的 force_stop 线程去处理
            # self.worker.wait(5000)
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.log("监控已停止")
        self.statusBar().showMessage("已停止")
    
    def on_monitor_finished(self, result: dict):
        """监控完成"""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        
        off_sale = len(result.get("off_sale", []))
        sold_out = len(result.get("sold_out", []))
        total = result.get("total", 0)
        
        self.off_sale_label.setText(f"已下架: {off_sale}")
        self.sold_out_label.setText(f"已售罄: {sold_out}")
        self.total_label.setText(f"总计: {total}")
        
        self.log("=" * 50)
        self.statusBar().showMessage("监控完成")
    
    def on_monitor_error(self, error: str):
        """监控出错"""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.log(f"✗ 错误: {error}")
        self.statusBar().showMessage("出错")
        QMessageBox.warning(self, "错误", error)
    
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
        # 如果监控正在运行，直接停止（不提示确认）
        if self.worker and self.worker.isRunning():
            self.stop_monitor()
        
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
