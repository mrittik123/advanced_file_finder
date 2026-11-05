"""Main window: a 4-step wizard (Sources -> Rules -> Preview -> Copy) with Back / Next."""
from __future__ import annotations

import logging
import traceback

import customtkinter as ctk

from ..settings import Settings, load_settings, save_settings
from ..utils import IS_WINDOWS, resource_path
from .state import WizardState
from .step_copy import CopyStep
from .step_preview import PreviewStep
from .step_rules import RulesStep
from .step_sources import SourcesStep
from .widgets import StepIndicator, col

log = logging.getLogger("aff.ui")

try:                                           # optional: drag & drop of folders
    from tkinterdnd2 import TkinterDnD
    _Base = type("_Base", (ctk.CTk, TkinterDnD.DnDWrapper), {})
except Exception:                              # pragma: no cover
    TkinterDnD = None
    _Base = ctk.CTk

COMPACT = 780                                  # below this width the stepper becomes "Step 2 of 4"


class Wizard(_Base):
    def __init__(self):
        self.settings: Settings = load_settings()
        ctk.set_appearance_mode(self.settings.theme if self.settings.theme in ("dark", "light", "system") else "dark")
        ctk.set_default_color_theme("blue")
        super().__init__()
        self.dnd_ok = False
        if TkinterDnD is not None:
            try:
                self.TkdndVersion = TkinterDnD._require(self)
                self.dnd_ok = True
            except Exception as e:
                log.info("Drag and drop unavailable: %s", e)

        self.title("Advanced File Finder")
        self.geometry(self.settings.window_geometry or "1080x720")
        self.minsize(640, 520)
        if IS_WINDOWS:                                   # window / taskbar icon (CTk resets it, so set it late)
            self.after(250, self._set_icon)
        self.wstate = WizardState(self.settings)
        self.report_callback_exception = self._on_tk_error

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # header: title, theme switch, stepper
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(14, 6))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Advanced File Finder", font=ctk.CTkFont(size=20, weight="bold")
                     ).grid(row=0, column=0, sticky="w")
        self.theme_switch = ctk.CTkSwitch(header, text="Dark", command=self._toggle_theme, width=70)
        if ctk.get_appearance_mode() == "Dark":
            self.theme_switch.select()
        self.theme_switch.grid(row=0, column=1, sticky="e")
        self.stepper = StepIndicator(header, ["Sources", "Rules", "Preview", "Copy"], on_click=self._jump_back)
        self.stepper.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        # pages
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=1, column=0, sticky="nsew", padx=20, pady=6)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self.steps = [SourcesStep(self.content, self), RulesStep(self.content, self),
                      PreviewStep(self.content, self), CopyStep(self.content, self)]
        self.index = -1

        # footer: message + Back / Next
        footer = ctk.CTkFrame(self, corner_radius=0)
        footer.grid(row=2, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        self.message = ctk.CTkLabel(footer, text="", anchor="w", justify="left", wraplength=500)
        self.message.grid(row=0, column=0, sticky="ew", padx=20, pady=12)
        self.back_btn = ctk.CTkButton(footer, text="‹  Back", width=110, height=36, command=self.back,
                                      fg_color=("gray75", "gray30"), text_color=("gray10", "gray95"),
                                      hover_color=("gray65", "gray40"))
        self.back_btn.grid(row=0, column=1, padx=6, pady=12)
        self.next_btn = ctk.CTkButton(footer, text="Next  ›", width=150, height=36, command=self.next,
                                      font=ctk.CTkFont(weight="bold"))
        self.next_btn.grid(row=0, column=2, padx=(6, 20), pady=12)
        self._next_colors = (self.next_btn.cget("fg_color"), self.next_btn.cget("hover_color"))

        self._resize_job = None
        self.bind("<Configure>", self._on_configure)
        self.bind("<Control-Right>", lambda _e: self.next())
        self.bind("<Control-Left>", lambda _e: self.back())
        self.bind("<Control-z>", self._undo_shortcut)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.go_to(0, forward=True)

    def _set_icon(self) -> None:
        try:
            self.iconbitmap(resource_path("assets/app.ico"))
        except Exception:
            pass

    # ------------------------------------------------------------ navigation
    @property
    def current(self):
        return self.steps[self.index] if self.index >= 0 else None

    def go_to(self, index: int, forward: bool) -> None:
        if self.current:
            self.current.on_leave()
            self.current.grid_forget()
        self.index = index
        step = self.steps[index]
        step.grid(row=0, column=0, sticky="nsew")
        self.stepper.set_step(index)
        self.show_message("", "info")
        self.set_back_enabled(index > 0)
        self.set_next(step.next_text, True)
        step.on_enter(forward)
        self.update_idletasks()
        step.on_resize(self.winfo_width())

    def next(self) -> None:
        step = self.current
        if self.next_btn.cget("state") == "disabled":
            return
        if step.on_next() and self.index < len(self.steps) - 1:
            self.go_to(self.index + 1, forward=True)

    def back(self) -> None:
        if self.back_btn.cget("state") == "disabled" or self.index <= 0:
            return
        self.go_to(self.index - 1, forward=False)

    def _jump_back(self, index: int) -> None:
        if index < self.index and self.back_btn.cget("state") != "disabled":
            self.go_to(index, forward=False)

    def restart(self) -> None:
        """After a finished copy: start a new search from step 1 (settings are kept)."""
        self.wstate.plan, self.wstate.found = None, []
        self.wstate.invalidate_results()
        self.steps[3].phase = "idle"
        self.go_to(0, forward=True)

    # --------------------------------------------------------- footer helpers
    def set_next(self, text: str, enabled: bool = True, danger: bool = False) -> None:
        fg, hover = ("#b91c1c", "#991b1b") if danger else self._next_colors
        self.next_btn.configure(text=text, state="normal" if enabled else "disabled", fg_color=fg, hover_color=hover)

    def set_next_enabled(self, enabled: bool) -> None:
        self.next_btn.configure(state="normal" if enabled else "disabled")

    def set_back_enabled(self, enabled: bool) -> None:
        self.back_btn.configure(state="normal" if enabled else "disabled")

    def show_message(self, text: str, kind: str = "info") -> None:
        color = {"error": col("bad"), "info": col("muted"), "ok": col("ok")}.get(kind, col("muted"))
        self.message.configure(text=("⚠  " + text) if (text and kind == "error") else text, text_color=color)

    # ----------------------------------------------------------- responsive
    def _on_configure(self, event) -> None:
        if event.widget is not self:
            return
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(60, self._apply_size)

    def _apply_size(self) -> None:
        self._resize_job = None
        width = self.winfo_width()
        self.stepper.set_compact(width < COMPACT)
        self.message.configure(wraplength=max(160, width - 360))
        if self.current:
            self.current.on_resize(width)

    # ------------------------------------------------------------------ misc
    def _toggle_theme(self) -> None:
        mode = "dark" if self.theme_switch.get() else "light"
        ctk.set_appearance_mode(mode)
        self.settings.theme = mode
        self.after(50, lambda: [s.on_theme_change() for s in self.steps])

    def _undo_shortcut(self, _e) -> None:
        if self.index == 1:
            self.steps[1].undo()

    def _on_tk_error(self, exc, val, tb) -> None:
        log.error("UI error: %s", "".join(traceback.format_exception(exc, val, tb)))
        self.show_message(f"Something went wrong: {val}", "error")

    def _close(self) -> None:
        try:
            if self.current:
                self.current.on_leave()
            self.wstate.save_into_settings()
            self.settings.window_geometry = self.geometry()
            save_settings(self.settings)
        finally:
            self.destroy()
