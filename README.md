# 淘宝闪购商品监控工具

监控淘宝闪购商家后台（饿了么连锁商家后台）的商品状态，自动检测已下架和已售罄的商品，支持导出Excel报表和企业微信通知。

## ✨ 功能特点

- 🖥️ **Windows桌面应用** - 图形化界面，操作简单
- 🔐 **账号密码登录** - 支持保存账号密码，自动填充登录
- 💾 **登录态持久化** - 首次登录后自动保存，无需重复登录
- 📊 **商品状态监控** - 实时监控已下架、已售罄商品
- 📈 **Excel报表导出** - 一键导出监控结果
- 📢 **企业微信通知** - 发现问题商品自动推送告警
- ⏰ **定时监控** - 支持自定义间隔持续监控
- 🌐 **多浏览器支持** - 自动检测Edge/Chrome/Chromium

---

## 🚀 快速开始

### 方式一：下载预编译版本（推荐）

1. 从 `dist/` 目录下载最新的 `TaobaoFlashSaleMonitorVx.x.exe`
2. 双击运行即可，无需安装Python

### 方式二：从源码运行

```bash
# 1. 安装Python 3.8+
# 下载地址：https://www.python.org/downloads/

# 2. 安装依赖
pip install PyQt6 cryptography selenium openpyxl requests beautifulsoup4 lxml

# 3. 运行GUI应用
python gui_app.py

# 或双击 run_gui.bat（Windows）
```

---

## 🔨 编译打包

### Windows下编译

```batch
# 方法1：双击 build.bat

# 方法2：手动运行
pip install pyinstaller PyQt6 cryptography selenium openpyxl requests beautifulsoup4 lxml
python build_exe.py
```

### WSL/Linux下交叉编译Windows exe

```bash
# 在WSL中运行（会调用Windows的Python进行编译）
bash build_from_wsl.sh
```

### 版本号自动递增

每次编译会自动递增版本号：
- `TaobaoFlashSaleMonitorV1.1.exe`
- `TaobaoFlashSaleMonitorV1.2.exe`
- `TaobaoFlashSaleMonitorV1.3.exe`
- ...

版本号保存在 `version.json` 文件中。

### 编译输出

编译完成后，exe文件位于 `dist/` 目录：
```
dist/
└── TaobaoFlashSaleMonitorV1.x.exe  (约57MB)
```

---

## 📖 界面使用说明

应用界面分为左侧配置区和右侧控制区：

```
┌─────────────────────────────────────────────────────────────┐
│              🛒 淘宝闪购商品监控工具                          │
├─────────────────────────┬───────────────────────────────────┤
│  [🔐登录] [🏪店铺] [⚙️高级]│  [▶开始监控] [⏹停止] [💾保存配置]  │
│                         │                                   │
│  ┌─────────────────┐   │  ┌─────────────────────────────┐  │
│  │ 📱 淘宝账号登录   │   │  │ 📋 运行日志                  │  │
│  │                 │   │  │                             │  │
│  │ 账号: [______]  │   │  │ [xx:xx:xx] 正在初始化...     │  │
│  │ 密码: [______]  │   │  │ [xx:xx:xx] 找到浏览器...     │  │
│  │ ☐ 记住密码      │   │  │ [xx:xx:xx] 浏览器已启动      │  │
│  │ ☐ 自动填充      │   │  │                             │  │
│  │                 │   │  └─────────────────────────────┘  │
│  └─────────────────┘   │                                   │
│                         │  ┌─────────────────────────────┐  │
│                         │  │ 📊 监控结果                  │  │
│                         │  │ 已下架: 0  已售罄: 0  总计: 0│  │
│                         │  └─────────────────────────────┘  │
└─────────────────────────┴───────────────────────────────────┘
```

---

## ⚙️ 设置选项详解

### 🔐 登录标签页

| 选项 | 说明 |
|------|------|
| **账号** | 淘宝/饿了么商家账号（手机号） |
| **密码** | 登录密码 |
| **记住密码** | 勾选后密码会加密保存到本地，下次启动自动填入 |
| **自动填充** | 勾选后启动监控时自动填充账号密码到登录页面 |

> 💡 **提示**：首次登录需要在浏览器中完成验证码/滑块验证，登录成功后系统会保存登录状态，后续无需重复登录。

### 🏪 店铺标签页

| 选项 | 说明 | 示例 |
|------|------|------|
| **连锁ID** | 饿了么连锁商家后台的 chain_id | `99760038` |
| **门店ID** | 具体门店的 shop_id | `1303549223` |
| **门店名称** | 仅用于显示和报表，可随意填写 | `我的门店` |
| **Webhook** | 企业微信机器人的Webhook地址 | `https://qyapi.weixin.qq.com/...` |
| **启用通知** | 勾选后发现问题商品会推送到企业微信 | |

> 📝 **如何获取 chain_id 和 shop_id？**
> 
> 登录饿了么商家后台，查看URL：
> ```
> https://melody.shop.ele.me/app/chain/{chain_id}/shop#...
> ```

### ⚙️ 高级标签页

#### 🌐 浏览器设置

| 选项 | 说明 | 默认值 |
|------|------|--------|
| **调试端口** | 浏览器远程调试端口 | `9222` |
| **浏览器路径** | 指定浏览器可执行文件路径（留空自动检测） | 空 |
| **无头模式** | 勾选后浏览器在后台运行，不显示窗口 | 不勾选 |

**常见浏览器路径：**

| 浏览器 | Windows路径 |
|--------|-------------|
| **Microsoft Edge** | `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe` |
| **Google Chrome** | `C:\Program Files\Google\Chrome\Application\chrome.exe` |
| **Chromium** | `C:\Program Files\Chromium\Application\chrome.exe` |

> ⚠️ **如果浏览器无法启动**，请在此手动指定浏览器路径，点击「选择」按钮浏览选择exe文件。

#### ⏰ 监控设置

| 选项 | 说明 | 默认值 |
|------|------|--------|
| **检查间隔** | 持续监控模式下，每隔多久检查一次 | `30分钟` |
| **导出目录** | Excel报表保存位置 | `./exports` |

#### 🗑️ 缓存管理

| 按钮 | 说明 |
|------|------|
| **清除登录缓存** | 删除浏览器登录状态，下次需要重新登录 |

---

## 🎯 使用流程

### 首次使用

1. **运行应用**
   - 双击 `TaobaoFlashSaleMonitorVx.x.exe`

2. **配置店铺信息**（必须）
   - 点击「🏪 店铺」标签
   - 填写「连锁ID」和「门店ID」
   - 点击「💾 保存配置」

3. **配置账号**（可选）
   - 点击「🔐 登录」标签
   - 填写淘宝账号和密码
   - 勾选「记住密码」和「自动填充」
   - 点击「💾 保存配置」

4. **开始监控**
   - 点击「▶ 开始监控」
   - 浏览器会自动打开并跳转到登录页面
   - 首次需要手动完成验证（滑块/验证码）
   - 登录成功后自动开始抓取

### 日常使用

1. 运行应用
2. 直接点击「▶ 开始监控」
3. 系统会自动复用上次的登录状态

---

## ❓ 常见问题

### Q: 提示"无法启动浏览器"？

**解决方法：**
1. 确保已安装 Microsoft Edge（Windows自带）或 Google Chrome
2. 关闭所有浏览器窗口后重试
3. 在「高级设置」中手动指定浏览器路径：
   - Edge: `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`
   - Chrome: `C:\Program Files\Google\Chrome\Application\chrome.exe`

### Q: 提示"端口被占用"？

**解决方法：**
1. 在「高级设置」中将调试端口改为其他值（如 `9333`）
2. 或关闭占用9222端口的程序

### Q: 登录状态丢失？

**原因：** 浏览器profile被清除

**解决方法：**
- 不要手动删除配置目录
- 如需重新登录，点击「清除登录缓存」

### Q: 打包后运行报错？

**解决方法：**
1. 使用调试版本查看错误：
   ```bash
   python build_exe.py --debug
   ```
2. 运行生成的 `TaobaoFlashSaleMonitorVx.x_Debug.exe` 查看控制台输出

---

## 📁 项目结构

```
taobao_flashsale_monitor/
├── gui_app.py           # GUI桌面应用主程序
├── main.py              # 命令行版本主程序
├── selenium_fetcher.py  # Selenium浏览器自动化模块
├── config_manager.py    # 配置管理模块（加密存储）
├── version.py           # 版本管理模块
├── version.json         # 当前版本号
├── build_exe.py         # PyInstaller打包脚本
├── build_from_wsl.sh    # WSL交叉编译脚本
├── build.bat            # Windows一键打包
├── run_gui.bat          # Windows一键运行
├── requirements.txt     # Python依赖
├── dist/                # 编译产物目录
│   └── TaobaoFlashSaleMonitorVx.x.exe
└── README.md            # 说明文档
```

---

## 📦 数据存储位置

| 平台 | 配置目录 |
|------|----------|
| **Windows** | `%APPDATA%\TaobaoFlashSaleMonitor\` |
| **Linux/Mac** | `~/.taobao_flashsale_monitor/` |

目录内容：
- `config.json` - 配置文件（密码已加密）
- `chromium_profile/` - 浏览器登录态缓存

---

## 🛠️ 技术栈

- **Python 3.8+**
- **PyQt6** - GUI界面
- **Selenium** - 浏览器自动化
- **cryptography** - 密码加密存储
- **PyInstaller** - 打包为exe

---

## 📋 命令行模式

除了GUI应用，也支持命令行运行：

```bash
# 持续监控模式
python main.py

# 仅运行一次
python main.py --once

# 仅导出不发送通知
python main.py --export-only

# 指定检查间隔（分钟）
python main.py --interval 60

# 指定浏览器调试端口
python main.py --debug-port 9333

# 指定浏览器路径
python main.py --browser-path "C:\Program Files\Google\Chrome\Application\chrome.exe"

# 查看所有参数
python main.py --help
```

---

## ⚠️ 免责声明

本工具仅供学习和个人使用，请遵守淘宝/饿了么平台的相关规定。使用本工具造成的任何后果由使用者自行承担。

---

## 📄 License

MIT License
