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
from PyQt6.QtGui import QFont, QIcon, QPalette, QColor, QTextCursor

from config_manager import ConfigManager, AppConfig


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
    
    def log(self, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_signal.emit(f"[{timestamp}] {msg}")
    
    def run(self):
        try:
            from selenium_fetcher import SeleniumGoodsFetcher
            
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
                self.log("常见浏览器位置:")
                self.log("  - C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe")
                self.log("  - C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe")
                self.log("或在「高级设置」中手动指定浏览器路径")
                self.error_signal.emit(
                    "无法找到浏览器！\n\n"
                    "请确保已安装以下浏览器之一：\n"
                    "• Microsoft Edge (Windows自带)\n"
                    "• Google Chrome\n"
                    "• Chromium\n\n"
                    "或在「高级设置」中手动指定浏览器路径"
                )
                return
            
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
            
            self.log("浏览器已启动")
            self.progress_signal.emit(30)
            
            # 如果需要自动填充登录
            if self.auto_fill_login and self.config.taobao_username and self.config.taobao_password:
                self.log("正在尝试自动登录...")
                self._try_auto_login()
            
            # 开始抓取
            self.log("开始抓取商品数据...")
            self.status_signal.emit("抓取中...")
            self.progress_signal.emit(50)
            
            goods_list = self.fetcher.login_and_fetch(
                auto_login=False,
                wait_for_login=True,
                login_timeout=30 * 60,
            )
            
            self.progress_signal.emit(80)
            
            # 统计结果
            off_sale = [g for g in goods_list if g.status == "OFF_SALE"]
            sold_out = [g for g in goods_list if g.status == "SOLD_OUT"]
            
            result = {
                "off_sale": off_sale,
                "sold_out": sold_out,
                "total": len(goods_list),
            }
            
            self.log(f"抓取完成！已下架: {len(off_sale)} 个, 已售罄: {len(sold_out)} 个")
            self.progress_signal.emit(100)
            self.status_signal.emit("完成")
            self.finished_signal.emit(result)
            
        except Exception as e:
            self.error_signal.emit(f"监控出错: {str(e)}")
            import traceback
            self.log(f"错误详情: {traceback.format_exc()}")
        finally:
            if self.fetcher:
                try:
                    self.fetcher.close()
                except:
                    pass
    
    def _try_auto_login(self):
        """尝试自动填充登录表单"""
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
        self.running = False
        if self.fetcher:
            try:
                self.fetcher.close()
            except:
                pass


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
        self.setWindowTitle("淘宝闪购监控工具 v1.0")
        self.setMinimumSize(900, 700)
        
        # 设置样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1a1a2e;
            }
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                color: #e94560;
                border: 2px solid #16213e;
                border-radius: 8px;
                margin-top: 12px;
                padding: 10px;
                background-color: #16213e;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px;
            }
            QLabel {
                color: #eaeaea;
                font-size: 12px;
            }
            QLineEdit, QSpinBox {
                padding: 8px 12px;
                border: 1px solid #0f3460;
                border-radius: 6px;
                background-color: #0f3460;
                color: #eaeaea;
                font-size: 12px;
                selection-background-color: #e94560;
            }
            QLineEdit:focus, QSpinBox:focus {
                border: 1px solid #e94560;
            }
            QPushButton {
                padding: 10px 24px;
                background-color: #e94560;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #ff6b6b;
            }
            QPushButton:pressed {
                background-color: #c73e54;
            }
            QPushButton:disabled {
                background-color: #4a4a6a;
                color: #8a8a9a;
            }
            QPushButton#secondaryBtn {
                background-color: #0f3460;
                border: 1px solid #e94560;
            }
            QPushButton#secondaryBtn:hover {
                background-color: #1a4a7a;
            }
            QCheckBox {
                color: #eaeaea;
                font-size: 12px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid #0f3460;
                background-color: #0f3460;
            }
            QCheckBox::indicator:checked {
                background-color: #e94560;
                border-color: #e94560;
            }
            QTextEdit {
                background-color: #0f3460;
                color: #00ff88;
                border: 1px solid #16213e;
                border-radius: 6px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 11px;
                padding: 8px;
            }
            QProgressBar {
                border: none;
                border-radius: 4px;
                background-color: #0f3460;
                height: 8px;
                text-align: center;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #e94560, stop:1 #ff6b6b);
                border-radius: 4px;
            }
            QTabWidget::pane {
                border: 1px solid #16213e;
                border-radius: 6px;
                background-color: #16213e;
            }
            QTabBar::tab {
                background-color: #0f3460;
                color: #eaeaea;
                padding: 10px 20px;
                margin-right: 2px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            QTabBar::tab:selected {
                background-color: #e94560;
            }
            QStatusBar {
                background-color: #0f3460;
                color: #eaeaea;
            }
        """)
        
        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 标题
        title_label = QLabel("🛒 淘宝闪购商品监控工具")
        title_label.setFont(QFont("Microsoft YaHei", 20, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #e94560; margin-bottom: 10px;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)
        
        # 使用分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, 1)
        
        # 左侧配置面板
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 10, 0)
        
        # Tab页
        tabs = QTabWidget()
        left_layout.addWidget(tabs)
        
        # --- 登录配置Tab ---
        login_tab = QWidget()
        login_layout = QVBoxLayout(login_tab)
        
        login_group = QGroupBox("📱 淘宝账号登录")
        login_form = QFormLayout(login_group)
        login_form.setSpacing(12)
        
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
        login_note.setStyleSheet("color: #8a8aaa; font-size: 11px; padding: 10px;")
        login_note.setWordWrap(True)
        login_layout.addWidget(login_note)
        
        login_layout.addStretch()
        tabs.addTab(login_tab, "🔐 登录")
        
        # --- 店铺配置Tab ---
        shop_tab = QWidget()
        shop_layout = QVBoxLayout(shop_tab)
        
        shop_group = QGroupBox("🏪 店铺信息")
        shop_form = QFormLayout(shop_group)
        shop_form.setSpacing(12)
        
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
        notify_form.setSpacing(12)
        
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
        
        browser_group = QGroupBox("🌐 浏览器设置")
        browser_form = QFormLayout(browser_group)
        browser_form.setSpacing(12)
        
        self.debug_port_spin = QSpinBox()
        self.debug_port_spin.setRange(1024, 65535)
        self.debug_port_spin.setValue(9222)
        browser_form.addRow("调试端口:", self.debug_port_spin)
        
        browser_path_layout = QHBoxLayout()
        self.browser_path_input = QLineEdit()
        self.browser_path_input.setPlaceholderText("留空自动检测")
        browser_path_btn = QPushButton("选择")
        browser_path_btn.setObjectName("secondaryBtn")
        browser_path_btn.setFixedWidth(60)
        browser_path_btn.clicked.connect(self.select_browser_path)
        browser_path_layout.addWidget(self.browser_path_input)
        browser_path_layout.addWidget(browser_path_btn)
        browser_form.addRow("浏览器路径:", browser_path_layout)
        
        self.headless_checkbox = QCheckBox("无头模式（后台运行，不显示浏览器窗口）")
        browser_form.addRow("", self.headless_checkbox)
        
        advanced_layout.addWidget(browser_group)
        
        monitor_group = QGroupBox("⏰ 监控设置")
        monitor_form = QFormLayout(monitor_group)
        monitor_form.setSpacing(12)
        
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
        export_btn.setFixedWidth(60)
        export_btn.clicked.connect(self.select_export_dir)
        export_layout.addWidget(self.export_dir_input)
        export_layout.addWidget(export_btn)
        monitor_form.addRow("导出目录:", export_layout)
        
        advanced_layout.addWidget(monitor_group)
        
        # 缓存管理
        cache_group = QGroupBox("🗑️ 缓存管理")
        cache_layout = QHBoxLayout(cache_group)
        
        clear_cache_btn = QPushButton("清除登录缓存")
        clear_cache_btn.setObjectName("secondaryBtn")
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
        right_layout.setContentsMargins(10, 0, 0, 0)
        
        # 控制按钮
        control_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("▶ 开始监控")
        self.start_btn.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        self.start_btn.setMinimumHeight(45)
        self.start_btn.clicked.connect(self.start_monitor)
        control_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.setObjectName("secondaryBtn")
        self.stop_btn.setMinimumHeight(45)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_monitor)
        control_layout.addWidget(self.stop_btn)
        
        self.save_btn = QPushButton("💾 保存配置")
        self.save_btn.setObjectName("secondaryBtn")
        self.save_btn.setMinimumHeight(45)
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
        
        self.off_sale_label = QLabel("已下架: 0")
        self.off_sale_label.setStyleSheet("color: #ff6b6b; font-size: 16px; font-weight: bold;")
        result_layout.addWidget(self.off_sale_label)
        
        self.sold_out_label = QLabel("已售罄: 0")
        self.sold_out_label.setStyleSheet("color: #ffd93d; font-size: 16px; font-weight: bold;")
        result_layout.addWidget(self.sold_out_label)
        
        self.total_label = QLabel("总计: 0")
        self.total_label.setStyleSheet("color: #6bcb77; font-size: 16px; font-weight: bold;")
        result_layout.addWidget(self.total_label)
        
        right_layout.addWidget(result_group)
        
        splitter.addWidget(right_panel)
        splitter.setSizes([350, 550])
        
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
            self.worker.wait(5000)
        
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
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(
                self, "确认",
                "监控正在运行中，确定要退出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            self.stop_monitor()
        
        # 保存配置
        self.save_ui_to_config()
        self.config_manager.save()
        event.accept()


def main():
    """主函数"""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # 设置应用程序图标（如果有的话）
    # app.setWindowIcon(QIcon("icon.ico"))
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
