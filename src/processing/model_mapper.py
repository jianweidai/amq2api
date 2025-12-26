"""
模型映射模块
负责将请求的模型名称映射到账号配置的目标模型名称
"""
import logging
import json
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def apply_model_mapping(account: Dict[str, Any], requested_model: str) -> str:
    """
    应用账号的模型映射规则
    
    Args:
        account: 账号信息字典
        requested_model: 请求的模型名称
    
    Returns:
        映射后的模型名称，如果没有匹配的映射则返回原始模型名称
    """
    # 获取 other 字段
    other = account.get("other", {})
    
    # 如果 other 是字符串，尝试解析为 JSON
    if isinstance(other, str):
        try:
            other = json.loads(other)
        except json.JSONDecodeError as e:
            logger.warning(f"解析账号 {account.get('id')} 的 other 字段失败: {e}")
            return requested_model
    
    # 获取模型映射列表
    model_mappings = other.get("modelMappings", [])
    
    # 如果没有映射规则，直接返回原始模型
    if not model_mappings:
        return requested_model
    
    # 遍历映射规则，查找匹配项
    for mapping in model_mappings:
        if not isinstance(mapping, dict):
            continue
            
        request_model = mapping.get("requestModel")
        target_model = mapping.get("targetModel")
        
        # 检查是否匹配
        if request_model == requested_model and target_model:
            logger.info(
                f"模型映射应用: {requested_model} -> {target_model} "
                f"(账号: {account.get('id')}, 标签: {account.get('label', 'N/A')})"
            )
            return target_model
    
    # 没有找到匹配的映射，返回原始模型
    return requested_model
