"""Tests for the config-driven LLMAgent factory."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from atrium.core.agent import Agent
from atrium.core.llm_agent import create_agent_class


def _base_config(**overrides) -> dict:
    base = {
        "name": "test_llm",
        "description": "Test LLM agent",
        "system_prompt": "You are a helpful assistant.",
        "model": "anthropic:claude-sonnet-4-6",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Class-creation tests
# ---------------------------------------------------------------------------

def test_create_agent_class_returns_subclass():
    """create_agent_class returns a valid Agent subclass."""
    cls = create_agent_class(_base_config())
    assert issubclass(cls, Agent)


def test_agent_type_is_llm():
    """Created class has agent_type='llm'."""
    cls = create_agent_class(_base_config())
    assert cls.agent_type == "llm"


def test_category_set_from_config():
    """category is correctly propagated from config."""
    cls = create_agent_class(_base_config(category="writing"))
    assert cls.category == "writing"


def test_category_defaults_to_none():
    """category defaults to None when not provided."""
    cls = create_agent_class(_base_config())
    assert cls.category is None


def test_class_name_reflects_config():
    """Class __name__ encodes the agent name."""
    cls = create_agent_class(_base_config(name="my_llm"))
    assert cls.__name__ == "my_llm_LLMAgent"


def test_class_attributes():
    """Name, description, capabilities are set correctly."""
    cls = create_agent_class(_base_config(capabilities=["chat", "write"]))
    assert cls.name == "test_llm"
    assert cls.description == "Test LLM agent"
    assert cls.capabilities == ["chat", "write"]


def test_default_capabilities():
    """Capabilities default to []."""
    cls = create_agent_class(_base_config())
    assert cls.capabilities == []


# ---------------------------------------------------------------------------
# Config validation tests
# ---------------------------------------------------------------------------

def test_missing_name_raises_key_error():
    """Missing 'name' raises KeyError (AgentMeta enforcement)."""
    config = {"description": "no name", "system_prompt": "sys"}
    with pytest.raises(KeyError):
        create_agent_class(config)


def test_missing_description_raises_key_error():
    """Missing 'description' raises KeyError."""
    config = {"name": "no_desc", "system_prompt": "sys"}
    with pytest.raises(KeyError):
        create_agent_class(config)


def test_missing_system_prompt_raises_value_error():
    """Missing system_prompt raises ValueError."""
    config = {"name": "no_sys", "description": "no system prompt"}
    with pytest.raises(ValueError, match="system_prompt"):
        create_agent_class(config)


def test_empty_system_prompt_raises_value_error():
    """Empty system_prompt raises ValueError."""
    config = {"name": "empty_sys", "description": "desc", "system_prompt": ""}
    with pytest.raises(ValueError, match="system_prompt"):
        create_agent_class(config)


def test_none_system_prompt_raises_value_error():
    """None system_prompt raises ValueError."""
    config = {"name": "none_sys", "description": "desc", "system_prompt": None}
    with pytest.raises(ValueError, match="system_prompt"):
        create_agent_class(config)


# ---------------------------------------------------------------------------
# run() — happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_returns_expected_keys():
    """run() returns dict with response, model, source keys."""
    cls = create_agent_class(_base_config())

    with patch("atrium.engine.llm.LLMClient") as MockLLMClient:
        mock_client = AsyncMock()
        mock_client.generate_text = AsyncMock(return_value="Hello there!")
        MockLLMClient.return_value = mock_client

        instance = cls()
        result = await instance.run({"query": "hi"})

    assert result["response"] == "Hello there!"
    assert result["model"] == "anthropic:claude-sonnet-4-6"
    assert result["source"] == "test_llm"
    assert "error" not in result


@pytest.mark.asyncio
async def test_run_uses_extract_query():
    """run() resolves query from upstream data."""
    cls = create_agent_class(_base_config())

    with patch("atrium.engine.llm.LLMClient") as MockLLMClient:
        mock_client = AsyncMock()
        mock_client.generate_text = AsyncMock(return_value="response text")
        MockLLMClient.return_value = mock_client

        instance = cls()
        input_data = {"upstream": {"prev": {"result": "upstream content"}}}
        result = await instance.run(input_data)

    # Verify generate_text was called with the upstream content as user_prompt
    call_args = mock_client.generate_text.call_args
    assert call_args[0][1] == "upstream content"  # second positional arg = user_prompt
    assert result["response"] == "response text"


# ---------------------------------------------------------------------------
# run() — error swallowing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_swallows_llm_exception():
    """run() returns error dict instead of raising when LLMClient fails."""
    cls = create_agent_class(_base_config())

    with patch("atrium.engine.llm.LLMClient") as MockLLMClient:
        mock_client = AsyncMock()
        mock_client.generate_text = AsyncMock(
            side_effect=RuntimeError("connection refused")
        )
        MockLLMClient.return_value = mock_client

        instance = cls()
        result = await instance.run({"query": "anything"})

    assert result["response"] == ""
    assert "connection refused" in result["error"]
    assert result["source"] == "test_llm"


@pytest.mark.asyncio
async def test_run_error_dict_has_no_model_key():
    """Error response dict does not include 'model' key."""
    cls = create_agent_class(_base_config())

    with patch("atrium.engine.llm.LLMClient") as MockLLMClient:
        mock_client = AsyncMock()
        mock_client.generate_text = AsyncMock(side_effect=ValueError("bad"))
        MockLLMClient.return_value = mock_client

        instance = cls()
        result = await instance.run({"query": "q"})

    assert "model" not in result
    assert result["error"] == "bad"


# ---------------------------------------------------------------------------
# Multiple distinct classes
# ---------------------------------------------------------------------------

def test_each_call_returns_distinct_class():
    """Two calls produce distinct classes."""
    cls_a = create_agent_class(_base_config(name="llm_a", description="A"))
    cls_b = create_agent_class(_base_config(name="llm_b", description="B"))
    assert cls_a is not cls_b
    assert cls_a.name != cls_b.name


# ---------------------------------------------------------------------------
# Model resolution
# ---------------------------------------------------------------------------

def test_model_without_prefix_calls_detect_llm():
    """Config with model='claude-sonnet-4-6' (no colon) should call detect_llm()."""
    config = _base_config(model="claude-sonnet-4-6")

    with patch("atrium.engine.llm.detect_llm", return_value="anthropic:claude-sonnet-4-6") as mock_detect:
        cls = create_agent_class(config)

    mock_detect.assert_called_once()
    assert cls.agent_type == "llm"
