#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
淘宝登录态复用测试脚本
验证：一次登录，后续复用登录态
"""

import os
import time
import sys

def test_taobao_login():
    """测试淘宝登录态"""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    
    # 固定的profile目录
    profile_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chromium_profile")
    debug_port = 9222
    
    print("=" * 60)
    print("淘宝登录态复用测试")
    print("=" * 60)
    print(f"Profile目录: {profile_dir}")
    print(f"调试端口: {debug_port}")
    print("=" * 60)
    
    # 启动浏览器
    import subprocess
    import socket
    
    def is_port_open():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                return s.connect_ex(("127.0.0.1", debug_port)) == 0
        except:
            return False
    
    if not is_port_open():
        print("\n正在启动 Chrome 浏览器...")
        os.makedirs(profile_dir, exist_ok=True)
        cmd = [
            "/usr/bin/google-chrome",
            f"--remote-debugging-port={debug_port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        if os.geteuid() == 0:
            cmd.append("--no-sandbox")
        
        subprocess.Popen(cmd)
        
        # 等待浏览器启动
        for _ in range(20):
            if is_port_open():
                break
            time.sleep(0.5)
    
    # 连接到浏览器
    print("\n连接到浏览器...")
    options = Options()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{debug_port}")
    
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(10)
    
    # 访问淘宝
    print("\n访问淘宝网: https://www.taobao.com/")
    driver.get("https://www.taobao.com/")
    print("等待页面完全加载（包括JS动态内容）...")
    time.sleep(15)  # 淘宝页面JS动态加载需要更长时间
    
    # 检测登录状态
    print("\n检测登录状态...")
    page_source = driver.page_source
    current_url = driver.current_url
    
    # 登录状态判断
    logged_in_indicators = [
        "我的淘宝", "已买到的宝贝", "购物车", "收藏夹",
        "会员中心", "退出", "我的足迹"
    ]
    
    login_indicators = [
        "请登录", "亲，请登录", "免费注册", "登录淘宝",
        "login.taobao", "扫码登录"
    ]
    
    is_logged_in = False
    
    # 检查是否已登录
    for indicator in logged_in_indicators:
        if indicator in page_source:
            is_logged_in = True
            break
    
    # 检查是否在登录页
    for indicator in login_indicators:
        if indicator in page_source or indicator in current_url:
            is_logged_in = False
            break
    
    # 二次确认：如果初步判断为未登录，再等待几秒后重新检查
    if not is_logged_in:
        print("初步检测未登录，等待页面完全加载后二次确认...")
        time.sleep(5)
        page_source = driver.page_source
        for indicator in logged_in_indicators:
            if indicator in page_source:
                is_logged_in = True
                print("二次确认：检测到登录状态！")
                break
    
    print(f"\n当前URL: {current_url}")
    print(f"页面标题: {driver.title}")
    
    # 先保存截图
    screenshot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "taobao_test.png")
    driver.save_screenshot(screenshot_path)
    print(f"截图已保存: {screenshot_path}")
    
    if is_logged_in:
        print("\n" + "=" * 60)
        print("✅ 检测结果: 已登录！")
        print("   登录态已成功复用，无需重新登录")
        print("=" * 60)
        return  # 已登录直接退出
    else:
        print("\n" + "=" * 60)
        print("⚠️  检测结果: 未登录")
        print("   请在浏览器中完成登录...")
        print("   登录后再次运行此脚本验证登录态复用")
        print("=" * 60)
        
        # 等待用户登录
        print("\n等待登录中（按 Ctrl+C 退出）...")
        try:
            while True:
                time.sleep(5)
                page_source = driver.page_source
                for indicator in logged_in_indicators:
                    if indicator in page_source:
                        print("\n✅ 检测到登录成功！")
                        print("   登录态已保存到 profile 目录")
                        print("   下次运行将自动复用登录态")
                        return
        except KeyboardInterrupt:
            print("\n用户取消")

if __name__ == "__main__":
    test_taobao_login()
