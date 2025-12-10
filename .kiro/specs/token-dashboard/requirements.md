# Requirements Document

## Introduction

本功能为 amq2api 代理服务添加一个 Token 使用量仪表盘页面。仪表盘将展示 token 消耗情况、缓存统计、输入输出分布等关键指标，支持按时间范围（小时/天/周/月/全部）查看统计数据。页面采用与现有账号管理页面一致的深色主题设计风格。

## Glossary

- **Token Dashboard**: Token 使用量仪表盘页面
- **input_tokens**: 输入 token 数量
- **output_tokens**: 输出 token 数量
- **cache_creation_input_tokens**: 缓存创建时消耗的 token 数量
- **cache_read_input_tokens**: 从缓存读取的 token 数量
- **Period**: 统计周期（hour/day/week/month/all）
- **Proxy Service**: 本项目的代理服务（amq2api）

## Requirements

### Requirement 1

**User Story:** As a system operator, I want to view token consumption statistics on a dashboard, so that I can monitor API usage at a glance.

#### Acceptance Criteria

1. WHEN a user visits the dashboard page THEN the Proxy Service SHALL display total token consumption for the selected period
2. WHEN a user visits the dashboard page THEN the Proxy Service SHALL display total request count for the selected period
3. WHEN a user visits the dashboard page THEN the Proxy Service SHALL display input tokens and output tokens separately
4. WHEN displaying token statistics THEN the Proxy Service SHALL format large numbers with appropriate units (K/M)

### Requirement 2

**User Story:** As a system operator, I want to view cache statistics on the dashboard, so that I can understand caching effectiveness.

#### Acceptance Criteria

1. WHEN a user visits the dashboard page THEN the Proxy Service SHALL display cache_creation_input_tokens for the selected period
2. WHEN a user visits the dashboard page THEN the Proxy Service SHALL display cache_read_input_tokens for the selected period
3. WHEN displaying cache statistics THEN the Proxy Service SHALL show cache hit ratio if applicable

### Requirement 3

**User Story:** As a system operator, I want to select different time ranges for statistics, so that I can analyze usage patterns over different periods.

#### Acceptance Criteria

1. WHEN a user selects "hour" period THEN the Proxy Service SHALL display statistics for the last hour
2. WHEN a user selects "day" period THEN the Proxy Service SHALL display statistics for the last 24 hours
3. WHEN a user selects "week" period THEN the Proxy Service SHALL display statistics for the last 7 days
4. WHEN a user selects "month" period THEN the Proxy Service SHALL display statistics for the last 30 days
5. WHEN a user selects "all" period THEN the Proxy Service SHALL display all-time statistics

### Requirement 4

**User Story:** As a system operator, I want the dashboard to auto-refresh, so that I can see real-time statistics without manual refresh.

#### Acceptance Criteria

1. WHEN the dashboard page is open THEN the Proxy Service SHALL auto-refresh statistics every 30 seconds
2. WHEN a user clicks the refresh button THEN the Proxy Service SHALL immediately refresh statistics
3. WHEN statistics are being loaded THEN the Proxy Service SHALL display a loading indicator

### Requirement 5

**User Story:** As a system operator, I want the dashboard to match the existing UI style, so that the interface is consistent.

#### Acceptance Criteria

1. WHEN rendering the dashboard THEN the Proxy Service SHALL use the same dark theme as the account management page
2. WHEN rendering statistics cards THEN the Proxy Service SHALL use a card-based layout with icons
3. WHEN the page loads THEN the Proxy Service SHALL be responsive and work on mobile devices
