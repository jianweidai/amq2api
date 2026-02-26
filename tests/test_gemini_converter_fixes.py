"""
测试 Gemini converter 的 bug fix：
1. tool_id_to_name 映射（tool_result 缺少 name 时从历史消息查找）
2. maxOutputTokens 包含 thinking budget
3. exclusiveMaximum/Minimum 字段支持
4. thinking-only assistant 消息自动补充文本
"""
import pytest
from src.models import ClaudeRequest, ClaudeMessage
from src.gemini.converter import convert_claude_to_gemini, clean_json_schema


# ── 1. tool_id_to_name 映射 ──────────────────────────────────────────────────

def test_tool_result_name_resolved_from_history():
    """tool_result 没有 name 字段时，应从历史 tool_use 消息中查找"""
    messages = [
        ClaudeMessage(role="assistant", content=[
            {"type": "tool_use", "id": "tool_abc", "name": "read_file", "input": {"path": "/tmp/x"}}
        ]),
        ClaudeMessage(role="user", content=[
            # 故意不带 name 字段
            {"type": "tool_result", "tool_use_id": "tool_abc", "content": "file content"}
        ]),
    ]
    req = ClaudeRequest(model="claude-sonnet-4-5", messages=messages, stream=True)
    result = convert_claude_to_gemini(req, project="test-project")

    contents = result["request"]["contents"]
    # 找到 functionResponse 的那条消息
    func_resp = None
    for c in contents:
        for part in c.get("parts", []):
            if "functionResponse" in part:
                func_resp = part["functionResponse"]
    assert func_resp is not None, "应该有 functionResponse"
    assert func_resp["name"] == "read_file", f"name 应为 read_file，实际: {func_resp['name']}"


def test_tool_result_name_uses_own_name_first():
    """tool_result 自带 name 时，优先使用自己的 name"""
    messages = [
        ClaudeMessage(role="assistant", content=[
            {"type": "tool_use", "id": "tool_xyz", "name": "write_file", "input": {}}
        ]),
        ClaudeMessage(role="user", content=[
            {"type": "tool_result", "tool_use_id": "tool_xyz", "name": "custom_name", "content": "ok"}
        ]),
    ]
    req = ClaudeRequest(model="claude-sonnet-4-5", messages=messages, stream=True)
    result = convert_claude_to_gemini(req, project="test-project")

    contents = result["request"]["contents"]
    func_resp = None
    for c in contents:
        for part in c.get("parts", []):
            if "functionResponse" in part:
                func_resp = part["functionResponse"]
    assert func_resp is not None
    assert func_resp["name"] == "custom_name"


# ── 2. maxOutputTokens 包含 thinking budget ──────────────────────────────────

def test_max_output_tokens_includes_thinking_budget():
    """maxOutputTokens 应该 >= max_tokens 且 >= thinking budget"""
    messages = [ClaudeMessage(role="user", content="hello")]
    req = ClaudeRequest(
        model="claude-sonnet-4-5-thinking",
        messages=messages,
        max_tokens=1000,
        thinking={"type": "enabled", "budget_tokens": 5000},
        stream=True
    )
    result = convert_claude_to_gemini(req, project="test-project")
    max_output = result["request"]["generationConfig"]["maxOutputTokens"]
    # 应该是 max(1000, 5000) + 1 = 5001
    assert max_output >= 5001, f"maxOutputTokens 应 >= 5001，实际: {max_output}"


def test_max_output_tokens_no_thinking():
    """没有 thinking 时，maxOutputTokens 应该是 max_tokens + 1"""
    messages = [ClaudeMessage(role="user", content="hello")]
    req = ClaudeRequest(
        model="claude-sonnet-4-5",
        messages=messages,
        max_tokens=2000,
        thinking=False,
        stream=True
    )
    result = convert_claude_to_gemini(req, project="test-project")
    max_output = result["request"]["generationConfig"]["maxOutputTokens"]
    # thinking budget 为 0，所以 max(2000, 0) + 1 = 2001
    assert max_output == 2001, f"maxOutputTokens 应为 2001，实际: {max_output}"


# ── 3. exclusiveMaximum/Minimum 字段支持 ─────────────────────────────────────

def test_clean_json_schema_removes_exclusive_bounds():
    """clean_json_schema 应该移除 exclusiveMaximum 和 exclusiveMinimum"""
    schema = {
        "type": "number",
        "exclusiveMaximum": 100,
        "exclusiveMinimum": 0,
        "description": "a number"
    }
    cleaned = clean_json_schema(schema)
    assert "exclusiveMaximum" not in cleaned, "exclusiveMaximum 应被移除"
    assert "exclusiveMinimum" not in cleaned, "exclusiveMinimum 应被移除"
    # 验证信息应追加到 description
    assert "exclusiveMaximum" in cleaned.get("description", ""), "验证信息应追加到 description"


def test_clean_json_schema_keeps_other_fields():
    """clean_json_schema 不应影响其他字段"""
    schema = {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "minimum": 1, "maximum": 10}
        },
        "required": ["count"]
    }
    cleaned = clean_json_schema(schema)
    assert cleaned["type"] == "object"
    assert "required" in cleaned
    assert "count" in cleaned["properties"]
    assert "minimum" not in cleaned["properties"]["count"]
    assert "maximum" not in cleaned["properties"]["count"]


# ── 4. thinking-only assistant 消息自动补充文本 ───────────────────────────────

def test_thinking_only_message_gets_placeholder_text():
    """只有 thinking 没有 text 的 assistant 消息，应自动补充文本避免 Gemini 报错"""
    messages = [
        ClaudeMessage(role="user", content="请思考一下"),
        ClaudeMessage(role="assistant", content=[
            {"type": "thinking", "thinking": "let me think...", "signature": "sig123"}
            # 故意没有 text block
        ]),
        ClaudeMessage(role="user", content="继续"),
    ]
    req = ClaudeRequest(model="claude-sonnet-4-5-thinking", messages=messages, stream=True)
    result = convert_claude_to_gemini(req, project="test-project")

    contents = result["request"]["contents"]
    # 找到 role=model 的消息
    model_msgs = [c for c in contents if c["role"] == "model"]
    assert len(model_msgs) >= 1

    # 该消息的 parts 中应该有非 thought 的 text part
    model_parts = model_msgs[0]["parts"]
    has_non_thought_text = any(
        "text" in p and not p.get("thought", False)
        for p in model_parts
    )
    assert has_non_thought_text, "thinking-only 消息应自动补充文本 part"


def test_normal_assistant_message_unchanged():
    """正常的 assistant 消息（有 text）不应被修改"""
    messages = [
        ClaudeMessage(role="user", content="hello"),
        ClaudeMessage(role="assistant", content=[
            {"type": "thinking", "thinking": "thinking...", "signature": "sig"},
            {"type": "text", "text": "Here is my answer"}
        ]),
    ]
    req = ClaudeRequest(model="claude-sonnet-4-5-thinking", messages=messages, stream=True)
    result = convert_claude_to_gemini(req, project="test-project")

    contents = result["request"]["contents"]
    model_msgs = [c for c in contents if c["role"] == "model"]
    assert len(model_msgs) >= 1

    # 找到 text 内容
    text_parts = [
        p for p in model_msgs[0]["parts"]
        if "text" in p and not p.get("thought", False)
    ]
    # 应该只有原始的 "Here is my answer"，不应有额外补充
    assert any(p.get("text") == "Here is my answer" for p in text_parts)


# ── 5. 空 parts 消息跳过 ──────────────────────────────────────────────────────

def test_empty_content_message_skipped():
    """空 content 的消息应被跳过，不加入 contents"""
    messages = [
        ClaudeMessage(role="user", content="hello"),
        ClaudeMessage(role="assistant", content=[]),  # 空 content
        ClaudeMessage(role="user", content="world"),
    ]
    req = ClaudeRequest(model="claude-sonnet-4-5", messages=messages, stream=True)
    result = convert_claude_to_gemini(req, project="test-project")

    contents = result["request"]["contents"]
    # 空消息应被跳过，只有 2 条
    assert len(contents) == 2, f"应有 2 条消息，实际: {len(contents)}"
