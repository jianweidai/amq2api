#!/bin/bash
#
# Docker 镜像构建和推送脚本
# 用于将本地镜像构建并推送到 Docker Hub
#

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 配置(请修改为你的 Docker Hub 用户名)
DOCKER_USERNAME="${DOCKER_USERNAME:-yourusername}"
IMAGE_NAME="amq2api"
FULL_IMAGE_NAME="${DOCKER_USERNAME}/${IMAGE_NAME}"

# 显示使用说明
usage() {
    cat << USAGE
用法: $0 [选项]

选项:
    -u, --username USER    Docker Hub 用户名 (默认: ${DOCKER_USERNAME})
    -t, --tag TAG         镜像标签 (默认: latest)
    -v, --version VER     版本号 (例如: v1.0.0)
    --no-push             只构建不推送
    --no-cache            不使用缓存构建
    -h, --help            显示帮助信息

示例:
    # 构建并推送 latest 标签
    $0

    # 构建并推送指定版本
    $0 -v v1.0.0

    # 只构建不推送
    $0 --no-push

    # 指定用户名和版本
    $0 -u myusername -v v1.0.0
USAGE
    exit 1
}

# 解析命令行参数
TAG="latest"
VERSION=""
NO_PUSH=false
NO_CACHE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -u|--username)
            DOCKER_USERNAME="$2"
            FULL_IMAGE_NAME="${DOCKER_USERNAME}/${IMAGE_NAME}"
            shift 2
            ;;
        -t|--tag)
            TAG="$2"
            shift 2
            ;;
        -v|--version)
            VERSION="$2"
            shift 2
            ;;
        --no-push)
            NO_PUSH=true
            shift
            ;;
        --no-cache)
            NO_CACHE="--no-cache"
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo -e "${RED}错误: 未知选项 $1${NC}"
            usage
            ;;
    esac
done

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: 未安装 Docker${NC}"
    echo "请访问 https://docs.docker.com/get-docker/ 安装 Docker"
    exit 1
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Docker 镜像构建与推送${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "配置信息:"
echo "  Docker 用户名: ${DOCKER_USERNAME}"
echo "  镜像名称: ${FULL_IMAGE_NAME}"
echo "  标签: ${TAG}"
if [ -n "$VERSION" ]; then
    echo "  版本: ${VERSION}"
fi
echo ""

# 确认构建
read -p "确认以上配置并继续? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "已取消"
    exit 0
fi

# 构建镜像
echo -e "${YELLOW}步骤 1/3: 构建镜像...${NC}"
BUILD_TAGS="-t ${FULL_IMAGE_NAME}:${TAG}"

# 如果指定了版本,添加版本标签
if [ -n "$VERSION" ]; then
    BUILD_TAGS="${BUILD_TAGS} -t ${FULL_IMAGE_NAME}:${VERSION}"
    
    # 提取主版本和次版本
    if [[ $VERSION =~ ^v([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
        MAJOR="${BASH_REMATCH[1]}"
        MINOR="${BASH_REMATCH[2]}"
        BUILD_TAGS="${BUILD_TAGS} -t ${FULL_IMAGE_NAME}:v${MAJOR}.${MINOR}"
        BUILD_TAGS="${BUILD_TAGS} -t ${FULL_IMAGE_NAME}:v${MAJOR}"
    fi
fi

echo "构建命令: docker build ${NO_CACHE} ${BUILD_TAGS} ."
docker build ${NO_CACHE} ${BUILD_TAGS} .

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ 镜像构建成功${NC}"
else
    echo -e "${RED}✗ 镜像构建失败${NC}"
    exit 1
fi

# 显示镜像信息
echo ""
echo -e "${YELLOW}步骤 2/3: 镜像信息${NC}"
docker images | grep "${DOCKER_USERNAME}/${IMAGE_NAME}"

# 推送镜像
if [ "$NO_PUSH" = false ]; then
    echo ""
    echo -e "${YELLOW}步骤 3/3: 推送镜像到 Docker Hub...${NC}"
    
    # 检查是否已登录
    if ! docker info | grep -q "Username: ${DOCKER_USERNAME}"; then
        echo "请先登录 Docker Hub:"
        docker login
    fi
    
    # 推送所有标签
    echo "推送 ${FULL_IMAGE_NAME}:${TAG}"
    docker push "${FULL_IMAGE_NAME}:${TAG}"
    
    if [ -n "$VERSION" ]; then
        echo "推送 ${FULL_IMAGE_NAME}:${VERSION}"
        docker push "${FULL_IMAGE_NAME}:${VERSION}"
        
        if [[ $VERSION =~ ^v([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
            MAJOR="${BASH_REMATCH[1]}"
            MINOR="${BASH_REMATCH[2]}"
            echo "推送 ${FULL_IMAGE_NAME}:v${MAJOR}.${MINOR}"
            docker push "${FULL_IMAGE_NAME}:v${MAJOR}.${MINOR}"
            echo "推送 ${FULL_IMAGE_NAME}:v${MAJOR}"
            docker push "${FULL_IMAGE_NAME}:v${MAJOR}"
        fi
    fi
    
    echo -e "${GREEN}✓ 镜像推送成功${NC}"
    echo ""
    echo "在其他服务器上使用:"
    echo "  docker pull ${FULL_IMAGE_NAME}:${TAG}"
else
    echo ""
    echo -e "${YELLOW}跳过推送步骤 (--no-push)${NC}"
fi

# 完成
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ 完成!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "镜像标签:"
docker images | grep "${DOCKER_USERNAME}/${IMAGE_NAME}" | awk '{print "  - " $1":"$2}'

if [ "$NO_PUSH" = false ]; then
    echo ""
    echo "Docker Hub 链接:"
    echo "  https://hub.docker.com/r/${DOCKER_USERNAME}/${IMAGE_NAME}"
fi
