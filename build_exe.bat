@echo off
rem psd-annotate Windows one-click build script (run on Windows, produces dist\psd-annotate.exe)
rem Steps: create isolated build venv -> install deps + PyInstaller -> build single-file exe
chcp 65001 >nul
setlocal
cd /d "%~dp0psd-annotate"

if not exist .venv-build\Scripts\python.exe (
    echo [build] creating build venv .venv-build ...
    python -m venv .venv-build
    if errorlevel 1 (
        echo [error] venv creation failed. Please install Python 3.9+ and add it to PATH.
        exit /b 1
    )
)

echo [build] installing dependencies and PyInstaller ...
.venv-build\Scripts\python.exe -m pip install -q -r ..\requirements.txt pyinstaller
if errorlevel 1 (
    echo [error] dependency install failed.
    exit /b 1
)

echo [build] building exe, this may take a few minutes on first run ...
.venv-build\Scripts\python.exe -m PyInstaller --noconfirm psd-annotate.spec
if errorlevel 1 (
    echo [error] build failed.
    exit /b 1
)

echo.
echo [done] exe created at: psd-annotate\dist\psd-annotate.exe
echo usage: copy psd-annotate.exe anywhere and double-click to run.
echo        data dirs (uploads/output) are created next to the exe.
endlocal
