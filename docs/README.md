# 文档索引

## 功能文档

### 核心功能
- [API 详细说明](API_DETAILS.md) - API 端点和使用说明
- [环境变量配置](ENVIRONMENT_VARIABLES.md) - 所有环境变量的详细说明 ⭐ 新增
- [限流和统计指南](RATE_LIMIT_GUIDE.md) - 账号限流和调用统计功能使用指南 ⭐ 新增
- [账号导入导出指南](IMPORT_EXPORT_ISSUES.md) - 账号数据导入导出完整指南（含数据丢失修复） ⭐ 新增
- [Main 分支功能同步](SYNC_MAIN_FEATURES.md) - Main 分支功能移植到 Release 分支的详细说明 ⭐ 新增

### 高级特性
- [Thinking Mode 实现](thinking-mode-implementation.md) - Thinking 模式的实现细节
- [Azure Thinking Continuity](azure-thinking-continuity.md) - Azure 思考连续性功能
- [Token 计数实现](token-counting-implementation.md) - Token 统计和计数功能
- [URL 登录功能](url-login-feature.md) - URL 登录功能说明

### 集成和扩展
- [Custom API 更新摘要](custom-api-updates-summary.md) - Custom API 功能更新

## 部署文档

- [Docker 部署](DOCKER_DEPLOY.md) - Docker 部署指南

## 变更记录

- [更新日志](CHANGELOG.md) - 版本更新历史
- [Bug 修复](BUGFIXES.md) - Bug 修复记录
- [提交消息](COMMIT_MESSAGE.txt) - 最新功能的 Git 提交消息

## 快速导航

### 新用户
1. 阅读 [README.md](../README.md) 了解项目概述
2. 查看 [环境变量配置](ENVIRONMENT_VARIABLES.md) 配置服务
3. 查看 [Docker 部署](DOCKER_DEPLOY.md) 快速开始
4. 参考 [API 详细说明](API_DETAILS.md) 使用 API

### 功能使用
- **环境配置** → [环境变量配置](ENVIRONMENT_VARIABLES.md)
- **限流管理** → [限流和统计指南](RATE_LIMIT_GUIDE.md)
- **账号导入导出** → [账号导入导出指南](IMPORT_EXPORT_ISSUES.md)
- **多账号管理** → [API 详细说明](API_DETAILS.md#账号管理)
- **Thinking 模式** → [Thinking Mode 实现](thinking-mode-implementation.md)
- **Token 统计** → [Token 计数实现](token-counting-implementation.md)

### 开发者
- **功能实现** → [Main 分支功能同步](SYNC_MAIN_FEATURES.md)
- **架构设计** → [../README.md](../README.md#项目结构)
- **测试** → [../tests/](../tests/)

## 最新更新 (2025-01-09)

### 新增功能
- ✅ 账号调用统计和滑动窗口限流
- ✅ Gemini 429 错误自动换号重试
- ✅ Gemini 转换问题修复
- ✅ 调用记录自动集成
- ✅ 账号导入导出数据丢失修复（weight、rate_limit_per_hour、other 字段完整保留）

详见 [Main 分支功能同步](SYNC_MAIN_FEATURES.md) 和 [账号导入导出指南](IMPORT_EXPORT_ISSUES.md)

## 贡献

如果你发现文档有误或需要补充，欢迎提交 PR 或 Issue。
