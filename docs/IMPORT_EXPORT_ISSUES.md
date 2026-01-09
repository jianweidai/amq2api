# 账号导入导出功能问题分析与修复

## 修复状态：✅ 已完成

所有数据丢失问题已修复，导入导出功能现在完整保留所有账号字段。

## 问题概述

当前的账号导入导出功能存在数据丢失问题，会导致以下字段在导出后再导入时丢失：

1. **所有账号类型**：`weight`（权重）、`rate_limit_per_hour`（限流配置）
2. **Custom API 账号**：`clientId` 字段
3. **Gemini 账号**：`other` 字段中的 `creditsInfo`、`modelMappings` 等扩展信息

## 详细问题分析

### 1. Amazon Q 账号

**旧导出格式**：
```
amazonq|label|clientId|clientSecret|refreshToken|accessToken|project|api_endpoint
```

**丢失字段**：
- `weight`：账号权重（默认50，用户可能自定义为其他值）
- `rate_limit_per_hour`：每小时限流（默认20，用户可能自定义）

**影响**：
- 导入后权重恢复为默认值50，影响负载均衡
- 导入后限流恢复为默认值20，可能导致账号被限流或浪费配额

### 2. Gemini 账号

**旧导出格式**：
```
gemini|label|clientId|clientSecret|refreshToken|accessToken|project|api_endpoint
```

**丢失字段**：
- `weight`：账号权重
- `rate_limit_per_hour`：每小时限流
- `other.creditsInfo`：配额信息（包含各模型的剩余配额和重置时间）
- `other.modelMappings`：模型映射配置

**影响**：
- 配额信息丢失，无法正确判断模型是否可用
- 模型映射丢失，可能导致请求失败
- 权重和限流配置丢失

### 3. Custom API 账号

**旧导出格式**：
```
custom_api|label|clientSecret(apiKey)|empty|empty|api_base|model|format
```

**问题**：
- 格式与其他账号类型不一致
- `clientId` 字段被跳过，直接导出 `clientSecret`
- 使用空字段占位，导致格式混乱

**丢失字段**：
- `clientId`：客户端ID（如果用户存储了重要信息）
- `weight`：账号权重
- `rate_limit_per_hour`：每小时限流
- `other` 中除 `api_base`、`model`、`format` 外的所有字段

**影响**：
- `clientId` 信息永久丢失
- 无法恢复完整的账号配置

## 解决方案

采用**扩展管道分隔格式 + 向后兼容**方案。

### 新导出格式（11字段）

```
type|label|clientId|clientSecret|refreshToken|accessToken|project|api_endpoint|weight|rate_limit|other_json
```

**字段说明**：
1. `type`：账号类型（amazonq/gemini/custom_api）
2. `label`：账号标签
3. `clientId`：客户端ID
4. `clientSecret`：客户端密钥（Custom API 为 API Key）
5. `refreshToken`：刷新令牌
6. `accessToken`：访问令牌
7. `project`：项目ID（Gemini）
8. `api_endpoint`：API端点（Gemini/Custom API）
9. `weight`：账号权重（1-100，默认50）
10. `rate_limit`：每小时调用限制（默认20）
11. `other_json`：其他扩展字段的JSON序列化（如 creditsInfo、modelMappings 等）

**示例**：
```
amazonq|我的账号|client123|secret456|refresh789|access000|||50|20|{}
gemini|Gemini账号|client|secret|refresh|access|my-project|https://api.com|70|30|{"creditsInfo":{"models":{...}},"modelMappings":[...]}
custom_api|自定义API|custom_client|api_key_123|||https://api.custom.com||80|50|{"api_base":"https://api.custom.com","model":"gpt-4","format":"openai"}
```

### 向后兼容

导入功能自动检测格式：
- **8个字段**：旧格式，使用默认值填充 `weight=50`、`rate_limit_per_hour=20`、`other={}`
- **11个字段**：新格式，完整解析所有字段

这确保了旧的导出文件仍然可以导入，只是会使用默认值填充缺失的字段。

## 实现的修改

### 1. 后端修改

#### `src/auth/account_manager.py`
- ✅ 在 `create_account()` 函数添加 `rate_limit_per_hour` 参数
- ✅ 更新 SQLite 和 MySQL 的 INSERT 语句包含 `rate_limit_per_hour` 字段

#### `src/main.py`
- ✅ 在 `AccountCreate` 模型添加 `rate_limit_per_hour` 字段
- ✅ 在 `AccountUpdate` 模型添加 `rate_limit_per_hour` 字段
- ✅ 更新 `create_account_endpoint` 传递 `rate_limit_per_hour` 参数
- ✅ 更新 `update_account_endpoint` 支持更新 `rate_limit_per_hour`

### 2. 前端修改

#### `frontend/index.html`

**导出函数修改**：
- ✅ 统一所有账号类型使用相同的11字段格式
- ✅ 包含 `weight` 和 `rate_limit_per_hour` 字段
- ✅ 将 `other` 中除 `project` 和 `api_endpoint` 外的字段序列化为 JSON
- ✅ 移除 Custom API 的特殊格式，使用统一格式

**导入函数修改**：
- ✅ 添加格式自动检测（8字段 vs 11字段）
- ✅ 解析 `weight` 和 `rate_limit_per_hour` 字段
- ✅ 解析 `other_json` 并合并到 `other` 对象
- ✅ 在创建账号时传递 `weight` 和 `rate_limit_per_hour`
- ✅ 向后兼容旧格式（使用默认值）

**UI 更新**：
- ✅ 更新导入格式说明，显示新格式并注明兼容旧格式

## 测试覆盖

已创建测试文件 `tests/test_import_export.py`，包含：
- ✅ 各账号类型的导出格式测试
- ✅ 数据丢失问题验证
- ✅ 解决方案验证（JSON格式和扩展管道格式）

运行测试：
```bash
python3 -m pytest tests/test_import_export.py -v
```

所有测试通过：9/9 ✅

完整测试套件：
```bash
python3 -m pytest tests/ -v
```

所有测试通过：160/160 ✅

## 使用指南

### 导出账号

1. 在管理界面点击"导出所有账号"或"导出选中"按钮
2. 下载的文件使用新的11字段格式
3. 文件名格式：`accounts_all_YYYY-MM-DD.txt` 或 `accounts_selected_N_YYYY-MM-DD.txt`

### 导入账号

1. 准备账号数据文件（支持新旧格式）
2. 选择导入类型：
   - **完整格式**：支持所有账号类型，自动检测新旧格式
   - **Amazon Q 简化**：6字段格式（email|password|clientId|clientSecret|refreshToken|accessToken）
   - **Gemini 简化**：7字段格式（label|clientId|clientSecret|refreshToken|accessToken|project|api_endpoint）
3. 粘贴账号数据到文本框
4. 点击"批量导入"按钮

### 格式示例

**新格式（推荐）**：
```
amazonq|主账号|client_id_1|secret_1|refresh_1|access_1|||80|30|{}
gemini|Gemini测试|client_id_2|secret_2|refresh_2|access_2|my-project|https://api.gemini.com|70|25|{"modelMappings":[{"from":"claude-3-5-sonnet-20241022","to":"gemini-2.0-flash-exp"}]}
custom_api|OpenAI代理|user_id|api_key_xxx|||||60|40|{"api_base":"https://api.openai.com/v1","model":"gpt-4","format":"openai"}
```

**旧格式（仍然支持）**：
```
amazonq|主账号|client_id_1|secret_1|refresh_1|access_1||
gemini|Gemini测试|client_id_2|secret_2|refresh_2|access_2|my-project|https://api.gemini.com
```

## 迁移建议

1. **立即重新导出**：使用新版本重新导出所有账号，保存为备份
2. **验证导入**：在测试环境导入验证所有字段正确
3. **更新文档**：更新团队文档，说明新的导出格式
4. **保留旧备份**：保留旧格式的备份文件，以防需要回滚

## 注意事项

1. **旧格式导入**：旧格式文件导入后，`weight` 和 `rate_limit_per_hour` 会使用默认值（50和20）
2. **JSON转义**：`other_json` 字段中的特殊字符（如管道符 `|`）会被JSON自动转义，无需手动处理
3. **空字段**：空字段使用空字符串表示，不要省略管道符
4. **注释行**：以 `#` 开头的行会被忽略，可用于添加注释

## 相关文件

- `frontend/index.html`：导入导出UI和逻辑
- `src/auth/account_manager.py`：账号数据库操作
- `src/main.py`：账号管理API端点
- `tests/test_import_export.py`：导入导出测试
- `docs/ENVIRONMENT_VARIABLES.md`：环境变量文档
