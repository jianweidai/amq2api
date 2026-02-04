"""
pytest 配置和共享 fixtures

"""
import sys
import os
import pytest

# 确保项目根目录在 Python 路径中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


@pytest.fixture
def sample_claude_request():
    """示例 Claude 请求数据"""
    return {
        "model": "claude-sonnet-4.5",
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": "Hello, world!"}
        ]
    }


@pytest.fixture
def sample_account():
    """示例账号数据"""
    return {
        "id": "test-account-1",
        "label": "Test Account",
        "type": "amazonq",
        "enabled": True,
        "weight": 50
    }
