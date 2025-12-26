"""
单元测试：模型映射功能
测试 model_mapper.py 中的 apply_model_mapping 函数
"""
import pytest
import json
from src.processing.model_mapper import apply_model_mapping


class TestApplyModelMapping:
    """测试 apply_model_mapping 函数"""
    
    def test_matching_mapping(self):
        """测试匹配映射的情况 - Requirements 4.2"""
        account = {
            "id": "test-account-1",
            "label": "Test Account",
            "other": {
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
        }
        
        # 测试第一个映射
        result = apply_model_mapping(account, "claude-sonnet-4-5-20250929")
        assert result == "claude-sonnet-4-5"
        
        # 测试第二个映射
        result = apply_model_mapping(account, "claude-haiku-4-5-20251001")
        assert result == "claude-haiku-4-5"
    
    def test_no_matching_mapping(self):
        """测试不匹配映射的情况 - Requirements 4.3"""
        account = {
            "id": "test-account-2",
            "label": "Test Account",
            "other": {
                "modelMappings": [
                    {
                        "requestModel": "claude-sonnet-4-5-20250929",
                        "targetModel": "claude-sonnet-4-5"
                    }
                ]
            }
        }
        
        # 请求一个不在映射列表中的模型
        result = apply_model_mapping(account, "claude-opus-4-5-20251101")
        assert result == "claude-opus-4-5-20251101"
    
    def test_empty_mapping_list(self):
        """测试空映射列表 - Requirements 4.3"""
        account = {
            "id": "test-account-3",
            "label": "Test Account",
            "other": {
                "modelMappings": []
            }
        }
        
        result = apply_model_mapping(account, "claude-sonnet-4-5-20250929")
        assert result == "claude-sonnet-4-5-20250929"
    
    def test_no_model_mappings_key(self):
        """测试 other 字段中没有 modelMappings 键"""
        account = {
            "id": "test-account-4",
            "label": "Test Account",
            "other": {}
        }
        
        result = apply_model_mapping(account, "claude-sonnet-4-5-20250929")
        assert result == "claude-sonnet-4-5-20250929"
    
    def test_no_other_field(self):
        """测试账号没有 other 字段"""
        account = {
            "id": "test-account-5",
            "label": "Test Account"
        }
        
        result = apply_model_mapping(account, "claude-sonnet-4-5-20250929")
        assert result == "claude-sonnet-4-5-20250929"
    
    def test_json_string_other_field(self):
        """测试 other 字段为 JSON 字符串的情况"""
        mappings = {
            "modelMappings": [
                {
                    "requestModel": "claude-sonnet-4-5-20250929",
                    "targetModel": "claude-sonnet-4-5"
                }
            ]
        }
        
        account = {
            "id": "test-account-6",
            "label": "Test Account",
            "other": json.dumps(mappings)
        }
        
        result = apply_model_mapping(account, "claude-sonnet-4-5-20250929")
        assert result == "claude-sonnet-4-5"
    
    def test_json_parse_error(self):
        """测试 JSON 解析错误 - Requirements 4.3"""
        account = {
            "id": "test-account-7",
            "label": "Test Account",
            "other": "invalid json string {{"
        }
        
        # 应该返回原始模型名称，不抛出异常
        result = apply_model_mapping(account, "claude-sonnet-4-5-20250929")
        assert result == "claude-sonnet-4-5-20250929"
    
    def test_empty_target_model(self):
        """测试目标模型为空的情况"""
        account = {
            "id": "test-account-8",
            "label": "Test Account",
            "other": {
                "modelMappings": [
                    {
                        "requestModel": "claude-sonnet-4-5-20250929",
                        "targetModel": ""
                    }
                ]
            }
        }
        
        # 空的目标模型应该被忽略，返回原始模型
        result = apply_model_mapping(account, "claude-sonnet-4-5-20250929")
        assert result == "claude-sonnet-4-5-20250929"
    
    def test_missing_target_model(self):
        """测试映射规则缺少 targetModel 字段"""
        account = {
            "id": "test-account-9",
            "label": "Test Account",
            "other": {
                "modelMappings": [
                    {
                        "requestModel": "claude-sonnet-4-5-20250929"
                    }
                ]
            }
        }
        
        result = apply_model_mapping(account, "claude-sonnet-4-5-20250929")
        assert result == "claude-sonnet-4-5-20250929"
    
    def test_invalid_mapping_format(self):
        """测试映射规则格式错误（不是字典）"""
        account = {
            "id": "test-account-10",
            "label": "Test Account",
            "other": {
                "modelMappings": [
                    "invalid-mapping",
                    {
                        "requestModel": "claude-sonnet-4-5-20250929",
                        "targetModel": "claude-sonnet-4-5"
                    }
                ]
            }
        }
        
        # 应该跳过无效的映射，使用有效的映射
        result = apply_model_mapping(account, "claude-sonnet-4-5-20250929")
        assert result == "claude-sonnet-4-5"
    
    def test_multiple_mappings_first_match_wins(self):
        """测试多个映射规则，第一个匹配的生效"""
        account = {
            "id": "test-account-11",
            "label": "Test Account",
            "other": {
                "modelMappings": [
                    {
                        "requestModel": "claude-sonnet-4-5-20250929",
                        "targetModel": "first-target"
                    },
                    {
                        "requestModel": "claude-sonnet-4-5-20250929",
                        "targetModel": "second-target"
                    }
                ]
            }
        }
        
        # 第一个匹配的映射应该生效
        result = apply_model_mapping(account, "claude-sonnet-4-5-20250929")
        assert result == "first-target"
