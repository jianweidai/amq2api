# Docker 镜像构建与发布指南

本指南介绍如何构建 Docker 镜像并发布到镜像仓库,以便在其他 VPS 上快速部署。

## 快速开始 (3 步完成)

### 方式一: Docker Hub (推荐,免费)

```bash
# 1. 登录 Docker Hub
docker login

# 2. 构建并推送镜像(替换 yourusername 为你的用户名)
docker build -t yourusername/amq2api:latest .
docker push yourusername/amq2api:latest

# 3. 在其他 VPS 上使用
docker pull yourusername/amq2api:latest
docker run -d -p 8080:8080 --env-file .env yourusername/amq2api:latest
```

### 方式二: 导出镜像文件(适合内网)

```bash
# 1. 构建并导出
docker build -t amq2api:latest .
docker save amq2api:latest | gzip > amq2api.tar.gz

# 2. 传输到 VPS
scp amq2api.tar.gz user@your-vps:/tmp/

# 3. 在 VPS 上导入
ssh user@your-vps
docker load < /tmp/amq2api.tar.gz
docker run -d -p 8080:8080 --env-file .env amq2api:latest
```

---

## 详细步骤

### 一、发布到 Docker Hub

#### 1.1 注册 Docker Hub 账号

访问 https://hub.docker.com 注册免费账号

#### 1.2 登录

```bash
docker login
# 输入用户名和密码
```

#### 1.3 构建镜像

```bash
# 替换 yourusername 为你的 Docker Hub 用户名
docker build -t yourusername/amq2api:latest .

# 可以同时打多个标签
docker build -t yourusername/amq2api:latest \
             -t yourusername/amq2api:v1.0 .
```

#### 1.4 推送镜像

```bash
# 推送最新版本
docker push yourusername/amq2api:latest

# 推送特定版本
docker push yourusername/amq2api:v1.0
```

#### 1.5 验证

访问 https://hub.docker.com/r/yourusername/amq2api 查看镜像

---

### 二、在 VPS 上部署

#### 2.1 安装 Docker

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# 重新登录以应用组权限
exit
```

#### 2.2 创建部署目录

```bash
mkdir -p ~/amq2api
cd ~/amq2api
```

#### 2.3 创建配置文件

```bash
cat > .env << 'EOF'
# 服务配置
PORT=8080

# 多账号数量
AMAZONQ_ACCOUNT_COUNT=3

# 账号 1
AMAZONQ_ACCOUNT_1_ID=primary
AMAZONQ_ACCOUNT_1_REFRESH_TOKEN=你的token
AMAZONQ_ACCOUNT_1_CLIENT_ID=你的client_id
AMAZONQ_ACCOUNT_1_CLIENT_SECRET=你的secret
AMAZONQ_ACCOUNT_1_WEIGHT=10
AMAZONQ_ACCOUNT_1_ENABLED=true

# 账号 2
AMAZONQ_ACCOUNT_2_ID=backup
AMAZONQ_ACCOUNT_2_REFRESH_TOKEN=你的token
AMAZONQ_ACCOUNT_2_CLIENT_ID=你的client_id
AMAZONQ_ACCOUNT_2_CLIENT_SECRET=你的secret
AMAZONQ_ACCOUNT_2_WEIGHT=5
AMAZONQ_ACCOUNT_2_ENABLED=true

# 账号 3
AMAZONQ_ACCOUNT_3_ID=fallback
AMAZONQ_ACCOUNT_3_REFRESH_TOKEN=你的token
AMAZONQ_ACCOUNT_3_CLIENT_ID=你的client_id
AMAZONQ_ACCOUNT_3_CLIENT_SECRET=你的secret
AMAZONQ_ACCOUNT_3_WEIGHT=3
AMAZONQ_ACCOUNT_3_ENABLED=true

# 负载均衡
LOAD_BALANCE_STRATEGY=weighted_round_robin

# 熔断器
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_ERROR_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=300
EOF

# 编辑配置文件
vim .env
```

#### 2.4 创建 docker-compose.yml

```bash
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  amq2api:
    image: yourusername/amq2api:latest  # 替换为你的镜像名
    container_name: amq2api
    ports:
      - "8080:8080"
    env_file:
      - .env
    volumes:
      - token_cache:/home/appuser/.cache/amazonq
      - ./logs:/app/logs
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

volumes:
  token_cache:
EOF
```

#### 2.5 启动服务

```bash
# 拉取镜像并启动
docker compose up -d

# 查看日志
docker compose logs -f

# 验证服务
curl http://localhost:8080/health
curl http://localhost:8080/admin/accounts
```

---

## 一键部署脚本

创建 `quick-deploy.sh`:

```bash
#!/bin/bash

# 配置
IMAGE_NAME="yourusername/amq2api:latest"  # 替换为你的镜像名
PORT=8080

echo "=================================="
echo "Amazon Q API Proxy 快速部署"
echo "=================================="

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "安装 Docker..."
    curl -fsSL https://get.docker.com | sh
fi

# 检查 .env
if [ ! -f .env ]; then
    echo "请先创建 .env 配置文件"
    exit 1
fi

# 拉取镜像
echo "拉取镜像..."
docker pull $IMAGE_NAME

# 停止旧容器
docker stop amq2api 2>/dev/null || true
docker rm amq2api 2>/dev/null || true

# 启动新容器
echo "启动服务..."
docker run -d \
  --name amq2api \
  -p $PORT:8080 \
  --env-file .env \
  -v amq2api-cache:/home/appuser/.cache/amazonq \
  -v $(pwd)/logs:/app/logs \
  --restart unless-stopped \
  $IMAGE_NAME

# 等待启动
sleep 5

# 验证
if curl -f -s http://localhost:$PORT/health > /dev/null; then
    echo "✅ 部署成功!"
    echo "访问: http://localhost:$PORT/health"
else
    echo "❌ 部署失败,查看日志:"
    docker logs amq2api
    exit 1
fi
```

使用脚本:

```bash
chmod +x quick-deploy.sh
./quick-deploy.sh
```

---

## 镜像导出/导入(离线部署)

### 导出镜像

```bash
# 构建镜像
docker build -t amq2api:latest .

# 导出为压缩文件
docker save amq2api:latest | gzip > amq2api.tar.gz

# 查看文件大小
ls -lh amq2api.tar.gz
```

### 传输到 VPS

```bash
# 方式 1: scp
scp amq2api.tar.gz user@your-vps:/tmp/

# 方式 2: rsync
rsync -avz --progress amq2api.tar.gz user@your-vps:/tmp/

# 方式 3: 使用 U 盘等物理介质
```

### 在 VPS 上导入

```bash
# 登录 VPS
ssh user@your-vps

# 导入镜像
docker load < /tmp/amq2api.tar.gz

# 或解压后导入
gunzip /tmp/amq2api.tar.gz
docker load -i /tmp/amq2api.tar

# 验证镜像
docker images | grep amq2api
```

---

## 私有镜像仓库

### 使用阿里云容器镜像服务

```bash
# 1. 登录阿里云容器镜像服务
docker login --username=你的阿里云账号 registry.cn-hangzhou.aliyuncs.com

# 2. 构建镜像
docker build -t registry.cn-hangzhou.aliyuncs.com/你的命名空间/amq2api:latest .

# 3. 推送镜像
docker push registry.cn-hangzhou.aliyuncs.com/你的命名空间/amq2api:latest

# 4. 在 VPS 上拉取
docker pull registry.cn-hangzhou.aliyuncs.com/你的命名空间/amq2api:latest
```

### 使用腾讯云容器镜像服务

```bash
# 登录
docker login --username=你的腾讯云账号 ccr.ccs.tencentyun.com

# 构建和推送
docker build -t ccr.ccs.tencentyun.com/你的命名空间/amq2api:latest .
docker push ccr.ccs.tencentyun.com/你的命名空间/amq2api:latest
```

---

## 自动化构建 (GitHub Actions)

创建 `.github/workflows/docker.yml`:

```yaml
name: Build Docker Image

on:
  push:
    branches: [ main ]
    tags: [ 'v*' ]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4

    - name: Log in to Docker Hub
      uses: docker/login-action@v3
      with:
        username: ${{ secrets.DOCKER_USERNAME }}
        password: ${{ secrets.DOCKER_PASSWORD }}

    - name: Build and push
      uses: docker/build-push-action@v5
      with:
        context: .
        push: true
        tags: ${{ secrets.DOCKER_USERNAME }}/amq2api:latest
```

配置 GitHub Secrets:
1. 进入仓库 Settings → Secrets → Actions
2. 添加 `DOCKER_USERNAME` 和 `DOCKER_PASSWORD`

---

## 常用命令

### 镜像管理

```bash
# 查看本地镜像
docker images

# 删除镜像
docker rmi amq2api:latest

# 清理未使用的镜像
docker image prune -a

# 给镜像打标签
docker tag amq2api:latest yourusername/amq2api:v1.0
```

### 容器管理

```bash
# 查看运行中的容器
docker ps

# 查看所有容器
docker ps -a

# 查看日志
docker logs -f amq2api

# 进入容器
docker exec -it amq2api bash

# 停止容器
docker stop amq2api

# 删除容器
docker rm amq2api
```

### 更新部署

```bash
# 拉取最新镜像
docker pull yourusername/amq2api:latest

# 重启服务
docker compose down
docker compose up -d

# 或使用一键更新
docker compose pull && docker compose up -d --force-recreate
```

---

## 版本管理

### 推荐的标签策略

```bash
# latest: 最新稳定版
yourusername/amq2api:latest

# 版本号: 特定版本
yourusername/amq2api:v1.0.0
yourusername/amq2api:v1.0
yourusername/amq2api:v1

# 分支版本
yourusername/amq2api:dev
yourusername/amq2api:beta
```

### 发布新版本

```bash
# 构建并推送多个标签
docker build -t yourusername/amq2api:latest \
             -t yourusername/amq2api:v1.0.0 \
             -t yourusername/amq2api:v1.0 \
             -t yourusername/amq2api:v1 .

docker push yourusername/amq2api:latest
docker push yourusername/amq2api:v1.0.0
docker push yourusername/amq2api:v1.0
docker push yourusername/amq2api:v1
```

---

## 故障排查

### 镜像拉取失败

```bash
# 检查网络连接
docker pull hello-world

# 配置镜像加速器(阿里云)
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<-'EOF'
{
  "registry-mirrors": ["https://你的加速器地址.mirror.aliyuncs.com"]
}
EOF
sudo systemctl daemon-reload
sudo systemctl restart docker
```

### 容器无法启动

```bash
# 查看详细日志
docker logs amq2api

# 检查配置文件
cat .env

# 手动运行查看错误
docker run -it --rm --env-file .env yourusername/amq2api:latest
```

### 端口被占用

```bash
# 查看端口占用
sudo lsof -i :8080

# 使用其他端口
docker run -d -p 8081:8080 --env-file .env yourusername/amq2api:latest
```

---

## 性能优化

### 镜像大小优化

当前镜像已优化至 ~320MB,通过:
- ✅ 多阶段构建
- ✅ 精简基础镜像(python:3.11-slim)
- ✅ 清理构建缓存

### 启动速度优化

```bash
# 使用本地缓存
docker compose up -d

# 预热镜像(在业务低峰期更新)
docker pull yourusername/amq2api:latest
```

---

## 安全建议

1. **不要将敏感信息打包进镜像**
   - ✅ 使用 .env 文件
   - ✅ 使用 Docker Secrets
   - ❌ 不要在 Dockerfile 中硬编码凭证

2. **定期更新镜像**
   ```bash
   # 重新构建以获取安全更新
   docker build --no-cache -t yourusername/amq2api:latest .
   docker push yourusername/amq2api:latest
   ```

3. **使用非 root 用户**(已配置)

4. **扫描镜像漏洞**
   ```bash
   docker scout cves amq2api:latest
   ```

---

## 完整部署流程示例

### 在开发机器上

```bash
# 1. 构建镜像
cd amq2api
docker build -t yourusername/amq2api:v1.0 .

# 2. 本地测试
docker run -d -p 8080:8080 --env-file .env yourusername/amq2api:v1.0
curl http://localhost:8080/health

# 3. 推送到 Docker Hub
docker login
docker push yourusername/amq2api:v1.0

# 4. 推送 latest 标签
docker tag yourusername/amq2api:v1.0 yourusername/amq2api:latest
docker push yourusername/amq2api:latest
```

### 在生产 VPS 上

```bash
# 1. 准备环境
mkdir -p ~/amq2api && cd ~/amq2api

# 2. 创建配置
vim .env  # 填写账号信息

# 3. 创建 docker-compose.yml
cat > docker-compose.yml << 'EOF'
version: '3.8'
services:
  amq2api:
    image: yourusername/amq2api:latest
    container_name: amq2api
    ports:
      - "8080:8080"
    env_file:
      - .env
    volumes:
      - token_cache:/home/appuser/.cache/amazonq
    restart: unless-stopped
volumes:
  token_cache:
EOF

# 4. 启动服务
docker compose up -d

# 5. 验证
curl http://localhost:8080/health
curl http://localhost:8080/admin/accounts
```

---

## 相关文档

- [Docker 部署详解](DOCKER_DEPLOYMENT.md)
- [多账号配置指南](MULTI_ACCOUNT.md)
- [快速参考手册](QUICK_REFERENCE.md)

---

**祝你部署顺利! 🚀**
