# -*- coding: utf-8 -*-
"""
测试 map_claude_model_to_amazonq 模型映射逻辑
"""
import pytest
from src.amazonq.converter import map_claude_model_to_amazonq


class TestMapClaudeModelToAmazonQ:

    # --- sonnet ---
    def test_sonnet_4_6(self):
        assert map_claude_model_to_amazonq("claude-sonnet-4-6") == "claude-sonnet-4.6"

    def test_sonnet_4_dot_6(self):
        assert map_claude_model_to_amazonq("claude-sonnet-4.6") == "claude-sonnet-4.6"

    def test_sonnet_4_6_with_date(self):
        assert map_claude_model_to_amazonq("claude-sonnet-4-6-20260101") == "claude-sonnet-4.6"

    def test_sonnet_4_5(self):
        assert map_claude_model_to_amazonq("claude-sonnet-4-5") == "claude-sonnet-4.5"

    def test_sonnet_4_dot_5(self):
        assert map_claude_model_to_amazonq("claude-sonnet-4.5") == "claude-sonnet-4.5"

    def test_sonnet_4_no_version(self):
        # 无版本号的 sonnet 默认走 4.5
        assert map_claude_model_to_amazonq("claude-sonnet-4") == "claude-sonnet-4.5"

    def test_sonnet_3_5(self):
        assert map_claude_model_to_amazonq("claude-3-5-sonnet-20241022") == "claude-sonnet-4.5"

    # --- opus ---
    def test_opus_4_6(self):
        assert map_claude_model_to_amazonq("claude-opus-4-6") == "claude-opus-4.6"

    def test_opus_4_dot_6(self):
        assert map_claude_model_to_amazonq("claude-opus-4.6") == "claude-opus-4.6"

    def test_opus_4_5(self):
        assert map_claude_model_to_amazonq("claude-opus-4-5") == "claude-opus-4.5"

    def test_opus_4_dot_5(self):
        assert map_claude_model_to_amazonq("claude-opus-4.5") == "claude-opus-4.5"

    def test_opus_4_no_version(self):
        # 无版本号的 opus 默认走 4.6（最新）
        assert map_claude_model_to_amazonq("claude-opus-4") == "claude-opus-4.6"

    def test_opus_4_5_with_thinking_suffix(self):
        assert map_claude_model_to_amazonq("claude-opus-4-5-20251101-thinking") == "claude-opus-4.5"

    def test_opus_4_6_with_thinking_suffix(self):
        assert map_claude_model_to_amazonq("claude-opus-4-6-thinking") == "claude-opus-4.6"

    # --- haiku ---
    def test_haiku_4_5(self):
        assert map_claude_model_to_amazonq("claude-haiku-4-5") == "claude-haiku-4.5"

    def test_haiku_4(self):
        assert map_claude_model_to_amazonq("claude-haiku-4") == "claude-haiku-4.5"

    def test_haiku_3_5(self):
        assert map_claude_model_to_amazonq("claude-3-5-haiku-20241022") == "claude-haiku-4.5"

    # --- 未知模型 ---
    def test_unknown_model_defaults_to_sonnet_4_5(self):
        assert map_claude_model_to_amazonq("gpt-4o") == "claude-sonnet-4.5"

    def test_unknown_claude_model(self):
        assert map_claude_model_to_amazonq("claude-unknown") == "claude-sonnet-4.5"

    # --- 大小写不敏感 ---
    def test_case_insensitive_sonnet(self):
        assert map_claude_model_to_amazonq("Claude-Sonnet-4.6") == "claude-sonnet-4.6"

    def test_case_insensitive_opus(self):
        assert map_claude_model_to_amazonq("CLAUDE-OPUS-4.5") == "claude-opus-4.5"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
