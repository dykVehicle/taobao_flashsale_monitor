# -*- coding: utf-8 -*-
"""
淘宝闪购商品监控工具 - 企业微信机器人模块
"""

import json
import logging
from typing import List, Dict, Optional
from datetime import datetime

import requests

logger = logging.getLogger(__name__)


class WeComBot:
    """企业微信机器人"""
    
    def __init__(self, webhook_url: str):
        """
        初始化机器人
        
        Args:
            webhook_url: 企业微信机器人的webhook地址
        """
        self.webhook_url = webhook_url
    
    def send_text(self, content: str, mentioned_list: List[str] = None, 
                  mentioned_mobile_list: List[str] = None) -> bool:
        """
        发送文本消息
        
        Args:
            content: 消息内容
            mentioned_list: @的用户ID列表，@all表示所有人
            mentioned_mobile_list: @的手机号列表
            
        Returns:
            是否发送成功
        """
        data = {
            "msgtype": "text",
            "text": {
                "content": content,
            }
        }
        
        if mentioned_list:
            data["text"]["mentioned_list"] = mentioned_list
        if mentioned_mobile_list:
            data["text"]["mentioned_mobile_list"] = mentioned_mobile_list
        
        return self._send(data)
    
    def send_markdown(self, content: str) -> bool:
        """
        发送Markdown消息
        
        Args:
            content: Markdown格式的消息内容
            
        Returns:
            是否发送成功
        """
        data = {
            "msgtype": "markdown",
            "markdown": {
                "content": content
            }
        }
        return self._send(data)
    
    def send_goods_report(self, store_name: str, statistics: Dict, 
                          problematic_goods: Dict, 
                          mentioned_list: List[str] = None) -> bool:
        """
        发送商品状态报告
        
        Args:
            store_name: 门店名称
            statistics: 统计信息
            problematic_goods: 问题商品字典
            mentioned_list: @的用户列表
            
        Returns:
            是否发送成功
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 构建Markdown消息
        content = f"""## 📊 【{store_name}】商品状态报告

**统计时间**: {now}

### 📈 商品统计
| 状态 | 数量 |
|:---|---:|
| 总商品数 | {statistics.get('total', 0)} |
| <font color="info">在售</font> | {statistics.get('on_sale', 0)} |
| <font color="warning">已下架</font> | {statistics.get('off_sale', 0)} |
| <font color="warning">已售罄</font> | {statistics.get('sold_out', 0)} |
| <font color="warning">缺货</font> | {statistics.get('out_of_stock', 0)} |
| <font color="comment">暂停售卖</font> | {statistics.get('pause', 0)} |

"""
        
        # 添加问题商品列表
        has_issues = False
        
        if problematic_goods.get("已下架"):
            has_issues = True
            content += self._format_goods_list("🔴 已下架商品", problematic_goods["已下架"])
        
        if problematic_goods.get("已售罄"):
            has_issues = True
            content += self._format_goods_list("🟡 已售罄商品", problematic_goods["已售罄"])
        
        if problematic_goods.get("缺货"):
            has_issues = True
            content += self._format_goods_list("🟠 缺货商品", problematic_goods["缺货"])
        
        if problematic_goods.get("暂停售卖"):
            has_issues = True
            content += self._format_goods_list("⚪ 暂停售卖商品", problematic_goods["暂停售卖"])
        
        if not has_issues:
            content += "\n✅ **所有商品状态正常！**\n"
        
        # 发送消息
        success = self.send_markdown(content)
        
        # 如果有问题且需要@人
        if has_issues and mentioned_list:
            self.send_text("请及时处理以上问题商品！", mentioned_list=mentioned_list)
        
        return success
    
    def send_alert(self, store_name: str, alert_type: str, 
                   goods_list: List, mentioned_list: List[str] = None) -> bool:
        """
        发送告警消息
        
        Args:
            store_name: 门店名称
            alert_type: 告警类型（已下架/已售罄/缺货）
            goods_list: 商品列表
            mentioned_list: @的用户列表
            
        Returns:
            是否发送成功
        """
        if not goods_list:
            return True
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        emoji_map = {
            "已下架": "🔴",
            "已售罄": "🟡",
            "缺货": "🟠",
            "暂停售卖": "⚪"
        }
        emoji = emoji_map.get(alert_type, "⚠️")
        
        content = f"""## {emoji} 【{store_name}】{alert_type}告警

**告警时间**: {now}
**{alert_type}商品数**: {len(goods_list)}

"""
        content += self._format_goods_list(f"{alert_type}商品列表", goods_list, max_items=10)
        
        success = self.send_markdown(content)
        
        if mentioned_list:
            self.send_text(f"【{store_name}】有{len(goods_list)}个商品{alert_type}，请及时处理！", 
                          mentioned_list=mentioned_list)
        
        return success
    
    def _format_goods_list(self, title: str, goods_list: List, max_items: int = 20) -> str:
        """
        格式化商品列表为Markdown
        
        Args:
            title: 列表标题
            goods_list: 商品列表
            max_items: 最多显示数量
            
        Returns:
            Markdown格式的商品列表
        """
        content = f"\n### {title} ({len(goods_list)}个)\n"
        
        display_list = goods_list[:max_items]
        
        for i, goods in enumerate(display_list, 1):
            name = goods.goods_name if hasattr(goods, 'goods_name') else str(goods)
            content += f"{i}. {name}\n"
        
        if len(goods_list) > max_items:
            content += f"\n... 还有 {len(goods_list) - max_items} 个商品\n"
        
        return content
    
    def _send(self, data: Dict) -> bool:
        """
        发送消息到企业微信
        
        Args:
            data: 消息数据
            
        Returns:
            是否发送成功
        """
        try:
            response = requests.post(
                self.webhook_url,
                json=data,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            response.raise_for_status()
            
            result = response.json()
            if result.get("errcode") == 0:
                logger.info("消息发送成功")
                return True
            else:
                logger.error(f"消息发送失败: {result.get('errmsg', '未知错误')}")
                return False
                
        except requests.RequestException as e:
            logger.error(f"发送消息请求失败: {e}")
            return False


class WeComBotManager:
    """企业微信机器人管理器，管理多个门店的机器人"""
    
    def __init__(self, store_webhooks: Dict[str, str]):
        """
        初始化管理器
        
        Args:
            store_webhooks: 门店名称到webhook的映射
        """
        self.bots = {
            store_name: WeComBot(webhook)
            for store_name, webhook in store_webhooks.items()
        }
    
    def get_bot(self, store_name: str) -> Optional[WeComBot]:
        """获取指定门店的机器人"""
        return self.bots.get(store_name)
    
    def send_to_all(self, message: str) -> Dict[str, bool]:
        """
        向所有门店发送消息
        
        Args:
            message: 消息内容
            
        Returns:
            每个门店的发送结果
        """
        results = {}
        for store_name, bot in self.bots.items():
            results[store_name] = bot.send_text(message)
        return results
    
    def broadcast_report(self, reports: Dict[str, Dict]) -> Dict[str, bool]:
        """
        广播各门店的报告
        
        Args:
            reports: 门店报告数据 {store_name: {statistics, problematic_goods}}
            
        Returns:
            每个门店的发送结果
        """
        results = {}
        for store_name, report_data in reports.items():
            bot = self.get_bot(store_name)
            if bot:
                results[store_name] = bot.send_goods_report(
                    store_name=store_name,
                    statistics=report_data.get("statistics", {}),
                    problematic_goods=report_data.get("problematic_goods", {})
                )
            else:
                logger.warning(f"未找到门店 {store_name} 的机器人配置")
                results[store_name] = False
        return results

