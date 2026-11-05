"""State shared by all wizard steps."""
from __future__ import annotations

import json

from ..models import (ConflictPolicy, CopyPlan, FileInfo, OutputLayout, RuleSet, SearchConfig, SearchStats)
from ..planner import build_plan, carry_selection
from ..settings import Settings

POLICY_LABELS = {
    ConflictPolicy.KEEP_BOTH: "Keep both (rename the new copy)",
    ConflictPolicy.SKIP: "Skip existing files",
    ConflictPolicy.OVERWRITE: "Overwrite existing files",
    ConflictPolicy.OVERWRITE_IF_NEWER: "Overwrite only if source is newer",
}


class WizardState:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.sources: list[str] = list(settings.sources)
        self.recursive = settings.recursive
        self.max_depth = settings.max_depth
        self.destination = settings.destination
        try:
            self.policy = ConflictPolicy(settings.conflict_policy)
        except ValueError:
            self.policy = ConflictPolicy.KEEP_BOTH
        try:
            self.rules = RuleSet.from_dict(settings.rules) if settings.rules else RuleSet()
        except (KeyError, ValueError, TypeError):
            self.rules = RuleSet()
        self.layout = OutputLayout.from_dict(settings.layout)
        self.undo_stack: list[dict] = []
        self.found: list[FileInfo] = []
        self.plan: CopyPlan | None = None
        self.stats = SearchStats()
        self.signature: str | None = None       # what the current results were built from

    def config(self) -> SearchConfig:
        return SearchConfig(sources=list(self.sources), recursive=self.recursive,
                            max_depth=self.max_depth, rules=self.rules,
                            content_max_bytes=self.settings.content_max_mb * 1024 * 1024)

    def signature_now(self) -> str:
        return json.dumps([self.config().to_dict(), self.destination, self.policy.value, self.layout.to_dict()],
                          sort_keys=True, default=str)

    def make_plan(self, files=None, cancel=None) -> CopyPlan:
        return build_plan(self.found if files is None else files, self.destination, self.sources,
                          self.policy, cancel, self.layout)

    def replan(self, cancel=None) -> CopyPlan:
        """Rebuild destination paths for the files already found (after a layout change)."""
        new = self.make_plan(cancel=cancel)
        if self.plan is not None:
            carry_selection(self.plan, new)
        self.plan = new
        self.signature = self.signature_now()
        return new

    def invalidate_results(self) -> None:
        self.signature = None

    # ---- undo for rule edits ----
    def push_undo(self) -> None:
        self.undo_stack.append(self.rules.to_dict())
        del self.undo_stack[:-100]

    def undo(self) -> bool:
        if not self.undo_stack:
            return False
        self.rules = RuleSet.from_dict(self.undo_stack.pop())
        return True

    def save_into_settings(self) -> Settings:
        s = self.settings
        s.sources, s.recursive, s.max_depth = list(self.sources), self.recursive, self.max_depth
        s.destination, s.conflict_policy = self.destination, self.policy.value
        s.layout = self.layout.to_dict()
        s.rules = self.rules.to_dict()
        return s
