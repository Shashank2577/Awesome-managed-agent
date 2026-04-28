"""Agent category taxonomy for the Atrium framework."""

from __future__ import annotations

CATEGORIES: tuple[str, ...] = (
    "research",
    "coding",
    "writing",
    "data",
    "security",
    "ops",
    "design",
    "communication",
    "analysis",
    "creative",
    "productivity",
)

VALID_CATEGORIES: frozenset[str] = frozenset(CATEGORIES)
