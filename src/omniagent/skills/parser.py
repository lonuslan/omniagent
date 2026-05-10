"""
SKILL.md parser — lightweight YAML front-matter + markdown body.

No pyyaml dependency. Handles the simple YAML subset used in SKILL.md:
  - scalar values: key: value
  - inline lists: key: [a, b, c]
  - multi-line lists (items starting with -)
  - quoted strings
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .models import SkillManifest, SkillToolConfig


def parse_skill_md(path: Path) -> SkillManifest:
    """Parse a SKILL.md file into a SkillManifest.

    Format: YAML front-matter between --- delimiters, markdown body as instructions.
    """
    text = path.read_text(encoding="utf-8")
    return parse_skill_md_text(text)


def parse_skill_md_text(text: str) -> SkillManifest:
    """Parse SKILL.md content string into a SkillManifest."""
    front_matter, body = _split_front_matter(text)
    data = _parse_yaml_simple(front_matter)
    data["instructions"] = body.strip()
    return SkillManifest.from_dict(data)


def _split_front_matter(text: str) -> tuple[str, str]:
    """Split text into (front_matter_yaml, markdown_body)."""
    text = text.lstrip()
    if not text.startswith("---"):
        return "", text

    # Find the closing ---
    end = text.find("---", 3)
    if end < 0:
        return "", text

    front_matter = text[3:end].strip()
    body = text[end + 3:].strip()
    return front_matter, body


def _parse_yaml_simple(yaml_text: str) -> dict[str, Any]:
    """Parse simple YAML key-value pairs without pyyaml.

    Supports:
      - key: scalar_value
      - key: [item1, item2, item3]
      - key:
          - item1
          - item2
      - key:
          subkey: value
      - Quoted strings: 'value' or "value"
    """
    result: dict[str, Any] = {}
    if not yaml_text:
        return result

    lines = yaml_text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        # Top-level key: value
        kv_match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_-]*)\s*:\s*(.*)$', stripped)
        if kv_match:
            key = kv_match.group(1)
            raw_value = kv_match.group(2).strip()

            if raw_value:
                result[key] = _parse_value(raw_value)
                i += 1
            else:
                # Value is on subsequent indented lines
                i += 1
                sub_lines: list[str] = []
                while i < len(lines):
                    next_line = lines[i]
                    next_stripped = next_line.strip()
                    if not next_stripped or next_stripped.startswith("#"):
                        i += 1
                        continue
                    # Check if line is indented (belongs to this key)
                    indent = len(next_line) - len(next_line.lstrip())
                    if indent > 0:
                        sub_lines.append(next_line)
                        i += 1
                    else:
                        break
                # Parse sub-lines: check if they're list items or nested kv pairs
                if sub_lines:
                    first_sub = sub_lines[0].strip()
                    if first_sub.startswith("-"):
                        result[key] = _parse_list_block(sub_lines)
                    else:
                        sub_text = "\n".join(sub_lines)
                        result[key] = _parse_yaml_simple(sub_text)
                else:
                    result[key] = {}
        else:
            i += 1

    return result


def _parse_list_block(lines: list[str]) -> list[str]:
    """Parse indented list lines (  - item)."""
    items = []
    for line in lines:
        stripped = line.strip()
        match = re.match(r'^-\s+(.+)$', stripped)
        if match:
            items.append(_unquote(match.group(1).strip()))
    return items


def _parse_value(raw: str) -> Any:
    """Parse a single YAML value."""
    # Inline list: [a, b, c]
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [_unquote(item.strip()) for item in inner.split(",")]

    # Boolean
    if raw.lower() in ("true", "yes"):
        return True
    if raw.lower() in ("false", "no"):
        return False

    # Integer
    try:
        return int(raw)
    except ValueError:
        pass

    # Float
    try:
        return float(raw)
    except ValueError:
        pass

    # String (unquote if needed)
    return _unquote(raw)


def _unquote(s: str) -> str:
    """Remove surrounding quotes from a string."""
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        return s[1:-1]
    return s
