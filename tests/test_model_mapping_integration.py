"""
端到端集成测试：模型映射功能
测试 Amazon Q、Gemini 和 Custom API 三个渠道的模型映射应用

Requirements: 4.1, 4.2
"""
import pytest
import json
import uuid

# 导入需要测试的模块
from src.auth.account_manager import create_account, delete_account, get_account
from src.processing.model_mapper import apply_model_mapping


class TestAmazonQModelMapping:
    """测试 Amazon Q 渠道的模型映射应用 - Requirements 4.1, 4.2"""
    
    def setup_method(self):
        """每个测试前的设置"""
        # 创建测试账号（带模型映射）
        self.test_account_id = str(uuid.uuid4())
        self.account = create_account(
            label="Test Amazon Q Account",
            client_id="test_client_id",
            client_secret="test_client_secret",
            refresh_token="test_refresh_token",
            access_token="test_access_token",
            other={
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
            },
            enabled=True,
            account_type="amazonq"
        )
        self.test_account_id = self.account['id']
    
    def teardown_method(self):
        """每个测试后的清理"""
        if self.test_account_id:
            delete_account(self.test_account_id)
    
    def test_model_mapping_applied_in_request(self):
        """测试模型映射在请求中被正确应用 - Requirements 4.1"""
        # 验证账号创建成功
        account = get_account(self.test_account_id)
        assert account is not None
        assert account['type'] == 'amazonq'
        
        # 验证模型映射配置
        other = account.get('other', {})
        if isinstance(other, str):
            other = json.loads(other)
        
        mappings = other.get('modelMappings', [])
        assert len(mappings) == 2
        assert mappings[0]['requestModel'] == 'claude-sonnet-4-5-20250929'
        assert mappings[0]['targetModel'] == 'claude-sonnet-4-5'
    
    def test_apply_model_mapping_function(self):
        """测试 apply_model_mapping 函数正确应用映射 - Requirements 4.2"""
        account = get_account(self.test_account_id)
        
        # 测试匹配的映射
        result = apply_model_mapping(account, "claude-sonnet-4-5-20250929")
        assert result == "claude-sonnet-4-5"
        
        # 测试另一个匹配的映射
        result = apply_model_mapping(account, "claude-haiku-4-5-20251001")
        assert result == "claude-haiku-4-5"
        
        # 测试不匹配的模型（应返回原始模型）
        result = apply_model_mapping(account, "claude-opus-4-5")
        assert result == "claude-opus-4-5"
    
    def test_mapping_persists_across_retrieval(self):
        """测试模型映射在数据库存储和读取后保持一致"""
        # 读取账号
        account = get_account(self.test_account_id)
        
        # 验证映射仍然存在且正确
        result = apply_model_mapping(account, "claude-sonnet-4-5-20250929")
        assert result == "claude-sonnet-4-5"


class TestGeminiModelMapping:
    """测试 Gemini 渠道的模型映射应用 - Requirements 4.1, 4.2"""
    
    def setup_method(self):
        """每个测试前的设置"""
        # 创建测试 Gemini 账号（带模型映射）
        self.test_account_id = str(uuid.uuid4())
        self.account = create_account(
            label="Test Gemini Account",
            client_id="test_gemini_client_id",
            client_secret="test_gemini_client_secret",
            refresh_token="test_gemini_refresh_token",
            access_token="test_gemini_access_token",
            other={
                "modelMappings": [
                    {
                        "requestModel": "claude-sonnet-4-5-thinking",
                        "targetModel": "claude-sonnet-4-5"
                    }
                ],
                "project": "test-project-id",
                "api_endpoint": "https://test-gemini-api.com"
            },
            enabled=True,
            account_type="gemini"
        )
        self.test_account_id = self.account['id']
    
    def teardown_method(self):
        """每个测试后的清理"""
        if self.test_account_id:
            delete_account(self.test_account_id)
    
    def test_gemini_model_mapping_applied(self):
        """测试 Gemini 账号的模型映射被正确应用 - Requirements 4.1, 4.2"""
        account = get_account(self.test_account_id)
        assert account is not None
        assert account['type'] == 'gemini'
        
        # 测试映射应用
        result = apply_model_mapping(account, "claude-sonnet-4-5-thinking")
        assert result == "claude-sonnet-4-5"
        
        # 测试不匹配的模型
        result = apply_model_mapping(account, "claude-opus-4-5")
        assert result == "claude-opus-4-5"
    
    def test_gemini_mapping_with_other_fields(self):
        """测试 Gemini 账号的映射不影响其他配置字段"""
        account = get_account(self.test_account_id)
        other = account.get('other', {})
        if isinstance(other, str):
            other = json.loads(other)
        
        # 验证其他字段仍然存在
        assert other.get('project') == 'test-project-id'
        assert other.get('api_endpoint') == 'https://test-gemini-api.com'
        
        # 验证映射也存在
        mappings = other.get('modelMappings', [])
        assert len(mappings) == 1


class TestCustomAPIModelMapping:
    """测试 Custom API 渠道的模型映射应用 - Requirements 4.1, 4.2"""
    
    def setup_method(self):
        """每个测试前的设置"""
        # 创建测试 Custom API 账号（带模型映射）
        self.test_account_id = str(uuid.uuid4())
        self.account = create_account(
            label="Test Custom API Account",
            client_id="test_custom_client_id",
            client_secret="test_custom_api_key",
            refresh_token=None,
            access_token=None,
            other={
                "modelMappings": [
                    {
                        "requestModel": "claude-sonnet-4-5",
                        "targetModel": "gpt-4o"
                    }
                ],
                "format": "openai",
                "api_base": "https://api.openai.com/v1",
                "model": "gpt-4o"
            },
            enabled=True,
            account_type="custom_api"
        )
        self.test_account_id = self.account['id']
    
    def teardown_method(self):
        """每个测试后的清理"""
        if self.test_account_id:
            delete_account(self.test_account_id)
    
    def test_custom_api_model_mapping_applied(self):
        """测试 Custom API 账号的模型映射被正确应用 - Requirements 4.1, 4.2"""
        account = get_account(self.test_account_id)
        assert account is not None
        assert account['type'] == 'custom_api'
        
        # 测试映射应用
        result = apply_model_mapping(account, "claude-sonnet-4-5")
        assert result == "gpt-4o"
        
        # 测试不匹配的模型
        result = apply_model_mapping(account, "claude-opus-4-5")
        assert result == "claude-opus-4-5"
    
    def test_custom_api_mapping_with_format_config(self):
        """测试 Custom API 账号的映射与格式配置共存"""
        account = get_account(self.test_account_id)
        other = account.get('other', {})
        if isinstance(other, str):
            other = json.loads(other)
        
        # 验证格式配置存在
        assert other.get('format') == 'openai'
        assert other.get('api_base') == 'https://api.openai.com/v1'
        assert other.get('model') == 'gpt-4o'
        
        # 验证映射也存在
        mappings = other.get('modelMappings', [])
        assert len(mappings) == 1
        assert mappings[0]['requestModel'] == 'claude-sonnet-4-5'
        assert mappings[0]['targetModel'] == 'gpt-4o'


class TestModelMappingIndependence:
    """测试不同账号的模型映射独立性 - Requirements 4.4"""
    
    def setup_method(self):
        """每个测试前的设置"""
        # 创建两个不同的账号，使用不同的映射规则
        self.account1 = create_account(
            label="Account 1",
            client_id="client1",
            client_secret="secret1",
            refresh_token="refresh1",
            access_token="access1",
            other={
                "modelMappings": [
                    {
                        "requestModel": "claude-sonnet-4-5",
                        "targetModel": "claude-sonnet-4"
                    }
                ]
            },
            enabled=True,
            account_type="amazonq"
        )
        
        self.account2 = create_account(
            label="Account 2",
            client_id="client2",
            client_secret="secret2",
            refresh_token="refresh2",
            access_token="access2",
            other={
                "modelMappings": [
                    {
                        "requestModel": "claude-sonnet-4-5",
                        "targetModel": "claude-haiku-4-5"
                    }
                ]
            },
            enabled=True,
            account_type="amazonq"
        )
    
    def teardown_method(self):
        """每个测试后的清理"""
        if hasattr(self, 'account1') and self.account1:
            delete_account(self.account1['id'])
        if hasattr(self, 'account2') and self.account2:
            delete_account(self.account2['id'])
    
    def test_different_accounts_different_mappings(self):
        """测试不同账号对同一模型应用不同的映射 - Requirements 4.4"""
        # 对同一个请求模型，两个账号应该映射到不同的目标模型
        result1 = apply_model_mapping(self.account1, "claude-sonnet-4-5")
        result2 = apply_model_mapping(self.account2, "claude-sonnet-4-5")
        
        assert result1 == "claude-sonnet-4"
        assert result2 == "claude-haiku-4-5"
        assert result1 != result2
    
    def test_accounts_do_not_interfere(self):
        """测试账号之间的映射不会相互干扰"""
        # 修改 account1 不应影响 account2
        from src.auth.account_manager import update_account
        
        # 更新 account1 的映射
        update_account(
            self.account1['id'],
            other={
                "modelMappings": [
                    {
                        "requestModel": "claude-sonnet-4-5",
                        "targetModel": "claude-opus-4-5"
                    }
                ]
            }
        )
        
        # 重新读取账号
        account1_updated = get_account(self.account1['id'])
        account2_unchanged = get_account(self.account2['id'])
        
        # account1 的映射应该已更新
        result1 = apply_model_mapping(account1_updated, "claude-sonnet-4-5")
        assert result1 == "claude-opus-4-5"
        
        # account2 的映射应该保持不变
        result2 = apply_model_mapping(account2_unchanged, "claude-sonnet-4-5")
        assert result2 == "claude-haiku-4-5"


class TestCrossChannelMapping:
    """测试跨渠道的模型映射功能"""
    
    def setup_method(self):
        """每个测试前的设置"""
        # 创建三个不同渠道的账号，都使用相同的请求模型但映射到不同的目标
        self.amazonq_account = create_account(
            label="Amazon Q Account",
            client_id="amazonq_client",
            client_secret="amazonq_secret",
            refresh_token="amazonq_refresh",
            access_token="amazonq_access",
            other={
                "modelMappings": [
                    {
                        "requestModel": "claude-sonnet-4-5",
                        "targetModel": "claude-sonnet-4"
                    }
                ]
            },
            enabled=True,
            account_type="amazonq"
        )
        
        self.gemini_account = create_account(
            label="Gemini Account",
            client_id="gemini_client",
            client_secret="gemini_secret",
            refresh_token="gemini_refresh",
            access_token="gemini_access",
            other={
                "modelMappings": [
                    {
                        "requestModel": "claude-sonnet-4-5",
                        "targetModel": "gemini-2.0-flash-exp"
                    }
                ],
                "project": "test-project"
            },
            enabled=True,
            account_type="gemini"
        )
        
        self.custom_api_account = create_account(
            label="Custom API Account",
            client_id="custom_client",
            client_secret="custom_secret",
            refresh_token=None,
            access_token=None,
            other={
                "modelMappings": [
                    {
                        "requestModel": "claude-sonnet-4-5",
                        "targetModel": "gpt-4o"
                    }
                ],
                "format": "openai",
                "api_base": "https://api.openai.com/v1"
            },
            enabled=True,
            account_type="custom_api"
        )
    
    def teardown_method(self):
        """每个测试后的清理"""
        if hasattr(self, 'amazonq_account') and self.amazonq_account:
            delete_account(self.amazonq_account['id'])
        if hasattr(self, 'gemini_account') and self.gemini_account:
            delete_account(self.gemini_account['id'])
        if hasattr(self, 'custom_api_account') and self.custom_api_account:
            delete_account(self.custom_api_account['id'])
    
    def test_same_request_model_different_targets_across_channels(self):
        """测试相同的请求模型在不同渠道映射到不同的目标模型"""
        # 同一个请求模型在三个渠道应该映射到不同的目标
        amazonq_result = apply_model_mapping(self.amazonq_account, "claude-sonnet-4-5")
        gemini_result = apply_model_mapping(self.gemini_account, "claude-sonnet-4-5")
        custom_api_result = apply_model_mapping(self.custom_api_account, "claude-sonnet-4-5")
        
        assert amazonq_result == "claude-sonnet-4"
        assert gemini_result == "gemini-2.0-flash-exp"
        assert custom_api_result == "gpt-4o"
        
        # 确保三个结果都不相同
        assert amazonq_result != gemini_result
        assert gemini_result != custom_api_result
        assert amazonq_result != custom_api_result


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
