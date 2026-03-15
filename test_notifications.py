#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通知渠道自动测试脚本

用法:
    # 测试所有已配置渠道的连通性
    python test_notifications.py --test-channel

    # 测试指定渠道
    python test_notifications.py --test-channel pushplus
    python test_notifications.py --test-channel wecom-app
    python test_notifications.py --test-channel serverchan
    python test_notifications.py --test-channel wecom-webhook --webhook <URL>

    # 模拟异常门店数据推送（触发所有通知）
    python test_notifications.py --test-mock abnormal

    # 模拟正常门店数据推送
    python test_notifications.py --test-mock normal
"""

import os
import sys
import argparse
import json
from datetime import datetime
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server_monitor import (
    send_wecom_webhook,
    send_dingtalk_webhook,
    send_serverchan,
    send_pushplus,
    send_wecom_app_message,
    send_wechat_via_wcf,
)
from wechat_notifier import format_shop_message
from shop_manager import ShopInfo


@dataclass
class MockGoodsItem:
    goods_name: str
    status: str = ""
    goods_id: str = ""
    category: str = ""
    price: float = 0
    original_price: float = 0
    stock: int = 0
    status_text: str = ""


CHANNEL_NAMES = {
    "wecom-webhook": "企业微信 Webhook",
    "dingtalk": "钉钉 Webhook",
    "serverchan": "Server 酱",
    "pushplus": "PushPlus",
    "wecom-app": "企业微信应用消息",
    "wcf": "微信消息(WeChatFerry)",
}


def _make_test_message(channel_name: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"[测试] 淘宝闪购监控 - 通知渠道连通性测试\n"
        f"渠道: {channel_name}\n"
        f"时间: {now}\n"
        f"状态: 如果你收到这条消息，说明该通知渠道配置正确"
    )


def test_single_channel(channel: str, webhook_url: str = None) -> dict:
    """测试单个渠道，返回 {channel, status, detail}"""
    result = {"channel": channel, "name": CHANNEL_NAMES.get(channel, channel)}

    if channel == "wecom-webhook":
        url = webhook_url or os.environ.get("WECOM_WEBHOOK")
        if not url:
            return {**result, "status": "skipped", "detail": "未配置 WECOM_WEBHOOK 环境变量，也未通过 --webhook 指定"}
        msg = _make_test_message("企业微信 Webhook")
        ok = send_wecom_webhook(url, msg)
        return {**result, "status": "pass" if ok else "fail", "detail": "发送成功" if ok else "发送失败，请检查 Webhook URL"}

    elif channel == "dingtalk":
        url = os.environ.get("DINGTALK_WEBHOOK")
        if not url:
            return {**result, "status": "skipped", "detail": "未设置 DINGTALK_WEBHOOK"}
        msg = _make_test_message("钉钉 Webhook")
        ok = send_dingtalk_webhook(url, msg)
        return {**result, "status": "pass" if ok else "fail", "detail": "发送成功" if ok else "发送失败"}

    elif channel == "serverchan":
        key = os.environ.get("SERVERCHAN_KEY")
        if not key:
            return {**result, "status": "skipped", "detail": "未设置 SERVERCHAN_KEY"}
        msg = _make_test_message("Server 酱")
        ok = send_serverchan(key, "淘宝闪购监控-连通性测试", msg)
        return {**result, "status": "pass" if ok else "fail", "detail": "发送成功" if ok else "发送失败"}

    elif channel == "pushplus":
        token = os.environ.get("PUSHPLUS_TOKEN")
        if not token:
            return {**result, "status": "skipped", "detail": "未设置 PUSHPLUS_TOKEN"}
        msg = _make_test_message("PushPlus")
        ok = send_pushplus(token, "淘宝闪购监控-连通性测试", msg)
        return {**result, "status": "pass" if ok else "fail", "detail": "发送成功" if ok else "发送失败"}

    elif channel == "wecom-app":
        corpid = os.environ.get("WECOM_CORPID")
        corpsecret = os.environ.get("WECOM_CORPSECRET")
        agentid = os.environ.get("WECOM_AGENTID")
        touser = os.environ.get("WECOM_TOUSER", "@all")
        if not all([corpid, corpsecret, agentid]):
            missing = [k for k, v in {"WECOM_CORPID": corpid, "WECOM_CORPSECRET": corpsecret, "WECOM_AGENTID": agentid}.items() if not v]
            return {**result, "status": "skipped", "detail": f"未设置: {', '.join(missing)}"}
        msg = _make_test_message("企业微信应用消息")
        ok = send_wecom_app_message(corpid, corpsecret, agentid, touser, msg)
        return {**result, "status": "pass" if ok else "fail", "detail": "发送成功" if ok else "发送失败，请检查 corpid/corpsecret/agentid"}

    elif channel == "wcf":
        wcf_url = os.environ.get("WCF_URL")
        wcf_receivers = os.environ.get("WCF_RECEIVERS")
        if not wcf_url:
            return {**result, "status": "skipped", "detail": "未设置 WCF_URL (如 http://192.168.1.7:9999)"}
        if not wcf_receivers:
            return {**result, "status": "skipped", "detail": "未设置 WCF_RECEIVERS (微信ID或群ID)"}
        msg = _make_test_message("微信消息(WeChatFerry)")
        ok = send_wechat_via_wcf(wcf_url, wcf_receivers, msg)
        return {**result, "status": "pass" if ok else "fail", "detail": "发送成功" if ok else "发送失败，请检查 wcfhttp 服务是否启动"}

    else:
        return {**result, "status": "fail", "detail": f"未知渠道: {channel}"}


def test_all_channels(webhook_url: str = None) -> list:
    """测试所有渠道"""
    channels = ["wecom-webhook", "dingtalk", "serverchan", "pushplus", "wecom-app", "wcf"]
    return [test_single_channel(ch, webhook_url=webhook_url) for ch in channels]


def test_mock_notification(mode: str = "abnormal", webhook_url: str = None) -> list:
    """模拟门店监控结果推送"""
    mock_shop = ShopInfo(name="测试门店-自动验证", webhook=webhook_url or "", enabled=True)

    if mode == "abnormal":
        off_sale = [
            MockGoodsItem(goods_name="芋泥波波奶茶", status="OFF_SALE"),
            MockGoodsItem(goods_name="杨枝甘露", status="OFF_SALE"),
            MockGoodsItem(goods_name="椰椰芒芒", status="OFF_SALE"),
        ]
        sold_out = [
            MockGoodsItem(goods_name="黑糖珍珠鲜奶", status="SOLD_OUT"),
            MockGoodsItem(goods_name="手打柠檬茶", status="SOLD_OUT"),
        ]
    else:
        off_sale = []
        sold_out = []

    message = format_shop_message(
        shop_name=mock_shop.name,
        off_sale_goods=off_sale,
        sold_out_goods=sold_out,
        shop_status="营业中",
        duration=12.5,
    )

    has_abnormal = len(off_sale) > 0 or len(sold_out) > 0
    results = []

    # 企业微信 Webhook
    wh = mock_shop.webhook or os.environ.get("WECOM_WEBHOOK")
    if wh:
        ok = send_wecom_webhook(wh, message)
        results.append({"channel": "wecom-webhook", "name": "企业微信 Webhook", "status": "pass" if ok else "fail", "detail": ""})
    else:
        results.append({"channel": "wecom-webhook", "name": "企业微信 Webhook", "status": "skipped", "detail": "未配置"})

    # 钉钉
    dt = os.environ.get("DINGTALK_WEBHOOK")
    if dt:
        ok = send_dingtalk_webhook(dt, message)
        results.append({"channel": "dingtalk", "name": "钉钉 Webhook", "status": "pass" if ok else "fail", "detail": ""})
    else:
        results.append({"channel": "dingtalk", "name": "钉钉 Webhook", "status": "skipped", "detail": "未配置"})

    # Server 酱
    sc = os.environ.get("SERVERCHAN_KEY")
    if sc and has_abnormal:
        title = f"商品异常: {mock_shop.name}"
        ok = send_serverchan(sc, title, message)
        results.append({"channel": "serverchan", "name": "Server 酱", "status": "pass" if ok else "fail", "detail": ""})
    else:
        results.append({"channel": "serverchan", "name": "Server 酱", "status": "skipped", "detail": "未配置或无异常" if not sc else "正常状态不发送"})

    # PushPlus
    pp = os.environ.get("PUSHPLUS_TOKEN")
    if pp and (has_abnormal or mode == "normal"):
        title = f"商品异常: {mock_shop.name}" if has_abnormal else f"商品正常: {mock_shop.name}"
        ok = send_pushplus(pp, title, message)
        results.append({"channel": "pushplus", "name": "PushPlus", "status": "pass" if ok else "fail", "detail": ""})
    else:
        results.append({"channel": "pushplus", "name": "PushPlus", "status": "skipped", "detail": "未配置"})

    # 企业微信应用消息
    corpid = os.environ.get("WECOM_CORPID")
    corpsecret = os.environ.get("WECOM_CORPSECRET")
    agentid = os.environ.get("WECOM_AGENTID")
    touser = os.environ.get("WECOM_TOUSER", "@all")
    if all([corpid, corpsecret, agentid]) and (has_abnormal or mode == "normal"):
        ok = send_wecom_app_message(corpid, corpsecret, agentid, touser, message)
        results.append({"channel": "wecom-app", "name": "企业微信应用消息", "status": "pass" if ok else "fail", "detail": ""})
    else:
        results.append({"channel": "wecom-app", "name": "企业微信应用消息", "status": "skipped", "detail": "未配置"})

    # WeChatFerry 微信消息
    wcf_url = os.environ.get("WCF_URL")
    wcf_receivers = os.environ.get("WCF_RECEIVERS")
    if wcf_url and wcf_receivers and (has_abnormal or mode == "normal"):
        ok = send_wechat_via_wcf(wcf_url, wcf_receivers, message)
        results.append({"channel": "wcf", "name": "微信消息(WeChatFerry)", "status": "pass" if ok else "fail", "detail": ""})
    else:
        results.append({"channel": "wcf", "name": "微信消息(WeChatFerry)", "status": "skipped", "detail": "未配置 WCF_URL 或 WCF_RECEIVERS"})

    return results


def print_test_report(results: list, title: str = "通知渠道测试报告"):
    """打印结构化测试报告"""
    print()
    print("=" * 50)
    print(f" {title}")
    print("=" * 50)

    pass_count = 0
    fail_count = 0
    skip_count = 0

    for r in results:
        name = r["name"]
        status = r["status"]
        detail = r.get("detail", "")

        if status == "pass":
            tag = "成功"
            pass_count += 1
        elif status == "fail":
            tag = "失败"
            fail_count += 1
        else:
            tag = "跳过"
            skip_count += 1

        detail_str = f"  ({detail})" if detail else ""
        print(f" {name:16s} : {tag}{detail_str}")

    print("=" * 50)
    total_tested = pass_count + fail_count
    if total_tested > 0:
        print(f" 通过: {pass_count}/{total_tested}  跳过: {skip_count}  失败: {fail_count}")
    else:
        print(f" 所有渠道均未配置（跳过: {skip_count}）")
        print(" 请设置相应环境变量后重新测试")
    print("=" * 50)
    print()

    return fail_count == 0


def main():
    parser = argparse.ArgumentParser(
        description="淘宝闪购监控 - 通知渠道测试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--test-channel",
        nargs="?",
        const="all",
        metavar="CHANNEL",
        help="测试通知渠道连通性。不指定渠道名则测试全部。可选: wecom-webhook, dingtalk, serverchan, pushplus, wecom-app",
    )
    parser.add_argument(
        "--test-mock",
        choices=["abnormal", "normal"],
        help="模拟门店监控结果推送测试。abnormal=有异常商品, normal=无异常",
    )
    parser.add_argument(
        "--webhook",
        type=str,
        default=None,
        help="企业微信 Webhook URL（用于 wecom-webhook 渠道测试）",
    )

    args = parser.parse_args()

    if not args.test_channel and not args.test_mock:
        parser.print_help()
        sys.exit(0)

    all_pass = True

    if args.test_channel:
        if args.test_channel == "all":
            results = test_all_channels(webhook_url=args.webhook)
            ok = print_test_report(results, "通知渠道连通性测试")
        else:
            results = [test_single_channel(args.test_channel, webhook_url=args.webhook)]
            ok = print_test_report(results, f"渠道测试: {args.test_channel}")
        all_pass = all_pass and ok

    if args.test_mock:
        print(f"模拟门店监控结果: {'异常（有下架/售罄商品）' if args.test_mock == 'abnormal' else '正常（无异常商品）'}")
        results = test_mock_notification(args.test_mock, webhook_url=args.webhook)
        ok = print_test_report(results, f"模拟推送测试 ({args.test_mock})")
        all_pass = all_pass and ok

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
