"""
Property-based tests for cache_manager module.
Uses hypothesis for property-based testing.
"""
import hashlib
from hypothesis import given, strategies as st, settings

from src.processing.cache_manager import CacheManager


class TestCacheKeyDeterminism:
    """
    **Feature: prompt-caching, Property 6: Cache key determinism**
    
    *For any* cacheable content string, the calculated cache key should be 
    the SHA-256 hash of that content, and calculating the key multiple times 
    for the same content should produce the same result.
    
    **Validates: Requirements 3.4, 7.4**
    """
    
    @given(content=st.text(min_size=0, max_size=10000))
    @settings(max_examples=100)
    def test_cache_key_is_sha256(self, content: str):
        """Cache key should be the SHA-256 hash of the content."""
        cm = CacheManager()
        
        key = cm.calculate_cache_key(content)
        expected = hashlib.sha256(content.encode('utf-8')).hexdigest()
        
        assert key == expected, f"Cache key {key} does not match expected SHA-256 {expected}"
    
    @given(content=st.text(min_size=0, max_size=10000))
    @settings(max_examples=100)
    def test_cache_key_determinism(self, content: str):
        """Calculating the key multiple times for the same content should produce the same result."""
        cm = CacheManager()
        
        key1 = cm.calculate_cache_key(content)
        key2 = cm.calculate_cache_key(content)
        key3 = cm.calculate_cache_key(content)
        
        assert key1 == key2 == key3, f"Cache keys are not deterministic: {key1}, {key2}, {key3}"
    
    @given(content=st.text(min_size=0, max_size=10000))
    @settings(max_examples=100)
    def test_cache_key_across_instances(self, content: str):
        """Different CacheManager instances should produce the same key for the same content."""
        cm1 = CacheManager(ttl_seconds=100, max_entries=500)
        cm2 = CacheManager(ttl_seconds=300, max_entries=1000)
        
        key1 = cm1.calculate_cache_key(content)
        key2 = cm2.calculate_cache_key(content)
        
        assert key1 == key2, f"Different instances produce different keys: {key1} vs {key2}"
    
    @given(content=st.text(min_size=1, max_size=10000))
    @settings(max_examples=100)
    def test_cache_key_is_64_hex_chars(self, content: str):
        """Cache key should be a 64-character hexadecimal string (SHA-256 output)."""
        cm = CacheManager()
        
        key = cm.calculate_cache_key(content)
        
        assert len(key) == 64, f"Cache key length is {len(key)}, expected 64"
        assert all(c in '0123456789abcdef' for c in key), f"Cache key contains non-hex characters: {key}"


class TestCacheMissBehavior:
    """
    **Feature: prompt-caching, Property 3: Cache miss reports creation tokens**
    
    *For any* request with cache_control that results in a cache miss, the response 
    should report the cacheable tokens as cache_creation_input_tokens and 
    cache_read_input_tokens should be zero.
    
    **Validates: Requirements 3.1**
    """
    
    @given(
        content=st.text(min_size=1, max_size=10000),
        token_count=st.integers(min_value=1, max_value=100000)
    )
    @settings(max_examples=100)
    def test_cache_miss_reports_creation_tokens(self, content: str, token_count: int):
        """On cache miss, cache_creation_input_tokens should equal token_count and cache_read_input_tokens should be zero."""
        cm = CacheManager()
        
        key = cm.calculate_cache_key(content)
        result = cm.check_cache(key, token_count)
        
        assert result.is_hit is False, "First access should be a cache miss"
        assert result.cache_creation_input_tokens == token_count, \
            f"cache_creation_input_tokens should be {token_count}, got {result.cache_creation_input_tokens}"
        assert result.cache_read_input_tokens == 0, \
            f"cache_read_input_tokens should be 0 on miss, got {result.cache_read_input_tokens}"
    
    @given(
        contents=st.lists(st.text(min_size=1, max_size=1000), min_size=2, max_size=10, unique=True),
        token_counts=st.lists(st.integers(min_value=1, max_value=10000), min_size=2, max_size=10)
    )
    @settings(max_examples=100)
    def test_multiple_unique_keys_all_miss(self, contents: list, token_counts: list):
        """Multiple unique cache keys should all result in cache misses with correct creation tokens."""
        cm = CacheManager()
        
        # Ensure we have matching lengths
        pairs = list(zip(contents, token_counts))
        
        for content, token_count in pairs:
            key = cm.calculate_cache_key(content)
            result = cm.check_cache(key, token_count)
            
            assert result.is_hit is False, f"First access to key should be a cache miss"
            assert result.cache_creation_input_tokens == token_count, \
                f"cache_creation_input_tokens should be {token_count}, got {result.cache_creation_input_tokens}"
            assert result.cache_read_input_tokens == 0, \
                f"cache_read_input_tokens should be 0 on miss, got {result.cache_read_input_tokens}"
