"""Small helpers: app folders, long-path support, size and date parsing."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

APP_NAME = "AdvancedFileFinder"
IS_WINDOWS = os.name == "nt"


def app_data_dir() -> Path:
    """Per-user folder for settings and logs. Override with AFF_HOME (used by tests)."""
    override = os.environ.get("AFF_HOME")
    if override:
        base = Path(override)
    elif IS_WINDOWS:
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_NAME
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def fs_path(path: str) -> str:
    """Path to hand to OS calls. On Windows, long paths get the \\\\?\\ prefix."""
    if not IS_WINDOWS or len(path) < 240 or path.startswith("\\\\?\\"):
        return path
    path = os.path.abspath(path)
    if path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + path[2:]
    return "\\\\?\\" + path


_SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?|\.\d+)\s*([a-zA-Z]*)\s*$")
_UNITS = {
    "": 1, "b": 1,
    "k": 1024, "kb": 1024, "kib": 1024,
    "m": 1024**2, "mb": 1024**2, "mib": 1024**2,
    "g": 1024**3, "gb": 1024**3, "gib": 1024**3,
    "t": 1024**4, "tb": 1024**4, "tib": 1024**4,
}


def parse_size(value: Any) -> int:
    """'10MB', '1.5 GB', 2048 -> bytes (1 KB = 1024 bytes, as Windows Explorer shows)."""
    if isinstance(value, bool):
        raise ValueError("invalid size")
    if isinstance(value, (int, float)):
        return int(value)
    m = _SIZE_RE.match(str(value))
    if not m or m.group(2).lower() not in _UNITS:
        raise ValueError(f"invalid size: {value!r} (examples: 500, 10KB, 1.5MB, 2GB)")
    return int(float(m.group(1)) * _UNITS[m.group(2).lower()])


def format_size(n: float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{int(n)} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def parse_when(value: Any) -> tuple[datetime, bool]:
    """Parse a date or datetime. Returns (datetime, date_only)."""
    if isinstance(value, datetime):
        return value, False
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day), True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value), False
    text = str(value).strip()
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(f"invalid date: {value!r} (use YYYY-MM-DD or YYYY-MM-DD HH:MM)") from None
    return dt, len(text) <= 10


def day_end(dt: datetime) -> datetime:
    return dt + timedelta(days=1)


def open_path(path: str) -> None:
    """Open a file or folder with the default application."""
    if IS_WINDOWS:
        os.startfile(path)                      # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def reveal_in_folder(path: str) -> None:
    """Open the folder that contains a file (selecting the file in Explorer on Windows)."""
    if IS_WINDOWS and os.path.isfile(path):
        subprocess.Popen(["explorer", f"/select,{os.path.normpath(path)}"])
    elif sys.platform == "darwin" and os.path.isfile(path):
        subprocess.Popen(["open", "-R", path])
    else:
        open_path(os.path.dirname(path) if os.path.isfile(path) else path)


def resource_path(relative: str) -> str:
    """Path of a bundled data file, both when running from source and inside the PyInstaller .exe."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)
