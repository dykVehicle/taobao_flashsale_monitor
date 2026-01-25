#!/usr/bin/env python3
"""
测试企业微信机器人消息格式

由于保存的HTML页面是门店首页，不包含商品列表数据，
这里使用模拟数据测试企业微信消息格式。
"""

from datetime import datetime

def format_wecom_message(store_name: str, off_sale_items: list, sold_out_items: list) -> str:
    """
    格式化企业微信机器人消息
    
    Args:
        store_name: 门店名称
        off_sale_items: 已下架商品列表 [{"name": "商品名", "price": 10.0}, ...]
        sold_out_items: 已售罄商品列表 [{"name": "商品名", "price": 10.0}, ...]
    
    Returns:
        格式化后的消息文本
    """
    lines = []
    
    # 标题
    lines.append("🚨 淘宝闪购监控告警")
    lines.append(f"门店: {store_name}")
    lines.append(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("─────────────────")
    
    # 已下架商品
    if off_sale_items:
        lines.append(f"")
        lines.append(f"📦 已下架商品 ({len(off_sale_items)}个):")
        for i, item in enumerate(off_sale_items[:10], 1):  # 最多显示10个
            price_str = f"¥{item.get('price', 0):.2f}" if item.get('price') else ""
            lines.append(f"  {i}. {item['name']} {price_str}")
        if len(off_sale_items) > 10:
            lines.append(f"  ... 还有 {len(off_sale_items) - 10} 个")
    
    # 已售罄商品
    if sold_out_items:
        lines.append(f"")
        lines.append(f"🔴 已售罄商品 ({len(sold_out_items)}个):")
        for i, item in enumerate(sold_out_items[:10], 1):  # 最多显示10个
            price_str = f"¥{item.get('price', 0):.2f}" if item.get('price') else ""
            lines.append(f"  {i}. {item['name']} {price_str}")
        if len(sold_out_items) > 10:
            lines.append(f"  ... 还有 {len(sold_out_items) - 10} 个")
    
    # 汇总
    lines.append("")
    lines.append("─────────────────")
    lines.append(f"📊 总计: 下架{len(off_sale_items)}个, 售罄{len(sold_out_items)}个")
    
    return "\n".join(lines)


def main():
    # 模拟数据 - 基于饿了么商家后台的门店信息
    store_name = "阿狗手打·黑糖珍珠奶茶(长宁区龙之梦店)"
    
    # 模拟已下架商品
    off_sale_items = [
        {"name": "芋泥波波奶茶", "price": 18.00},
        {"name": "杨枝甘露", "price": 22.00},
        {"name": "椰椰芒芒", "price": 20.00},
    ]
    
    # 模拟已售罄商品
    sold_out_items = [
        {"name": "黑糖珍珠鲜奶", "price": 16.00},
        {"name": "手打柠檬茶", "price": 15.00},
        {"name": "芝芝莓莓", "price": 19.00},
        {"name": "多肉葡萄", "price": 21.00},
        {"name": "烤奶茶", "price": 12.00},
    ]
    
    # 生成消息
    message = format_wecom_message(store_name, off_sale_items, sold_out_items)
    
    print("=" * 50)
    print("企业微信机器人消息预览：")
    print("=" * 50)
    print()
    print(message)
    print()
    print("=" * 50)
    
    # 无异常情况
    print("\n无异常情况的消息：")
    print("-" * 50)
    message_no_issue = format_wecom_message(store_name, [], [])
    print(message_no_issue)


if __name__ == "__main__":
    main()
