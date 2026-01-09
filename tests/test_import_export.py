"""
测试账号导入导出功能
验证所有账号类型的数据完整性
"""
import pytest
import json


class TestImportExportFormat:
    """测试导入导出格式的数据完整性"""

    def test_amazonq_export_format(self):
        """测试 Amazon Q 账号导出格式"""
        # 模拟账号数据
        account = {
            "id": "test-id-1",
            "type": "amazonq",
            "label": "测试账号",
            "clientId": "client123",
            "clientSecret": "secret456",
            "refreshToken": "refresh789",
            "accessToken": "access000",
            "other": {
                "project": "",
                "api_endpoint": "",
                "weight": 50,
                "rate_limit_per_hour": 20
            }
        }

        # 模拟导出逻辑
        other = account.get("other", {})
        export_line = f"{account['type']}|{account['label']}|{account['clientId']}|{account['clientSecret']}|{account['refreshToken']}|{account['accessToken']}|{other.get('project', '')}|{other.get('api_endpoint', '')}"

        # 验证导出格式
        parts = export_line.split('|')
        assert len(parts) == 8
        assert parts[0] == "amazonq"
        assert parts[1] == "测试账号"
        assert parts[2] == "client123"
        assert parts[3] == "secret456"
        assert parts[4] == "refresh789"
        assert parts[5] == "access000"
        # project 和 api_endpoint 为空
        assert parts[6] == ""
        assert parts[7] == ""

    def test_gemini_export_format(self):
        """测试 Gemini 账号导出格式"""
        account = {
            "id": "test-id-2",
            "type": "gemini",
            "label": "Gemini账号",
            "clientId": "gemini_client",
            "clientSecret": "gemini_secret",
            "refreshToken": "gemini_refresh",
            "accessToken": "gemini_access",
            "other": {
                "project": "my-project",
                "api_endpoint": "https://api.gemini.com",
                "creditsInfo": {
                    "models": {
                        "claude-3-5-sonnet-20241022": {
                            "remainingFraction": 0.8,
                            "remainingPercent": 80
                        }
                    }
                },
                "modelMappings": [
                    {"from": "claude-3-5-sonnet-20241022", "to": "gemini-model"}
                ]
            }
        }

        # 模拟导出逻辑
        other = account.get("other", {})
        export_line = f"{account['type']}|{account['label']}|{account['clientId']}|{account['clientSecret']}|{account['refreshToken']}|{account['accessToken']}|{other.get('project', '')}|{other.get('api_endpoint', '')}"

        # 验证导出格式
        parts = export_line.split('|')
        assert len(parts) == 8
        assert parts[0] == "gemini"
        assert parts[1] == "Gemini账号"
        assert parts[6] == "my-project"
        assert parts[7] == "https://api.gemini.com"

        # 问题：creditsInfo 和 modelMappings 丢失了！

    def test_custom_api_export_format_issue(self):
        """测试 Custom API 账号导出格式 - 发现数据丢失问题"""
        account = {
            "id": "test-id-3",
            "type": "custom_api",
            "label": "自定义API",
            "clientId": "custom_client",  # 这个字段会丢失！
            "clientSecret": "api_key_123",
            "refreshToken": None,
            "accessToken": None,
            "other": {
                "api_base": "https://api.custom.com",
                "model": "gpt-4",
                "format": "openai"
            }
        }

        # 当前的导出逻辑（有问题）
        other = account.get("other", {})
        current_export = f"{account['type']}|{account['label']}|{account['clientSecret']}|||{other.get('api_base', '')}|{other.get('model', '')}|{other.get('format', 'openai')}"

        # 验证当前导出格式
        parts = current_export.split('|')
        assert len(parts) == 8
        assert parts[0] == "custom_api"
        assert parts[1] == "自定义API"
        assert parts[2] == "api_key_123"  # clientSecret (API Key)
        assert parts[3] == ""  # 空字段
        assert parts[4] == ""  # 空字段
        assert parts[5] == "https://api.custom.com"
        assert parts[6] == "gpt-4"
        assert parts[7] == "openai"

        # 问题：clientId 字段丢失了！
        # 如果 clientId 存储了重要信息（如用户ID），导入后会丢失

    def test_import_custom_api_missing_clientid(self):
        """测试导入 Custom API 时 clientId 缺失的问题"""
        # 模拟从导出文件导入的数据
        import_line = "custom_api|自定义API|api_key_123|||https://api.custom.com|gpt-4|openai"
        parts = import_line.split('|')

        # 模拟导入逻辑（完整格式）
        type_val = parts[0]
        label = parts[1]
        clientId = parts[2] if len(parts) > 2 else ""
        clientSecret = parts[3] if len(parts) > 3 else ""
        refreshToken = parts[4] if len(parts) > 4 else ""
        accessToken = parts[5] if len(parts) > 5 else ""
        project = parts[6] if len(parts) > 6 else ""
        api_endpoint = parts[7] if len(parts) > 7 else ""

        # 对于 custom_api，当前导出格式是：
        # type|label|clientSecret(apiKey)|empty|empty|api_base|model|format
        # 所以导入时需要特殊处理
        if type_val == "custom_api":
            # clientId 位置实际是 clientSecret (API Key)
            # clientSecret 位置是空的
            # 需要重新映射
            actual_api_key = clientId  # parts[2]
            api_base = project  # parts[6] 实际是 api_base
            model = api_endpoint  # parts[7] 实际是 model
            format_val = parts[8] if len(parts) > 8 else "openai"

            # 问题：没有地方存储原始的 clientId！

    def test_gemini_import_missing_other_fields(self):
        """测试 Gemini 导入时 other 字段中的数据丢失"""
        # 原始账号有 creditsInfo 和 modelMappings
        original_other = {
            "project": "my-project",
            "api_endpoint": "https://api.gemini.com",
            "creditsInfo": {
                "models": {
                    "claude-3-5-sonnet-20241022": {
                        "remainingFraction": 0.8,
                        "remainingPercent": 80
                    }
                }
            },
            "modelMappings": [
                {"from": "claude-3-5-sonnet-20241022", "to": "gemini-model"}
            ],
            "rate_limit_per_hour": 30,
            "weight": 70
        }

        # 导出格式只包含 project 和 api_endpoint
        export_line = f"gemini|账号|client|secret|refresh|access|my-project|https://api.gemini.com"

        # 导入时重建 other
        parts = export_line.split('|')
        project = parts[6]
        api_endpoint = parts[7]

        imported_other = {}
        if project:
            imported_other["project"] = project
        if api_endpoint:
            imported_other["api_endpoint"] = api_endpoint

        # 验证数据丢失
        assert "creditsInfo" not in imported_other
        assert "modelMappings" not in imported_other
        assert "rate_limit_per_hour" not in imported_other
        assert "weight" not in imported_other

        # 这些重要信息在导入后会丢失！


class TestImportExportDataLoss:
    """测试导入导出过程中的数据丢失问题"""

    def test_weight_field_loss(self):
        """测试权重字段是否会丢失"""
        # 权重存储在数据库的 weight 字段，不在 other 中
        # 但导出格式中没有包含 weight 字段
        account = {
            "id": "test-id",
            "type": "amazonq",
            "label": "测试",
            "weight": 80,  # 自定义权重
            "clientId": "client",
            "clientSecret": "secret",
            "refreshToken": "refresh",
            "accessToken": "access",
            "other": {}
        }

        # 导出不包含 weight
        export_line = f"{account['type']}|{account['label']}|{account['clientId']}|{account['clientSecret']}|{account['refreshToken']}|{account['accessToken']}||"

        # 导入后 weight 会使用默认值 50，而不是原来的 80
        # 数据丢失！

    def test_rate_limit_field_loss(self):
        """测试限流字段是否会丢失"""
        # rate_limit_per_hour 存储在数据库字段，不在 other 中
        # 但导出格式中没有包含此字段
        account = {
            "id": "test-id",
            "type": "gemini",
            "label": "测试",
            "rate_limit_per_hour": 100,  # 自定义限流
            "clientId": "client",
            "clientSecret": "secret",
            "refreshToken": "refresh",
            "accessToken": "access",
            "other": {
                "project": "proj",
                "api_endpoint": "https://api.com"
            }
        }

        # 导出不包含 rate_limit_per_hour
        other = account.get("other", {})
        export_line = f"{account['type']}|{account['label']}|{account['clientId']}|{account['clientSecret']}|{account['refreshToken']}|{account['accessToken']}|{other.get('project', '')}|{other.get('api_endpoint', '')}"

        # 导入后 rate_limit_per_hour 会使用默认值 20，而不是原来的 100
        # 数据丢失！


class TestProposedSolution:
    """测试建议的解决方案"""

    def test_json_export_format(self):
        """测试使用 JSON 格式导出（完整保留所有字段）"""
        account = {
            "id": "test-id",
            "type": "custom_api",
            "label": "自定义API",
            "clientId": "custom_client",
            "clientSecret": "api_key_123",
            "refreshToken": None,
            "accessToken": None,
            "weight": 80,
            "rate_limit_per_hour": 50,
            "other": {
                "api_base": "https://api.custom.com",
                "model": "gpt-4",
                "format": "openai",
                "modelMappings": [{"from": "claude", "to": "gpt"}]
            }
        }

        # JSON 导出（完整保留所有字段）
        json_export = json.dumps(account, ensure_ascii=False)
        imported = json.loads(json_export)

        # 验证所有字段都保留
        assert imported["clientId"] == "custom_client"
        assert imported["weight"] == 80
        assert imported["rate_limit_per_hour"] == 50
        assert imported["other"]["modelMappings"] == [{"from": "claude", "to": "gpt"}]

    def test_extended_pipe_format(self):
        """测试扩展的管道分隔格式（向后兼容）"""
        account = {
            "id": "test-id",
            "type": "custom_api",
            "label": "自定义API",
            "clientId": "custom_client",
            "clientSecret": "api_key_123",
            "refreshToken": "",
            "accessToken": "",
            "weight": 80,
            "rate_limit_per_hour": 50,
            "other": {
                "api_base": "https://api.custom.com",
                "model": "gpt-4",
                "format": "openai"
            }
        }

        # 扩展格式：添加 weight 和 rate_limit_per_hour 字段
        # 格式：type|label|clientId|clientSecret|refreshToken|accessToken|project|api_endpoint|weight|rate_limit|other_json
        other = account.get("other", {})
        other_json = json.dumps(other, ensure_ascii=False) if other else ""

        export_line = f"{account['type']}|{account['label']}|{account['clientId']}|{account['clientSecret']}|{account.get('refreshToken', '')}|{account.get('accessToken', '')}|{other.get('project', '')}|{other.get('api_endpoint', '')}|{account.get('weight', 50)}|{account.get('rate_limit_per_hour', 20)}|{other_json}"

        # 验证导出
        parts = export_line.split('|')
        assert len(parts) == 11
        assert parts[8] == "80"  # weight
        assert parts[9] == "50"  # rate_limit_per_hour
        assert parts[10] != ""  # other_json

        # 模拟导入
        imported_weight = int(parts[8]) if len(parts) > 8 and parts[8] else 50
        imported_rate_limit = int(parts[9]) if len(parts) > 9 and parts[9] else 20
        imported_other = json.loads(parts[10]) if len(parts) > 10 and parts[10] else {}

        assert imported_weight == 80
        assert imported_rate_limit == 50
        assert imported_other["api_base"] == "https://api.custom.com"
