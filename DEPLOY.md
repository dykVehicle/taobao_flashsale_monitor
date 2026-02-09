# 云服务器部署指南

本文档介绍如何将「淘宝闪购智能助手」部署到云服务器上，实现 7x24 小时自动监控。

---

## 服务器要求

| 项目 | 最低要求 | 推荐配置 |
|------|---------|---------|
| CPU | 1 核 | 2 核 |
| 内存 | 1 GB | 2~4 GB |
| 硬盘 | 2 GB 可用 | 5 GB |
| 系统 | Ubuntu 20.04+ / Debian 11+ | Ubuntu 22.04 |
| 网络 | 能访问淘宝/饿了么 | 国内服务器 |

**推荐云服务器**：阿里云轻量应用服务器 2核4G / 腾讯云轻量 2核2G

---

## 部署方式

提供两种部署方式，推荐使用 Docker 部署（更简单）。

- [方式一：Docker 部署](#方式一docker-部署推荐)（推荐）
- [方式二：直接部署](#方式二直接部署)

---

## 方式一：Docker 部署（推荐）

### 1. 安装 Docker

```bash
# Ubuntu/Debian 一键安装
curl -fsSL https://get.docker.com | sh

# 启动Docker服务
sudo systemctl enable docker
sudo systemctl start docker

# 安装Docker Compose（如果未自带）
sudo apt-get install -y docker-compose-plugin
```

### 2. 上传项目文件

将项目文件上传到服务器：

```bash
# 方法1：通过git克隆
git clone <your-repo-url> /opt/taobao-monitor
cd /opt/taobao-monitor

# 方法2：通过scp上传
scp -r taobao_flashsale_monitor/ user@your-server:/opt/taobao-monitor
ssh user@your-server
cd /opt/taobao-monitor
```

### 3. 配置通知

编辑 `docker-compose.yml`，配置通知方式：

```yaml
environment:
  - HEADLESS=true
  # 企业微信机器人（推荐）
  - WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY
  # 钉钉机器人（可选）
  - DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN
  # Server酱（可选，推送到微信）
  - SERVERCHAN_KEY=YOUR_SENDKEY
```

### 4. 首次登录

首次使用需要在浏览器中完成淘宝登录（验证码/滑块验证）：

```bash
# 方法A：临时使用 VNC（推荐）
# 先在服务器上安装 VNC
sudo apt-get install -y tigervnc-standalone-server
vncserver :1 -geometry 1280x800 -depth 24
export DISPLAY=:1

# 然后运行登录模式
docker compose run --rm monitor --login
```

```bash
# 方法B：在本地登录后复制 profile
# 1. 在本地 Windows 上正常登录程序
# 2. 找到登录数据目录 playwright_profile/
# 3. 将整个 playwright_profile/ 目录上传到服务器
scp -r playwright_profile/ user@server:/opt/taobao-monitor/
# 4. 挂载到 Docker 容器中（修改 docker-compose.yml）
# volumes:
#   - ./playwright_profile:/app/playwright_profile
```

### 5. 启动监控

```bash
# 构建镜像
docker compose build

# 启动服务（后台运行）
docker compose up -d

# 查看实时日志
docker compose logs -f

# 查看运行状态
docker compose ps
```

### 6. 管理命令

```bash
# 停止监控
docker compose down

# 重启
docker compose restart

# 仅运行一次（测试）
docker compose run --rm monitor --once

# 自定义参数
docker compose run --rm monitor --interval 60 --workers 3

# 进入容器调试
docker compose exec monitor bash

# 清除登录缓存（需要重新登录）
docker compose run --rm monitor bash -c "rm -rf /app/playwright_profile/*"
```

---

## 方式二：直接部署

### 1. 安装 Python 3.11+

```bash
# Ubuntu 22.04 自带 Python 3.10，建议安装 3.11
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip

# 或使用系统默认 Python（3.8+即可）
sudo apt install -y python3 python3-venv python3-pip
```

### 2. 创建项目目录和虚拟环境

```bash
# 创建项目目录
sudo mkdir -p /opt/taobao-monitor
sudo chown $USER:$USER /opt/taobao-monitor

# 上传项目文件后
cd /opt/taobao-monitor

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements-server.txt

# 安装Playwright浏览器
playwright install chromium
playwright install-deps chromium
```

### 3. 配置

```bash
# 编辑配置（首次运行会自动创建）
# 配置文件位置: ~/.taobao_flashsale_monitor/config.json

# 或通过环境变量配置通知
export WECOM_WEBHOOK="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY"
export HEADLESS=true
```

### 4. 首次登录

```bash
# 需要 X11 转发或 VNC
# 方法A：SSH X11 转发（需要本地有X Server）
ssh -X user@server
cd /opt/taobao-monitor
source venv/bin/activate
python server_monitor.py --login

# 方法B：复制本地登录数据（见 Docker 部署的方法B）
```

### 5. 启动监控

```bash
cd /opt/taobao-monitor
source venv/bin/activate

# 前台运行（测试）
python server_monitor.py --once

# 后台运行
nohup python server_monitor.py --interval 30 --workers 5 > /dev/null 2>&1 &

# 或使用 systemd 服务（推荐）
```

### 6. 配置 systemd 服务（推荐）

创建服务文件：

```bash
sudo tee /etc/systemd/system/taobao-monitor.service << 'EOF'
[Unit]
Description=Taobao FlashSale Monitor
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/taobao-monitor
Environment=HEADLESS=true
Environment=WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY
# 如需钉钉通知，取消注释下一行
# Environment=DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN
ExecStart=/opt/taobao-monitor/venv/bin/python server_monitor.py --interval 30 --workers 5
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
EOF
```

启动服务：

```bash
# 加载配置
sudo systemctl daemon-reload

# 启动
sudo systemctl start taobao-monitor

# 开机自启
sudo systemctl enable taobao-monitor

# 查看状态
sudo systemctl status taobao-monitor

# 查看日志
sudo journalctl -u taobao-monitor -f

# 重启
sudo systemctl restart taobao-monitor

# 停止
sudo systemctl stop taobao-monitor
```

---

## 通知配置详解

服务端部署后，Windows 微信自动化（wxauto）不可用，需要使用以下替代方案：

### 企业微信机器人（推荐）

1. 在企业微信群聊中，添加「群机器人」
2. 复制 Webhook 地址
3. 设置环境变量 `WECOM_WEBHOOK`

### 钉钉机器人

1. 在钉钉群聊中，添加「自定义机器人」
2. 安全设置选择「自定义关键词」，填入：`商品`、`监控`、`下架`、`售罄`
3. 复制 Webhook 地址
4. 设置环境变量 `DINGTALK_WEBHOOK`

### Server酱（推送到微信）

1. 访问 [https://sct.ftqq.com/](https://sct.ftqq.com/)
2. 用微信扫码登录
3. 获取 SendKey
4. 设置环境变量 `SERVERCHAN_KEY`

### Bark（推送到iPhone）

如需 Bark 推送，可以在 `server_monitor.py` 中添加：

```python
def send_bark(bark_url: str, title: str, message: str) -> bool:
    resp = requests.get(f"{bark_url}/{title}/{message}")
    return resp.status_code == 200
```

---

## 命令行参数

```
python server_monitor.py [选项]

选项:
  --login           登录模式（有头浏览器，完成首次登录）
  --once            仅运行一次
  --interval N      监控间隔，单位：分钟（默认30）
  --workers N       并行页面数量（默认5）
  --chain-id ID     连锁ID
  --shop-id ID      门店ID
  --webhook URL     企业微信Webhook地址
  --shop-list FILE  门店列表文件路径（xlsx/json）

环境变量:
  HEADLESS          无头模式（true/false，默认true）
  WECOM_WEBHOOK     企业微信Webhook
  DINGTALK_WEBHOOK  钉钉Webhook
  SERVERCHAN_KEY    Server酱SendKey
```

---

## 常见问题

### Q: 登录状态过期怎么办？

登录状态通常有效数天到数周。过期后需要重新登录：

```bash
# Docker部署
docker compose run --rm monitor --login

# 直接部署
python server_monitor.py --login
```

### Q: Playwright 浏览器安装失败？

```bash
# 手动安装系统依赖
sudo apt-get install -y libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
  libcups2 libdrm2 libdbus-1-3 libxkbcommon0 libatspi2.0-0 \
  libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
  libpango-1.0-0 libcairo2 libasound2

# 重新安装浏览器
playwright install chromium
playwright install-deps chromium
```

### Q: 内存不足怎么办？

1. 减少并行页面数量：`--workers 2`
2. 服务器至少需要 1GB 可用内存
3. 创建 swap 分区：

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Q: 如何查看监控日志？

```bash
# Docker
docker compose logs -f

# systemd
sudo journalctl -u taobao-monitor -f

# 直接查看日志文件
tail -f /opt/taobao-monitor/monitor.log
```

### Q: 如何在阿里云轻量服务器上快速部署？

```bash
# 1. 购买阿里云轻量应用服务器（Ubuntu 22.04, 2核4G）
# 2. SSH连接后执行以下命令：

# 安装 Docker
curl -fsSL https://get.docker.com | sh

# 上传项目
cd /opt && git clone <repo-url> taobao-monitor && cd taobao-monitor

# 配置通知（编辑docker-compose.yml中的环境变量）
vi docker-compose.yml

# 构建并启动
docker compose build && docker compose up -d

# 查看日志
docker compose logs -f
```

---

## 项目文件说明

```
taobao_flashsale_monitor/
├── server_monitor.py        # 服务端无头运行入口 ← 新增
├── requirements-server.txt  # 服务端依赖（无GUI） ← 新增
├── Dockerfile               # Docker构建文件     ← 新增
├── docker-compose.yml       # Docker编排配置     ← 新增
├── DEPLOY.md                # 本部署指南         ← 新增
├── playwright_monitor.py    # Playwright监控核心
├── config_manager.py        # 配置管理
├── shop_manager.py          # 门店管理
├── wechat_notifier.py       # 通知格式化
├── selenium_fetcher.py      # Selenium模块（服务端可选）
├── gui_app.py               # GUI应用（服务端不需要）
└── doc/
    └── 门店列表_v2.xlsx      # 门店配置
```
