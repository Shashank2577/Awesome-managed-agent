"""Shared input-extraction helpers for config-driven agents."""

from __future__ import annotations


def extract_query(input_data: dict) -> str:
    """Resolve the user query from *input_data* with a chain of fallbacks.

    Resolution order:
    1. ``input_data["query"]`` if present and non-empty.
    2. The first non-empty value found inside ``input_data["upstream"]`` — tries
       ``"query"``, ``"result"``, then the first 100 characters of ``str(v)``.
    3. The first 200 characters of ``str(input_data)`` as a last resort.

    Args:
        input_data: The raw input dict passed to an agent's ``run`` method.

    Returns:
        A non-empty string (best-effort), or an empty string if *input_data* is
        completely empty.
    """
    query: str = input_data.get("query", "")

    if not query:
        upstream = input_data.get("upstream", {})
        for v in upstream.values():
            if isinstance(v, dict):
                query = (
                    v.get("query", "")
                    or v.get("result", "")
                    or str(v)[:100]
                )
                break
        if not query:
            query = str(input_data)[:200]

    return query
