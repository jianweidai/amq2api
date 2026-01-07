#!/usr/bin/env python3
"""
测试 thinking 块清理修复
"""
import sys
import logging
from src.custom_api.handler import _clean_claude_request_for_azure

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_thinking_cleanup():
    """测试 thinking 块清理逻辑
    
    Azure API 要求：当 thinking 启用时，最后一条 assistant 消息必须以 thinking 块开头。
    如果最后一条 assistant 消息没有有效的 thinking 块开头，需要禁用 thinking 功能。
    """
    
    # 模拟包含 thinking 块的请求数据（带有 thinking 参数）
    # 注意：最后一条 assistant 消息的 thinking 块没有 signature，所以 thinking 会被禁用
    request_data = {
        "model": "claude-haiku-4-5",
        "thinking": {"type": "enabled"},
        "messages": [
            {
                "role": "user",
                "content": "Hello"
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "我需要思考这个问题",
                        # 注意：这里没有 signature
                    },
                    {
                        "type": "text",
                        "text": "Hello! 我在这里帮你。"
                    }
                ]
            }
        ]
    }
    
    print("=== 测试用例 1: 包含缺少 signature 的 thinking 块（最后一条 assistant 消息）===")
    print("原始请求:")
    import json
    print(json.dumps(request_data, ensure_ascii=False, indent=2))
    
    # 清理请求
    cleaned = _clean_claude_request_for_azure(request_data)
    
    print("\n清理后请求:")
    print(json.dumps(cleaned, ensure_ascii=False, indent=2))
    
    # 验证结果 - Azure 要求：最后一条 assistant 消息没有有效 thinking 块开头时，禁用 thinking
    has_thinking_param = "thinking" in cleaned
    has_thinking_blocks = False
    
    for msg in cleaned.get("messages", []):
        if isinstance(msg.get("content"), list):
            for block in msg["content"]:
                if isinstance(block, dict):
                    if block.get("type") == "thinking":
                        has_thinking_blocks = True
    
    print(f"\n验证结果:")
    print(f"- thinking 参数: {'保持启用' if has_thinking_param else '已移除'}")
    print(f"- thinking 块: {'仍存在' if has_thinking_blocks else '已移除'}")
    
    # 断言：因为最后一条 assistant 消息没有有效 thinking 块开头，thinking 被禁用
    assert not has_thinking_param, "thinking 参数应该被移除（最后一条 assistant 消息没有有效 thinking 块开头）"
    assert not has_thinking_blocks, "thinking 块应该被移除"
    print("✅ 测试通过: thinking 被正确禁用，thinking 块已移除")
    
    print("\n" + "="*60)
    
    # 测试用例 2: thinking 已被禁用，但历史中有 thinking 块
    request_data_2 = {
        "model": "claude-haiku-4-5",
        "messages": [
            {
                "role": "user",
                "content": "Hello"
            },
            {
                "role": "assistant", 
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "我需要思考这个问题",
                        "signature": "some_signature"
                    },
                    {
                        "type": "text",
                        "text": "Hello! 我在这里帮你。"
                    }
                ]
            }
        ]
    }
    
    print("=== 测试用例 2: thinking 已禁用但历史中有 thinking 块 ===")
    print("原始请求:")
    print(json.dumps(request_data_2, ensure_ascii=False, indent=2))
    
    # 清理请求
    cleaned_2 = _clean_claude_request_for_azure(request_data_2)
    
    print("\n清理后请求:")
    print(json.dumps(cleaned_2, ensure_ascii=False, indent=2))
    
    # 验证结果
    has_thinking_blocks_2 = False
    
    for msg in cleaned_2.get("messages", []):
        if isinstance(msg.get("content"), list):
            for block in msg["content"]:
                if isinstance(block, dict) and block.get("type") == "thinking":
                    has_thinking_blocks_2 = True
                    break
    
    print(f"\n验证结果:")
    print(f"- thinking 块: {'已移除' if not has_thinking_blocks_2 else '仍存在'}")
    
    assert not has_thinking_blocks_2, "thinking 块未正确清理"
    print("✅ 测试通过: 所有 thinking 块已正确清理")
    
    print("\n" + "="*60)
    
    # 测试用例 3: thinking 启用且有有效 signature 的 thinking 块
    request_data_3 = {
        "model": "claude-haiku-4-5",
        "thinking": {"type": "enabled"},
        "messages": [
            {
                "role": "user",
                "content": "Hello"
            },
            {
                "role": "assistant", 
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "我需要思考这个问题",
                        "signature": "valid_signature"
                    },
                    {
                        "type": "text",
                        "text": "Hello! 我在这里帮你。"
                    }
                ]
            }
        ]
    }
    
    print("=== 测试用例 3: thinking 启用且有有效 signature 的 thinking 块 ===")
    print("原始请求:")
    print(json.dumps(request_data_3, ensure_ascii=False, indent=2))
    
    # 清理请求
    cleaned_3 = _clean_claude_request_for_azure(request_data_3)
    
    print("\n清理后请求:")
    print(json.dumps(cleaned_3, ensure_ascii=False, indent=2))
    
    # 验证结果
    has_thinking_param_3 = "thinking" in cleaned_3
    has_valid_thinking_block = False
    
    for msg in cleaned_3.get("messages", []):
        if isinstance(msg.get("content"), list):
            for block in msg["content"]:
                if isinstance(block, dict) and block.get("type") == "thinking" and block.get("signature"):
                    has_valid_thinking_block = True
                    break
    
    print(f"\n验证结果:")
    print(f"- thinking 参数: {'保持启用' if has_thinking_param_3 else '已移除'}")
    print(f"- 有效 thinking 块: {'保留' if has_valid_thinking_block else '已移除'}")
    
    assert has_thinking_param_3, "thinking 参数应该保持启用"
    assert has_valid_thinking_block, "有效 thinking 块应该被保留"
    print("✅ 测试通过: thinking 参数保持启用，有效 thinking 块已保留")

def test_content_block_order_preservation():
    """测试内容块顺序保持 - Task 4.1
    
    当最后一条 assistant 消息以有效 thinking 块开头时，
    其他消息中的无效 thinking 块应该被转换为文本，且顺序保持。
    """
    import json
    
    # 测试用例: 多个内容块，最后一条 assistant 消息以有效 thinking 块开头
    # 这样 thinking 功能会保持启用，其他消息中的无效 thinking 块会被转换
    request_data = {
        "model": "claude-haiku-4-5",
        "thinking": {"type": "enabled"},
        "messages": [
            {
                "role": "user",
                "content": "Hello"
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": "First text block"
                    },
                    {
                        "type": "thinking",
                        "thinking": "Middle thinking content"
                        # 无 signature，应该被转换
                    },
                    {
                        "type": "text",
                        "text": "Last text block"
                    }
                ]
            },
            {
                "role": "user",
                "content": "Continue"
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "Valid thinking",
                        "signature": "valid_sig"  # 有效 signature
                    },
                    {
                        "type": "text",
                        "text": "Final response"
                    }
                ]
            }
        ]
    }
    
    cleaned = _clean_claude_request_for_azure(request_data)
    
    # 验证 thinking 参数保持启用（因为最后一条 assistant 消息以有效 thinking 块开头）
    assert "thinking" in cleaned, "thinking 参数应该保持启用"
    
    # 验证第一条 assistant 消息的内容块顺序
    first_assistant_content = cleaned["messages"][1]["content"]
    
    assert len(first_assistant_content) == 3, f"应该有 3 个内容块，实际有 {len(first_assistant_content)}"
    
    # 第一个块应该是原始文本
    assert first_assistant_content[0]["type"] == "text"
    assert first_assistant_content[0]["text"] == "First text block"
    
    # 第二个块应该是转换后的 thinking 文本
    assert first_assistant_content[1]["type"] == "text"
    assert "<previous_thinking>" in first_assistant_content[1]["text"]
    assert "Middle thinking content" in first_assistant_content[1]["text"]
    
    # 第三个块应该是原始文本
    assert first_assistant_content[2]["type"] == "text"
    assert first_assistant_content[2]["text"] == "Last text block"
    
    # 验证最后一条 assistant 消息的有效 thinking 块被保留
    last_assistant_content = cleaned["messages"][3]["content"]
    assert last_assistant_content[0]["type"] == "thinking"
    assert last_assistant_content[0].get("signature") == "valid_sig"
    
    print("✅ 测试通过: 内容块顺序正确保持")


def test_empty_message_handling():
    """测试空消息处理 - Task 4.2"""
    import json
    
    # 测试用例 1: 只有 thinking 块的消息（非最后一条 assistant）
    request_data_1 = {
        "model": "claude-haiku-4-5",
        "messages": [
            {
                "role": "user",
                "content": "Hello"
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "Some thinking"
                        # 无 signature，thinking 未启用时会被移除
                    }
                ]
            },
            {
                "role": "user",
                "content": "Continue"
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": "Final response"
                    }
                ]
            }
        ]
    }
    
    # thinking 未启用，thinking 块会被移除，导致第一个 assistant 消息为空
    cleaned_1 = _clean_claude_request_for_azure(request_data_1)
    
    # 空消息应该被跳过
    assert len(cleaned_1["messages"]) == 3, f"应该有 3 条消息（空消息被跳过），实际有 {len(cleaned_1['messages'])}"
    assert cleaned_1["messages"][0]["role"] == "user"
    assert cleaned_1["messages"][1]["role"] == "user"
    assert cleaned_1["messages"][2]["role"] == "assistant"
    
    print("✅ 测试通过: 空消息被正确跳过")
    
    # 测试用例 2: 最后一条 assistant 消息为空（应该保留）
    request_data_2 = {
        "model": "claude-haiku-4-5",
        "messages": [
            {
                "role": "user",
                "content": "Hello"
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "Some thinking"
                    }
                ]
            }
        ]
    }
    
    cleaned_2 = _clean_claude_request_for_azure(request_data_2)
    
    # 最后一条 assistant 消息即使为空也应该保留
    assert len(cleaned_2["messages"]) == 2, f"应该有 2 条消息，实际有 {len(cleaned_2['messages'])}"
    assert cleaned_2["messages"][1]["role"] == "assistant"
    
    print("✅ 测试通过: 最后一条空 assistant 消息被正确保留")


def test_thinking_enabled_converts_to_text():
    """测试 thinking 启用时，无效 thinking 块转换为文本后消息非空 - Task 4.2
    
    当最后一条 assistant 消息以有效 thinking 块开头时，
    其他消息中的无效 thinking 块会被转换为文本。
    """
    import json
    
    # 测试用例: thinking 启用，最后一条 assistant 消息有有效 thinking 块
    # 中间的 assistant 消息只有无效 thinking 块，会被转换为文本
    request_data = {
        "model": "claude-haiku-4-5",
        "thinking": {"type": "enabled"},
        "messages": [
            {
                "role": "user",
                "content": "Hello"
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "Only thinking content"
                        # 无 signature，会被转换为文本
                    }
                ]
            },
            {
                "role": "user",
                "content": "Continue"
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "Valid thinking",
                        "signature": "valid_sig"  # 有效 signature
                    },
                    {
                        "type": "text",
                        "text": "Final response"
                    }
                ]
            }
        ]
    }
    
    cleaned = _clean_claude_request_for_azure(request_data)
    
    # thinking 启用时，无效 thinking 块被转换为文本，消息不为空
    assert len(cleaned["messages"]) == 4, f"应该有 4 条消息，实际有 {len(cleaned['messages'])}"
    
    # 第二条消息应该包含转换后的文本
    assistant_content = cleaned["messages"][1]["content"]
    assert len(assistant_content) == 1
    assert assistant_content[0]["type"] == "text"
    assert "<previous_thinking>" in assistant_content[0]["text"]
    
    print("✅ 测试通过: thinking 启用时，转换后的文本块确保消息非空")


def test_thinking_disabled_removes_all_thinking_content():
    """测试 thinking 禁用时移除所有 thinking 相关块 - Task 5.1
    
    Requirements: 1.3, 3.3
    - 当请求中 thinking 参数为 disabled 或不存在时
    - 移除所有 thinking 和 redacted_thinking 块
    """
    import json
    
    # 测试用例 1: 没有 thinking 参数（默认禁用）
    request_data_1 = {
        "model": "claude-haiku-4-5",
        # 没有 thinking 参数 - 意味着 thinking 被禁用
        "messages": [
            {
                "role": "user",
                "content": "Hello"
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "Some thinking content",
                        "signature": "valid_signature"  # 即使有有效 signature
                    },
                    {
                        "type": "redacted_thinking",
                        "data": "some_encrypted_data"  # 即使有有效 data
                    },
                    {
                        "type": "text",
                        "text": "Hello!"
                    }
                ]
            }
        ]
    }
    
    cleaned_1 = _clean_claude_request_for_azure(request_data_1)
    
    # 验证所有 thinking 和 redacted_thinking 块都被移除
    has_thinking = False
    has_redacted_thinking = False
    
    for msg in cleaned_1.get("messages", []):
        if isinstance(msg.get("content"), list):
            for block in msg["content"]:
                if isinstance(block, dict):
                    if block.get("type") == "thinking":
                        has_thinking = True
                    if block.get("type") == "redacted_thinking":
                        has_redacted_thinking = True
    
    assert not has_thinking, "thinking 块应该在 thinking 禁用时被移除"
    assert not has_redacted_thinking, "redacted_thinking 块应该在 thinking 禁用时被移除"
    print("✅ 测试通过: 没有 thinking 参数时，所有 thinking 内容被移除")
    
    # 测试用例 2: thinking 参数显式设置为非 enabled
    request_data_2 = {
        "model": "claude-haiku-4-5",
        "thinking": {"type": "disabled"},  # 显式禁用
        "messages": [
            {
                "role": "user",
                "content": "Hello"
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "Some thinking content",
                        "signature": "valid_signature"
                    },
                    {
                        "type": "redacted_thinking",
                        "data": "some_encrypted_data"
                    },
                    {
                        "type": "text",
                        "text": "Hello!"
                    }
                ]
            }
        ]
    }
    
    cleaned_2 = _clean_claude_request_for_azure(request_data_2)
    
    has_thinking_2 = False
    has_redacted_thinking_2 = False
    
    for msg in cleaned_2.get("messages", []):
        if isinstance(msg.get("content"), list):
            for block in msg["content"]:
                if isinstance(block, dict):
                    if block.get("type") == "thinking":
                        has_thinking_2 = True
                    if block.get("type") == "redacted_thinking":
                        has_redacted_thinking_2 = True
    
    assert not has_thinking_2, "thinking 块应该在 thinking 显式禁用时被移除"
    assert not has_redacted_thinking_2, "redacted_thinking 块应该在 thinking 显式禁用时被移除"
    print("✅ 测试通过: thinking 显式禁用时，所有 thinking 内容被移除")
    
    # 测试用例 3: 多条消息中的 thinking 块都应该被移除
    request_data_3 = {
        "model": "claude-haiku-4-5",
        "messages": [
            {
                "role": "user",
                "content": "First question"
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "First thinking"
                    },
                    {
                        "type": "text",
                        "text": "First answer"
                    }
                ]
            },
            {
                "role": "user",
                "content": "Second question"
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "Second thinking",
                        "signature": "sig"
                    },
                    {
                        "type": "redacted_thinking",
                        "data": "data"
                    },
                    {
                        "type": "text",
                        "text": "Second answer"
                    }
                ]
            }
        ]
    }
    
    cleaned_3 = _clean_claude_request_for_azure(request_data_3)
    
    thinking_count = 0
    redacted_thinking_count = 0
    
    for msg in cleaned_3.get("messages", []):
        if isinstance(msg.get("content"), list):
            for block in msg["content"]:
                if isinstance(block, dict):
                    if block.get("type") == "thinking":
                        thinking_count += 1
                    if block.get("type") == "redacted_thinking":
                        redacted_thinking_count += 1
    
    assert thinking_count == 0, f"所有 thinking 块应该被移除，但发现 {thinking_count} 个"
    assert redacted_thinking_count == 0, f"所有 redacted_thinking 块应该被移除，但发现 {redacted_thinking_count} 个"
    print("✅ 测试通过: 多条消息中的所有 thinking 内容都被移除")


def test_backward_compatibility_no_thinking_blocks():
    """测试向后兼容性：无 thinking 块请求的处理 - Task 6.1
    
    Requirements: 5.1
    - 当请求中没有 thinking 块时，处理行为应与当前实现一致
    - 确保普通请求不受影响
    """
    import json
    
    # 测试用例 1: 简单文本消息，无 thinking 块
    request_data_1 = {
        "model": "claude-haiku-4-5",
        "messages": [
            {
                "role": "user",
                "content": "Hello, how are you?"
            },
            {
                "role": "assistant",
                "content": "I'm doing well, thank you!"
            },
            {
                "role": "user",
                "content": "What's the weather like?"
            }
        ]
    }
    
    cleaned_1 = _clean_claude_request_for_azure(request_data_1)
    
    # 验证消息结构保持不变
    assert len(cleaned_1["messages"]) == 3, f"消息数量应该保持为 3，实际为 {len(cleaned_1['messages'])}"
    assert cleaned_1["messages"][0]["role"] == "user"
    assert cleaned_1["messages"][0]["content"] == "Hello, how are you?"
    assert cleaned_1["messages"][1]["role"] == "assistant"
    assert cleaned_1["messages"][1]["content"] == "I'm doing well, thank you!"
    assert cleaned_1["messages"][2]["role"] == "user"
    assert cleaned_1["messages"][2]["content"] == "What's the weather like?"
    
    print("✅ 测试通过: 简单文本消息处理正确")
    
    # 测试用例 2: 带有列表格式 content 的消息，无 thinking 块
    request_data_2 = {
        "model": "claude-haiku-4-5",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "What's in this image?"
                    },
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "base64data..."
                        }
                    }
                ]
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": "I can see a beautiful landscape."
                    }
                ]
            }
        ]
    }
    
    cleaned_2 = _clean_claude_request_for_azure(request_data_2)
    
    # 验证消息结构保持不变
    assert len(cleaned_2["messages"]) == 2
    assert len(cleaned_2["messages"][0]["content"]) == 2
    assert cleaned_2["messages"][0]["content"][0]["type"] == "text"
    assert cleaned_2["messages"][0]["content"][1]["type"] == "image"
    assert len(cleaned_2["messages"][1]["content"]) == 1
    assert cleaned_2["messages"][1]["content"][0]["type"] == "text"
    
    print("✅ 测试通过: 列表格式 content 消息处理正确")
    
    # 测试用例 3: 带有工具调用的消息，无 thinking 块
    request_data_3 = {
        "model": "claude-haiku-4-5",
        "messages": [
            {
                "role": "user",
                "content": "What's the weather in Tokyo?"
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool_123",
                        "name": "get_weather",
                        "input": {"location": "Tokyo"}
                    }
                ]
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool_123",
                        "content": "Sunny, 25°C"
                    }
                ]
            }
        ]
    }
    
    cleaned_3 = _clean_claude_request_for_azure(request_data_3)
    
    # 验证消息结构保持不变
    assert len(cleaned_3["messages"]) == 3
    assert cleaned_3["messages"][1]["content"][0]["type"] == "tool_use"
    assert cleaned_3["messages"][2]["content"][0]["type"] == "tool_result"
    
    print("✅ 测试通过: 工具调用消息处理正确")
    
    # 测试用例 4: 带有 thinking 参数但无 thinking 块的请求
    request_data_4 = {
        "model": "claude-haiku-4-5",
        "thinking": {"type": "enabled"},
        "messages": [
            {
                "role": "user",
                "content": "Hello"
            }
        ]
    }
    
    cleaned_4 = _clean_claude_request_for_azure(request_data_4)
    
    # thinking 参数应该保持
    assert "thinking" in cleaned_4, "thinking 参数应该保持"
    assert cleaned_4["thinking"]["type"] == "enabled"
    assert len(cleaned_4["messages"]) == 1
    
    print("✅ 测试通过: 带 thinking 参数但无 thinking 块的请求处理正确")
    
    # 测试用例 5: 不支持的字段应该被移除
    request_data_5 = {
        "model": "claude-haiku-4-5",
        "context_management": {"enabled": True},
        "betas": ["some-beta"],
        "anthropic_beta": "some-beta",
        "messages": [
            {
                "role": "user",
                "content": "Hello"
            }
        ]
    }
    
    cleaned_5 = _clean_claude_request_for_azure(request_data_5)
    
    # 不支持的字段应该被移除
    assert "context_management" not in cleaned_5, "context_management 应该被移除"
    assert "betas" not in cleaned_5, "betas 应该被移除"
    assert "anthropic_beta" not in cleaned_5, "anthropic_beta 应该被移除"
    assert len(cleaned_5["messages"]) == 1
    
    print("✅ 测试通过: 不支持的字段被正确移除")


def test_backward_compatibility_all_valid_thinking_blocks():
    """测试向后兼容性：全部有效 thinking 块请求的处理 - Task 6.2
    
    Requirements: 5.2
    - 当请求中所有 thinking 块都有有效 signature 时
    - 这些 thinking 块应该被保留
    - 处理行为应与当前实现一致
    
    注意：Azure 要求最后一条 assistant 消息必须以 thinking 块开头
    """
    import json
    
    # 测试用例 1: 单条消息中的有效 thinking 块（以 thinking 块开头）
    request_data_1 = {
        "model": "claude-haiku-4-5",
        "thinking": {"type": "enabled"},
        "messages": [
            {
                "role": "user",
                "content": "Solve this math problem: 2+2"
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "Let me calculate 2+2. The answer is 4.",
                        "signature": "valid_signature_abc123"
                    },
                    {
                        "type": "text",
                        "text": "The answer is 4."
                    }
                ]
            }
        ]
    }
    
    cleaned_1 = _clean_claude_request_for_azure(request_data_1)
    
    # 验证 thinking 参数保持启用
    assert "thinking" in cleaned_1, "thinking 参数应该保持"
    assert cleaned_1["thinking"]["type"] == "enabled"
    
    # 验证有效 thinking 块被保留
    assistant_content = cleaned_1["messages"][1]["content"]
    thinking_blocks = [b for b in assistant_content if b.get("type") == "thinking"]
    
    assert len(thinking_blocks) == 1, f"应该有 1 个 thinking 块，实际有 {len(thinking_blocks)}"
    assert thinking_blocks[0].get("signature") == "valid_signature_abc123"
    assert thinking_blocks[0].get("thinking") == "Let me calculate 2+2. The answer is 4."
    
    print("✅ 测试通过: 单条消息中的有效 thinking 块被保留")
    
    # 测试用例 2: 多条消息中的有效 thinking 块（都以 thinking 块开头）
    request_data_2 = {
        "model": "claude-haiku-4-5",
        "thinking": {"type": "enabled"},
        "messages": [
            {
                "role": "user",
                "content": "First question"
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "First thinking content",
                        "signature": "sig_1"
                    },
                    {
                        "type": "text",
                        "text": "First answer"
                    }
                ]
            },
            {
                "role": "user",
                "content": "Second question"
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "Second thinking content",
                        "signature": "sig_2"
                    },
                    {
                        "type": "text",
                        "text": "Second answer"
                    }
                ]
            }
        ]
    }
    
    cleaned_2 = _clean_claude_request_for_azure(request_data_2)
    
    # 验证所有有效 thinking 块都被保留
    total_thinking_blocks = 0
    for msg in cleaned_2["messages"]:
        if isinstance(msg.get("content"), list):
            for block in msg["content"]:
                if block.get("type") == "thinking":
                    total_thinking_blocks += 1
                    assert block.get("signature"), "有效 thinking 块应该有 signature"
    
    assert total_thinking_blocks == 2, f"应该有 2 个 thinking 块，实际有 {total_thinking_blocks}"
    
    print("✅ 测试通过: 多条消息中的有效 thinking 块都被保留")
    
    # 测试用例 3: 有效 thinking 块和 redacted_thinking 块混合（以 thinking 块开头）
    request_data_3 = {
        "model": "claude-haiku-4-5",
        "thinking": {"type": "enabled"},
        "messages": [
            {
                "role": "user",
                "content": "Complex question"
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "Visible thinking",
                        "signature": "sig_visible"
                    },
                    {
                        "type": "redacted_thinking",
                        "data": "encrypted_thinking_data"
                    },
                    {
                        "type": "text",
                        "text": "My answer"
                    }
                ]
            }
        ]
    }
    
    cleaned_3 = _clean_claude_request_for_azure(request_data_3)
    
    # 验证有效 thinking 块和 redacted_thinking 块都被保留
    assistant_content = cleaned_3["messages"][1]["content"]
    
    thinking_blocks = [b for b in assistant_content if b.get("type") == "thinking"]
    redacted_blocks = [b for b in assistant_content if b.get("type") == "redacted_thinking"]
    
    assert len(thinking_blocks) == 1, "有效 thinking 块应该被保留"
    assert len(redacted_blocks) == 1, "有效 redacted_thinking 块应该被保留"
    assert redacted_blocks[0].get("data") == "encrypted_thinking_data"
    
    print("✅ 测试通过: 有效 thinking 块和 redacted_thinking 块混合处理正确")


print("\n🎉 所有测试通过！thinking 块清理修复有效。")

if __name__ == "__main__":
    try:
        test_thinking_cleanup()
        test_content_block_order_preservation()
        test_empty_message_handling()
        test_thinking_enabled_converts_to_text()
        test_thinking_disabled_removes_all_thinking_content()
        test_backward_compatibility_no_thinking_blocks()
        test_backward_compatibility_all_valid_thinking_blocks()
        print("\n🎉 所有测试通过！thinking 块清理修复有效。")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n💥 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 测试出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)