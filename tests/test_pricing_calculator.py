"""
测试价格计算模块
验证 Claude 4.5 系列模型的价格计算
"""
import pytest
from src.processing.pricing_calculator import (
    identify_model_type,
    calculate_cost,
    calculate_usage_cost,
    format_cost,
    PRICING_TABLE
)


class TestModelIdentification:
    """测试模型识别"""
    
    def test_identify_opus_45(self):
        """测试识别 Opus 4.5"""
        assert identify_model_type("claude-opus-4.5") == "opus-4.5"
        assert identify_model_type("claude-opus-4-5") == "opus-4.5"
        assert identify_model_type("claude-opus-4.5-20250929") == "opus-4.5"
        assert identify_model_type("CLAUDE-OPUS-4.5") == "opus-4.5"
    
    def test_identify_sonnet_45(self):
        """测试识别 Sonnet 4.5"""
        assert identify_model_type("claude-sonnet-4.5") == "sonnet-4.5"
        assert identify_model_type("claude-sonnet-4-5") == "sonnet-4.5"
        assert identify_model_type("claude-sonnet-4.5-20250929") == "sonnet-4.5"
        assert identify_model_type("CLAUDE-SONNET-4.5") == "sonnet-4.5"
    
    def test_identify_haiku_45(self):
        """测试识别 Haiku 4.5"""
        assert identify_model_type("claude-haiku-4.5") == "haiku-4.5"
        assert identify_model_type("claude-haiku-4-5") == "haiku-4.5"
        assert identify_model_type("claude-haiku-4.5-20250929") == "haiku-4.5"
        assert identify_model_type("CLAUDE-HAIKU-4.5") == "haiku-4.5"
    
    def test_identify_unknown_model(self):
        """测试无法识别的模型"""
        assert identify_model_type("claude-sonnet-4") is None
        assert identify_model_type("claude-opus-3") is None
        assert identify_model_type("gpt-4") is None
        assert identify_model_type("") is None
        assert identify_model_type(None) is None


class TestCostCalculation:
    """测试成本计算"""
    
    def test_calculate_sonnet_45_basic(self):
        """测试 Sonnet 4.5 基础成本计算"""
        # 100K input, 50K output
        cost = calculate_cost(
            model="claude-sonnet-4.5",
            input_tokens=100_000,
            output_tokens=50_000
        )
        
        # 预期: (100K / 1M) * $3 + (50K / 1M) * $15 = $0.3 + $0.75 = $1.05
        assert cost is not None
        assert abs(cost - 1.05) < 0.001
    
    def test_calculate_sonnet_45_with_cache(self):
        """测试 Sonnet 4.5 带缓存的成本计算"""
        cost = calculate_cost(
            model="claude-sonnet-4.5",
            input_tokens=100_000,
            output_tokens=50_000,
            cache_creation_input_tokens=20_000,
            cache_read_input_tokens=10_000
        )
        
        # 预期:
        # Base input: (100K / 1M) * $3 = $0.3
        # Cache write (5m): (20K / 1M) * $3.75 = $0.075
        # Cache read: (10K / 1M) * $0.30 = $0.003
        # Output: (50K / 1M) * $15 = $0.75
        # Total: $1.128
        assert cost is not None
        assert abs(cost - 1.128) < 0.001
    
    def test_calculate_haiku_45_cost(self):
        """测试 Haiku 4.5 成本计算"""
        cost = calculate_cost(
            model="claude-haiku-4.5",
            input_tokens=100_000,
            output_tokens=50_000
        )
        
        # 预期: (100K / 1M) * $1 + (50K / 1M) * $5 = $0.1 + $0.25 = $0.35
        assert cost is not None
        assert abs(cost - 0.35) < 0.001
    
    def test_calculate_opus_45_cost(self):
        """测试 Opus 4.5 成本计算"""
        cost = calculate_cost(
            model="claude-opus-4.5",
            input_tokens=100_000,
            output_tokens=50_000
        )
        
        # 预期: (100K / 1M) * $5 + (50K / 1M) * $25 = $0.5 + $1.25 = $1.75
        assert cost is not None
        assert abs(cost - 1.75) < 0.001
    
    def test_calculate_unknown_model_cost(self):
        """测试无法识别模型的成本计算"""
        cost = calculate_cost(
            model="gpt-4",
            input_tokens=100_000,
            output_tokens=50_000
        )
        
        assert cost is None
    
    def test_calculate_zero_tokens(self):
        """测试零 token 的成本计算"""
        cost = calculate_cost(
            model="claude-sonnet-4.5",
            input_tokens=0,
            output_tokens=0
        )
        
        assert cost is not None
        assert cost == 0.0


class TestUsageCostCalculation:
    """测试使用量成本计算"""
    
    def test_calculate_usage_cost_single_model(self):
        """测试单个模型的使用量成本"""
        usage_data = {
            "by_model": [
                {
                    "model": "claude-sonnet-4.5",
                    "request_count": 10,
                    "input_tokens": 100_000,
                    "output_tokens": 50_000,
                    "total_tokens": 150_000,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0
                }
            ]
        }
        
        result = calculate_usage_cost(usage_data)
        
        assert "total_cost" in result
        assert "model_costs" in result
        assert "currency" in result
        assert result["currency"] == "USD"
        assert abs(result["total_cost"] - 1.05) < 0.001
        assert len(result["model_costs"]) == 1
    
    def test_calculate_usage_cost_multiple_models(self):
        """测试多个模型的使用量成本"""
        usage_data = {
            "by_model": [
                {
                    "model": "claude-sonnet-4.5",
                    "request_count": 5,
                    "input_tokens": 50_000,
                    "output_tokens": 25_000,
                    "total_tokens": 75_000,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0
                },
                {
                    "model": "claude-haiku-4.5",
                    "request_count": 10,
                    "input_tokens": 100_000,
                    "output_tokens": 50_000,
                    "total_tokens": 150_000,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0
                }
            ]
        }
        
        result = calculate_usage_cost(usage_data)
        
        # Sonnet: $0.525, Haiku: $0.35, Total: $0.875
        assert abs(result["total_cost"] - 0.875) < 0.001
        assert len(result["model_costs"]) == 2
    
    def test_calculate_usage_cost_with_unknown_model(self):
        """测试包含无法识别模型的使用量成本"""
        usage_data = {
            "by_model": [
                {
                    "model": "claude-sonnet-4.5",
                    "request_count": 5,
                    "input_tokens": 50_000,
                    "output_tokens": 25_000,
                    "total_tokens": 75_000,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0
                },
                {
                    "model": "gpt-4",  # 无法识别
                    "request_count": 10,
                    "input_tokens": 100_000,
                    "output_tokens": 50_000,
                    "total_tokens": 150_000,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0
                }
            ]
        }
        
        result = calculate_usage_cost(usage_data)
        
        # 只计算 Sonnet 的成本
        assert abs(result["total_cost"] - 0.525) < 0.001
        assert len(result["model_costs"]) == 1


class TestCostFormatting:
    """测试成本格式化"""
    
    def test_format_small_cost(self):
        """测试小额成本格式化"""
        assert format_cost(0.0001) == "$0.0001"
        assert format_cost(0.0099) == "$0.0099"
    
    def test_format_medium_cost(self):
        """测试中等成本格式化"""
        assert format_cost(0.123) == "$0.123"
        assert format_cost(0.999) == "$0.999"
    
    def test_format_large_cost(self):
        """测试大额成本格式化"""
        assert format_cost(1.23) == "$1.23"
        assert format_cost(123.45) == "$123.45"
        assert format_cost(1234.56) == "$1234.56"


class TestPricingTable:
    """测试价格表完整性"""
    
    def test_pricing_table_structure(self):
        """测试价格表结构"""
        required_models = ["opus-4.5", "sonnet-4.5", "haiku-4.5"]
        required_fields = ["base_input", "cache_write_5m", "cache_hits", "output"]
        
        for model in required_models:
            assert model in PRICING_TABLE
            for field in required_fields:
                assert field in PRICING_TABLE[model]
                assert isinstance(PRICING_TABLE[model][field], (int, float))
                assert PRICING_TABLE[model][field] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
