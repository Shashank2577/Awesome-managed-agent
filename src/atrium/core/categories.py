"""Agent category taxonomy for the Atrium framework."""

from __future__ import annotations

from fastapi import APIRouter

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

# ---------------------------------------------------------------------------
# Router — GET /agents/categories
# ---------------------------------------------------------------------------

router = APIRouter()


@router.get("/agents/categories")
async def list_categories() -> dict:
    """Return all valid agent category values."""
    return {"categories": list(CATEGORIES)}
