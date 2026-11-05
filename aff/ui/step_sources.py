"""Step 1: source folders, depth, destination and conflict policy."""
from __future__ import annotations

import os
from tkinter import filedialog

import customtkinter as ctk

from ..models import ConflictPolicy
from ..planner import validate_destination
from .state import POLICY_LABELS
from .step_base import Step
from .widgets import Card

WIDE = 900


class SourcesStep(Step):
    title = "Sources & destination"

    def __init__(self, master, wizard):
        super().__init__(master, wizard)
        self.grid_columnconfigure(0, weight=1, uniform="cols")
        self.grid_columnconfigure(1, weight=1, uniform="cols")
        self.grid_rowconfigure(0, weight=1)
        self._wide = None

        # ---- left: sources
        self.left = Card(self, "Folders to search", "Add one or more folders. You can also drag folders "
                                                    "from Explorer and drop them here.")
        self.left.grid_rowconfigure(self.left.body_row, weight=1)
        self.list = ctk.CTkScrollableFrame(self.left, height=150, fg_color=("gray92", "gray16"))
        self.list.grid(row=self.left.next_row(), column=0, sticky="nsew", padx=12, pady=6)
        self.list.grid_columnconfigure(0, weight=1)
        bar = ctk.CTkFrame(self.left, fg_color="transparent")
        bar.grid(row=self.left.next_row(), column=0, sticky="ew", padx=12, pady=(0, 12))
        ctk.CTkButton(bar, text="＋  Add folder…", command=self._add_folder, width=130).pack(side="left")
        ctk.CTkButton(bar, text="Clear all", width=80, fg_color=("gray75", "gray30"),
                      text_color=("gray10", "gray95"), hover_color=("gray65", "gray40"),
                      command=self._clear).pack(side="left", padx=8)

        # ---- right: options
        self.right = Card(self, "Search options")
        r = self.right
        self._label(r, "How deep should the search go?")
        self.depth_seg = ctk.CTkSegmentedButton(r, values=["This folder only", "Include subfolders"],
                                                command=self._depth_changed)
        self.depth_seg.grid(row=r.next_row(), column=0, sticky="ew", padx=16, pady=(0, 6))
        self.depth_row = ctk.CTkFrame(r, fg_color="transparent")
        self.depth_row.grid(row=r.next_row(), column=0, sticky="ew", padx=16, pady=(0, 6))
        self.depth_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.depth_row, text="Max depth (optional)").grid(row=0, column=0, sticky="w")
        self.depth_entry = ctk.CTkEntry(self.depth_row, placeholder_text="unlimited", width=110)
        self.depth_entry.grid(row=0, column=1, sticky="w", padx=10)

        self._label(r, "Copy the files to")
        drow = ctk.CTkFrame(r, fg_color="transparent")
        drow.grid(row=r.next_row(), column=0, sticky="ew", padx=16, pady=(0, 6))
        drow.grid_columnconfigure(0, weight=1)
        self.dest_entry = ctk.CTkEntry(drow, placeholder_text="Choose the destination folder")
        self.dest_entry.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(drow, text="Browse…", width=90, command=self._browse_dest).grid(row=0, column=1, padx=(8, 0))

        self._label(r, "If a file already exists at the destination")
        self.policy_menu = ctk.CTkOptionMenu(r, values=list(POLICY_LABELS.values()), dynamic_resizing=False)
        self.policy_menu.grid(row=r.next_row(), column=0, sticky="ew", padx=16, pady=(0, 16))
        self._arrange(True)
        self.after(200, self._setup_dnd)

    @staticmethod
    def _label(card: Card, text: str) -> None:
        ctk.CTkLabel(card, text=text, anchor="w", font=ctk.CTkFont(weight="bold")
                     ).grid(row=card.next_row(), column=0, sticky="ew", padx=16, pady=(10, 2))

    # ---------------------------------------------------------------- layout
    def _arrange(self, wide: bool) -> None:
        if wide == self._wide:
            return
        self._wide = wide
        self.left.grid_forget()
        self.right.grid_forget()
        if wide:
            self.grid_rowconfigure(1, weight=0)
            self.left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
            self.right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        else:
            self.grid_rowconfigure(1, weight=0)
            self.left.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 10))
            self.right.grid(row=1, column=0, columnspan=2, sticky="nsew")

    def on_resize(self, width: int) -> None:
        self._arrange(width >= WIDE)
        half = width // 2 - 60 if width >= WIDE else width - 60
        self.left.set_wrap(half)

    # ----------------------------------------------------------- drag & drop
    def _setup_dnd(self) -> None:
        if not getattr(self.wizard, "dnd_ok", False):
            return
        try:
            from tkinterdnd2 import DND_FILES
        except ImportError:
            return
        for w in (self.left, self.list, getattr(self.list, "_parent_canvas", None)):
            if w is None:
                continue
            try:
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass

    def _on_drop(self, event) -> None:
        added = 0
        for p in self.tk.splitlist(event.data):
            folder = p if os.path.isdir(p) else os.path.dirname(p)
            added += self._add_source(folder)
        self._render_sources()
        if not added:
            self.wizard.show_message("Those folders are already in the list.", "info")

    # --------------------------------------------------------------- sources
    def _add_source(self, path: str) -> int:
        path = os.path.normpath(path)
        if path and os.path.isdir(path) and os.path.normcase(path) not in {
                os.path.normcase(s) for s in self.state.sources}:
            self.state.sources.append(path)
            return 1
        return 0

    def _add_folder(self) -> None:
        start = self.state.sources[-1] if self.state.sources else os.path.expanduser("~")
        path = filedialog.askdirectory(title="Choose a folder to search", initialdir=start, mustexist=True)
        if path:
            self._add_source(path)
            self._render_sources()

    def _clear(self) -> None:
        self.state.sources.clear()
        self._render_sources()

    def _remove(self, path: str) -> None:
        self.state.sources.remove(path)
        self._render_sources()

    def _render_sources(self) -> None:
        for child in self.list.winfo_children():
            child.destroy()
        if not self.state.sources:
            ctk.CTkLabel(self.list, text="No folders yet.\nClick “Add folder…” or drop folders here.",
                         text_color=("gray40", "gray60")).grid(row=0, column=0, pady=30)
            return
        for i, path in enumerate(self.state.sources):
            row = ctk.CTkFrame(self.list, fg_color=("gray86", "gray22"), corner_radius=8)
            row.grid(row=i, column=0, sticky="ew", pady=2)
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(row, text="📁  " + path, anchor="w").grid(row=0, column=0, sticky="ew", padx=10, pady=4)
            ctk.CTkButton(row, text="✕", width=28, height=26, fg_color="transparent",
                          text_color=("gray30", "gray70"), hover_color=("gray75", "gray35"),
                          command=lambda p=path: self._remove(p)).grid(row=0, column=1, padx=4)

    # ---------------------------------------------------------------- options
    def _depth_changed(self, _value=None) -> None:
        if self.depth_seg.get() == "Include subfolders":
            self.depth_row.grid()
        else:
            self.depth_row.grid_remove()

    def _browse_dest(self) -> None:
        path = filedialog.askdirectory(title="Choose the destination folder",
                                       initialdir=self.dest_entry.get() or os.path.expanduser("~"))
        if path:
            self.dest_entry.delete(0, "end")
            self.dest_entry.insert(0, os.path.normpath(path))

    def on_enter(self, forward: bool) -> None:
        st = self.state
        self._render_sources()
        self.depth_seg.set("Include subfolders" if st.recursive else "This folder only")
        self.depth_entry.delete(0, "end")
        if st.max_depth is not None:
            self.depth_entry.insert(0, str(st.max_depth))
        self._depth_changed()
        self.dest_entry.delete(0, "end")
        self.dest_entry.insert(0, st.destination)
        self.policy_menu.set(POLICY_LABELS[st.policy])

    def _commit(self) -> str | None:
        st = self.state
        st.recursive = self.depth_seg.get() == "Include subfolders"
        text = self.depth_entry.get().strip()
        st.max_depth = None
        if st.recursive and text:
            try:
                st.max_depth = int(text)
                if st.max_depth < 0:
                    raise ValueError
            except ValueError:
                return "Max depth must be a whole number (0 or more), or leave it empty for unlimited."
        st.destination = self.dest_entry.get().strip().strip('"')
        label = self.policy_menu.get()
        st.policy = next((p for p, lbl in POLICY_LABELS.items() if lbl == label), ConflictPolicy.KEEP_BOTH)
        return None

    def validate(self) -> str | None:
        err = self._commit()
        if err:
            return err
        st = self.state
        if not st.sources:
            return "Add at least one folder to search."
        for s in st.sources:
            if not os.path.isdir(s):
                return f"This folder was not found: {s}"
        errors = validate_destination(st.sources, st.destination)
        return errors[0] if errors else None

    def on_leave(self) -> None:
        self._commit()
