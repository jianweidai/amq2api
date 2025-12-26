"""
Tests for usage_tracker module with cache statistics support
"""
import pytest
import os
import tempfile
from pathlib import Path
from src.processing import usage_tracker


class TestUsageTrackerCacheFields:
    """Test cache token fields in usage tracker"""
    
    def test_record_usage_with_cache_creation_tokens(self):
        """Test recording usage with cache_creation_input_tokens"""
        record_id = usage_tracker.record_usage(
            model="claude-3-sonnet",
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=500,
            cache_read_input_tokens=0
        )
        
        assert record_id is not None
        assert len(record_id) == 36  # UUID format
    
    def test_record_usage_with_cache_read_tokens(self):
        """Test recording usage with cache_read_input_tokens"""
        record_id = usage_tracker.record_usage(
            model="claude-3-sonnet",
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=500
        )
        
        assert record_id is not None
        assert len(record_id) == 36
    
    def test_record_usage_backward_compatible(self):
        """Test that record_usage works without cache parameters (backward compatibility)"""
        record_id = usage_tracker.record_usage(
            model="claude-3-sonnet",
            input_tokens=100,
            output_tokens=50
        )
        
        assert record_id is not None
    
    def test_get_usage_summary_includes_cache_fields(self):
        """Test that get_usage_summary includes cache statistics"""
        # Record some usage with cache stats
        usage_tracker.record_usage(
            model="claude-3-opus",
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=1000,
            cache_read_input_tokens=0
        )
        
        summary = usage_tracker.get_usage_summary(period="all")
        
        # Verify cache fields exist in summary
        assert "cache_creation_input_tokens" in summary
        assert "cache_read_input_tokens" in summary
        assert summary["cache_creation_input_tokens"] >= 0
        assert summary["cache_read_input_tokens"] >= 0
    
    def test_get_usage_summary_aggregates_cache_tokens(self):
        """Test that cache tokens are properly aggregated in summary"""
        # Record multiple usages with cache stats
        usage_tracker.record_usage(
            model="test-model-agg",
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=500,
            cache_read_input_tokens=0
        )
        usage_tracker.record_usage(
            model="test-model-agg",
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=500
        )
        
        summary = usage_tracker.get_usage_summary(period="all", model="test-model-agg")
        
        # Both cache fields should have values
        assert summary["cache_creation_input_tokens"] >= 500
        assert summary["cache_read_input_tokens"] >= 500
    
    def test_get_recent_usage_includes_cache_fields(self):
        """Test that get_recent_usage returns records with cache fields"""
        # Record usage with cache stats
        usage_tracker.record_usage(
            model="claude-3-haiku",
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=200,
            cache_read_input_tokens=300
        )
        
        recent = usage_tracker.get_recent_usage(limit=1)
        
        assert len(recent) > 0
        # Check that cache fields exist in the record
        assert "cache_creation_input_tokens" in recent[0]
        assert "cache_read_input_tokens" in recent[0]
    
    def test_by_model_includes_cache_fields(self):
        """Test that by_model breakdown includes cache statistics"""
        usage_tracker.record_usage(
            model="test-by-model",
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=100,
            cache_read_input_tokens=200
        )
        
        summary = usage_tracker.get_usage_summary(period="all")
        
        # Find our test model in by_model
        by_model = summary.get("by_model", [])
        test_model_stats = None
        for model_stat in by_model:
            if model_stat.get("model") == "test-by-model":
                test_model_stats = model_stat
                break
        
        if test_model_stats:
            assert "cache_creation_input_tokens" in test_model_stats
            assert "cache_read_input_tokens" in test_model_stats
