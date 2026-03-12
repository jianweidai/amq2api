"""
模型映射模块
负责将请求的模型名称映射到全局配置的目标模型名称

全局 AMQ 模型映射：
- 存储在数据库 config 表的 "amq_model_mapping" 键中
- 格式为 {"请求模型": "目标模型", ...}
- 通过 enable_model_mapping 开关控制是否启用
- 不在映射表中的模型直接使用原始名称
"""
import logging
import os
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def is_model_mapping_enabled() -> bool:
    """
    检查全局模型映射开关是否启用
    优先读取数据库配置，如果数据库没有则读取环境变量
    """
    try:
        from src.auth.account_manager import get_config
        db_value = get_config("enable_model_mapping")
        if db_value is not None:
            return bool(db_value)
    except Exception as e:
        logger.warning(f"读取数据库模型映射开关失败: {e}")

    # 回退到环境变量，默认 true
    return os.getenv("ENABLE_MODEL_MAPPING", "true").lower() == "true"


def get_amq_model_mapping() -> Dict[str, str]:
    """
    获取全局 AMQ 模型映射配置
    返回 {"请求模型": "目标模型"} 字典
    """
    try:
        from src.auth.account_manager import get_config
        mapping = get_config("amq_model_mapping")
        if isinstance(mapping, dict):
            return mapping
    except Exception as e:
        logger.warning(f"读取全局 AMQ 模型映射失败: {e}")
    return {}


def apply_model_mapping(account: Dict[str, Any], requested_model: str) -> str:
    """
    应用全局 AMQ 模型映射规则

    读取数据库 config 表中的 amq_model_mapping 配置，
    如果请求的模型在映射表中，则返回映射后的模型名称；
    否则返回原始模型名称。

    Args:
        account: 账号信息字典（保留参数以兼容调用方）
        requested_model: 请求的模型名称

    Returns:
        映射后的模型名称，如果没有匹配的映射则返回原始模型名称
    """
    # 检查全局开关
    if not is_model_mapping_enabled():
        logger.debug(f"模型映射已关闭，跳过映射: {requested_model}")
        return requested_model

    # 获取全局映射配置
    mapping = get_amq_model_mapping()
    if not mapping:
        logger.debug(f"全局 AMQ 模型映射为空，跳过: {requested_model}")
        return requested_model

    # 查找映射
    target_model = mapping.get(requested_model)
    if target_model:
        logger.info(
            f"全局模型映射: {requested_model} -> {target_model} "
            f"(账号: {account.get('id')}, 标签: {account.get('label', 'N/A')})"
        )
        return target_model

    # 没有匹配的映射，返回原始模型
    logger.info(f"模型 '{requested_model}' 不在映射表中，使用原始名称 (映射表keys: {list(mapping.keys())})")
    return requested_model
