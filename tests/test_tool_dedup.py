"""
工具调用去重模块测试
"""
import pytest
import time
import os
from unittest.mock import patch


class TestToolDedupManager:
    """ToolDedupManager 测试"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前重置单例和缓存"""
        import src.processing.tool_dedup as dedup_module
        # 重置单例
        dedup_module._dedup_manager = None
        dedup_module.ToolDedupManager._instance = None
        yield
        # 测试后清理
        dedup_module._dedup_manager = None
        dedup_module.ToolDedupManager._instance = None
    
    def test_singleton_pattern(self):
        """测试单例模式"""
        from src.processing.tool_dedup import get_dedup_manager
        
        manager1 = get_dedup_manager()
        manager2 = get_dedup_manager()
        
        assert manager1 is manager2
    
    def test_is_enabled_default(self):
        """测试默认启用"""
        from src.processing.tool_dedup import get_dedup_manager
        
        manager = get_dedup_manager()
        assert manager.is_enabled() is True
    
    def test_is_enabled_disabled(self):
        """测试禁用功能"""
        from src.processing.tool_dedup import get_dedup_manager
        
        with patch.dict(os.environ, {"ENABLE_TOOL_DEDUP": "false"}):
            manager = get_dedup_manager()
            assert manager.is_enabled() is False
    
    def test_record_first_call(self):
        """测试首次调用记录"""
        from src.processing.tool_dedup import get_dedup_manager
        
        manager = get_dedup_manager()
        
        cache_key, call_count, is_short_dup = manager.record_tool_call(
            "Bash",
            {"command": "git status"}
        )
        
        assert cache_key != ""
        assert call_count == 1
        assert is_short_dup is False
    
    def test_record_duplicate_call(self):
        """测试重复调用检测"""
        from src.processing.tool_dedup import get_dedup_manager
        
        manager = get_dedup_manager()
        
        # 第一次调用
        cache_key1, count1, _ = manager.record_tool_call(
            "Bash",
            {"command": "git status"}
        )
        
        # 第二次相同调用
        cache_key2, count2, is_short_dup = manager.record_tool_call(
            "Bash",
            {"command": "git status"}
        )
        
        assert cache_key1 == cache_key2
        assert count1 == 1
        assert count2 == 2
        assert is_short_dup is True
    
    def test_different_commands_not_duplicate(self):
        """测试不同命令不被视为重复"""
        from src.processing.tool_dedup import get_dedup_manager
        
        manager = get_dedup_manager()
        
        cache_key1, _, _ = manager.record_tool_call(
            "Bash",
            {"command": "git status"}
        )
        
        cache_key2, count2, _ = manager.record_tool_call(
            "Bash",
            {"command": "git log"}
        )
        
        assert cache_key1 != cache_key2
        assert count2 == 1
    
    def test_warning_threshold(self):
        """测试警告阈值"""
        from src.processing.tool_dedup import get_dedup_manager
        
        manager = get_dedup_manager()
        tool_input = {"command": "git status"}
        
        # 第一次调用 - 无警告
        _, count1, is_short1 = manager.record_tool_call("Bash", tool_input)
        warning1 = manager.get_dedup_warning("Bash", tool_input, count1, is_short1)
        assert warning1 is None
        
        # 第二次调用 - 无警告（未超过阈值）
        _, count2, is_short2 = manager.record_tool_call("Bash", tool_input)
        warning2 = manager.get_dedup_warning("Bash", tool_input, count2, is_short2)
        assert warning2 is None
        
        # 第三次调用 - 有警告（超过阈值）
        _, count3, is_short3 = manager.record_tool_call("Bash", tool_input)
        warning3 = manager.get_dedup_warning("Bash", tool_input, count3, is_short3)
        assert warning3 is not None
        assert "DUPLICATE" in warning3
    
    def test_check_and_warn_convenience_method(self):
        """测试便捷方法 check_and_warn"""
        from src.processing.tool_dedup import get_dedup_manager
        
        manager = get_dedup_manager()
        tool_input = {"command": "git status"}
        
        # 多次调用直到触发警告
        for i in range(3):
            cache_key, warning = manager.check_and_warn("Bash", tool_input)
            assert cache_key != ""
            
            if i < 2:
                assert warning is None
            else:
                assert warning is not None
    
    def test_update_result(self):
        """测试更新结果预览"""
        from src.processing.tool_dedup import get_dedup_manager
        
        manager = get_dedup_manager()
        
        cache_key, _, _ = manager.record_tool_call(
            "Bash",
            {"command": "git status"}
        )
        
        manager.update_result(cache_key, "On branch main\nnothing to commit")
        
        # 验证结果已更新
        assert cache_key in manager._cache
        assert "On branch main" in manager._cache[cache_key].result_preview
    
    def test_get_stats(self):
        """测试统计信息"""
        from src.processing.tool_dedup import get_dedup_manager
        
        manager = get_dedup_manager()
        
        # 添加一些调用
        manager.record_tool_call("Bash", {"command": "git status"})
        manager.record_tool_call("Bash", {"command": "git status"})
        manager.record_tool_call("Read", {"file_path": "/test.py"})
        
        stats = manager.get_stats()
        
        assert stats["enabled"] is True
        assert stats["cache_entries"] == 2
        assert stats["total_calls_tracked"] == 3
        assert stats["duplicate_calls"] == 1
        assert "Bash" in stats["by_tool"]
        assert "Read" in stats["by_tool"]
    
    def test_cache_expiration(self):
        """测试缓存过期"""
        from src.processing.tool_dedup import get_dedup_manager
        
        manager = get_dedup_manager()
        # 设置很短的 TTL 用于测试
        original_ttl = manager.ttl
        manager.ttl = 0.1  # 100ms
        
        try:
            cache_key, _, _ = manager.record_tool_call(
                "Bash",
                {"command": "git status"}
            )
            
            assert cache_key in manager._cache
            
            # 等待过期
            time.sleep(0.2)
            
            # 触发清理
            manager._cleanup_expired()
            
            assert cache_key not in manager._cache
        finally:
            manager.ttl = original_ttl
    
    def test_lru_eviction(self):
        """测试 LRU 淘汰"""
        from src.processing.tool_dedup import get_dedup_manager
        
        manager = get_dedup_manager()
        original_max = manager.max_entries
        manager.max_entries = 3
        
        try:
            # 添加 4 个条目
            for i in range(4):
                manager.record_tool_call("Bash", {"command": f"cmd{i}"})
            
            # 应该只保留 3 个
            assert len(manager._cache) == 3
            
            # 最早的应该被淘汰
            stats = manager.get_stats()
            assert stats["cache_entries"] == 3
        finally:
            manager.max_entries = original_max
    
    def test_session_key_tracking(self):
        """测试会话 key 跟踪"""
        from src.processing.tool_dedup import get_dedup_manager
        
        manager = get_dedup_manager()
        
        cache_key, _, _ = manager.record_tool_call(
            "Bash",
            {"command": "git status"},
            session_key="session1"
        )
        
        manager.record_tool_call(
            "Bash",
            {"command": "git status"},
            session_key="session2"
        )
        
        record = manager._cache[cache_key]
        assert "session1" in record.session_keys
        assert "session2" in record.session_keys


class TestConverterIntegration:
    """Converter 集成测试"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前重置单例"""
        import src.processing.tool_dedup as dedup_module
        dedup_module._dedup_manager = None
        dedup_module.ToolDedupManager._instance = None
        yield
        dedup_module._dedup_manager = None
        dedup_module.ToolDedupManager._instance = None
    
    def test_extract_tool_uses_from_messages(self):
        """测试从消息中提取工具调用"""
        from src.amazonq.converter import extract_tool_uses_from_messages
        from unittest.mock import MagicMock
        
        # 创建模拟消息
        messages = [
            MagicMock(role="user", content="Hello"),
            MagicMock(role="assistant", content=[
                {"type": "text", "text": "Let me check"},
                {"type": "tool_use", "id": "tool1", "name": "Bash", "input": {"command": "git status"}}
            ]),
            MagicMock(role="user", content=[
                {"type": "tool_result", "tool_use_id": "tool1", "content": "On branch main"}
            ]),
            MagicMock(role="assistant", content=[
                {"type": "tool_use", "id": "tool2", "name": "Read", "input": {"file_path": "/test.py"}}
            ])
        ]
        
        tool_uses = extract_tool_uses_from_messages(messages)
        
        assert "tool1" in tool_uses
        assert tool_uses["tool1"]["name"] == "Bash"
        assert tool_uses["tool1"]["input"]["command"] == "git status"
        
        assert "tool2" in tool_uses
        assert tool_uses["tool2"]["name"] == "Read"
    
    def test_check_and_inject_dedup_warning(self):
        """测试去重警告注入"""
        from src.amazonq.converter import check_and_inject_dedup_warning
        from src.processing.tool_dedup import get_dedup_manager
        
        manager = get_dedup_manager()
        tool_input = {"command": "git status"}
        original_content = [{"text": "On branch main"}]
        
        # 多次调用直到触发警告
        for i in range(3):
            result = check_and_inject_dedup_warning(
                "Bash", tool_input, [{"text": "On branch main"}]
            )
            
            if i < 2:
                # 前两次不应该有警告
                assert "DUPLICATE" not in result[0]["text"]
            else:
                # 第三次应该有警告
                assert len(result) == 1
                assert "DUPLICATE" in result[0]["text"]
    
    def test_dedup_disabled(self):
        """测试禁用去重时不注入警告"""
        import src.processing.tool_dedup as dedup_module
        
        with patch.dict(os.environ, {"ENABLE_TOOL_DEDUP": "false"}):
            # 重置单例以应用新的环境变量
            dedup_module._dedup_manager = None
            dedup_module.ToolDedupManager._instance = None
            
            from src.amazonq.converter import check_and_inject_dedup_warning
            
            tool_input = {"command": "git status"}
            original_content = [{"text": "On branch main"}]
            
            # 多次调用
            for _ in range(5):
                result = check_and_inject_dedup_warning(
                    "Bash", tool_input, [{"text": "On branch main"}]
                )
                # 禁用时不应该有警告
                assert "DUPLICATE" not in result[0]["text"]
