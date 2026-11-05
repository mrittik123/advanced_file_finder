import codecs

from aff.content import ContentResult, detect_encoding, file_contains, make_line_matcher
from aff.models import Field, Op, Rule, RuleSet
from aff.models import SearchStats
from aff.rules import RuleEngine
from aff.scanner import Scanner
from aff.models import SearchConfig
from conftest import write

MB = 1024 * 1024


def check(path, text, op=Op.CONTAINS, cs=False, max_bytes=50 * MB):
    return file_contains(str(path), make_line_matcher(op, text, cs), max_bytes=max_bytes)


def test_plain_text_match(tmp_path):
    p = write(tmp_path / "a.txt", "hello\nworld\n")
    assert check(p, "world") is ContentResult.MATCH
    assert check(p, "nothing") is ContentResult.NO_MATCH


def test_case_sensitivity(tmp_path):
    p = write(tmp_path / "a.txt", "Hello")
    assert check(p, "hello") is ContentResult.MATCH
    assert check(p, "hello", cs=True) is ContentResult.NO_MATCH


def test_regex(tmp_path):
    p = write(tmp_path / "a.txt", "order 12345 shipped")
    assert check(p, r"order \d{5}", Op.REGEX) is ContentResult.MATCH
    assert check(p, r"order \d{6}", Op.REGEX) is ContentResult.NO_MATCH


def test_contains_treats_text_literally(tmp_path):
    p = write(tmp_path / "a.txt", "price (USD) [new]")
    assert check(p, "(USD) [new]") is ContentResult.MATCH


def test_binary_skipped(tmp_path):
    p = write(tmp_path / "a.bin", data=b"\x00\x01\x02needle\x00")
    assert check(p, "needle") is ContentResult.BINARY


def test_size_cap(tmp_path):
    p = write(tmp_path / "big.txt", "needle" * 1000)
    assert check(p, "needle", max_bytes=100) is ContentResult.TOO_LARGE


def test_empty_file(tmp_path):
    assert check(write(tmp_path / "e.txt", ""), "x") is ContentResult.NO_MATCH


def test_utf8_bom(tmp_path):
    p = write(tmp_path / "a.txt", data=codecs.BOM_UTF8 + "héllo wörld".encode("utf-8"))
    assert check(p, "wörld") is ContentResult.MATCH


def test_utf16_with_bom(tmp_path):
    p = write(tmp_path / "a.txt", data="line one\nrésumé\n".encode("utf-16"))
    assert detect_encoding(p.read_bytes()) == "utf-16"
    assert check(p, "résumé") is ContentResult.MATCH


def test_utf32_with_bom(tmp_path):
    p = write(tmp_path / "a.txt", data="needle".encode("utf-32"))
    assert check(p, "needle") is ContentResult.MATCH


def test_legacy_cp1252(tmp_path):
    p = write(tmp_path / "a.txt", data="caf\xe9 cr\xe8me".encode("latin-1"))
    assert check(p, "café") is ContentResult.MATCH


def test_invalid_bytes_do_not_crash(tmp_path):
    p = write(tmp_path / "a.txt", data=b"good text \x81\x8d\x8f more text needle")
    assert check(p, "needle") is ContentResult.MATCH


def test_missing_file_is_error_not_exception(tmp_path):
    assert check(tmp_path / "nope.txt", "x") is ContentResult.ERROR


def test_match_on_last_line_without_newline(tmp_path):
    p = write(tmp_path / "a.txt", "a\nb\nneedle")
    assert check(p, "needle") is ContentResult.MATCH


def test_content_rule_end_to_end_with_stats(tree):
    write(tree / "bin.dat", data=b"\x00\x00invoice\x00")
    rs = RuleSet()
    rs.add_include(Rule(Field.CONTENT, Op.CONTAINS, "invoice"))
    stats = SearchStats()
    engine = RuleEngine(rs, stats=stats)
    found = [f.name for f in Scanner(SearchConfig(sources=[str(tree)])).scan() if engine.matches(f)]
    assert sorted(found) == ["a.txt", "e.txt"]
    assert stats.content_binary_skipped == 1


def test_content_rule_respects_size_cap(tree):
    rs = RuleSet()
    rs.add_include(Rule(Field.CONTENT, Op.CONTAINS, "invoice"))
    stats = SearchStats()
    engine = RuleEngine(rs, content_max_bytes=5, stats=stats)
    found = [f for f in Scanner(SearchConfig(sources=[str(tree)])).scan() if engine.matches(f)]
    assert found == [] and stats.content_too_large_skipped >= 2


def test_cheap_rules_run_before_content_rules(tree):
    """AND of (extension jpg) and (content): the content rule must not run for non-jpg files."""
    from aff.models import GroupOp
    rs = RuleSet()
    rs.include.operator = GroupOp.AND
    rs.add_include(Rule(Field.CONTENT, Op.CONTAINS, "invoice"))
    rs.add_include(Rule(Field.EXTENSION, Op.IN_LIST, "jpg"))
    stats = SearchStats()
    engine = RuleEngine(rs, stats=stats)
    found = [f for f in Scanner(SearchConfig(sources=[str(tree)])).scan() if engine.matches(f)]
    assert found == []
    assert stats.content_binary_skipped == 0 and stats.content_errors == 0
