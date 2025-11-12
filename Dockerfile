# ==============================================================================
# Multi-stage Dockerfile for Amazon Q to Claude API Proxy
# ==============================================================================

# Stage 1: Build stage
FROM python:3.11-slim as builder

WORKDIR /app

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖到用户目录
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime stage
FROM python:3.11-slim

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/home/appuser/.local/bin:$PATH \
    PORT=8080

WORKDIR /app

# 创建非 root 用户
RUN useradd -m -u 1000 appuser

# 从 builder stage 复制安装的依赖
COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local

# 复制应用代码
COPY --chown=appuser:appuser *.py ./
COPY --chown=appuser:appuser *.md ./

# 创建缓存目录
RUN mkdir -p /home/appuser/.cache/amazonq && \
    chown -R appuser:appuser /home/appuser/.cache

# 切换到非 root 用户
USER appuser

# 暴露端口(默认 8080)
EXPOSE 8080

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health').read()" || exit 1

# 启动命令
CMD ["python3", "main.py"]