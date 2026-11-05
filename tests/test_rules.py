import os
from datetime import datetime

import pytest

from aff.models import Field, GroupOp, Op, Rule, RuleGroup, RuleSet
from aff.rules import RuleEngine, RuleError, compile_rule, validate_ruleset
from aff.summary import describe_ruleset
from conftest import info


def engine(include=(), exclude=(), inc_op=GroupOp.OR, exc_op=GroupOp.OR):
    rs = RuleSet()
    rs.include.operator, rs.exclude.operator = inc_op, exc_op
    for r in include:
        rs.add_include(r)
    for r in exclude:
        rs.add_exclude(r)
    return RuleEngine(rs)


def R(field, op, value="", value2=None, **kw):
    return Rule(field, op, value, value2, **kw)


# ---- name ----
def test_wildcard_case_insensitive_default():
    assert engine([R(Field.NAME, Op.WILDCARD, "*.jpg")]).matches(info())


def test_wildcard_case_sensitive():
    e = engine([R(Field.NAME, Op.WILDCARD, "*.jpg", case_sensitive=True)])
    assert not e.matches(info())
    assert e.matches(info(path="/data/x.jpg"))


def test_wildcard_multiple_patterns():
    e = engine([R(Field.NAME, Op.WILDCARD, "*.png; *.jpg")])
    assert e.matches(info()) and not e.matches(info(path="/data/x.gif"))


def test_wildcard_question_mark_and_whole_name():
    e = engine([R(Field.NAME, Op.WILDCARD, "a?.txt")])
    assert e.matches(info(path="/d/ab.txt"))
    assert not e.matches(info(path="/d/abc.txt")) and not e.matches(info(path="/d/ab.txt.bak"))


def test_regex_filename_only():
    e = engine([R(Field.NAME, Op.REGEX, r"^holiday\.(jpg|png)$")])
    assert e.matches(info())
    # regex applies to the file name, not the folder
    assert not engine([R(Field.NAME, Op.REGEX, "photos")]).matches(info())


def test_regex_case_sensitive():
    assert not engine([R(Field.NAME, Op.REGEX, "holiday", case_sensitive=True)]).matches(info())
    assert engine([R(Field.NAME, Op.REGEX, "Holiday", case_sensitive=True)]).matches(info())


@pytest.mark.parametrize("op,value,expected", [
    (Op.CONTAINS, "oliday", True), (Op.STARTS_WITH, "holi", True), (Op.ENDS_WITH, ".jpg", True),
    (Op.EQUALS, "holiday.jpg", True), (Op.EQUALS, "holiday", False), (Op.STARTS_WITH, "day", False),
])
def test_text_ops(op, value, expected):
    assert engine([R(Field.NAME, op, value)]).matches(info()) is expected


# ---- extension ----
def test_extension_list_variants():
    e = engine([R(Field.EXTENSION, Op.IN_LIST, ".jpg, png;gif")])
    assert e.matches(info()) and e.matches(info(path="/d/x.GIF"))
    assert not e.matches(info(path="/d/x.txt")) and not e.matches(info(path="/d/noext"))


def test_extension_case_sensitive():
    e = engine([R(Field.EXTENSION, Op.IN_LIST, "jpg", case_sensitive=True)])
    assert not e.matches(info())          # .JPG


# ---- path / folder ----
def test_folder_contains_and_path_wildcard():
    assert engine([R(Field.FOLDER, Op.CONTAINS, "photos")]).matches(info())
    assert not engine([R(Field.FOLDER, Op.CONTAINS, "Holiday")]).matches(info())   # file name is not folder
    assert engine([R(Field.PATH, Op.WILDCARD, "*photos*")]).matches(info())


# ---- size ----
@pytest.mark.parametrize("op,v,v2,size,expected", [
    (Op.GT, "1KB", None, 2048, True), (Op.GT, "1KB", None, 1024, False),
    (Op.GTE, "1KB", None, 1024, True), (Op.LT, "1MB", None, 10, True),
    (Op.LTE, "10", None, 10, True), (Op.EQUALS, "5", None, 5, True),
    (Op.BETWEEN, "1KB", "2KB", 1500, True), (Op.BETWEEN, "2KB", "1KB", 1500, True),
    (Op.BETWEEN, "1KB", "2KB", 3000, False),
])
def test_size(op, v, v2, size, expected):
    assert engine([R(Field.SIZE, op, v, v2)]).matches(info(size=size)) is expected


# ---- dates ----
def ts(*a):
    return datetime(*a).timestamp()


def test_modified_whole_day_semantics():
    f = info(modified=ts(2024, 3, 15, 23, 30))
    assert engine([R(Field.MODIFIED, Op.EQUALS, "2024-03-15")]).matches(f)
    assert not engine([R(Field.MODIFIED, Op.GT, "2024-03-15")]).matches(f)      # same day is not "after"
    assert engine([R(Field.MODIFIED, Op.GT, "2024-03-14")]).matches(f)
    assert engine([R(Field.MODIFIED, Op.LTE, "2024-03-15")]).matches(f)
    assert not engine([R(Field.MODIFIED, Op.LT, "2024-03-15")]).matches(f)
    assert engine([R(Field.MODIFIED, Op.GTE, "2024-03-15")]).matches(f)


def test_modified_between_inclusive_days():
    e = engine([R(Field.MODIFIED, Op.BETWEEN, "2024-03-01", "2024-03-15")])
    assert e.matches(info(modified=ts(2024, 3, 15, 23, 59)))
    assert e.matches(info(modified=ts(2024, 3, 1, 0, 0)))
    assert not e.matches(info(modified=ts(2024, 3, 16, 0, 0)))
    assert not e.matches(info(modified=ts(2024, 2, 29, 23, 59)))


def test_datetime_precision():
    f = info(modified=ts(2024, 3, 15, 12, 0))
    assert engine([R(Field.MODIFIED, Op.GT, "2024-03-15 11:00")]).matches(f)
    assert not engine([R(Field.MODIFIED, Op.GT, "2024-03-15 12:00")]).matches(f)


def test_created_uses_created_timestamp():
    f = info(created=ts(2020, 1, 1, 10), modified=ts(2024, 1, 1, 10))
    assert engine([R(Field.CREATED, Op.LT, "2021-01-01")]).matches(f)
    assert not engine([R(Field.MODIFIED, Op.LT, "2021-01-01")]).matches(f)


# ---- attributes ----
def test_attributes():
    f = info(hidden=True, readonly=False)
    assert engine([R(Field.HIDDEN, Op.IS_TRUE)]).matches(f)
    assert not engine([R(Field.HIDDEN, Op.IS_FALSE)]).matches(f)
    assert engine([R(Field.READONLY, Op.IS_FALSE)]).matches(f)
    assert not engine([R(Field.SYSTEM, Op.IS_TRUE)]).matches(f)


# ---- combination logic ----
def test_no_rules_matches_everything():
    assert engine().matches(info())


def test_exclude_only_means_everything_except():
    e = engine(exclude=[R(Field.EXTENSION, Op.IN_LIST, "jpg")])
    assert not e.matches(info()) and e.matches(info(path="/d/x.txt"))


def test_exclude_always_wins():
    e = engine([R(Field.NAME, Op.WILDCARD, "*.jpg")], [R(Field.FOLDER, Op.CONTAINS, "photos")])
    assert not e.matches(info())


def test_include_or_default():
    e = engine([R(Field.EXTENSION, Op.IN_LIST, "txt"), R(Field.EXTENSION, Op.IN_LIST, "jpg")])
    assert e.matches(info())


def test_include_and_mode():
    rules = [R(Field.EXTENSION, Op.IN_LIST, "jpg"), R(Field.SIZE, Op.GT, "5KB")]
    e = engine(rules, inc_op=GroupOp.AND)
    assert not e.matches(info(size=100)) and e.matches(info(size=9000))


def test_nested_groups_a_and_b_or_c():
    group = RuleGroup(GroupOp.AND, [R(Field.EXTENSION, Op.IN_LIST, "txt"), R(Field.SIZE, Op.LT, "1KB")])
    e = engine([group, R(Field.NAME, Op.WILDCARD, "*.jpg")])
    assert e.matches(info())                                           # C
    assert e.matches(info(path="/d/a.txt", size=10))                   # A and B
    assert not e.matches(info(path="/d/a.txt", size=5000))             # A only


def test_disabled_rule_and_group_ignored():
    e = engine([R(Field.EXTENSION, Op.IN_LIST, "txt", enabled=False)])
    assert e.matches(info())                       # only include rule is off -> include everything
    off = RuleGroup(GroupOp.OR, [R(Field.EXTENSION, Op.IN_LIST, "jpg")], enabled=False)
    assert engine(exclude=[off]).matches(info())


def test_empty_group_ignored():
    assert engine([RuleGroup(GroupOp.AND, [])]).matches(info())


# ---- validation ----
def test_invalid_regex():
    with pytest.raises(RuleError):
        compile_rule(R(Field.NAME, Op.REGEX, "(unclosed"))


def test_invalid_size_date_and_missing_values():
    for bad in (R(Field.SIZE, Op.GT, "lots"), R(Field.MODIFIED, Op.GT, "yesterday"),
                R(Field.NAME, Op.CONTAINS, "  "), R(Field.SIZE, Op.BETWEEN, "1KB"),
                R(Field.MODIFIED, Op.BETWEEN, "2024-01-01")):
        with pytest.raises(RuleError):
            compile_rule(bad)


def test_operator_not_allowed_for_field():
    with pytest.raises(RuleError):
        compile_rule(R(Field.SIZE, Op.REGEX, "x"))
    with pytest.raises(RuleError):
        compile_rule(R(Field.HIDDEN, Op.CONTAINS, "x"))


def test_validate_ruleset_collects_all_problems():
    rs = RuleSet()
    rs.add_include(R(Field.NAME, Op.REGEX, "("))
    rs.add_exclude(R(Field.SIZE, Op.GT, "nope"))
    assert len(validate_ruleset(rs)) == 2


# ---- serialization & summary ----
def test_ruleset_roundtrip():
    rs = RuleSet()
    grp = rs.add_include(RuleGroup(GroupOp.AND))
    grp.add(R(Field.EXTENSION, Op.IN_LIST, "txt"))
    grp.add(R(Field.MODIFIED, Op.BETWEEN, datetime(2024, 1, 1), "2024-06-30"))
    rs.add_exclude(R(Field.HIDDEN, Op.IS_TRUE, enabled=False))
    again = RuleSet.from_dict(rs.to_dict())
    assert again.to_dict() == rs.to_dict()


def test_summary_text():
    assert describe_ruleset(RuleSet()) == "Include all files."
    rs = RuleSet()
    grp = rs.add_include(RuleGroup(GroupOp.AND))
    grp.add(R(Field.EXTENSION, Op.IN_LIST, "jpg,png"))
    grp.add(R(Field.SIZE, Op.GT, "1MB"))
    rs.add_include(R(Field.NAME, Op.WILDCARD, "*.pdf"))
    rs.add_exclude(R(Field.FOLDER, Op.CONTAINS, "backup"))
    text = describe_ruleset(rs)
    assert text == ('Include files where (extension is jpg, png AND size > 1MB) OR name matches "*.pdf". '
                    'Exclude files where folder contains "backup". Exclude always wins.')
