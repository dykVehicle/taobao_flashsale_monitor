#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
店铺管理模块 - 管理多店铺配置
"""

import os
from dataclasses import dataclass
from typing import List, Optional
import json


@dataclass
class ShopInfo:
    """店铺信息"""
    name: str  # 店铺名称（用于搜索）
    webhook: str  # 企业微信webhook地址
    enabled: bool = True  # 是否启用监控


class ShopManager:
    """店铺管理器"""
    
    def __init__(self, config_path: str = None):
        """
        初始化店铺管理器
        
        Args:
            config_path: 配置文件路径，支持xlsx或json格式
        """
        self.shops: List[ShopInfo] = []
        self.config_path = config_path
        
        if config_path and os.path.exists(config_path):
            self.load(config_path)
    
    def load(self, config_path: str) -> bool:
        """加载店铺配置"""
        try:
            ext = os.path.splitext(config_path)[1].lower()
            
            if ext in ['.xlsx', '.xls']:
                return self._load_excel(config_path)
            elif ext == '.json':
                return self._load_json(config_path)
            else:
                print(f"不支持的配置文件格式: {ext}")
                return False
                
        except Exception as e:
            print(f"加载店铺配置失败: {e}")
            return False
    
    def _load_excel(self, path: str) -> bool:
        """从Excel加载店铺配置"""
        try:
            import pandas as pd
            df = pd.read_excel(path)
            
            # 兼容多种列名
            name_col = None
            webhook_col = None
            
            # 查找门店名称列（兼容"店铺名称"和"门店名称"）
            for col in ['店铺名称', '门店名称', '名称', 'name']:
                if col in df.columns:
                    name_col = col
                    break
            
            # 查找WebHook列（兼容大小写）
            for col in ['WebHook', 'webhook', 'Webhook', 'WEBHOOK']:
                if col in df.columns:
                    webhook_col = col
                    break
            
            if not name_col:
                print(f"Excel缺少必要列: 店铺名称/门店名称，当前列: {df.columns.tolist()}")
                return False
            if not webhook_col:
                print(f"Excel缺少必要列: WebHook，当前列: {df.columns.tolist()}")
                return False
            
            self.shops = []
            for _, row in df.iterrows():
                name = str(row[name_col]).strip()
                webhook = str(row[webhook_col]).strip()
                
                # 过滤空行和无效数据（nan、空字符串等）
                if not name or name.lower() == 'nan':
                    continue
                if not webhook or webhook.lower() == 'nan' or not webhook.startswith('http'):
                    continue
                
                enabled = True
                if '启用' in df.columns:
                    enabled = bool(row.get('启用', True))
                
                self.shops.append(ShopInfo(
                    name=name,
                    webhook=webhook,
                    enabled=enabled
                ))
            
            print(f"成功加载 {len(self.shops)} 个店铺配置")
            return True
            
        except ImportError:
            print("需要安装 pandas 和 openpyxl: pip install pandas openpyxl")
            return False
        except Exception as e:
            print(f"读取Excel失败: {e}")
            return False
    
    def _load_json(self, path: str) -> bool:
        """从JSON加载店铺配置"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.shops = []
            for item in data.get('shops', []):
                self.shops.append(ShopInfo(
                    name=item['name'],
                    webhook=item['webhook'],
                    enabled=item.get('enabled', True)
                ))
            
            return True
        except Exception as e:
            print(f"读取JSON失败: {e}")
            return False
    
    def save_json(self, path: str) -> bool:
        """保存到JSON文件"""
        try:
            data = {
                'shops': [
                    {
                        'name': shop.name,
                        'webhook': shop.webhook,
                        'enabled': shop.enabled
                    }
                    for shop in self.shops
                ]
            }
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存JSON失败: {e}")
            return False
    
    def get_enabled_shops(self) -> List[ShopInfo]:
        """获取启用的店铺列表"""
        return [shop for shop in self.shops if shop.enabled]
    
    def get_shop_by_name(self, name: str) -> Optional[ShopInfo]:
        """根据名称获取店铺"""
        for shop in self.shops:
            if shop.name == name:
                return shop
        return None
    
    def add_shop(self, name: str, webhook: str, enabled: bool = True):
        """添加店铺"""
        self.shops.append(ShopInfo(name=name, webhook=webhook, enabled=enabled))
    
    def remove_shop(self, name: str) -> bool:
        """移除店铺"""
        for i, shop in enumerate(self.shops):
            if shop.name == name:
                self.shops.pop(i)
                return True
        return False


# 测试代码
if __name__ == "__main__":
    manager = ShopManager("doc/店铺列表.xlsx")
    for shop in manager.shops:
        print(f"店铺: {shop.name}, Webhook: {shop.webhook[:50]}...")
