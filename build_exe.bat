@echo off
rem psd-annotate Windows one-click build script (run on Windows, produces dist\psd-annotate.exe)
rem Flow: check Python -> create build venv -> upgrade pip -> download & install deps
rem       -> verify deps importable -> build single-file exe
chcp 65001 >nul
setlocal
cd /d "%~dp0psd-annotate"

rem pip 镜像源（国内默认清华源，加速依赖下载）；如需官方 PyPI 改为 https://pypi.org/simple
set "PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple"

echo [check] checking Python environment ...
where python >nul 2>nul
if errorlevel 1 (
    echo [error] python not found in PATH. Please install Python 3.9+ and check "Add to PATH" during setup.
    exit /b 1
)
python --version

rem 1. 创建独立构建虚拟环境（已存在则复用，不污染系统 Python）
if not exist .venv-build\Scripts\python.exe (
    echo [build] creating build venv .venv-build ...
    python -m venv .venv-build
    if errorlevel 1 (
        echo [error] venv creation failed.
        exit /b 1
    )
)

rem 2. 升级 pip（失败不中断，继续用已有 pip）
echo [build] upgrading pip ...
.venv-build\Scripts\python.exe -m pip install -q --upgrade pip -i %PIP_INDEX%
if errorlevel 1 echo [warn] pip upgrade failed, continuing with existing pip.

rem 3. 下载并安装依赖：requirements.txt（flask/psd-tools/pillow/mcp 及 aggdraw）+ pyinstaller
echo [build] installing dependencies (flask, psd-tools, pillow, mcp, pyinstaller) ...
.venv-build\Scripts\python.exe -m pip install -q -r ..\requirements.txt pyinstaller -i %PIP_INDEX%
if errorlevel 1 (
    echo [error] dependency install failed. Check network or change PIP_INDEX in this script.
    exit /b 1
)

rem 4. 校验依赖可导入（提前暴露缺包问题，避免打包后才失败）
echo [build] verifying dependencies ...
.venv-build\Scripts\python.exe -c "import flask, psd_tools, PIL, aggdraw, mcp, PyInstaller"
if errorlevel 1 (
    echo [error] dependency verification failed.
    exit /b 1
)

rem 5. 打包单文件 exe
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
