# 淘宝闪购智能助手 - 服务端部署 Dockerfile
# 基于 Python 3.11 + Playwright Chromium

FROM python:3.11-slim

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    HEADLESS=true \
    TZ=Asia/Shanghai

# 设置时区
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 安装系统依赖（Playwright Chromium 所需）
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Playwright 依赖
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libwayland-client0 \
    # 中文字体支持
    fonts-wqy-zenhei \
    fonts-wqy-microhei \
    # 工具
    curl \
    && rm -rf /var/lib/apt/lists/*

# 创建工作目录
WORKDIR /app

# 先复制依赖文件，利用Docker缓存
COPY requirements-server.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements-server.txt

# 安装Playwright Chromium浏览器
RUN playwright install chromium \
    && playwright install-deps chromium

# 复制项目文件
COPY *.py ./
COPY doc/ ./doc/

# 创建数据目录（用于持久化配置和登录状态）
RUN mkdir -p /app/data /app/exports /app/playwright_profile

# 数据卷（持久化登录状态和配置）
VOLUME ["/app/data", "/app/playwright_profile"]

# 健康检查
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python -c "import os; exit(0 if os.path.exists('/app/monitor.log') else 1)"

# 默认命令：无头模式持续监控
ENTRYPOINT ["python", "server_monitor.py"]
CMD ["--interval", "30", "--workers", "5"]
