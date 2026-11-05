"""Base class for the four wizard pages."""
from __future__ import annotations

import customtkinter as ctk


class Step(ctk.CTkFrame):
    title = ""
    next_text = "Next  ›"

    def __init__(self, master, wizard):
        super().__init__(master, fg_color="transparent")
        self.wizard = wizard
        self.state = wizard.wstate

    def on_enter(self, forward: bool) -> None:
        """Called every time the page is shown."""

    def on_leave(self) -> None:
        """Called when the user leaves the page (Back or Next)."""

    def validate(self) -> str | None:
        """Return an error message to block 'Next', or None."""
        return None

    def on_next(self) -> bool:
        """Next was pressed. Return True to move on to the next page."""
        err = self.validate()
        if err:
            self.wizard.show_message(err, "error")
            return False
        return True

    def on_resize(self, width: int) -> None:
        """Window width changed: re-arrange the layout for narrow/wide."""

    def on_theme_change(self) -> None:
        """Appearance mode changed (for custom-drawn widgets)."""
