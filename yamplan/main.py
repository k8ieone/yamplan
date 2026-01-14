#!/usr/bin/env python3

# budget.py
# A tiny "budget compiler":
# - each item is either fixed, percent-of-parent, or leftover
# - prints amount + % of whole + % of parent

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional, Tuple

import yaml

Number = float
Node = Dict[str, Any]


def as_percent(x: Any) -> Number:
    """Accept 0.2, 20, '20%', '0.2'."""
    if x is None:
        raise ValueError("percent value is missing")

    if isinstance(x, (int, float)):
        return (x / 100.0) if x > 1 else float(x)

    if isinstance(x, str):
        s = x.strip()
        if s.endswith("%"):
            return float(s[:-1].strip()) / 100.0
        v = float(s)
        return (v / 100.0) if v > 1 else v

    raise TypeError(f"percent must be number or string, got {type(x)}")


def money(x: Any) -> Number:
    if x is None:
        raise ValueError("fixed value is missing")
    return float(x)


def node_kind(n: Node) -> str:
    flags = {
        "fixed": "fixed" in n,
        "pct": "pct" in n,
        "leftover": bool(n.get("leftover", False)),
        "sum": bool(n.get("sum", False)),
    }

    kinds = [k for k, v in flags.items() if v]

    if len(kinds) != 1:
        name = n.get("name", "<unnamed>")
        raise ValueError(
            f'Item "{name}" must define exactly one of: fixed, pct, leftover:true, sum:true'
        )

    return kinds[0]


def compute_amount(n: Node, parent_amount: Number) -> Number:
    kind = node_kind(n)

    if kind == "fixed":
        return money(n["fixed"])

    if kind == "pct":
        return parent_amount * as_percent(n["pct"])

    if kind == "leftover":
        # decided at sibling level
        return 0.0

    if kind == "sum":
        # decided after children are computed
        return 0.0

    raise AssertionError("unreachable")


def compute_tree(n: Node, parent_amount: Number, total_amount: Number) -> Node:
    out = dict(n)
    children = [dict(c) for c in out.get("items", [])]

    kind = node_kind(out)

    # First pass: compute own amount if possible
    amount = compute_amount(out, parent_amount)

    # Prepare children (but don't assign leftovers yet)
    computed_children: List[Optional[Node]] = [None] * len(children)

    leftover_indexes = [i for i, c in enumerate(children) if c.get("leftover", False)]
    if len(leftover_indexes) > 1:
        raise ValueError(f'Only one leftover allowed under "{out.get("name", "<unnamed>")}"')

    used = 0.0
    for i, c in enumerate(children):
        if c.get("leftover", False):
            continue
        cc = compute_tree(c, parent_amount=amount, total_amount=total_amount)
        computed_children[i] = cc
        used += float(cc["amount"])

    # Handle leftover child
    if leftover_indexes:
        i = leftover_indexes[0]
        remainder = max(amount - used, 0.0)
        lc = dict(children[i])
        lc["fixed"] = remainder
        lc.pop("leftover", None)
        computed_children[i] = compute_tree(lc, amount, total_amount)
        used += remainder

    # Handle sum node: amount is sum of children
    if kind == "sum":
        amount = used

    out["amount"] = amount
    out["pct_of_parent"] = (amount / parent_amount) if parent_amount else 0.0
    out["pct_of_total"] = (amount / total_amount) if total_amount else 0.0
    out["items"] = [c for c in computed_children if c is not None]

    return out


def fmt_money(x: Number) -> str:
    return f"{x:,.0f}"


def fmt_pct(p: Number) -> str:
    v = p * 100.0
    return f"{int(v)}%" if abs(v - round(v)) < 1e-9 else f"{v:.1f}%"


def print_tree(n: Node, indent: str = "") -> None:
    print(
        f"{indent}{n.get('name', '<unnamed>')}: "
        f"{fmt_money(n['amount'])} "
        f"({fmt_pct(n['pct_of_parent'])} of parent, "
        f"{fmt_pct(n['pct_of_total'])} of whole)"
    )
    for c in n.get("items", []):
        print_tree(c, indent + "  ")


def load_plan(path: str) -> Tuple[Number, Node]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    income = float(data["income"])
    root = {
        "name": data.get("name", "TOTAL"),
        "fixed": income,
        "items": data.get("items", []),
    }
    return income, root


def main() -> int:
    argv: List[str] = sys.argv
    if len(argv) != 2:
        print("Usage: python budget.py plan.yml", file=sys.stderr)
        return 2

    total, root = load_plan(argv[1])
    computed = compute_tree(root, total, total)
    print_tree(computed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
