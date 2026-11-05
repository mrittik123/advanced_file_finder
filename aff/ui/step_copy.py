"""Step 4: choose how files are arranged, confirm, copy with progress, and show the report."""
from __future__ import annotations

import os
import threading
from tkinter import messagebox

import customtkinter as ctk

from ..copier import Copier, CopyReport
from ..layout import PRESETS, TOKEN_HELP, validate_pattern
from ..models import ConflictPolicy, LayoutMode, PlanStatus
from ..planner import carry_selection, check_free_space
from ..utils import format_size, open_path
from .state import POLICY_LABELS
from .step_base import Step
from .widgets import Card, col

IDLE, RUNNING, DONE = "idle", "running", "done"
MODE_LABELS = {LayoutMode.PRESERVE: "Keep folder structure", LayoutMode.FLAT: "All files together",
               LayoutMode.CUSTOM: "Custom pattern"}
PRESET_PLACEHOLDER = "Ready-made patterns…"


class CopyStep(Step):
    title = "Copy"
    next_text = "Start copy"

    def __init__(self, master, wizard):
        super().__init__(master, wizard)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.phase = IDLE
        self.copier: Copier | None = None
        self.cancel = threading.Event()
        self.report: CopyReport | None = None
        self.space_ok = True
        self._replanning = False
        self._replan_again = False
        self._replan_job = None
        self._layout_valid = True

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        self.body = body

        # ------------------------------------------------ output layout
        self.out_card = Card(body, "Output: how should the files be arranged?")
        self.out_card.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.mode_seg = ctk.CTkSegmentedButton(self.out_card, values=list(MODE_LABELS.values()),
                                               command=self._mode_changed)
        self.mode_seg.grid(row=self.out_card.next_row(), column=0, sticky="ew", padx=16, pady=(6, 4))

        self.opt_frame = ctk.CTkFrame(self.out_card, fg_color="transparent")     # holds the mode-specific part
        self.opt_frame.grid(row=self.out_card.next_row(), column=0, sticky="ew", padx=16)
        self.opt_frame.grid_columnconfigure(0, weight=1)

        self.preserve_box = ctk.CTkFrame(self.opt_frame, fg_color="transparent")
        self.source_check = ctk.CTkCheckBox(self.preserve_box, text="Add a folder named after each source folder",
                                            command=self._layout_changed)
        self.source_check.grid(row=0, column=0, sticky="w", pady=4)
        self.flat_box = ctk.CTkFrame(self.opt_frame, fg_color="transparent")
        self.flat_label = ctk.CTkLabel(self.flat_box, anchor="w", justify="left", wraplength=600,
                                       text="Every file goes straight into the destination folder. If two files have "
                                            "the same name, the later ones are copied as “name (1).ext”, "
                                            "“name (2).ext” - nothing is overwritten by accident.")
        self.flat_label.grid(row=0, column=0, sticky="ew", pady=4)

        self.custom_box = ctk.CTkFrame(self.opt_frame, fg_color="transparent")
        self.custom_box.grid_columnconfigure(0, weight=1)
        self.pattern_entry = ctk.CTkEntry(self.custom_box, placeholder_text="e.g. {category}/{year}/{name}")
        self.pattern_entry.bind("<KeyRelease>", lambda _e: self._layout_changed())
        self.preset_menu = ctk.CTkOptionMenu(self.custom_box, values=[PRESET_PLACEHOLDER] + list(PRESETS),
                                             command=self._preset_picked, dynamic_resizing=False, width=200)
        self.date_menu = ctk.CTkOptionMenu(self.custom_box, values=["Dates: modified", "Dates: created"],
                                           command=lambda _v: self._layout_changed(), dynamic_resizing=False,
                                           width=150)
        self.token_help = ctk.CTkLabel(
            self.custom_box, anchor="w", justify="left", wraplength=600, text_color=("gray35", "gray65"),
            text="Placeholders:  " + "   ".join("{%s}" % t for t in TOKEN_HELP) +
                 "\nThe file name is added automatically when the pattern has no {name} or {stem}. "
                 "Use / or \\ between folders.")
        self.pattern_error = ctk.CTkLabel(self.custom_box, text="", anchor="w", justify="left", wraplength=600,
                                          text_color=("#b91c1c", "#f87171"))
        self._custom_wide = None
        self._arrange_custom(True)

        self.example = ctk.CTkLabel(self.out_card, text="", anchor="w", justify="left", wraplength=600,
                                    text_color=("gray20", "gray85"), font=ctk.CTkFont(family="Consolas", size=12))
        self.example.grid(row=self.out_card.next_row(), column=0, sticky="ew", padx=16, pady=(6, 12))

        # ------------------------------------------------ summary
        self.sum_card = Card(body, "Ready to copy")
        self.sum_card.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.sum_text = ctk.CTkLabel(self.sum_card, text="", anchor="w", justify="left", wraplength=700)
        self.sum_text.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 4))
        self.space_label = ctk.CTkLabel(self.sum_card, text="", anchor="w", justify="left", wraplength=700)
        self.space_label.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 4))
        self.verify = ctk.CTkCheckBox(self.sum_card, text="Verify every copy with a checksum (slower, safest)")
        self.verify.grid(row=3, column=0, sticky="w", padx=16, pady=(4, 14))

        # ------------------------------------------------ progress
        self.prog_card = Card(body, "Progress")
        self.prog_card.grid(row=2, column=0, sticky="ew")
        self.bar = ctk.CTkProgressBar(self.prog_card, height=14)
        self.bar.set(0)
        self.bar.grid(row=1, column=0, sticky="ew", padx=16, pady=(4, 6))
        self.line1 = ctk.CTkLabel(self.prog_card, text="Press “Start copy” to begin.", anchor="w",
                                  font=ctk.CTkFont(size=13, weight="bold"))
        self.line1.grid(row=2, column=0, sticky="ew", padx=16)
        self.line2 = ctk.CTkLabel(self.prog_card, text="", anchor="w", text_color=("gray35", "gray65"))
        self.line2.grid(row=3, column=0, sticky="ew", padx=16)
        self.counts = ctk.CTkLabel(self.prog_card, text="", anchor="w")
        self.counts.grid(row=4, column=0, sticky="ew", padx=16, pady=(2, 6))
        self.log_box = ctk.CTkTextbox(self.prog_card, height=130, state="disabled")
        self.log_box.grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 8))
        self.actions = ctk.CTkFrame(self.prog_card, fg_color="transparent")
        self.actions.grid(row=6, column=0, sticky="w", padx=16, pady=(0, 14))
        self.open_dest = ctk.CTkButton(self.actions, text="Open destination", width=150, command=self._open_dest)
        self.open_log = ctk.CTkButton(self.actions, text="Open log file", width=120,
                                      fg_color=("gray75", "gray30"), text_color=("gray10", "gray95"),
                                      hover_color=("gray65", "gray40"), command=self._open_log)
        self.open_dest.grid(row=0, column=0)
        self.open_log.grid(row=0, column=1, padx=8)
        self.actions.grid_remove()

    # ================================================================= output layout
    def _arrange_custom(self, wide: bool) -> None:
        if wide == self._custom_wide:
            return
        self._custom_wide = wide
        for w in (self.pattern_entry, self.preset_menu, self.date_menu, self.token_help, self.pattern_error):
            w.grid_forget()
        for c in range(3):
            self.custom_box.grid_columnconfigure(c, weight=0)
        if wide:
            self.custom_box.grid_columnconfigure(0, weight=1)
            self.pattern_entry.grid(row=0, column=0, sticky="ew", pady=4)
            self.preset_menu.grid(row=0, column=1, padx=(8, 0), pady=4)
            self.date_menu.grid(row=0, column=2, padx=(8, 0), pady=4)
        else:
            self.custom_box.grid_columnconfigure(0, weight=1)
            self.custom_box.grid_columnconfigure(1, weight=1)
            self.pattern_entry.grid(row=0, column=0, columnspan=2, sticky="ew", pady=4)
            self.preset_menu.grid(row=1, column=0, sticky="w", pady=4)
            self.date_menu.grid(row=1, column=1, sticky="e", pady=4)
        self.token_help.grid(row=2, column=0, columnspan=3, sticky="ew")
        self.pattern_error.grid(row=3, column=0, columnspan=3, sticky="ew")

    def _show_mode_box(self, mode: LayoutMode) -> None:
        for box in (self.preserve_box, self.flat_box, self.custom_box):
            box.grid_forget()
        {LayoutMode.PRESERVE: self.preserve_box, LayoutMode.FLAT: self.flat_box,
         LayoutMode.CUSTOM: self.custom_box}[mode].grid(row=0, column=0, sticky="ew")

    def _load_layout_widgets(self) -> None:
        lay = self.state.layout
        self.mode_seg.set(MODE_LABELS[lay.mode])
        self._show_mode_box(lay.mode)
        self.source_check.select() if lay.include_source_name else self.source_check.deselect()
        self.pattern_entry.delete(0, "end")
        self.pattern_entry.insert(0, lay.pattern)
        self.date_menu.set("Dates: created" if lay.date_field == "created" else "Dates: modified")
        self.preset_menu.set(PRESET_PLACEHOLDER)
        self.pattern_error.configure(text="")
        self._layout_valid = True

    def _mode_changed(self, label: str) -> None:
        self.state.layout.mode = next(m for m, lbl in MODE_LABELS.items() if lbl == label)
        self._show_mode_box(self.state.layout.mode)
        self._layout_changed()

    def _preset_picked(self, label: str) -> None:
        if label in PRESETS:
            self.pattern_entry.delete(0, "end")
            self.pattern_entry.insert(0, PRESETS[label])
            self._layout_changed()
        self.preset_menu.set(PRESET_PLACEHOLDER)

    def _layout_changed(self) -> None:
        """Read the controls into the state; re-plan (debounced) when the layout is valid."""
        lay = self.state.layout
        lay.include_source_name = bool(self.source_check.get())
        lay.pattern = self.pattern_entry.get()
        lay.date_field = "created" if "created" in self.date_menu.get() else "modified"
        self._layout_valid = True
        self.pattern_error.configure(text="")
        if lay.mode is LayoutMode.CUSTOM:
            problems = validate_pattern(lay.pattern)
            if problems:
                self._layout_valid = False
                self.pattern_error.configure(text="⚠  " + " ".join(problems))
                self.wizard.set_next_enabled(False)
                return
        if self._replan_job:
            self.after_cancel(self._replan_job)
        self._replan_job = self.after(350, self._start_replan)

    def _start_replan(self) -> None:
        self._replan_job = None
        if self._replanning:
            self._replan_again = True
            return
        self._replanning = True
        self._replan_again = False
        self.wizard.set_next_enabled(False)
        self.line1.configure(text="Updating destination paths…", text_color=col("muted"))
        st = self.state
        result: dict = {}

        def work():
            try:
                result["plan"] = st.make_plan()
            except Exception as e:
                result["error"] = str(e)

        t = threading.Thread(target=work, daemon=True)
        t.start()
        self._wait_replan(t, result)

    def _wait_replan(self, thread: threading.Thread, result: dict) -> None:
        if thread.is_alive():
            self.after(80, lambda: self._wait_replan(thread, result))
            return
        self._replanning = False
        st = self.state
        if "plan" in result:
            if st.plan is not None:
                carry_selection(st.plan, result["plan"])
            st.plan = result["plan"]
            st.signature = st.signature_now()
        else:
            self.wizard.show_message(f"Could not update the paths: {result.get('error')}", "error")
        if self._replan_again:
            self._start_replan()
            return
        self.line1.configure(text="Press “Start copy” to begin.", text_color=col("text"))
        self._refresh_summary()
        self.wizard.set_next_enabled(self._layout_valid)

    def _example_text(self) -> str:
        plan = self.state.plan
        item = next((i for i in plan.items if i.selected), None) if plan else None
        if not item:
            return ""
        sep = os.sep
        rel = os.path.relpath(item.dest, plan.destination)
        return f"Example:\n  {item.source.path}\n  → {plan.destination.rstrip(sep)}{sep}{rel}"

    # ================================================================= summary
    def _refresh_summary(self) -> None:
        plan = self.state.plan
        if plan is None:
            return
        n = len(plan.selected_items)
        over = sum(1 for i in plan.selected_items if i.status is PlanStatus.WOULD_OVERWRITE)
        renamed = sum(1 for i in plan.selected_items if "new name" in i.note)
        lay = self.state.layout
        arrangement = {LayoutMode.PRESERVE: "Keep the folder structure",
                       LayoutMode.FLAT: "All files in one folder",
                       LayoutMode.CUSTOM: f"Pattern  {lay.pattern}"}[lay.mode]
        lines = [f"{n:,} files  ·  {format_size(plan.selected_size)}", f"To:  {plan.destination}",
                 f"Arrangement:  {arrangement}", f"If a file exists:  {POLICY_LABELS[plan.policy]}"]
        if over:
            lines.append(f"{over:,} existing files will be overwritten.")
        if renamed:
            lines.append(f"{renamed:,} files will be copied with a new name (name clash).")
        self.sum_text.configure(text="\n".join(lines))
        self.example.configure(text=self._example_text())
        try:
            chk = check_free_space(plan)
            self.space_ok = chk.ok
            self.space_label.configure(text=("✔  " if chk.ok else "✖  ") + chk.message(),
                                       text_color=col("ok") if chk.ok else col("bad"))
        except OSError as e:
            self.space_ok = True
            self.space_label.configure(text=f"Could not check free space: {e}", text_color=col("warn"))

    def _set_output_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for w in (self.mode_seg, self.source_check, self.pattern_entry, self.preset_menu, self.date_menu):
            w.configure(state=state)

    # ================================================================= enter / run
    def on_enter(self, forward: bool) -> None:
        if self.phase == RUNNING:
            self._nav_for_running()
            return
        if self.phase == DONE and not forward:
            return
        self.phase = IDLE
        self.bar.set(0)
        self.actions.grid_remove()
        self._write_log("")
        self.line1.configure(text="Press “Start copy” to begin.", text_color=col("text"))
        self.line2.configure(text="")
        self.counts.configure(text="")
        self._set_output_enabled(True)
        self._load_layout_widgets()
        self._refresh_summary()
        self.wizard.set_next("Start copy", True)
        self.wizard.set_back_enabled(True)

    def _nav_for_running(self) -> None:
        self.wizard.set_next("Cancel copy", True, danger=True)
        self.wizard.set_back_enabled(False)

    def on_next(self) -> bool:
        """Primary button: Start -> Cancel -> New search, depending on the phase."""
        if self.phase == IDLE:
            self._start()
        elif self.phase == RUNNING:
            self.cancel.set()
            self.line1.configure(text="Cancelling after the current file…")
        else:
            self.wizard.restart()
        return False

    def _start(self) -> None:
        plan = self.state.plan
        if self._replanning or self._replan_job:
            self.wizard.show_message("Still updating the destination paths - try again in a moment.", "info")
            return
        if not self._layout_valid:
            self.wizard.show_message("Fix the pattern first.", "error")
            return
        if not self.space_ok:
            self.wizard.show_message("There is not enough free space at the destination.", "error")
            return
        if not plan.selected_items:
            self.wizard.show_message("No files are selected.", "error")
            return
        over = sum(1 for i in plan.selected_items if i.status is PlanStatus.WOULD_OVERWRITE)
        if over and plan.policy is ConflictPolicy.OVERWRITE and not messagebox.askyesno(
                "Overwrite files?", f"{over:,} existing files will be overwritten. Continue?"):
            return
        self.phase = RUNNING
        self.cancel = threading.Event()
        self.report = None
        self._nav_for_running()
        self._set_output_enabled(False)
        self.verify.configure(state="disabled")
        self.wizard.show_message("", "info")
        self.copier = Copier(plan, self.cancel, verify=bool(self.verify.get()))
        copier = self.copier

        def work():
            try:
                self.report = copier.run()
            except Exception as e:                       # the copier already isolates single files
                self.report = CopyReport(failed=1, failures=[("(copy run)", str(e))])

        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()
        self._poll()

    def _poll(self) -> None:
        p = self.copier.progress
        self.bar.set(p.fraction)
        self.line1.configure(text=f"Copying {min(p.files_done + 1, p.total_files):,} of {p.total_files:,} files  ·  "
                                  f"{format_size(p.bytes_done)} of {format_size(p.total_bytes)}")
        self.line2.configure(text=p.current[-110:] if len(p.current) > 110 else p.current)
        self.counts.configure(text=f"Copied {p.copied:,}   ·   Skipped {p.skipped:,}   ·   Failed {p.failed:,}")
        if self._thread.is_alive():
            self.after(150, self._poll)
        else:
            self._finish()

    def _finish(self) -> None:
        rep = self.report
        self.phase = DONE
        p = self.copier.progress
        self.bar.set(1.0 if not rep.cancelled else p.fraction)
        self.line1.configure(text=rep.summary(),
                             text_color=col("bad") if rep.failed else col("warn") if rep.cancelled else col("ok"))
        self.line2.configure(text=f"{format_size(rep.bytes_copied)} copied to {self.state.plan.destination}")
        self.counts.configure(text="")
        lines = [rep.summary()]
        if rep.failures:
            lines.append("\nFailed files:")
            lines += [f"  {src}\n      {msg}" for src, msg in rep.failures[:200]]
            if len(rep.failures) > 200:
                lines.append(f"  … and {len(rep.failures) - 200} more (see the log file)")
        if rep.log_path:
            lines.append(f"\nFull log: {rep.log_path}")
        self._write_log("\n".join(lines))
        self.actions.grid()
        self.open_log.configure(state="normal" if rep.log_path else "disabled")
        self.verify.configure(state="normal")
        self.state.invalidate_results()          # the destination changed, so statuses are stale
        self.wizard.set_next("New search", True)
        self.wizard.set_back_enabled(True)

    # ---------------------------------------------------------------- helpers
    def _write_log(self, text: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.insert("end", text)
        self.log_box.configure(state="disabled")

    def _open_dest(self) -> None:
        try:
            os.makedirs(self.state.plan.destination, exist_ok=True)
            open_path(self.state.plan.destination)
        except OSError as e:
            self.wizard.show_message(str(e), "error")

    def _open_log(self) -> None:
        if self.report and self.report.log_path:
            try:
                open_path(str(self.report.log_path))
            except OSError as e:
                self.wizard.show_message(str(e), "error")

    def on_resize(self, width: int) -> None:
        wrap = max(220, width - 110)
        for w in (self.sum_text, self.space_label, self.example, self.token_help, self.pattern_error,
                  self.flat_label):
            w.configure(wraplength=wrap)
        self._arrange_custom(width >= 860)
