# Packaging Advanced File Finder as a Windows .exe

PyInstaller cannot cross-compile: **build on Windows** (the recipe was checked with a Linux build, so
the steps, bundled data and start-up are known to work; the Windows run is yours to confirm).

## 1. Build

Double-click **`build_exe.bat`** (or run it in a terminal).

| Command | Result |
|---|---|
| `build_exe.bat` | folder build: `dist\AdvancedFileFinder\AdvancedFileFinder.exe` + zip (**recommended**) |
| `build_exe.bat onefile` | one file: `dist\AdvancedFileFinder.exe` + zip |
| `build_exe.bat notests` | skip the test run (combine: `build_exe.bat onefile notests`) |

The script: creates `.venv` -> installs packages -> runs the tests (a failing test stops the build) ->
makes the icon and version info -> runs PyInstaller with `AdvancedFileFinder.spec` -> zips the result
as `dist\AdvancedFileFinder-<version>-win64.zip`.

**Folder vs one file**

| | Folder (default) | One file |
|---|---|---|
| Start-up | fast | 2-5 s (unpacks to a temp folder every start) |
| Antivirus false alarms | fewer | more (self-extracting files look suspicious) |
| Sharing | send the zip, unzip, run | send one .exe |
| Updating | replace the folder | replace the file |

Use the folder build for normal use and for the installer. Use one file only for quick sharing.

## 2. Files that matter

| File | Purpose |
|---|---|
| `run_app.py` | start script PyInstaller wraps |
| `AdvancedFileFinder.spec` | the recipe: what is bundled, windowed (no console), icon, version info, excludes |
| `assets/app.ico`, `app.png` | icon (regenerate with `python tools\make_icon.py`, or drop in your own .ico) |
| `tools/make_version_info.py` | writes the Windows "Details" tab from `aff.__version__` |
| `build_exe.bat` | one-click build |
| `installer/AdvancedFileFinder.iss` | optional real installer (Inno Setup) |

## 3. Release routine (each new version)

1. Change `__version__` in `aff/__init__.py` (and `AppVersion` in the `.iss` if you use the installer).
2. `build_exe.bat` (tests must pass).
3. Test the **zip** on a clean machine: Windows Sandbox is ideal (Windows Pro: turn on "Windows Sandbox",
   copy the zip in, unzip, run). Check: window opens, a search works, drag-and-drop, a copy works,
   settings are remembered after closing.
4. Keep the zip (name contains the version). Tag the source (`git tag v1.0.0`) if you use git.

## 4. Where the app keeps its data

`%APPDATA%\AdvancedFileFinder\` holds `settings.json` (folders, rules, window size, theme, column
widths) and `logs\` (`aff.log`, one `copy-<date>.log` per copy). Deleting an unzipped app does not
touch it. To reset the app, delete `settings.json`. Nothing is written next to the .exe.

## 5. Antivirus warnings and Windows SmartScreen

Unsigned PyInstaller programs are sometimes flagged. In order of effect:
1. Use the **folder** build (already the default; UPX compression is switched off in the spec).
2. **Sign** the exe with a code-signing certificate (removes most SmartScreen "unknown publisher" warnings):
   `signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a dist\AdvancedFileFinder\AdvancedFileFinder.exe`
   (sign the exe before zipping or building the installer; an installer is signed separately).
3. If one vendor flags it, submit the file as a false positive on that vendor's site
   (Microsoft: Security Intelligence > Submit a file).
4. Build from a clean venv on your own PC; do not download pre-built copies from anywhere else.

## 6. Installer (optional)

Install Inno Setup 6, run `build_exe.bat`, open `installer\AdvancedFileFinder.iss`, press Compile ->
`installer\Output\AdvancedFileFinder-Setup-<version>.exe` (Start-menu entry, optional desktop icon,
uninstaller, per-user install without admin rights).

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| "Failed to execute script" / nothing opens | In the spec set `console=False` to `console=True`, rebuild, run from a terminal to see the error |
| `ModuleNotFoundError` in the exe | add the module name to `hidden` in the spec and rebuild |
| Old code still in the exe | the script already passes `--clean`; delete the `build` and `dist` folders and rebuild |
| Drag-and-drop does nothing | the `tkinterdnd2` package must be installed in the `.venv` before building; Browse always works |
| Window icon missing | check `assets\app.ico` exists before building |
| Build says tests failed | fix the failing test, or `build_exe.bat notests` for a quick unverified build |
| Exe blocked after download | right-click the zip > Properties > Unblock, then unzip |
