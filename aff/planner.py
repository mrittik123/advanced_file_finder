"""Builds the copy plan (destination paths and statuses) and runs the safety checks."""
from __future__ import annotations

import os
import re
import shutil
import threading
from dataclasses import dataclass
from typing import Iterable

from .layout import relative_dest
from .models import (ConflictPolicy, CopyPlan, FileInfo, OutputLayout, PlanItem, PlanStatus)
from .scanner import is_within
from .utils import format_size, fs_path


def validate_destination(sources: Iterable[str], destination: str) -> list[str]:
    """Safety checks that must pass before a plan is built. Returns error messages."""
    errors: list[str] = []
    if not destination or not destination.strip():
        return ["Choose a destination folder."]
    dest = os.path.abspath(destination)
    if os.path.exists(fs_path(dest)) and not os.path.isdir(fs_path(dest)):
        errors.append(f"Destination is a file, not a folder: {dest}")
    for src in sources:
        if src and is_within(dest, os.path.abspath(src)):
            errors.append(f"Destination is inside the source folder '{src}'. "
                          "Copying there would copy files into the folder being searched.")
    return errors


@dataclass
class FreeSpaceCheck:
    ok: bool
    required: int
    available: int
    path: str

    def message(self) -> str:
        return (f"Needs {format_size(self.required)}, {format_size(self.available)} free on {self.path}"
                + ("" if self.ok else " - not enough space."))


def check_free_space(plan: CopyPlan) -> FreeSpaceCheck:
    """Conservative check: counts every file that will be written (overwrites included)."""
    required = sum(i.source.size for i in plan.items
                   if i.selected and i.status in (PlanStatus.NEW, PlanStatus.WOULD_OVERWRITE))
    probe = os.path.abspath(plan.destination)
    while probe and not os.path.exists(fs_path(probe)):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    available = shutil.disk_usage(probe).free
    return FreeSpaceCheck(available >= required, required, available, probe)


def _root_label(root: str) -> str:
    """Top-level folder name used inside the destination for a source folder."""
    root = os.path.normpath(root)
    name = os.path.basename(root)
    if not name:                                  # drive root such as C:\
        drive = os.path.splitdrive(root)[0]
        name = re.sub(r"[^\w.-]+", "", drive) or "root"
    return name


def root_labels(sources: Iterable[str]) -> dict[str, str]:
    """Unique destination folder name per source (photos, photos_2, ...)."""
    labels: dict[str, str] = {}
    used: set[str] = set()
    for src in sources:
        root = os.path.abspath(src)
        if root in labels:
            continue
        base = _root_label(root)
        label, n = base, 1
        while label.casefold() in used:
            n += 1
            label = f"{base}_{n}"
        used.add(label.casefold())
        labels[root] = label
    return labels


def unique_path(path: str, taken: set[str]) -> str:
    """name.ext -> name (1).ext, name (2).ext ... first one not on disk or already planned."""
    stem, ext = os.path.splitext(path)
    n = 1
    candidate = path
    while os.path.lexists(fs_path(candidate)) or os.path.normcase(candidate) in taken:
        candidate = f"{stem} ({n}){ext}"
        n += 1
    return candidate


def build_plan(files: Iterable[FileInfo], destination: str, sources: Iterable[str],
               policy: ConflictPolicy = ConflictPolicy.KEEP_BOTH,
               cancel: threading.Event | None = None,
               layout: OutputLayout | None = None) -> CopyPlan:
    """Map every found file to its destination path.

    Default layout keeps the structure: <destination>/<source folder name>/<path inside the source>.
    See aff.layout for the flat and custom-pattern layouts.
    """
    layout = layout or OutputLayout()
    destination = os.path.abspath(destination)
    labels = root_labels(sources)
    plan = CopyPlan(destination=destination, policy=policy)
    taken: set[str] = set()
    for info in files:
        if cancel is not None and cancel.is_set():
            break
        label = labels.get(os.path.abspath(info.root)) or _root_label(info.root)
        dest = os.path.join(destination, relative_dest(info, label, layout))
        item = PlanItem(source=info, dest=dest, status=PlanStatus.NEW)
        key = os.path.normcase(dest)

        if os.path.normcase(os.path.abspath(info.path)) == key:
            item.status, item.selected = PlanStatus.ERROR, False
            item.note = "source and destination are the same file"
        elif key in taken:
            # two files of this copy want the same name (typical for flat / pattern layouts):
            # never let one silently replace the other, whatever the conflict policy is
            item.dest = unique_path(dest, taken)
            item.note = "same name as another file in this copy - copied with a new name"
        elif os.path.isdir(fs_path(dest)):
            item.status, item.selected = PlanStatus.ERROR, False
            item.note = "a folder with this name exists at the destination"
        elif os.path.lexists(fs_path(dest)):
            if policy is ConflictPolicy.KEEP_BOTH:
                item.dest = unique_path(dest, taken)
                item.note = "exists - copied with a new name"
            elif policy is ConflictPolicy.OVERWRITE:
                item.status = PlanStatus.WOULD_OVERWRITE
            elif policy is ConflictPolicy.OVERWRITE_IF_NEWER:
                try:
                    newer = info.modified > os.stat(fs_path(dest)).st_mtime
                except OSError:
                    newer = True
                if newer:
                    item.status = PlanStatus.WOULD_OVERWRITE
                else:
                    item.status, item.selected = PlanStatus.EXISTS, False
                    item.note = "destination is newer or same age"
            else:                                           # SKIP
                item.status, item.selected = PlanStatus.EXISTS, False
                item.note = "exists - will be skipped"
        taken.add(os.path.normcase(item.dest))
        plan.items.append(item)
    return plan


def carry_selection(old: CopyPlan, new: CopyPlan) -> None:
    """After re-planning (e.g. a new output layout), keep the files the user had un-ticked."""
    unticked = {i.source.path for i in old.items
                if not i.selected and i.status not in (PlanStatus.ERROR, PlanStatus.EXISTS)}
    for item in new.items:
        if item.source.path in unticked and item.status is not PlanStatus.ERROR:
            item.selected = False
