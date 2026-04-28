"""Seed corpus utilities — iterate over bundled agent JSON files."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterator

_AGENTS_DIR = Path(__file__).parent / "agents"

logger = logging.getLogger(__name__)


def iter_seeds(source: str | Path | None = None) -> Iterator[dict]:
    """Walk the seed corpus directory and yield each config dict.

    Scans ``src/atrium/seeds/agents/**/*.json`` (recursively) and yields
    the parsed content of every file.  Invalid JSON files are skipped with
    a warning rather than crashing the caller.

    Args:
        source: Override the default corpus directory.  Useful for testing
            or for the ``atrium agents seed --source`` CLI flag.

    Yields:
        Agent config dicts, one per valid JSON file found.
    """
    directory = Path(source) if source is not None else _AGENTS_DIR

    if not directory.exists():
        return

    for json_file in sorted(directory.rglob("*.json")):
        try:
            text = json_file.read_text(encoding="utf-8")
            data = json.loads(text)
            if not isinstance(data, dict):
                logger.warning(
                    "Seed file %s does not contain a JSON object — skipping",
                    json_file,
                )
                continue
            yield data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to parse seed file %s: %s — skipping", json_file, exc)
