# Requirements Document

## Introduction

本功能为 Claude API 代理服务添加自定义 API 账号支持。用户可以添加第三方 API（支持 OpenAI 或 Claude 格式），使其参与负载均衡，从而扩展服务的 API 来源。自定义 API 账号需要完整支持流式响应和工具调用（tool_use），以确保与 Claude Code 的完全兼容。

## Glossary

- **Custom API Account**: 自定义 API 账号，用户配置的第三方 API 服务
- **API Base**: API 的基础 URL，如 `https://api.openai.com/v1`
- **API Key**: 用于认证的密钥，存储在 `clientSecret` 字段
- **Format**: API 格式类型，支持 `openai` 或 `claude`
- **Model**: 目标 API 使用的模型名称
- **Claude Code**: Anthropic 的 Claude Code 客户端，发送 Claude API 格式的请求
- **Tool Use**: Claude API 中的工具调用功能
- **Tool Call**: OpenAI API 中的工具调用功能（等同于 Tool Use）
- **SSE**: Server-Sent Events，流式响应格式

## Requirements

### Requirement 1

**User Story:** As a user, I want to add custom API accounts through the management interface, so that I can use third-party API services as additional backends.

#### Acceptance Criteria

1. WHEN a user selects "Custom API" as account type THEN the system SHALL display input fields for label, apiBase, apiKey, model, and format
2. WHEN a user submits a custom API account with valid fields THEN the system SHALL store the account in the database with type "custom_api"
3. WHEN a user views the account list THEN the system SHALL display custom API accounts with a distinct visual indicator
4. WHEN a user edits a custom API account THEN the system SHALL allow modification of all custom API specific fields
5. WHEN a user deletes a custom API account THEN the system SHALL remove the account from the database

### Requirement 2

**User Story:** As a system administrator, I want custom API accounts to participate in load balancing, so that requests can be distributed across all available backends.

#### Acceptance Criteria

1. WHEN the system selects a channel for a request THEN the system SHALL include enabled custom API accounts in the selection pool
2. WHEN multiple account types are available THEN the system SHALL weight selection by the number of enabled accounts per type
3. WHEN a custom API account is disabled THEN the system SHALL exclude the account from load balancing
4. WHEN all accounts of other types are unavailable THEN the system SHALL fall back to available custom API accounts

### Requirement 3

**User Story:** As a developer using Claude Code, I want the proxy to convert my Claude API requests to OpenAI format when needed, so that I can use OpenAI-compatible APIs seamlessly.

#### Acceptance Criteria

1. WHEN a request is routed to a custom API account with format "openai" THEN the system SHALL convert the Claude request to OpenAI format
2. WHEN converting messages THEN the system SHALL transform Claude content blocks to OpenAI message format
3. WHEN converting tool definitions THEN the system SHALL transform Claude tools to OpenAI function format
4. WHEN converting tool_use blocks THEN the system SHALL transform to OpenAI tool_calls format
5. WHEN converting tool_result blocks THEN the system SHALL transform to OpenAI tool message format
6. WHEN a request is routed to a custom API account with format "claude" THEN the system SHALL forward the request without format conversion

### Requirement 4

**User Story:** As a developer using Claude Code, I want to receive responses in Claude API format regardless of the backend, so that my client works consistently.

#### Acceptance Criteria

1. WHEN receiving a streaming response from an OpenAI format API THEN the system SHALL convert SSE events to Claude format
2. WHEN converting text content THEN the system SHALL transform OpenAI delta content to Claude content_block_delta events
3. WHEN converting tool calls THEN the system SHALL transform OpenAI tool_calls to Claude tool_use blocks
4. WHEN converting usage statistics THEN the system SHALL map OpenAI usage fields to Claude usage format
5. WHEN receiving a response from a Claude format API THEN the system SHALL forward the response without conversion

### Requirement 5

**User Story:** As a developer, I want tool calling to work correctly through custom API backends, so that Claude Code's agentic features function properly.

#### Acceptance Criteria

1. WHEN Claude Code sends a request with tools THEN the system SHALL include tool definitions in the converted request
2. WHEN the backend returns tool_calls THEN the system SHALL convert them to Claude tool_use format
3. WHEN Claude Code sends tool_result THEN the system SHALL convert to the appropriate backend format
4. WHEN multiple tool calls occur in sequence THEN the system SHALL maintain correct tool_use_id mapping

### Requirement 6

**User Story:** As a user, I want to test custom API accounts, so that I can verify they are configured correctly.

#### Acceptance Criteria

1. WHEN a user clicks test on a custom API account THEN the system SHALL send a test request to the configured API
2. WHEN the test succeeds THEN the system SHALL display a success message with response details
3. WHEN the test fails THEN the system SHALL display an error message with failure reason

### Requirement 7

**User Story:** As a system administrator, I want custom API errors to be handled gracefully, so that the system remains stable.

#### Acceptance Criteria

1. WHEN a custom API returns an error THEN the system SHALL convert the error to Claude API error format
2. WHEN a custom API times out THEN the system SHALL return a 502 error with appropriate message
3. WHEN a custom API is unreachable THEN the system SHALL mark the request as failed and return an error
