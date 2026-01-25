#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试浏览器启动脚本

使用与 gui_app.py 相同的方式启动浏览器，复用已保存的登录状态。
可用于调试和测试多门店切换等功能。

使用方法:
    python debug_browser.py                    # 启动浏览器并进入交互模式
    python debug_browser.py --test-switch      # 测试门店切换功能
    python debug_browser.py --shop "闵行维璟"   # 切换到指定门店
"""

import os
import sys
import time
import argparse

# 确保可以导入本地模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_manager import ConfigManager
from shop_manager import ShopManager
from selenium_fetcher import SeleniumGoodsFetcher


def log(msg: str):
    """打印日志"""
    print(f"[DEBUG] {msg}", flush=True)


def start_browser_with_login():
    """
    使用与 gui_app.py 相同的方式启动浏览器
    
    Returns:
        tuple: (fetcher, driver) 或 (None, None) 如果失败
    """
    print("=" * 60)
    print("调试浏览器启动器 - 使用已保存的登录状态")
    print("=" * 60)
    
    # 加载配置 - 和 gui_app.py 完全一样
    config_manager = ConfigManager()
    config = config_manager.config
    profile_dir = config_manager.get_profile_dir()
    
    print(f"\n配置信息:")
    print(f"  Profile目录: {profile_dir}")
    print(f"  Shop ID: {config.shop_id or '未设置'}")
    print(f"  Debug端口: {config.debug_port or 9222}")
    
    # 创建抓取器 - 和 gui_app.py MonitorWorker 完全一样
    print("\n正在初始化浏览器...")
    fetcher = SeleniumGoodsFetcher(
        shop_id=config.shop_id or "1303549223",
        chain_id=config.chain_id or "",
        base_url=config.base_url or "https://melody.shop.ele.me",
        headless=False,  # 调试时不使用无头模式
        debug_port=config.debug_port or 9222,
        user_data_dir=profile_dir,  # 使用已保存的登录状态
        browser_path=config.browser_path or None,
        auto_launch_browser=True,
    )
    fetcher._log_callback = log
    
    # 启动浏览器
    open_url = f"{config.base_url or 'https://melody.shop.ele.me'}/app/shop/{config.shop_id or '1303549223'}/food#app.shop.food?path=management"
    print(f"正在启动浏览器...")
    print(f"  URL: {open_url}")
    
    if not fetcher.ensure_debug_browser(open_url=open_url):
        print("✗ 无法启动浏览器")
        return None, None
    
    print("✓ 浏览器已启动")
    time.sleep(5)  # 等待浏览器完全启动
    
    # 初始化驱动
    print("正在初始化Selenium驱动...")
    max_retries = 3
    for retry in range(max_retries):
        if fetcher._init_driver():
            break
        print(f"  重试连接 ({retry + 1}/{max_retries})...")
        time.sleep(2)
    else:
        print("✗ 驱动初始化失败")
        return None, None
    
    print("✓ Selenium驱动初始化成功")
    time.sleep(2)
    
    # 获取当前页面信息
    try:
        print(f"  页面标题: {fetcher.driver.title}")
        print(f"  页面URL: {fetcher.driver.current_url}")
        
        # 如果不在商家后台页面，导航过去
        current_url = fetcher.driver.current_url
        if "melody.shop.ele.me" not in current_url or "login" in current_url:
            print("\n导航到商家后台...")
            fetcher.driver.get(open_url)
            time.sleep(5)
            print(f"  页面标题: {fetcher.driver.title}")
            print(f"  页面URL: {fetcher.driver.current_url}")
    except Exception as e:
        print(f"  页面操作失败: {e}")
        print("  尝试重新连接...")
        time.sleep(3)
        try:
            fetcher._init_driver()
            time.sleep(2)
            fetcher.driver.get(open_url)
            time.sleep(5)
        except:
            pass
    
    # 检查登录状态
    need_login = fetcher._need_login()
    print(f"  需要登录: {need_login}")
    
    if need_login:
        print("\n⚠ 请在浏览器中登录商家后台...")
        print("等待登录中 (最多5分钟)...")
        
        for i in range(150):  # 150 * 2秒 = 5分钟
            time.sleep(2)
            if not fetcher._need_login():
                print("✓ 登录成功！")
                break
            if i % 15 == 0 and i > 0:
                print(f"⏳ 等待登录中... ({i*2}秒)")
        else:
            print("✗ 登录超时")
            return None, None
    
    print("\n" + "=" * 60)
    print("✓ 浏览器已就绪，可以开始调试")
    print("=" * 60)
    
    return fetcher, fetcher.driver


def test_shop_switch(fetcher):
    """测试门店切换功能（带验证和重试）"""
    print("\n" + "=" * 60)
    print("测试门店切换功能（带验证和重试）")
    print("=" * 60)
    
    # 加载门店列表
    shop_manager = ShopManager("doc/店铺列表.xlsx")
    print(f"已加载 {len(shop_manager.shops)} 个门店")
    
    success_count = 0
    fail_count = 0
    failed_shops = []
    
    for shop in shop_manager.shops:
        print(f"\n>>> 切换到: {shop.name}")
        result = fetcher.switch_shop(shop.name)
        
        if result['success']:
            print(f"✓ 成功: {result['shop_name']}")
            success_count += 1
        else:
            print(f"✗ 失败: {result['message']}")
            fail_count += 1
            failed_shops.append({
                'name': shop.name,
                'reason': result['message']
            })
        
        time.sleep(2)
    
    # 打印统计结果
    print("\n" + "=" * 60)
    print("测试结果统计")
    print("=" * 60)
    print(f"  成功: {success_count} 个门店")
    print(f"  失败: {fail_count} 个门店")
    
    if failed_shops:
        print("\n失败门店详情:")
        for i, shop in enumerate(failed_shops, 1):
            print(f"  {i}. {shop['name']}")
            print(f"     原因: {shop['reason']}")
    
    print("\n测试完成！")


def switch_to_shop(fetcher, shop_name: str):
    """切换到指定门店"""
    print(f"\n切换到门店: {shop_name}")
    result = fetcher.switch_shop(shop_name)
    
    if result['success']:
        print(f"✓ 成功切换到: {result['shop_name']}")
    else:
        print(f"✗ 切换失败: {result['message']}")
    
    return result


def interactive_mode(fetcher, driver):
    """交互模式"""
    print("\n" + "=" * 60)
    print("进入交互模式")
    print("=" * 60)
    print("可用命令:")
    print("  switch <门店名>  - 切换到指定门店")
    print("  current         - 显示当前门店")
    print("  url             - 显示当前URL")
    print("  shops           - 列出所有门店")
    print("  test            - 测试门店切换")
    print("  quit / exit     - 退出")
    print("=" * 60)
    
    while True:
        try:
            cmd = input("\n>>> ").strip()
            
            if not cmd:
                continue
            
            if cmd in ('quit', 'exit', 'q'):
                print("退出调试模式")
                break
            
            if cmd == 'current':
                current = fetcher.get_current_shop_name()
                print(f"当前门店: {current or '未知'}")
            
            elif cmd == 'url':
                print(f"当前URL: {driver.current_url}")
            
            elif cmd == 'shops':
                shop_manager = ShopManager("doc/店铺列表.xlsx")
                print(f"共 {len(shop_manager.shops)} 个门店:")
                for i, shop in enumerate(shop_manager.shops):
                    print(f"  {i+1}. {shop.name}")
            
            elif cmd == 'test':
                test_shop_switch(fetcher)
            
            elif cmd.startswith('switch '):
                shop_name = cmd[7:].strip()
                if shop_name:
                    switch_to_shop(fetcher, shop_name)
                else:
                    print("请指定门店名称")
            
            else:
                print(f"未知命令: {cmd}")
                print("输入 'quit' 退出")
        
        except KeyboardInterrupt:
            print("\n退出调试模式")
            break
        except Exception as e:
            print(f"错误: {e}")


def main():
    parser = argparse.ArgumentParser(description="调试浏览器启动器")
    parser.add_argument('--test-switch', action='store_true', help='测试门店切换功能')
    parser.add_argument('--shop', type=str, help='切换到指定门店')
    parser.add_argument('--no-interactive', action='store_true', help='不进入交互模式')
    
    args = parser.parse_args()
    
    # 启动浏览器
    fetcher, driver = start_browser_with_login()
    
    if not fetcher or not driver:
        print("启动失败，退出")
        sys.exit(1)
    
    try:
        if args.test_switch:
            test_shop_switch(fetcher)
        elif args.shop:
            switch_to_shop(fetcher, args.shop)
        elif not args.no_interactive:
            interactive_mode(fetcher, driver)
        else:
            print("\n浏览器已启动，按 Ctrl+C 退出")
            while True:
                time.sleep(60)
    
    except KeyboardInterrupt:
        print("\n正在退出...")
    finally:
        # 不关闭浏览器，保持运行
        print("浏览器保持运行，可继续手动操作")


if __name__ == "__main__":
    main()
