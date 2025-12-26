"""
测试 parser.py 中 SSE 事件构建函数的缓存统计支持
"""
import json
import pytest
from src.amazonq.parser import build_claude_message_start_event, build_claude_message_stop_event


def parse_sse_event(event_str: str) -> list[dict]:
    """解析 SSE 事件字符串，返回数据对象列表"""
    results = []
    lines = event_str.strip().split('\n')
    for line in lines:
        if line.startswith('data:'):
            data = json.loads(line[5:].strip())
            results.append(data)
    return results


class TestBuildClaudeMessageStartEvent:
    """测试 build_claude_message_start_event 函数"""
    
    def test_includes_cache_creation_input_tokens(self):
        """验证 message_start 事件包含 cache_creation_input_tokens 字段"""
        event = build_claude_message_start_event(
            conversation_id='test-123',
            model='claude-sonnet-4.5',
            input_tokens=100,
            cache_creation_input_tokens=500,
            cache_read_input_tokens=0
        )
        data_list = parse_sse_event(event)
        assert len(data_list) == 1
        usage = data_list[0]['message']['usage']
        assert 'cache_creation_input_tokens' in usage
        assert usage['cache_creation_input_tokens'] == 500
    
    def test_includes_cache_read_input_tokens(self):
        """验证 message_start 事件包含 cache_read_input_tokens 字段"""
        event = build_claude_message_start_event(
            conversation_id='test-123',
            model='claude-sonnet-4.5',
            input_tokens=100,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=300
        )
        data_list = parse_sse_event(event)
        usage = data_list[0]['message']['usage']
        assert 'cache_read_input_tokens' in usage
        assert usage['cache_read_input_tokens'] == 300
    
    def test_backward_compatibility(self):
        """验证不传缓存参数时默认为 0"""
        event = build_claude_message_start_event(
            conversation_id='test-456',
            model='claude-sonnet-4.5',
            input_tokens=100
        )
        data_list = parse_sse_event(event)
        usage = data_list[0]['message']['usage']
        assert usage['cache_creation_input_tokens'] == 0
        assert usage['cache_read_input_tokens'] == 0
    
    def test_usage_object_completeness(self):
        """验证 usage 对象包含所有必需字段"""
        event = build_claude_message_start_event(
            conversation_id='test-789',
            model='claude-sonnet-4.5',
            input_tokens=100,
            cache_creation_input_tokens=500,
            cache_read_input_tokens=200
        )
        data_list = parse_sse_event(event)
        usage = data_list[0]['message']['usage']
        assert 'input_tokens' in usage
        assert 'output_tokens' in usage
        assert 'cache_creation_input_tokens' in usage
        assert 'cache_read_input_tokens' in usage


class TestBuildClaudeMessageStopEvent:
    """测试 build_claude_message_stop_event 函数"""
    
    def test_includes_cache_creation_input_tokens(self):
        """验证 message_delta 事件包含 cache_creation_input_tokens 字段"""
        event = build_claude_message_stop_event(
            input_tokens=100,
            output_tokens=50,
            stop_reason='end_turn',
            cache_creation_input_tokens=500,
            cache_read_input_tokens=0
        )
        data_list = parse_sse_event(event)
        # 第一个是 message_delta，第二个是 message_stop
        message_delta = next(d for d in data_list if d.get('type') == 'message_delta')
        usage = message_delta['usage']
        assert 'cache_creation_input_tokens' in usage
        assert usage['cache_creation_input_tokens'] == 500
    
    def test_includes_cache_read_input_tokens(self):
        """验证 message_delta 事件包含 cache_read_input_tokens 字段"""
        event = build_claude_message_stop_event(
            input_tokens=100,
            output_tokens=50,
            stop_reason='end_turn',
            cache_creation_input_tokens=0,
            cache_read_input_tokens=300
        )
        data_list = parse_sse_event(event)
        message_delta = next(d for d in data_list if d.get('type') == 'message_delta')
        usage = message_delta['usage']
        assert 'cache_read_input_tokens' in usage
        assert usage['cache_read_input_tokens'] == 300
    
    def test_backward_compatibility(self):
        """验证不传缓存参数时默认为 0"""
        event = build_claude_message_stop_event(
            input_tokens=100,
            output_tokens=50,
            stop_reason='end_turn'
        )
        data_list = parse_sse_event(event)
        message_delta = next(d for d in data_list if d.get('type') == 'message_delta')
        usage = message_delta['usage']
        assert usage['cache_creation_input_tokens'] == 0
        assert usage['cache_read_input_tokens'] == 0
    
    def test_usage_object_completeness(self):
        """验证 usage 对象包含所有必需字段"""
        event = build_claude_message_stop_event(
            input_tokens=100,
            output_tokens=50,
            stop_reason='end_turn',
            cache_creation_input_tokens=500,
            cache_read_input_tokens=200
        )
        data_list = parse_sse_event(event)
        message_delta = next(d for d in data_list if d.get('type') == 'message_delta')
        usage = message_delta['usage']
        assert 'input_tokens' in usage
        assert 'output_tokens' in usage
        assert 'cache_creation_input_tokens' in usage
        assert 'cache_read_input_tokens' in usage


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
