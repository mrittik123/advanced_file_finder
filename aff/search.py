"""High-level search: scanner + rule engine."""
from __future__ import annotations

import threading
from typing import Callable, Iterator

from .models import FileInfo, SearchConfig, SearchStats
from .rules import RuleEngine
from .scanner import Scanner

ProgressFn = Callable[[SearchStats], None]


def iter_search(config: SearchConfig, cancel: threading.Event | None = None,
                stats: SearchStats | None = None, progress: ProgressFn | None = None,
                progress_every: int = 500) -> Iterator[FileInfo]:
    """Yield matching files one at a time (good for streaming into a UI)."""
    stats = stats if stats is not None else SearchStats()
    engine = RuleEngine(config.rules, config.content_max_bytes, stats)
    for info in Scanner(config, cancel, stats).scan():
        if engine.matches(info):
            stats.files_matched += 1
            yield info
        if progress and stats.files_scanned % progress_every == 0:
            progress(stats)
    if progress:
        progress(stats)


def run_search(config: SearchConfig, cancel: threading.Event | None = None,
               stats: SearchStats | None = None, progress: ProgressFn | None = None) -> list[FileInfo]:
    return list(iter_search(config, cancel, stats, progress))
