#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build script - Package Taobao FlashSale Monitor to Windows exe
With automatic version incrementing
"""

import os
import sys
import subprocess
import shutil

# Fix Windows console encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def get_version():
    """Get current version from version.json"""
    import json
    version_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'version.json')
    if os.path.exists(version_file):
        try:
            with open(version_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('version', '1.0')
        except:
            pass
    return '1.0'

def increment_version():
    """Increment version and return new version"""
    import json
    version_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'version.json')
    current = get_version()
    try:
        parts = current.split('.')
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        minor += 1
        new_version = f"{major}.{minor}"
    except:
        new_version = '1.1'
    
    with open(version_file, 'w', encoding='utf-8') as f:
        json.dump({'version': new_version}, f)
    
    return new_version

def ensure_pyinstaller():
    """Ensure PyInstaller is installed"""
    try:
        import PyInstaller
        print(f"[OK] PyInstaller installed: {PyInstaller.__version__}")
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("[OK] PyInstaller installed")

def build():
    """Execute build with auto version increment"""
    ensure_pyinstaller()
    
    # Project directory
    project_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_dir)
    
    # Increment version
    version = increment_version()
    print(f"\n[VERSION] Building version: V{version}")
    
    # Output name with version
    output_name = f"TaobaoFlashSaleMonitorV{version}"
    
    # Clean old build files
    for folder in ['build']:
        path = os.path.join(project_dir, folder)
        if os.path.exists(path):
            print(f"Cleaning {folder}/ ...")
            shutil.rmtree(path)
    
    # Keep dist folder but clean old spec file
    spec_file = os.path.join(project_dir, f'{output_name}.spec')
    if os.path.exists(spec_file):
        os.remove(spec_file)
    
    print("\nStarting build...")
    print("=" * 50)
    
    # PyInstaller arguments
    args = [
        'gui_app.py',                           # Main program
        f'--name={output_name}',                # Output name with version
        '--onefile',                            # Single file mode
        '--windowed',                           # Windows GUI mode (no console)
        '--noconfirm',                          # No confirm overwrite
        # Add data files
        '--add-data=selenium_fetcher.py;.',
        '--add-data=config_manager.py;.',
        '--add-data=shop_manager.py;.',
        '--add-data=parallel_monitor.py;.',
        '--add-data=version.json;.',
        # Hidden imports
        '--hidden-import=version',
        '--hidden-import=shop_manager',
        '--hidden-import=parallel_monitor',
        '--hidden-import=pandas',
        '--hidden-import=selenium',
        '--hidden-import=selenium.webdriver',
        '--hidden-import=selenium.webdriver.chrome.options',
        '--hidden-import=selenium.webdriver.edge.options',
        '--hidden-import=selenium.webdriver.common.by',
        '--hidden-import=selenium.webdriver.support.ui',
        '--hidden-import=selenium.webdriver.support.expected_conditions',
        '--hidden-import=cryptography',
        '--hidden-import=PyQt6',
        '--hidden-import=PyQt6.QtCore',
        '--hidden-import=PyQt6.QtWidgets',
        '--hidden-import=PyQt6.QtGui',
        '--hidden-import=openpyxl',
        '--hidden-import=requests',
        '--hidden-import=bs4',
        '--hidden-import=lxml',
        # Exclude unused modules
        '--exclude-module=tkinter',
        '--exclude-module=matplotlib',
        '--exclude-module=numpy',
        # Note: pandas is required by shop_manager
        # Performance: use cache (no --clean), disable UPX compression
        '--noupx',
    ]
    
    # Add icon if exists
    icon_path = os.path.join(project_dir, 'icon.ico')
    if os.path.exists(icon_path):
        args.append(f'--icon={icon_path}')
    
    # Execute PyInstaller
    cmd = [sys.executable, '-m', 'PyInstaller'] + args
    print(f"Output: {output_name}.exe")
    print(f"Command: {' '.join(cmd[:5])}...\n")
    
    result = subprocess.run(cmd, cwd=project_dir)
    
    if result.returncode == 0:
        exe_path = os.path.join(project_dir, 'dist', f'{output_name}.exe')
        print("\n" + "=" * 50)
        print(f"[SUCCESS] Build completed! Version: V{version}")
        print(f"  Output: {exe_path}")
        print("\nUsage:")
        print(f"  1. Copy {output_name}.exe to any location")
        print("  2. Double-click to run")
        print("  3. Configure account and shop info on first run")
        print("  4. Login state will be saved automatically")
        return 0
    else:
        print("\n[FAILED] Build failed, check error messages above")
        return 1


def build_with_console():
    """Build debug version with console"""
    ensure_pyinstaller()
    
    project_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_dir)
    
    version = get_version()
    output_name = f"TaobaoFlashSaleMonitorV{version}_Debug"
    
    print(f"\nBuilding debug version V{version} (with console)...")
    
    args = [
        'gui_app.py',
        f'--name={output_name}',
        '--onefile',
        '--console',  # Show console
        '--noconfirm',
        '--add-data=selenium_fetcher.py;.',
        '--add-data=config_manager.py;.',
        '--add-data=shop_manager.py;.',
        '--add-data=parallel_monitor.py;.',
        '--add-data=version.json;.',
        '--hidden-import=version',
        '--hidden-import=shop_manager',
        '--hidden-import=parallel_monitor',
        '--hidden-import=selenium',
        '--hidden-import=selenium.webdriver',
        '--hidden-import=selenium.webdriver.edge.options',
        '--hidden-import=cryptography',
        '--hidden-import=PyQt6',
        '--hidden-import=openpyxl',
        '--hidden-import=pandas',
        '--hidden-import=requests',
        '--noupx',
    ]
    
    cmd = [sys.executable, '-m', 'PyInstaller'] + args
    subprocess.run(cmd, cwd=project_dir)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == '--debug':
        build_with_console()
    else:
        sys.exit(build())
