"""
缓存命中率改进方案

根据分析，缓存命中率低的主要原因和改进方案
"""

# ============================================================================
# 问题诊断
# ============================================================================

"""
## 缓存命中率低的主要原因

### 1. 客户端没有发送 cache_control 标记 ⚠️ 【最主要原因】
   
   当前实现：只缓存带有 `cache_control: {type: "ephemeral"}` 标记的内容
   
   问题：
   - Claude Code 等客户端可能不发送 cache_control 标记
   - 没有标记的请求，extract_cacheable_content() 返回空字符串
   - 导致缓存完全不工作
   
   影响：命中率 0%

### 2. 可缓存内容太少
   
   Anthropic 要求：至少 1024 tokens 才能缓存
   
   问题：
   - 短对话的 system prompt 通常少于 1024 tokens
   - 单条消息很少超过 1024 tokens
   
   影响：即使有 cache_control，也可能无法缓存

### 3. 内容变化性高
   
   问题：
   - 每个请求的内容都不同（不同的问题、不同的上下文）
   - 即使有相同的 system prompt，消息内容也不同
   - 缓存键基于完整内容的 SHA-256，内容稍有不同就无法命中
   
   影响：命中率低

### 4. 缓存策略过于严格
   
   当前策略：只缓存显式标记的内容
   
   问题：
   - 没有自动识别可缓存的模式（如 system prompt）
   - 没有部分匹配机制
   - 没有智能合并相似内容
   
   影响：错过很多缓存机会
"""

# ============================================================================
# 改进方案
# ============================================================================

"""
## 改进方案（按优先级排序）

### 方案 1：自动缓存 system prompt（推荐，立即实施）⭐⭐⭐⭐⭐

**原理**：
- 自动将 system prompt 作为可缓存内容
- 不依赖 cache_control 标记
- system prompt 通常在多个请求间保持稳定

**实现**：
```python
def extract_cacheable_content(self, request_data: Dict[str, Any]) -> Tuple[str, int]:
    cacheable_parts: List[str] = []
    
    # 1. 自动缓存 system prompt（新增）
    system = request_data.get("system")
    if system:
        if isinstance(system, str):
            cacheable_parts.append(system)
        elif isinstance(system, list):
            for block in system:
                if isinstance(block, dict) and block.get("type") == "text":
                    cacheable_parts.append(block.get("text", ""))
    
    # 2. 继续处理带 cache_control 的内容（保留原有逻辑）
    # ...
```

**优点**：
- 简单易实现
- 不需要客户端改动
- system prompt 通常稳定，命中率高
- 兼容现有的 cache_control 机制

**预期效果**：命中率提升到 30-50%

---

### 方案 2：智能识别历史消息（推荐）⭐⭐⭐⭐

**原理**：
- 自动缓存历史消息（除了最后一条）
- 历史消息在对话中保持不变
- 只有最新的用户消息会变化

**实现**：
```python
def extract_cacheable_content(self, request_data: Dict[str, Any]) -> Tuple[str, int]:
    cacheable_parts: List[str] = []
    
    # 1. 缓存 system prompt
    # ...
    
    # 2. 缓存历史消息（除了最后一条）
    messages = request_data.get("messages", [])
    if len(messages) > 1:
        for message in messages[:-1]:  # 排除最后一条
            content = message.get("content", "")
            if isinstance(content, str):
                cacheable_parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        cacheable_parts.append(block.get("text", ""))
    
    # 3. 继续处理带 cache_control 的内容
    # ...
```

**优点**：
- 对话越长，缓存效果越好
- 自动工作，不需要客户端支持
- 符合实际使用场景

**预期效果**：命中率提升到 50-70%

---

### 方案 3：分层缓存（高级）⭐⭐⭐⭐⭐

**原理**：
- 将请求分为多个层次：system、history、current
- 每层独立缓存
- 组合匹配，提高命中率

**实现**：
```python
def extract_cacheable_layers(self, request_data: Dict[str, Any]) -> Dict[str, Tuple[str, int]]:
    layers = {}
    
    # Layer 1: System prompt
    system = request_data.get("system")
    if system:
        system_text = self._extract_system_text(system)
        if system_text:
            layers["system"] = (system_text, self._estimate_token_count(system_text))
    
    # Layer 2: History messages
    messages = request_data.get("messages", [])
    if len(messages) > 1:
        history_text = self._extract_messages_text(messages[:-1])
        if history_text:
            layers["history"] = (history_text, self._estimate_token_count(history_text))
    
    # Layer 3: Tools definition
    tools = request_data.get("tools")
    if tools:
        tools_text = json.dumps(tools, sort_keys=True)
        layers["tools"] = (tools_text, self._estimate_token_count(tools_text))
    
    return layers

def check_cache_layered(self, layers: Dict[str, Tuple[str, int]]) -> CacheResult:
    total_creation = 0
    total_read = 0
    
    for layer_name, (content, token_count) in layers.items():
        key = self.calculate_cache_key(content)
        result = self.check_cache(key, token_count, len(content))
        
        total_creation += result.cache_creation_input_tokens
        total_read += result.cache_read_input_tokens
    
    return CacheResult(
        is_hit=total_read > 0,
        cache_creation_input_tokens=total_creation,
        cache_read_input_tokens=total_read
    )
```

**优点**：
- 最大化缓存利用率
- 部分命中也能节省 tokens
- 更符合 Anthropic 的 Prompt Caching 设计

**预期效果**：命中率提升到 70-90%

---

### 方案 4：内容标准化（辅助）⭐⭐⭐

**原理**：
- 移除或标准化动态内容
- 使内容更稳定，提高命中率

**实现**：
```python
def normalize_content(self, content: str) -> str:
    import re
    
    # 移除时间戳
    content = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}', '[TIMESTAMP]', content)
    
    # 移除 UUID
    content = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '[UUID]', content)
    
    # 移除请求 ID
    content = re.sub(r'request[_-]id[:\s]+[a-zA-Z0-9-]+', 'request_id: [ID]', content)
    
    return content
```

**优点**：
- 减少因动态数据导致的缓存未命中
- 可以与其他方案组合使用

**预期效果**：命中率提升 5-10%

---

### 方案 5：配置选项（灵活性）⭐⭐⭐

**原理**：
- 提供配置选项，让用户选择缓存策略
- 平衡性能和准确性

**实现**：
```python
class CacheManager:
    def __init__(
        self,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        auto_cache_system: bool = True,      # 自动缓存 system prompt
        auto_cache_history: bool = True,     # 自动缓存历史消息
        auto_cache_tools: bool = True,       # 自动缓存 tools 定义
        normalize_content: bool = False,     # 标准化内容
        min_cacheable_tokens: int = 1024,    # 最小可缓存 token 数
    ):
        # ...
```

**优点**：
- 灵活性高
- 可以根据实际情况调整
- 向后兼容

---

## 推荐实施顺序

1. **立即实施**：方案 1（自动缓存 system prompt）
   - 工作量：1-2 小时
   - 效果：立竿见影
   - 风险：低

2. **短期实施**：方案 2（智能识别历史消息）
   - 工作量：2-3 小时
   - 效果：显著提升
   - 风险：低

3. **中期实施**：方案 5（配置选项）
   - 工作量：1-2 小时
   - 效果：提供灵活性
   - 风险：低

4. **长期实施**：方案 3（分层缓存）
   - 工作量：4-6 小时
   - 效果：最大化
   - 风险：中等（需要重构）

5. **可选实施**：方案 4（内容标准化）
   - 工作量：2-3 小时
   - 效果：辅助提升
   - 风险：中等（可能影响语义）

---

## 测试验证

实施后，使用以下方法验证效果：

1. 查看 `/admin/cache/stats` 端点
2. 观察日志中的缓存命中信息
3. 使用 test_cache_hit_rate_analysis.py 分析实际请求
4. 对比实施前后的命中率

---

## 注意事项

1. **Anthropic 限制**：
   - 最小可缓存内容：1024 tokens
   - 最大缓存时间：5 分钟（实际可能更长）
   - 缓存只在同一会话内有效

2. **性能考虑**：
   - 缓存键计算（SHA-256）有开销
   - 过多的缓存条目会占用内存
   - 需要平衡缓存大小和命中率

3. **准确性考虑**：
   - 自动缓存可能缓存不应该缓存的内容
   - 需要提供配置选项让用户控制
   - 建议默认启用，但允许禁用
"""

if __name__ == "__main__":
    print(__doc__)
