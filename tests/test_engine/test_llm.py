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


@pytest.mark.asyncio
async def test_generate_json_returns_parsed_dict():
    """generate_json now returns (dict, usage_dict)."""
    client = LLMClient("openai:gpt-4o-mini")

    mock_response = MagicMock()
    mock_response.content = '{"plan": "test"}'
    mock_response.usage_metadata = None  # no usage

    with patch.object(client, "_get_chat_model") as mock_model:
        mock_instance = AsyncMock()
        mock_instance.ainvoke.return_value = mock_response
        mock_model.return_value = mock_instance

        result, usage = await client.generate_json("system prompt", "user prompt")
        assert result == {"plan": "test"}
        assert isinstance(usage, dict)


@pytest.mark.asyncio
async def test_generate_json_handles_markdown_fence():
    """generate_json strips ```json fences before parsing."""
    client = LLMClient("openai:gpt-4o-mini")

    mock_response = MagicMock()
    mock_response.content = '```json\n{"plan": "test"}\n```'
    mock_response.usage_metadata = None

    with patch.object(client, "_get_chat_model") as mock_model:
        mock_instance = AsyncMock()
        mock_instance.ainvoke.return_value = mock_response
        mock_model.return_value = mock_instance

        result, _ = await client.generate_json("system prompt", "user prompt")
        assert result == {"plan": "test"}


@pytest.mark.asyncio
async def test_generate_text_returns_raw_string():
    """generate_text returns stripped text without JSON parsing."""
    client = LLMClient("openai:gpt-4o-mini")

    mock_response = MagicMock()
    mock_response.content = "  Hello, I am an LLM.  "

    with patch.object(client, "_get_chat_model") as mock_model:
        mock_instance = AsyncMock()
        mock_instance.ainvoke.return_value = mock_response
        mock_model.return_value = mock_instance

        result = await client.generate_text("system prompt", "user prompt")
        assert result == "Hello, I am an LLM."


@pytest.mark.asyncio
async def test_generate_text_does_not_parse_json():
    """generate_text returns plain text even when content looks like JSON."""
    client = LLMClient("openai:gpt-4o-mini")

    mock_response = MagicMock()
    mock_response.content = '{"key": "value"}'

    with patch.object(client, "_get_chat_model") as mock_model:
        mock_instance = AsyncMock()
        mock_instance.ainvoke.return_value = mock_response
        mock_model.return_value = mock_instance

        result = await client.generate_text("system prompt", "user prompt")
        assert isinstance(result, str)
        assert result == '{"key": "value"}'


@pytest.mark.asyncio
async def test_generate_json_calls_generate_text_internally():
    """generate_json uses the chat model directly (no longer delegates to generate_text)."""
    client = LLMClient("openai:gpt-4o-mini")

    mock_response = MagicMock()
    mock_response.content = '{"answer": 42}'
    mock_response.usage_metadata = None

    with patch.object(client, "_get_chat_model") as mock_model:
        mock_instance = AsyncMock()
        mock_instance.ainvoke.return_value = mock_response
        mock_model.return_value = mock_instance

        result, _ = await client.generate_json("sys", "user")

    assert result == {"answer": 42}
