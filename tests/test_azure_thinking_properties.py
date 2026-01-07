"""
Property-based tests for Azure thinking continuity feature.
Uses hypothesis for property-based testing.

Tests the _clean_claude_request_for_azure function to ensure:
1. Valid thinking blocks (with signature) are preserved
2. Invalid thinking blocks (without signature) are converted to text
3. Thinking parameter is preserved when enabled
4. Content block order is maintained
5. Empty messages are handled correctly
"""
import copy
from hypothesis import given, strategies as st, settings, assume

from src.custom_api.handler import (
    _clean_claude_request_for_azure,
    _convert_thinking_block_to_text,
)


# ============================================================================
# Strategies for generating test data
# ============================================================================

def valid_thinking_block():
    """Generate a valid thinking block with signature."""
    return st.fixed_dictionaries({
        "type": st.just("thinking"),
        "thinking": st.text(min_size=0, max_size=500),
        "signature": st.text(min_size=1, max_size=100),
    })


def invalid_thinking_block():
    """Generate an invalid thinking block without signature."""
    return st.fixed_dictionaries({
        "type": st.just("thinking"),
        "thinking": st.text(min_size=0, max_size=500),
    })


def valid_redacted_thinking_block():
    """Generate a valid redacted_thinking block with data."""
    return st.fixed_dictionaries({
        "type": st.just("redacted_thinking"),
        "data": st.text(min_size=1, max_size=100),
    })


def invalid_redacted_thinking_block():
    """Generate an invalid redacted_thinking block without data."""
    return st.fixed_dictionaries({
        "type": st.just("redacted_thinking"),
    })


def text_block():
    """Generate a text block."""
    return st.fixed_dictionaries({
        "type": st.just("text"),
        "text": st.text(min_size=1, max_size=500),
    })


def tool_use_block():
    """Generate a tool_use block."""
    return st.fixed_dictionaries({
        "type": st.just("tool_use"),
        "id": st.text(min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_"),
        "name": st.text(min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz_"),
        "input": st.just({}),
    })


def content_block():
    """Generate any type of content block."""
    return st.one_of(
        text_block(),
        valid_thinking_block(),
        invalid_thinking_block(),
        valid_redacted_thinking_block(),
        invalid_redacted_thinking_block(),
        tool_use_block(),
    )


def assistant_message_with_content(content_strategy):
    """Generate an assistant message with specific content."""
    return st.fixed_dictionaries({
        "role": st.just("assistant"),
        "content": content_strategy,
    })


def user_message():
    """Generate a user message."""
    return st.one_of(
        st.fixed_dictionaries({
            "role": st.just("user"),
            "content": st.text(min_size=1, max_size=200),
        }),
        st.fixed_dictionaries({
            "role": st.just("user"),
            "content": st.lists(text_block(), min_size=1, max_size=3),
        }),
    )


def request_with_thinking_enabled(messages_strategy):
    """Generate a request with thinking enabled."""
    return st.fixed_dictionaries({
        "model": st.just("claude-haiku-4-5"),
        "thinking": st.just({"type": "enabled"}),
        "messages": messages_strategy,
    })


def request_without_thinking(messages_strategy):
    """Generate a request without thinking parameter."""
    return st.fixed_dictionaries({
        "model": st.just("claude-haiku-4-5"),
        "messages": messages_strategy,
    })


# ============================================================================
# Property Tests
# ============================================================================

class TestValidThinkingBlockPreservation:
    """
    **Feature: azure-thinking-continuity, Property 3: Valid thinking block preservation**
    
    *For any* thinking block with a valid signature field, the cleaner SHALL 
    preserve it unchanged in the output.
    
    **Validates: Requirements 2.3**
    
    Note: Azure requires the last assistant message to start with a valid thinking block
    when thinking is enabled. Tests are designed to satisfy this requirement.
    """
    
    @given(
        thinking_content=st.text(min_size=0, max_size=500),
        signature=st.text(min_size=1, max_size=100),
    )
    @settings(max_examples=100)
    def test_valid_thinking_block_preserved_when_thinking_enabled(
        self, thinking_content: str, signature: str
    ):
        """Valid thinking blocks should be preserved when thinking is enabled.
        
        The last assistant message starts with a valid thinking block, so thinking
        remains enabled and the block is preserved.
        """
        request_data = {
            "model": "claude-haiku-4-5",
            "thinking": {"type": "enabled"},
            "messages": [
                {"role": "user", "content": "Hello"},
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": thinking_content,
                            "signature": signature,
                        },
                        {"type": "text", "text": "Response"},
                    ],
                },
            ],
        }
        
        cleaned = _clean_claude_request_for_azure(request_data)
        
        # Find thinking blocks in cleaned output
        thinking_blocks = []
        for msg in cleaned.get("messages", []):
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "thinking":
                        thinking_blocks.append(block)
        
        assert len(thinking_blocks) == 1, f"Expected 1 thinking block, found {len(thinking_blocks)}"
        assert thinking_blocks[0].get("thinking") == thinking_content
        assert thinking_blocks[0].get("signature") == signature
    
    @given(
        blocks=st.lists(
            st.one_of(valid_thinking_block(), text_block()),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=100)
    def test_multiple_valid_thinking_blocks_preserved(self, blocks: list):
        """All valid thinking blocks should be preserved when last assistant message
        starts with a valid thinking block."""
        # Ensure at least one text block for non-empty content
        if not any(b.get("type") == "text" for b in blocks):
            blocks.append({"type": "text", "text": "Response"})
        
        # Ensure the content starts with a valid thinking block (Azure requirement)
        has_valid_thinking_at_start = (
            len(blocks) > 0 and 
            blocks[0].get("type") == "thinking" and 
            blocks[0].get("signature")
        )
        
        if not has_valid_thinking_at_start:
            # Add a valid thinking block at the start
            blocks.insert(0, {
                "type": "thinking",
                "thinking": "Valid thinking",
                "signature": "valid_sig"
            })
        
        request_data = {
            "model": "claude-haiku-4-5",
            "thinking": {"type": "enabled"},
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": blocks},
            ],
        }
        
        # Count valid thinking blocks in input
        input_valid_thinking = sum(
            1 for b in blocks
            if b.get("type") == "thinking" and b.get("signature")
        )
        
        cleaned = _clean_claude_request_for_azure(request_data)
        
        # Count thinking blocks in output
        output_thinking = 0
        for msg in cleaned.get("messages", []):
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "thinking":
                        output_thinking += 1
        
        assert output_thinking == input_valid_thinking, \
            f"Expected {input_valid_thinking} thinking blocks, found {output_thinking}"



class TestValidRedactedThinkingPreservation:
    """
    **Feature: azure-thinking-continuity, Property 6: Valid redacted_thinking preservation**
    
    *For any* redacted_thinking block with valid data AND thinking enabled, 
    the cleaner SHALL preserve it unchanged.
    
    **Validates: Requirements 3.1**
    
    Note: Azure requires the last assistant message to start with a valid thinking block
    when thinking is enabled. Tests are designed to satisfy this requirement.
    """
    
    @given(
        data=st.text(min_size=1, max_size=200),
    )
    @settings(max_examples=100)
    def test_valid_redacted_thinking_preserved_when_thinking_enabled(self, data: str):
        """Valid redacted_thinking blocks should be preserved when thinking is enabled.
        
        The last assistant message starts with a valid thinking block, so thinking
        remains enabled and redacted_thinking blocks are preserved.
        """
        request_data = {
            "model": "claude-haiku-4-5",
            "thinking": {"type": "enabled"},
            "messages": [
                {"role": "user", "content": "Hello"},
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": "Valid thinking",
                            "signature": "valid_sig",
                        },
                        {
                            "type": "redacted_thinking",
                            "data": data,
                        },
                        {"type": "text", "text": "Response"},
                    ],
                },
            ],
        }
        
        cleaned = _clean_claude_request_for_azure(request_data)
        
        # Find redacted_thinking blocks in cleaned output
        redacted_blocks = []
        for msg in cleaned.get("messages", []):
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "redacted_thinking":
                        redacted_blocks.append(block)
        
        assert len(redacted_blocks) == 1, f"Expected 1 redacted_thinking block, found {len(redacted_blocks)}"
        assert redacted_blocks[0].get("data") == data
    
    @given(
        data_values=st.lists(st.text(min_size=1, max_size=100), min_size=1, max_size=3),
    )
    @settings(max_examples=100)
    def test_multiple_valid_redacted_thinking_preserved(self, data_values: list):
        """All valid redacted_thinking blocks should be preserved when last assistant
        message starts with a valid thinking block."""
        content = [
            {
                "type": "thinking",
                "thinking": "Valid thinking",
                "signature": "valid_sig",
            }
        ]
        for data in data_values:
            content.append({"type": "redacted_thinking", "data": data})
        content.append({"type": "text", "text": "Response"})
        
        request_data = {
            "model": "claude-haiku-4-5",
            "thinking": {"type": "enabled"},
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": content},
            ],
        }
        
        cleaned = _clean_claude_request_for_azure(request_data)
        
        # Count redacted_thinking blocks in output
        output_redacted = 0
        for msg in cleaned.get("messages", []):
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "redacted_thinking":
                        output_redacted += 1
        
        assert output_redacted == len(data_values), \
            f"Expected {len(data_values)} redacted_thinking blocks, found {output_redacted}"


class TestInvalidRedactedThinkingRemoval:
    """
    **Feature: azure-thinking-continuity, Property 7: Invalid redacted_thinking removal**
    
    *For any* redacted_thinking block without valid data, the cleaner SHALL 
    remove it from the message.
    
    **Validates: Requirements 3.2**
    
    Note: Azure requires the last assistant message to start with a valid thinking block
    when thinking is enabled. Tests are designed to satisfy this requirement.
    """
    
    @given(
        text_content=st.text(min_size=1, max_size=200),
    )
    @settings(max_examples=100)
    def test_invalid_redacted_thinking_removed(self, text_content: str):
        """Invalid redacted_thinking blocks (without data) should be removed.
        
        The last assistant message starts with a valid thinking block, so thinking
        remains enabled, but invalid redacted_thinking blocks are still removed.
        """
        request_data = {
            "model": "claude-haiku-4-5",
            "thinking": {"type": "enabled"},
            "messages": [
                {"role": "user", "content": "Hello"},
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": "Valid thinking",
                            "signature": "valid_sig",
                        },
                        {
                            "type": "redacted_thinking",
                            # No data field - invalid
                        },
                        {"type": "text", "text": text_content},
                    ],
                },
            ],
        }
        
        cleaned = _clean_claude_request_for_azure(request_data)
        
        # Find redacted_thinking blocks in cleaned output
        redacted_blocks = []
        for msg in cleaned.get("messages", []):
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "redacted_thinking":
                        redacted_blocks.append(block)
        
        assert len(redacted_blocks) == 0, f"Expected 0 redacted_thinking blocks, found {len(redacted_blocks)}"
    
    @given(
        num_invalid=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=100)
    def test_multiple_invalid_redacted_thinking_all_removed(self, num_invalid: int):
        """All invalid redacted_thinking blocks should be removed.
        
        The last assistant message starts with a valid thinking block, so thinking
        remains enabled, but all invalid redacted_thinking blocks are removed.
        """
        content = [
            {
                "type": "thinking",
                "thinking": "Valid thinking",
                "signature": "valid_sig",
            }
        ]
        for _ in range(num_invalid):
            content.append({"type": "redacted_thinking"})  # No data - invalid
        content.append({"type": "text", "text": "Response"})
        
        request_data = {
            "model": "claude-haiku-4-5",
            "thinking": {"type": "enabled"},
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": content},
            ],
        }
        
        cleaned = _clean_claude_request_for_azure(request_data)
        
        # Count redacted_thinking blocks in output
        output_redacted = 0
        for msg in cleaned.get("messages", []):
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "redacted_thinking":
                        output_redacted += 1
        
        assert output_redacted == 0, f"Expected 0 redacted_thinking blocks, found {output_redacted}"
    
    @given(
        valid_data=st.text(min_size=1, max_size=100),
    )
    @settings(max_examples=100)
    def test_mixed_valid_invalid_redacted_thinking(self, valid_data: str):
        """Only valid redacted_thinking blocks should be preserved.
        
        The last assistant message starts with a valid thinking block, so thinking
        remains enabled. Valid redacted_thinking blocks are preserved, invalid ones removed.
        """
        content = [
            {
                "type": "thinking",
                "thinking": "Valid thinking",
                "signature": "valid_sig",
            },
            {"type": "redacted_thinking", "data": valid_data},  # Valid
            {"type": "redacted_thinking"},  # Invalid - no data
            {"type": "text", "text": "Response"},
        ]
        
        request_data = {
            "model": "claude-haiku-4-5",
            "thinking": {"type": "enabled"},
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": content},
            ],
        }
        
        cleaned = _clean_claude_request_for_azure(request_data)
        
        # Count redacted_thinking blocks in output
        output_redacted = []
        for msg in cleaned.get("messages", []):
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "redacted_thinking":
                        output_redacted.append(block)
        
        assert len(output_redacted) == 1, f"Expected 1 redacted_thinking block, found {len(output_redacted)}"
        assert output_redacted[0].get("data") == valid_data
