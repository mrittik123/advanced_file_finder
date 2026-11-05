"""Copier: runs a CopyPlan. Never moves or deletes source files.

Each file is copied to a temporary '.aff-partial' name and renamed when complete, so an
interrupted copy never leaves a half-written file under its real name. A failure on one file
is logged and skipped; it never stops the whole run.
"""
from __future__ import annotations

import hashlib
import os
import stat
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from .models import ConflictPolicy, CopyPlan, PlanItem, PlanStatus
from .planner import unique_path
from .utils import app_data_dir, fs_path

CHUNK = 1024 * 1024
PARTIAL_SUFFIX = ".aff-partial"


class _Cancelled(Exception):
    pass


@dataclass
class CopyProgress:
    """Live numbers; the UI polls this from its own thread."""
    total_files: int = 0
    total_bytes: int = 0
    files_done: int = 0
    bytes_done: int = 0
    copied: int = 0
    skipped: int = 0
    failed: int = 0
    current: str = ""

    @property
    def fraction(self) -> float:
        if self.total_bytes:
            return min(1.0, self.bytes_done / self.total_bytes)
        return min(1.0, self.files_done / self.total_files) if self.total_files else 1.0


@dataclass
class CopyReport:
    copied: int = 0
    skipped: int = 0
    failed: int = 0
    bytes_copied: int = 0
    cancelled: bool = False
    started: datetime = field(default_factory=datetime.now)
    finished: datetime | None = None
    log_path: Path | None = None
    failures: list[tuple[str, str]] = field(default_factory=list)

    def summary(self) -> str:
        state = "Cancelled" if self.cancelled else "Finished"
        return f"{state}: {self.copied} copied, {self.skipped} skipped, {self.failed} failed."


class Copier:
    def __init__(self, plan: CopyPlan, cancel: threading.Event | None = None, verify: bool = False,
                 log_dir: Path | None = None, on_progress: Callable[[CopyProgress], None] | None = None):
        self.plan = plan
        self.cancel = cancel or threading.Event()
        self.verify = verify
        self.log_dir = Path(log_dir) if log_dir else app_data_dir() / "logs"
        self.on_progress = on_progress
        self.progress = CopyProgress()
        self.report = CopyReport()

    # ------------------------------------------------------------------ public
    def run(self) -> CopyReport:
        items = self.plan.selected_items
        p, rep = self.progress, self.report
        p.total_files = len(items)
        p.total_bytes = sum(i.source.size for i in items)
        log = self._open_log()
        try:
            self._log(log, f"Copy started: {len(items)} files to {self.plan.destination} "
                           f"(policy: {self.plan.policy.value}, verify: {self.verify})")
            for item in items:
                if self.cancel.is_set():
                    rep.cancelled = True
                    break
                p.current = item.source.path
                base = p.bytes_done
                try:
                    outcome, detail = self._copy_item(item)
                except _Cancelled:
                    rep.cancelled = True
                    break
                except Exception as e:          # one bad file must never stop the run
                    outcome, detail = "failed", f"{type(e).__name__}: {e}"
                p.bytes_done = base + item.source.size
                p.files_done += 1
                if outcome == "copied":
                    p.copied += 1
                    rep.bytes_copied += item.source.size
                    self._log(log, f"COPIED  {item.source.path} -> {detail}")
                elif outcome == "skipped":
                    p.skipped += 1
                    self._log(log, f"SKIPPED {item.source.path} ({detail})")
                else:
                    p.failed += 1
                    rep.failures.append((item.source.path, detail))
                    self._log(log, f"FAILED  {item.source.path}: {detail}")
                if self.on_progress:
                    self.on_progress(p)
            rep.copied, rep.skipped, rep.failed = p.copied, p.skipped, p.failed
            rep.finished = datetime.now()
            self._log(log, rep.summary())
        finally:
            if log:
                log.close()
            if self.on_progress:
                self.on_progress(p)
        return rep

    # ----------------------------------------------------------------- helpers
    def _open_log(self):
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            path = self.log_dir / f"copy-{datetime.now():%Y%m%d-%H%M%S}.log"
            self.report.log_path = path
            return open(path, "w", encoding="utf-8", buffering=1)
        except OSError:
            self.report.log_path = None
            return None

    @staticmethod
    def _log(handle, message: str) -> None:
        if handle:
            try:
                handle.write(f"{datetime.now():%H:%M:%S} {message}\n")
            except OSError:
                pass

    def _resolve_dest(self, item: PlanItem) -> tuple[str | None, str]:
        """Re-check the destination right before copying (it may have changed since the preview)."""
        dest = item.dest
        if item.status is PlanStatus.WOULD_OVERWRITE or not os.path.lexists(fs_path(dest)):
            return dest, ""
        policy = self.plan.policy
        if policy is ConflictPolicy.KEEP_BOTH:
            return unique_path(dest, set()), ""
        if policy is ConflictPolicy.OVERWRITE:
            return dest, ""
        if policy is ConflictPolicy.OVERWRITE_IF_NEWER:
            try:
                if item.source.modified > os.stat(fs_path(dest)).st_mtime:
                    return dest, ""
            except OSError:
                return dest, ""
        return None, "destination file appeared since the preview"

    def _copy_item(self, item: PlanItem) -> tuple[str, str]:
        if item.status is PlanStatus.ERROR:
            return "skipped", item.note or "planned as error"
        dest, reason = self._resolve_dest(item)
        if dest is None:
            return "skipped", reason
        target, tmp = fs_path(dest), fs_path(dest + PARTIAL_SUFFIX)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        try:
            digest = self._copy_data(fs_path(item.source.path), tmp)
            if self.verify and digest is not None and self._hash(tmp) != digest:
                raise OSError("checksum mismatch after copy")
            try:
                shutil.copystat(fs_path(item.source.path), tmp)       # keep dates
            except OSError:
                pass
            self._replace(tmp, target)
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
        return "copied", dest

    def _copy_data(self, src: str, tmp: str) -> str | None:
        hasher = hashlib.sha256() if self.verify else None
        with open(src, "rb") as fin, open(tmp, "wb") as fout:
            while True:
                if self.cancel.is_set():
                    raise _Cancelled()
                chunk = fin.read(CHUNK)
                if not chunk:
                    break
                fout.write(chunk)
                if hasher:
                    hasher.update(chunk)
                self.progress.bytes_done += len(chunk)
        return hasher.hexdigest() if hasher else None

    @staticmethod
    def _hash(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(CHUNK), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _replace(tmp: str, target: str) -> None:
        try:
            os.replace(tmp, target)
        except PermissionError:                  # read-only file at the destination
            os.chmod(target, stat.S_IWRITE | stat.S_IREAD)
            os.replace(tmp, target)
