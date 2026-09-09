@echo off
rem psd-annotate Windows one-click build script (run on Windows, produces dist\psd-annotate.exe)
rem Flow: check Python -> create build venv -> upgrade pip -> download & install deps
rem       -> verify deps importable -> build single-file exe
rem NOTE: keep this file ASCII-only, and every exit path calls "pause"
rem       so the console window stays open and errors stay readable.

setlocal
cd /d "%~dp0psd-annotate"

rem pip mirror for faster download in China; change to https://pypi.org/simple if needed
set "PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple"

echo [check] checking Python environment ...
where python >nul 2>nul
if errorlevel 1 (
    echo [error] python not found in PATH. Please install Python 3.9+ and check "Add to PATH" during setup.
    goto :fail
)
python --version

rem 1. create isolated build venv (reuse if exists, keeps system Python clean)
if not exist .venv-build\Scripts\python.exe (
    echo [build] creating build venv .venv-build ...
    python -m venv .venv-build
    if errorlevel 1 (
        echo [error] venv creation failed.
        goto :fail
    )
)

rem 2. upgrade pip (non-fatal, keep going with existing pip on failure)
echo [build] upgrading pip ...
.venv-build\Scripts\python.exe -m pip install -q --upgrade pip -i %PIP_INDEX%
if errorlevel 1 echo [warn] pip upgrade failed, continuing with existing pip.

rem 3. download & install dependencies: requirements.txt (flask/psd-tools/pillow/mcp/aggdraw) + pyinstaller
echo [build] installing dependencies (flask, psd-tools, pillow, mcp, pyinstaller) ...
.venv-build\Scripts\python.exe -m pip install -q -r ..\requirements.txt pyinstaller -i %PIP_INDEX%
if errorlevel 1 (
    echo [error] dependency install failed. Check network or change PIP_INDEX in this script.
    goto :fail
)

rem 4. verify deps importable (catch missing packages before building)
echo [build] verifying dependencies ...
.venv-build\Scripts\python.exe -c "import flask, psd_tools, PIL, aggdraw, mcp, PyInstaller"
if errorlevel 1 (
    echo [error] dependency verification failed.
    goto :fail
)

rem 5. build single-file exe
echo [build] building exe, this may take a few minutes on first run ...
.venv-build\Scripts\python.exe -m PyInstaller --noconfirm psd-annotate.spec
if errorlevel 1 (
    echo [error] build failed. Scroll up to see the PyInstaller error output.
    goto :fail
)

echo.
echo [done] exe created at: psd-annotate\dist\psd-annotate.exe
echo usage: copy psd-annotate.exe anywhere and double-click to run.
echo        data dirs (uploads/output) are created next to the exe.
echo.
pause
exit /b 0

:fail
echo.
echo Build FAILED. See the [error] line above.
pause
exit /b 1
