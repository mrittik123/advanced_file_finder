"""Step 3: run the search in the background, then review and select files before copying."""
from __future__ import annotations

import glob
import os
import queue
import threading
import tkinter as tk
from datetime import datetime

import customtkinter as ctk

from ..models import Field, Op, PlanItem, PlanStatus, Rule, SearchStats
from ..rules import compile_rule
from ..search import iter_search
from ..utils import format_size, open_path, reveal_in_folder
from .step_base import Step
from .widgets import Column, VirtualTable

STATUS_COLORS = {PlanStatus.NEW: "ok", PlanStatus.EXISTS: "muted",
                 PlanStatus.WOULD_OVERWRITE: "warn", PlanStatus.ERROR: "bad"}
STATUS_FILTERS = ["All statuses", "New", "Exists", "Would overwrite", "Error"]
WIDE = 900

COLUMNS = [
    Column("name", "Name", 2.2, 120),
    Column("folder", "Source folder", 3, 120, trunc="start", hide_below=1050),
    Column("dest", "Destination", 3, 120, trunc="start", hide_below=760),
    Column("size", "Size", 1, 80, align="e"),
    Column("modified", "Modified", 1.5, 120, hide_below=900),
    Column("status", "Status", 1.3, 100),
]


class PreviewStep(Step):
    title = "Preview"

    def __init__(self, master, wizard):
        super().__init__(master, wizard)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.q: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.searching = False
        self.items: list[PlanItem] = []
        self.sel_count = 0
        self.sel_size = 0
        self._wide = None

        # status line + progress
        head = ctk.CTkFrame(self, corner_radius=12)
        head.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        head.grid_columnconfigure(0, weight=1)
        self.status = ctk.CTkLabel(head, text="", anchor="w", justify="left", wraplength=600)
        self.status.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 4))
        self.stop_btn = ctk.CTkButton(head, text="■ Stop", width=80, height=28, fg_color="#b91c1c",
                                      hover_color="#991b1b", command=self._stop)
        self.stop_btn.grid(row=0, column=1, padx=12, pady=(10, 4))
        self.bar = ctk.CTkProgressBar(head, mode="indeterminate", height=6)
        self.bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 10))

        # tools
        self.tools = ctk.CTkFrame(self, fg_color="transparent")
        self.tools.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        self.filter_entry = ctk.CTkEntry(self.tools, placeholder_text="🔍  Filter by name or path…")
        self.filter_entry.bind("<KeyRelease>", self._filter_typed)
        self.status_menu = ctk.CTkOptionMenu(self.tools, values=STATUS_FILTERS, width=150,
                                             command=self._status_filter, dynamic_resizing=False)
        self.sel_frame = ctk.CTkFrame(self.tools, fg_color="transparent")
        self.sel_buttons = []
        for text, fn in (("All", self._select_all), ("None", self._select_none),
                         ("Invert", self._invert), ("Visible", self._select_visible)):
            b = ctk.CTkButton(self.sel_frame, text=text, width=64, height=28, command=fn,
                              fg_color=("gray75", "gray30"), text_color=("gray10", "gray95"),
                              hover_color=("gray65", "gray40"))
            b.pack(side="left", padx=2)
            self.sel_buttons.append(b)

        # table
        holder = ctk.CTkFrame(self, corner_radius=10)
        holder.grid(row=2, column=0, sticky="nsew")
        holder.grid_rowconfigure(0, weight=1)
        holder.grid_columnconfigure(0, weight=1)
        self.table = VirtualTable(
            holder, COLUMNS, cell=self._cell, is_checked=lambda it: it.selected, set_checked=self._set_checked,
            status_color=lambda it: STATUS_COLORS[it.status], search_text=self._search_text,
            sort_key=self._sort_key, on_change=self._update_summary, on_context=self._context_menu,
            on_open=lambda it: self._safe(open_path, it.source.path), on_copy=self._copy_cell,
            on_widths_changed=self._save_widths, empty_text="No files to show")
        self.table.set_widths(self.state.settings.preview_col_widths)
        self.table.grid(row=0, column=0, sticky="nsew", padx=3, pady=3)

        # summary bar
        sb = ctk.CTkFrame(self, corner_radius=10)
        sb.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self.summary = ctk.CTkLabel(sb, text="", anchor="w", font=ctk.CTkFont(size=13, weight="bold"))
        self.summary.pack(side="left", padx=14, pady=8)
        self.hint = ctk.CTkLabel(sb, text="Drag a header border to resize · right-click copies a cell · double-click opens",
                                 text_color=("gray40", "gray60"))
        self.hint.pack(side="right", padx=14)
        self._arrange_tools(True)

    # ----------------------------------------------------------- table glue
    def _cell(self, it: PlanItem, key: str) -> str:
        s = it.source
        if key == "name":
            return s.name
        if key == "folder":
            return s.folder
        if key == "dest":
            return it.dest
        if key == "size":
            return format_size(s.size)
        if key == "modified":
            return datetime.fromtimestamp(s.modified).strftime("%Y-%m-%d %H:%M")
        return it.status.value

    @staticmethod
    def _search_text(it: PlanItem) -> str:
        return (it.source.path + "\n" + it.dest).lower()

    @staticmethod
    def _sort_key(it: PlanItem, key: str):
        s = it.source
        return {"name": s.name.casefold(), "folder": s.folder.casefold(), "dest": it.dest.casefold(),
                "size": s.size, "modified": s.modified, "status": it.status.value}[key]

    def _set_checked(self, it: PlanItem, value: bool) -> None:
        if it.status is PlanStatus.ERROR or it.selected == value:
            return
        it.selected = value
        self.sel_count += 1 if value else -1
        self.sel_size += it.source.size if value else -it.source.size

    def _recount(self) -> None:
        sel = [i for i in self.items if i.selected]
        self.sel_count, self.sel_size = len(sel), sum(i.source.size for i in sel)
        self._update_summary()
        self.table.redraw()

    def _update_summary(self) -> None:
        shown = len(self.table.view)
        extra = f"   ·   showing {shown:,}" if shown != len(self.items) else ""
        self.summary.configure(text=f"Found {len(self.items):,}   ·   Selected {self.sel_count:,}   ·   "
                                    f"To copy {format_size(self.sel_size)}{extra}")

    # ------------------------------------------------------------ selection
    def _select_all(self) -> None:
        for i in self.items:
            self._set_checked(i, True)
        self._recount()

    def _select_none(self) -> None:
        for i in self.items:
            self._set_checked(i, False)
        self._recount()

    def _invert(self) -> None:
        for i in self.items:
            self._set_checked(i, not i.selected)
        self._recount()

    def _select_visible(self) -> None:
        for i in self.table.visible_items():
            self._set_checked(i, True)
        self._recount()

    # -------------------------------------------------------------- filters
    def _filter_typed(self, _e=None) -> None:
        if getattr(self, "_filter_job", None):
            self.after_cancel(self._filter_job)
        self._filter_job = self.after(250, lambda: (self.table.set_filter(self.filter_entry.get()),
                                                    self._update_summary()))

    def _status_filter(self, label: str) -> None:
        if label == STATUS_FILTERS[0]:
            self.table.set_extra_filter(None)
        else:
            self.table.set_extra_filter(lambda it, v=label.lower(): it.status.value == v)
        self._update_summary()

    # ---------------------------------------------------------- context menu
    def _safe(self, fn, *args) -> None:
        try:
            fn(*args)
        except Exception as e:
            self.wizard.show_message(f"Could not open it: {e}", "error")

    # ----------------------------------------------------------- copy to clipboard
    FULL_VALUES = (("Name", "name"), ("Source folder", "folder"), ("Full source path", "path"),
                   ("Destination path", "dest"), ("Size", "size"), ("Modified", "modified"),
                   ("Status", "status"))

    def _value(self, it: PlanItem, key: str) -> str:
        if key == "path":
            return it.source.path
        if key == "size":
            return f"{it.source.size} bytes ({format_size(it.source.size)})"
        return self._cell(it, key)

    def _to_clipboard(self, text: str, what: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()                                  # keep the text after the app is idle/closed
        shown = text if len(text) <= 70 else text[:67] + "…"
        self.wizard.show_message(f"Copied {what}: {shown}", "info")

    def _copy_cell(self, it: PlanItem, key: str | None) -> None:
        """Ctrl+C: the cell last clicked, or the file name when no column was clicked."""
        key = key or "name"
        title = next((c.title for c in COLUMNS if c.key == key), key)
        self._to_clipboard(self._cell(it, key), title.lower())

    def _copy_row(self, it: PlanItem) -> None:
        cols = [c.key for c in COLUMNS]
        self._to_clipboard("\t".join(self._cell(it, k) for k in cols), "the row")

    def _save_widths(self, widths: dict) -> None:
        self.state.settings.preview_col_widths = widths or None

    def _context_menu(self, event, it: PlanItem, key: str | None = None) -> None:
        m = tk.Menu(self, tearoff=0)
        if key:
            title = next((c.title for c in COLUMNS if c.key == key), key)
            m.add_command(label=f"Copy this cell  ({title})", command=lambda: self._copy_cell(it, key))
        copy_menu = tk.Menu(m, tearoff=0)
        for label, k in self.FULL_VALUES:
            copy_menu.add_command(label=label, command=lambda k=k, label=label: self._to_clipboard(
                self._value(it, k), label.lower()))
        copy_menu.add_separator()
        copy_menu.add_command(label="Whole row (tab-separated)", command=lambda: self._copy_row(it))
        m.add_cascade(label="Copy…", menu=copy_menu)
        m.add_separator()
        m.add_command(label="Open file", command=lambda: self._safe(open_path, it.source.path))
        m.add_command(label="Open containing folder", command=lambda: self._safe(reveal_in_folder, it.source.path))
        m.add_separator()
        ext = it.source.ext
        if ext:
            m.add_command(label=f"Exclude this extension (.{ext})",
                          command=lambda: self._exclude(Rule(Field.EXTENSION, Op.IN_LIST, ext)))
        folder = it.source.folder
        m.add_command(label="Exclude this folder (and its subfolders)",
                      command=lambda: self._exclude(Rule(
                          Field.FOLDER, Op.WILDCARD, f"{glob.escape(folder)};{glob.escape(folder + os.sep)}*",
                          case_sensitive=False)))
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def _exclude(self, rule: Rule) -> None:
        """Add an Exclude rule (undoable in step 2) and drop matching files from this list."""
        try:
            _, matcher = compile_rule(rule)
        except Exception as e:
            self.wizard.show_message(str(e), "error")
            return
        self.state.push_undo()
        self.state.rules.add_exclude(rule)
        keep = [i for i in self.items if not matcher(i.source)]
        removed = len(self.items) - len(keep)
        self.items = keep
        self.state.found = [i.source for i in keep]
        self.state.plan.items = keep
        self.state.signature = self.state.signature_now()        # list already reflects the new rule
        self.table.set_items(self.items, keep_scroll=True)
        self._recount()
        self.wizard.show_message(f"Exclude rule added; {removed:,} files removed from the list. "
                                 "You can undo it on the Rules page.", "info")

    # --------------------------------------------------------------- layout
    def _arrange_tools(self, wide: bool) -> None:
        if wide == self._wide:
            return
        self._wide = wide
        for w in (self.filter_entry, self.status_menu, self.sel_frame):
            w.grid_forget()
        for c in range(3):
            self.tools.grid_columnconfigure(c, weight=0)
        if wide:
            self.tools.grid_columnconfigure(0, weight=1)
            self.filter_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
            self.status_menu.grid(row=0, column=1, padx=6)
            self.sel_frame.grid(row=0, column=2, padx=(6, 0))
        else:
            self.tools.grid_columnconfigure(0, weight=1)
            self.tools.grid_columnconfigure(1, weight=1)
            self.filter_entry.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
            self.status_menu.grid(row=1, column=0, sticky="w")
            self.sel_frame.grid(row=1, column=1, sticky="e")

    def on_resize(self, width: int) -> None:
        self._arrange_tools(width >= WIDE)
        self.status.configure(wraplength=max(200, width - 200))
        self.hint.pack_forget() if width < 760 else self.hint.pack(side="right", padx=14)

    def on_theme_change(self) -> None:
        self.table.redraw()

    # ------------------------------------------------------------ searching
    def on_enter(self, forward: bool) -> None:
        if self.searching:
            return
        if self.state.signature == self.state.signature_now() and self.state.plan is not None:
            self._show_results(self.state.plan.items, from_cache=True)
            return
        self._start_search()

    def _start_search(self) -> None:
        st = self.state
        self.cancel = threading.Event()
        self.q = queue.Queue()
        st.stats = SearchStats()
        st.plan, st.found = None, []
        self.items, self.sel_count, self.sel_size = [], 0, 0
        self.table.set_items([])
        self.table.empty_text = "Searching…"
        self.table.redraw()
        self._update_summary()
        self.searching = True
        self.stop_btn.grid()
        self.stop_btn.configure(state="normal")
        self.bar.configure(mode="indeterminate")
        self.bar.start()
        self._set_tools(False)
        self.wizard.set_next_enabled(False)
        signature, cfg = st.signature_now(), st.config()
        stats, cancel, q = st.stats, self.cancel, self.q

        def work():
            try:
                files = []
                for info in iter_search(cfg, cancel, stats):
                    files.append(info)
                q.put(("phase", "Preparing the copy plan…"))
                plan = st.make_plan(files)
                q.put(("done", signature, files, plan))
            except Exception as e:                                   # never crash the UI thread
                q.put(("error", f"{type(e).__name__}: {e}"))

        threading.Thread(target=work, daemon=True).start()
        self._phase = "Searching"
        self._poll()

    def _poll(self) -> None:
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "phase":
                    self._phase = msg[1]
                elif msg[0] == "done":
                    self._finish(msg[1], msg[2], msg[3])
                    return
                elif msg[0] == "error":
                    self._fail(msg[1])
                    return
        except queue.Empty:
            pass
        s = self.state.stats
        self.status.configure(text=f"{self._phase}…  {s.files_scanned:,} files checked in {s.dirs_scanned:,} "
                                   f"folders · {s.files_matched:,} match so far")
        self.after(120, self._poll)

    def _stop(self) -> None:
        self.cancel.set()
        self.stop_btn.configure(state="disabled")
        self.status.configure(text="Stopping…")

    def _fail(self, message: str) -> None:
        self._end_search()
        self.status.configure(text=f"The search failed: {message}")
        self.wizard.show_message("The search failed. See the message above.", "error")

    def _finish(self, signature: str, files, plan) -> None:
        st = self.state
        st.found, st.plan = files, plan
        stopped = self.cancel.is_set()
        # a stopped search is partial, so it is not cached: Back + Next searches again
        st.signature = None if stopped else signature
        self._end_search()
        self._show_results(plan.items, stopped=stopped)

    def _end_search(self) -> None:
        self.searching = False
        self.bar.stop()
        self.bar.configure(mode="determinate")
        self.bar.set(1)
        self.stop_btn.grid_remove()
        self._set_tools(True)
        self.wizard.set_next_enabled(True)

    def _set_tools(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for b in self.sel_buttons:
            b.configure(state=state)
        self.filter_entry.configure(state=state)
        self.status_menu.configure(state=state)

    def _show_results(self, items: list[PlanItem], stopped: bool = False, from_cache: bool = False) -> None:
        self.items = items
        self.sel_count = sum(1 for i in items if i.selected)
        self.sel_size = sum(i.source.size for i in items if i.selected)
        self.bar.stop()
        self.bar.configure(mode="determinate")
        self.bar.set(1)
        self.stop_btn.grid_remove()
        self._set_tools(True)
        self.table.empty_text = "No files match your rules"
        self.table.set_items(items)
        self._update_summary()
        s = self.state.stats
        parts = []
        if from_cache:
            parts.append("Showing the previous results (nothing changed).")
        else:
            parts.append(("Search stopped - partial results. " if stopped else "Search finished. ")
                         + f"{s.files_scanned:,} files checked, {len(items):,} match.")
        counts = {st: sum(1 for i in items if i.status is st) for st in PlanStatus}
        if counts[PlanStatus.EXISTS] or counts[PlanStatus.WOULD_OVERWRITE]:
            parts.append(f"{counts[PlanStatus.EXISTS]:,} already exist, "
                         f"{counts[PlanStatus.WOULD_OVERWRITE]:,} would be overwritten.")
        if s.content_binary_skipped or s.content_too_large_skipped:
            parts.append(f"Content search skipped {s.content_binary_skipped:,} binary and "
                         f"{s.content_too_large_skipped:,} oversized files.")
        if s.errors:
            parts.append(f"{len(s.errors):,} folders/files could not be read and were skipped.")
        self.status.configure(text=" ".join(parts))

    # ----------------------------------------------------------------- nav
    def validate(self) -> str | None:
        if self.searching:
            return "Wait for the search to finish, or press Stop."
        if self.state.plan is None or self.sel_count == 0:
            return "Select at least one file to copy."
        return None

    def on_leave(self) -> None:
        if self.searching:
            self.cancel.set()
