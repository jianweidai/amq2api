# Requirements Document

## Introduction

本功能为账号管理系统添加模型映射功能。用户可以在创建或编辑账号时配置模型映射规则，将从 Claude Code 请求的模型名称映射到实际 API 账号使用的模型名称。这允许用户灵活地处理不同 API 提供商之间的模型命名差异。

## Glossary

- **Model Mapping**: 模型映射，将请求模型名称转换为目标模型名称的规则
- **Request Model**: 请求模型，从 Claude Code 发送过来的模型名称
- **Target Model**: 目标模型，实际发送到 API 账号的模型名称
- **Account**: 账号，包括 Amazon Q、Gemini 和 Custom API 三种类型
- **Mapping Rule**: 映射规则，一对请求模型和目标模型的对应关系

## Requirements

### Requirement 1

**User Story:** As a user, I want to configure model mappings when creating an account, so that I can define how model names should be translated for this account.

#### Acceptance Criteria

1. WHEN a user creates a new account THEN the system SHALL display a model mapping configuration section
2. WHEN a user adds a mapping rule THEN the system SHALL allow input of both request model and target model names
3. WHEN a user submits the account creation form THEN the system SHALL store the model mappings in the account's `other` field
4. WHEN a user provides duplicate request model names THEN the system SHALL reject the submission with an error message
5. WHEN a user leaves both request and target model fields empty THEN the system SHALL ignore that mapping rule

### Requirement 2

**User Story:** As a user, I want to configure model mappings when editing an existing account, so that I can update or add new mapping rules.

#### Acceptance Criteria

1. WHEN a user edits an account THEN the system SHALL display existing model mappings
2. WHEN a user adds a new mapping rule THEN the system SHALL append it to the existing mappings
3. WHEN a user modifies an existing mapping rule THEN the system SHALL update the corresponding rule
4. WHEN a user deletes a mapping rule THEN the system SHALL remove it from the account's mappings
5. WHEN a user saves the account THEN the system SHALL persist all mapping changes to the database

### Requirement 3

**User Story:** As a user, I want to use predefined quick-add buttons for common model mappings, so that I can quickly configure standard mappings without manual typing.

#### Acceptance Criteria

1. WHEN a user views the model mapping section THEN the system SHALL display quick-add buttons for common model mappings
2. WHEN a user clicks a quick-add button THEN the system SHALL add the corresponding mapping rule to the list
3. WHEN a quick-add mapping already exists THEN the system SHALL not add a duplicate rule
4. THE system SHALL provide quick-add buttons for at least the following mappings:
   - claude-sonnet-4-5-20250929 → claude-sonnet-4-5
   - claude-haiku-4-5-20251001 → claude-haiku-4-5
   - claude-opus-4-5-20251101 → claude-opus-4-5

### Requirement 4

**User Story:** As a developer, I want the system to apply model mappings when processing requests, so that the correct model name is sent to the API.

#### Acceptance Criteria

1. WHEN a request is routed to an account with model mappings THEN the system SHALL check if the requested model matches any mapping rule
2. WHEN a mapping rule matches the requested model THEN the system SHALL replace the model name with the target model
3. WHEN no mapping rule matches the requested model THEN the system SHALL use the original model name
4. WHEN multiple accounts are available THEN the system SHALL apply mappings independently for each account

### Requirement 5

**User Story:** As a user, I want to see a clear visual interface for managing model mappings, so that I can easily understand and modify the mapping configuration.

#### Acceptance Criteria

1. WHEN a user views the model mapping section THEN the system SHALL display each mapping rule as a pair of input fields with an arrow indicator
2. WHEN a user views the model mapping section THEN the system SHALL display a delete button for each mapping rule
3. WHEN a user views the model mapping section THEN the system SHALL display an "Add Mapping" button to create new rules
4. WHEN a user views the model mapping section THEN the system SHALL display a help text explaining the purpose of model mappings
5. THE system SHALL use a visually distinct style for the model mapping section to separate it from other account fields

### Requirement 6

**User Story:** As a system administrator, I want model mappings to be stored in a structured format, so that they can be easily queried and modified programmatically.

#### Acceptance Criteria

1. THE system SHALL store model mappings in the account's `other` field as a JSON object
2. THE system SHALL use the key `modelMappings` to store the mapping rules
3. THE system SHALL store each mapping rule as an object with `requestModel` and `targetModel` fields
4. WHEN retrieving an account THEN the system SHALL parse the `modelMappings` from the `other` field
5. WHEN updating an account THEN the system SHALL serialize the `modelMappings` back to the `other` field

### Requirement 7

**User Story:** As a user, I want to customize both request and target model names, so that I can handle any model naming convention.

#### Acceptance Criteria

1. WHEN a user enters a request model name THEN the system SHALL accept any non-empty string
2. WHEN a user enters a target model name THEN the system SHALL accept any non-empty string
3. WHEN a user submits a mapping with empty request model THEN the system SHALL reject the submission
4. WHEN a user submits a mapping with empty target model THEN the system SHALL reject the submission
5. THE system SHALL trim whitespace from both request and target model names before storing

