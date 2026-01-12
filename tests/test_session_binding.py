"""
会话绑定模块测试
测试同一会话的请求是否能绑定到同一个账号
"""
import pytest
import time
from src.auth.session_binding import (
    _compute_session_key,
    _extract_system_text,
    get_bound_account,
    get_bound_conversation_id,
    bind_session_to_account,
    unbind_session,
    get_binding_stats,
    _session_bindings,
    BINDING_TTL
)


class TestExtractSystemText:
    """测试 system prompt 文本提取"""
    
    def test_string_system(self):
        """字符串格式的 system prompt"""
        result = _extract_system_text("You are a helpful assistant.")
        assert result == "You are a helpful assistant."
    
    def test_list_system_with_text_type(self):
        """数组格式的 system prompt（带 type: text）"""
        system = [{"type": "text", "text": "You are a helpful assistant."}]
        result = _extract_system_text(system)
        assert result == "You are a helpful assistant."
    
    def test_list_system_without_type(self):
        """数组格式的 system prompt（不带 type）"""
        system = [{"text": "You are a helpful assistant."}]
        result = _extract_system_text(system)
        assert result == "You are a helpful assistant."
    
    def test_empty_system(self):
        """空的 system prompt"""
        assert _extract_system_text("") == ""
        assert _extract_system_text([]) == ""
        assert _extract_system_text(None) == ""


class TestComputeSessionKey:
    """测试会话 key 计算"""
    
    def test_same_system_prompt_same_key(self):
        """相同 system prompt 应该生成相同的 key"""
        request1 = {
            "model": "claude-sonnet-4.5",
            "system": "You are a helpful assistant.",
            "messages": [{"role": "user", "content": "Hello"}]
        }
        request2 = {
            "model": "claude-sonnet-4.5",
            "system": "You are a helpful assistant.",
            "messages": [{"role": "user", "content": "Hello"}]
        }
        
        key1 = _compute_session_key(request1)
        key2 = _compute_session_key(request2)
        
        assert key1 == key2
    
    def test_different_system_prompt_different_key(self):
        """不同 system prompt 应该生成不同的 key"""
        request1 = {
            "model": "claude-sonnet-4.5",
            "system": "You are a helpful assistant.",
            "messages": [{"role": "user", "content": "Hello"}]
        }
        request2 = {
            "model": "claude-sonnet-4.5",
            "system": "You are a coding assistant.",
            "messages": [{"role": "user", "content": "Hello"}]
        }
        
        key1 = _compute_session_key(request1)
        key2 = _compute_session_key(request2)
        
        assert key1 != key2
    
    def test_same_system_different_messages_same_key(self):
        """相同 system prompt 但不同消息应该生成相同的 key"""
        request1 = {
            "model": "claude-sonnet-4.5",
            "system": "You are a helpful assistant.",
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"}
            ]
        }
        request2 = {
            "model": "claude-sonnet-4.5",
            "system": "You are a helpful assistant.",
            "messages": [
                {"role": "user", "content": "Different message"},
                {"role": "assistant", "content": "Different response"}
            ]
        }
        
        key1 = _compute_session_key(request1)
        key2 = _compute_session_key(request2)
        
        # 只基于 system prompt，消息不同也应该相同
        assert key1 == key2
    
    def test_system_as_list(self):
        """system 为数组格式时也能正确计算 key"""
        request1 = {
            "model": "claude-sonnet-4.5",
            "system": "You are a helpful assistant.",
            "messages": [{"role": "user", "content": "Hello"}]
        }
        request2 = {
            "model": "claude-sonnet-4.5",
            "system": [{"type": "text", "text": "You are a helpful assistant."}],
            "messages": [{"role": "user", "content": "Hello"}]
        }
        
        key1 = _compute_session_key(request1)
        key2 = _compute_session_key(request2)
        
        assert key1 == key2
    
    def test_different_model_same_key(self):
        """不同模型应该生成相同的 key（同一会话的并发请求）"""
        request1 = {
            "model": "claude-sonnet-4.5",
            "system": "You are a helpful assistant.",
            "messages": [{"role": "user", "content": "Hello"}]
        }
        request2 = {
            "model": "claude-opus-4",
            "system": "You are a helpful assistant.",
            "messages": [{"role": "user", "content": "Hello"}]
        }
        
        key1 = _compute_session_key(request1)
        key2 = _compute_session_key(request2)
        
        # 现在不同模型应该生成相同的 key
        assert key1 == key2
    
    def test_truncated_system_same_key(self):
        """system prompt 前 200 字符相同时应该生成相同的 key"""
        base_system = "You are a helpful assistant. " * 10  # 约 300 字符
        
        request1 = {
            "model": "claude-sonnet-4.5",
            "system": base_system + "Extra content 1 that is different",
            "messages": [{"role": "user", "content": "Hello"}]
        }
        request2 = {
            "model": "claude-sonnet-4.5",
            "system": base_system + "Extra content 2 that is also different",
            "messages": [{"role": "user", "content": "Hello"}]
        }
        
        key1 = _compute_session_key(request1)
        key2 = _compute_session_key(request2)
        
        # 前 200 字符相同，应该生成相同的 key
        assert key1 == key2
    
    def test_no_system_uses_first_message(self):
        """没有 system prompt 时使用第一条消息"""
        request1 = {
            "model": "claude-sonnet-4.5",
            "messages": [{"role": "user", "content": "Hello world"}]
        }
        request2 = {
            "model": "claude-sonnet-4.5",
            "messages": [{"role": "user", "content": "Hello world"}]
        }
        
        key1 = _compute_session_key(request1)
        key2 = _compute_session_key(request2)
        
        assert key1 == key2
    
    def test_concurrent_requests_same_key(self):
        """模拟并发请求（相同 system，不同消息）应该生成相同的 key"""
        # 主请求
        main_request = {
            "model": "claude-sonnet-4.5",
            "system": "You are Kiro, an AI assistant.",
            "messages": [{"role": "user", "content": "Help me with coding"}]
        }
        # Token 计数请求（可能消息不同）
        token_request = {
            "model": "claude-sonnet-4.5",
            "system": "You are Kiro, an AI assistant.",
            "messages": [{"role": "user", "content": "Count tokens"}]
        }
        # 预加载请求
        preload_request = {
            "model": "claude-sonnet-4.5",
            "system": "You are Kiro, an AI assistant.",
            "messages": [{"role": "user", "content": "Preload context"}]
        }
        
        key1 = _compute_session_key(main_request)
        key2 = _compute_session_key(token_request)
        key3 = _compute_session_key(preload_request)
        
        # 所有并发请求应该生成相同的 key
        assert key1 == key2 == key3


class TestSessionBinding:
    """测试会话绑定功能"""
    
    def setup_method(self):
        """每个测试前清空绑定缓存"""
        _session_bindings.clear()
    
    def test_bind_and_get(self):
        """测试绑定和获取"""
        request_data = {
            "model": "claude-sonnet-4.5",
            "system": "Test system prompt",
            "messages": [{"role": "user", "content": "Test message"}]
        }
        account_id = "test-account-123"
        
        # 绑定
        session_key, conv_id = bind_session_to_account(request_data, account_id, account_type="amazonq")
        
        # 获取账号
        bound_id = get_bound_account(request_data, account_type="amazonq")
        assert bound_id == account_id
        
        # 获取 conversationId
        bound_conv_id = get_bound_conversation_id(request_data, account_type="amazonq")
        assert bound_conv_id == conv_id
    
    def test_bind_with_custom_conversation_id(self):
        """测试使用自定义 conversationId 绑定"""
        request_data = {
            "model": "claude-sonnet-4.5",
            "system": "Test custom conv id",
            "messages": [{"role": "user", "content": "Test"}]
        }
        account_id = "test-account-456"
        custom_conv_id = "custom-conversation-id-789"
        
        # 绑定时指定 conversationId
        session_key, conv_id = bind_session_to_account(
            request_data, account_id, 
            account_type="amazonq", 
            conversation_id=custom_conv_id
        )
        
        assert conv_id == custom_conv_id
        
        # 获取 conversationId
        bound_conv_id = get_bound_conversation_id(request_data, account_type="amazonq")
        assert bound_conv_id == custom_conv_id
    
    def test_get_nonexistent_binding(self):
        """测试获取不存在的绑定"""
        request_data = {
            "model": "claude-sonnet-4.5",
            "system": "Nonexistent session",
            "messages": [{"role": "user", "content": "Test"}]
        }
        
        bound_id = get_bound_account(request_data, account_type="amazonq")
        assert bound_id is None
        
        bound_conv_id = get_bound_conversation_id(request_data, account_type="amazonq")
        assert bound_conv_id is None
    
    def test_unbind_session(self):
        """测试解除绑定"""
        request_data = {
            "model": "claude-sonnet-4.5",
            "system": "Test unbind",
            "messages": [{"role": "user", "content": "Test"}]
        }
        account_id = "test-account-456"
        
        # 绑定
        bind_session_to_account(request_data, account_id, account_type="amazonq")
        
        # 验证绑定存在
        assert get_bound_account(request_data, account_type="amazonq") == account_id
        
        # 解除绑定
        result = unbind_session(request_data)
        
        assert result is True
        assert get_bound_account(request_data, account_type="amazonq") is None
        assert get_bound_conversation_id(request_data, account_type="amazonq") is None
    
    def test_different_account_types(self):
        """测试不同账号类型的绑定是独立的"""
        request_data = {
            "model": "claude-sonnet-4.5",
            "system": "Test account types",
            "messages": [{"role": "user", "content": "Test"}]
        }
        
        # 绑定到 amazonq
        bind_session_to_account(request_data, "amazonq-account", account_type="amazonq")
        
        # 绑定到 gemini（会覆盖，因为 key 相同但类型不同）
        bind_session_to_account(request_data, "gemini-account", account_type="gemini")
        
        # 获取 amazonq 类型应该返回 None（因为被 gemini 覆盖了）
        # 注意：当前实现中，同一个 session key 只能绑定一个账号
        # 如果需要支持不同类型独立绑定，需要修改 key 计算逻辑
        bound_amazonq = get_bound_account(request_data, account_type="amazonq")
        bound_gemini = get_bound_account(request_data, account_type="gemini")
        
        # 最后绑定的是 gemini，所以 gemini 能获取到
        assert bound_gemini == "gemini-account"
        # amazonq 类型不匹配，返回 None
        assert bound_amazonq is None
    
    def test_binding_stats(self):
        """测试绑定统计"""
        request_data = {
            "model": "claude-sonnet-4.5",
            "system": "Test stats",
            "messages": [{"role": "user", "content": "Test"}]
        }
        
        bind_session_to_account(request_data, "test-account", account_type="amazonq")
        
        stats = get_binding_stats()
        
        assert stats["total_bindings"] == 1
        assert stats["max_bindings"] == 1000
        assert stats["ttl_seconds"] == BINDING_TTL


class TestSessionBindingExpiration:
    """测试会话绑定过期"""
    
    def setup_method(self):
        """每个测试前清空绑定缓存"""
        _session_bindings.clear()
    
    def test_binding_not_expired(self):
        """测试未过期的绑定"""
        request_data = {
            "model": "claude-sonnet-4.5",
            "system": "Test expiration",
            "messages": [{"role": "user", "content": "Test"}]
        }
        account_id = "test-account"
        
        bind_session_to_account(request_data, account_id, account_type="amazonq")
        
        # 立即获取应该成功
        bound_id = get_bound_account(request_data, account_type="amazonq")
        assert bound_id == account_id


class TestMultipleSessionBindings:
    """测试多个会话绑定"""
    
    def setup_method(self):
        """每个测试前清空绑定缓存"""
        _session_bindings.clear()
    
    def test_multiple_sessions(self):
        """测试多个不同会话的绑定"""
        sessions = [
            {
                "request": {
                    "model": "claude-sonnet-4.5",
                    "system": f"Session {i}",
                    "messages": [{"role": "user", "content": "Hello"}]
                },
                "account_id": f"account-{i}"
            }
            for i in range(5)
        ]
        
        # 绑定所有会话
        for session in sessions:
            bind_session_to_account(
                session["request"], 
                session["account_id"], 
                account_type="amazonq"
            )
        
        # 验证所有绑定
        for session in sessions:
            bound_id = get_bound_account(session["request"], account_type="amazonq")
            assert bound_id == session["account_id"]
    
    def test_same_session_rebind(self):
        """测试同一会话重新绑定"""
        request_data = {
            "model": "claude-sonnet-4.5",
            "system": "Test rebind",
            "messages": [{"role": "user", "content": "Test"}]
        }
        
        # 第一次绑定
        bind_session_to_account(request_data, "account-1", account_type="amazonq")
        assert get_bound_account(request_data, account_type="amazonq") == "account-1"
        
        # 重新绑定到不同账号
        bind_session_to_account(request_data, "account-2", account_type="amazonq")
        assert get_bound_account(request_data, account_type="amazonq") == "account-2"
