# ============================================================
# MemoMCP Memory Server Dockerfile
# ============================================================
FROM python:3.12-slim

# 系统依赖（asyncpg 需要的编译工具）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖（利用 Docker 层缓存，使用清华镜像加速）
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r requirements.txt

# 复制应用代码
COPY app/ ./app/

# 创建非 root 用户
RUN useradd -m -u 1000 memomcp && chown -R memomcp:memomcp /app
USER memomcp

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

EXPOSE 8000

# 默认启动 REST API（MCP stdio 模式由 client 直接调用 python -m app.main）
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
