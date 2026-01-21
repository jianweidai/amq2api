"""
Web Search 功能测试
"""
import pytest
from src.amazonq.websearch import (
    has_web_search_tool,
    extract_search_query,
    create_mcp_request,
    parse_search_results,
    generate_search_summary,
    WebSearchResults,
    WebSearchResult
)


class TestWebSearchDetection:
    """测试 Web Search 请求检测"""
    
    def test_has_web_search_tool_single(self):
        """测试单个 web_search 工具的检测"""
        request_data = {
            "model": "claude-sonnet-4",
            "messages": [{"role": "user", "content": "test"}],
            "tools": [{"name": "web_search", "description": "Search the web"}]
        }
        assert has_web_search_tool(request_data) is True
    
    def test_has_web_search_tool_multiple(self):
        """测试多个工具时不应被识别为 web_search 请求"""
        request_data = {
            "model": "claude-sonnet-4",
            "messages": [{"role": "user", "content": "test"}],
            "tools": [
                {"name": "web_search", "description": "Search the web"},
                {"name": "other_tool", "description": "Other tool"}
            ]
        }
        assert has_web_search_tool(request_data) is False
    
    def test_has_web_search_tool_no_tools(self):
        """测试没有工具时返回 False"""
        request_data = {
            "model": "claude-sonnet-4",
            "messages": [{"role": "user", "content": "test"}]
        }
        assert has_web_search_tool(request_data) is False
    
    def test_has_web_search_tool_wrong_name(self):
        """测试工具名称不匹配时返回 False"""
        request_data = {
            "model": "claude-sonnet-4",
            "messages": [{"role": "user", "content": "test"}],
            "tools": [{"name": "other_search", "description": "Other search"}]
        }
        assert has_web_search_tool(request_data) is False


class TestQueryExtraction:
    """测试搜索查询提取"""
    
    def test_extract_query_with_prefix(self):
        """测试带前缀的查询提取"""
        request_data = {
            "messages": [{
                "role": "user",
                "content": [{
                    "type": "text",
                    "text": "Perform a web search for the query: rust latest version 2026"
                }]
            }]
        }
        query = extract_search_query(request_data)
        assert query == "rust latest version 2026"
    
    def test_extract_query_plain_text(self):
        """测试纯文本查询提取"""
        request_data = {
            "messages": [{
                "role": "user",
                "content": "What is the weather today?"
            }]
        }
        query = extract_search_query(request_data)
        assert query == "What is the weather today?"
    
    def test_extract_query_structured_content(self):
        """测试结构化内容的查询提取"""
        request_data = {
            "messages": [{
                "role": "user",
                "content": [{
                    "type": "text",
                    "text": "Python 3.12 new features"
                }]
            }]
        }
        query = extract_search_query(request_data)
        assert query == "Python 3.12 new features"
    
    def test_extract_query_empty_messages(self):
        """测试空消息列表"""
        request_data = {"messages": []}
        query = extract_search_query(request_data)
        assert query is None
    
    def test_extract_query_no_text(self):
        """测试没有文本内容的消息"""
        request_data = {
            "messages": [{
                "role": "user",
                "content": [{"type": "image", "source": {}}]
            }]
        }
        query = extract_search_query(request_data)
        assert query is None


class TestMCPRequest:
    """测试 MCP 请求构建"""
    
    def test_create_mcp_request(self):
        """测试 MCP 请求创建"""
        query = "test query"
        tool_use_id, mcp_request = create_mcp_request(query)
        
        # 验证 tool_use_id 格式
        assert tool_use_id.startswith("srvtoolu_")
        assert len(tool_use_id) == 41  # "srvtoolu_" (9) + 32 hex chars
        
        # 验证 MCP 请求格式
        assert mcp_request["jsonrpc"] == "2.0"
        assert mcp_request["method"] == "tools/call"
        assert mcp_request["params"]["name"] == "web_search"
        assert mcp_request["params"]["arguments"]["query"] == query
        
        # 验证 ID 格式
        request_id = mcp_request["id"]
        assert request_id.startswith("web_search_tooluse_")
        parts = request_id.split("_")
        assert len(parts) >= 4  # web, search, tooluse, random, timestamp, random
    
    def test_create_mcp_request_unique_ids(self):
        """测试每次生成的 ID 都是唯一的"""
        _, req1 = create_mcp_request("test")
        _, req2 = create_mcp_request("test")
        
        assert req1["id"] != req2["id"]


class TestResponseParsing:
    """测试响应解析"""
    
    def test_parse_search_results_success(self):
        """测试成功解析搜索结果"""
        mcp_response = {
            "result": {
                "content": [{
                    "type": "text",
                    "text": '{"results":[{"title":"Test","url":"https://example.com","snippet":"Test snippet"}],"totalResults":1}'
                }]
            }
        }
        
        results = parse_search_results(mcp_response)
        assert results is not None
        assert len(results.results) == 1
        assert results.results[0].title == "Test"
        assert results.results[0].url == "https://example.com"
        assert results.results[0].snippet == "Test snippet"
    
    def test_parse_search_results_no_result(self):
        """测试没有 result 字段"""
        mcp_response = {"error": "some error"}
        results = parse_search_results(mcp_response)
        assert results is None
    
    def test_parse_search_results_invalid_json(self):
        """测试无效的 JSON"""
        mcp_response = {
            "result": {
                "content": [{
                    "type": "text",
                    "text": "invalid json"
                }]
            }
        }
        results = parse_search_results(mcp_response)
        assert results is None
    
    def test_parse_search_results_wrong_content_type(self):
        """测试错误的内容类型"""
        mcp_response = {
            "result": {
                "content": [{
                    "type": "image",
                    "data": "..."
                }]
            }
        }
        results = parse_search_results(mcp_response)
        assert results is None


class TestSummaryGeneration:
    """测试搜索结果摘要生成"""
    
    def test_generate_summary_with_results(self):
        """测试有结果时的摘要生成"""
        results = WebSearchResults(
            results=[
                WebSearchResult(
                    title="Test Result",
                    url="https://example.com",
                    snippet="This is a test snippet"
                )
            ],
            total_results=1,
            query="test"
        )
        
        summary = generate_search_summary("test", results)
        
        assert "test" in summary
        assert "Test Result" in summary
        assert "https://example.com" in summary
        assert "This is a test snippet" in summary
    
    def test_generate_summary_no_results(self):
        """测试没有结果时的摘要生成"""
        summary = generate_search_summary("test", None)
        
        assert "test" in summary
        assert "No results found" in summary
    
    def test_generate_summary_truncate_long_snippet(self):
        """测试长摘要的截断"""
        long_snippet = "a" * 300
        results = WebSearchResults(
            results=[
                WebSearchResult(
                    title="Test",
                    url="https://example.com",
                    snippet=long_snippet
                )
            ]
        )
        
        summary = generate_search_summary("test", results)
        
        # 应该被截断到 200 字符 + "..."
        assert "..." in summary
        assert len(summary) < len(long_snippet) + 200


@pytest.mark.asyncio
class TestSSEGeneration:
    """测试 SSE 事件生成"""
    
    async def test_generate_sse_events(self):
        """测试 SSE 事件序列生成"""
        from src.amazonq.websearch import generate_websearch_sse_events
        
        results = WebSearchResults(
            results=[
                WebSearchResult(
                    title="Test",
                    url="https://example.com",
                    snippet="Test snippet"
                )
            ]
        )
        
        events = []
        async for event in generate_websearch_sse_events(
            model="claude-sonnet-4.5",
            query="test",
            tool_use_id="test_id",
            search_results=results,
            input_tokens=10
        ):
            events.append(event)
        
        # 验证事件序列
        assert len(events) > 0
        
        # 检查关键事件
        event_types = [e for e in events if "event:" in e]
        assert any("message_start" in e for e in event_types)
        assert any("content_block_start" in e for e in event_types)
        assert any("content_block_delta" in e for e in event_types)
        assert any("content_block_stop" in e for e in event_types)
        assert any("message_stop" in e for e in event_types)
    
    async def test_generate_sse_events_no_results(self):
        """测试没有搜索结果时的 SSE 生成"""
        from src.amazonq.websearch import generate_websearch_sse_events
        
        events = []
        async for event in generate_websearch_sse_events(
            model="claude-sonnet-4.5",
            query="test",
            tool_use_id="test_id",
            search_results=None,
            input_tokens=10
        ):
            events.append(event)
        
        # 即使没有结果，也应该生成完整的事件序列
        assert len(events) > 0
        
        # 检查是否包含 "No results found"
        all_events_text = "".join(events)
        assert "No results found" in all_events_text
