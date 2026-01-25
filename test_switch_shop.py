#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试门店切换功能

使用方法:
1. 运行此脚本: python test_switch_shop.py
2. 浏览器会自动打开，请在浏览器中登录商家后台
3. 登录成功后，回到终端按 Enter 键继续
4. 脚本会自动测试切换门店功能
"""

import time
import sys
import os

# 确保导入路径正确
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from selenium_fetcher import SeleniumGoodsFetcher
from shop_manager import ShopManager


def test_switch_shop():
    """测试切换门店功能"""
    
    print("=" * 60)
    print("淘宝闪购商家后台 - 门店切换测试")
    print("=" * 60)
    print()
    
    # 加载门店列表
    shop_file = os.path.join(script_dir, "doc/店铺列表.xlsx")
    shop_manager = ShopManager(shop_file)
    if not shop_manager.shops:
        print("✗ 无法加载门店列表")
        print(f"  文件路径: {shop_file}")
        return
    
    print(f"✓ 已加载 {len(shop_manager.shops)} 个门店:")
    for i, shop in enumerate(shop_manager.shops):
        print(f"   {i+1}. {shop.name}")
    print()
    
    # 创建抓取器
    print("正在创建抓取器...")
    fetcher = SeleniumGoodsFetcher(
        shop_id="1303549223",
        chain_id="",
        debug_port=9222,
        auto_launch_browser=True,
    )
    
    # 定义日志回调
    def log_callback(msg):
        print(f"   {msg}")
    fetcher._log_callback = log_callback
    
    # 启动浏览器
    print("正在启动浏览器...")
    open_url = "https://melody.shop.ele.me/app/shop/1303549223/food#app.shop.food?path=management"
    
    if not fetcher.ensure_debug_browser(open_url=open_url):
        print("✗ 无法启动浏览器")
        print("  请确保：")
        print("  1. Chrome/Edge 浏览器已安装")
        print("  2. 没有其他程序占用端口 9222")
        return
    
    print("✓ 浏览器已启动")
    
    # 初始化驱动
    print("正在初始化Selenium驱动...")
    if not fetcher._init_driver():
        print("✗ 无法初始化驱动")
        return
    
    print("✓ 已连接浏览器")
    print()
    
    # 等待用户登录
    print("-" * 50)
    print("请在浏览器中登录商家后台")
    print("登录成功后，按 Enter 键继续测试...")
    print("-" * 50)
    input()
    
    # 检查是否需要登录
    if fetcher._need_login():
        print("⚠ 检测到仍需登录，请先在浏览器中完成登录")
        print("登录成功后，按 Enter 键继续...")
        input()
    
    # 获取当前门店名称
    current_shop = fetcher.get_current_shop_name()
    if current_shop:
        print(f"当前门店: {current_shop}")
    print()
    
    # 测试切换每个门店
    for idx, shop in enumerate(shop_manager.shops):
        print(f"\n{'='*50}")
        print(f"[{idx+1}/{len(shop_manager.shops)}] 测试切换到: {shop.name}")
        print(f"{'='*50}")
        
        result = fetcher.switch_shop(shop.name)
        
        if result['success']:
            print(f"✓ 切换成功!")
            print(f"  门店: {result['shop_name']}")
            print(f"  状态: 营业中")
            
            # 等待页面加载
            time.sleep(3)
            
            # 可以在这里添加商品抓取测试
            # goods = fetcher.login_and_fetch(...)
            
        else:
            print(f"✗ 切换失败: {result['message']}")
            if result['shop_name']:
                print(f"  找到的门店: {result['shop_name']}")
                status = '营业中' if result['is_open'] else '休息中/未营业'
                print(f"  状态: {status}")
        
        # 等待一下再测试下一个
        time.sleep(2)
        
        if idx < len(shop_manager.shops) - 1:
            print("\n按 Enter 测试下一个门店，输入 q 退出...")
            user_input = input()
            if user_input.lower() == 'q':
                break
    
    print("\n" + "=" * 50)
    print("测试完成！")
    print("=" * 50)


def main():
    try:
        test_switch_shop()
    except KeyboardInterrupt:
        print("\n\n用户中断，退出测试")
    except Exception as e:
        print(f"\n测试出错: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n按 Enter 退出...")
    input()


if __name__ == "__main__":
    main()
