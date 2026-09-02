from __future__ import annotations

import re
from typing import Any


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_VALID_OPS = {"eq", "neq", "gt", "gte", "lt", "lte", "in", "like", "isnull"}


def validate_identifier(value: str, *, kind: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"invalid {kind}: {value!r}")
    return value


def normalize_order_item(item: str) -> str:
    text = item.strip()
    if not text:
        raise ValueError("invalid order_by item: empty")

    if text.startswith("-"):
        col = validate_identifier(text[1:], kind="order_by column")
        return f"{col} DESC"

    parts = text.split()
    if len(parts) == 1:
        col = validate_identifier(parts[0], kind="order_by column")
        return f"{col} ASC"
    if len(parts) == 2:
        col = validate_identifier(parts[0], kind="order_by column")
        direction = parts[1].upper()
        if direction not in {"ASC", "DESC"}:
            raise ValueError(f"invalid order_by direction: {parts[1]!r}")
        return f"{col} {direction}"

    raise ValueError(f"invalid order_by item: {item!r}")


def where_to_sql(where: dict[str, object] | None) -> tuple[str, dict[str, Any]]:
    if not where:
        return "", {}

    clauses: list[str] = []
    params: dict[str, Any] = {}

    for idx, (raw_key, value) in enumerate(where.items()):
        if "__" in raw_key:
            column, op = raw_key.rsplit("__", 1)
        else:
            column, op = raw_key, "eq"

        column = validate_identifier(column, kind="where column")
        if op not in _VALID_OPS:
            raise ValueError(f"unsupported where operator: {op!r}")

        param_key = f"w_{idx}"

        if op == "eq":
            clauses.append(f"{column} = :{param_key}")
            params[param_key] = value
        elif op == "neq":
            clauses.append(f"{column} != :{param_key}")
            params[param_key] = value
        elif op == "gt":
            clauses.append(f"{column} > :{param_key}")
            params[param_key] = value
        elif op == "gte":
            clauses.append(f"{column} >= :{param_key}")
            params[param_key] = value
        elif op == "lt":
            clauses.append(f"{column} < :{param_key}")
            params[param_key] = value
        elif op == "lte":
            clauses.append(f"{column} <= :{param_key}")
            params[param_key] = value
        elif op == "like":
            clauses.append(f"{column} LIKE :{param_key}")
            params[param_key] = value
        elif op == "isnull":
            clauses.append(f"{column} IS NULL" if bool(value) else f"{column} IS NOT NULL")
        elif op == "in":
            if not isinstance(value, (list, tuple, set)):
                raise ValueError(f"where __in expects list/tuple/set: {raw_key}")
            values = list(value)
            if len(values) == 0:
                clauses.append("1=0")
                continue
            in_names: list[str] = []
            for j, item in enumerate(values):
                key = f"{param_key}_{j}"
                params[key] = item
                in_names.append(f":{key}")
            clauses.append(f"{column} IN ({', '.join(in_names)})")

    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params
