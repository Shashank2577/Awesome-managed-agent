#!/usr/bin/env python3
"""Import agent markdown files from wshobson/agents and similar repos.

Usage:
    python3 scripts/import_wshobson.py --source /tmp/wshobson-agents
    python3 scripts/import_wshobson.py --source /tmp/awesome-claude-agents --output src/atrium/seeds/agents/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Category mapping — iterated in order, first match wins
# ---------------------------------------------------------------------------

CATEGORY_MAP: dict[str, str] = {
    # coding
    "code": "coding",
    "debug": "coding",
    "refactor": "coding",
    "engineer": "coding",
    "developer": "coding",
    "programming": "coding",
    "architect": "coding",
    # security
    "security": "security",
    "pentest": "security",
    "audit": "security",
    "threat": "security",
    "vulnerab": "security",
    "devsecops": "security",
    # writing
    "writer": "writing",
    "writing": "writing",
    "editor": "writing",
    "content": "writing",
    "copywriter": "writing",
    "documentation": "writing",
    "docs": "writing",
    # research
    "research": "research",
    "analyst": "research",
    "analysis": "research",
    "investigat": "research",
    "scientist": "research",
    # data
    "data": "data",
    "database": "data",
    "sql": "data",
    "etl": "data",
    "pipeline": "data",
    "ml": "data",
    "machine-learn": "data",
    # ops
    "devops": "ops",
    "ops": "ops",
    "infra": "ops",
    "kubernetes": "ops",
    "docker": "ops",
    "cloud": "ops",
    "deploy": "ops",
    "monitor": "ops",
    "sre": "ops",
    # design
    "design": "design",
    "ui": "design",
    "ux": "design",
    "frontend": "design",
    # communication
    "communicat": "communication",
    "pr-": "communication",
    "scrum": "communication",
    "agile": "communication",
    "product": "communication",
    "manager": "communication",
    # analysis
    "review": "analysis",
    "test": "analysis",
    "qa": "analysis",
    # creative
    "creative": "creative",
    # productivity
    "task": "productivity",
    "planner": "productivity",
    "coach": "productivity",
}

DEFAULT_MODEL = "anthropic:claude-sonnet-4-6"


def resolve_category(name: str) -> str:
    """Return the category for an agent by matching name substrings."""
    lower = name.lower()
    for keyword, category in CATEGORY_MAP.items():
        if keyword in lower:
            return category
    return "productivity"


def slugify(name: str) -> str:
    """Convert an agent name to a URL-safe slug."""
    slug = name.lower().replace(" ", "-").replace("_", "-")
    # Remove any characters that aren't alphanumeric or hyphens
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    # Collapse consecutive hyphens
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML-like frontmatter from a markdown string.

    Returns a tuple of (frontmatter_dict, body_text).  If no frontmatter block
    is found the dict is empty and the full text is the body.
    """
    if not text.startswith("---"):
        return {}, text

    # Find the closing ---
    lines = text.splitlines()
    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return {}, text

    fm_lines = lines[1:end_idx]
    body = "\n".join(lines[end_idx + 1:]).strip()

    # Simple YAML key:value parser (handles single-line values only)
    frontmatter: dict = {}
    for line in fm_lines:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        # Strip surrounding quotes if present
        if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
            value = value[1:-1]
        if key:
            frontmatter[key] = value

    return frontmatter, body


def import_file(md_path: Path, output_dir: Path) -> bool:
    """Import a single markdown agent file.  Returns True if written."""
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"  SKIP (read error): {md_path} — {exc}")
        return False

    fm, body = parse_frontmatter(text)

    # Must have a name
    raw_name: str = fm.get("name", "").strip()
    if not raw_name:
        # Fall back to filename stem
        raw_name = md_path.stem

    if not raw_name:
        print(f"  SKIP (no name): {md_path}")
        return False

    # Body must be non-trivial
    if len(body.strip()) < 50:
        print(f"  SKIP (body too short): {md_path}")
        return False

    slug = slugify(raw_name)
    if not slug:
        print(f"  SKIP (empty slug): {md_path}")
        return False

    seed_name = f"seed/{slug}"
    category = resolve_category(raw_name)
    description = fm.get("description", "").strip()
    if not description:
        # Build a short description from the first non-empty body line
        for line in body.splitlines():
            line = line.strip().lstrip("#").strip()
            if line:
                description = line[:200]
                break
    if not description:
        description = f"{raw_name} agent"

    # Derive capabilities from frontmatter tags/tools if present
    capabilities: list[str] = []
    raw_caps = fm.get("tools", fm.get("tags", fm.get("capabilities", "")))
    if raw_caps:
        caps = [c.strip() for c in re.split(r"[,\s]+", raw_caps) if c.strip()]
        capabilities = caps[:10]

    seed: dict = {
        "name": seed_name,
        "description": description,
        "agent_type": "llm",
        "category": category,
        "system_prompt": body,
        "model": DEFAULT_MODEL,
        "capabilities": capabilities,
        "seeded": True,
        "seed_version": 1,
    }

    # Write output
    cat_dir = output_dir / category
    cat_dir.mkdir(parents=True, exist_ok=True)
    out_file = cat_dir / f"{slug}.json"

    # Skip if already exists (dedup)
    if out_file.exists():
        print(f"  SKIP (already exists): {out_file.name}")
        return False

    out_file.write_text(json.dumps(seed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def run(source: Path, output: Path) -> None:
    if not source.exists():
        print(f"ERROR: source directory not found: {source}")
        sys.exit(1)

    md_files = sorted(source.rglob("*.md"))
    print(f"Found {len(md_files)} markdown files under {source}")

    written = 0
    skipped = 0

    for md_path in md_files:
        # Filter to agent files only — skip skills, commands, references, READMEs
        parts = {p.lower() for p in md_path.parts}
        if any(p in parts for p in {"skills", "commands", "references", "readme", "readme.md"}):
            continue
        if md_path.name.upper() in {"README.MD", "SKILL.MD"}:
            continue
        if "/agents/" not in str(md_path) and md_path.parent.name != "agents":
            # Accept top-level .md files too (some repos dump agents at root)
            pass

        result = import_file(md_path, output)
        if result:
            written += 1
        else:
            skipped += 1

    print(f"\nSummary: {written} written, {skipped} skipped")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import agent markdown files into Atrium seed corpus")
    parser.add_argument("--source", required=True, type=Path, help="Path to source repo root")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("src/atrium/seeds/agents/"),
        help="Output directory for seed JSON files",
    )
    args = parser.parse_args()
    run(args.source, args.output)


if __name__ == "__main__":
    main()
