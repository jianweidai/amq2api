"""
缓存命中率分析工具

用于诊断为什么缓存命中率低，并提供改进建议
"""
import json
from typing import Dict, Any, List
from src.processing.cache_manager import CacheManager


def analyze_request_cacheability(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    分析请求的可缓存性
    
    Returns:
        分析结果，包含：
        - has_cache_control: 是否有 cache_control 标记
        - cacheable_content: 可缓存内容
        - token_count: token 数量
        - issues: 发现的问题列表
        - suggestions: 改进建议列表
    """
    cache_manager = CacheManager()
    issues = []
    suggestions = []
    
    # 1. 检查是否有 cache_control 标记
    has_cache_control = False
    
    # 检查 system prompt
    system = request_data.get("system")
    if system:
        if isinstance(system, str):
            issues.append("system prompt 是字符串格式，不支持 cache_control")
            suggestions.append("将 system prompt 改为数组格式，并添加 cache_control 标记")
        elif isinstance(system, list):
            for block in system:
                if isinstance(block, dict) and block.get("cache_control"):
                    has_cache_control = True
                    break
            if not has_cache_control:
                issues.append("system prompt 是数组格式，但没有 cache_control 标记")
                suggestions.append("在 system prompt 的最后一个 block 添加 cache_control")
    
    # 检查 messages
    messages = request_data.get("messages", [])
    message_with_cache = 0
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            continue
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("cache_control"):
                    has_cache_control = True
                    message_with_cache += 1
                    break
    
    if message_with_cache == 0 and messages:
        issues.append(f"有 {len(messages)} 条消息，但没有任何消息有 cache_control 标记")
        suggestions.append("在历史消息的最后一条添加 cache_control 标记")
    
    # 2. 提取可缓存内容
    cacheable_content, token_count = cache_manager.extract_cacheable_content(request_data)
    
    if not cacheable_content:
        issues.append("没有提取到任何可缓存内容")
        suggestions.append("确保请求中有带 cache_control 标记的内容块")
    elif token_count < 1024:
        issues.append(f"可缓存内容太少（{token_count} tokens），Anthropic 要求至少 1024 tokens")
        suggestions.append("增加可缓存内容的长度，或将多个内容块合并")
    
    # 3. 检查内容变化性
    if cacheable_content:
        # 检查是否包含时间戳、UUID 等动态内容
        dynamic_patterns = [
            ("timestamp", ["timestamp", "time:", "date:", "at 20", "at 19"]),
            ("uuid", ["uuid", "id:", "-", "request_id"]),
            ("random", ["random", "nonce", "session"]),
        ]
        
        for pattern_name, keywords in dynamic_patterns:
            for keyword in keywords:
                if keyword.lower() in cacheable_content.lower():
                    issues.append(f"可缓存内容中可能包含动态数据（{pattern_name}）")
                    suggestions.append(f"移除或标准化动态数据（{pattern_name}），使内容更稳定")
                    break
    
    return {
        "has_cache_control": has_cache_control,
        "cacheable_content_length": len(cacheable_content),
        "token_count": token_count,
        "message_count": len(messages),
        "message_with_cache": message_with_cache,
        "issues": issues,
        "suggestions": suggestions,
        "cacheable_content_preview": cacheable_content[:200] if cacheable_content else ""
    }


def simulate_cache_behavior(requests: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    模拟一系列请求的缓存行为
    
    Args:
        requests: 请求列表
        
    Returns:
        模拟结果，包含命中率、未命中原因等
    """
    cache_manager = CacheManager(ttl_seconds=86400, max_entries=5000)
    
    results = {
        "total_requests": len(requests),
        "hits": 0,
        "misses": 0,
        "no_cacheable_content": 0,
        "cache_keys": [],
        "duplicate_keys": 0,
    }
    
    seen_keys = set()
    
    for i, request_data in enumerate(requests):
        cacheable_content, token_count = cache_manager.extract_cacheable_content(request_data)
        
        if not cacheable_content:
            results["no_cacheable_content"] += 1
            continue
        
        cache_key = cache_manager.calculate_cache_key(cacheable_content)
        
        # 检查是否是重复的键
        if cache_key in seen_keys:
            results["duplicate_keys"] += 1
        else:
            seen_keys.add(cache_key)
        
        # 检查缓存
        cache_result = cache_manager.check_cache(cache_key, token_count, len(cacheable_content))
        
        if cache_result.is_hit:
            results["hits"] += 1
        else:
            results["misses"] += 1
        
        results["cache_keys"].append({
            "request_index": i,
            "key_preview": cache_key[:32],
            "is_hit": cache_result.is_hit,
            "token_count": token_count,
            "content_length": len(cacheable_content)
        })
    
    # 计算命中率
    total_cacheable = results["hits"] + results["misses"]
    if total_cacheable > 0:
        results["hit_rate"] = results["hits"] / total_cacheable
    else:
        results["hit_rate"] = 0.0
    
    # 统计信息
    stats = cache_manager.get_statistics()
    results["cache_stats"] = {
        "hit_count": stats.hit_count,
        "miss_count": stats.miss_count,
        "hit_rate": stats.hit_rate,
        "total_requests": stats.total_requests
    }
    
    return results


def print_analysis_report(analysis: Dict[str, Any]):
    """打印分析报告"""
    print("\n" + "="*80)
    print("缓存可用性分析报告")
    print("="*80)
    
    print(f"\n✓ 是否有 cache_control 标记: {'是' if analysis['has_cache_control'] else '否'}")
    print(f"✓ 可缓存内容长度: {analysis['cacheable_content_length']} 字符")
    print(f"✓ Token 数量: {analysis['token_count']}")
    print(f"✓ 消息总数: {analysis['message_count']}")
    print(f"✓ 带缓存标记的消息: {analysis['message_with_cache']}")
    
    if analysis['cacheable_content_preview']:
        print(f"\n可缓存内容预览:")
        print(f"  {analysis['cacheable_content_preview']}...")
    
    if analysis['issues']:
        print(f"\n⚠️  发现的问题:")
        for i, issue in enumerate(analysis['issues'], 1):
            print(f"  {i}. {issue}")
    
    if analysis['suggestions']:
        print(f"\n💡 改进建议:")
        for i, suggestion in enumerate(analysis['suggestions'], 1):
            print(f"  {i}. {suggestion}")
    
    print("\n" + "="*80)


def print_simulation_report(results: Dict[str, Any]):
    """打印模拟报告"""
    print("\n" + "="*80)
    print("缓存行为模拟报告")
    print("="*80)
    
    print(f"\n总请求数: {results['total_requests']}")
    print(f"缓存命中: {results['hits']}")
    print(f"缓存未命中: {results['misses']}")
    print(f"无可缓存内容: {results['no_cacheable_content']}")
    print(f"重复的缓存键: {results['duplicate_keys']}")
    print(f"命中率: {results['hit_rate']*100:.2f}%")
    
    print(f"\n缓存统计:")
    stats = results['cache_stats']
    print(f"  命中次数: {stats['hit_count']}")
    print(f"  未命中次数: {stats['miss_count']}")
    print(f"  命中率: {stats['hit_rate']*100:.2f}%")
    
    print("\n" + "="*80)


# 示例：分析典型的 Claude API 请求
if __name__ == "__main__":
    # 示例 1: 没有 cache_control 的请求（命中率低）
    print("\n【示例 1】没有 cache_control 的请求")
    request_without_cache = {
        "model": "claude-sonnet-4.5",
        "max_tokens": 1024,
        "system": "You are a helpful assistant.",
        "messages": [
            {"role": "user", "content": "Hello, how are you?"}
        ]
    }
    analysis1 = analyze_request_cacheability(request_without_cache)
    print_analysis_report(analysis1)
    
    # 示例 2: 有 cache_control 的请求（命中率高）
    print("\n\n【示例 2】有 cache_control 的请求")
    request_with_cache = {
        "model": "claude-sonnet-4.5",
        "max_tokens": 1024,
        "system": [
            {
                "type": "text",
                "text": "You are a helpful assistant with access to a large knowledge base.",
                "cache_control": {"type": "ephemeral"}
            }
        ],
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Here is a large document:\n" + "Lorem ipsum " * 500,
                        "cache_control": {"type": "ephemeral"}
                    },
                    {
                        "type": "text",
                        "text": "What is the main topic?"
                    }
                ]
            }
        ]
    }
    analysis2 = analyze_request_cacheability(request_with_cache)
    print_analysis_report(analysis2)
    
    # 示例 3: 模拟多个请求的缓存行为
    print("\n\n【示例 3】模拟多个请求的缓存行为")
    
    # 创建一系列相似的请求（应该有高命中率）
    requests = []
    base_system = [
        {
            "type": "text",
            "text": "You are a helpful assistant. " + "Context: " * 300,
            "cache_control": {"type": "ephemeral"}
        }
    ]
    
    for i in range(10):
        requests.append({
            "model": "claude-sonnet-4.5",
            "max_tokens": 1024,
            "system": base_system,
            "messages": [
                {"role": "user", "content": f"Question {i}: What is the answer?"}
            ]
        })
    
    simulation_results = simulate_cache_behavior(requests)
    print_simulation_report(simulation_results)
    
    print("\n\n💡 总结：")
    print("1. 确保请求中有 cache_control 标记")
    print("2. 可缓存内容应该至少 1024 tokens（Anthropic 要求）")
    print("3. 可缓存内容应该在多个请求间保持稳定")
    print("4. 避免在可缓存内容中包含动态数据（时间戳、UUID 等）")
    print("5. 使用数组格式的 system prompt 和 message content")
