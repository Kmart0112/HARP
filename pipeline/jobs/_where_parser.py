from __future__ import annotations

import ast


def _parse_value(raw: str) -> object:
    text = raw.strip()
    lower = text.lower()
    if lower in {"none", "null"}:
        return None
    if lower == "true":
        return True
    if lower == "false":
        return False
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return text


def parse_where_args(where_args: list[str] | None) -> dict[str, object] | None:
    if not where_args:
        return None

    where: dict[str, object] = {}
    for item in where_args:
        if "=" not in item:
            raise ValueError(f"invalid --where format: {item!r} (expected key=value)")
        key, raw_value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"invalid --where key: {item!r}")
        where[key] = _parse_value(raw_value)
    return where or None

