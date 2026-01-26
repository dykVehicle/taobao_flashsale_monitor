#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块 - 保存用户设置和账号信息
"""

import os
import json
import base64
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def get_config_dir() -> str:
    """获取配置目录（支持Windows/Linux/Mac）"""
    if os.name == 'nt':  # Windows
        config_dir = os.path.join(os.environ.get('APPDATA', ''), 'TaobaoFlashSaleMonitor')
    else:
        config_dir = os.path.expanduser('~/.taobao_flashsale_monitor')
    os.makedirs(config_dir, exist_ok=True)
    return config_dir


def get_key(password: str = "taobao_monitor_default_key") -> bytes:
    """根据密码生成加密密钥"""
    salt = b'taobao_flashsale_monitor_salt_v1'
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key


@dataclass
class AppConfig:
    """应用程序配置"""
    # 淘宝账号
    taobao_username: str = ""
    taobao_password: str = ""
    remember_password: bool = False
    auto_login: bool = False
    
    # 店铺配置
    chain_id: str = "99760038"
    shop_id: str = "1303549223"
    shop_name: str = "测试门店"
    base_url: str = "https://melody.shop.ele.me"
    
    # 通知配置
    wecom_webhook: str = ""
    enable_notification: bool = False
    
    # 监控设置
    check_interval: int = 30  # 分钟
    export_dir: str = "./exports"
    
    # 浏览器配置
    debug_port: int = 9222
    browser_path: str = ""
    headless: bool = False
    
    # 门店列表配置
    shop_list_file: str = "doc/门店列表_v2.xlsx"  # 当前门店列表文件
    shop_list_last_update: str = ""  # 上一次更新时间
    shop_list_history: str = ""  # 历史记录（JSON格式）
    
    # 并行监控配置
    parallel_workers: int = 20  # 并行worker数量，默认20个
    enable_parallel: bool = True  # 是否启用并行监控


class ConfigManager:
    """配置管理器"""
    
    def __init__(self):
        self.config_dir = get_config_dir()
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.key = get_key()
        self.fernet = Fernet(self.key)
        self.config = AppConfig()
        self.load()
    
    def _encrypt(self, text: str) -> str:
        """加密字符串"""
        if not text:
            return ""
        try:
            encrypted = self.fernet.encrypt(text.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
        except Exception:
            return ""
    
    def _decrypt(self, encrypted_text: str) -> str:
        """解密字符串"""
        if not encrypted_text:
            return ""
        try:
            encrypted = base64.urlsafe_b64decode(encrypted_text.encode())
            decrypted = self.fernet.decrypt(encrypted)
            return decrypted.decode()
        except Exception:
            return ""
    
    def load(self) -> AppConfig:
        """加载配置"""
        if not os.path.exists(self.config_file):
            return self.config
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 解密敏感字段
            if data.get('taobao_password'):
                data['taobao_password'] = self._decrypt(data['taobao_password'])
            if data.get('wecom_webhook'):
                data['wecom_webhook'] = self._decrypt(data['wecom_webhook'])
            
            # 更新配置
            for key, value in data.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)
            
        except Exception as e:
            print(f"加载配置失败: {e}")
        
        return self.config
    
    def save(self) -> bool:
        """保存配置"""
        try:
            data = asdict(self.config)
            
            # 加密敏感字段
            if self.config.remember_password and data.get('taobao_password'):
                data['taobao_password'] = self._encrypt(data['taobao_password'])
            else:
                data['taobao_password'] = ""
            
            if data.get('wecom_webhook'):
                data['wecom_webhook'] = self._encrypt(data['wecom_webhook'])
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            print(f"保存配置失败: {e}")
            return False
    
    def get_profile_dir(self) -> str:
        """获取浏览器profile目录"""
        profile_dir = os.path.join(self.config_dir, "chromium_profile")
        os.makedirs(profile_dir, exist_ok=True)
        return profile_dir
    
    def clear_login_cache(self) -> bool:
        """清除登录缓存"""
        import shutil
        profile_dir = self.get_profile_dir()
        try:
            if os.path.exists(profile_dir):
                shutil.rmtree(profile_dir)
                os.makedirs(profile_dir, exist_ok=True)
            return True
        except Exception as e:
            print(f"清除缓存失败: {e}")
            return False
