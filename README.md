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

## 🚀 快速开始

### 方式一：运行 Windows 桌面应用（推荐）

#### 使用预编译版本

1. 从 [Releases](./releases) 下载 `淘宝闪购监控工具.exe`
2. 双击运行即可

#### 从源码运行

```bash
# 1. 安装Python 3.8+（如果没有）
# 下载地址：https://www.python.org/downloads/

# 2. 双击 run_gui.bat 运行
# 或手动运行：
pip install PyQt6 cryptography selenium openpyxl requests beautifulsoup4 lxml
python gui_app.py
```

### 方式二：打包成独立 exe 文件

```bash
# Windows下双击 build.bat
# 或手动运行：
pip install pyinstaller PyQt6 cryptography selenium openpyxl requests beautifulsoup4 lxml
python build_exe.py

# 打包完成后在 dist/ 目录找到 淘宝闪购监控工具.exe
```

### 方式三：命令行模式

```bash
# 安装依赖
pip install -r requirements.txt

# 运行（持续模式）
python main.py

# 仅运行一次
python main.py --once

# 更多参数
python main.py --help
```

## 📖 使用说明

### 首次使用

1. **启动应用** - 运行 `淘宝闪购监控工具.exe` 或 `python gui_app.py`

2. **配置店铺信息**
   - 进入「店铺」标签页
   - 填写连锁ID（chain_id）和门店ID（shop_id）
   - 这些ID可以从饿了么商家后台URL中获取

3. **配置账号（可选）**
   - 进入「登录」标签页
   - 填写淘宝账号和密码
   - 勾选「记住密码」可加密保存
   - 勾选「自动填充」下次启动自动填入

4. **开始监控**
   - 点击「开始监控」
   - 首次运行会弹出浏览器窗口
   - 在浏览器中完成登录验证
   - 登录成功后自动开始抓取

### 登录方式

支持两种登录方式：

1. **自动填充模式**
   - 在应用中填写账号密码
   - 勾选「自动填充」
   - 程序会自动填入登录表单
   - 你只需完成验证码/滑块验证

2. **手动登录模式**
   - 不填写账号密码
   - 在弹出的浏览器中手动登录
   - 登录态会自动保存

### 配置说明

| 配置项 | 说明 |
|--------|------|
| 连锁ID | 饿了么连锁商家后台的 chain_id，从URL获取 |
| 门店ID | 具体门店的 shop_id |
| 检查间隔 | 持续模式下多久检查一次（分钟） |
| Webhook | 企业微信机器人地址，用于告警通知 |
| 调试端口 | 浏览器远程调试端口，默认9222 |

### 数据存储位置

- **Windows**: `%APPDATA%\TaobaoFlashSaleMonitor\`
- **Linux/Mac**: `~/.taobao_flashsale_monitor/`

包含：
- `config.json` - 配置文件（密码已加密）
- `chromium_profile/` - 浏览器登录态缓存

## 🔧 高级配置

### 命令行参数（main.py）

```
--once              仅运行一次后退出
--export-only       仅导出不发送通知
--interval N        检查间隔（分钟），默认30
--debug-port N      浏览器调试端口，默认9222
--profile-dir PATH  浏览器数据目录
--browser-path PATH 浏览器可执行文件路径
--dump-debug        保存调试截图
```

### 企业微信通知配置

1. 在企业微信群中添加机器人
2. 获取机器人Webhook地址
3. 在应用「店铺」配置中填入
4. 勾选「启用企业微信通知」

## ❓ 常见问题

### Q: 浏览器无法启动？

确保已安装以下浏览器之一：
- Google Chrome
- Chromium
- Microsoft Edge

或在「高级设置」中手动指定浏览器路径。

### Q: 登录状态丢失？

登录态保存在浏览器profile目录中：
- 不要删除 `chromium_profile` 目录
- 如需重新登录，点击「清除登录缓存」

### Q: 如何获取 chain_id 和 shop_id？

登录饿了么商家后台，URL格式如下：
```
https://melody.shop.ele.me/app/chain/{chain_id}/shop#...
```

### Q: 打包后运行报错？

1. 确保Python环境正确
2. 尝试运行调试版本：`python build_exe.py --debug`
3. 查看控制台错误信息

## 📁 项目结构

```
taobao_flashsale_monitor/
├── gui_app.py          # GUI桌面应用主程序
├── main.py             # 命令行版本主程序
├── selenium_fetcher.py # Selenium抓取模块
├── config_manager.py   # 配置管理模块
├── build_exe.py        # PyInstaller打包脚本
├── build.bat           # Windows一键打包
├── run_gui.bat         # Windows一键运行
├── requirements.txt    # Python依赖
└── README.md           # 说明文档
```

## 🛠️ 技术栈

- **Python 3.8+**
- **PyQt6** - GUI界面
- **Selenium** - 浏览器自动化
- **cryptography** - 密码加密存储
- **PyInstaller** - 打包为exe

## ⚠️ 免责声明

本工具仅供学习和个人使用，请遵守淘宝/饿了么平台的相关规定。使用本工具造成的任何后果由使用者自行承担。

## 📄 License

MIT License
