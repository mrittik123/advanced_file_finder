"""Writes build/version_info.txt (the Windows 'Details' tab of the .exe) from aff.__version__."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from aff import __version__  # noqa: E402

nums = [int(n) for n in re.findall(r"\d+", __version__)[:3]] + [0, 0, 0]
tup = tuple(nums[:3]) + (0,)
text = ".".join(map(str, tup))

TEMPLATE = """# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(filevers={tup}, prodvers={tup}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', ''),
      StringStruct('FileDescription', 'Advanced File Finder'),
      StringStruct('FileVersion', '{text}'),
      StringStruct('InternalName', 'AdvancedFileFinder'),
      StringStruct('LegalCopyright', ''),
      StringStruct('OriginalFilename', 'AdvancedFileFinder.exe'),
      StringStruct('ProductName', 'Advanced File Finder'),
      StringStruct('ProductVersion', '{text}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
out = ROOT / "build"
out.mkdir(exist_ok=True)
(out / "version_info.txt").write_text(TEMPLATE.format(tup=tup, text=text), encoding="utf-8")
print("version", __version__, "->", text)
