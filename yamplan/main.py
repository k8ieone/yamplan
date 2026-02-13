#!/usr/bin/env python3

# budget.py

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional, Tuple

import yaml

Number = float
Node = Dict[str, Any]
YamlDict = Dict[str, Any]


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
    if kind in ("leftover", "sum"):
        # decided at sibling level / after children are computed
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
        remainder = amount - used
        if remainder < -1e-9:
            raise ValueError(
                f'Overallocated under "{out.get("name", "<unnamed>")}": '
                f"allocated {used} but only had {amount}"
            )
        remainder = max(remainder, 0.0)
        lc = dict(children[i])
        lc["fixed"] = remainder
        lc.pop("leftover", None)
        computed_children[i] = compute_tree(lc, amount, total_amount)
        used += remainder
    # Handle sum node: amount is sum of children
    if kind == "sum":
        amount = used

    out["amount"] = float(amount)
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
        f"({fmt_pct(n['pct_of_total'])} of household, {fmt_pct(n['pct_of_parent'])} of parent)"
    )
    for c in n.get("items", []):
        print_tree(c, indent + "  ")


def _transfer_kind(t: Dict[str, Any]) -> str:
    flags = {"fixed": "fixed" in t, "pct": "pct" in t}
    kinds = [k for k, v in flags.items() if v]
    if len(kinds) != 1:
        raise ValueError('Transfer must define exactly one of: fixed, pct')
    return kinds[0]


def _load_yaml(path: str) -> YamlDict:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("Top-level YAML must be a mapping/object")
    return data


def load_single_user(data: YamlDict) -> Tuple[Number, Node]:
    total = float(data["income"])
    root = {
        "name": data.get("name", "TOTAL"),
        "fixed": total,
        "items": data.get("items", []),
    }
    return total, root


def load_multiuser(data: YamlDict) -> Tuple[Number, Dict[str, Node], List[Dict[str, Any]]]:
    pools_in = data.get("pools", [])
    if not isinstance(pools_in, list) or not pools_in:
        raise ValueError('"pools" must be a non-empty list')

    # Index pools and validate uniqueness
    by_name: Dict[str, Dict[str, Any]] = {}
    for p in pools_in:
        if not isinstance(p, dict):
            raise ValueError("Each pool must be an object")
        name = p.get("name")
        if not name or not isinstance(name, str):
            raise ValueError("Each pool must have a string name")
        if name in by_name:
            raise ValueError(f'Duplicate pool name "{name}"')
        by_name[name] = p

    # Gross (explicit) incomes
    explicit_income: Dict[str, Number] = {}
    for name, p in by_name.items():
        inc = p.get("income", None)
        explicit_income[name] = float(inc) if inc is not None else 0.0

    # Compute transfers based on SOURCE explicit income (gross)
    incoming: Dict[str, Number] = {name: 0.0 for name in by_name}
    outgoing: Dict[str, Number] = {name: 0.0 for name in by_name}
    transfers_report: List[Dict[str, Any]] = []

    for src_name, p in by_name.items():
        ts = p.get("transfers", [])
        if ts is None:
            ts = []
        if not isinstance(ts, list):
            raise ValueError(f'"transfers" in pool "{src_name}" must be a list')

        src_gross = explicit_income[src_name]
        for t in ts:
            if not isinstance(t, dict):
                raise ValueError(f'Each transfer in pool "{src_name}" must be an object')
            to = t.get("to")
            if not to or not isinstance(to, str):
                raise ValueError(f'Transfer in pool "{src_name}" is missing "to"')
            if to not in by_name:
                raise ValueError(f'Transfer from "{src_name}" references unknown pool "{to}"')

            kind = _transfer_kind(t)

            # Disallow pct transfers from pools that are "computed-only" (no explicit income)
            if kind == "pct" and src_gross <= 0.0 and "income" not in p:
                raise ValueError(
                    f'Pool "{src_name}" has no explicit income; pct-based transfers are not allowed'
                )

            if kind == "fixed":
                amt = money(t["fixed"])
            else:
                amt = src_gross * as_percent(t["pct"])

            if amt < -1e-9:
                raise ValueError(f'Negative transfer from "{src_name}" to "{to}" is not allowed')

            outgoing[src_name] += amt
            incoming[to] += amt

            transfers_report.append(
                {
                    "from": src_name,
                    "to": to,
                    "kind": kind,
                    "spec": t.get(kind),
                    "amount": float(amt),
                }
            )

    # Net available per pool after transfers
    net: Dict[str, Number] = {}
    for name in by_name:
        n = explicit_income[name] + incoming[name] - outgoing[name]
        if n < -1e-6:
            raise ValueError(
                f'Pool "{name}" becomes negative after transfers: {n}. '
                f"Check transfer amounts/pcts."
            )
        net[name] = float(max(n, 0.0))

    household_total = float(sum(net.values()))

    # Build pool roots for the existing allocation engine
    roots: Dict[str, Node] = {}
    for name, p in by_name.items():
        items = p.get("items", [])
        if items is None:
            items = []
        if not isinstance(items, list):
            raise ValueError(f'"items" in pool "{name}" must be a list')
        roots[name] = {
            "name": name,
            "fixed": net[name],
            "items": items,
        }

    return household_total, roots, transfers_report


def print_transfers(transfers: List[Dict[str, Any]]) -> None:
    if not transfers:
        return
    print("Transfers:")
    for t in transfers:
        spec = t["spec"]
        spec_str = f'{spec}%' if t["kind"] == "pct" and isinstance(spec, (int, float)) else str(spec)
        print(f'  {t["from"]} -> {t["to"]}: {fmt_money(t["amount"])} ({t["kind"]}={spec_str})')
    print("")


def main() -> int:
    argv: List[str] = sys.argv
    if len(argv) != 2:
        print("Usage: python budget.py plan.yml", file=sys.stderr)
        return 2

    data = _load_yaml(argv[1])

    if "pools" not in data:
        total, root = load_single_user(data)
        computed = compute_tree(root, parent_amount=total, total_amount=total)
        print_tree(computed)
        return 0

    household_total, roots, transfers = load_multiuser(data)

    print(f"Household total available: {fmt_money(household_total)}\n")
    print_transfers(transfers)

    for name in roots:
        computed = compute_tree(roots[name], parent_amount=float(roots[name]["fixed"]), total_amount=household_total)
        print_tree(computed)
        print("")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
