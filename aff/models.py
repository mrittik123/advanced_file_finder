"""Data models shared by the engine, planner, copier and UI."""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field as dc_field
from datetime import date, datetime
from enum import Enum
from typing import Any, Union


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


class Field(str, Enum):
    NAME = "name"
    EXTENSION = "extension"
    PATH = "path"          # full path of the file
    FOLDER = "folder"      # folder containing the file
    SIZE = "size"
    CREATED = "created"
    MODIFIED = "modified"
    HIDDEN = "hidden"
    READONLY = "readonly"
    SYSTEM = "system"
    CONTENT = "content"    # text inside the file


class Op(str, Enum):
    WILDCARD = "wildcard"
    REGEX = "regex"
    CONTAINS = "contains"
    EQUALS = "equals"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    IN_LIST = "in_list"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    BETWEEN = "between"
    IS_TRUE = "is_true"
    IS_FALSE = "is_false"


class GroupOp(str, Enum):
    AND = "and"
    OR = "or"


_TEXT_OPS = {Op.WILDCARD, Op.REGEX, Op.CONTAINS, Op.EQUALS, Op.STARTS_WITH, Op.ENDS_WITH}
_NUM_OPS = {Op.GT, Op.GTE, Op.LT, Op.LTE, Op.EQUALS, Op.BETWEEN}
_BOOL_OPS = {Op.IS_TRUE, Op.IS_FALSE}

ALLOWED_OPS: dict[Field, set[Op]] = {
    Field.NAME: _TEXT_OPS,
    Field.PATH: _TEXT_OPS,
    Field.FOLDER: _TEXT_OPS,
    Field.EXTENSION: {Op.IN_LIST, Op.EQUALS, Op.WILDCARD, Op.REGEX},
    Field.SIZE: _NUM_OPS,
    Field.CREATED: _NUM_OPS,
    Field.MODIFIED: _NUM_OPS,
    Field.HIDDEN: _BOOL_OPS,
    Field.READONLY: _BOOL_OPS,
    Field.SYSTEM: _BOOL_OPS,
    Field.CONTENT: {Op.CONTAINS, Op.REGEX},
}


def _jsonable(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


@dataclass
class Rule:
    field: Field
    op: Op
    value: Any = ""
    value2: Any = None            # upper bound for BETWEEN
    case_sensitive: bool = False
    enabled: bool = True
    id: str = dc_field(default_factory=_new_id)

    def to_dict(self) -> dict:
        return {
            "type": "rule", "id": self.id, "field": self.field.value, "op": self.op.value,
            "value": _jsonable(self.value), "value2": _jsonable(self.value2),
            "case_sensitive": self.case_sensitive, "enabled": self.enabled,
        }

    @staticmethod
    def from_dict(d: dict) -> "Rule":
        return Rule(
            field=Field(d["field"]), op=Op(d["op"]), value=d.get("value", ""),
            value2=d.get("value2"), case_sensitive=bool(d.get("case_sensitive", False)),
            enabled=bool(d.get("enabled", True)), id=d.get("id") or _new_id(),
        )


@dataclass
class RuleGroup:
    operator: GroupOp = GroupOp.OR
    children: list[Union[Rule, "RuleGroup"]] = dc_field(default_factory=list)
    enabled: bool = True
    id: str = dc_field(default_factory=_new_id)

    def add(self, node: Union[Rule, "RuleGroup"]):
        self.children.append(node)
        return node

    def to_dict(self) -> dict:
        return {
            "type": "group", "id": self.id, "operator": self.operator.value,
            "enabled": self.enabled, "children": [c.to_dict() for c in self.children],
        }

    @staticmethod
    def from_dict(d: dict) -> "RuleGroup":
        return RuleGroup(
            operator=GroupOp(d.get("operator", "or")),
            children=[node_from_dict(c) for c in d.get("children", [])],
            enabled=bool(d.get("enabled", True)), id=d.get("id") or _new_id(),
        )


def node_from_dict(d: dict) -> Union[Rule, RuleGroup]:
    return RuleGroup.from_dict(d) if d.get("type") == "group" else Rule.from_dict(d)


@dataclass
class RuleSet:
    """A file is selected when the include tree matches (or is empty) AND the exclude tree
    does not match. Exclude always wins."""
    include: RuleGroup = dc_field(default_factory=lambda: RuleGroup(GroupOp.OR))
    exclude: RuleGroup = dc_field(default_factory=lambda: RuleGroup(GroupOp.OR))

    def add_include(self, node):
        return self.include.add(node)

    def add_exclude(self, node):
        return self.exclude.add(node)

    def to_dict(self) -> dict:
        return {"include": self.include.to_dict(), "exclude": self.exclude.to_dict()}

    @staticmethod
    def from_dict(d: dict) -> "RuleSet":
        return RuleSet(include=RuleGroup.from_dict(d.get("include", {})),
                       exclude=RuleGroup.from_dict(d.get("exclude", {})))


@dataclass(slots=True)
class FileInfo:
    """One file found by the scanner (no content is read here)."""
    path: str
    root: str
    size: int
    created: float
    modified: float
    hidden: bool = False
    readonly: bool = False
    system: bool = False

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    @property
    def ext(self) -> str:
        return os.path.splitext(self.name)[1].lstrip(".")

    @property
    def folder(self) -> str:
        return os.path.dirname(self.path)

    @property
    def rel_path(self) -> str:
        return os.path.relpath(self.path, self.root)


DEFAULT_CONTENT_MAX_BYTES = 50 * 1024 * 1024


@dataclass
class SearchConfig:
    sources: list[str] = dc_field(default_factory=list)
    recursive: bool = True
    max_depth: int | None = None          # None = unlimited; 0 = source folder only
    rules: RuleSet = dc_field(default_factory=RuleSet)
    content_max_bytes: int = DEFAULT_CONTENT_MAX_BYTES
    follow_symlinks: bool = False

    @property
    def effective_max_depth(self) -> int | None:
        """How many levels below a source we descend. None = no limit."""
        if not self.recursive:
            return 0
        return self.max_depth

    def to_dict(self) -> dict:
        return {
            "sources": list(self.sources), "recursive": self.recursive, "max_depth": self.max_depth,
            "rules": self.rules.to_dict(), "content_max_bytes": self.content_max_bytes,
            "follow_symlinks": self.follow_symlinks,
        }

    @staticmethod
    def from_dict(d: dict) -> "SearchConfig":
        return SearchConfig(
            sources=list(d.get("sources", [])), recursive=bool(d.get("recursive", True)),
            max_depth=d.get("max_depth"), rules=RuleSet.from_dict(d.get("rules", {})),
            content_max_bytes=int(d.get("content_max_bytes", DEFAULT_CONTENT_MAX_BYTES)),
            follow_symlinks=bool(d.get("follow_symlinks", False)),
        )


@dataclass
class SearchStats:
    dirs_scanned: int = 0
    files_scanned: int = 0
    files_matched: int = 0
    content_binary_skipped: int = 0
    content_too_large_skipped: int = 0
    content_errors: int = 0
    cancelled: bool = False
    errors: list[tuple[str, str]] = dc_field(default_factory=list)   # (path, message), capped

    MAX_ERRORS = 1000

    def add_error(self, path: str, message: str) -> None:
        if len(self.errors) < self.MAX_ERRORS:
            self.errors.append((path, message))


class ConflictPolicy(str, Enum):
    SKIP = "skip"
    OVERWRITE = "overwrite"
    KEEP_BOTH = "keep_both"
    OVERWRITE_IF_NEWER = "overwrite_if_newer"


class LayoutMode(str, Enum):
    PRESERVE = "preserve"      # keep the source folder structure
    FLAT = "flat"              # all files together in the destination folder
    CUSTOM = "custom"          # build the sub-path from a pattern such as {category}/{year}/{name}


@dataclass
class OutputLayout:
    mode: LayoutMode = LayoutMode.PRESERVE
    include_source_name: bool = True          # PRESERVE: dest/<source folder name>/... or dest/...
    pattern: str = "{category}/{name}"        # CUSTOM
    date_field: str = "modified"              # CUSTOM: which date {year}/{month}/{day}/{date} use

    def to_dict(self) -> dict:
        return {"mode": self.mode.value, "include_source_name": self.include_source_name,
                "pattern": self.pattern, "date_field": self.date_field}

    @staticmethod
    def from_dict(d: dict | None) -> "OutputLayout":
        d = d or {}
        try:
            mode = LayoutMode(d.get("mode", "preserve"))
        except ValueError:
            mode = LayoutMode.PRESERVE
        return OutputLayout(mode=mode, include_source_name=bool(d.get("include_source_name", True)),
                            pattern=str(d.get("pattern") or "{category}/{name}"),
                            date_field="created" if d.get("date_field") == "created" else "modified")


class PlanStatus(str, Enum):
    NEW = "new"
    EXISTS = "exists"
    WOULD_OVERWRITE = "would overwrite"
    ERROR = "error"


@dataclass
class PlanItem:
    source: FileInfo
    dest: str
    status: PlanStatus
    selected: bool = True
    note: str = ""


@dataclass
class CopyPlan:
    destination: str
    policy: ConflictPolicy
    items: list[PlanItem] = dc_field(default_factory=list)

    @property
    def selected_items(self) -> list[PlanItem]:
        return [i for i in self.items if i.selected]

    @property
    def selected_size(self) -> int:
        return sum(i.source.size for i in self.items if i.selected)

    def count(self, status: PlanStatus) -> int:
        return sum(1 for i in self.items if i.status is status)
