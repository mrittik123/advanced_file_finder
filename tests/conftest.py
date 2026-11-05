import os
from datetime import datetime

import pytest

from aff.models import FileInfo


def write(path, text="", data=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if data is not None:
        path.write_bytes(data)
    else:
        path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _aff_home(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("AFF_HOME", str(tmp_path_factory.mktemp("aff_home")))


@pytest.fixture
def tree(tmp_path):
    """root/
         a.txt, b.jpg
         sub/c.txt, sub/d.PNG
         sub/deep/e.txt
         node_modules/f.js
    """
    root = tmp_path / "root"
    write(root / "a.txt", "alpha invoice")
    write(root / "b.jpg", "jpgdata")
    write(root / "sub" / "c.txt", "gamma")
    write(root / "sub" / "d.PNG", "pngdata")
    write(root / "sub" / "deep" / "e.txt", "epsilon invoice")
    write(root / "node_modules" / "f.js", "console.log(1)")
    return root


def info(path="/data/photos/Holiday.JPG", size=1000, modified=None, created=None, root="/data",
         hidden=False, readonly=False, system=False):
    ts = datetime(2024, 3, 15, 12, 0).timestamp()
    return FileInfo(path=path, root=root, size=size, created=created or ts,
                    modified=modified or ts, hidden=hidden, readonly=readonly, system=system)


def names(files):
    return sorted(os.path.basename(f.path) for f in files)
