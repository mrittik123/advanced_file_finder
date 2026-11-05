"""Drives the real window through all four steps. Skipped when there is no display / tkinter."""
import os
import time

import pytest

pytest.importorskip("customtkinter")

from aff.models import Field, Op, Rule  # noqa: E402


@pytest.fixture
def wizard():
    try:
        from aff.ui.wizard import Wizard
        w = Wizard()
    except Exception as e:                       # no display, no tkinter, ...
        pytest.skip(f"UI cannot start here: {e}")
    yield w
    try:
        w.destroy()
    except Exception:
        pass


def pump(w, seconds=0.3, until=None):
    end = time.time() + seconds
    while time.time() < end:
        w.update()
        if until and until():
            return
        time.sleep(0.01)


def test_wizard_end_to_end(wizard, tree, tmp_path):
    w, dest = wizard, tmp_path / "out"
    w.wstate.sources, w.wstate.destination = [str(tree)], str(dest)
    w.steps[0].on_enter(True)
    w.next()
    assert w.index == 1
    w.steps[1]._chip("include", [Rule(Field.EXTENSION, Op.IN_LIST, "txt")])
    w.next()
    assert w.index == 2
    pump(w, 10, until=lambda: not w.steps[2].searching)
    assert w.steps[2].sel_count == 3
    w.next()
    assert w.index == 3
    w.next()                                              # Start copy
    pump(w, 10, until=lambda: w.steps[3].phase == "done")
    assert w.steps[3].report.copied == 3
    assert (dest / "root" / "sub" / "deep" / "e.txt").exists()


def test_validation_blocks_next(wizard, tmp_path):
    w = wizard
    w.wstate.sources, w.wstate.destination = [], ""
    w.steps[0].on_enter(True)
    w.next()
    assert w.index == 0 and "Add at least one folder" in w.message.cget("text")
    w.wstate.sources = [str(tmp_path)]
    w.wstate.destination = str(tmp_path / "inside")        # destination inside the source
    w.steps[0].on_enter(True)
    w.next()
    assert w.index == 0


def test_back_and_undo(wizard, tmp_path):
    w = wizard
    w.wstate.sources, w.wstate.destination = [str(tmp_path)], str(tmp_path.parent / "dst")
    w.steps[0].on_enter(True)
    w.next()
    rules = w.steps[1]
    rules._chip("exclude", [Rule(Field.HIDDEN, Op.IS_TRUE)])
    assert len(w.wstate.rules.exclude.children) == 1
    rules.undo()
    assert len(w.wstate.rules.exclude.children) == 0
    w.back()
    assert w.index == 0


def test_responsive_switch(wizard):
    w = wizard
    w.geometry("600x700")
    pump(w, 0.5)
    assert w.stepper.compact
    w.geometry("1100x700")
    pump(w, 0.5)
    assert not w.stepper.compact


def _to_step(w, n, tree, dest):
    w.wstate.sources, w.wstate.destination = [str(tree)], str(dest)
    w.steps[0].on_enter(True)
    for _ in range(n):
        w.next()
        if w.index == 2:
            pump(w, 10, until=lambda: not w.steps[2].searching)


def test_output_layout_flat_and_custom(wizard, tree, tmp_path):
    w, dest = wizard, tmp_path / "out"
    _to_step(w, 3, tree, dest)
    assert w.index == 3
    cs = w.steps[3]
    cs.mode_seg.set("All files together")
    cs._mode_changed("All files together")
    pump(w, 5, until=lambda: not cs._replanning and not cs._replan_job and cs.state.plan
         and all(os.path.dirname(i.dest) == str(dest) for i in cs.state.plan.items))
    assert all(os.path.dirname(i.dest) == str(dest) for i in w.wstate.plan.items)
    # custom pattern, invalid first
    cs.mode_seg.set("Custom pattern")
    cs._mode_changed("Custom pattern")
    cs.pattern_entry.delete(0, "end")
    cs.pattern_entry.insert(0, "{nope}/{name}")
    cs._layout_changed()
    assert not cs._layout_valid and "Unknown placeholder" in cs.pattern_error.cget("text")
    assert w.next_btn.cget("state") == "disabled"
    cs.pattern_entry.delete(0, "end")
    cs.pattern_entry.insert(0, "{category}/{name}")
    cs._layout_changed()
    pump(w, 5, until=lambda: not cs._replanning and not cs._replan_job and any(
        "Images" in i.dest for i in cs.state.plan.items))
    w.next()
    pump(w, 10, until=lambda: cs.phase == "done")
    assert cs.report.copied == 6
    assert sorted(os.listdir(dest)) == ["Code", "Documents", "Images"]


def test_back_to_preview_shows_new_layout_without_new_search(wizard, tree, tmp_path):
    w, dest = wizard, tmp_path / "out"
    _to_step(w, 3, tree, dest)
    cs = w.steps[3]
    cs.mode_seg.set("All files together")
    cs._mode_changed("All files together")
    pump(w, 5, until=lambda: not cs._replanning and not cs._replan_job)
    pump(w, 0.5)
    w.back()
    assert w.index == 2 and not w.steps[2].searching          # cached results, not a new search
    assert all(os.path.dirname(i.dest) == str(dest) for i in w.steps[2].items)


def test_table_resize_autofit_and_copy_cell(wizard, tree, tmp_path):
    w = wizard
    _to_step(w, 2, tree, tmp_path / "out")
    pv = w.steps[2]
    t = pv.table
    pump(w, 0.5)
    t._ensure_manual()
    before = t.widths["name"]

    class E:                      # minimal fake mouse event
        x, y = 100, 5

    t._drag = ("name", 0, before)
    t._drag_move(E)
    assert t.widths["name"] == before + 100
    t._drag_end(E)
    assert w.wstate.settings.preview_col_widths["name"] == before + 100     # remembered
    t._drag = ("name", 0, before)
    E.x = -10_000
    t._drag_move(E)
    assert t.widths["name"] == t.MIN_COL                                     # cannot collapse below the minimum
    t._drag = None
    t.autofit("size")
    assert t.widths["size"] >= t.MIN_COL
    t.reset_widths()
    assert not t.widths

    item = t.items[t.view[0]]
    pv._copy_cell(item, "name")
    try:
        assert w.clipboard_get() == item.source.name
    except Exception:
        pytest.skip("no clipboard in this environment")
    pv._to_clipboard(pv._value(item, "path"), "full source path")
    assert w.clipboard_get() == item.source.path
