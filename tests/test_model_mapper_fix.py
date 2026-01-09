"""
测试 model_mapper 的空值处理
"""
import pytest
from src.processing.model_mapper import apply_model_mapping


def test_apply_model_mapping_with_none_other():
    """测试 other 字段为 None 的情况"""
    account = {
        "id": "test-account",
        "label": "Test Account",
        "other": None  # other 为 None
    }
    
    # 应该返回原始模型，不抛出异常
    result = apply_model_mapping(account, "claude-sonnet-4.5")
    assert result == "claude-sonnet-4.5"


def test_apply_model_mapping_with_empty_other():
    """测试 other 字段为空字符串的情况"""
    account = {
        "id": "test-account",
        "label": "Test Account",
        "other": ""  # other 为空字符串
    }
    
    # 应该返回原始模型，不抛出异常
    result = apply_model_mapping(account, "claude-sonnet-4.5")
    assert result == "claude-sonnet-4.5"


def test_apply_model_mapping_with_missing_other():
    """测试 other 字段缺失的情况"""
    account = {
        "id": "test-account",
        "label": "Test Account"
        # 没有 other 字段
    }
    
    # 应该返回原始模型，不抛出异常
    result = apply_model_mapping(account, "claude-sonnet-4.5")
    assert result == "claude-sonnet-4.5"


def test_apply_model_mapping_with_empty_dict():
    """测试 other 字段为空字典的情况"""
    account = {
        "id": "test-account",
        "label": "Test Account",
        "other": {}  # other 为空字典
    }
    
    # 应该返回原始模型
    result = apply_model_mapping(account, "claude-sonnet-4.5")
    assert result == "claude-sonnet-4.5"


def test_apply_model_mapping_with_invalid_json():
    """测试 other 字段为无效 JSON 字符串的情况"""
    account = {
        "id": "test-account",
        "label": "Test Account",
        "other": "{invalid json"  # 无效的 JSON
    }
    
    # 应该返回原始模型，不抛出异常
    result = apply_model_mapping(account, "claude-sonnet-4.5")
    assert result == "claude-sonnet-4.5"


def test_apply_model_mapping_with_valid_mapping():
    """测试正常的模型映射"""
    account = {
        "id": "test-account",
        "label": "Test Account",
        "other": {
            "modelMappings": [
                {
                    "requestModel": "claude-sonnet-4.5",
                    "targetModel": "gemini-2.5-flash"
                }
            ]
        }
    }
    
    # 应该返回映射后的模型
    result = apply_model_mapping(account, "claude-sonnet-4.5")
    assert result == "gemini-2.5-flash"


def test_apply_model_mapping_with_no_match():
    """测试没有匹配的映射"""
    account = {
        "id": "test-account",
        "label": "Test Account",
        "other": {
            "modelMappings": [
                {
                    "requestModel": "claude-opus-4",
                    "targetModel": "gemini-3-pro-high"
                }
            ]
        }
    }
    
    # 请求的模型不在映射中，应该返回原始模型
    result = apply_model_mapping(account, "claude-sonnet-4.5")
    assert result == "claude-sonnet-4.5"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
