#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WeChat通知模块 - 使用wxauto实现Windows桌面微信自动化
"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# 延迟导入wxauto，避免在非Windows环境或未安装时出错
# 这里缓存 WeChat 类（而不是模块），减少对 wxauto 内部导出方式的依赖
_WeChat = None
_wxauto_available = False


def _lazy_import_wxauto():
    """延迟导入wxauto"""
    global _WeChat, _wxauto_available
    
    if _wxauto_available:
        return _WeChat
    
    try:
        from wxauto import WeChat  # type: ignore
        _WeChat = WeChat
        _wxauto_available = True
        logger.info("wxauto模块加载成功")
        return _WeChat
    except ImportError:
        logger.warning("wxauto未安装，WeChat通知功能不可用。请运行: pip install wxauto")
        _wxauto_available = False
        return None
    except Exception as e:
        logger.error(f"加载wxauto失败: {e}")
        _wxauto_available = False
        return None


def is_wxauto_available() -> bool:
    """检查wxauto是否可用"""
    _lazy_import_wxauto()
    return _wxauto_available


def parse_targets(targets_text: str) -> List[str]:
    """
    解析WeChat目标（个人或群组名称），支持多行
    
    Args:
        targets_text: 多行文本，每行一个目标名称
        
    Returns:
        目标名称列表（去除空行和空白）
    """
    if not targets_text:
        return []
    
    targets = []
    for line in targets_text.strip().split('\n'):
        line = line.strip()
        if line and not line.startswith('#'):  # 忽略空行和注释行
            targets.append(line)
    
    return targets


def format_shop_message(
    shop_name: str,
    off_sale_goods: List,
    sold_out_goods: List,
    shop_status: str = "营业中",
    duration: float = 0,
) -> str:
    """
    格式化门店监控消息（用于WeChat发送）
    
    Args:
        shop_name: 门店名称
        off_sale_goods: 已下架商品列表
        sold_out_goods: 已售罄商品列表
        shop_status: 门店营业状态
        duration: 监控耗时（秒）
        
    Returns:
        格式化后的消息文本
    """
    from datetime import datetime
    
    now = datetime.now().strftime("%m-%d %H:%M")
    off_count = len(off_sale_goods)
    sold_count = len(sold_out_goods)
    total = off_count + sold_count
    
    lines = []
    
    if total == 0:
        # 正常状态
        lines.append(f"✅ 【{shop_name}】")
        lines.append(f"🏪 {shop_status}")
        lines.append(f"⏰ {now}")
        lines.append("")
        lines.append("商品状态正常，无异常商品 👍")
    else:
        # 异常状态
        lines.append(f"🔔 【商品状态提醒】")
        lines.append(f"📍 {shop_name}")
        lines.append(f"🏪 {shop_status}")
        lines.append(f"⏰ {now}")
        if duration > 0:
            lines.append(f"⏱ 耗时: {int(duration)}秒")
        lines.append("")
        
        if off_sale_goods:
            lines.append(f"🔻 已下架 ({off_count})")
            lines.append("─" * 16)
            for i, g in enumerate(off_sale_goods, 1):
                name = g.goods_name[:15] + "..." if len(g.goods_name) > 15 else g.goods_name
                lines.append(f"  {i}. {name}")
            lines.append("")
        
        if sold_out_goods:
            lines.append(f"🔴 已售罄 ({sold_count})")
            lines.append("─" * 16)
            for i, g in enumerate(sold_out_goods, 1):
                name = g.goods_name[:15] + "..." if len(g.goods_name) > 15 else g.goods_name
                lines.append(f"  {i}. {name}")
            lines.append("")
        
        lines.append("─" * 16)
        lines.append(f"📊 共 {total} 个异常商品")
        lines.append("💡 请及时处理")
    
    return "\n".join(lines)


def send_text(target: str, message: str, retry: int = 2) -> dict:
    """
    发送文本消息到指定目标（个人或群组）
    
    Args:
        target: 目标名称（个人微信名或群组名）
        message: 消息内容
        retry: 重试次数
        
    Returns:
        {'success': bool, 'error': str or None}
    """
    WeChat = _lazy_import_wxauto()
    if not WeChat:
        err = "wxauto未安装，请运行: pip install wxauto"
        logger.error(err)
        return {'success': False, 'error': err}
    
    try:
        # 初始化微信客户端
        wx = WeChat()
        
        # 查找目标（个人或群组）
        wx.GetSessionList()  # 刷新会话列表
        
        # 尝试发送消息
        last_error = None
        for attempt in range(retry + 1):
            try:
                wx.SendMsg(message, target)
                logger.info(f"✓ WeChat消息已发送到: {target}")
                return {'success': True, 'error': None}
            except Exception as e:
                last_error = str(e)
                if attempt < retry:
                    logger.warning(f"发送失败，重试 {attempt + 1}/{retry}: {e}")
                    import time
                    time.sleep(1)
                else:
                    logger.error(f"✗ 发送WeChat消息失败: {e}")
        
        return {'success': False, 'error': last_error}
        
    except Exception as e:
        import traceback
        err = f"{e}\n{traceback.format_exc()}"
        logger.error(f"✗ WeChat发送出错: {err}")
        return {'success': False, 'error': str(e)}


def send_to_targets(
    targets: List[str],
    message: str,
    send_normal: bool = False,
    has_abnormal: bool = True,
) -> dict:
    """
    发送消息到多个目标
    
    Args:
        targets: 目标列表
        message: 消息内容
        send_normal: 是否发送正常状态消息
        has_abnormal: 是否有异常商品（False表示正常状态）
        
    Returns:
        {
            'success_count': int,
            'failed_count': int,
            'failed_targets': List[str]
        }
    """
    # 如果是正常状态且不发送正常消息，直接返回
    if not has_abnormal and not send_normal:
        return {
            'success_count': 0,
            'failed_count': 0,
            'failed_targets': []
        }
    
    if not targets:
        logger.warning("没有配置WeChat目标")
        return {
            'success_count': 0,
            'failed_count': 0,
            'failed_targets': []
        }
    
    success_count = 0
    failed_count = 0
    failed_targets = []
    errors = []
    
    for target in targets:
        result = send_text(target, message)
        if result['success']:
            success_count += 1
        else:
            failed_count += 1
            failed_targets.append(target)
            if result.get('error'):
                errors.append(f"{target}: {result['error']}")
    
    return {
        'success_count': success_count,
        'failed_count': failed_count,
        'failed_targets': failed_targets,
        'errors': errors,
    }
