import os
import shutil

import pytest

from aff.models import ConflictPolicy, Field, Op, PlanStatus, Rule, RuleSet, SearchConfig
from aff.planner import (build_plan, check_free_space, root_labels, unique_path, validate_destination)
from aff.search import run_search
from conftest import names, write


def find(tree):
    return run_search(SearchConfig(sources=[str(tree)]))


def plan_for(tree, dest, policy=ConflictPolicy.KEEP_BOTH, files=None):
    return build_plan(files if files is not None else find(tree), str(dest), [str(tree)], policy)


def rel(plan, dest):
    return sorted(os.path.relpath(i.dest, dest).replace("\\", "/") for i in plan.items)


def test_structure_preserved(tree, tmp_path):
    dest = tmp_path / "out"
    plan = plan_for(tree, dest)
    assert rel(plan, dest) == ["root/a.txt", "root/b.jpg", "root/node_modules/f.js",
                               "root/sub/c.txt", "root/sub/d.PNG", "root/sub/deep/e.txt"]
    assert all(i.status is PlanStatus.NEW and i.selected for i in plan.items)
    assert plan.selected_size == sum(i.source.size for i in plan.items)


def test_two_sources_same_name_get_separate_folders(tmp_path):
    a, b = tmp_path / "a" / "photos", tmp_path / "b" / "photos"
    write(a / "x.jpg", "1")
    write(b / "x.jpg", "2")
    files = run_search(SearchConfig(sources=[str(a), str(b)]))
    plan = build_plan(files, str(tmp_path / "out"), [str(a), str(b)])
    assert rel(plan, tmp_path / "out") == ["photos/x.jpg", "photos_2/x.jpg"]
    assert root_labels([str(a), str(b)]) == {str(a): "photos", str(b): "photos_2"}


def test_conflict_skip(tree, tmp_path):
    dest = tmp_path / "out"
    write(dest / "root" / "a.txt", "old")
    plan = plan_for(tree, dest, ConflictPolicy.SKIP)
    item = next(i for i in plan.items if i.source.name == "a.txt")
    assert item.status is PlanStatus.EXISTS and not item.selected
    assert len(plan.selected_items) == 5


def test_conflict_overwrite(tree, tmp_path):
    dest = tmp_path / "out"
    write(dest / "root" / "a.txt", "old")
    item = next(i for i in plan_for(tree, dest, ConflictPolicy.OVERWRITE).items if i.source.name == "a.txt")
    assert item.status is PlanStatus.WOULD_OVERWRITE and item.selected


def test_conflict_keep_both_names_are_unique(tree, tmp_path):
    dest = tmp_path / "out"
    write(dest / "root" / "a.txt", "old")
    write(dest / "root" / "a (1).txt", "old")
    item = next(i for i in plan_for(tree, dest).items if i.source.name == "a.txt")
    assert item.status is PlanStatus.NEW and os.path.basename(item.dest) == "a (2).txt"


def test_conflict_overwrite_if_newer(tree, tmp_path):
    dest = tmp_path / "out"
    existing = write(dest / "root" / "a.txt", "old")
    src = tree / "a.txt"
    os.utime(existing, (1_600_000_000, 1_600_000_000))       # destination older
    os.utime(src, (1_700_000_000, 1_700_000_000))
    p = plan_for(tree, dest, ConflictPolicy.OVERWRITE_IF_NEWER)
    assert next(i for i in p.items if i.source.name == "a.txt").status is PlanStatus.WOULD_OVERWRITE
    os.utime(existing, (1_800_000_000, 1_800_000_000))       # destination newer
    p = plan_for(tree, dest, ConflictPolicy.OVERWRITE_IF_NEWER)
    item = next(i for i in p.items if i.source.name == "a.txt")
    assert item.status is PlanStatus.EXISTS and not item.selected


def test_folder_in_the_way_is_an_error(tree, tmp_path):
    dest = tmp_path / "out"
    (dest / "root" / "a.txt").mkdir(parents=True)
    item = next(i for i in plan_for(tree, dest).items if i.source.name == "a.txt")
    assert item.status is PlanStatus.ERROR and not item.selected


def test_source_equals_destination_file_is_an_error(tree, tmp_path):
    # destination = parent of source, so root/a.txt would map onto itself
    plan = build_plan(find(tree), str(tree.parent), [str(tree)], ConflictPolicy.OVERWRITE)
    assert all(i.status is PlanStatus.ERROR for i in plan.items)


def test_unique_path_considers_planned_names(tmp_path):
    p = str(tmp_path / "x.txt")
    taken = {os.path.normcase(p)}
    assert unique_path(p, taken) == str(tmp_path / "x (1).txt")


def test_destination_inside_source_rejected(tree):
    assert validate_destination([str(tree)], str(tree / "sub" / "out"))
    assert validate_destination([str(tree)], str(tree))
    assert validate_destination([str(tree)], "  ")


def test_destination_outside_source_ok(tree, tmp_path):
    assert validate_destination([str(tree)], str(tmp_path / "out")) == []
    assert validate_destination([str(tree)], str(tmp_path / "root_backup")) == []   # name prefix only


def test_destination_must_not_be_a_file(tree, tmp_path):
    f = write(tmp_path / "file.txt", "x")
    assert validate_destination([str(tree)], str(f))


def test_free_space_ok_and_not_enough(tree, tmp_path, monkeypatch):
    plan = plan_for(tree, tmp_path / "does" / "not" / "exist")
    assert check_free_space(plan).ok
    Usage = shutil._ntuple_diskusage
    monkeypatch.setattr(shutil, "disk_usage", lambda p: Usage(100, 99, 1))
    result = check_free_space(plan)
    assert not result.ok and result.required == plan.selected_size and "not enough" in result.message()


def test_plan_after_rules_end_to_end(tree, tmp_path):
    rs = RuleSet()
    rs.add_include(Rule(Field.EXTENSION, Op.IN_LIST, "txt,jpg"))
    rs.add_exclude(Rule(Field.FOLDER, Op.CONTAINS, "deep"))
    files = run_search(SearchConfig(sources=[str(tree)], rules=rs))
    assert names(files) == ["a.txt", "b.jpg", "c.txt"]
    plan = build_plan(files, str(tmp_path / "out"), [str(tree)])
    assert len(plan.items) == 3
