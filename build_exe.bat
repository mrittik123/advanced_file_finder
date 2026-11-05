@echo off
setlocal
cd /d "%~dp0"
title Advanced File Finder - build .exe

rem Usage:  build_exe.bat            -> folder build   dist\AdvancedFileFinder\AdvancedFileFinder.exe (recommended)
rem         build_exe.bat onefile    -> single file    dist\AdvancedFileFinder.exe (slower start-up)
rem         build_exe.bat notests    -> skip the test run (can be combined: build_exe.bat onefile notests)

set "ONEFILE=0"
set "RUNTESTS=1"
:args
if "%~1"=="" goto :argsdone
if /i "%~1"=="onefile" set "ONEFILE=1"
if /i "%~1"=="notests" set "RUNTESTS=0"
shift
goto :args
:argsdone

rem ---- Python 3.10+ ----
set "PY="
where py >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    where python >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY goto :nopython
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 goto :nopython

rem ---- venv + packages ----
if not exist ".venv\Scripts\python.exe" (
    echo [1/5] Creating virtual environment...
    %PY% -m venv .venv
    if errorlevel 1 goto :fail
)
set "VPY=%~dp0.venv\Scripts\python.exe"
echo [2/5] Installing packages...
"%VPY%" -m pip install --upgrade pip >nul 2>&1
"%VPY%" -m pip install -r requirements-dev.txt pillow
if errorlevel 1 goto :fail

rem ---- tests ----
if "%RUNTESTS%"=="1" (
    echo [3/5] Running tests...
    "%VPY%" -m pytest -q
    if errorlevel 1 (
        echo Tests failed - the .exe was NOT built. Fix the tests or run: build_exe.bat notests
        goto :fail
    )
) else (
    echo [3/5] Tests skipped.
)

rem ---- icon + version resource ----
echo [4/5] Preparing icon and version info...
if not exist "assets\app.ico" "%VPY%" tools\make_icon.py
"%VPY%" tools\make_version_info.py
if errorlevel 1 goto :fail

rem ---- PyInstaller ----
echo [5/5] Building (this takes a minute or two)...
set "AFF_ONEFILE=%ONEFILE%"
"%VPY%" -m PyInstaller AdvancedFileFinder.spec --noconfirm --clean
if errorlevel 1 goto :fail

rem ---- zip for sharing ----
for /f "delims=" %%v in ('"%VPY%" -c "import aff; print(aff.__version__)"') do set "VER=%%v"
if "%ONEFILE%"=="1" (
    set "OUT=dist\AdvancedFileFinder.exe"
    powershell -NoProfile -Command "Compress-Archive -Force -Path 'dist\AdvancedFileFinder.exe' -DestinationPath 'dist\AdvancedFileFinder-%VER%-win64-onefile.zip'"
) else (
    set "OUT=dist\AdvancedFileFinder\AdvancedFileFinder.exe"
    powershell -NoProfile -Command "Compress-Archive -Force -Path 'dist\AdvancedFileFinder' -DestinationPath 'dist\AdvancedFileFinder-%VER%-win64.zip'"
)
echo.
echo Done.  Program : %OUT%
echo        Zip     : dist\AdvancedFileFinder-%VER%-win64*.zip
echo See PACKAGING.md for signing, testing on a clean PC and releasing.
goto :end

:nopython
echo Python 3.10 or newer was not found. Install it from https://www.python.org/downloads/
goto :end
:fail
echo.
echo Build failed - scroll up for the error message.
:end
echo.
pause
endlocal
