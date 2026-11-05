"""Persistent user settings (JSON). Corrupt or missing files never crash the app."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .utils import app_data_dir

log = logging.getLogger("aff.settings")


@dataclass
class Settings:
    theme: str = "dark"                       # dark | light | system
    window_geometry: str = ""
    sources: list[str] = field(default_factory=list)
    destination: str = ""
    recursive: bool = True
    max_depth: int | None = None
    conflict_policy: str = "keep_both"
    content_max_mb: int = 50
    rules: dict | None = None                 # RuleSet.to_dict()
    recent_destinations: list[str] = field(default_factory=list)
    layout: dict | None = None                # OutputLayout.to_dict()
    preview_col_widths: dict | None = None    # column widths the user dragged in the preview


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def load_settings(path: Path | None = None) -> Settings:
    path = Path(path) if path else settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        known = {f.name for f in fields(Settings)}
        return Settings(**{k: v for k, v in data.items() if k in known})
    except FileNotFoundError:
        return Settings()
    except (OSError, ValueError, TypeError) as e:
        log.warning("Could not read settings (%s); using defaults", e)
        return Settings()


def save_settings(settings: Settings, path: Path | None = None) -> None:
    path = Path(path) if path else settings_path()
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
        os.replace(tmp, path)                 # atomic: never leaves a half-written file
    except OSError as e:
        log.warning("Could not save settings: %s", e)
