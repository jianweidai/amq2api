"""
测试 system prompt 过滤功能
用于诊断和修复 Custom API 的 system prompt 问题
"""
import pytest
import re
from src.custom_api.converter import convert_claude_to_openai_request
from src.models import ClaudeRequest


def test_detect_reserved_keywords():
    """测试检测保留关键字"""
    reserved_keywords = [
        "x-anthropic-billing-header",
        "anthropic-billing",
        "billing-header",
    ]
    
    # 测试包含保留关键字的 system prompt
    bad_prompts = [
        "You are a helpful assistant. x-anthropic-billing-header: test",
        "System: x-anthropic-billing-header is reserved",
        "Note: anthropic-billing should not be used",
    ]
    
    for prompt in bad_prompts:
        for keyword in reserved_keywords:
            if keyword.lower() in prompt.lower():
                print(f"✗ 检测到保留关键字 '{keyword}' 在: {prompt[:50]}...")
                assert True
                break


def filter_reserved_keywords(system_prompt: str) -> str:
    """
    从 system prompt 中过滤掉保留关键字
    
    Args:
        system_prompt: 原始 system prompt
    
    Returns:
        过滤后的 system prompt
    """
    if not system_prompt:
        return system_prompt
    
    # 定义保留关键字列表（不区分大小写）
    reserved_keywords = [
        r"x-anthropic-billing-header",
        r"anthropic-billing",
        r"billing-header",
    ]
    
    filtered_prompt = system_prompt
    
    # 移除包含保留关键字的整行
    for keyword in reserved_keywords:
        # 匹配包含关键字的整行（包括前后的空白）
        pattern = rf"^.*{keyword}.*$"
        filtered_prompt = re.sub(pattern, "", filtered_prompt, flags=re.IGNORECASE | re.MULTILINE)
    
    # 清理多余的空行
    filtered_prompt = re.sub(r'\n\s*\n\s*\n', '\n\n', filtered_prompt)
    filtered_prompt = filtered_prompt.strip()
    
    return filtered_prompt


def test_filter_reserved_keywords():
    """测试过滤保留关键字"""
    # 测试用例 1: 包含保留关键字的 prompt
    prompt1 = """You are a helpful assistant.
x-anthropic-billing-header: test
Please help the user."""
    
    filtered1 = filter_reserved_keywords(prompt1)
    assert "x-anthropic-billing-header" not in filtered1.lower()
    assert "helpful assistant" in filtered1
    assert "help the user" in filtered1
    print(f"✓ 测试 1 通过")
    print(f"  原始: {prompt1[:50]}...")
    print(f"  过滤后: {filtered1[:50]}...")
    
    # 测试用例 2: 多个保留关键字
    prompt2 = """System instructions:
1. Be helpful
2. x-anthropic-billing-header should not be used
3. anthropic-billing is reserved
4. Follow user requests"""
    
    filtered2 = filter_reserved_keywords(prompt2)
    assert "x-anthropic-billing-header" not in filtered2.lower()
    assert "anthropic-billing" not in filtered2.lower()
    assert "Be helpful" in filtered2
    assert "Follow user requests" in filtered2
    print(f"✓ 测试 2 通过")
    
    # 测试用例 3: 没有保留关键字
    prompt3 = "You are a helpful assistant. Please help the user."
    filtered3 = filter_reserved_keywords(prompt3)
    assert filtered3 == prompt3
    print(f"✓ 测试 3 通过")
    
    # 测试用例 4: 空 prompt
    prompt4 = ""
    filtered4 = filter_reserved_keywords(prompt4)
    assert filtered4 == ""
    print(f"✓ 测试 4 通过")


def test_filter_in_context():
    """测试在实际场景中过滤"""
    # 模拟 Claude Code 发送的 system prompt
    claude_code_prompt = """You are Claude Code, an AI coding assistant.

Important: x-anthropic-billing-header is a reserved keyword.

Your capabilities:
- Code generation
- Bug fixing
- Code review

Please help the user with their coding tasks."""
    
    filtered = filter_reserved_keywords(claude_code_prompt)
    
    # 验证保留关键字被移除
    assert "x-anthropic-billing-header" not in filtered.lower()
    
    # 验证其他内容保留
    assert "Claude Code" in filtered
    assert "AI coding assistant" in filtered
    assert "Code generation" in filtered
    assert "Bug fixing" in filtered
    
    print(f"✓ 实际场景测试通过")
    print(f"\n原始 prompt:\n{claude_code_prompt}")
    print(f"\n过滤后 prompt:\n{filtered}")


def test_converter_filters_system_prompt():
    """测试 converter 自动过滤 system prompt 中的保留关键字"""
    from src.models import ClaudeMessage
    
    # 创建包含保留关键字的 Claude 请求
    claude_req = ClaudeRequest(
        model="claude-sonnet-4.5",
        messages=[
            ClaudeMessage(
                role="user",
                content="Hello"
            )
        ],
        max_tokens=1024,
        system="You are a helpful assistant.\nx-anthropic-billing-header: test\nPlease help the user."
    )
    
    # 转换为 OpenAI 格式
    openai_req, thinking_enabled = convert_claude_to_openai_request(claude_req, "gpt-4o")
    
    # 验证 system prompt 中的保留关键字被过滤
    system_message = None
    for msg in openai_req["messages"]:
        if msg["role"] == "system":
            system_message = msg["content"]
            break
    
    assert system_message is not None, "应该有 system 消息"
    assert "x-anthropic-billing-header" not in system_message.lower(), "保留关键字应该被过滤"
    assert "helpful assistant" in system_message, "正常内容应该保留"
    assert "help the user" in system_message, "正常内容应该保留"
    
    print(f"✓ Converter 集成测试通过")
    print(f"\n过滤后的 system prompt:\n{system_message}")


def test_converter_filters_system_prompt_array():
    """测试 converter 过滤数组格式的 system prompt"""
    from src.models import ClaudeMessage
    
    # 创建包含保留关键字的 Claude 请求（数组格式）
    claude_req = ClaudeRequest(
        model="claude-sonnet-4.5",
        messages=[
            ClaudeMessage(
                role="user",
                content="Hello"
            )
        ],
        max_tokens=1024,
        system=[
            {"type": "text", "text": "You are a helpful assistant."},
            {"type": "text", "text": "x-anthropic-billing-header: test"},
            {"type": "text", "text": "Please help the user."}
        ]
    )
    
    # 转换为 OpenAI 格式
    openai_req, thinking_enabled = convert_claude_to_openai_request(claude_req, "gpt-4o")
    
    # 验证 system prompt 中的保留关键字被过滤
    system_message = None
    for msg in openai_req["messages"]:
        if msg["role"] == "system":
            system_message = msg["content"]
            break
    
    assert system_message is not None, "应该有 system 消息"
    assert "x-anthropic-billing-header" not in system_message.lower(), "保留关键字应该被过滤"
    assert "helpful assistant" in system_message, "正常内容应该保留"
    assert "help the user" in system_message, "正常内容应该保留"
    
    print(f"✓ Converter 数组格式集成测试通过")
    print(f"\n过滤后的 system prompt:\n{system_message}")


if __name__ == "__main__":
    print("=" * 80)
    print("System Prompt 过滤测试")
    print("=" * 80)
    
    test_detect_reserved_keywords()
    print()
    test_filter_reserved_keywords()
    print()
    test_filter_in_context()
    print()
    test_converter_filters_system_prompt()
    print()
    test_converter_filters_system_prompt_array()
    
    print("\n" + "=" * 80)
    print("所有测试通过！")
    print("=" * 80)
