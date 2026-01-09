# 安全漏洞修复说明

## 修复日期
2025-01-09

## 漏洞描述

### 🚨 严重性：高危

在修复前，管理后台存在以下安全问题：

### 1. **ADMIN_KEY 未设置时完全无保护**
- 如果环境变量 `ADMIN_KEY` 未设置，任何人都可以访问管理 API
- 攻击者可以：
  - 查看所有账号信息（包括 tokens）
  - 创建/修改/删除账号
  - 刷新 tokens
  - 导出所有账号数据

### 2. **密钥存储在 localStorage**
- 前端将 `ADMIN_KEY` 永久存储在浏览器的 `localStorage` 中
- 风险：
  - XSS 攻击可以窃取密钥
  - 任何能访问该浏览器的人都能获取密钥
  - 密钥不会过期，除非手动清除

### 3. **URL 参数传递密钥**
- 管理页面支持 `?key=ADMIN_KEY` 参数
- 风险：
  - 密钥会出现在浏览器历史记录中
  - 密钥会出现在服务器日志中
  - 密钥可能被代理服务器记录

## 修复措施

### ✅ 后端修复

#### 1. 强制要求 ADMIN_KEY
```python
async def verify_admin_key(x_admin_key: Optional[str] = Header(None)):
    """验证管理员密钥"""
    admin_key = os.getenv("ADMIN_KEY")

    # 如果没有设置 ADMIN_KEY，拒绝访问
    if not admin_key:
        logger.warning("⚠️  ADMIN_KEY 未设置！管理功能已禁用。")
        raise HTTPException(status_code=403, detail="管理功能已禁用：未设置 ADMIN_KEY")

    # 必须验证密钥
    if not x_admin_key or x_admin_key != admin_key:
        raise HTTPException(status_code=403, detail="访问被拒绝")
    return True
```

**改进**：
- ❌ 旧：未设置 `ADMIN_KEY` 时允许访问
- ✅ 新：未设置 `ADMIN_KEY` 时拒绝所有管理请求

#### 2. 管理页面也需要鉴权
```python
@app.get("/admin", response_class=FileResponse)
async def admin_page(_: bool = Depends(verify_admin_key)):
    """管理页面（需要鉴权）"""
    # 必须在 HTTP Header 中提供 X-Admin-Key
```

**改进**：
- ❌ 旧：通过 URL 参数 `?key=xxx` 验证
- ✅ 新：通过 HTTP Header `X-Admin-Key` 验证

### ✅ 前端修复

#### 1. 使用 sessionStorage 替代 localStorage
```javascript
function getAdminKey() {
    // 使用 sessionStorage（标签关闭后自动清除）
    let adminKey = sessionStorage.getItem('adminKey');
    
    // 从 URL 获取后立即清除 URL 参数
    if (!adminKey) {
        const urlParams = new URLSearchParams(window.location.search);
        const keyFromUrl = urlParams.get('key');
        if (keyFromUrl) {
            sessionStorage.setItem('adminKey', keyFromUrl);
            // 清除 URL 中的密钥参数
            window.history.replaceState({}, document.title, window.location.pathname);
            adminKey = keyFromUrl;
        }
    }
    
    return adminKey;
}
```

**改进**：
- ❌ 旧：密钥永久存储在 `localStorage`
- ✅ 新：密钥存储在 `sessionStorage`（标签关闭后自动清除）
- ✅ 新：从 URL 获取密钥后立即清除 URL 参数

#### 2. 添加登录提示和退出功能
```javascript
// 如果没有密钥，提示用户输入
function showLoginPrompt() {
    const key = prompt('请输入管理员密钥 (ADMIN_KEY):');
    if (key) {
        sessionStorage.setItem('adminKey', key);
        location.reload();
    }
}

// 退出登录
function logout() {
    sessionStorage.removeItem('adminKey');
    alert('已退出登录');
    location.reload();
}
```

#### 3. 自动处理认证失败
```javascript
function authFetch(url, options = {}) {
    return fetch(url, { ...options, headers })
        .then(response => {
            // 如果返回 403，清除密钥并提示重新登录
            if (response.status === 403) {
                sessionStorage.removeItem('adminKey');
                alert('管理员密钥无效或已过期，请重新登录');
                location.reload();
                throw new Error('认证失败');
            }
            return response;
        });
}
```

## 使用说明

### 首次配置

1. **设置 ADMIN_KEY 环境变量**（必需）：
```bash
# .env 文件
ADMIN_KEY=your_secure_random_key_here
```

⚠️ **重要**：请使用强密码，建议至少 32 个字符的随机字符串。

生成强密码示例：
```bash
# Linux/Mac
openssl rand -base64 32

# Python
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

2. **重启服务**：
```bash
docker compose restart
# 或
./start.sh
```

### 访问管理后台

#### 方法 1：通过 URL 参数（首次登录）
```
http://localhost:8080/admin?key=YOUR_ADMIN_KEY
```
- 密钥会自动保存到 sessionStorage
- URL 中的密钥参数会被自动清除

#### 方法 2：通过登录提示
```
http://localhost:8080/admin
```
- 如果没有密钥，会弹出输入框
- 输入密钥后会保存到 sessionStorage

#### 方法 3：直接使用 API（推荐用于脚本）
```bash
curl -H "X-Admin-Key: YOUR_ADMIN_KEY" http://localhost:8080/v2/accounts
```

### 退出登录

点击页面右上角的 "🚪 退出登录" 按钮，或关闭浏览器标签。

## 安全最佳实践

### ✅ 推荐做法

1. **始终设置 ADMIN_KEY**
   - 即使是本地开发环境也应该设置
   - 使用强密码（至少 32 个字符）

2. **定期更换密钥**
   - 建议每 3-6 个月更换一次
   - 如果怀疑密钥泄露，立即更换

3. **使用 HTTPS**
   - 生产环境必须使用 HTTPS
   - 防止密钥在传输过程中被窃取

4. **限制访问来源**
   - 使用防火墙限制管理端口的访问
   - 仅允许信任的 IP 地址访问

5. **监控访问日志**
   - 定期检查服务器日志
   - 注意异常的访问模式

### ❌ 不推荐做法

1. **不要在 URL 中长期保留密钥**
   - 不要分享带密钥的 URL
   - 不要将带密钥的 URL 保存到书签

2. **不要在公共场所使用**
   - 避免在公共 WiFi 下访问管理后台
   - 使用后及时退出登录

3. **不要使用弱密码**
   - 不要使用 "admin"、"123456" 等简单密码
   - 不要使用与其他服务相同的密码

## 迁移指南

### 从旧版本升级

如果你正在使用旧版本（未修复的版本）：

1. **更新代码**：
```bash
git pull origin main
```

2. **设置 ADMIN_KEY**：
```bash
# 在 .env 文件中添加
ADMIN_KEY=$(openssl rand -base64 32)
```

3. **重启服务**：
```bash
docker compose down
docker compose up -d
```

4. **清除浏览器缓存**：
- 打开浏览器开发者工具（F12）
- 进入 Application/Storage 标签
- 清除 localStorage 中的 `adminKey`

5. **重新登录**：
- 访问 `http://localhost:8080/admin?key=YOUR_NEW_ADMIN_KEY`

## 测试验证

### 验证修复是否生效

1. **测试未设置 ADMIN_KEY**：
```bash
# 临时移除 ADMIN_KEY
unset ADMIN_KEY
./start.sh

# 尝试访问管理 API（应该返回 403）
curl http://localhost:8080/v2/accounts
# 预期结果：{"detail":"管理功能已禁用：未设置 ADMIN_KEY"}
```

2. **测试错误的密钥**：
```bash
# 使用错误的密钥（应该返回 403）
curl -H "X-Admin-Key: wrong_key" http://localhost:8080/v2/accounts
# 预期结果：{"detail":"访问被拒绝：需要有效的管理员密钥"}
```

3. **测试正确的密钥**：
```bash
# 使用正确的密钥（应该返回账号列表）
curl -H "X-Admin-Key: YOUR_ADMIN_KEY" http://localhost:8080/v2/accounts
# 预期结果：[{"id":"...","label":"..."}]
```

## 相关文件

- `src/main.py` - 后端鉴权逻辑
- `frontend/index.html` - 前端认证处理
- `.env.example` - 环境变量示例
- `docs/ENVIRONMENT_VARIABLES.md` - 环境变量文档

## 问题反馈

如果发现安全问题，请通过以下方式报告：
- 创建 GitHub Issue（标记为 Security）
- 或直接联系项目维护者

**请勿在公开渠道披露安全漏洞细节。**
