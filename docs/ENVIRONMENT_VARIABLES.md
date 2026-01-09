# 环境变量配置说明

本文档详细说明所有可用的环境变量及其用途。

## 快速开始

复制 `.env.example` 到 `.env` 并根据需要修改：

```bash
cp .env.example .env
```

## 配置分类

### 1. Amazon Q API 配置

用于单账号模式的 Amazon Q 认证信息。如果使用多账号管理，这些可以留空。

| 变量名 | 必需 | 默认值 | 说明 |
|--------|------|--------|------|
| `AMAZONQ_REFRESH_TOKEN` | 否 | - | Amazon Q 的 refresh token |
| `AMAZONQ_CLIENT_ID` | 否 | - | Amazon Q 的 client ID |
| `AMAZONQ_CLIENT_SECRET` | 否 | - | Amazon Q 的 client secret |
| `AMAZONQ_PROFILE_ARN` | 否 | - | Amazon Q 的 profile ARN（可选）|

### 2. 服务配置

| 变量名 | 必需 | 默认值 | 说明 |
|--------|------|--------|------|
| `PORT` | 否 | `8080` | 服务监听端口 |

### 3. 安全配置

| 变量名 | 必需 | 默认值 | 说明 |
|--------|------|--------|------|
| `ADMIN_KEY` | 否 | - | 管理 API 的访问密钥。设置后，访问 `/v2/accounts` 等管理端点需要在请求头中添加 `X-Admin-Key` |
| `API_KEY` | 否 | - | API 访问密钥。设置后，调用 `/v1/messages` 等端点需要在请求头中添加 `X-API-Key` |

**使用示例：**
```bash
# 设置管理密钥
export ADMIN_KEY=my_secret_admin_key

# 调用管理 API
curl -H "X-Admin-Key: my_secret_admin_key" \
  http://localhost:8080/v2/accounts
```

### 4. API Endpoints

| 变量名 | 必需 | 默认值 | 说明 |
|--------|------|--------|------|
| `AMAZONQ_API_ENDPOINT` | 否 | `https://q.us-east-1.amazonaws.com/` | Amazon Q API 端点 |
| `AMAZONQ_TOKEN_ENDPOINT` | 否 | `https://oidc.us-east-1.amazonaws.com/token` | Amazon Q Token 端点 |

### 5. OAuth 回调配置

| 变量名 | 必需 | 默认值 | 说明 |
|--------|------|--------|------|
| `BASE_URL` | 否 | `http://localhost:{PORT}` | OAuth 回调的基础 URL。生产环境应设置为实际域名，如 `https://your-domain.com` |

### 6. 数据库配置

用于多实例部署场景。如果不配置，将使用本地 SQLite。

| 变量名 | 必需 | 默认值 | 说明 |
|--------|------|--------|------|
| `MYSQL_HOST` | 否 | - | MySQL 主机地址 |
| `MYSQL_PORT` | 否 | `3306` | MySQL 端口 |
| `MYSQL_USER` | 否 | - | MySQL 用户名 |
| `MYSQL_PASSWORD` | 否 | - | MySQL 密码 |
| `MYSQL_DATABASE` | 否 | `amq2api` | MySQL 数据库名 |

**使用场景：**
- 单实例部署：使用 SQLite（默认）
- 多实例部署：配置 MySQL 实现数据共享

### 7. Prompt Caching 模拟配置

模拟 Claude API 的 `cache_control` 功能。

| 变量名 | 必需 | 默认值 | 说明 |
|--------|------|--------|------|
| `ENABLE_CACHE_SIMULATION` | 否 | `false` | 是否启用 Prompt Caching 模拟 |
| `CACHE_TTL_SECONDS` | 否 | `86400` | 缓存过期时间（秒），默认 24 小时 |
| `MAX_CACHE_ENTRIES` | 否 | `5000` | 最大缓存条目数 |

**功能说明：**
- 启用后，系统会识别请求中的 `cache_control` 标记
- 模拟 Claude API 的缓存行为，返回 `cache_creation_input_tokens` 和 `cache_read_input_tokens`
- 实际不会减少上游 API 的 token 消耗，仅用于兼容性

### 8. Token 自动刷新配置

后台定期刷新所有账号的 token。

| 变量名 | 必需 | 默认值 | 说明 |
|--------|------|--------|------|
| `ENABLE_AUTO_REFRESH` | 否 | `true` | 是否启用自动刷新 |
| `TOKEN_REFRESH_INTERVAL_HOURS` | 否 | `5` | 刷新间隔（小时）|

**建议：**
- 生产环境建议启用
- 刷新间隔建议设置为 token 有效期的一半

### 9. Token 统计配置

| 变量名 | 必需 | 默认值 | 说明 |
|--------|------|--------|------|
| `ZERO_INPUT_TOKEN_MODELS` | 否 | - | 不统计 input tokens 的模型列表，用逗号分隔。例如：`haiku,other` |

**使用场景：**
- 某些小模型可能不返回准确的 input tokens
- 设置后，这些模型的 input tokens 将记录为 0

### 10. 输入验证配置

控制请求长度验证行为。

| 变量名 | 必需 | 默认值 | 说明 |
|--------|------|--------|------|
| `DISABLE_INPUT_VALIDATION` | 否 | `false` | 是否禁用输入验证。设置为 `true` 可完全禁用 |
| `AMAZONQ_MAX_INPUT_TOKENS` | 否 | `100000` | 最大输入 tokens 限制。仅在验证启用时生效 |

**行为说明：**
- 验证启用时：超过限制会记录警告，但不阻止请求
- 验证禁用时：不进行任何检查
- 建议：如果经常遇到长对话，可以禁用验证或提高限制

**示例：**
```bash
# 完全禁用验证
export DISABLE_INPUT_VALIDATION=true

# 或者提高限制到 200k tokens
export AMAZONQ_MAX_INPUT_TOKENS=200000
```

### 11. Gemini 配置

| 变量名 | 必需 | 默认值 | 说明 |
|--------|------|--------|------|
| `GEMINI_ENABLED` | 否 | `true` | 是否启用 Gemini 功能 |
| `GEMINI_CLIENT_ID` | 否 | - | Gemini OAuth Client ID |
| `GEMINI_CLIENT_SECRET` | 否 | - | Gemini OAuth Client Secret |
| `GEMINI_REFRESH_TOKEN` | 否 | - | Gemini Refresh Token（单账号模式）|
| `GEMINI_API_ENDPOINT` | 否 | `https://daily-cloudcode-pa.sandbox.googleapis.com` | Gemini API 端点 |

### 12. Gemini 投喂站配置

允许用户通过 OAuth 授权贡献自己的 Gemini 账号。

| 变量名 | 必需 | 默认值 | 说明 |
|--------|------|--------|------|
| `GEMINI_DONATE_CLIENT_ID` | 否 | - | 投喂站 OAuth Client ID |
| `GEMINI_DONATE_CLIENT_SECRET` | 否 | - | 投喂站 OAuth Client Secret |

**使用说明：**
- 如果不配置，投喂功能将不可用
- 需要在 Google Cloud Console 创建 OAuth 应用
- 回调 URL 设置为：`{BASE_URL}/api/gemini/oauth/callback`

## 配置示例

### 最小配置（单账号模式）

```bash
# 只配置 Amazon Q
AMAZONQ_REFRESH_TOKEN=your_token
AMAZONQ_CLIENT_ID=your_client_id
AMAZONQ_CLIENT_SECRET=your_secret
PORT=8080
```

### 生产环境配置

```bash
# 服务配置
PORT=8080
BASE_URL=https://your-domain.com

# 安全配置
ADMIN_KEY=your_strong_admin_key
API_KEY=your_strong_api_key

# MySQL 配置
MYSQL_HOST=mysql.example.com
MYSQL_PORT=3306
MYSQL_USER=amq2api
MYSQL_PASSWORD=strong_password
MYSQL_DATABASE=amq2api

# 功能配置
ENABLE_CACHE_SIMULATION=true
ENABLE_AUTO_REFRESH=true
TOKEN_REFRESH_INTERVAL_HOURS=5

# 输入验证（宽松模式）
DISABLE_INPUT_VALIDATION=false
AMAZONQ_MAX_INPUT_TOKENS=200000

# Gemini 配置
GEMINI_ENABLED=true
GEMINI_DONATE_CLIENT_ID=your_oauth_client_id
GEMINI_DONATE_CLIENT_SECRET=your_oauth_secret
```

### 开发环境配置

```bash
# 简单配置，禁用安全检查
PORT=8001
DISABLE_INPUT_VALIDATION=true
ENABLE_CACHE_SIMULATION=true
ENABLE_AUTO_REFRESH=false
```

## 配置优先级

1. 环境变量（最高优先级）
2. `.env` 文件
3. 代码中的默认值（最低优先级）

## 故障排查

### 问题：配置不生效

**检查步骤：**
1. 确认 `.env` 文件在项目根目录
2. 确认环境变量名称拼写正确
3. 重启服务使配置生效
4. 检查日志中的配置加载信息

### 问题：MySQL 连接失败

**检查步骤：**
1. 确认 MySQL 服务正在运行
2. 确认网络连接正常
3. 确认用户名密码正确
4. 确认数据库已创建
5. 查看日志中的详细错误信息

### 问题：OAuth 回调失败

**检查步骤：**
1. 确认 `BASE_URL` 配置正确
2. 确认 OAuth 应用的回调 URL 配置正确
3. 确认 Client ID 和 Secret 正确
4. 检查网络防火墙设置

## 相关文档

- [限流和统计指南](RATE_LIMIT_GUIDE.md)
- [API 详细说明](API_DETAILS.md)
- [Docker 部署](DOCKER_DEPLOY.md)
