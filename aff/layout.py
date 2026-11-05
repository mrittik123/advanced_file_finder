"""Where does each file go inside the destination folder? (structure / flat / custom pattern)"""
from __future__ import annotations

import os
import re
from datetime import datetime

from .models import FileInfo, LayoutMode, OutputLayout

CATEGORIES = {
    "Images": "jpg jpeg png gif bmp webp heic heif tif tiff svg ico raw cr2 nef arw dng",
    "Documents": "pdf doc docx xls xlsx ppt pptx txt rtf odt ods odp csv md epub",
    "Videos": "mp4 mkv avi mov wmv flv webm m4v mpg mpeg",
    "Audio": "mp3 wav flac aac m4a ogg wma opus",
    "Archives": "zip rar 7z tar gz bz2 xz iso",
    "Code": "py js ts java c cpp h cs go rs php rb html css json xml yml yaml sh bat ps1 sql",
    "Programs": "exe msi dll apk",
}
EXT_TO_CATEGORY = {ext: cat for cat, exts in CATEGORIES.items() for ext in exts.split()}

TOKEN_HELP = {
    "name": "file name with extension", "stem": "file name without extension",
    "ext": "extension in lower case (no_extension if none)",
    "category": "Images, Documents, Videos, Audio, Archives, Code, Programs or Other",
    "year": "4-digit year", "month": "2-digit month", "month_name": "month name",
    "day": "2-digit day", "date": "YYYY-MM-DD",
    "source": "name of the source folder that was searched",
    "parent": "name of the folder that held the file",
    "rel_dir": "folders between the source folder and the file",
}
PRESETS = {
    "By category": "{category}/{name}",
    "By extension": "{ext}/{name}",
    "By year and month": "{year}/{month}/{name}",
    "By date": "{date}/{name}",
    "By category and year": "{category}/{year}/{name}",
    "By source folder": "{source}/{name}",
    "Rename: date_name": "{date}_{name}",
}

_TOKEN_RE = re.compile(r"\{(\w+)\}")
_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def validate_pattern(pattern: str) -> list[str]:
    """Problems with a custom pattern (empty list = fine)."""
    pattern = (pattern or "").strip()
    if not pattern:
        return ["Type a pattern, for example {category}/{name}"]
    errors = []
    unknown = sorted({t for t in _TOKEN_RE.findall(pattern) if t not in TOKEN_HELP})
    if unknown:
        errors.append("Unknown placeholder: " + ", ".join("{%s}" % t for t in unknown))
    rest = _TOKEN_RE.sub("", pattern)
    if "{" in rest or "}" in rest:
        errors.append("Unbalanced { } in the pattern.")
    if pattern[0] in "/\\" or re.match(r"^[A-Za-z]:", pattern):
        errors.append("Use a relative pattern (no drive letter or leading slash): the destination folder "
                      "is added in front automatically.")
    if ".." in re.split(r"[\\/]+", pattern):
        errors.append("'..' is not allowed in the pattern.")
    return errors


def _clean(part: str) -> str:
    return _BAD_CHARS.sub("_", part).strip(" .")


def _values(info: FileInfo, label: str, layout: OutputLayout) -> dict[str, str]:
    ts = info.created if layout.date_field == "created" else info.modified
    try:
        dt = datetime.fromtimestamp(ts)
    except (OverflowError, OSError, ValueError):
        dt = datetime(1970, 1, 1)
    ext = info.ext.lower()
    rel_dir = os.path.dirname(info.rel_path).replace("\\", "/")
    return {
        "name": info.name, "stem": os.path.splitext(info.name)[0], "ext": _clean(ext) or "no_extension",
        "category": EXT_TO_CATEGORY.get(ext, "Other"),
        "year": f"{dt:%Y}", "month": f"{dt:%m}", "month_name": dt.strftime("%B"), "day": f"{dt:%d}",
        "date": f"{dt:%Y-%m-%d}", "source": _clean(label) or "source",
        "parent": _clean(os.path.basename(info.folder)) or "root",
        "rel_dir": "/".join(_clean(p) for p in rel_dir.split("/") if _clean(p)),
    }


def relative_dest(info: FileInfo, label: str, layout: OutputLayout) -> str:
    """Path of the file relative to the destination folder."""
    if layout.mode is LayoutMode.FLAT:
        return info.name
    if layout.mode is LayoutMode.CUSTOM:
        pattern = layout.pattern.strip()
        if "{name}" not in pattern and "{stem}" not in pattern:
            pattern = pattern.rstrip("/\\") + "/{name}"        # folder-only pattern: keep the file name
        values = _values(info, label, layout)
        expanded = _TOKEN_RE.sub(lambda m: values.get(m.group(1), ""), pattern)
        parts = [_clean(p) for p in re.split(r"[\\/]+", expanded)]
        parts = [p for p in parts if p]
        if not parts:
            return info.name
        return os.path.join(*parts)
    rel = info.rel_path
    return os.path.join(label, rel) if layout.include_source_name else rel
