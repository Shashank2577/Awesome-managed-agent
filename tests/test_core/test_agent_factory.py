"""Tests for agent_factory.build_agent_class dispatcher."""

from __future__ import annotations

import pytest

from atrium.core.agent_factory import build_agent_class
from atrium.core.agent import Agent

_HTTP_CONFIG = {
    "name": "factory_http",
    "description": "An HTTP agent from factory",
    "api_url": "https://example.com/api",
    "agent_type": "http",
}


def test_http_agent_type_returns_agent_subclass():
    """build_agent_class with agent_type='http' returns a valid Agent subclass."""
    cls = build_agent_class(_HTTP_CONFIG)
    assert issubclass(cls, Agent)


def test_http_agent_class_has_correct_name():
    """Returned class carries the name from the config."""
    cls = build_agent_class(_HTTP_CONFIG)
    assert cls.name == "factory_http"


def test_missing_agent_type_defaults_to_http():
    """A config without agent_type key defaults to the HTTP branch."""
    config = {
        "name": "default_http",
        "description": "No agent_type key",
        "api_url": "https://example.com/api",
    }
    cls = build_agent_class(config)
    assert issubclass(cls, Agent)
    assert cls.name == "default_http"


def test_llm_agent_type_raises_not_implemented():
    """build_agent_class with agent_type='llm' raises NotImplementedError."""
    config = {
        "name": "llm_agent",
        "description": "An LLM agent",
        "agent_type": "llm",
        "system_prompt": "You are helpful.",
    }
    with pytest.raises(NotImplementedError, match="LLMAgent not yet implemented"):
        build_agent_class(config)


def test_unknown_agent_type_raises_value_error():
    """build_agent_class with an unknown agent_type raises ValueError."""
    config = {
        "name": "weird_agent",
        "description": "Unknown type",
        "agent_type": "grpc",
    }
    with pytest.raises(ValueError, match="Unknown agent_type: grpc"):
        build_agent_class(config)


def test_each_call_returns_distinct_class():
    """Two calls with different names produce distinct classes."""
    config_a = {**_HTTP_CONFIG, "name": "agent_a"}
    config_b = {**_HTTP_CONFIG, "name": "agent_b"}
    cls_a = build_agent_class(config_a)
    cls_b = build_agent_class(config_b)
    assert cls_a is not cls_b
    assert cls_a.name != cls_b.name
