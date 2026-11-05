@echo off
setlocal
cd /d "%~dp0"
title Advanced File Finder

echo ============================================
echo   Advanced File Finder - setup and launch
echo ============================================
echo.

rem ---- 1. Find Python 3.10+ ----
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

rem ---- 2. Virtual environment ----
if exist ".venv\Scripts\python.exe" goto :venv_ok
echo [1/3] Creating virtual environment...
%PY% -m venv .venv
if errorlevel 1 goto :fail
:venv_ok
set "VPY=%~dp0.venv\Scripts\python.exe"

rem ---- 3. Install packages (only when requirements changed) ----
set "NEED=0"
fc /b requirements.txt .venv\req.stamp >nul 2>&1
if errorlevel 1 set "NEED=1"
fc /b requirements-dev.txt .venv\req-dev.stamp >nul 2>&1
if errorlevel 1 set "NEED=1"
if "%NEED%"=="0" (
    echo [2/3] Packages already installed.
    goto :tests
)
echo [2/3] Installing packages (first run takes a minute)...
"%VPY%" -m pip install --upgrade pip >nul 2>&1
"%VPY%" -m pip install -r requirements-dev.txt
if errorlevel 1 goto :fail
copy /y requirements.txt .venv\req.stamp >nul
copy /y requirements-dev.txt .venv\req-dev.stamp >nul

rem ---- 4. Run the tests ----
:tests
echo [3/3] Running tests...
"%VPY%" -m pytest -q
if errorlevel 1 (
    echo.
    echo Some tests failed.
    set "GO="
    set /p GO=Continue anyway? [y/N]: 
    if /i not "%GO%"=="y" goto :end
)
echo.

rem ---- 5. Launch ----
if exist "aff\app.py" (
    echo Starting Advanced File Finder...
    "%VPY%" -m aff.app
    goto :end
)

echo The window version is not built yet (stage 4). Using the search + preview
echo command line instead. Nothing is copied; this only shows what would be found.
echo.

:again
set "SRC="
set "DST="
set "EXT="
set /p SRC=Source folder to search: 
if not defined SRC goto :end
set "SRC=%SRC:"=%"
if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"
set /p DST=Destination folder (blank to skip the copy plan): 
set "DST=%DST:"=%"
if defined DST if "%DST:~-1%"=="\" set "DST=%DST:~0,-1%"
set /p EXT=Only these extensions, e.g. jpg,png (blank for all files): 

set "DSTARG="
set "EXTARG="
if defined DST set DSTARG=-d "%DST%"
if defined EXT set EXTARG=-i extension:in_list:%EXT%

echo.
"%VPY%" -m aff -s "%SRC%" %DSTARG% %EXTARG% --limit 50
echo.
set "AGAIN="
set /p AGAIN=Search again? [y/N]: 
if /i "%AGAIN%"=="y" goto :again
goto :end

:nopython
echo Python 3.10 or newer was not found.
echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH",
echo then run this file again.
start "" https://www.python.org/downloads/
goto :end

:fail
echo.
echo Setup failed. Scroll up to see the error message.

:end
echo.
pause
endlocal
