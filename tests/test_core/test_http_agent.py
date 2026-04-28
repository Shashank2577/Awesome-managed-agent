"""Tests for the config-driven HTTPAgent factory."""

import pytest

from atrium.core.agent import Agent
from atrium.core.http_agent import create_agent_class


def _base_config(**overrides) -> dict:
    base = {
        "name": "test_api",
        "description": "Test API agent",
        "capabilities": ["test"],
        "api_url": "https://httpbin.org/get",
        "method": "GET",
    }
    base.update(overrides)
    return base


def test_create_agent_class_returns_subclass():
    cls = create_agent_class(_base_config())
    assert issubclass(cls, Agent)


def test_class_attributes():
    cls = create_agent_class(_base_config())
    assert cls.name == "test_api"
    assert cls.description == "Test API agent"
    assert cls.capabilities == ["test"]


def test_instance_attributes():
    cls = create_agent_class(_base_config())
    instance = cls()
    assert instance.name == "test_api"
    assert instance._config["api_url"] == "https://httpbin.org/get"


def test_class_name_reflects_config():
    cls = create_agent_class(_base_config(name="weather"))
    assert cls.__name__ == "weather_Agent"


def test_create_multiple_unique_agents():
    configs = [
        _base_config(name=f"agent_{i}", description=f"Agent {i}")
        for i in range(3)
    ]
    classes = [create_agent_class(c) for c in configs]
    names = [c.name for c in classes]
    assert len(set(names)) == 3


def test_missing_name_raises():
    with pytest.raises(KeyError):
        create_agent_class({"description": "no name"})


def test_missing_description_raises():
    with pytest.raises(KeyError):
        create_agent_class({"name": "no_desc"})


def test_default_capabilities():
    cls = create_agent_class({"name": "x", "description": "x"})
    assert cls.capabilities == []


def test_manifest():
    cls = create_agent_class(_base_config())
    instance = cls()
    m = instance.manifest()
    assert m["name"] == "test_api"
    assert m["description"] == "Test API agent"
    assert m["capabilities"] == ["test"]
