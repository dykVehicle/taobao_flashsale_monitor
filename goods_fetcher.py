# -*- coding: utf-8 -*-
"""
淘宝闪购商品监控工具 - 商品数据抓取模块
支持两种模式:
1. API模式 - 直接调用接口获取数据（需要cookie）
2. Selenium模式 - 模拟浏览器抓取（需要登录）
"""

import json
import time
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from enum import Enum

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class GoodsStatus(Enum):
    """商品状态枚举"""
    ON_SALE = "在售"
    OFF_SALE = "已下架"
    SOLD_OUT = "已售罄"
    OUT_OF_STOCK = "缺货"
    PAUSE = "暂停售卖"
    UNKNOWN = "未知"


@dataclass
class GoodsItem:
    """商品信息数据类"""
    goods_id: str
    goods_name: str
    category: str
    price: float
    original_price: float
    stock: int
    status: GoodsStatus
    status_text: str
    image_url: str = ""
    sku_list: List[Dict] = None
    
    def __post_init__(self):
        if self.sku_list is None:
            self.sku_list = []
    
    def to_dict(self) -> Dict:
        result = asdict(self)
        result['status'] = self.status.value
        return result


class GoodsFetcher:
    """商品数据抓取器"""
    
    def __init__(self, shop_id: str, cookie: str, headers: Dict = None):
        """
        初始化抓取器
        
        Args:
            shop_id: 店铺ID
            cookie: 登录cookie
            headers: 请求头
        """
        self.shop_id = shop_id
        self.cookie = cookie
        self.session = requests.Session()
        
        # 设置默认请求头
        default_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Content-Type": "application/json",
            "Cookie": cookie,
        }
        if headers:
            default_headers.update(headers)
        self.session.headers.update(default_headers)
        
        # API endpoints
        self.base_url = "https://napos-goods-pc.faas.ele.me"
        self.goods_list_url = f"{self.base_url}/api/goods/list"
        self.goods_category_url = f"{self.base_url}/api/category/list"
    
    def fetch_goods_list(self, page: int = 1, page_size: int = 50, 
                         status_filter: str = None) -> Dict:
        """
        获取商品列表
        
        Args:
            page: 页码
            page_size: 每页数量
            status_filter: 状态过滤 (ON_SALE/OFF_SALE/SOLD_OUT等)
            
        Returns:
            包含商品列表和分页信息的字典
        """
        payload = {
            "shopId": self.shop_id,
            "pageNo": page,
            "pageSize": page_size,
        }
        
        if status_filter:
            payload["status"] = status_filter
        
        try:
            response = self.session.post(
                self.goods_list_url,
                json=payload,
                timeout=30
            )
            
            # 调试输出
            logger.info(f"请求URL: {self.goods_list_url}")
            logger.info(f"响应状态码: {response.status_code}")
            logger.info(f"响应内容前500字符: {response.text[:500]}")
            
            response.raise_for_status()
            data = response.json()
            
            if data.get("success") or data.get("code") == 200:
                return data.get("data", {})
            else:
                logger.error(f"API返回错误: {data.get('message', '未知错误')}")
                return {}
                
        except requests.RequestException as e:
            logger.error(f"请求商品列表失败: {e}")
            # 输出响应内容帮助调试
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"响应内容: {e.response.text[:500]}")
            return {}
    
    def fetch_all_goods(self) -> List[GoodsItem]:
        """
        获取所有商品（自动分页）
        
        Returns:
            商品列表
        """
        all_goods = []
        page = 1
        page_size = 50
        
        while True:
            logger.info(f"正在获取第{page}页商品...")
            result = self.fetch_goods_list(page=page, page_size=page_size)
            
            if not result:
                break
            
            goods_list = result.get("list", []) or result.get("items", [])
            if not goods_list:
                break
            
            for item in goods_list:
                goods = self._parse_goods_item(item)
                if goods:
                    all_goods.append(goods)
            
            # 检查是否还有下一页
            total = result.get("total", 0) or result.get("totalCount", 0)
            if page * page_size >= total:
                break
            
            page += 1
            time.sleep(0.5)  # 避免请求过快
        
        logger.info(f"共获取到 {len(all_goods)} 个商品")
        return all_goods
    
    def _parse_goods_item(self, item: Dict) -> Optional[GoodsItem]:
        """
        解析单个商品数据
        
        Args:
            item: 原始商品数据
            
        Returns:
            GoodsItem对象
        """
        try:
            # 解析状态
            status_str = item.get("status", "") or item.get("goodsStatus", "")
            status = self._parse_status(status_str)
            
            # 解析库存（可能在不同字段）
            stock = item.get("stock", 0) or item.get("inventory", 0) or item.get("totalStock", 0)
            
            # 如果库存为0，标记为售罄
            if stock == 0 and status == GoodsStatus.ON_SALE:
                status = GoodsStatus.SOLD_OUT
            
            return GoodsItem(
                goods_id=str(item.get("goodsId", "") or item.get("id", "")),
                goods_name=item.get("goodsName", "") or item.get("name", "") or item.get("title", ""),
                category=item.get("categoryName", "") or item.get("category", ""),
                price=float(item.get("price", 0) or item.get("sellPrice", 0)),
                original_price=float(item.get("originalPrice", 0) or item.get("marketPrice", 0)),
                stock=int(stock),
                status=status,
                status_text=item.get("statusText", status.value),
                image_url=item.get("imageUrl", "") or item.get("picUrl", "") or item.get("mainPic", ""),
                sku_list=item.get("skuList", []) or item.get("skus", [])
            )
        except Exception as e:
            logger.error(f"解析商品数据失败: {e}, 原始数据: {item}")
            return None
    
    def _parse_status(self, status_str: str) -> GoodsStatus:
        """解析商品状态字符串"""
        status_map = {
            "ON_SALE": GoodsStatus.ON_SALE,
            "在售": GoodsStatus.ON_SALE,
            "1": GoodsStatus.ON_SALE,
            
            "OFF_SALE": GoodsStatus.OFF_SALE,
            "已下架": GoodsStatus.OFF_SALE,
            "下架": GoodsStatus.OFF_SALE,
            "0": GoodsStatus.OFF_SALE,
            
            "SOLD_OUT": GoodsStatus.SOLD_OUT,
            "已售罄": GoodsStatus.SOLD_OUT,
            "售罄": GoodsStatus.SOLD_OUT,
            
            "OUT_OF_STOCK": GoodsStatus.OUT_OF_STOCK,
            "缺货": GoodsStatus.OUT_OF_STOCK,
            
            "PAUSE": GoodsStatus.PAUSE,
            "暂停售卖": GoodsStatus.PAUSE,
            "暂停": GoodsStatus.PAUSE,
        }
        return status_map.get(status_str, GoodsStatus.UNKNOWN)
    
    def get_problematic_goods(self, goods_list: List[GoodsItem] = None) -> Dict[str, List[GoodsItem]]:
        """
        获取问题商品（已下架/已售罄/缺货）
        
        Args:
            goods_list: 商品列表，如果为None则重新获取
            
        Returns:
            按状态分类的问题商品字典
        """
        if goods_list is None:
            goods_list = self.fetch_all_goods()
        
        result = {
            "已下架": [],
            "已售罄": [],
            "缺货": [],
            "暂停售卖": [],
        }
        
        for goods in goods_list:
            if goods.status == GoodsStatus.OFF_SALE:
                result["已下架"].append(goods)
            elif goods.status == GoodsStatus.SOLD_OUT:
                result["已售罄"].append(goods)
            elif goods.status == GoodsStatus.OUT_OF_STOCK:
                result["缺货"].append(goods)
            elif goods.status == GoodsStatus.PAUSE:
                result["暂停售卖"].append(goods)
        
        return result
    
    def get_statistics(self, goods_list: List[GoodsItem] = None) -> Dict:
        """
        获取商品统计信息
        
        Args:
            goods_list: 商品列表
            
        Returns:
            统计信息字典
        """
        if goods_list is None:
            goods_list = self.fetch_all_goods()
        
        stats = {
            "total": len(goods_list),
            "on_sale": 0,
            "off_sale": 0,
            "sold_out": 0,
            "out_of_stock": 0,
            "pause": 0,
            "unknown": 0,
        }
        
        for goods in goods_list:
            if goods.status == GoodsStatus.ON_SALE:
                stats["on_sale"] += 1
            elif goods.status == GoodsStatus.OFF_SALE:
                stats["off_sale"] += 1
            elif goods.status == GoodsStatus.SOLD_OUT:
                stats["sold_out"] += 1
            elif goods.status == GoodsStatus.OUT_OF_STOCK:
                stats["out_of_stock"] += 1
            elif goods.status == GoodsStatus.PAUSE:
                stats["pause"] += 1
            else:
                stats["unknown"] += 1
        
        return stats


class SeleniumGoodsFetcher:
    """
    使用Selenium抓取商品数据
    适用于API方式无法获取数据的情况
    """
    
    def __init__(self, shop_id: str, headless: bool = True):
        """
        初始化Selenium抓取器
        
        Args:
            shop_id: 店铺ID
            headless: 是否无头模式
        """
        self.shop_id = shop_id
        self.headless = headless
        self.driver = None
    
    def _init_driver(self):
        """初始化Chrome浏览器"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            
            options = Options()
            if self.headless:
                options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1920,1080")
            
            self.driver = webdriver.Chrome(options=options)
            self.driver.implicitly_wait(10)
            
        except ImportError:
            logger.error("请安装selenium: pip install selenium")
            raise
        except Exception as e:
            logger.error(f"初始化Chrome驱动失败: {e}")
            raise
    
    def login_and_fetch(self, wait_for_login: bool = True) -> List[GoodsItem]:
        """
        登录并抓取商品数据
        
        Args:
            wait_for_login: 是否等待用户手动登录
            
        Returns:
            商品列表
        """
        if not self.driver:
            self._init_driver()
        
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        try:
            # 打开商品管理页面
            goods_url = f"https://napos-goods-pc.faas.ele.me/single/goods-manage?shopId={self.shop_id}"
            self.driver.get(goods_url)
            
            if wait_for_login:
                logger.info("请在浏览器中完成登录，完成后按Enter继续...")
                input("按Enter继续...")
            
            # 等待页面加载
            time.sleep(3)
            
            # 解析页面数据
            goods_list = self._parse_page_data()
            
            return goods_list
            
        except Exception as e:
            logger.error(f"Selenium抓取失败: {e}")
            return []
        finally:
            if self.driver:
                self.driver.quit()
    
    def _parse_page_data(self) -> List[GoodsItem]:
        """解析页面中的商品数据"""
        goods_list = []
        
        try:
            # 尝试从页面的JavaScript变量或表格中提取数据
            # 这里需要根据实际页面结构调整
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # 查找商品表格行
            table_rows = soup.select('.ant-table-row, .goods-item, [class*="goodsItem"]')
            
            for row in table_rows:
                try:
                    goods = self._parse_row(row)
                    if goods:
                        goods_list.append(goods)
                except Exception as e:
                    logger.warning(f"解析商品行失败: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"解析页面数据失败: {e}")
        
        return goods_list
    
    def _parse_row(self, row) -> Optional[GoodsItem]:
        """解析单个商品行"""
        # 这里需要根据实际页面HTML结构调整选择器
        name_elem = row.select_one('[class*="name"], [class*="title"], .goods-name')
        status_elem = row.select_one('[class*="status"], .goods-status')
        price_elem = row.select_one('[class*="price"], .goods-price')
        
        if not name_elem:
            return None
        
        name = name_elem.get_text(strip=True)
        status_text = status_elem.get_text(strip=True) if status_elem else "未知"
        price_text = price_elem.get_text(strip=True) if price_elem else "0"
        
        # 解析价格
        try:
            price = float(''.join(c for c in price_text if c.isdigit() or c == '.'))
        except:
            price = 0.0
        
        # 解析状态
        status = self._text_to_status(status_text)
        
        return GoodsItem(
            goods_id="",
            goods_name=name,
            category="",
            price=price,
            original_price=price,
            stock=0,
            status=status,
            status_text=status_text
        )
    
    def _text_to_status(self, text: str) -> GoodsStatus:
        """文本转状态枚举"""
        if "下架" in text:
            return GoodsStatus.OFF_SALE
        elif "售罄" in text:
            return GoodsStatus.SOLD_OUT
        elif "缺货" in text:
            return GoodsStatus.OUT_OF_STOCK
        elif "暂停" in text:
            return GoodsStatus.PAUSE
        elif "在售" in text or "上架" in text:
            return GoodsStatus.ON_SALE
        return GoodsStatus.UNKNOWN

