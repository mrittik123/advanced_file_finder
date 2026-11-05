"""Rule engine: compiles a RuleSet into fast matcher functions."""
from __future__ import annotations

import fnmatch
import os
import re
from typing import Callable, Union

from .content import ContentResult, file_contains, make_line_matcher
from .models import (ALLOWED_OPS, DEFAULT_CONTENT_MAX_BYTES, FileInfo, Field, GroupOp, Op, Rule,
                     RuleGroup, RuleSet, SearchStats)
from .utils import day_end, parse_size, parse_when

Matcher = Callable[[FileInfo], bool]
Compiled = tuple[int, Matcher]          # (cost, function): cheap rules run before content rules

COST_CHEAP = 1
COST_CONTENT = 100


class RuleError(ValueError):
    """A rule is invalid (bad regex, bad size, wrong operator for the field...)."""


def _label(rule: Rule) -> str:
    return f"{rule.field.value} {rule.op.value} {rule.value!r}"


def _require_value(rule: Rule) -> str:
    if rule.value is None or not str(rule.value).strip():
        raise RuleError(f"Rule '{rule.field.value} {rule.op.value}' needs a value")
    return str(rule.value)


_TEXT_GETTERS: dict[Field, Callable[[FileInfo], str]] = {
    Field.NAME: lambda i: i.name,
    Field.EXTENSION: lambda i: i.ext,
    Field.PATH: lambda i: i.path,
    Field.FOLDER: lambda i: i.folder,
}


def _text_matcher(rule: Rule) -> Matcher:
    get = _TEXT_GETTERS[rule.field]
    value = _require_value(rule)
    flags = 0 if rule.case_sensitive else re.IGNORECASE
    path_like = rule.field in (Field.PATH, Field.FOLDER)

    if rule.op is Op.REGEX:
        try:
            rx = re.compile(value, flags)
        except re.error as e:
            raise RuleError(f"Invalid regular expression {value!r}: {e}") from None
        return lambda i: rx.search(get(i)) is not None

    if rule.op is Op.WILDCARD:
        patterns = [p.strip() for p in re.split(r"[;|]", value) if p.strip()]
        if path_like:
            patterns = [p.replace("/", os.sep) for p in patterns]
        regexes = [re.compile(fnmatch.translate(p), flags) for p in patterns]
        return lambda i: any(r.match(get(i)) for r in regexes)

    if rule.op in (Op.IN_LIST, Op.EQUALS) and rule.field is Field.EXTENSION:
        items = {x.lstrip(".") for x in re.split(r"[;,|\s]+", value) if x.strip(". ")}
        if not rule.case_sensitive:
            items = {x.casefold() for x in items}
            return lambda i: i.ext.casefold() in items
        return lambda i: i.ext in items

    needle = value.replace("/", os.sep) if path_like else value
    if not rule.case_sensitive:
        needle = needle.casefold()
        prep = str.casefold
    else:
        prep = lambda s: s              # noqa: E731
    if rule.op is Op.CONTAINS:
        return lambda i: needle in prep(get(i))
    if rule.op is Op.EQUALS:
        return lambda i: prep(get(i)) == needle
    if rule.op is Op.STARTS_WITH:
        return lambda i: prep(get(i)).startswith(needle)
    if rule.op is Op.ENDS_WITH:
        return lambda i: prep(get(i)).endswith(needle)
    raise RuleError(f"Unsupported operator for {_label(rule)}")


def _size_matcher(rule: Rule) -> Matcher:
    try:
        a = parse_size(_require_value(rule))
        b = parse_size(rule.value2) if rule.op is Op.BETWEEN else None
    except ValueError as e:
        raise RuleError(str(e)) from None
    if rule.op is Op.BETWEEN:
        if rule.value2 is None or str(rule.value2).strip() == "":
            raise RuleError("A 'between' size rule needs two values")
        lo, hi = min(a, b), max(a, b)
        return lambda i: lo <= i.size <= hi
    return {
        Op.GT: lambda i: i.size > a, Op.GTE: lambda i: i.size >= a,
        Op.LT: lambda i: i.size < a, Op.LTE: lambda i: i.size <= a,
        Op.EQUALS: lambda i: i.size == a,
    }[rule.op]


def _date_matcher(rule: Rule) -> Matcher:
    attr = "created" if rule.field is Field.CREATED else "modified"
    try:
        a, a_date = parse_when(_require_value(rule))
        start_a = a.timestamp()
        end_a = day_end(a).timestamp() if a_date else start_a     # exclusive end for whole days
        if rule.op is Op.BETWEEN:
            if rule.value2 is None or str(rule.value2).strip() == "":
                raise RuleError("A 'between' date rule needs two values")
            b, b_date = parse_when(rule.value2)
            start_b = b.timestamp()
            end_b = day_end(b).timestamp() if b_date else start_b
    except ValueError as e:
        raise RuleError(str(e)) from None

    # Whole-day values (YYYY-MM-DD) are treated as the full calendar day:
    # "after 2024-01-01" means from 2 Jan onward, "on or before" includes the whole day.
    if rule.op is Op.GT:
        return (lambda i: getattr(i, attr) >= end_a) if a_date else (lambda i: getattr(i, attr) > start_a)
    if rule.op is Op.GTE:
        return lambda i: getattr(i, attr) >= start_a
    if rule.op is Op.LT:
        return lambda i: getattr(i, attr) < start_a
    if rule.op is Op.LTE:
        return (lambda i: getattr(i, attr) < end_a) if a_date else (lambda i: getattr(i, attr) <= start_a)
    if rule.op is Op.EQUALS:
        return ((lambda i: start_a <= getattr(i, attr) < end_a) if a_date
                else (lambda i: abs(getattr(i, attr) - start_a) < 1))
    if rule.op is Op.BETWEEN:
        lo = min(start_a, start_b)
        if b_date:
            hi = max(end_a if a_date else start_a, end_b)
            return lambda i: lo <= getattr(i, attr) < hi
        hi = max(start_a, start_b)
        return lambda i: lo <= getattr(i, attr) <= hi
    raise RuleError(f"Unsupported operator for {_label(rule)}")


def _attr_matcher(rule: Rule) -> Matcher:
    attr = rule.field.value                     # hidden / readonly / system
    want = rule.op is Op.IS_TRUE
    return lambda i: getattr(i, attr) == want


def _content_matcher(rule: Rule, max_bytes: int, stats: SearchStats) -> Matcher:
    try:
        line_match = make_line_matcher(rule.op, _require_value(rule), rule.case_sensitive)
    except ValueError as e:
        raise RuleError(str(e)) from None

    def match(info: FileInfo) -> bool:
        result = file_contains(info.path, line_match, max_bytes=max_bytes, size=info.size)
        if result is ContentResult.MATCH:
            return True
        if result is ContentResult.BINARY:
            stats.content_binary_skipped += 1
        elif result is ContentResult.TOO_LARGE:
            stats.content_too_large_skipped += 1
        elif result is ContentResult.ERROR:
            stats.content_errors += 1
        return False

    return match


def compile_rule(rule: Rule, max_bytes: int = DEFAULT_CONTENT_MAX_BYTES,
                 stats: SearchStats | None = None) -> Compiled:
    if rule.op not in ALLOWED_OPS[rule.field]:
        raise RuleError(f"'{rule.op.value}' cannot be used with the '{rule.field.value}' field")
    stats = stats if stats is not None else SearchStats()
    f = rule.field
    if f in _TEXT_GETTERS:
        return COST_CHEAP, _text_matcher(rule)
    if f is Field.SIZE:
        return COST_CHEAP, _size_matcher(rule)
    if f in (Field.CREATED, Field.MODIFIED):
        return COST_CHEAP, _date_matcher(rule)
    if f in (Field.HIDDEN, Field.READONLY, Field.SYSTEM):
        return COST_CHEAP, _attr_matcher(rule)
    if f is Field.CONTENT:
        return COST_CONTENT, _content_matcher(rule, max_bytes, stats)
    raise RuleError(f"Unknown field {f}")


def compile_node(node: Union[Rule, RuleGroup], max_bytes: int, stats: SearchStats) -> Compiled | None:
    """Compile a rule or group. Disabled and empty nodes return None (they are ignored)."""
    if not node.enabled:
        return None
    if isinstance(node, Rule):
        return compile_rule(node, max_bytes, stats)
    kids = [c for c in (compile_node(k, max_bytes, stats) for k in node.children) if c]
    if not kids:
        return None
    if len(kids) == 1:
        return kids[0]
    kids.sort(key=lambda c: c[0])               # AND/OR are commutative: run cheap tests first
    fns = [c[1] for c in kids]
    cost = max(c[0] for c in kids)
    if node.operator is GroupOp.AND:
        return cost, lambda i: all(f(i) for f in fns)
    return cost, lambda i: any(f(i) for f in fns)


def validate_ruleset(rules: RuleSet) -> list[str]:
    """Return a list of human-readable problems (empty list = all rules are valid)."""
    problems: list[str] = []

    def walk(node):
        if isinstance(node, RuleGroup):
            for c in node.children:
                walk(c)
            return
        try:
            compile_rule(node)
        except RuleError as e:
            problems.append(str(e))

    walk(rules.include)
    walk(rules.exclude)
    return problems


class RuleEngine:
    """matches(info) is True when the file passes the include rules and no exclude rule hits.

    No include rules = every file is included. Exclude always wins.
    """

    def __init__(self, rules: RuleSet, content_max_bytes: int = DEFAULT_CONTENT_MAX_BYTES,
                 stats: SearchStats | None = None):
        self.stats = stats if stats is not None else SearchStats()
        inc = compile_node(rules.include, content_max_bytes, self.stats)
        exc = compile_node(rules.exclude, content_max_bytes, self.stats)
        self.has_includes = inc is not None
        self.has_excludes = exc is not None
        # file passes = include AND NOT exclude; test the cheaper side first
        if inc is None and exc is None:
            self._fn: Matcher = lambda i: True
        elif exc is None:
            self._fn = inc[1]
        elif inc is None:
            ex = exc[1]
            self._fn = lambda i: not ex(i)
        else:
            inc_fn, exc_fn = inc[1], exc[1]
            if inc[0] <= exc[0]:
                self._fn = lambda i: inc_fn(i) and not exc_fn(i)
            else:
                self._fn = lambda i: not exc_fn(i) and inc_fn(i)

    def matches(self, info: FileInfo) -> bool:
        return self._fn(info)
