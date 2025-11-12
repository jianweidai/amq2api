#!/bin/bash
#
# VPS 快速部署脚本
# 在新的 VPS 上快速部署 Amazon Q to Claude API Proxy
#

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 配置
IMAGE_NAME="${IMAGE_NAME:-yourusername/amq2api:latest}"
CONTAINER_NAME="amq2api"
PORT="${PORT:-8080}"
DEPLOY_DIR="${HOME}/amq2api"

# 显示横幅
banner() {
    cat << BANNER
${GREEN}================================================================
   Amazon Q to Claude API Proxy - 快速部署脚本
================================================================${NC}

配置信息:
  镜像名称: ${IMAGE_NAME}
  容器名称: ${CONTAINER_NAME}
  监听端口: ${PORT}
  部署目录: ${DEPLOY_DIR}

BANNER
}

# 检查 Docker
check_docker() {
    echo -e "${BLUE}[1/6] 检查 Docker...${NC}"
    
    if ! command -v docker &> /dev/null; then
        echo -e "${YELLOW}Docker 未安装,正在安装...${NC}"
        
        # 检测操作系统
        if [ -f /etc/os-release ]; then
            . /etc/os-release
            OS=$ID
        else
            echo -e "${RED}无法检测操作系统${NC}"
            exit 1
        fi
        
        # 安装 Docker
        curl -fsSL https://get.docker.com | sh
        
        # 启动 Docker 服务
        if command -v systemctl &> /dev/null; then
            sudo systemctl start docker
            sudo systemctl enable docker
        fi
        
        # 添加当前用户到 docker 组
        sudo usermod -aG docker $USER
        
        echo -e "${GREEN}✓ Docker 安装完成${NC}"
        echo -e "${YELLOW}注意: 请重新登录以应用 docker 组权限${NC}"
        echo "运行: exit 后重新连接,然后再次执行此脚本"
        exit 0
    else
        echo -e "${GREEN}✓ Docker 已安装${NC}"
        docker --version
    fi
}

# 检查 Docker Compose
check_docker_compose() {
    echo -e "${BLUE}[2/6] 检查 Docker Compose...${NC}"
    
    if ! docker compose version &> /dev/null; then
        echo -e "${YELLOW}Docker Compose 插件未安装,正在安装...${NC}"
        
        # 安装 Docker Compose 插件
        sudo apt-get update
        sudo apt-get install -y docker-compose-plugin
        
        echo -e "${GREEN}✓ Docker Compose 安装完成${NC}"
    else
        echo -e "${GREEN}✓ Docker Compose 已安装${NC}"
        docker compose version
    fi
}

# 创建部署目录
setup_directory() {
    echo -e "${BLUE}[3/6] 创建部署目录...${NC}"
    
    mkdir -p "${DEPLOY_DIR}"
    cd "${DEPLOY_DIR}"
    
    echo -e "${GREEN}✓ 部署目录: ${DEPLOY_DIR}${NC}"
}

# 配置环境
setup_env() {
    echo -e "${BLUE}[4/6] 配置环境变量...${NC}"
    
    if [ -f .env ]; then
        echo -e "${YELLOW}发现已有 .env 文件${NC}"
        read -p "是否保留现有配置? (Y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Nn]$ ]]; then
            rm .env
        else
            echo -e "${GREEN}✓ 保留现有配置${NC}"
            return
        fi
    fi
    
    echo "创建配置文件..."
    cat > .env << 'ENVFILE'
# 服务配置
PORT=8080

# 多账号数量
AMAZONQ_ACCOUNT_COUNT=3

# 账号 1 - 主账号
AMAZONQ_ACCOUNT_1_ID=primary
AMAZONQ_ACCOUNT_1_REFRESH_TOKEN=your_refresh_token_here
AMAZONQ_ACCOUNT_1_CLIENT_ID=your_client_id_here
AMAZONQ_ACCOUNT_1_CLIENT_SECRET=your_client_secret_here
AMAZONQ_ACCOUNT_1_PROFILE_ARN=
AMAZONQ_ACCOUNT_1_WEIGHT=10
AMAZONQ_ACCOUNT_1_ENABLED=true

# 账号 2 - 备用账号
AMAZONQ_ACCOUNT_2_ID=backup
AMAZONQ_ACCOUNT_2_REFRESH_TOKEN=your_refresh_token_here
AMAZONQ_ACCOUNT_2_CLIENT_ID=your_client_id_here
AMAZONQ_ACCOUNT_2_CLIENT_SECRET=your_client_secret_here
AMAZONQ_ACCOUNT_2_PROFILE_ARN=
AMAZONQ_ACCOUNT_2_WEIGHT=5
AMAZONQ_ACCOUNT_2_ENABLED=true

# 账号 3 - 应急账号
AMAZONQ_ACCOUNT_3_ID=fallback
AMAZONQ_ACCOUNT_3_REFRESH_TOKEN=your_refresh_token_here
AMAZONQ_ACCOUNT_3_CLIENT_ID=your_client_id_here
AMAZONQ_ACCOUNT_3_CLIENT_SECRET=your_client_secret_here
AMAZONQ_ACCOUNT_3_PROFILE_ARN=
AMAZONQ_ACCOUNT_3_WEIGHT=3
AMAZONQ_ACCOUNT_3_ENABLED=true

# 负载均衡策略
LOAD_BALANCE_STRATEGY=weighted_round_robin

# 熔断器配置
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_ERROR_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=300

# API 端点
AMAZONQ_API_ENDPOINT=https://q.us-east-1.amazonaws.com/
AMAZONQ_TOKEN_ENDPOINT=https://oidc.us-east-1.amazonaws.com/token
ENVFILE
    
    echo -e "${YELLOW}请编辑 .env 文件填写账号信息${NC}"
    echo "按回车继续编辑配置文件..."
    read
    
    # 使用默认编辑器
    ${EDITOR:-vim} .env
    
    echo -e "${GREEN}✓ 配置文件已创建${NC}"
}

# 创建 docker-compose.yml
setup_compose() {
    echo -e "${BLUE}[5/6] 创建 docker-compose.yml...${NC}"
    
    cat > docker-compose.yml << COMPOSEFILE
version: '3.8'

services:
  amq2api:
    image: ${IMAGE_NAME}
    container_name: ${CONTAINER_NAME}
    ports:
      - "${PORT}:8080"
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
    driver: local
COMPOSEFILE
    
    echo -e "${GREEN}✓ docker-compose.yml 已创建${NC}"
}

# 启动服务
start_service() {
    echo -e "${BLUE}[6/6] 启动服务...${NC}"
    
    # 停止旧容器
    if docker ps -a | grep -q ${CONTAINER_NAME}; then
        echo "停止旧容器..."
        docker compose down
    fi
    
    # 拉取最新镜像
    echo "拉取镜像..."
    docker pull ${IMAGE_NAME}
    
    # 启动服务
    echo "启动容器..."
    docker compose up -d
    
    # 等待启动
    echo "等待服务启动..."
    sleep 10
    
    # 健康检查
    echo "验证服务..."
    MAX_RETRIES=10
    RETRY=0
    
    while [ $RETRY -lt $MAX_RETRIES ]; do
        if curl -f -s http://localhost:${PORT}/health > /dev/null 2>&1; then
            echo -e "${GREEN}✓ 服务启动成功!${NC}"
            break
        fi
        RETRY=$((RETRY+1))
        echo "等待中... ($RETRY/$MAX_RETRIES)"
        sleep 3
    done
    
    if [ $RETRY -eq $MAX_RETRIES ]; then
        echo -e "${RED}✗ 服务启动失败${NC}"
        echo "查看日志: docker compose logs"
        exit 1
    fi
}

# 显示结果
show_result() {
    echo ""
    echo -e "${GREEN}================================================================${NC}"
    echo -e "${GREEN}✓ 部署完成!${NC}"
    echo -e "${GREEN}================================================================${NC}"
    echo ""
    echo "服务信息:"
    echo "  健康检查: http://localhost:${PORT}/health"
    echo "  账号状态: http://localhost:${PORT}/admin/accounts"
    echo "  指标监控: http://localhost:${PORT}/metrics"
    echo ""
    echo "常用命令:"
    echo "  查看日志: docker compose logs -f"
    echo "  查看状态: docker compose ps"
    echo "  重启服务: docker compose restart"
    echo "  停止服务: docker compose down"
    echo "  更新镜像: docker compose pull && docker compose up -d"
    echo ""
    echo "测试服务:"
    echo "  curl http://localhost:${PORT}/health"
    echo "  curl http://localhost:${PORT}/admin/accounts"
    echo ""
}

# 主流程
main() {
    banner
    check_docker
    check_docker_compose
    setup_directory
    setup_env
    setup_compose
    start_service
    show_result
}

# 执行
main
