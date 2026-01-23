# -*- coding: utf-8 -*-
"""
淘宝闪购商品监控工具 - 配置文件
"""

# ===========================================
# 门店配置
# 每个门店包含: 门店名称、shopId、企业微信机器人webhook
# ===========================================
STORES = [
    {
        "name": "阿狗手打·手作(长宁龙之梦店)",
        "shop_id": "1303549223",
        "webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_WEBHOOK_KEY_1"
    },
    # 添加更多门店...
    # {
    #     "name": "门店名称2",
    #     "shop_id": "店铺ID2",
    #     "webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_WEBHOOK_KEY_2"
    # },
]

# ===========================================
# API配置 (从浏览器获取的cookie和token)
# ===========================================
API_CONFIG = {
    # 从浏览器开发者工具获取的Cookie
    "cookie": "cna=IcP4IRhE91cCATr3QnKyK90S; xlly_s=1; x5check_napos=YWRKMDMTA1MzQ5MTMwNzg4ODAxUUN5TWZjSTFQ; ksid=YWRKMDMTA1MzQ5MTMwNzg4ODAxUUN5TWZjSTFQ; _c_WBKFRo=VWuVJZtJThH68exHKXccIiBvoiWSYMcZIDNed80W; _nb_ioWEgULi=; menuType=SHOP; shopId=1303549223; AEM_TAG_ID_CATCH_DATA_ES00000044={%22tagId%22:%22ES00000044%22%2C%22data%22:%22%E7%94%9C%E7%82%B9%E9%A5%AE%E5%93%81%22%2C%22userId%22:1303549223%2C%22time%22:1769071767801}; AEM_TAG_ID_CATCH_DATA_ES00000069={%22tagId%22:%22ES00000069%22%2C%22data%22:%22%E8%80%81%E5%BA%97%22%2C%22userId%22:1303549223%2C%22time%22:1769071767801}; AEM_TAG_ID_CATCH_DATA_ES00000035={%22tagId%22:%22ES00000035%22%2C%22userId%22:1303549223%2C%22time%22:1769071767801}; AEM_TAG_ID_CATCH_DATA_ES00000021={%22tagId%22:%22ES00000021%22%2C%22data%22:%22%E5%8C%BA%E5%9F%9F%E8%BF%9E%E9%94%81%22%2C%22userId%22:1303549223%2C%22time%22:1769071767801}; AEM_TAG_ID_CATCH_DATA_ES00000019={%22tagId%22:%22ES00000019%22%2C%22data%22:%22%E4%B8%8A%E6%B5%B7%22%2C%22userId%22:1303549223%2C%22time%22:1769071767801}; o2o_ad_platform=napos; o2o_ad_loginId=1303549223; o2o_ad_ksid=YWRKMDMTA1MzQ5MTMwNzg4ODAxUUN5TWZjSTFQ; AEM_TAG_ID_CATCH_DATA={%22data%22:{%22ES00000019%22:%22%E4%B8%8A%E6%B5%B7%22%2C%22ES00000826%22:%22%E8%80%81%E5%BA%97%22%2C%22ES00000814%22:%22%E8%80%81%E5%BA%97-%E6%99%AE%E9%80%9A%22%2C%22ES00000044%22:%22%E7%94%9C%E7%82%B9%E9%A5%AE%E5%93%81%22%2C%22ES00000021%22:%22%E5%8C%BA%E5%9F%9F%E8%BF%9E%E9%94%81%22}%2C%22userId%22:1303549223%2C%22time%22:1769071774528}; isg=BLS04y2zYZXDcPVaKFllRJm-hXsmjdh3-PyAhU4Vkz_CuVYDdpyPBn2yOfFhQRDP; tfstk=gKfSV9al9Fx2qZncruUqcrDL3bOCAMNa92TdSwhrJQdROXscm6uPJ3uCAwxVUBzlJ6GBDMteYQKrRM_HmUhJ93hvkU8eJbd8-MsCjH4kYB7pv2sAJpBeaQulnG7ta_ykTXOktBEab5PNlaAH9uflqfxlkZYLuUFTCrA2tBEa0BO5o7dhVe7WI_QYle8HvvIpyqUXSeOKwph-HmKDJBdK9YnvMFTI9bKRvZUX-nKp9LLDCmTUFeQ77h6HI2DyYaKj9XCYtLt1yvlK9sTWF6QJcrzVGU9Wbp6vCFCC5wCyGOiLeNOc_p5A0WGDaN6vMe13WvtBCOCBZsFSjU6A5IKy6506D__CGLXq2zJf5FQGdBNmo3BG3gCvtVkDaO7NtdC8Ncx2IesXQTZsNGIz3f-6iWkIldcBlhzblvDnzwkBexVKnupJoUFalrijKLLDlEablmZWeEY8xraj4K1..",
    
    # 商品列表API地址
    "goods_list_api": "https://napos-goods-pc.faas.ele.me/api/goods/list",
    
    # 请求头配置
    "headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Content-Type": "application/json",
        "Origin": "https://napos-goods-pc.faas.ele.me",
        "Referer": "https://napos-goods-pc.faas.ele.me/single/goods-manage",
    }
}

# ===========================================
# 商品状态定义
# ===========================================
GOODS_STATUS = {
    "ON_SALE": "在售",
    "OFF_SALE": "已下架", 
    "SOLD_OUT": "已售罄",
    "OUT_OF_STOCK": "缺货",
    "PAUSE": "暂停售卖"
}

# ===========================================
# 导出配置
# ===========================================
EXPORT_CONFIG = {
    "output_dir": "./exports",
    "excel_filename_template": "{store_name}_{date}_商品状态报告.xlsx",
}

# ===========================================
# 定时任务配置
# ===========================================
SCHEDULE_CONFIG = {
    # 定时检查间隔（分钟）
    "check_interval_minutes": 30,
    
    # 每日报告时间（24小时制）
    "daily_report_times": ["09:00", "14:00", "20:00"],
    
    # 是否只在有问题商品时发送通知
    "notify_only_on_issues": True,
}

# ===========================================
# 日志配置
# ===========================================
LOG_CONFIG = {
    "log_file": "./logs/monitor.log",
    "log_level": "INFO",
    "max_bytes": 10 * 1024 * 1024,  # 10MB
    "backup_count": 5,
}

