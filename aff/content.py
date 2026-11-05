"""Text search inside files: size cap, binary detection, encoding handling."""
from __future__ import annotations

import codecs
import io
import re
from enum import Enum
from typing import Callable

from .models import Op
from .utils import fs_path

SAMPLE_SIZE = 8192

# UTF-32 BOMs must be tested before UTF-16 (the UTF-32 LE BOM starts with the UTF-16 LE BOM).
_BOMS = [
    (codecs.BOM_UTF32_LE, "utf-32"), (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"), (codecs.BOM_UTF16_BE, "utf-16"),
]


class ContentResult(Enum):
    MATCH = "match"
    NO_MATCH = "no match"
    BINARY = "binary"
    TOO_LARGE = "too large"
    ERROR = "error"


def detect_encoding(sample: bytes) -> str | None:
    """Pick an encoding for a text file from its first bytes. None means 'binary'."""
    for bom, enc in _BOMS:
        if sample.startswith(bom):
            return enc
    if not sample:
        return "utf-8"
    if b"\x00" in sample:
        return None
    control = sum(1 for b in sample if b < 9 or (13 < b < 32 and b != 27))
    if control / len(sample) > 0.10:
        return None
    try:
        codecs.getincrementaldecoder("utf-8")().decode(sample, final=False)
        return "utf-8"
    except UnicodeDecodeError:
        return "cp1252"          # typical legacy Windows text; undefined bytes are replaced


def make_line_matcher(op: Op, value: str, case_sensitive: bool) -> Callable[[str], bool]:
    """Build a function that tests one line of text. Raises ValueError for a bad pattern."""
    if not value:
        raise ValueError("a search text is required")
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        rx = re.compile(re.escape(value) if op is Op.CONTAINS else value, flags)
    except re.error as e:
        raise ValueError(f"invalid regular expression: {e}") from None
    return lambda line: rx.search(line) is not None


def file_contains(path: str, line_matcher: Callable[[str], bool], *,
                  max_bytes: int, size: int | None = None) -> ContentResult:
    """Stream a file line by line and report whether any line matches.

    Files over max_bytes and binary files are skipped (reported, never an exception).
    """
    try:
        target = fs_path(path)
        if size is None:
            import os
            size = os.path.getsize(target)
        if size > max_bytes:
            return ContentResult.TOO_LARGE
        if size == 0:
            return ContentResult.NO_MATCH
        with open(target, "rb") as raw:
            encoding = detect_encoding(raw.read(SAMPLE_SIZE))
            if encoding is None:
                return ContentResult.BINARY
            raw.seek(0)
            text = io.TextIOWrapper(raw, encoding=encoding, errors="replace")
            for line in text:
                if line_matcher(line):
                    return ContentResult.MATCH
        return ContentResult.NO_MATCH
    except OSError:
        return ContentResult.ERROR
