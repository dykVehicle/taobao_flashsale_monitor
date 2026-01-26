#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试商品分类子页面遍历功能
"""

import os
import sys
import asyncio
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_manager import ConfigManager
from playwright_monitor import PlaywrightMonitor, ensure_playwright_browsers

def log(msg):
    print(f"[TEST] {msg}")

async def test_category_parse():
    """测试分类遍历功能"""
    print("=" * 60)
    print("测试商品分类子页面遍历功能")
    print("=" * 60)
    
    # 加载配置
    config_manager = ConfigManager()
    config = config_manager.config
    profile_dir = config_manager.get_profile_dir()
    
    print(f"Profile目录: {profile_dir}")
    print(f"Shop ID: {config.shop_id or '1303549223'}")
    
    # 确保Playwright浏览器已安装
    if not ensure_playwright_browsers(log):
        print("Playwright浏览器未安装")
        return
    
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        # 启动浏览器，使用用户数据目录
        print("\n正在启动Chromium浏览器...")
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=False,
            args=[
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled',
            ]
        )
        
        print("✓ 浏览器已启动")
        
        # 获取或创建页面
        if browser.pages:
            page = browser.pages[0]
        else:
            page = await browser.new_page()
        
        # 导航到商品管理页面
        goods_url = f"https://melody.shop.ele.me/app/shop/{config.shop_id or '1303549223'}/food#app.shop.food?path=management"
        print(f"\n导航到: {goods_url}")
        await page.goto(goods_url, wait_until='load', timeout=60000)
        await asyncio.sleep(5)
        
        print(f"页面标题: {await page.title()}")
        print(f"页面URL: {page.url}")
        
        # 检查是否需要登录
        if 'login' in page.url.lower():
            print("\n⚠ 需要登录，请在浏览器中登录...")
            print("等待登录中...")
            for i in range(60):
                await asyncio.sleep(2)
                if 'login' not in page.url.lower():
                    print("✓ 登录成功!")
                    break
                if i % 10 == 0:
                    print(f"  等待登录... ({i*2}秒)")
            else:
                print("✗ 登录超时")
                await browser.close()
                return
        
        # 创建监控器来测试功能
        monitor = PlaywrightMonitor(
            num_workers=1,
            config=config,
            log_callback=log,
        )
        
        # 等待页面完全加载
        await asyncio.sleep(3)
        
        # 测试点击"已售罄"标签
        print("\n" + "=" * 60)
        print("测试点击'已售罄'标签并遍历分类")
        print("=" * 60)
        
        # 找到iframe
        frames = page.frames
        print(f"找到 {len(frames)} 个frame")
        
        work_frame = None
        for frame in frames:
            frame_url = frame.url.lower()
            if any(kw in frame_url for kw in ['food', 'management', 'goods']):
                work_frame = frame
                print(f"找到商品管理iframe: {frame_url[:80]}...")
                break
        
        if not work_frame:
            work_frame = page.main_frame
            print("使用主frame")
        
        # 测试分析标签结构
        print("\n分析标签结构...")
        elements = await monitor._analyze_tab_structure(work_frame)
        
        # 点击"已售罄"标签
        print("\n点击'已售罄'标签...")
        clicked = await monitor._click_tab_in_frame(work_frame, "已售罄")
        print(f"点击结果: {clicked}")
        
        if clicked:
            await asyncio.sleep(3)
            
            # 测试获取分类列表
            print("\n获取分类列表...")
            categories = await monitor._get_category_list(work_frame)
            print(f"发现 {len(categories)} 个分类:")
            for cat in categories:
                print(f"  - {cat.get('name', '')} ({cat.get('count', 0)})")
            
            # 测试解析商品
            print("\n解析商品列表（遍历所有分类）...")
            goods = await monitor._parse_goods_from_frame(work_frame, "SOLD_OUT")
            print(f"\n✓ 共解析到 {len(goods)} 个售罄商品:")
            for g in goods:
                print(f"  - {g.goods_name} [{g.category}]")
        
        # 同样测试"已下架"
        print("\n" + "=" * 60)
        print("测试点击'已下架'标签并遍历分类")
        print("=" * 60)
        
        clicked = await monitor._click_tab_in_frame(work_frame, "已下架")
        print(f"点击结果: {clicked}")
        
        if clicked:
            await asyncio.sleep(3)
            
            categories = await monitor._get_category_list(work_frame)
            print(f"发现 {len(categories)} 个分类:")
            for cat in categories:
                print(f"  - {cat.get('name', '')} ({cat.get('count', 0)})")
            
            goods = await monitor._parse_goods_from_frame(work_frame, "OFF_SALE")
            print(f"\n✓ 共解析到 {len(goods)} 个下架商品:")
            for g in goods:
                print(f"  - {g.goods_name} [{g.category}]")
        
        print("\n" + "=" * 60)
        print("测试完成！")
        print("=" * 60)
        
        # 保持浏览器打开一会儿
        print("\n浏览器将在30秒后关闭...")
        await asyncio.sleep(30)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_category_parse())
