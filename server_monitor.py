#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
淘宝闪购智能助手Agent - 服务端无头模式运行脚本

适用于在Linux云服务器上无GUI运行，使用Playwright headless模式。
首次登录需要临时开启有头模式（通过VNC或X11转发）完成验证。

用法:
    # 首次登录（需要VNC/X11显示）
    python server_monitor.py --login

    # 后台无头监控（登录后）
    python server_monitor.py

    # 指定参数运行
    python server_monitor.py --interval 30 --workers 5

    # 仅运行一次
    python server_monitor.py --once

    # 使用配置文件
    python server_monitor.py --config /path/to/config.json

环境变量:
    WECOM_WEBHOOK  - 企业微信机器人Webhook地址（可覆盖配置文件中的值）
    HEADLESS       - 是否无头模式（默认 true，首次登录设为 false）
"""

import os
import sys
import time
import signal
import logging
import argparse
import json
import asyncio
import requests
from datetime import datetime
from typing import List, Optional

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('monitor.log', encoding='utf-8'),
    ]
)
logger = logging.getLogger(__name__)

# 导入项目模块
from config_manager import ConfigManager, AppConfig
from shop_manager import ShopManager, ShopInfo
from playwright_monitor import PlaywrightMonitor, ensure_playwright_browsers
from wechat_notifier import format_shop_message


# ========== 通知模块 ==========

def send_wecom_webhook(webhook_url: str, message: str) -> bool:
    """发送企业微信Webhook通知"""
    if not webhook_url:
        return False

    try:
        payload = {
            "msgtype": "text",
            "text": {"content": message}
        }
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code == 200:
            result = resp.json()
            if result.get('errcode') == 0:
                logger.info(f"企业微信通知发送成功")
                return True
            else:
                logger.warning(f"企业微信通知发送失败: {result}")
                return False
        else:
            logger.warning(f"企业微信通知HTTP错误: {resp.status_code}")
            return False
    except Exception as e:
        logger.error(f"发送企业微信通知失败: {e}")
        return False


def send_dingtalk_webhook(webhook_url: str, message: str) -> bool:
    """发送钉钉机器人通知"""
    if not webhook_url:
        return False

    try:
        payload = {
            "msgtype": "text",
            "text": {"content": message}
        }
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code == 200:
            result = resp.json()
            if result.get('errcode') == 0:
                logger.info(f"钉钉通知发送成功")
                return True
            else:
                logger.warning(f"钉钉通知发送失败: {result}")
                return False
        else:
            logger.warning(f"钉钉通知HTTP错误: {resp.status_code}")
            return False
    except Exception as e:
        logger.error(f"发送钉钉通知失败: {e}")
        return False


def send_serverchan(sendkey: str, title: str, message: str) -> bool:
    """发送Server酱通知 (https://sct.ftqq.com/)"""
    if not sendkey:
        return False

    try:
        url = f"https://sctapi.ftqq.com/{sendkey}.send"
        payload = {"title": title, "desp": message}
        resp = requests.post(url, data=payload, timeout=10)
        if resp.status_code == 200:
            logger.info(f"Server酱通知发送成功")
            return True
        else:
            logger.warning(f"Server酱通知失败: {resp.status_code}")
            return False
    except Exception as e:
        logger.error(f"发送Server酱通知失败: {e}")
        return False


def send_pushplus(token: str, title: str, content: str) -> bool:
    """发送PushPlus通知 (https://www.pushplus.plus/)"""
    if not token:
        return False
    try:
        url = "http://www.pushplus.plus/send"
        payload = {"token": token, "title": title, "content": content, "template": "txt"}
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            result = resp.json()
            if result.get("code") == 200:
                logger.info("PushPlus通知发送成功")
                return True
            else:
                logger.warning(f"PushPlus通知失败: {result}")
                return False
        else:
            logger.warning(f"PushPlus通知HTTP错误: {resp.status_code}")
            return False
    except Exception as e:
        logger.error(f"发送PushPlus通知失败: {e}")
        return False


_wecom_token_cache = {"token": "", "expires": 0}


def _get_wecom_access_token(corpid: str, corpsecret: str) -> str:
    """获取企业微信应用 access_token（带缓存）"""
    if _wecom_token_cache["token"] and time.time() < _wecom_token_cache["expires"]:
        return _wecom_token_cache["token"]
    try:
        url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={corpid}&corpsecret={corpsecret}"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get("errcode") == 0:
            _wecom_token_cache["token"] = data["access_token"]
            _wecom_token_cache["expires"] = time.time() + data.get("expires_in", 7200) - 300
            return data["access_token"]
        else:
            logger.warning(f"获取企业微信token失败: {data}")
            return ""
    except Exception as e:
        logger.error(f"获取企业微信token异常: {e}")
        return ""


def send_wecom_app_message(corpid: str, corpsecret: str, agentid: str, touser: str, content: str) -> bool:
    """发送企业微信应用消息（推送到个人微信）"""
    if not all([corpid, corpsecret, agentid]):
        return False
    try:
        token = _get_wecom_access_token(corpid, corpsecret)
        if not token:
            return False
        url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
        payload = {
            "touser": touser or "@all",
            "msgtype": "text",
            "agentid": int(agentid),
            "text": {"content": content}
        }
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            result = resp.json()
            if result.get("errcode") == 0:
                logger.info("企业微信应用消息发送成功")
                return True
            else:
                logger.warning(f"企业微信应用消息失败: {result}")
        return False
    except Exception as e:
        logger.error(f"发送企业微信应用消息失败: {e}")
        return False


def send_wechat_via_wcf(wcf_url: str, receivers: str, message: str) -> bool:
    """通过 wxauto HTTP API 发送微信消息到个人或群

    Args:
        wcf_url: wxauto HTTP 服务地址，如 http://192.168.1.7:9999
        receivers: 接收者列表，逗号分隔。直接使用微信昵称或群名
        message: 消息内容
    """
    if not wcf_url or not receivers:
        return False
    wcf_url = wcf_url.rstrip('/')
    success_count = 0
    for receiver in receivers.split(','):
        receiver = receiver.strip()
        if not receiver:
            continue
        try:
            resp = requests.post(f"{wcf_url}/api/sendText", json={
                "who": receiver,
                "msg": message,
            }, timeout=15)
            if resp.status_code == 200:
                result = resp.json()
                if result.get("code") == 0:
                    logger.info(f"微信消息已发送到: {receiver}")
                    success_count += 1
                else:
                    logger.warning(f"微信消息发送失败({receiver}): {result.get('msg')}")
            else:
                logger.warning(f"微信消息发送失败({receiver}): HTTP {resp.status_code}")
        except Exception as e:
            logger.error(f"发送微信消息失败({receiver}): {e}")
    return success_count > 0


# ========== 核心监控逻辑 ==========

class ServerMonitor:
    """服务端监控管理器"""

    def __init__(self, args):
        self.args = args
        self.running = True
        self.config_manager = ConfigManager()
        self.config = self.config_manager.config
        self.shop_manager = ShopManager()

        # 覆盖配置
        self._apply_args()

        # 注册信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """优雅退出"""
        logger.info(f"收到退出信号 ({signum})，正在停止...")
        self.running = False

    def _apply_args(self):
        """将命令行参数应用到配置"""
        if self.args.interval:
            self.config.check_interval = self.args.interval
        if self.args.workers:
            self.config.parallel_workers = self.args.workers
        if self.args.chain_id:
            self.config.chain_id = self.args.chain_id
        if self.args.shop_id:
            self.config.shop_id = self.args.shop_id
        if self.args.webhook:
            self.config.wecom_webhook = self.args.webhook
            self.config.enable_notification = True
        if self.args.shop_list:
            self.config.shop_list_file = self.args.shop_list

        # 环境变量覆盖
        env_webhook = os.environ.get('WECOM_WEBHOOK')
        if env_webhook:
            self.config.wecom_webhook = env_webhook
            self.config.enable_notification = True

        # 无头模式
        env_headless = os.environ.get('HEADLESS', 'true').lower()
        if self.args.login:
            self.config.headless = False  # 登录模式强制有头
        else:
            self.config.headless = env_headless in ('true', '1', 'yes')

    def log(self, msg: str):
        """统一日志输出"""
        logger.info(msg)

    def _send_notification(self, shop: ShopInfo, off_sale: list, sold_out: list,
                           shop_status: str = "营业中", duration: float = 0):
        """发送通知回调"""
        message = format_shop_message(
            shop_name=shop.name,
            off_sale_goods=off_sale,
            sold_out_goods=sold_out,
            shop_status=shop_status,
            duration=duration,
        )

        has_abnormal = len(off_sale) > 0 or len(sold_out) > 0

        # 企业微信Webhook通知（每个门店可能有独立的webhook）
        webhook = shop.webhook or self.config.wecom_webhook
        if webhook and (has_abnormal or self.config.wechat_send_normal):
            send_wecom_webhook(webhook, message)

        # 钉钉通知
        dingtalk_webhook = os.environ.get('DINGTALK_WEBHOOK')
        if dingtalk_webhook and (has_abnormal or self.config.wechat_send_normal):
            send_dingtalk_webhook(dingtalk_webhook, message)

        # Server酱通知
        serverchan_key = os.environ.get('SERVERCHAN_KEY')
        if serverchan_key and has_abnormal:
            title = f"商品异常: {shop.name}"
            send_serverchan(serverchan_key, title, message)

        # PushPlus通知
        pushplus_token = os.environ.get('PUSHPLUS_TOKEN')
        if pushplus_token and (has_abnormal or self.config.wechat_send_normal):
            title = f"商品异常: {shop.name}" if has_abnormal else f"商品正常: {shop.name}"
            send_pushplus(pushplus_token, title, message)

        # 企业微信应用消息（推送到个人微信）
        wecom_corpid = os.environ.get('WECOM_CORPID')
        wecom_corpsecret = os.environ.get('WECOM_CORPSECRET')
        wecom_agentid = os.environ.get('WECOM_AGENTID')
        wecom_touser = os.environ.get('WECOM_TOUSER', '@all')
        if all([wecom_corpid, wecom_corpsecret, wecom_agentid]) and (has_abnormal or self.config.wechat_send_normal):
            send_wecom_app_message(wecom_corpid, wecom_corpsecret, wecom_agentid, wecom_touser, message)

        # wxauto 微信消息（始终发送每个门店的结果）
        wcf_url = os.environ.get('WCF_URL')
        wcf_receivers = os.environ.get('WCF_RECEIVERS')
        if wcf_url and wcf_receivers:
            send_wechat_via_wcf(wcf_url, wcf_receivers, message)

    def _send_summary_notification(self, results: dict, duration_str: str):
        """发送汇总监控结果通知"""
        from datetime import datetime
        now = datetime.now().strftime("%m-%d %H:%M")

        monitored = results.get('shops_monitored', 0)
        skipped = results.get('shops_skipped', 0)
        total_off = results.get('total_off_sale', 0)
        total_sold = results.get('total_sold_out', 0)
        total_abnormal = total_off + total_sold
        shop_results = results.get('shop_results', [])
        skipped_shops = results.get('skipped_shops', [])

        lines = []
        if total_abnormal == 0 and skipped == 0:
            lines.append("✅ 【监控汇总】全部正常")
        elif total_abnormal > 0:
            lines.append("🔔 【监控汇总】发现异常")
        else:
            lines.append("📋 【监控汇总】")

        lines.append(f"⏰ {now}  耗时 {duration_str}")
        lines.append(f"📊 监控 {monitored} 家 | 跳过 {skipped} 家")
        if total_abnormal > 0:
            lines.append(f"⚠️ 下架 {total_off} | 售罄 {total_sold}")
        lines.append("")

        abnormal_shops = [r for r in shop_results if r.get('off_sale') or r.get('sold_out')]
        normal_shops = [r for r in shop_results if not r.get('off_sale') and not r.get('sold_out')]

        if abnormal_shops:
            lines.append("── 异常门店 ──")
            for r in abnormal_shops:
                name = r.get('short_name') or r.get('shop_name', '')
                off = len(r.get('off_sale') or [])
                sold = len(r.get('sold_out') or [])
                parts = []
                if off: parts.append(f"下架{off}")
                if sold: parts.append(f"售罄{sold}")
                lines.append(f"  ❌ {name}: {', '.join(parts)}")
            lines.append("")

        if normal_shops:
            names = [r.get('short_name') or r.get('shop_name', '') for r in normal_shops]
            lines.append(f"── 正常门店({len(names)}家) ──")
            lines.append(f"  ✅ {', '.join(names)}")
            lines.append("")

        if skipped_shops:
            lines.append("── 跳过门店 ──")
            for s in skipped_shops:
                name = s.get('short_name') or s.get('name', '')
                reason = s.get('reason', '未知')
                lines.append(f"  ⏭ {name}: {reason}")

        summary_msg = "\n".join(lines)

        wcf_url = os.environ.get('WCF_URL')
        wcf_receivers = os.environ.get('WCF_RECEIVERS')
        if wcf_url and wcf_receivers:
            send_wechat_via_wcf(wcf_url, wcf_receivers, summary_msg)

    def _load_shops(self) -> List[ShopInfo]:
        """加载门店列表"""
        shop_file = self.config.shop_list_file

        if shop_file and os.path.exists(shop_file):
            self.log(f"加载门店列表: {shop_file}")
            success = self.shop_manager.load(shop_file)
            if success:
                shops = self.shop_manager.get_enabled_shops()
                self.log(f"已加载 {len(shops)} 个门店")
                return shops
            else:
                self.log(f"门店列表加载失败: {shop_file}")

        # 如果没有门店列表，使用配置中的单个门店
        self.log("使用配置中的单门店模式")
        return [ShopInfo(
            name=self.config.shop_name or "默认门店",
            webhook=self.config.wecom_webhook,
            enabled=True,
        )]

    def _run_once(self, shops: List[ShopInfo]):
        """运行一次监控"""
        monitor_start = time.time()

        self.log(f"")
        self.log(f"{'=' * 50}")
        self.log(f"开始监控 {len(shops)} 个门店")
        self.log(f"并行页面: {self.config.parallel_workers}")
        self.log(f"无头模式: {'是' if self.config.headless else '否'}")
        self.log(f"{'=' * 50}")

        # 创建Playwright监控器
        pw_monitor = PlaywrightMonitor(
            num_workers=self.config.parallel_workers,
            config=self.config,
            log_callback=self.log,
            only_open_shops=self.config.only_open_shops,
            retry_timeout_minutes=self.config.retry_timeout_minutes,
            shop_manager=self.shop_manager if self.shop_manager.valid_goods_names else None,
        )

        # 运行监控
        results = pw_monitor.run_parallel_monitor(
            shops=shops,
            send_notification_callback=self._send_notification,
        )

        # 打印汇总
        duration = time.time() - monitor_start
        if duration >= 60:
            duration_str = f"{int(duration // 60)}分{int(duration % 60)}秒"
        else:
            duration_str = f"{duration:.0f}秒"

        self.log(f"")
        self.log(f"{'=' * 50}")
        self.log(f"监控完成")
        self.log(f"  总耗时: {duration_str}")
        self.log(f"  成功: {results.get('shops_monitored', 0)} 个门店")
        self.log(f"  跳过: {results.get('shops_skipped', 0)} 个门店")
        self.log(f"  下架: {results.get('total_off_sale', 0)} 个商品")
        self.log(f"  售罄: {results.get('total_sold_out', 0)} 个商品")
        self.log(f"{'=' * 50}")

        self._send_summary_notification(results, duration_str)

        return results

    def run(self):
        """主运行循环"""
        self.log("=" * 50)
        self.log("淘宝闪购智能助手 - 服务端模式")
        self.log("=" * 50)

        # 确保Playwright浏览器已安装
        self.log("检查Playwright浏览器...")
        if not ensure_playwright_browsers(self.log):
            self.log("Playwright浏览器未安装，正在安装...")
            return

        # 加载门店列表
        shops = self._load_shops()
        if not shops:
            self.log("没有可监控的门店，退出")
            return

        # 登录模式：仅启动浏览器等待手动登录
        if self.args.login:
            self.log("")
            self.log("*** 登录模式 ***")
            self.log("浏览器将以有头模式启动，请在浏览器中完成登录")
            self.log("登录成功后，登录状态会自动保存到 playwright_profile 目录")
            self.log("之后可以使用无头模式运行: python server_monitor.py")
            self.log("")
            self._run_once(shops)
            return

        # 单次运行模式
        if self.args.once:
            self._run_once(shops)
            return

        # 持续监控模式
        round_num = 0
        while self.running:
            round_num += 1
            self.log(f"")
            self.log(f"===== 第 {round_num} 轮监控 =====")

            self._run_once(shops)

            if not self.running:
                break

            # 等待下一轮
            interval = self.config.check_interval * 60
            self.log(f"")
            self.log(f"下一轮监控将在 {self.config.check_interval} 分钟后开始...")

            wait_start = time.time()
            while self.running and (time.time() - wait_start) < interval:
                time.sleep(1)

        self.log("监控已停止")


# ========== Playwright headless 补丁 ==========

def _patch_playwright_headless(config: AppConfig):
    """
    补丁：让PlaywrightMonitor支持headless配置

    原始代码中 headless 写死为 False，这里通过猴子补丁修改。
    """
    import playwright_monitor as pm

    original_run = pm.PlaywrightMonitor._run_parallel_async

    async def patched_run(self, shops, send_notification_callback=None):
        # 保存原始方法的引用
        return await original_run(self, shops, send_notification_callback)

    # 修补 launch_persistent_context 调用（通过包装 async with）
    original_init = pm.PlaywrightMonitor.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        # 确保 headless 属性可用
        if self.config and hasattr(self.config, 'headless'):
            self._headless = self.config.headless
        else:
            self._headless = True  # 服务端默认无头

    pm.PlaywrightMonitor.__init__ = patched_init


# ========== 入口 ==========

def main():
    parser = argparse.ArgumentParser(
        description='淘宝闪购智能助手 - 服务端监控',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 首次登录（需要显示器/VNC）
  python server_monitor.py --login

  # 无头模式持续监控
  python server_monitor.py --interval 30 --workers 5

  # 仅运行一次
  python server_monitor.py --once

  # 指定门店列表文件
  python server_monitor.py --shop-list doc/门店列表_v2.xlsx

  # 通过环境变量设置通知
  WECOM_WEBHOOK=https://... python server_monitor.py
  DINGTALK_WEBHOOK=https://... python server_monitor.py
  SERVERCHAN_KEY=xxx python server_monitor.py
        """
    )

    parser.add_argument('--login', action='store_true',
                        help='登录模式：以有头模式启动浏览器，完成首次登录')
    parser.add_argument('--once', action='store_true',
                        help='仅运行一次，不循环')
    parser.add_argument('--interval', type=int, default=None,
                        help='监控间隔（分钟），默认使用配置文件中的值')
    parser.add_argument('--workers', type=int, default=None,
                        help='并行页面数量，默认5')
    parser.add_argument('--chain-id', type=str, default=None,
                        help='连锁ID')
    parser.add_argument('--shop-id', type=str, default=None,
                        help='门店ID')
    parser.add_argument('--webhook', type=str, default=None,
                        help='企业微信Webhook地址')
    parser.add_argument('--shop-list', type=str, default=None,
                        help='门店列表文件路径（xlsx或json）')
    parser.add_argument('--config', type=str, default=None,
                        help='配置文件路径')

    args = parser.parse_args()

    # 如果指定了配置文件，先切换工作目录
    if args.config:
        config_dir = os.path.dirname(os.path.abspath(args.config))
        os.environ['TAOBAO_MONITOR_CONFIG'] = args.config

    # 应用headless补丁
    _patch_playwright_headless(AppConfig())

    # 启动监控
    monitor = ServerMonitor(args)
    monitor.run()


if __name__ == '__main__':
    main()
