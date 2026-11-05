import threading

from aff.models import SearchConfig, SearchStats
from aff.scanner import Scanner, is_within
from conftest import names


def scan(cfg, **kw):
    return list(Scanner(cfg, **kw).scan())


def test_recursive_unlimited(tree):
    files = scan(SearchConfig(sources=[str(tree)]))
    assert names(files) == ["a.txt", "b.jpg", "c.txt", "d.PNG", "e.txt", "f.js"]


def test_current_folder_only(tree):
    files = scan(SearchConfig(sources=[str(tree)], recursive=False))
    assert names(files) == ["a.txt", "b.jpg"]


def test_max_depth_zero_with_recursive(tree):
    files = scan(SearchConfig(sources=[str(tree)], recursive=True, max_depth=0))
    assert names(files) == ["a.txt", "b.jpg"]


def test_max_depth_one(tree):
    files = scan(SearchConfig(sources=[str(tree)], max_depth=1))
    assert names(files) == ["a.txt", "b.jpg", "c.txt", "d.PNG", "f.js"]


def test_max_depth_two_reaches_deep(tree):
    files = scan(SearchConfig(sources=[str(tree)], max_depth=2))
    assert "e.txt" in names(files)


def test_overlapping_sources_not_duplicated(tree):
    files = scan(SearchConfig(sources=[str(tree), str(tree / "sub")]))
    assert len(files) == 6
    assert len({f.path for f in files}) == 6


def test_duplicate_sources_ignored(tree):
    assert len(scan(SearchConfig(sources=[str(tree), str(tree)]))) == 6


def test_multiple_sources(tree, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    (other / "z.txt").write_text("z")
    files = scan(SearchConfig(sources=[str(tree / "sub"), str(other)]))
    assert names(files) == ["c.txt", "d.PNG", "e.txt", "z.txt"]
    assert {f.root for f in files} == {str(tree / "sub"), str(other)}


def test_missing_source_is_reported_not_fatal(tree, tmp_path):
    stats = SearchStats()
    files = scan(SearchConfig(sources=[str(tmp_path / "nope"), str(tree)]), stats=stats)
    assert len(files) == 6
    assert len(stats.errors) == 1


def test_cancel(tree):
    cancel = threading.Event()
    stats = SearchStats()
    gen = Scanner(SearchConfig(sources=[str(tree)]), cancel, stats).scan()
    next(gen)
    cancel.set()
    assert list(gen) == []
    assert stats.cancelled


def test_file_info_fields(tree):
    f = next(f for f in scan(SearchConfig(sources=[str(tree)])) if f.name == "c.txt")
    assert f.size == 5 and f.ext == "txt" and f.rel_path.replace("\\", "/") == "sub/c.txt"
    assert f.root == str(tree)


def test_is_within(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    assert is_within(str(tmp_path / "a" / "b"), str(tmp_path / "a"))
    assert is_within(str(tmp_path / "a"), str(tmp_path / "a"))
    assert not is_within(str(tmp_path / "a"), str(tmp_path / "a" / "b"))
    assert not is_within(str(tmp_path / "ab"), str(tmp_path / "a"))
