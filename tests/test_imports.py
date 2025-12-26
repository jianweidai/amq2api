"""
测试所有模块的导入是否正确
验证项目重构后的 import 路径
"""
import pytest


class TestModuleImports:
    """测试所有核心模块的导入"""

    def test_main_import(self):
        """测试 main 模块导入"""
        from src.main import app
        assert app is not None

    def test_config_import(self):
        """测试 config 模块导入"""
        from src.config import read_global_config, get_config_sync
        assert read_global_config is not None
        assert get_config_sync is not None

    def test_models_import(self):
        """测试 models 模块导入"""
        from src.models import ClaudeRequest, ClaudeMessage
        assert ClaudeRequest is not None
        assert ClaudeMessage is not None


class TestAuthModuleImports:
    """测试 auth 模块的导入"""

    def test_auth_import(self):
        """测试 auth.auth 模块导入"""
        from src.auth.auth import get_auth_headers_with_retry
        assert get_auth_headers_with_retry is not None

    def test_account_manager_import(self):
        """测试 auth.account_manager 模块导入"""
        from src.auth.account_manager import (
            list_all_accounts,
            get_account,
            get_random_account,
        )
        assert list_all_accounts is not None
        assert get_account is not None
        assert get_random_account is not None

    def test_token_scheduler_import(self):
        """测试 auth.token_scheduler 模块导入"""
        from src.auth.token_scheduler import scheduled_token_refresh
        assert scheduled_token_refresh is not None


class TestAmazonQModuleImports:
    """测试 amazonq 模块的导入"""

    def test_converter_import(self):
        """测试 amazonq.converter 模块导入"""
        from src.amazonq.converter import convert_claude_to_codewhisperer_request
        assert convert_claude_to_codewhisperer_request is not None

    def test_parser_import(self):
        """测试 amazonq.parser 模块导入"""
        from src.amazonq.parser import parse_event_data
        assert parse_event_data is not None

    def test_event_stream_parser_import(self):
        """测试 amazonq.event_stream_parser 模块导入"""
        from src.amazonq.event_stream_parser import EventStreamParser
        assert EventStreamParser is not None

    def test_stream_handler_import(self):
        """测试 amazonq.stream_handler 模块导入"""
        from src.amazonq.stream_handler import handle_amazonq_stream
        assert handle_amazonq_stream is not None


class TestProcessingModuleImports:
    """测试 processing 模块的导入"""

    def test_message_processor_import(self):
        """测试 processing.message_processor 模块导入"""
        from src.processing.message_processor import merge_user_messages
        assert merge_user_messages is not None

    def test_model_mapper_import(self):
        """测试 processing.model_mapper 模块导入"""
        from src.processing.model_mapper import apply_model_mapping
        assert apply_model_mapping is not None

    def test_cache_manager_import(self):
        """测试 processing.cache_manager 模块导入"""
        from src.processing.cache_manager import CacheManager
        assert CacheManager is not None

    def test_usage_tracker_import(self):
        """测试 processing.usage_tracker 模块导入"""
        from src.processing.usage_tracker import record_usage
        assert record_usage is not None


class TestGeminiModuleImports:
    """测试 gemini 模块的导入"""

    def test_gemini_auth_import(self):
        """测试 gemini.auth 模块导入"""
        from src.gemini.auth import GeminiTokenManager
        assert GeminiTokenManager is not None

    def test_gemini_converter_import(self):
        """测试 gemini.converter 模块导入"""
        from src.gemini.converter import convert_claude_to_gemini
        assert convert_claude_to_gemini is not None

    def test_gemini_handler_import(self):
        """测试 gemini.handler 模块导入"""
        from src.gemini.handler import handle_gemini_stream
        assert handle_gemini_stream is not None

    def test_gemini_models_import(self):
        """测试 gemini.models 模块导入"""
        from src.gemini.models import GeminiRequest
        assert GeminiRequest is not None


class TestCustomApiModuleImports:
    """测试 custom_api 模块的导入"""

    def test_custom_api_converter_import(self):
        """测试 custom_api.converter 模块导入"""
        from src.custom_api.converter import convert_claude_to_openai_request
        assert convert_claude_to_openai_request is not None

    def test_custom_api_handler_import(self):
        """测试 custom_api.handler 模块导入"""
        from src.custom_api.handler import handle_custom_api_request
        assert handle_custom_api_request is not None


class TestCrossModuleImports:
    """测试跨模块导入（验证内部依赖正确）"""

    def test_stream_handler_uses_correct_config(self):
        """验证 stream_handler 使用正确的 config 导入"""
        # 这会触发 stream_handler 内部的 config 导入
        from src.amazonq.stream_handler import AmazonQStreamHandler
        assert AmazonQStreamHandler is not None

    def test_custom_api_handler_uses_correct_model_mapper(self):
        """验证 custom_api.handler 使用正确的 model_mapper 导入"""
        # 这会触发 handler 内部的 model_mapper 导入
        from src.custom_api.handler import handle_custom_api_request
        assert handle_custom_api_request is not None
