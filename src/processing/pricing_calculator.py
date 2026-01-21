"""
价格计算模块
基于 Anthropic 官方定价计算 token 使用成本
"""
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

# Claude 4.5 系列定价（美元/百万 tokens）
# 基于 Anthropic 官方定价表
PRICING_TABLE = {
    "opus-4.5": {
        "base_input": 5.0,           # Base Input Tokens
        "cache_write_5m": 6.25,      # 5m Cache Writes
        "cache_hits": 0.50,          # Cache Hits & Refreshes
        "output": 25.0,              # Output Tokens
    },
    "sonnet-4.5": {
        "base_input": 3.0,
        "cache_write_5m": 3.75,
        "cache_hits": 0.30,
        "output": 15.0,
    },
    "haiku-4.5": {
        "base_input": 1.0,
        "cache_write_5m": 1.25,
        "cache_hits": 0.10,
        "output": 5.0,
    },
}


def identify_model_type(model: str) -> Optional[str]:
    """识别模型类型（模糊匹配）
    
    Args:
        model: 模型名称
    
    Returns:
        模型类型键（opus-4.5/sonnet-4.5/haiku-4.5）或 None
    """
    if not model:
        return None
    
    model_lower = model.lower()
    
    # 匹配 Opus 4.5
    if any(pattern in model_lower for pattern in ['opus-4.5', 'opus-4-5', 'opus4.5', 'opus45']):
        return "opus-4.5"
    
    # 匹配 Sonnet 4.5
    if any(pattern in model_lower for pattern in ['sonnet-4.5', 'sonnet-4-5', 'sonnet4.5', 'sonnet45']):
        return "sonnet-4.5"
    
    # 匹配 Haiku 4.5
    if any(pattern in model_lower for pattern in ['haiku-4.5', 'haiku-4-5', 'haiku4.5', 'haiku45']):
        return "haiku-4.5"
    
    return None


def calculate_cost(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0
) -> Optional[float]:
    """计算单次请求的成本
    
    Args:
        model: 模型名称
        input_tokens: 基础输入 token 数
        output_tokens: 输出 token 数
        cache_creation_input_tokens: 缓存创建 token 数（按 5m Cache Writes 计算）
        cache_read_input_tokens: 缓存读取 token 数
    
    Returns:
        成本（美元），如果模型无法识别则返回 None
    """
    model_type = identify_model_type(model)
    
    if not model_type:
        logger.debug(f"无法识别模型类型，跳过价格计算: {model}")
        return None
    
    pricing = PRICING_TABLE[model_type]
    
    # 计算各部分成本（转换为百万 tokens）
    base_input_cost = (input_tokens / 1_000_000) * pricing["base_input"]
    cache_write_cost = (cache_creation_input_tokens / 1_000_000) * pricing["cache_write_5m"]
    cache_read_cost = (cache_read_input_tokens / 1_000_000) * pricing["cache_hits"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    
    total_cost = base_input_cost + cache_write_cost + cache_read_cost + output_cost
    
    logger.debug(
        f"价格计算 [{model_type}]: "
        f"输入=${base_input_cost:.6f}, "
        f"缓存写=${cache_write_cost:.6f}, "
        f"缓存读=${cache_read_cost:.6f}, "
        f"输出=${output_cost:.6f}, "
        f"总计=${total_cost:.6f}"
    )
    
    return total_cost


def calculate_usage_cost(usage_data: Dict) -> Dict:
    """计算使用量数据的总成本
    
    Args:
        usage_data: 使用量数据字典，包含 by_model 列表
    
    Returns:
        包含总成本和按模型分组成本的字典
    """
    total_cost = 0.0
    model_costs = []
    
    by_model = usage_data.get("by_model", [])
    
    for model_data in by_model:
        model = model_data.get("model", "")
        
        cost = calculate_cost(
            model=model,
            input_tokens=model_data.get("input_tokens", 0),
            output_tokens=model_data.get("output_tokens", 0),
            cache_creation_input_tokens=model_data.get("cache_creation_input_tokens", 0),
            cache_read_input_tokens=model_data.get("cache_read_input_tokens", 0)
        )
        
        if cost is not None:
            total_cost += cost
            model_costs.append({
                "model": model,
                "cost": cost,
                "request_count": model_data.get("request_count", 0),
                "total_tokens": model_data.get("total_tokens", 0)
            })
    
    return {
        "total_cost": total_cost,
        "model_costs": model_costs,
        "currency": "USD"
    }


def format_cost(cost: float) -> str:
    """格式化成本显示
    
    Args:
        cost: 成本（美元）
    
    Returns:
        格式化的成本字符串（如 "$1.23"）
    """
    if cost < 0.01:
        return f"${cost:.4f}"
    elif cost < 1:
        return f"${cost:.3f}"
    else:
        return f"${cost:.2f}"
