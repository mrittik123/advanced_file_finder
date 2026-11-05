"""Folder scanner: walks source folders with depth control and yields FileInfo objects."""
from __future__ import annotations

import os
import stat
import threading
from typing import Iterator

from .models import FileInfo, SearchConfig, SearchStats
from .utils import fs_path

_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def is_within(child: str, parent: str) -> bool:
    """True if child is the same as, or inside, parent (case-insensitive on Windows)."""
    try:
        c = os.path.normcase(os.path.realpath(child))
        p = os.path.normcase(os.path.realpath(parent))
        return os.path.commonpath([c, p]) == p
    except ValueError:      # different drives
        return False


def _attributes(name: str, st: os.stat_result) -> tuple[bool, bool, bool]:
    """(hidden, readonly, system)"""
    fa = getattr(st, "st_file_attributes", None)
    if fa is not None:      # Windows
        return (bool(fa & stat.FILE_ATTRIBUTE_HIDDEN), bool(fa & stat.FILE_ATTRIBUTE_READONLY),
                bool(fa & stat.FILE_ATTRIBUTE_SYSTEM))
    return name.startswith("."), not (st.st_mode & stat.S_IWUSR), False


class Scanner:
    """Usage: for info in Scanner(config, cancel_event, stats).scan(): ...

    Errors on a single folder or file are recorded in stats and skipped, never raised.
    """

    def __init__(self, config: SearchConfig, cancel: threading.Event | None = None,
                 stats: SearchStats | None = None):
        self.config = config
        self.cancel = cancel or threading.Event()
        self.stats = stats if stats is not None else SearchStats()

    def _normalized_sources(self) -> list[str]:
        out, seen = [], set()
        for s in self.config.sources:
            if not s or not s.strip():
                continue
            p = os.path.abspath(s)
            key = os.path.normcase(p)
            if key not in seen:
                seen.add(key)
                out.append(p)
        return out

    @staticmethod
    def _overlapping(sources: list[str]) -> bool:
        return any(i != j and is_within(a, b)
                   for i, a in enumerate(sources) for j, b in enumerate(sources))

    def scan(self) -> Iterator[FileInfo]:
        sources = self._normalized_sources()
        # Only pay for de-duplication when one source sits inside another.
        seen_files: set[str] | None = set() if self._overlapping(sources) else None
        for root in sources:
            if self.cancel.is_set():
                self.stats.cancelled = True
                return
            if not os.path.isdir(fs_path(root)):
                self.stats.add_error(root, "source folder not found or not a folder")
                continue
            yield from self._scan_root(root, seen_files)

    def _scan_root(self, root: str, seen_files: set[str] | None) -> Iterator[FileInfo]:
        max_depth = self.config.effective_max_depth
        follow = self.config.follow_symlinks
        visited_dirs: set[str] = set()
        stack: list[tuple[str, int]] = [(root, 0)]
        while stack:
            if self.cancel.is_set():
                self.stats.cancelled = True
                return
            folder, depth = stack.pop()
            if follow:
                real = os.path.normcase(os.path.realpath(folder))
                if real in visited_dirs:
                    continue
                visited_dirs.add(real)
            try:
                it = os.scandir(fs_path(folder))
            except OSError as e:
                self.stats.add_error(folder, str(e))
                continue
            self.stats.dirs_scanned += 1
            subdirs: list[str] = []
            with it:
                while True:
                    if self.cancel.is_set():
                        self.stats.cancelled = True
                        return
                    try:
                        entry = next(it)
                    except StopIteration:
                        break
                    except OSError as e:
                        self.stats.add_error(folder, str(e))
                        break
                    path = os.path.join(folder, entry.name)
                    try:
                        if entry.is_dir(follow_symlinks=follow):
                            if not follow and self._is_reparse(entry):
                                continue            # skip junctions / symlinked folders
                            if max_depth is None or depth < max_depth:
                                subdirs.append(path)
                            continue
                        if not entry.is_file():
                            continue
                        st = entry.stat()
                    except OSError as e:
                        self.stats.add_error(path, str(e))
                        continue
                    if seen_files is not None:
                        key = os.path.normcase(path)
                        if key in seen_files:
                            continue
                        seen_files.add(key)
                    self.stats.files_scanned += 1
                    hidden, readonly, system = _attributes(entry.name, st)
                    yield FileInfo(
                        path=path, root=root, size=st.st_size,
                        created=getattr(st, "st_birthtime", st.st_ctime), modified=st.st_mtime,
                        hidden=hidden, readonly=readonly, system=system,
                    )
            # Push in reverse so folders are visited in alphabetical order.
            stack.extend((d, depth + 1) for d in sorted(subdirs, reverse=True))

    @staticmethod
    def _is_reparse(entry: os.DirEntry) -> bool:
        try:
            if entry.is_symlink():
                return True
            fa = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
            return bool(fa & _REPARSE)
        except OSError:
            return False
