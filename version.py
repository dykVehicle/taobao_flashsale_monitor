#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
版本管理模块
"""

import os
import json
import sys

def get_base_path():
    """获取基础路径，兼容PyInstaller打包后的路径"""
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

VERSION_FILE = os.path.join(get_base_path(), 'version.json')

# 开发环境下的写入路径（打包后不应写入）
DEV_VERSION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'version.json')

def get_version() -> str:
    """获取当前版本号"""
    # 优先尝试读取 VERSION_FILE (打包后或开发环境)
    target_file = VERSION_FILE
    if not os.path.exists(target_file):
        target_file = DEV_VERSION_FILE
        
    if os.path.exists(target_file):
        try:
            with open(target_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('version', '1.0')
        except:
            pass
    return '1.0'

def increment_version() -> str:
    """增加版本号并返回新版本（仅在开发环境有效）"""
    current = get_version()
    try:
        parts = current.split('.')
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        minor += 1
        new_version = f"{major}.{minor}"
    except:
        new_version = '1.1'
    
    # 始终写入到开发目录的文件，而不是临时目录
    with open(DEV_VERSION_FILE, 'w', encoding='utf-8') as f:
        json.dump({'version': new_version}, f)
    
    return new_version

def set_version(version: str):
    """设置版本号（仅在开发环境有效）"""
    with open(DEV_VERSION_FILE, 'w', encoding='utf-8') as f:
        json.dump({'version': version}, f)

if __name__ == '__main__':
    print(f"Current version: {get_version()}")
