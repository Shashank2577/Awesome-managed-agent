"""Per-model token pricing table. Update when providers change pricing."""
from decimal import Decimal

# Prices per 1M tokens, USD. Conservative values; trim quarterly.
PRICING_PER_MILLION: dict[str, tuple[Decimal, Decimal]] = {
    # provider:model              (input,         output)
    "anthropic:claude-sonnet-4-6": (Decimal("3"),  Decimal("15")),
    "anthropic:claude-opus-4-7":   (Decimal("15"), Decimal("75")),
    "openai:gpt-4o-mini":          (Decimal("0.15"), Decimal("0.60")),
    "openai:gpt-4o":               (Decimal("2.50"), Decimal("10")),
    "gemini:gemini-2.5-flash":     (Decimal("0.075"), Decimal("0.30")),
    "gemini:gemini-2.5-pro":       (Decimal("1.25"), Decimal("5")),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Return USD cost estimate. Returns 0 if the model isn't priced yet."""
    pricing = PRICING_PER_MILLION.get(model)
    if not pricing:
        return Decimal("0")
    in_price, out_price = pricing
    return (in_price * input_tokens + out_price * output_tokens) / Decimal("1000000")
