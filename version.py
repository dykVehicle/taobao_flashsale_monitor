#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
版本管理模块
"""

import os
import json

VERSION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'version.json')

def get_version() -> str:
    """获取当前版本号"""
    if os.path.exists(VERSION_FILE):
        try:
            with open(VERSION_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('version', '1.0')
        except:
            pass
    return '1.0'

def increment_version() -> str:
    """增加版本号并返回新版本"""
    current = get_version()
    try:
        parts = current.split('.')
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        minor += 1
        new_version = f"{major}.{minor}"
    except:
        new_version = '1.1'
    
    # 保存新版本
    with open(VERSION_FILE, 'w', encoding='utf-8') as f:
        json.dump({'version': new_version}, f)
    
    return new_version

def set_version(version: str):
    """设置版本号"""
    with open(VERSION_FILE, 'w', encoding='utf-8') as f:
        json.dump({'version': version}, f)

if __name__ == '__main__':
    print(f"Current version: {get_version()}")
