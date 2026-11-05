import os
import threading

from aff.copier import Copier, PARTIAL_SUFFIX
from aff.models import ConflictPolicy, SearchConfig
from aff.planner import build_plan
from aff.search import run_search
from conftest import write


def make_plan(tree, dest, policy=ConflictPolicy.KEEP_BOTH):
    files = run_search(SearchConfig(sources=[str(tree)]))
    return build_plan(files, str(dest), [str(tree)], policy)


def run(plan, tmp_path, **kw):
    return Copier(plan, log_dir=tmp_path / "logs", **kw).run()


def test_copies_everything_and_preserves_structure(tree, tmp_path):
    dest = tmp_path / "out"
    rep = run(make_plan(tree, dest), tmp_path)
    assert (rep.copied, rep.skipped, rep.failed) == (6, 0, 0)
    assert (dest / "root" / "sub" / "deep" / "e.txt").read_text() == "epsilon invoice"
    assert (tree / "a.txt").exists()                               # sources untouched
    assert rep.log_path and rep.log_path.exists()
    assert not list(dest.rglob("*" + PARTIAL_SUFFIX))


def test_modified_time_preserved(tree, tmp_path):
    os.utime(tree / "a.txt", (1_600_000_000, 1_600_000_000))
    dest = tmp_path / "out"
    run(make_plan(tree, dest), tmp_path)
    assert int((dest / "root" / "a.txt").stat().st_mtime) == 1_600_000_000


def test_only_selected_items_are_copied(tree, tmp_path):
    plan = make_plan(tree, tmp_path / "out")
    for item in plan.items:
        item.selected = item.source.name.endswith(".txt")
    rep = run(plan, tmp_path)
    assert rep.copied == 3 and not (tmp_path / "out" / "root" / "b.jpg").exists()


def test_skip_policy_keeps_existing_file(tree, tmp_path):
    dest = tmp_path / "out"
    write(dest / "root" / "a.txt", "old")
    rep = run(make_plan(tree, dest, ConflictPolicy.SKIP), tmp_path)
    assert (dest / "root" / "a.txt").read_text() == "old" and rep.copied == 5


def test_overwrite_policy(tree, tmp_path):
    dest = tmp_path / "out"
    write(dest / "root" / "a.txt", "old")
    run(make_plan(tree, dest, ConflictPolicy.OVERWRITE), tmp_path)
    assert (dest / "root" / "a.txt").read_text() == "alpha invoice"


def test_overwrite_read_only_destination(tree, tmp_path):
    dest = tmp_path / "out"
    old = write(dest / "root" / "a.txt", "old")
    os.chmod(old, 0o444)
    rep = run(make_plan(tree, dest, ConflictPolicy.OVERWRITE), tmp_path)
    assert rep.failed == 0 and old.read_text() == "alpha invoice"


def test_keep_both(tree, tmp_path):
    dest = tmp_path / "out"
    write(dest / "root" / "a.txt", "old")
    run(make_plan(tree, dest), tmp_path)
    assert (dest / "root" / "a.txt").read_text() == "old"
    assert (dest / "root" / "a (1).txt").read_text() == "alpha invoice"


def test_destination_changed_after_preview_is_respected(tree, tmp_path):
    dest = tmp_path / "out"
    plan = make_plan(tree, dest, ConflictPolicy.SKIP)             # preview says "new"
    write(dest / "root" / "a.txt", "appeared later")
    rep = run(plan, tmp_path)
    assert (dest / "root" / "a.txt").read_text() == "appeared later" and rep.skipped == 1


def test_one_failing_file_does_not_stop_the_run(tree, tmp_path):
    plan = make_plan(tree, tmp_path / "out")
    os.remove(tree / "b.jpg")                                      # vanishes after the search
    rep = run(plan, tmp_path)
    assert rep.failed == 1 and rep.copied == 5
    assert rep.failures[0][0].endswith("b.jpg")
    assert not list((tmp_path / "out").rglob("*" + PARTIAL_SUFFIX))


def test_cancel_stops_and_cleans_up(tree, tmp_path):
    cancel = threading.Event()
    plan = make_plan(tree, tmp_path / "out")
    seen = []

    def on_progress(p):
        seen.append(p.files_done)
        if p.files_done >= 2:
            cancel.set()

    rep = run(plan, tmp_path, cancel=cancel, on_progress=on_progress)
    assert rep.cancelled and rep.copied == 2
    assert not list((tmp_path / "out").rglob("*" + PARTIAL_SUFFIX))


def test_verify_option(tree, tmp_path):
    rep = run(make_plan(tree, tmp_path / "out"), tmp_path, verify=True)
    assert rep.failed == 0 and rep.copied == 6


def test_progress_reaches_100_percent(tree, tmp_path):
    c = Copier(make_plan(tree, tmp_path / "out"), log_dir=tmp_path / "logs")
    c.run()
    assert c.progress.fraction == 1.0 and c.progress.files_done == 6
