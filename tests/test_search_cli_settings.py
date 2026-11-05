import json

import pytest

from aff.cli import main, parse_rule_spec
from aff.models import Field, Op, Rule, RuleSet, SearchConfig
from aff.search import run_search
from aff.settings import Settings, load_settings, save_settings
from conftest import names


def test_run_search_include_exclude_depth(tree):
    rs = RuleSet()
    rs.add_include(Rule(Field.EXTENSION, Op.IN_LIST, "txt"))
    rs.add_exclude(Rule(Field.FOLDER, Op.CONTAINS, "deep"))
    assert names(run_search(SearchConfig(sources=[str(tree)], rules=rs))) == ["a.txt", "c.txt"]
    assert names(run_search(SearchConfig(sources=[str(tree)], rules=rs, recursive=False))) == ["a.txt"]


def test_parse_rule_spec():
    inc, r = parse_rule_spec("+name:wildcard:*.jpg")
    assert inc and (r.field, r.op, r.value) == (Field.NAME, Op.WILDCARD, "*.jpg")
    inc, r = parse_rule_spec("-size:between:1MB..2MB")
    assert not inc and (r.value, r.value2) == ("1MB", "2MB")
    inc, r = parse_rule_spec(r"+path:contains:C:\data")          # colons in the value are fine
    assert r.value == r"C:\data"
    for bad in ("name:wildcard:x", "+name:wildcard", "+bogus:contains:x", "+size:between:5"):
        with pytest.raises(ValueError):
            parse_rule_spec(bad)


def test_cli_end_to_end(tree, tmp_path, capsys):
    out = tmp_path / "out"
    code = main(["-s", str(tree), "-d", str(out), "-i", "extension:in_list:txt", "-x", "folder:contains:deep"])
    text = capsys.readouterr().out
    assert code == 0
    assert "2 match" in text and "to copy 2 files" in text
    assert not out.exists()                                 # dry run only: nothing is written


def test_cli_rejects_destination_inside_source(tree, capsys):
    assert main(["-s", str(tree), "-d", str(tree / "out")]) == 1


def test_cli_reports_bad_rule(tree, capsys):
    assert main(["-s", str(tree), "-i", "name:regex:("]) == 2


def test_cli_rules_file(tree, tmp_path, capsys):
    rules = {"include": {"type": "group", "operator": "or", "children": [
        {"type": "group", "operator": "and", "children": [
            {"type": "rule", "field": "extension", "op": "in_list", "value": "txt"},
            {"type": "rule", "field": "content", "op": "contains", "value": "invoice"}]},
        {"type": "rule", "field": "name", "op": "wildcard", "value": "*.jpg"}]}}
    f = tmp_path / "rules.json"
    f.write_text(json.dumps(rules))
    assert main(["-s", str(tree), "--rules-file", str(f)]) == 0
    text = capsys.readouterr().out
    assert "3 match" in text and "(extension is txt AND content contains" in text


def test_settings_roundtrip_and_corruption(tmp_path):
    p = tmp_path / "s.json"
    assert load_settings(p) == Settings()
    save_settings(Settings(theme="light", sources=["C:\\a"]), p)
    assert load_settings(p).theme == "light"
    p.write_text("{ not json")
    assert load_settings(p) == Settings()
    p.write_text(json.dumps({"theme": "light", "unknown_future_key": 1}))
    assert load_settings(p).theme == "light"


def test_cli_signed_rule_form(tree, capsys):
    assert main(["-s", str(tree), "--rule=+extension:in_list:txt", "--rule=-folder:contains:deep"]) == 0
    assert "2 match" in capsys.readouterr().out


def test_cli_layouts(tree, tmp_path, capsys):
    out = tmp_path / "out"
    assert main(["-s", str(tree), "-d", str(out), "--layout", "flat", "--limit", "0"]) == 0
    text = capsys.readouterr().out
    assert "->  " + str(out / "a.txt") in text and str(out / "root") not in text
    assert main(["-s", str(tree), "-d", str(out), "--layout", "custom", "--pattern", "{category}/{name}",
                 "--limit", "0"]) == 0
    assert "Images" in capsys.readouterr().out
    assert main(["-s", str(tree), "-d", str(out), "--layout", "custom", "--pattern", "{bogus}/{name}"]) == 2
