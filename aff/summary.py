"""Plain-language description of a RuleSet (shown under the rules panel)."""
from __future__ import annotations

from typing import Union

from .models import Field, GroupOp, Op, Rule, RuleGroup, RuleSet

_DATE_WORDS = {Op.GT: "after", Op.GTE: "on or after", Op.LT: "before", Op.LTE: "on or before",
               Op.EQUALS: "on"}
_SIZE_WORDS = {Op.GT: ">", Op.GTE: ">=", Op.LT: "<", Op.LTE: "<=", Op.EQUALS: "="}
_TEXT_WORDS = {Op.CONTAINS: "contains", Op.EQUALS: "is exactly", Op.STARTS_WITH: "starts with",
               Op.ENDS_WITH: "ends with"}


def describe_rule(r: Rule) -> str:
    f = r.field
    case = " (case-sensitive)" if r.case_sensitive and f in (
        Field.NAME, Field.EXTENSION, Field.PATH, Field.FOLDER, Field.CONTENT) else ""
    if f in (Field.HIDDEN, Field.READONLY, Field.SYSTEM):
        return f"file is {'not ' if r.op is Op.IS_FALSE else ''}{f.value}"
    if f is Field.CONTENT:
        how = "matches regex" if r.op is Op.REGEX else "contains"
        return f'content {how} "{r.value}"{case}'
    if f is Field.EXTENSION and r.op in (Op.IN_LIST, Op.EQUALS):
        items = [x.strip(". ") for x in str(r.value).replace(";", ",").replace("|", ",").split(",")]
        return "extension is " + ", ".join(x for x in items if x) + case
    if f is Field.SIZE:
        if r.op is Op.BETWEEN:
            return f"size between {r.value} and {r.value2}"
        return f"size {_SIZE_WORDS[r.op]} {r.value}"
    if f in (Field.CREATED, Field.MODIFIED):
        if r.op is Op.BETWEEN:
            return f"{f.value} between {r.value} and {r.value2}"
        return f"{f.value} {_DATE_WORDS[r.op]} {r.value}"
    # text fields
    if r.op is Op.WILDCARD:
        return f'{f.value} matches "{r.value}"{case}'
    if r.op is Op.REGEX:
        return f'{f.value} matches regex "{r.value}"{case}'
    return f'{f.value} {_TEXT_WORDS.get(r.op, r.op.value)} "{r.value}"{case}'


def _active(node: Union[Rule, RuleGroup]) -> bool:
    if not node.enabled:
        return False
    return True if isinstance(node, Rule) else any(_active(c) for c in node.children)


def _describe(node: Union[Rule, RuleGroup], nested: bool = False) -> str:
    if isinstance(node, Rule):
        return describe_rule(node)
    parts = [_describe(c, nested=True) for c in node.children if _active(c)]
    text = f" {node.operator.value.upper()} ".join(parts)
    return f"({text})" if nested and len(parts) > 1 else text


def describe_ruleset(rules: RuleSet) -> str:
    lines = []
    lines.append(f"Include files where {_describe(rules.include)}." if _active(rules.include)
                 else "Include all files.")
    if _active(rules.exclude):
        lines.append(f"Exclude files where {_describe(rules.exclude)}. Exclude always wins.")
    return " ".join(lines)
