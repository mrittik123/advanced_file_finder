"""Command-line search + dry-run plan. Lets you verify the engine before any UI exists.

Examples:
  python -m aff -s C:\\Photos -d D:\\Backup -i extension:in_list:jpg,png -x folder:contains:thumbs
  python -m aff -s . -d ./out -i size:between:1MB..10MB -i content:contains:invoice --include-mode and
  python -m aff -s . -d ./out --rules-file examples/rules_example.json
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from collections import Counter

from .layout import PRESETS, validate_pattern
from .models import (ConflictPolicy, Field, GroupOp, LayoutMode, Op, OutputLayout, Rule, RuleSet,
                     SearchConfig, SearchStats)
from .planner import build_plan, check_free_space, validate_destination
from .rules import validate_ruleset
from .search import run_search
from .summary import describe_ruleset
from .utils import format_size, parse_size


def parse_rule_spec(spec: str) -> tuple[bool, Rule]:
    """'+name:wildcard:*.jpg' -> (include=True, Rule). Use '-' for exclude, 'a..b' for between."""
    if not spec or spec[0] not in "+-":
        raise ValueError(f"rule must start with + or -: {spec!r}")
    try:
        field_s, op_s, value = spec[1:].split(":", 2)
        field, op = Field(field_s.strip().lower()), Op(op_s.strip().lower())
    except ValueError:
        raise ValueError(f"bad rule {spec!r}; expected [+|-]field:operator:value") from None
    value2 = None
    if op is Op.BETWEEN:
        if ".." not in value:
            raise ValueError(f"'between' needs a..b, got {value!r}")
        value, value2 = value.split("..", 1)
    return spec[0] == "+", Rule(field, op, value, value2)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aff", description="Advanced File Finder (search + dry-run plan)")
    p.add_argument("-s", "--source", action="append", default=[], help="source folder (repeatable)")
    p.add_argument("-d", "--dest", default="", help="destination folder (for the plan)")
    p.add_argument("--no-recursive", action="store_true", help="search only the source folder itself")
    p.add_argument("--max-depth", type=int, default=None, help="levels below each source (0 = source only)")
    p.add_argument("-i", "--include", action="append", default=[], metavar="RULE",
                   help="include rule field:operator:value (repeatable), e.g. -i extension:in_list:jpg,png")
    p.add_argument("-x", "--exclude", action="append", default=[], metavar="RULE",
                   help="exclude rule field:operator:value (repeatable), e.g. -x folder:contains:node_modules")
    p.add_argument("-r", "--rule", action="append", default=[], metavar="SPEC",
                   help="same as -i/-x but with a sign: --rule=+name:wildcard:*.jpg  --rule=-hidden:is_true:")
    p.add_argument("--rules-file", help="JSON file with a full RuleSet (supports nested AND/OR groups)")
    p.add_argument("--include-mode", choices=["and", "or"], default="or")
    p.add_argument("--exclude-mode", choices=["and", "or"], default="or")
    p.add_argument("--case-sensitive", action="store_true")
    p.add_argument("--content-max", default="50MB", help="skip content search in files above this size")
    p.add_argument("--policy", choices=[c.value for c in ConflictPolicy], default="keep_both")
    p.add_argument("--layout", choices=[m.value for m in LayoutMode], default="preserve",
                   help="preserve the folder structure, put all files in one folder (flat), or use a --pattern")
    p.add_argument("--pattern", default="{category}/{name}",
                   help="custom layout, e.g. {ext}/{year}/{name}. Ready-made: " + "; ".join(PRESETS.values()))
    p.add_argument("--no-source-folder", action="store_true",
                   help="preserve layout: do not add a folder named after each source")
    p.add_argument("--date-field", choices=["modified", "created"], default="modified")
    p.add_argument("--limit", type=int, default=50, help="rows to print (0 = all)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.source:
        print("Give at least one source folder with -s", file=sys.stderr)
        return 2
    try:
        if args.rules_file:
            with open(args.rules_file, encoding="utf-8") as fh:
                rules = RuleSet.from_dict(json.load(fh))
        else:
            rules = RuleSet()
            rules.include.operator = GroupOp(args.include_mode)
            rules.exclude.operator = GroupOp(args.exclude_mode)
        specs = ["+" + x for x in args.include] + ["-" + x for x in args.exclude] + args.rule
        for spec in specs:
            include, rule = parse_rule_spec(spec)
            rule.case_sensitive = args.case_sensitive
            (rules.add_include if include else rules.add_exclude)(rule)
        config = SearchConfig(sources=args.source, recursive=not args.no_recursive,
                              max_depth=args.max_depth, rules=rules,
                              content_max_bytes=parse_size(args.content_max))
    except (ValueError, OSError, KeyError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    layout = OutputLayout(LayoutMode(args.layout), not args.no_source_folder, args.pattern, args.date_field)
    if layout.mode is LayoutMode.CUSTOM:
        bad = validate_pattern(layout.pattern)
        if bad:
            print("Pattern problem: " + " ".join(bad), file=sys.stderr)
            return 2

    problems = validate_ruleset(rules)
    if problems:
        print("Rule problems:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 2

    print(describe_ruleset(rules))
    stats = SearchStats()
    try:
        files = run_search(config, threading.Event(), stats)
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130

    print(f"\nScanned {stats.files_scanned} files in {stats.dirs_scanned} folders; "
          f"{len(files)} match ({format_size(sum(f.size for f in files))}).")
    if stats.content_binary_skipped or stats.content_too_large_skipped:
        print(f"Content search skipped {stats.content_binary_skipped} binary and "
              f"{stats.content_too_large_skipped} oversized files.")
    for path, msg in stats.errors[:10]:
        print(f"  ! {path}: {msg}")

    if args.dest:
        errs = validate_destination(args.source, args.dest)
        if errs:
            print("\n".join(errs), file=sys.stderr)
            return 1
        plan = build_plan(files, args.dest, args.source, ConflictPolicy(args.policy), layout=layout)
        counts = Counter(i.status.value for i in plan.items)
        print(f"Plan: {dict(counts)}; to copy {len(plan.selected_items)} files, "
              f"{format_size(plan.selected_size)}")
        print(check_free_space(plan).message())
        rows = plan.items if args.limit == 0 else plan.items[: args.limit]
        for i in rows:
            print(f"  [{i.status.value:<15}] {format_size(i.source.size):>9}  {i.source.path}  ->  {i.dest}")
    else:
        rows = files if args.limit == 0 else files[: args.limit]
        for f in rows:
            print(f"  {format_size(f.size):>9}  {f.path}")
    if args.limit and len(files) > args.limit:
        print(f"  ... and {len(files) - args.limit} more (use --limit 0 for all)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
