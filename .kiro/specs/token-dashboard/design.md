# Design Document: Token Dashboard

## Overview

本设计文档描述了为 amq2api 代理服务添加 Token 使用量仪表盘的技术方案。仪表盘将复用现有的 `/v1/usage` API，通过一个新的前端页面展示 token 消耗、缓存统计等关键指标。

### 核心目标

1. 展示 token 消耗统计（总量、输入、输出）
2. 展示缓存统计（创建、读取、命中率）
3. 支持多时间范围选择
4. 自动刷新和手动刷新
5. 与现有 UI 风格一致

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    frontend/dashboard.html                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Dashboard UI                            │   │
│  │  - Period selector (hour/day/week/month/all)             │   │
│  │  - Statistics cards (token, cache, requests)             │   │
│  │  - Auto-refresh (30s interval)                           │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                │ GET /v1/usage?period=xxx
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                         main.py                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              /v1/usage endpoint (existing)                │   │
│  │  - Returns usage summary for specified period            │   │
│  │  - Includes cache statistics                             │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     usage_tracker.py                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              get_usage_summary() (existing)               │   │
│  │  - Aggregates token statistics from database             │   │
│  │  - Returns input/output/cache tokens                     │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. Dashboard Page (frontend/dashboard.html)

新建仪表盘页面，展示统计卡片。

**页面结构：**
- 标题区域：页面标题和刷新按钮
- 时间选择器：hour/day/week/month/all 切换
- 统计卡片网格：
  - 总 Token 消耗
  - 请求次数
  - 输入 Token
  - 输出 Token
  - 缓存创建 Token
  - 缓存读取 Token
  - 缓存命中率

### 2. API Response Format (existing)

现有 `/v1/usage` API 返回格式：

```json
{
  "period": "day",
  "start_time": "2025-12-09 10:00:00",
  "request_count": 59,
  "input_tokens": 20790,
  "output_tokens": 24180,
  "total_tokens": 44970,
  "cache_creation_input_tokens": 1000,
  "cache_read_input_tokens": 500,
  "by_model": [...]
}
```

### 3. Number Formatting Utility

前端 JavaScript 函数，用于格式化大数字：

```javascript
function formatNumber(num) {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(2) + 'M';
  } else if (num >= 1000) {
    return (num / 1000).toFixed(2) + 'K';
  }
  return num.toString();
}
```

### 4. Cache Hit Ratio Calculation

缓存命中率计算公式：

```javascript
function calculateCacheHitRatio(cacheRead, cacheCreation) {
  const total = cacheRead + cacheCreation;
  if (total === 0) return 0;
  return (cacheRead / total) * 100;
}
```

## Data Models

### Usage Summary (existing)

| 字段 | 类型 | 说明 |
|------|------|------|
| period | str | 统计周期 |
| start_time | str | 统计开始时间 |
| request_count | int | 请求次数 |
| input_tokens | int | 输入 token 数 |
| output_tokens | int | 输出 token 数 |
| total_tokens | int | 总 token 数 |
| cache_creation_input_tokens | int | 缓存创建 token 数 |
| cache_read_input_tokens | int | 缓存读取 token 数 |
| by_model | list | 按模型分组统计 |

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Number formatting consistency

*For any* non-negative integer, the formatNumber function should return a string that:
- Uses 'M' suffix for numbers >= 1,000,000
- Uses 'K' suffix for numbers >= 1,000 and < 1,000,000
- Returns the original number as string for numbers < 1,000

**Validates: Requirements 1.4**

### Property 2: Cache hit ratio calculation

*For any* pair of non-negative integers (cacheRead, cacheCreation), the cache hit ratio should be:
- 0 when both values are 0
- (cacheRead / (cacheRead + cacheCreation)) * 100 otherwise
- Always between 0 and 100 inclusive

**Validates: Requirements 2.3**

## Error Handling

### 1. API 请求失败

- 显示错误提示信息
- 保留上次成功加载的数据
- 允许用户手动重试

### 2. 数据为空

- 显示 "暂无数据" 提示
- 所有统计值显示为 0

### 3. 网络超时

- 设置合理的请求超时时间（10秒）
- 超时后显示错误提示

## Testing Strategy

### 单元测试

由于本功能主要是前端页面，核心测试集中在：

1. **数字格式化函数测试**
   - 测试 K/M 后缀转换
   - 测试边界值（999, 1000, 999999, 1000000）

2. **缓存命中率计算测试**
   - 测试零值情况
   - 测试正常计算

### 属性测试

使用 **hypothesis** 库进行属性测试（如果需要后端测试）：

- 每个属性测试运行至少 100 次迭代
- 测试标注格式：`**Feature: token-dashboard, Property {number}: {property_text}**`

### 手动测试

1. 验证页面在不同时间范围下正确显示数据
2. 验证自动刷新功能
3. 验证响应式布局在移动设备上的表现
