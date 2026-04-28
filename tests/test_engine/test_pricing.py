"""Phase 4 pricing table tests — all providers, unknown model warning."""
import logging
from decimal import Decimal

import pytest

from atrium.engine.pricing import PRICING_PER_MILLION, estimate_cost, _unknown_logged


def test_all_phase4_models_are_priced():
    required = [
        "anthropic:claude-sonnet-4-6",
        "openai:gpt-4o-2024-08-06",
        "openai:o1",
        "openai:o3-mini",
        "gemini:gemini-2.5-pro",
        "gemini:gemini-2.5-flash",
        "deepseek:deepseek-chat",
        "deepseek:deepseek-reasoner",
        "openrouter:default",
    ]
    for model in required:
        assert model in PRICING_PER_MILLION, f"Missing pricing for {model}"


def test_estimate_cost_anthropic():
    cost = estimate_cost("anthropic:claude-sonnet-4-6", 1_000_000, 0)
    assert cost == Decimal("3")


def test_estimate_cost_deepseek_chat():
    cost = estimate_cost("deepseek:deepseek-chat", 0, 1_000_000)
    assert cost == Decimal("1.10")


def test_estimate_cost_openai_o1():
    cost = estimate_cost("openai:o1", 1_000_000, 0)
    assert cost == Decimal("15")


def test_estimate_cost_openrouter_default():
    cost = estimate_cost("openrouter:default", 1_000_000, 0)
    assert cost == Decimal("3")


def test_estimate_cost_unknown_openrouter_model_uses_default():
    # openrouter:some-new-model → falls through to openrouter:default
    cost = estimate_cost("openrouter:some-new-model-xyz", 1_000_000, 0)
    assert cost == Decimal("3")


def test_estimate_cost_unknown_model_returns_zero_and_warns(caplog):
    _unknown_logged.discard("unknown:model-xyz")
    with caplog.at_level(logging.WARNING, logger="atrium.engine.pricing"):
        cost = estimate_cost("unknown:model-xyz", 100, 100)
    assert cost == Decimal("0")
    assert any("unknown:model-xyz" in r.message for r in caplog.records)


def test_estimate_cost_unknown_model_warns_only_once(caplog):
    _unknown_logged.discard("unknown:warn-once-test")
    with caplog.at_level(logging.WARNING, logger="atrium.engine.pricing"):
        estimate_cost("unknown:warn-once-test", 1, 1)
        estimate_cost("unknown:warn-once-test", 1, 1)
    warnings = [r for r in caplog.records if "warn-once-test" in r.message]
    assert len(warnings) == 1
