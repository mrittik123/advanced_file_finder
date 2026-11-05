# Advanced File Finder

Search folders with include/exclude rules, preview the results, then copy the files while
keeping the folder structure. Python 3.10+, Windows target (the engine also runs on Linux/macOS).

## Build status (V1 plan)

| Stage | Status |
|---|---|
| 1. Foundation (structure, models, logging, settings, tests) | done |
| 2. Engine (scanner, depth, rules, AND/OR groups, planner) | done, tested |
| 3. Content search (size cap, binary skip, encodings) | done, tested |
| 4. Main window (sources, depth, rules, threaded search with Stop) | done |
| 5. Preview window (virtualized table, checkboxes, filter, sort, right-click) | done |
| 6. Copy (conflict policies, progress, cancel, report, log, optional checksum) | done |
| 7. UX layer: themes, remembered folders/rules/window size, undo, quick-add chips, shortcuts | done; presets and search history still to do |
| 8. Hardening (500k-file timing, UNC/USB testing) | next |
| 9. Packaging (.exe build script, icon, version info, installer template, guide) | done, see PACKAGING.md |

## Quick start (Windows)

Double-click `setup_and_run.bat`. It creates `.venv`, installs the packages, runs the tests and then
starts the window app (`python -m aff.app`).

## Manual setup

    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements-dev.txt
    python -m pytest

## The window

The app is a 4-step wizard with Back / Next: **1 Sources & destination -> 2 Rules -> 3 Preview ->
4 Copy**. It adapts to the window width (the step bar becomes "Step 2 of 4" and panels stack).
Shortcuts: Ctrl+Right = Next, Ctrl+Left = Back, Ctrl+Z = undo a rule edit (step 2).
Drag-and-drop of folders needs `tkinterdnd2` (in requirements.txt); Browse always works.

The preview table: drag a header border to resize a column (double-click the border to fit it to its
content, right-click the header to reset), right-click a cell to copy it (or copy the path, folder, size,
whole row), Ctrl+C copies the selected cell. Step 4 lets you choose how files are arranged at the
destination: keep the folder structure, put all files together, or a custom pattern such as
`{category}/{year}/{month}/{name}`.

## Build the .exe

Run `build_exe.bat` (details in PACKAGING.md).

## Command line (no window)

    python -m aff -s C:\Photos -d D:\Backup -i extension:in_list:jpg,png -x folder:contains:thumbs
    python -m aff -s . -i size:between:1MB..10MB -i content:contains:invoice --include-mode and
    python -m aff -s . -d .\out --rules-file examples\rules_example.json --policy skip

It prints a plain-language summary of your rules, the matching files, and the copy plan
(destination, status, free-space check). It never copies anything.

Rule format: `field:operator:value`. Use `-i` for include and `-x` for exclude (repeatable).

| Field | Operators |
|---|---|
| name, path, folder | wildcard, regex, contains, equals, starts_with, ends_with |
| extension | in_list, wildcard, regex |
| size | gt, gte, lt, lte, equals, between (`1MB..10MB`) |
| created, modified | gt, gte, lt, lte, equals, between (`2024-01-01..2024-06-30`) |
| hidden, readonly, system | is_true, is_false |
| content | contains, regex |

Nested AND/OR groups come from a JSON file (`--rules-file`, see `examples/rules_example.json`).

## Behaviour decisions

- Include and exclude groups default to OR; `--include-mode and` switches it. Exclude always wins.
  No include rules means every file is included.
- Regex and wildcard on `name` match the file name only; use `path` or `folder` for paths.
- Date-only values mean whole days: "modified after 2024-03-15" starts on 16 March.
- Content search reads line by line (a pattern cannot span lines), skips binary files and files
  over the size cap (default 50 MB), and handles UTF-8/16/32 BOMs and legacy cp1252 text.
- Destination layout: `<destination>\<source folder name>\<path inside source>`. Two sources
  with the same folder name become `photos` and `photos_2`.
- Default conflict policy is keep both (`name (1).ext`).
