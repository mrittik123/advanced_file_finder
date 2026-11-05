"""Step 2: include / exclude rules with AND/OR groups, quick-add chips, undo and a live summary."""
from __future__ import annotations

from datetime import date, timedelta

import customtkinter as ctk

from ..models import ALLOWED_OPS, Field, GroupOp, Op, Rule, RuleGroup
from ..rules import validate_ruleset
from ..summary import describe_ruleset
from .step_base import Step
from .widgets import Card, col

FIELD_LABELS = {
    Field.NAME: "File name", Field.EXTENSION: "Extension", Field.PATH: "Full path",
    Field.FOLDER: "Folder", Field.SIZE: "Size", Field.CREATED: "Created date",
    Field.MODIFIED: "Modified date", Field.HIDDEN: "Hidden", Field.READONLY: "Read-only",
    Field.SYSTEM: "System file", Field.CONTENT: "Text inside file",
}
_TEXT = [Op.WILDCARD, Op.CONTAINS, Op.STARTS_WITH, Op.ENDS_WITH, Op.EQUALS, Op.REGEX]
_NUM = [Op.GT, Op.GTE, Op.LT, Op.LTE, Op.EQUALS, Op.BETWEEN]
OP_ORDER = {
    Field.NAME: _TEXT, Field.PATH: _TEXT, Field.FOLDER: _TEXT,
    Field.EXTENSION: [Op.IN_LIST, Op.WILDCARD, Op.REGEX],
    Field.SIZE: _NUM, Field.CREATED: _NUM, Field.MODIFIED: _NUM,
    Field.HIDDEN: [Op.IS_TRUE, Op.IS_FALSE], Field.READONLY: [Op.IS_TRUE, Op.IS_FALSE],
    Field.SYSTEM: [Op.IS_TRUE, Op.IS_FALSE], Field.CONTENT: [Op.CONTAINS, Op.REGEX],
}
_TEXT_OP_LABELS = {Op.WILDCARD: "matches wildcard", Op.REGEX: "matches regex", Op.CONTAINS: "contains",
                   Op.EQUALS: "equals", Op.STARTS_WITH: "starts with", Op.ENDS_WITH: "ends with",
                   Op.IN_LIST: "is one of"}
_SIZE_OP_LABELS = {Op.GT: "bigger than", Op.GTE: "at least", Op.LT: "smaller than", Op.LTE: "at most",
                   Op.EQUALS: "exactly", Op.BETWEEN: "between"}
_DATE_OP_LABELS = {Op.GT: "after", Op.GTE: "on or after", Op.LT: "before", Op.LTE: "on or before",
                   Op.EQUALS: "on", Op.BETWEEN: "between"}
PLACEHOLDERS = {
    Field.NAME: "e.g. *.jpg; report_*", Field.EXTENSION: "e.g. jpg, png", Field.PATH: "e.g. *\\2024\\*",
    Field.FOLDER: "e.g. node_modules", Field.SIZE: "e.g. 10MB", Field.CREATED: "YYYY-MM-DD",
    Field.MODIFIED: "YYYY-MM-DD", Field.CONTENT: "text to find",
}
BOOL_FIELDS = (Field.HIDDEN, Field.READONLY, Field.SYSTEM)


def op_label(field: Field, op: Op) -> str:
    if field in BOOL_FIELDS:
        return "is set" if op is Op.IS_TRUE else "is not set"
    if field is Field.SIZE:
        return _SIZE_OP_LABELS[op]
    if field in (Field.CREATED, Field.MODIFIED):
        return _DATE_OP_LABELS[op]
    return _TEXT_OP_LABELS[op]


def _op_values(field: Field) -> list[str]:
    return [op_label(field, o) for o in OP_ORDER[field] if o in ALLOWED_OPS[field]]


COMPACT_ROW = 640


class RuleRow(ctk.CTkFrame):
    def __init__(self, master, step: "RulesStep", parent: RuleGroup, rule: Rule):
        super().__init__(master, corner_radius=8, fg_color=("gray88", "gray21"))
        self.step, self.parent, self.rule = step, parent, rule
        self._compact = None
        self._burst = False
        self.en = ctk.CTkCheckBox(self, text="", width=24, checkbox_width=20, checkbox_height=20,
                                  command=self._toggle_enabled)
        self.en.select() if rule.enabled else self.en.deselect()
        self.field_menu = ctk.CTkOptionMenu(self, values=list(FIELD_LABELS.values()), width=130,
                                            command=self._field_changed, dynamic_resizing=False)
        self.field_menu.set(FIELD_LABELS[rule.field])
        self.op_menu = ctk.CTkOptionMenu(self, values=_op_values(rule.field), width=150,
                                         command=self._op_changed, dynamic_resizing=False)
        self.op_menu.set(op_label(rule.field, rule.op))
        self.val = ctk.CTkEntry(self, placeholder_text=PLACEHOLDERS.get(rule.field, ""))
        self.val2 = ctk.CTkEntry(self, width=120, placeholder_text="to…")
        if rule.value not in (None, ""):
            self.val.insert(0, str(rule.value))
        if rule.value2 not in (None, ""):
            self.val2.insert(0, str(rule.value2))
        for e, attr in ((self.val, "value"), (self.val2, "value2")):
            e.bind("<FocusIn>", lambda _e: setattr(self, "_burst", False), add="+")
            e.bind("<KeyRelease>", lambda _e, e=e, a=attr: self._typed(e, a), add="+")
        self.case = ctk.CTkCheckBox(self, text="Aa", width=52, checkbox_width=18, checkbox_height=18,
                                    command=self._toggle_case)
        self.case.select() if rule.case_sensitive else self.case.deselect()
        self.btns = ctk.CTkFrame(self, fg_color="transparent")
        for i, (txt, cmd) in enumerate((("⧉", self._dup), ("▲", lambda: self._move(-1)),
                                        ("▼", lambda: self._move(1)), ("✕", self._delete))):
            ctk.CTkButton(self.btns, text=txt, width=28, height=28, fg_color="transparent",
                          text_color=("gray20", "gray85"), hover_color=("gray72", "gray35"),
                          command=cmd).grid(row=0, column=i, padx=1)
        self._sync_visibility()
        self._layout(False)
        self.bind("<Configure>", self._on_configure)

    # ---- layout: one line when wide, two lines when narrow
    def _on_configure(self, event) -> None:
        compact = event.width < COMPACT_ROW
        if compact != self._compact:
            self._layout(compact)

    def _layout(self, compact: bool) -> None:
        self._compact = compact
        for w in (self.en, self.field_menu, self.op_menu, self.val, self.val2, self.case, self.btns):
            w.grid_forget()
        for c in range(8):
            self.grid_columnconfigure(c, weight=0)
        pad = dict(padx=4, pady=4)
        self.en.grid(row=0, column=0, **pad)
        self.field_menu.grid(row=0, column=1, **pad)
        self.op_menu.grid(row=0, column=2, **pad)
        if compact:
            self.grid_columnconfigure(3, weight=1)
            self.btns.grid(row=0, column=3, sticky="e", **pad)
            self.val.grid(row=1, column=1, columnspan=2, sticky="ew", **pad)
            self.val2.grid(row=1, column=3, sticky="w", **pad)
            self.case.grid(row=1, column=4, **pad)
        else:
            self.grid_columnconfigure(3, weight=1)
            self.val.grid(row=0, column=3, sticky="ew", **pad)
            self.val2.grid(row=0, column=4, **pad)
            self.case.grid(row=0, column=5, **pad)
            self.btns.grid(row=0, column=6, **pad)
        self._sync_visibility()

    def _sync_visibility(self) -> None:
        r = self.rule
        needs_value = r.field not in BOOL_FIELDS
        for w, show in ((self.val, needs_value), (self.val2, needs_value and r.op is Op.BETWEEN),
                        (self.case, r.field in (Field.NAME, Field.EXTENSION, Field.PATH, Field.FOLDER,
                                               Field.CONTENT))):
            if show:
                w.grid()
            else:
                w.grid_remove()

    # ---- editing
    def _toggle_enabled(self) -> None:
        self.step.edit()
        self.rule.enabled = bool(self.en.get())
        self.step.changed()

    def _toggle_case(self) -> None:
        self.step.edit()
        self.rule.case_sensitive = bool(self.case.get())
        self.step.changed()

    def _field_changed(self, label: str) -> None:
        self.step.edit()
        self.rule.field = next(f for f, lbl in FIELD_LABELS.items() if lbl == label)
        self.rule.op = OP_ORDER[self.rule.field][0]
        self.rule.value, self.rule.value2 = "", None
        self.step.rebuild()

    def _op_changed(self, label: str) -> None:
        self.step.edit()
        self.rule.op = next(o for o in OP_ORDER[self.rule.field] if op_label(self.rule.field, o) == label)
        self.step.rebuild()

    def _typed(self, entry, attr: str) -> None:
        if not self._burst:
            self.step.edit()
            self._burst = True
        setattr(self.rule, attr, entry.get())
        self.step.changed()

    def _dup(self) -> None:
        self.step.edit()
        copy = Rule.from_dict({**self.rule.to_dict(), "id": None})
        self.parent.children.insert(self.parent.children.index(self.rule) + 1, copy)
        self.step.rebuild()

    def _move(self, delta: int) -> None:
        kids = self.parent.children
        i = kids.index(self.rule)
        j = i + delta
        if 0 <= j < len(kids):
            self.step.edit()
            kids[i], kids[j] = kids[j], kids[i]
            self.step.rebuild()

    def _delete(self) -> None:
        self.step.edit()
        self.parent.children.remove(self.rule)
        self.step.rebuild()


class GroupView(ctk.CTkFrame):
    """Renders one RuleGroup: its AND/OR switch, its rules and nested groups."""

    def __init__(self, master, step: "RulesStep", group: RuleGroup, parent: RuleGroup | None = None):
        nested = parent is not None
        super().__init__(master, corner_radius=10, fg_color=("gray95", "gray16") if nested else "transparent",
                         border_width=1 if nested else 0, border_color=("gray75", "gray35"))
        self.step, self.group, self.parent = step, group, parent
        self.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 2))
        head.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(head, text="Group · match" if nested else "Match", text_color=("gray35", "gray65")
                     ).grid(row=0, column=0, padx=(2, 6))
        self.seg = ctk.CTkSegmentedButton(head, values=["Any (OR)", "All (AND)"], command=self._op_changed)
        self.seg.set("All (AND)" if group.operator is GroupOp.AND else "Any (OR)")
        self.seg.grid(row=0, column=1, sticky="w")
        if nested:
            ctk.CTkButton(head, text="Remove group", width=100, height=26, fg_color="transparent",
                          border_width=1, text_color=("gray20", "gray85"),
                          command=self._remove).grid(row=0, column=3, sticky="e")
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="ew", padx=(10 if nested else 0, 6 if nested else 0))
        body.grid_columnconfigure(0, weight=1)
        for i, child in enumerate(group.children):
            w = (RuleRow(body, step, group, child) if isinstance(child, Rule)
                 else GroupView(body, step, child, group))
            w.grid(row=i, column=0, sticky="ew", pady=3)
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=2, column=0, sticky="w", padx=6, pady=(2, 8))
        ctk.CTkButton(foot, text="＋ Rule", width=84, height=28, command=self._add_rule).grid(row=0, column=0)
        ctk.CTkButton(foot, text="＋ Group", width=90, height=28, fg_color=("gray75", "gray30"),
                      text_color=("gray10", "gray95"), hover_color=("gray65", "gray40"),
                      command=self._add_group).grid(row=0, column=1, padx=6)

    def _op_changed(self, label: str) -> None:
        self.step.edit()
        self.group.operator = GroupOp.AND if label.startswith("All") else GroupOp.OR
        self.step.changed()

    def _add_rule(self) -> None:
        self.step.edit()
        self.group.add(Rule(Field.NAME, Op.WILDCARD, ""))
        self.step.rebuild()

    def _add_group(self) -> None:
        self.step.edit()
        g = self.group.add(RuleGroup(GroupOp.AND))
        g.add(Rule(Field.NAME, Op.WILDCARD, ""))
        self.step.rebuild()

    def _remove(self) -> None:
        self.step.edit()
        self.parent.children.remove(self.group)
        self.step.rebuild()


def _images() -> list[Rule]:
    return [Rule(Field.EXTENSION, Op.IN_LIST, "jpg,jpeg,png,gif,bmp,webp,heic,tif,tiff")]


CHIPS = [
    ("＋ Images", "include", lambda: _images()),
    ("＋ Documents", "include", lambda: [Rule(Field.EXTENSION, Op.IN_LIST, "pdf,doc,docx,xls,xlsx,ppt,pptx,txt,rtf,odt")]),
    ("＋ Videos", "include", lambda: [Rule(Field.EXTENSION, Op.IN_LIST, "mp4,mkv,avi,mov,wmv,flv,webm")]),
    ("＋ Audio", "include", lambda: [Rule(Field.EXTENSION, Op.IN_LIST, "mp3,wav,flac,aac,m4a,ogg")]),
    ("＋ Archives", "include", lambda: [Rule(Field.EXTENSION, Op.IN_LIST, "zip,rar,7z,tar,gz")]),
    ("＋ Over 100 MB", "include", lambda: [Rule(Field.SIZE, Op.GT, "100MB")]),
    ("＋ Last 30 days", "include", lambda: [Rule(Field.MODIFIED, Op.GTE, (date.today() - timedelta(days=30)).isoformat())]),
    ("− Hidden files", "exclude", lambda: [Rule(Field.HIDDEN, Op.IS_TRUE)]),
    ("− System files", "exclude", lambda: [Rule(Field.SYSTEM, Op.IS_TRUE)]),
    ("− Temp files", "exclude", lambda: [Rule(Field.NAME, Op.WILDCARD, "~*;*.tmp;*.bak;Thumbs.db")]),
    ("− node_modules & .git", "exclude", lambda: [Rule(Field.FOLDER, Op.CONTAINS, "node_modules"),
                                                  Rule(Field.FOLDER, Op.CONTAINS, ".git")]),
]
WIDE_PANELS = 1000
CHIP_W = 150


class RulesStep(Step):
    title = "Rules"

    def __init__(self, master, wizard):
        super().__init__(master, wizard)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._wide = None

        top = Card(self, "What should be found?",
                   "Include rules choose files, exclude rules remove them again - exclude always wins. "
                   "With no include rules, every file is included.")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.top = top
        bar = ctk.CTkFrame(top, fg_color="transparent")
        bar.grid(row=top.next_row(), column=0, sticky="ew", padx=12, pady=(0, 10))
        self.chips_frame = ctk.CTkFrame(bar, fg_color="transparent")
        self.chips_frame.grid(row=0, column=0, sticky="ew")
        bar.grid_columnconfigure(0, weight=1)
        self.chips = []
        for label, kind, make in CHIPS:
            exclude = kind == "exclude"
            b = ctk.CTkButton(self.chips_frame, text=label, height=28, width=CHIP_W - 10,
                              fg_color=("#fde2e2", "#4a2323") if exclude else ("#dbe7fd", "#26344f"),
                              text_color=("#7f1d1d", "#fca5a5") if exclude else ("#1e3a8a", "#bcd2ff"),
                              hover_color=("#fbc7c7", "#633030") if exclude else ("#c3d6fb", "#34456a"),
                              command=lambda k=kind, m=make: self._chip(k, m()))
            self.chips.append(b)
        self.undo_btn = ctk.CTkButton(bar, text="↶ Undo", width=80, height=28, fg_color=("gray75", "gray30"),
                                      text_color=("gray10", "gray95"), hover_color=("gray65", "gray40"),
                                      command=self.undo)
        self.undo_btn.grid(row=0, column=1, sticky="ne", padx=(8, 0))

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.grid(row=1, column=0, sticky="nsew")
        self.scroll.grid_columnconfigure(0, weight=1, uniform="p")
        self.scroll.grid_columnconfigure(1, weight=1, uniform="p")
        self.inc_card = Card(self.scroll, "＋  Include files that match")
        self.exc_card = Card(self.scroll, "−  Exclude files that match  (always wins)")
        self.inc_holder = ctk.CTkFrame(self.inc_card, fg_color="transparent")
        self.inc_holder.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))
        self.exc_holder = ctk.CTkFrame(self.exc_card, fg_color="transparent")
        self.exc_holder.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))
        for h in (self.inc_holder, self.exc_holder):
            h.grid_columnconfigure(0, weight=1)

        self.summary_card = Card(self)
        self.summary_card.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.summary = ctk.CTkLabel(self.summary_card, text="", anchor="w", justify="left", wraplength=700)
        self.summary.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 2))
        self.problem = ctk.CTkLabel(self.summary_card, text="", anchor="w", justify="left", wraplength=700,
                                    text_color=("#b91c1c", "#f87171"))
        self.problem.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))
        self._arrange(True)
        self._reflow_chips(1000)

    # ------------------------------------------------------------- model ops
    def edit(self) -> None:
        """Called just before every change so it can be undone."""
        self.state.push_undo()
        self._update_undo()

    def changed(self) -> None:
        self.update_summary()

    def undo(self) -> None:
        if self.state.undo():
            self.rebuild()

    def _chip(self, kind: str, rules: list[Rule]) -> None:
        self.edit()
        group = self.state.rules.include if kind == "include" else self.state.rules.exclude
        for r in rules:
            group.add(r)
        self.rebuild()

    def _update_undo(self) -> None:
        self.undo_btn.configure(state="normal" if self.state.undo_stack else "disabled")

    # ---------------------------------------------------------------- render
    def rebuild(self) -> None:
        for holder in (self.inc_holder, self.exc_holder):
            for child in holder.winfo_children():
                child.destroy()
        GroupView(self.inc_holder, self, self.state.rules.include).grid(row=0, column=0, sticky="ew")
        GroupView(self.exc_holder, self, self.state.rules.exclude).grid(row=0, column=0, sticky="ew")
        self.update_summary()
        self._update_undo()

    def update_summary(self) -> None:
        rules = self.state.rules
        self.summary.configure(text="In words:  " + describe_ruleset(rules))
        problems = validate_ruleset(rules)
        self.problem.configure(text=("⚠  " + "\n⚠  ".join(problems[:3])) if problems else "")

    def _arrange(self, wide: bool) -> None:
        if wide == self._wide:
            return
        self._wide = wide
        self.inc_card.grid_forget()
        self.exc_card.grid_forget()
        if wide:
            self.inc_card.grid(row=0, column=0, sticky="new", padx=(0, 6), pady=2)
            self.exc_card.grid(row=0, column=1, sticky="new", padx=(6, 0), pady=2)
        else:
            self.inc_card.grid(row=0, column=0, columnspan=2, sticky="ew", pady=2)
            self.exc_card.grid(row=1, column=0, columnspan=2, sticky="ew", pady=2)

    def _reflow_chips(self, width: int) -> None:
        per_row = max(1, (width - 150) // CHIP_W)
        for b in self.chips:
            b.grid_forget()
        for i, b in enumerate(self.chips):
            b.grid(row=i // per_row, column=i % per_row, padx=3, pady=3, sticky="w")

    def on_resize(self, width: int) -> None:
        self._arrange(width >= WIDE_PANELS)
        self._reflow_chips(width)
        wrap = max(200, width - 90)
        self.summary.configure(wraplength=wrap)
        self.problem.configure(wraplength=wrap)
        self.top.set_wrap(wrap)

    def on_enter(self, forward: bool) -> None:
        self.rebuild()

    def validate(self) -> str | None:
        problems = validate_ruleset(self.state.rules)
        return problems[0] if problems else None
