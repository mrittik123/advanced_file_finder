"""Reusable widgets: colours, step indicator, card, and a virtualized table."""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass
from typing import Any, Callable

import customtkinter as ctk

PALETTE = {                      # (light, dark)
    "bg": ("#ffffff", "#1e1e22"),
    "row_alt": ("#f5f7fa", "#26262b"),
    "header": ("#e4e8ee", "#2e2e35"),
    "selected": ("#dbe7fd", "#34405a"),
    "text": ("#1a1a1a", "#e8e8e8"),
    "muted": ("#6b7280", "#9aa0a6"),
    "line": ("#d5d9e0", "#3a3a42"),
    "ok": ("#15803d", "#4ade80"),
    "warn": ("#b45309", "#fbbf24"),
    "bad": ("#b91c1c", "#f87171"),
    "accent": ("#2563eb", "#4c8dff"),
}


def col(name: str) -> str:
    light, dark = PALETTE[name]
    return dark if ctk.get_appearance_mode() == "Dark" else light


def accent_pair():
    return ctk.ThemeManager.theme["CTkButton"]["fg_color"]


class Card(ctk.CTkFrame):
    """A rounded panel with an optional title."""

    def __init__(self, master, title: str = "", subtitle: str = "", **kw):
        super().__init__(master, corner_radius=12, **kw)
        self.grid_columnconfigure(0, weight=1)
        self.body_row = 0
        if title:
            ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=15, weight="bold"), anchor="w"
                         ).grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 0))
            self.body_row = 1
        if subtitle:
            self.sub = ctk.CTkLabel(self, text=subtitle, anchor="w", justify="left", wraplength=360,
                                    text_color=("gray35", "gray65"))
            self.sub.grid(row=self.body_row, column=0, sticky="ew", padx=16, pady=(0, 4))
            self.body_row += 1

    def next_row(self) -> int:
        r = self.body_row
        self.body_row += 1
        return r

    def set_wrap(self, px: int) -> None:
        if hasattr(self, "sub"):
            self.sub.configure(wraplength=max(160, px))


class StepIndicator(ctk.CTkFrame):
    """Numbered progress indicator. Collapses to 'Step 2 of 4' plus a bar on narrow windows."""

    def __init__(self, master, labels: list[str], on_click: Callable[[int], None] | None = None):
        super().__init__(master, fg_color="transparent")
        self.labels, self.on_click = labels, on_click
        self.current, self.compact = 0, False
        self.grid_columnconfigure(0, weight=1)

        self.full = ctk.CTkFrame(self, fg_color="transparent")
        self.circles, self.titles, self.lines = [], [], []
        n = len(labels)
        for i, text in enumerate(labels):
            circle = ctk.CTkLabel(self.full, text=str(i + 1), width=34, height=34, corner_radius=17,
                                  font=ctk.CTkFont(size=14, weight="bold"))
            circle.grid(row=0, column=2 * i, padx=4)
            title = ctk.CTkLabel(self.full, text=text, font=ctk.CTkFont(size=12))
            title.grid(row=1, column=2 * i, pady=(2, 0))
            for w in (circle, title):
                w.bind("<Button-1>", lambda _e, i=i: self._clicked(i))
            self.circles.append(circle)
            self.titles.append(title)
            if i < n - 1:
                line = ctk.CTkFrame(self.full, height=3, corner_radius=2)
                line.grid(row=0, column=2 * i + 1, sticky="ew", padx=4)
                self.full.grid_columnconfigure(2 * i + 1, weight=1)
                self.lines.append(line)

        self.small = ctk.CTkFrame(self, fg_color="transparent")
        self.small.grid_columnconfigure(0, weight=1)
        self.small_label = ctk.CTkLabel(self.small, text="", anchor="w",
                                        font=ctk.CTkFont(size=14, weight="bold"))
        self.small_label.grid(row=0, column=0, sticky="ew")
        self.small_bar = ctk.CTkProgressBar(self.small, height=8)
        self.small_bar.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self._show()
        self.set_step(0)

    def _clicked(self, i: int) -> None:
        if self.on_click and i < self.current:
            self.on_click(i)

    def _show(self) -> None:
        if self.compact:
            self.full.grid_remove()
            self.small.grid(row=0, column=0, sticky="ew")
        else:
            self.small.grid_remove()
            self.full.grid(row=0, column=0, sticky="ew")

    def set_compact(self, compact: bool) -> None:
        if compact != self.compact:
            self.compact = compact
            self._show()

    def set_step(self, current: int) -> None:
        self.current = current
        accent = accent_pair()
        grey = ("gray78", "gray28")
        for i, circle in enumerate(self.circles):
            if i < current:
                circle.configure(text="✓", fg_color=accent, text_color="white", cursor="hand2")
            elif i == current:
                circle.configure(text=str(i + 1), fg_color=accent, text_color="white", cursor="")
            else:
                circle.configure(text=str(i + 1), fg_color=grey, text_color=("gray30", "gray70"), cursor="")
            self.titles[i].configure(font=ctk.CTkFont(size=12, weight="bold" if i == current else "normal"),
                                     text_color=("gray10", "gray95") if i <= current else ("gray45", "gray60"))
        for i, line in enumerate(self.lines):
            line.configure(fg_color=accent if i < current else grey)
        self.small_label.configure(text=f"Step {current + 1} of {len(self.labels)}  ·  {self.labels[current]}")
        self.small_bar.set((current + 1) / len(self.labels))


@dataclass
class Column:
    key: str
    title: str
    weight: float = 1.0
    min_w: int = 70
    align: str = "w"              # w | e
    trunc: str = "end"            # end | start (start keeps the file name visible in paths)
    hide_below: int = 0           # auto layout only: hide the column when the table is narrower than this


class VirtualTable(tk.Frame):
    """Table that only draws the rows on screen, so 500k+ rows scroll smoothly.

    Columns fit the width automatically until the user drags a header border; after that the
    widths are fixed (all columns shown, sideways scrolling) until "Reset column widths".
    The table never copies the data: it keeps a list of indexes (the 'view') into `items`.
    """
    ROW_H = 26
    CHECK_W = 36
    MIN_COL = 40
    GRAB = 5                                  # pixels either side of a border that count as the border

    def __init__(self, master, columns: list[Column], *, cell: Callable[[Any, str], str],
                 is_checked: Callable[[Any], bool], set_checked: Callable[[Any, bool], None],
                 status_color: Callable[[Any], str | None] | None = None,
                 search_text: Callable[[Any], str] | None = None,
                 sort_key: Callable[[Any, str], Any] | None = None,
                 on_change: Callable[[], None] | None = None,
                 on_context: Callable[[tk.Event, Any, str | None], None] | None = None,
                 on_open: Callable[[Any], None] | None = None,
                 on_copy: Callable[[Any, str | None], None] | None = None,
                 on_widths_changed: Callable[[dict], None] | None = None,
                 empty_text: str = "Nothing to show"):
        super().__init__(master, bd=0, highlightthickness=0)
        self.columns, self.cell, self.is_checked, self.set_checked = columns, cell, is_checked, set_checked
        self.status_color, self.search_text, self.sort_key = status_color, search_text, sort_key
        self.on_change, self.on_context, self.on_open = on_change, on_context, on_open
        self.on_copy, self.on_widths_changed = on_copy, on_widths_changed
        self.empty_text = empty_text
        self.items: list = []
        self.view: list[int] = []
        self.top = 0
        self.xoff = 0
        self.cursor: int | None = None
        self.cursor_col: str | None = None
        self.sort_col: str | None = None
        self.sort_desc = False
        self.filter_text = ""
        self.extra_filter: Callable[[Any], bool] | None = None
        self.widths: dict[str, int] = {}          # non-empty = manual widths
        self._header_hits: list[tuple[int, int, str]] = []
        self._drag: tuple[str, int, int] | None = None
        self._total_w = 0

        base = tkfont.nametofont("TkDefaultFont")
        self.font = base.copy()
        self.font.configure(size=10)
        self.bold = base.copy()
        self.bold.configure(size=10, weight="bold")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, takefocus=True)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar = ctk.CTkScrollbar(self, command=self._on_vbar)
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar = ctk.CTkScrollbar(self, orientation="horizontal", command=self._on_hbar)
        self.hbar.grid(row=1, column=0, sticky="ew")
        self.hbar.grid_remove()

        c = self.canvas
        c.bind("<Configure>", lambda _e: self.redraw())
        c.bind("<Button-1>", self._click)
        c.bind("<B1-Motion>", self._drag_move)
        c.bind("<ButtonRelease-1>", self._drag_end)
        c.bind("<Motion>", self._motion)
        c.bind("<Double-Button-1>", self._double)
        c.bind("<Button-3>", self._context)
        c.bind("<Button-2>", self._context)
        c.bind("<MouseWheel>", self._wheel)
        c.bind("<Shift-MouseWheel>", lambda e: self._scroll_x(-80 if e.delta > 0 else 80))
        c.bind("<Button-4>", lambda _e: self._scroll_rows(-3))
        c.bind("<Button-5>", lambda _e: self._scroll_rows(3))
        c.bind("<Shift-Button-4>", lambda _e: self._scroll_x(-80))
        c.bind("<Shift-Button-5>", lambda _e: self._scroll_x(80))
        c.bind("<Up>", lambda _e: self._move(-1))
        c.bind("<Down>", lambda _e: self._move(1))
        c.bind("<Prior>", lambda _e: self._move(-self._rows_visible()))
        c.bind("<Next>", lambda _e: self._move(self._rows_visible()))
        c.bind("<Home>", lambda _e: self._move(-10**9))
        c.bind("<End>", lambda _e: self._move(10**9))
        c.bind("<space>", self._space)
        c.bind("<Control-c>", self._ctrl_c)

    # ---------------------------------------------------------------- data
    def set_items(self, items: list, keep_scroll: bool = False) -> None:
        self.items = items
        self._rebuild_view(keep_scroll)

    def set_filter(self, text: str) -> None:
        self.filter_text = text.strip().lower()
        self._rebuild_view()

    def set_extra_filter(self, fn: Callable[[Any], bool] | None) -> None:
        self.extra_filter = fn
        self._rebuild_view()

    def visible_items(self) -> list:
        return [self.items[i] for i in self.view]

    def _rebuild_view(self, keep_scroll: bool = False) -> None:
        items, text = self.items, self.filter_text
        view = range(len(items))
        if text and self.search_text:
            st = self.search_text
            view = [i for i in view if text in st(items[i])]
        if self.extra_filter:
            ef = self.extra_filter
            view = [i for i in view if ef(items[i])]
        view = list(view)
        if self.sort_col and self.sort_key:
            key, sk = self.sort_col, self.sort_key
            view.sort(key=lambda i: sk(items[i], key), reverse=self.sort_desc)
        self.view = view
        if not keep_scroll:
            self.top = 0
            self.cursor = None
        self.redraw()

    def sort_by(self, key: str) -> None:
        if self.sort_col == key:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_col, self.sort_desc = key, False
        self._rebuild_view(keep_scroll=True)

    # ------------------------------------------------------- column widths
    def get_widths(self) -> dict[str, int]:
        return dict(self.widths)

    def set_widths(self, widths: dict | None) -> None:
        clean = {}
        for c in self.columns:
            v = (widths or {}).get(c.key)
            if isinstance(v, int) and not isinstance(v, bool):
                clean[c.key] = max(self.MIN_COL, min(v, 2000))
        self.widths = clean if len(clean) == len(self.columns) else {}
        self.xoff = 0
        self.redraw()

    def reset_widths(self) -> None:
        self.widths = {}
        self.xoff = 0
        self.redraw()
        self._widths_changed()

    def _widths_changed(self) -> None:
        if self.on_widths_changed:
            self.on_widths_changed(self.get_widths())

    def _ensure_manual(self) -> None:
        """Freeze the current automatic widths so they can be edited one by one."""
        if self.widths:
            return
        w = self.canvas.winfo_width()
        cols, ws = self._layout(w)
        self.widths = {c.key: wd for c, wd in zip(cols, ws)}
        for c in self.columns:
            self.widths.setdefault(c.key, max(c.min_w, 150))

    def autofit(self, key: str) -> None:
        """Make a column just wide enough for its header and for the first rows."""
        column = next(c for c in self.columns if c.key == key)
        widest = self.bold.measure(column.title) + 36
        for i in self.view[:1500]:
            widest = max(widest, self.font.measure(self.cell(self.items[i], key)) + 24)
        self._ensure_manual()
        self.widths[key] = max(self.MIN_COL, min(int(widest), 900))
        self.redraw()
        self._widths_changed()

    # -------------------------------------------------------------- layout
    def _rows_visible(self) -> int:
        return max(1, (self.canvas.winfo_height() - self.ROW_H) // self.ROW_H)

    def _layout(self, width: int):
        if self.widths:
            cols = list(self.columns)
            return cols, [self.widths.get(c.key, max(c.min_w, 150)) for c in cols]
        cols = [c for c in self.columns if width >= c.hide_below]
        avail = max(60, width - self.CHECK_W)
        total = sum(c.weight for c in cols) or 1
        return cols, [max(c.min_w, int(avail * c.weight / total)) for c in cols]

    def _fit(self, text: str, width: int, mode: str) -> str:
        maxw = max(10, width - 16)
        if self.font.measure(text) <= maxw:
            return text
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            cand = text[:mid] + "…" if mode == "end" else "…" + text[-mid:]
            if self.font.measure(cand) <= maxw:
                lo = mid
            else:
                hi = mid - 1
        return (text[:lo] + "…") if mode == "end" else ("…" + text[-lo:] if lo else "…")

    # ------------------------------------------------------------- drawing
    def redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 20 or h < 20:
            return
        c.configure(bg=col("bg"))
        cols, widths = self._layout(w)
        rh, n = self.ROW_H, len(self.view)
        rows = self._rows_visible()
        self.top = max(0, min(self.top, max(0, n - rows)))
        self._total_w = sum(widths)
        avail = max(60, w - self.CHECK_W)
        max_x = max(0, self._total_w - avail) if self.widths else 0
        self.xoff = max(0, min(self.xoff, max_x))

        # header
        c.create_rectangle(0, 0, w, rh, fill=col("header"), outline="")
        self._header_hits = []
        x = self.CHECK_W - self.xoff
        for column, wd in zip(cols, widths):
            arrow = (" ▼" if self.sort_desc else " ▲") if self.sort_col == column.key else ""
            title = self._fit(column.title + arrow, wd, "end")
            tx = x + 8 if column.align == "w" else x + wd - 8
            c.create_text(tx, rh / 2, text=title, anchor=column.align, font=self.bold, fill=col("text"))
            c.create_line(x + wd, 5, x + wd, rh - 5, fill=col("line"))          # grab handle hint
            self._header_hits.append((x, x + wd, column.key))
            x += wd
        c.create_rectangle(0, 0, self.CHECK_W, rh, fill=col("header"), outline="")

        # rows
        for r in range(rows + 1):
            vi = self.top + r
            if vi >= n:
                break
            item = self.items[self.view[vi]]
            y0 = rh * (r + 1)
            bg = col("selected") if vi == self.cursor else (col("row_alt") if vi % 2 else col("bg"))
            c.create_rectangle(0, y0, w, y0 + rh, fill=bg, outline="")
            status_fg = self.status_color(item) if self.status_color else None
            x = self.CHECK_W - self.xoff
            for column, wd in zip(cols, widths):
                if x + wd > self.CHECK_W and x < w:                              # skip off-screen columns
                    text = self._fit(self.cell(item, column.key), wd, column.trunc)
                    color = col(status_fg) if (status_fg and column.key == "status") else col("text")
                    if vi == self.cursor and column.key == self.cursor_col:
                        c.create_rectangle(x + 1, y0 + 1, x + wd - 1, y0 + rh - 1, outline=col("accent"))
                    tx = x + 8 if column.align == "w" else x + wd - 8
                    c.create_text(tx, y0 + rh / 2, text=text, anchor=column.align, font=self.font, fill=color)
                x += wd
            c.create_rectangle(0, y0, self.CHECK_W, y0 + rh, fill=bg, outline="")
            self._draw_check(c, 11, y0 + rh / 2, self.is_checked(item))
        c.create_line(0, rh, w, rh, fill=col("line"))
        if not n:
            c.create_text(w / 2, h / 2, text=self.empty_text, fill=col("muted"), font=self.font)

        if n <= rows:
            self.vbar.set(0, 1)
        else:
            self.vbar.set(self.top / n, min(1.0, (self.top + rows) / n))
        if max_x:
            self.hbar.grid()
            self.hbar.set(self.xoff / self._total_w, min(1.0, (self.xoff + avail) / self._total_w))
        else:
            self.hbar.grid_remove()

    def _draw_check(self, c: tk.Canvas, x: int, cy: float, checked: bool) -> None:
        s = 8
        c.create_rectangle(x, cy - s, x + 2 * s, cy + s, outline=col("accent"), width=2,
                           fill=col("accent") if checked else col("bg"))
        if checked:
            c.create_line(x + 4, cy, x + 7, cy + 4, x + 13, cy - 4, fill="white", width=2)

    # -------------------------------------------------------------- events
    def _on_vbar(self, *args) -> None:
        n = len(self.view)
        if args[0] == "moveto":
            self.top = int(float(args[1]) * n)
        elif args[0] == "scroll":
            self.top += int(args[1]) * (self._rows_visible() if args[2] == "pages" else 3)
        self.redraw()

    def _on_hbar(self, *args) -> None:
        if args[0] == "moveto":
            self.xoff = int(float(args[1]) * self._total_w)
        elif args[0] == "scroll":
            self.xoff += int(args[1]) * (400 if args[2] == "pages" else 40)
        self.redraw()

    def _scroll_rows(self, delta: int) -> None:
        self.top += delta
        self.redraw()

    def _scroll_x(self, delta: int) -> None:
        self.xoff += delta
        self.redraw()

    def _wheel(self, e: tk.Event) -> None:
        self._scroll_rows(-3 if e.delta > 0 else 3)

    def _row_at(self, y: int) -> int | None:
        if y < self.ROW_H:
            return None
        vi = self.top + (y - self.ROW_H) // self.ROW_H
        return vi if vi < len(self.view) else None

    def _col_at(self, x: int) -> str | None:
        for x0, x1, key in self._header_hits:
            if x0 <= x < x1 and x >= self.CHECK_W:
                return key
        return None

    def _border_at(self, x: int) -> str | None:
        """Column whose right border is under x (only in the header strip)."""
        if x < self.CHECK_W - self.GRAB:
            return None
        for _x0, x1, key in self._header_hits:
            if abs(x - x1) <= self.GRAB and x1 > self.CHECK_W - 2:
                return key
        return None

    def _motion(self, e: tk.Event) -> None:
        on_border = e.y < self.ROW_H and self._border_at(e.x) is not None
        self.canvas.configure(cursor="sb_h_double_arrow" if on_border else "")

    def _click(self, e: tk.Event) -> None:
        self.canvas.focus_set()
        if e.y < self.ROW_H:
            key = self._border_at(e.x)
            if key:
                self._ensure_manual()
                self._drag = (key, e.x, self.widths[key])
                return
            hit = self._col_at(e.x)
            if hit:
                self.sort_by(hit)
            return
        vi = self._row_at(e.y)
        if vi is None:
            return
        self.cursor, self.cursor_col = vi, self._col_at(e.x)
        if e.x < self.CHECK_W:
            self._toggle(vi)
        self.redraw()

    def _drag_move(self, e: tk.Event) -> None:
        if not self._drag:
            return
        key, x0, w0 = self._drag
        self.widths[key] = max(self.MIN_COL, min(2000, w0 + e.x - x0))
        self.redraw()

    def _drag_end(self, _e: tk.Event) -> None:
        if self._drag:
            self._drag = None
            self._widths_changed()

    def _toggle(self, vi: int) -> None:
        item = self.items[self.view[vi]]
        self.set_checked(item, not self.is_checked(item))
        if self.on_change:
            self.on_change()

    def _space(self, _e) -> None:
        if self.cursor is not None:
            self._toggle(self.cursor)
            self.redraw()

    def _move(self, delta: int) -> None:
        if not self.view:
            return
        cur = 0 if self.cursor is None else self.cursor
        self.cursor = max(0, min(len(self.view) - 1, cur + delta))
        rows = self._rows_visible()
        if self.cursor < self.top:
            self.top = self.cursor
        elif self.cursor >= self.top + rows:
            self.top = self.cursor - rows + 1
        self.redraw()

    def _double(self, e: tk.Event) -> None:
        if e.y < self.ROW_H:
            key = self._border_at(e.x)
            if key:
                self._drag = None
                self.autofit(key)
            return
        vi = self._row_at(e.y)
        if vi is not None and e.x >= self.CHECK_W and self.on_open:
            self.on_open(self.items[self.view[vi]])

    def _ctrl_c(self, _e) -> str:
        if self.cursor is not None and self.on_copy and self.cursor < len(self.view):
            self.on_copy(self.items[self.view[self.cursor]], self.cursor_col)
        return "break"

    def _context(self, e: tk.Event) -> None:
        if e.y < self.ROW_H:
            self._header_menu(e)
            return
        vi = self._row_at(e.y)
        if vi is not None:
            self.cursor, self.cursor_col = vi, self._col_at(e.x)
            self.redraw()
            if self.on_context:
                self.on_context(e, self.items[self.view[vi]], self.cursor_col)

    def _header_menu(self, e: tk.Event) -> None:
        m = tk.Menu(self, tearoff=0)
        key = self._col_at(e.x)
        if key:
            m.add_command(label="Fit this column to its content", command=lambda: self.autofit(key))
        m.add_command(label="Reset column widths (fit window)", command=self.reset_widths)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()
