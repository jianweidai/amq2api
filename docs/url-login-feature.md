# URL 登录功能实现文档

本文档详细描述了项目中的 URL 登录（设备授权）功能的完整实现流程，便于移植到其他项目中使用。

## 功能概述

URL 登录功能允许用户通过 AWS OIDC 设备授权流程（Device Authorization Grant）来获取账号凭证，并自动创建账号。用户只需输入一个 label（可选），系统会生成一个验证链接，用户在浏览器中完成 AWS 登录后，系统自动获取 token 并创建账号。

## 核心流程

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  前端页面   │────▶│  后端 API   │────▶│  AWS OIDC   │────▶│  数据库     │
│  (触发登录) │     │  (协调流程) │     │  (认证服务) │     │  (存储账号) │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

### 三步流程

1. **启动登录** (`POST /v2/auth/start`) - 注册 OIDC 客户端，获取设备授权码和验证链接
2. **用户授权** - 用户在浏览器中打开验证链接，完成 AWS 登录
3. **等待并创建账号** (`POST /v2/auth/claim/{authId}`) - 轮询 token，成功后创建账号

## 涉及的文件

| 文件 | 作用 |
|------|------|
| `src/auth/auth.py` | OIDC 认证核心逻辑（客户端注册、设备授权、token 轮询） |
| `src/main.py` | API 端点定义和业务逻辑 |
| `src/auth/account_manager.py` | 数据库操作抽象层 |
| `frontend/index.html` | 前端 UI（URL登录 Tab） |

---

## 详细实现

### 1. src/auth/auth.py - OIDC 认证核心

这是整个功能的核心模块，包含与 AWS OIDC 服务交互的所有逻辑。

#### 1.1 常量定义

```python
# OIDC 端点
OIDC_BASE = "https://oidc.us-east-1.amazonaws.com"
REGISTER_URL = f"{OIDC_BASE}/client/register"      # 客户端注册
DEVICE_AUTH_URL = f"{OIDC_BASE}/device_authorization"  # 设备授权
TOKEN_URL = f"{OIDC_BASE}/token"                   # Token 获取
START_URL = "https://view.awsapps.com/start"       # AWS 登录起始页

# HTTP 请求头（模拟 AWS CLI）
USER_AGENT = "aws-sdk-rust/1.3.9 os/windows lang/rust/1.87.0"
X_AMZ_USER_AGENT = "aws-sdk-rust/1.3.9 ua/2.1 api/ssooidc/1.88.0 os/windows lang/rust/1.87.0 m/E app/AmazonQ-For-CLI"
AMZ_SDK_REQUEST = "attempt=1; max=3"
```

#### 1.2 请求头构造函数

```python
def make_headers() -> Dict[str, str]:
    return {
        "content-type": "application/json",
        "user-agent": USER_AGENT,
        "x-amz-user-agent": X_AMZ_USER_AGENT,
        "amz-sdk-request": AMZ_SDK_REQUEST,
        "amz-sdk-invocation-id": str(uuid.uuid4()),  # 每次请求唯一 ID
    }
```

#### 1.3 register_client_min() - 注册 OIDC 客户端

```python
async def register_client_min() -> Tuple[str, str]:
    """
    注册 OIDC 客户端，返回 (clientId, clientSecret)
    """
    payload = {
        "clientName": "Amazon Q Developer for command line",
        "clientType": "public",
        "scopes": [
            "codewhisperer:completions",
            "codewhisperer:analysis",
            "codewhisperer:conversations",
        ],
    }
    
    async with httpx.AsyncClient(mounts=mounts) as client:
        r = await post_json(client, REGISTER_URL, payload)
        r.raise_for_status()
        data = r.json()
        return data["clientId"], data["clientSecret"]
```

#### 1.4 device_authorize() - 启动设备授权

```python
async def device_authorize(client_id: str, client_secret: str) -> Dict:
    """
    启动设备授权流程，返回包含以下字段的字典：
    - deviceCode: 设备码（用于后续轮询）
    - interval: 轮询间隔（秒）
    - expiresIn: 过期时间（秒）
    - verificationUriComplete: 完整验证链接（用户需要访问）
    - userCode: 用户码（显示给用户）
    """
    payload = {
        "clientId": client_id,
        "clientSecret": client_secret,
        "startUrl": START_URL,
    }
    
    async with httpx.AsyncClient(mounts=mounts) as client:
        r = await post_json(client, DEVICE_AUTH_URL, payload)
        r.raise_for_status()
        return r.json()
```

#### 1.5 poll_token_device_code() - 轮询获取 Token

```python
async def poll_token_device_code(
    client_id: str,
    client_secret: str,
    device_code: str,
    interval: int,
    expires_in: int,
    max_timeout_sec: Optional[int] = 300,  # 最大等待 5 分钟
) -> Dict:
    """
    轮询 token 端点，直到用户完成授权或超时。
    
    返回包含以下字段的字典：
    - accessToken: 访问令牌
    - refreshToken: 刷新令牌（可选）
    
    异常：
    - TimeoutError: 超时未授权
    - httpx.HTTPError: HTTP 错误
    """
    payload = {
        "clientId": client_id,
        "clientSecret": client_secret,
        "deviceCode": device_code,
        "grantType": "urn:ietf:params:oauth:grant-type:device_code",
    }

    deadline = min(time.time() + expires_in, time.time() + max_timeout_sec)
    poll_interval = max(1, int(interval or 1))

    async with httpx.AsyncClient(mounts=mounts) as client:
        while time.time() < deadline:
            r = await post_json(client, TOKEN_URL, payload)
            
            if r.status_code == 200:
                return r.json()  # 成功获取 token
            
            if r.status_code == 400:
                err = r.json()
                if err.get("error") == "authorization_pending":
                    await asyncio.sleep(poll_interval)  # 继续等待
                    continue
                r.raise_for_status()  # 其他错误
            
            r.raise_for_status()

    raise TimeoutError("Device authorization expired before approval")
```

---

### 2. src/main.py - API 端点实现

#### 2.1 数据结构定义

```python
# 内存中的授权会话存储
AUTH_SESSIONS: Dict[str, Dict[str, Any]] = {}

# 请求体模型
class AuthStartBody(BaseModel):
    label: Optional[str] = None      # 账号标签（可选）
    enabled: Optional[bool] = True   # 是否启用（默认 True）
```

#### 2.2 POST /v2/auth/start - 启动登录

```python
@app.post("/v2/auth/start")
async def auth_start(body: AuthStartBody, _: bool = Depends(verify_admin_password)):
    """启动设备授权，返回验证链接"""
    
    # 1. 注册 OIDC 客户端
    cid, csec = await register_client_min()
    
    # 2. 获取设备授权信息
    dev = await device_authorize(cid, csec)
    
    # 3. 创建会话并存储
    auth_id = str(uuid.uuid4())
    sess = {
        "clientId": cid,
        "clientSecret": csec,
        "deviceCode": dev.get("deviceCode"),
        "interval": int(dev.get("interval", 1)),
        "expiresIn": int(dev.get("expiresIn", 600)),
        "verificationUriComplete": dev.get("verificationUriComplete"),
        "userCode": dev.get("userCode"),
        "startTime": int(time.time()),
        "label": body.label,
        "enabled": True if body.enabled is None else bool(body.enabled),
        "status": "pending",
        "error": None,
        "accountId": None,
    }
    AUTH_SESSIONS[auth_id] = sess
    
    # 4. 返回验证信息
    return {
        "authId": auth_id,
        "verificationUriComplete": sess["verificationUriComplete"],
        "userCode": sess["userCode"],
        "expiresIn": sess["expiresIn"],
        "interval": sess["interval"],
    }
```

#### 2.3 GET /v2/auth/status/{auth_id} - 查询状态

```python
@app.get("/v2/auth/status/{auth_id}")
async def auth_status(auth_id: str, _: bool = Depends(verify_admin_password)):
    """查询授权状态"""
    sess = AUTH_SESSIONS.get(auth_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Auth session not found")
    
    now_ts = int(time.time())
    deadline = sess["startTime"] + min(int(sess.get("expiresIn", 600)), 300)
    remaining = max(0, deadline - now_ts)
    
    return {
        "status": sess.get("status"),      # pending/completed/timeout/error
        "remaining": remaining,             # 剩余时间（秒）
        "error": sess.get("error"),
        "accountId": sess.get("accountId"),
    }
```

#### 2.4 POST /v2/auth/claim/{auth_id} - 等待并创建账号

```python
@app.post("/v2/auth/claim/{auth_id}")
async def auth_claim(auth_id: str, _: bool = Depends(verify_admin_password)):
    """阻塞等待用户授权，成功后创建账号"""
    sess = AUTH_SESSIONS.get(auth_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Auth session not found")
    
    # 如果已完成，直接返回
    if sess.get("status") in ("completed", "timeout", "error"):
        return {
            "status": sess["status"],
            "accountId": sess.get("accountId"),
            "error": sess.get("error"),
        }
    
    try:
        # 1. 轮询获取 token（最多等待 5 分钟）
        toks = await poll_token_device_code(
            sess["clientId"],
            sess["clientSecret"],
            sess["deviceCode"],
            sess["interval"],
            sess["expiresIn"],
            max_timeout_sec=300,
        )
        
        access_token = toks.get("accessToken")
        refresh_token = toks.get("refreshToken")
        
        if not access_token:
            raise HTTPException(status_code=502, detail="No accessToken returned")
        
        # 2. 创建账号
        acc = await _create_account_from_tokens(
            sess["clientId"],
            sess["clientSecret"],
            access_token,
            refresh_token,
            sess.get("label"),
            sess.get("enabled", True),
        )
        
        # 3. 更新会话状态
        sess["status"] = "completed"
        sess["accountId"] = acc["id"]
        
        return {
            "status": "completed",
            "account": acc,
        }
        
    except TimeoutError:
        sess["status"] = "timeout"
        raise HTTPException(status_code=408, detail="Authorization timeout (5 minutes)")
    except httpx.HTTPError as e:
        sess["status"] = "error"
        sess["error"] = str(e)
        raise HTTPException(status_code=502, detail=f"OIDC error: {str(e)}")
```

#### 2.5 _create_account_from_tokens() - 创建账号

```python
async def _create_account_from_tokens(
    client_id: str,
    client_secret: str,
    access_token: str,
    refresh_token: Optional[str],
    label: Optional[str],
    enabled: bool,
) -> Dict[str, Any]:
    """从 token 创建账号并存入数据库"""
    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    acc_id = str(uuid.uuid4())
    
    await _db.execute(
        """
        INSERT INTO accounts (id, label, clientId, clientSecret, refreshToken, 
                            accessToken, other, last_refresh_time, last_refresh_status, 
                            created_at, updated_at, enabled)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            acc_id,
            label,
            client_id,
            client_secret,
            refresh_token,
            access_token,
            None,
            now,
            "success",
            now,
            now,
            1 if enabled else 0,
        ),
    )
    
    row = await _db.fetchone("SELECT * FROM accounts WHERE id=?", (acc_id,))
    return _row_to_dict(row)
```

---

### 3. 数据库表结构

```sql
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    label TEXT,                    -- 账号标签
    clientId TEXT,                 -- OIDC 客户端 ID
    clientSecret TEXT,             -- OIDC 客户端密钥
    refreshToken TEXT,             -- 刷新令牌
    accessToken TEXT,              -- 访问令牌
    other TEXT,                    -- 其他信息（JSON）
    last_refresh_time TEXT,        -- 最后刷新时间
    last_refresh_status TEXT,      -- 最后刷新状态
    created_at TEXT,               -- 创建时间
    updated_at TEXT,               -- 更新时间
    enabled INTEGER DEFAULT 1,     -- 是否启用
    error_count INTEGER DEFAULT 0, -- 错误计数
    success_count INTEGER DEFAULT 0 -- 成功计数
);
```

---

### 4. 前端实现 (frontend/index.html)

#### 4.1 HTML 结构

```html
<div id="tab-login" class="tab-content">
  <div class="panel">
    <h2>URL 登录（5分钟超时）</h2>
    <div class="row">
      <div class="field">
        <label>label（可选）</label>
        <input id="auth_label" />
      </div>
      <div class="field" style="max-width:220px">
        <label>启用（登录成功后新账号是否启用）</label>
        <div>
          <label class="switch">
            <input id="auth_enabled" type="checkbox" checked />
            <span class="slider"></span>
          </label>
        </div>
      </div>
    </div>
    <div class="row">
      <button onclick="startAuth()">开始登录</button>
      <button class="btn-secondary" onclick="claimAuth()">等待授权并创建账号</button>
    </div>
    <div class="field">
      <label>登录信息</label>
      <pre class="code mono" id="auth_info">尚未开始</pre>
    </div>
  </div>
</div>
```

#### 4.2 JavaScript 逻辑

```javascript
let currentAuth = null;

// 启动登录
async function startAuth() {
  const body = {
    label: (document.getElementById('auth_label').value || '').trim() || null,
    enabled: document.getElementById('auth_enabled').checked
  };
  
  try {
    const r = await authFetch(api('/v2/auth/start'), {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body)
    });
    
    if (!r.ok) throw new Error(await r.text());
    
    const j = await r.json();
    currentAuth = j;
    
    // 显示验证信息
    const info = [
      '验证链接: ' + j.verificationUriComplete,
      '用户代码: ' + (j.userCode || ''),
      'authId: ' + j.authId,
      'expiresIn: ' + j.expiresIn + 's',
      'interval: ' + j.interval + 's'
    ].join('\n');
    
    document.getElementById('auth_info').textContent = 
      info + '\n\n请在新窗口中打开上述链接完成登录。';
    
    // 自动打开验证链接
    try { 
      window.open(j.verificationUriComplete, '_blank'); 
    } catch {}
    
  } catch(e) {
    document.getElementById('auth_info').textContent = '启动失败：' + e;
  }
}

// 等待授权并创建账号
async function claimAuth() {
  if (!currentAuth || !currentAuth.authId) {
    document.getElementById('auth_info').textContent = '请先点击"开始登录"。';
    return;
  }
  
  document.getElementById('auth_info').textContent += 
    '\n\n正在等待授权并创建账号（最多5分钟）...';
  
  try {
    const r = await authFetch(
      api('/v2/auth/claim/' + encodeURIComponent(currentAuth.authId)), 
      { method: 'POST' }
    );
    
    const text = await r.text();
    let j;
    try { j = JSON.parse(text); } catch { j = { raw: text }; }
    
    document.getElementById('auth_info').textContent = 
      '完成：\n' + JSON.stringify(j, null, 2);
    
    // 刷新账号列表
    await loadAccounts();
    
  } catch(e) {
    document.getElementById('auth_info').textContent += '\n失败：' + e;
  }
}
```

---

## 移植指南

### 必需依赖

```txt
httpx>=0.24.0
fastapi>=0.100.0
pydantic>=2.0.0
aiosqlite>=0.19.0  # 或其他数据库驱动
```

### 移植步骤

1. **复制核心文件**
   - `src/auth/auth.py` - OIDC 认证逻辑（可直接使用）
   
2. **集成到你的 FastAPI 应用**
   - 导入 auth_flow 模块中的三个函数
   - 创建 `AUTH_SESSIONS` 字典存储会话
   - 实现三个 API 端点
   - 实现 `_create_account_from_tokens()` 函数（根据你的数据库结构调整）

3. **前端集成**
   - 添加 URL 登录 UI
   - 实现 `startAuth()` 和 `claimAuth()` 函数

### 注意事项

1. **会话存储**: 当前实现使用内存存储 `AUTH_SESSIONS`，重启后会丢失。生产环境建议使用 Redis 等持久化存储。

2. **超时设置**: 默认 5 分钟超时，可通过 `max_timeout_sec` 参数调整。

3. **代理支持**: `src/auth/auth.py` 支持通过 `HTTP_PROXY` 环境变量配置代理。

4. **错误处理**: 需要处理网络错误、超时、用户取消等情况。

5. **安全性**: 
   - API 端点需要认证保护（示例中使用 `verify_admin_password`）
   - `clientSecret` 等敏感信息需要安全存储

---

## API 调用示例

### cURL 示例

```bash
# 1. 启动登录
curl -X POST http://localhost:8000/v2/auth/start \
  -H "Authorization: Bearer your_admin_password" \
  -H "Content-Type: application/json" \
  -d '{"label": "我的账号", "enabled": true}'

# 响应示例：
# {
#   "authId": "550e8400-e29b-41d4-a716-446655440000",
#   "verificationUriComplete": "https://device.sso.us-east-1.amazonaws.com/?user_code=XXXX-XXXX",
#   "userCode": "XXXX-XXXX",
#   "expiresIn": 600,
#   "interval": 1
# }

# 2. 用户在浏览器中打开 verificationUriComplete 链接完成登录

# 3. 等待并创建账号
curl -X POST http://localhost:8000/v2/auth/claim/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer your_admin_password"

# 响应示例：
# {
#   "status": "completed",
#   "account": {
#     "id": "...",
#     "label": "我的账号",
#     "clientId": "...",
#     ...
#   }
# }
```

---

## 时序图

```
用户                前端                后端                AWS OIDC
 │                   │                   │                    │
 │  输入 label       │                   │                    │
 │──────────────────▶│                   │                    │
 │                   │  POST /auth/start │                    │
 │                   │──────────────────▶│                    │
 │                   │                   │  register_client   │
 │                   │                   │───────────────────▶│
 │                   │                   │◀───────────────────│
 │                   │                   │  device_authorize  │
 │                   │                   │───────────────────▶│
 │                   │                   │◀───────────────────│
 │                   │◀──────────────────│                    │
 │  显示验证链接     │                   │                    │
 │◀──────────────────│                   │                    │
 │                   │                   │                    │
 │  打开链接并登录   │                   │                    │
 │─────────────────────────────────────────────────────────▶│
 │                   │                   │                    │
 │  点击"等待授权"   │                   │                    │
 │──────────────────▶│                   │                    │
 │                   │ POST /auth/claim  │                    │
 │                   │──────────────────▶│                    │
 │                   │                   │  poll_token (循环) │
 │                   │                   │───────────────────▶│
 │                   │                   │◀───────────────────│
 │                   │                   │  创建账号          │
 │                   │                   │────┐               │
 │                   │                   │◀───┘               │
 │                   │◀──────────────────│                    │
 │  显示成功         │                   │                    │
 │◀──────────────────│                   │                    │
```
