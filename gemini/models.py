"""
Gemini 数据模型
"""
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class GeminiRequest:
    """Gemini API 请求格式"""
    project: str
    request_id: str
    request: Dict[str, Any]
    model: str
    user_agent: str = "antigravity/1.15.8 linux/arm64"