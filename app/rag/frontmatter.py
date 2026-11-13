"""YAML front matter parsing for the knowledge base documents."""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

import yaml

_FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value).strip() or None


def split_front_matter(raw: str) -> tuple[dict[str, Any], str, str | None]:
    """Return ``(front_matter, body, error)``.

    The parser is deliberately strict about YAML errors but forgiving when front
    matter is absent, so the audit can report it as a data quality issue.
    """

    raw = raw.lstrip("\ufeff")
    match = _FRONT_MATTER_RE.match(raw)
    if not match:
        return {}, raw.strip(), "front matter tidak ditemukan"

    try:
        parsed = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - message is enough
        return {}, raw[match.end() :].strip(), f"YAML tidak valid: {exc}"

    if not isinstance(parsed, dict):
        return {}, raw[match.end() :].strip(), "front matter bukan mapping YAML"

    normalized: dict[str, Any] = {}
    for key, value in parsed.items():
        if key in {"last_updated", "effective_date"}:
            normalized[key] = _iso(value)
        else:
            normalized[key] = value

    return normalized, raw[match.end() :].strip(), None
