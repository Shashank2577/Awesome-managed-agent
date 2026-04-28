"""Per-model token pricing table. Update when providers change pricing."""
from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

# Prices per 1M tokens, USD. Conservative values; trim quarterly.
PRICING_PER_MILLION: dict[str, tuple[Decimal, Decimal]] = {
    # provider:model                         (input,             output)
    "anthropic:claude-sonnet-4-6":           (Decimal("3"),      Decimal("15")),
    "anthropic:claude-opus-4-7":             (Decimal("15"),     Decimal("75")),
    "anthropic:claude-haiku-3-5":            (Decimal("0.80"),   Decimal("4")),
    # OpenAI
    "openai:gpt-4o-mini":                    (Decimal("0.15"),   Decimal("0.60")),
    "openai:gpt-4o":                         (Decimal("2.50"),   Decimal("10")),
    "openai:gpt-4o-2024-08-06":              (Decimal("2.50"),   Decimal("10")),
    "openai:o1":                             (Decimal("15"),     Decimal("60")),
    "openai:o3-mini":                        (Decimal("1.10"),   Decimal("4.40")),
    # Gemini
    "gemini:gemini-2.5-flash":               (Decimal("0.075"),  Decimal("0.30")),
    "gemini:gemini-2.5-pro":                 (Decimal("1.25"),   Decimal("5")),
    "gemini:gemini-1.5-pro":                 (Decimal("3.50"),   Decimal("10.50")),
    # DeepSeek
    "deepseek:deepseek-chat":                (Decimal("0.27"),   Decimal("1.10")),
    "deepseek:deepseek-reasoner":            (Decimal("0.55"),   Decimal("2.19")),
    # OpenRouter — conservative average markup
    "openrouter:default":                    (Decimal("3"),      Decimal("15")),
}

_unknown_logged: set[str] = set()


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Return USD cost estimate. Returns 0 and logs a WARNING for unknown models."""
    pricing = PRICING_PER_MILLION.get(model)
    if not pricing:
        # OpenRouter passthrough: strip to provider:model and try "openrouter:default"
        provider = model.split(":", 1)[0]
        if provider == "openrouter":
            pricing = PRICING_PER_MILLION.get("openrouter:default")
        if not pricing:
            if model not in _unknown_logged:
                logger.warning(
                    "No pricing entry for model %r — cost reported as $0. "
                    "Add to pricing.PRICING_PER_MILLION.",
                    model,
                )
                _unknown_logged.add(model)
            return Decimal("0")
    in_price, out_price = pricing
    return (in_price * input_tokens + out_price * output_tokens) / Decimal("1_000_000")
