# Bug 修复记录

## 2025-01-09: 账号导入导出数据丢失修复

### 问题描述
账号导入导出功能存在严重的数据丢失问题：
- 所有账号类型的 `weight`（权重）和 `rate_limit_per_hour`（限流配置）字段丢失
- Custom API 账号的 `clientId` 字段丢失
- Gemini 账号的 `other` 字段中的扩展信息（creditsInfo、modelMappings）丢失

### 影响范围
- 导出后再导入的账号会丢失自定义权重配置，影响负载均衡
- 导出后再导入的账号会丢失限流配置，可能导致账号被限流或浪费配额
- Gemini 账号的配额信息和模型映射丢失，影响功能正常使用
- Custom API 账号的 clientId 信息永久丢失

### 修复方案
采用扩展管道分隔格式（11字段）+ 向后兼容方案：

**新导出格式**：
```
type|label|clientId|clientSecret|refreshToken|accessToken|project|api_endpoint|weight|rate_limit|other_json
```

**向后兼容**：
- 导入时自动检测格式（8字段旧格式 vs 11字段新格式）
- 旧格式使用默认值填充缺失字段（weight=50, rate_limit_per_hour=20）

### 修改文件
1. **后端**：
   - `src/auth/account_manager.py`：添加 `rate_limit_per_hour` 参数到 `create_account()`
   - `src/main.py`：更新 `AccountCreate` 和 `AccountUpdate` 模型，支持 `rate_limit_per_hour`

2. **前端**：
   - `frontend/index.html`：
     - 导出函数：统一使用11字段格式，完整保留所有字段
     - 导入函数：自动检测格式，解析所有字段包括 `other_json`

3. **测试**：
   - `tests/test_import_export.py`：9个测试用例验证问题和解决方案

4. **文档**：
   - `docs/IMPORT_EXPORT_ISSUES.md`：完整的问题分析和使用指南
   - `docs/README.md`：更新文档索引

### 测试结果
- 所有测试通过：160/160 ✅
- 导入导出测试：9/9 ✅
- 向后兼容性验证通过

### 使用建议
1. 立即重新导出所有账号，保存为新格式备份
2. 旧格式文件仍可导入，但会使用默认值填充缺失字段
3. 查看 [账号导入导出指南](IMPORT_EXPORT_ISSUES.md) 了解详细使用方法

---

## 2025-01-08: 输入验证限制调整

### 问题描述
输入验证的 token 限制过于严格（30,000 tokens），导致正常的长对话被拒绝。

### 修复方案
1. 提高默认限制从 30,000 到 100,000 tokens
2. 添加 `AMAZONQ_MAX_INPUT_TOKENS` 环境变量支持自定义限制
3. 添加 `DISABLE_INPUT_VALIDATION` 环境变量支持完全禁用验证
4. 将验证改为警告模式，不阻止请求

### 修改文件
- `src/processing/input_validator.py`
- `src/main.py`
- `tests/test_input_validator.py`

---

## 2025-01-08: model_mapper NoneType 错误修复

### 问题描述
```
AttributeError: 'NoneType' object has no attribute 'get'
```

在 `src/processing/model_mapper.py` 中，当账号的 `other` 字段为 `None` 时会导致错误。

### 修复方案
1. 添加 `other` 字段的 null 检查
2. 添加类型验证确保 `other` 是字典
3. 添加 JSON 解析错误处理

### 修改文件
- `src/processing/model_mapper.py`
- `tests/test_model_mapper_fix.py`（7个测试用例）

### 测试结果
所有测试通过：151/151 ✅

---

## 历史修复记录

更多历史修复记录请查看 Git 提交历史。
