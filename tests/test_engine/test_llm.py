import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from atrium.engine.llm import LLMClient, parse_llm_config


def test_parse_llm_config_openai():
    provider, model = parse_llm_config("openai:gpt-4o-mini")
    assert provider == "openai"
    assert model == "gpt-4o-mini"


def test_parse_llm_config_default_model():
    provider, model = parse_llm_config("openai")
    assert provider == "openai"
    assert model is None


def test_parse_llm_config_anthropic():
    provider, model = parse_llm_config("anthropic:claude-sonnet-4-6")
    assert provider == "anthropic"
    assert model == "claude-sonnet-4-6"


async def test_generate_json_returns_parsed_dict():
    client = LLMClient("openai:gpt-4o-mini")

    mock_response = MagicMock()
    mock_response.content = '{"plan": "test"}'

    with patch.object(client, "_get_chat_model") as mock_model:
        mock_instance = AsyncMock()
        mock_instance.ainvoke.return_value = mock_response
        mock_model.return_value = mock_instance

        result = await client.generate_json("system prompt", "user prompt")
        assert result == {"plan": "test"}


async def test_generate_json_handles_markdown_fence():
    client = LLMClient("openai:gpt-4o-mini")

    mock_response = MagicMock()
    mock_response.content = '```json\n{"plan": "test"}\n```'

    with patch.object(client, "_get_chat_model") as mock_model:
        mock_instance = AsyncMock()
        mock_instance.ainvoke.return_value = mock_response
        mock_model.return_value = mock_instance

        result = await client.generate_json("system prompt", "user prompt")
        assert result == {"plan": "test"}
