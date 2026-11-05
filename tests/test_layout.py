import os
from datetime import datetime

from aff.copier import Copier
from aff.layout import relative_dest, validate_pattern
from aff.models import ConflictPolicy, LayoutMode, OutputLayout, PlanStatus, SearchConfig
from aff.planner import build_plan, carry_selection
from aff.search import run_search
from conftest import info, write


def rel(path):
    return path.replace("\\", "/")


def lay(mode, **kw):
    return OutputLayout(mode=mode, **kw)


def test_preserve_with_and_without_source_name():
    f = info(path=os.path.join("/data", "photos", "Holiday.JPG"), root="/data")
    assert rel(relative_dest(f, "data", lay(LayoutMode.PRESERVE))) == "data/photos/Holiday.JPG"
    assert rel(relative_dest(f, "data", lay(LayoutMode.PRESERVE, include_source_name=False))) == "photos/Holiday.JPG"


def test_flat():
    f = info()
    assert relative_dest(f, "data", lay(LayoutMode.FLAT)) == "Holiday.JPG"


def test_custom_tokens():
    ts = datetime(2024, 3, 5, 9, 0).timestamp()
    f = info(path="/data/photos/Holiday.JPG", modified=ts, created=datetime(2020, 1, 2).timestamp())
    c = lambda p, **kw: rel(relative_dest(f, "data", lay(LayoutMode.CUSTOM, pattern=p, **kw)))
    assert c("{ext}/{name}") == "jpg/Holiday.JPG"
    assert c("{category}/{year}/{month}/{name}") == "Images/2024/03/Holiday.JPG"
    assert c("{date}_{name}") == "2024-03-05_Holiday.JPG"
    assert c("{year}", date_field="created") == "2020/Holiday.JPG"            # folder-only pattern keeps the name
    assert c("{source}\\{parent}\\{stem}.bak") == "data/photos/Holiday.bak"
    assert c("{month_name}/{name}") == "March/Holiday.JPG"
    assert c("{rel_dir}/{name}") == "photos/Holiday.JPG"


def test_custom_unknown_category_and_no_extension():
    f = info(path="/data/README")
    assert rel(relative_dest(f, "d", lay(LayoutMode.CUSTOM, pattern="{category}/{ext}/{name}"))) == "Other/no_extension/README"


def test_invalid_characters_are_cleaned():
    f = info(path="/data/a:b/x.txt")
    out = rel(relative_dest(f, "d", lay(LayoutMode.CUSTOM, pattern="{parent}/{name}")))
    assert out == "a_b/x.txt"


def test_pattern_validation():
    assert validate_pattern("{category}/{year}/{name}") == []
    assert validate_pattern("") and validate_pattern("{nope}/{name}") and validate_pattern("/abs/{name}")
    assert validate_pattern("C:\\x\\{name}") and validate_pattern("../{name}") and validate_pattern("{name")


def make(tree, dest, layout, policy=ConflictPolicy.KEEP_BOTH):
    files = run_search(SearchConfig(sources=[str(tree)]))
    return build_plan(files, str(dest), [str(tree)], policy, layout=layout)


def test_flat_duplicates_are_renamed_even_with_overwrite(tree, tmp_path):
    write(tree / "sub" / "a.txt", "second a")             # same name as root/a.txt
    plan = make(tree, tmp_path / "out", lay(LayoutMode.FLAT), ConflictPolicy.OVERWRITE)
    names = sorted(os.path.basename(i.dest) for i in plan.items)
    assert names.count("a.txt") == 1 and "a (1).txt" in names
    assert len(set(i.dest for i in plan.items)) == len(plan.items)
    assert all(i.status is PlanStatus.NEW for i in plan.items if "a" in os.path.basename(i.dest)[:1])


def test_flat_copy_puts_everything_in_one_folder(tree, tmp_path):
    dest = tmp_path / "out"
    plan = make(tree, dest, lay(LayoutMode.FLAT))
    rep = Copier(plan, log_dir=tmp_path / "logs").run()
    assert rep.copied == 6 and rep.failed == 0
    assert sorted(os.listdir(dest)) == ["a.txt", "b.jpg", "c.txt", "d.PNG", "e.txt", "f.js"]


def test_custom_copy_by_category(tree, tmp_path):
    dest = tmp_path / "out"
    plan = make(tree, dest, lay(LayoutMode.CUSTOM, pattern="{category}/{name}"))
    Copier(plan, log_dir=tmp_path / "logs").run()
    assert sorted(os.listdir(dest)) == ["Code", "Documents", "Images"]
    assert sorted(os.listdir(dest / "Images")) == ["b.jpg", "d.PNG"]


def test_carry_selection_keeps_unticked_files(tree, tmp_path):
    old = make(tree, tmp_path / "out", lay(LayoutMode.PRESERVE))
    next(i for i in old.items if i.source.name == "b.jpg").selected = False
    new = make(tree, tmp_path / "out", lay(LayoutMode.FLAT))
    carry_selection(old, new)
    assert [i.source.name for i in new.items if not i.selected] == ["b.jpg"]
