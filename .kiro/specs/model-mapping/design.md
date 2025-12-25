# Design Document

## Overview

本设计文档描述了模型映射功能的实现方案。该功能允许用户在账号级别配置模型名称映射规则，将从 Claude Code 请求的模型名称自动转换为实际 API 使用的模型名称。这个功能对于处理不同 API 提供商之间的模型命名差异非常有用。

模型映射规则存储在账号的 `other` 字段中，以 JSON 格式保存。前端提供直观的 UI 界面来管理映射规则，包括快捷添加按钮和手动编辑功能。后端在处理请求时自动应用映射规则。

## Architecture

系统采用三层架构：

1. **前端层（Frontend）**: HTML/JavaScript 实现的管理界面
   - 提供模型映射的 CRUD 操作界面
   - 快捷添加按钮用于常用映射
   - 实时验证和错误提示

2. **API 层（Backend API）**: FastAPI 实现的 RESTful API
   - 账号创建和更新端点已存在，无需修改
   - 模型映射数据通过 `other` 字段传递

3. **数据层（Data Layer）**: SQLite/MySQL 数据库
   - 账号表的 `other` 字段存储 JSON 格式的映射规则
   - 无需修改数据库结构

4. **请求处理层（Request Handler）**: 请求路由和转换逻辑
   - 在请求处理时应用模型映射
   - 支持 Amazon Q、Gemini 和 Custom API 三种渠道

## Components and Interfaces

### 1. 数据模型

#### ModelMapping 结构

```python
{
    "modelMappings": [
        {
            "requestModel": "claude-sonnet-4-5-20250929",
            "targetModel": "claude-sonnet-4-5"
        },
        {
            "requestModel": "claude-haiku-4-5-20251001",
            "targetModel": "claude-haiku-4-5"
        }
    ]
}
```

存储位置：`accounts.other` 字段（JSON 格式）

### 2. 前端组件

#### 模型映射管理 UI

位置：`frontend/index.html`

组件结构：
```html
<div id="model_mapping_section">
  <h3>模型映射（可选）</h3>
  <p class="help-text">配置模型映射关系。左侧是客户端请求的模型，右侧是实际发送给API的模型。</p>
  
  <!-- 快捷添加按钮 -->
  <div class="quick-add-buttons">
    <button onclick="addQuickMapping('claude-sonnet-4-5-20250929', 'claude-sonnet-4-5')">+ Sonnet 4.5</button>
    <button onclick="addQuickMapping('claude-haiku-4-5-20251001', 'claude-haiku-4-5')">+ Haiku 4.5</button>
    <button onclick="addQuickMapping('claude-opus-4-5-20251101', 'claude-opus-4-5')">+ Opus 4.5</button>
  </div>
  
  <!-- 映射列表 -->
  <div id="mapping_list"></div>
  
  <!-- 添加映射按钮 -->
  <button onclick="addMappingRow()">添加模型映射</button>
</div>
```

JavaScript 函数：
- `renderMappingList(mappings)`: 渲染映射列表
- `addMappingRow()`: 添加空白映射行
- `addQuickMapping(request, target)`: 快捷添加预定义映射
- `removeMappingRow(index)`: 删除映射行
- `getMappingsFromUI()`: 从 UI 收集映射数据
- `validateMappings(mappings)`: 验证映射数据

### 3. 后端组件

#### 模型映射应用函数

位置：新建 `model_mapper.py`

```python
def apply_model_mapping(account: Dict[str, Any], requested_model: str) -> str:
    """
    应用账号的模型映射规则
    
    Args:
        account: 账号信息字典
        requested_model: 请求的模型名称
    
    Returns:
        映射后的模型名称，如果没有匹配的映射则返回原始模型名称
    """
    other = account.get("other", {})
    if isinstance(other, str):
        import json
        try:
            other = json.loads(other)
        except json.JSONDecodeError:
            return requested_model
    
    model_mappings = other.get("modelMappings", [])
    
    for mapping in model_mappings:
        if mapping.get("requestModel") == requested_model:
            target_model = mapping.get("targetModel")
            if target_model:
                logger.info(f"模型映射: {requested_model} -> {target_model} (账号: {account.get('id')})")
                return target_model
    
    return requested_model
```

#### 集成点

需要在以下位置调用 `apply_model_mapping`:

1. **Amazon Q 渠道** (`main.py` 的 `create_message` 函数)
   - 在获取账号后，转换请求前应用映射

2. **Gemini 渠道** (`main.py` 的 `create_gemini_message` 函数)
   - 在转换为 Gemini 请求前应用映射

3. **Custom API 渠道** (`custom_api/handler.py`)
   - 在构建请求前应用映射

## Data Models

### Account 数据模型扩展

现有的 `accounts` 表不需要修改，模型映射数据存储在 `other` 字段中：

```json
{
  "id": "uuid",
  "label": "我的账号",
  "type": "amazonq",
  "other": {
    "modelMappings": [
      {
        "requestModel": "claude-sonnet-4-5-20250929",
        "targetModel": "claude-sonnet-4-5"
      }
    ],
    // ... 其他现有字段
  }
}
```

### 前端数据流

1. **创建账号**:
   ```
   用户输入 → UI 收集映射 → 构建 other 对象 → POST /v2/accounts
   ```

2. **编辑账号**:
   ```
   加载账号 → 解析 other.modelMappings → 渲染 UI → 用户修改 → PATCH /v2/accounts/{id}
   ```

3. **应用映射**:
   ```
   请求到达 → 获取账号 → 提取 modelMappings → 查找匹配 → 替换模型名称 → 发送请求
   ```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Mapping Storage Integrity

*For any* account with model mappings, when the account is saved and then retrieved, the model mappings should be identical to the original mappings.

**Validates: Requirements 1.3, 2.5, 6.4**

### Property 2: Mapping Application Correctness

*For any* account with model mappings and any requested model that matches a mapping rule, the applied model should equal the target model specified in the mapping.

**Validates: Requirements 4.2**

### Property 3: No Mapping Fallback

*For any* account with model mappings and any requested model that does not match any mapping rule, the applied model should equal the original requested model.

**Validates: Requirements 4.3**

### Property 4: Duplicate Request Model Rejection

*For any* set of model mappings where two or more mappings have the same request model, the validation should fail and reject the submission.

**Validates: Requirements 1.4**

### Property 5: Empty Mapping Filtering

*For any* set of model mappings that includes mappings with empty request or target models, those empty mappings should be filtered out before storage.

**Validates: Requirements 1.5, 7.5**

### Property 6: Mapping Independence

*For any* two accounts with different model mappings, applying mappings for the same requested model should produce different results based on each account's configuration.

**Validates: Requirements 4.4**

### Property 7: Quick-Add Idempotence

*For any* quick-add mapping, clicking the quick-add button multiple times should result in only one mapping being added (no duplicates).

**Validates: Requirements 3.3**

## Error Handling

### 前端错误处理

1. **验证错误**:
   - 空的请求模型或目标模型 → 显示错误提示，阻止提交
   - 重复的请求模型 → 高亮重复项，显示错误消息
   - 格式：红色边框 + 错误文本

2. **网络错误**:
   - API 请求失败 → 显示错误 toast
   - 超时 → 提示用户重试

### 后端错误处理

1. **数据解析错误**:
   - `other` 字段 JSON 解析失败 → 记录日志，返回空映射列表
   - 不影响账号的其他功能

2. **映射应用错误**:
   - 映射数据格式错误 → 记录日志，使用原始模型名称
   - 确保请求能够继续处理

### 错误日志

所有错误都应该记录到日志系统：
```python
logger.error(f"模型映射解析失败 (账号: {account_id}): {error}")
logger.warning(f"模型映射格式错误，使用原始模型: {requested_model}")
```

## Testing Strategy

### 单元测试

使用 pytest 框架编写单元测试：

1. **模型映射应用测试** (`test_model_mapper.py`):
   - 测试匹配映射的情况
   - 测试不匹配映射的情况
   - 测试空映射列表
   - 测试 JSON 解析错误

2. **前端验证测试** (手动测试):
   - 测试重复请求模型检测
   - 测试空字段验证
   - 测试快捷添加按钮

### 属性测试

使用 Hypothesis 框架编写属性测试：

1. **Property 1: Mapping Storage Integrity**
   - 生成随机映射列表
   - 保存到账号
   - 读取并验证一致性

2. **Property 2: Mapping Application Correctness**
   - 生成随机账号和映射
   - 生成匹配的请求模型
   - 验证应用后的模型正确

3. **Property 3: No Mapping Fallback**
   - 生成随机账号和映射
   - 生成不匹配的请求模型
   - 验证返回原始模型

### 集成测试

1. **端到端测试**:
   - 创建账号 with 映射 → 发送请求 → 验证使用正确的模型
   - 编辑账号映射 → 发送请求 → 验证新映射生效

2. **多渠道测试**:
   - 测试 Amazon Q 渠道的映射应用
   - 测试 Gemini 渠道的映射应用
   - 测试 Custom API 渠道的映射应用

### 测试配置

- 最小迭代次数：100 次（属性测试）
- 测试标签格式：`# Feature: model-mapping, Property {number}: {property_text}`

