#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试门店切换功能
请先手动在浏览器中登录商家后台，然后运行此脚本
"""

import time
import sys
from selenium_fetcher import SeleniumGoodsFetcher
from shop_manager import ShopManager


def test_switch_shop():
    """测试切换门店功能"""
    
    print("=" * 60)
    print("淘宝闪购商家后台 - 门店切换测试")
    print("=" * 60)
    
    # 加载门店列表
    shop_manager = ShopManager("doc/店铺列表.xlsx")
    if not shop_manager.shops:
        print("✗ 无法加载门店列表")
        return
    
    print(f"✓ 已加载 {len(shop_manager.shops)} 个门店")
    for i, shop in enumerate(shop_manager.shops):
        print(f"   {i+1}. {shop.name}")
    print()
    
    # 创建抓取器
    fetcher = SeleniumGoodsFetcher(
        shop_id="1303549223",  # 默认店铺ID
        chain_id="",
        debug_port=9222,
        auto_launch_browser=True,
    )
    
    # 定义日志回调
    def log_callback(msg):
        print(f"   {msg}")
    fetcher._log_callback = log_callback
    
    # 确保浏览器已启动
    print("正在连接浏览器...")
    open_url = "https://melody.shop.ele.me/app/shop/1303549223/food#app.shop.food?path=management"
    
    if not fetcher.ensure_debug_browser(open_url=open_url):
        print("✗ 无法连接或启动浏览器")
        print("  请确保：")
        print("  1. Chrome/Edge 浏览器已安装")
        print("  2. 没有其他程序占用端口 9222")
        return
    
    # 初始化驱动
    print("正在初始化Selenium驱动...")
    if not fetcher._init_driver():
        print("✗ 无法初始化驱动")
        return
    
    print("✓ 已连接浏览器")
    print()
    
    # 等待用户登录
    print("请确保您已在浏览器中登录商家后台")
    print("按 Enter 键继续测试门店切换...")
    input()
    
    # 测试切换每个门店
    for shop in shop_manager.shops:
        print(f"\n{'='*50}")
        print(f"测试切换到: {shop.name}")
        print(f"{'='*50}")
        
        result = fetcher.switch_shop(shop.name)
        
        if result['success']:
            print(f"✓ 切换成功: {result['shop_name']}")
            print(f"  营业状态: {'营业中' if result['is_open'] else '休息中'}")
        else:
            print(f"✗ 切换失败: {result['message']}")
            if result['shop_name']:
                print(f"  找到的门店: {result['shop_name']}")
                print(f"  营业状态: {'营业中' if result['is_open'] else '休息中'}")
        
        # 等待一下再测试下一个
        time.sleep(2)
        
        print("\n按 Enter 测试下一个门店，输入 q 退出...")
        user_input = input()
        if user_input.lower() == 'q':
            break
    
    print("\n测试完成！")
    fetcher.close()


if __name__ == "__main__":
    test_switch_shop()
