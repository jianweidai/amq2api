# Implementation Plan: Model Mapping

## Overview

本实现计划将模型映射功能集成到现有的账号管理系统中。实现分为三个主要部分：后端模型映射逻辑、前端 UI 组件和集成测试。

## Tasks

- [x] 1. 实现后端模型映射核心逻辑
  - 创建 `model_mapper.py` 模块
  - 实现 `apply_model_mapping` 函数
  - 添加日志记录
  - _Requirements: 4.2, 4.3, 6.4_

- [ ]* 1.1 编写模型映射应用的属性测试
  - **Property 2: Mapping Application Correctness**
  - **Validates: Requirements 4.2**

- [ ]* 1.2 编写无映射回退的属性测试
  - **Property 3: No Mapping Fallback**
  - **Validates: Requirements 4.3**

- [ ] 2. 集成模型映射到请求处理流程
  - [x] 2.1 在 Amazon Q 渠道应用模型映射
    - 修改 `main.py` 的 `create_message` 函数
    - 在获取账号后应用映射
    - _Requirements: 4.1, 4.2_

  - [x] 2.2 在 Gemini 渠道应用模型映射
    - 修改 `main.py` 的 `create_gemini_message` 函数
    - 在转换请求前应用映射
    - _Requirements: 4.1, 4.2_

  - [x] 2.3 在 Custom API 渠道应用模型映射
    - 修改 `custom_api/handler.py`
    - 在构建请求前应用映射
    - _Requirements: 4.1, 4.2_

- [ ]* 2.4 编写映射独立性的属性测试
  - **Property 6: Mapping Independence**
  - **Validates: Requirements 4.4**

- [x] 3. Checkpoint - 确保后端逻辑正常工作
  - 确保所有测试通过，如有问题请询问用户

- [x] 4. 实现前端模型映射 UI 组件
  - [x] 4.1 添加模型映射 HTML 结构
    - 在 `frontend/index.html` 中添加映射管理区域
    - 添加快捷按钮（Sonnet 4.5, Haiku 4.5, Opus 4.5）
    - 添加映射列表容器
    - _Requirements: 1.1, 3.1, 5.1, 5.2, 5.3, 5.4_

  - [x] 4.2 实现映射管理 JavaScript 函数
    - 实现 `renderMappingList(mappings)` 函数
    - 实现 `addMappingRow()` 函数
    - 实现 `addQuickMapping(request, target)` 函数
    - 实现 `removeMappingRow(index)` 函数
    - _Requirements: 1.2, 2.2, 2.3, 2.4, 3.2_

  - [x] 4.3 实现映射数据收集和验证
    - 实现 `getMappingsFromUI()` 函数
    - 实现 `validateMappings(mappings)` 函数
    - 检测重复的请求模型
    - 过滤空映射
    - _Requirements: 1.4, 1.5, 7.3, 7.4, 7.5_

  - [x] 4.4 集成映射 UI 到账号创建流程
    - 修改 `createAccount()` 函数
    - 收集映射数据并添加到 `other` 字段
    - _Requirements: 1.3, 6.2, 6.3_

  - [x] 4.5 集成映射 UI 到账号编辑流程
    - 修改 `editAccount()` 函数
    - 加载现有映射到 UI
    - 保存修改后的映射
    - _Requirements: 2.1, 2.5, 6.5_

- [ ]* 4.6 手动测试前端功能
  - 测试快捷添加按钮（验证 Property 7）
  - 测试重复检测
  - 测试空字段验证
  - _Requirements: 3.3, 1.4, 1.5_

- [x] 5. Checkpoint - 确保前端 UI 正常工作
  - 前端实现已完成，可以进行手动测试

- [-] 6. 编写单元测试
  - [x] 6.1 创建 `test_model_mapper.py`
    - 测试匹配映射的情况
    - 测试不匹配映射的情况
    - 测试空映射列表
    - 测试 JSON 解析错误
    - _Requirements: 4.2, 4.3_

- [ ]* 6.2 编写映射存储完整性的属性测试
  - **Property 1: Mapping Storage Integrity**
  - **Validates: Requirements 1.3, 2.5, 6.4**

- [ ]* 6.3 编写重复请求模型拒绝的属性测试
  - **Property 4: Duplicate Request Model Rejection**
  - **Validates: Requirements 1.4**

- [ ]* 6.4 编写空映射过滤的属性测试
  - **Property 5: Empty Mapping Filtering**
  - **Validates: Requirements 1.5, 7.5**

- [x] 7. 端到端集成测试
  - [x] 7.1 测试 Amazon Q 渠道的映射应用
    - 创建账号 with 映射
    - 发送请求
    - 验证使用正确的模型
    - _Requirements: 4.1, 4.2_

  - [x] 7.2 测试 Gemini 渠道的映射应用
    - 创建账号 with 映射
    - 发送请求
    - 验证使用正确的模型
    - _Requirements: 4.1, 4.2_

  - [x] 7.3 测试 Custom API 渠道的映射应用
    - 创建账号 with 映射
    - 发送请求
    - 验证使用正确的模型
    - _Requirements: 4.1, 4.2_

- [x] 8. Final Checkpoint - 确保所有功能正常
  - 确保所有测试通过，如有问题请询问用户

## Notes

- 任务标记 `*` 的为可选任务，可以跳过以加快 MVP 开发
- 每个任务都引用了具体的需求编号以便追溯
- Checkpoint 任务确保增量验证
- 属性测试验证通用正确性属性
- 单元测试验证具体示例和边界情况

