@echo off
setlocal

cd /d "%~dp0"

set "CODEX_PYTHON_DIR=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python"
if exist "%CODEX_PYTHON_DIR%\python.exe" (
    set "PYTHON_EXE=%CODEX_PYTHON_DIR%\python.exe"
    set "PYTHONW_EXE=%CODEX_PYTHON_DIR%\pythonw.exe"
) else (
    where py >nul 2>&1
    if errorlevel 1 (
        set "PYTHON_EXE=python"
        set "PYTHONW_EXE=pythonw"
    ) else (
        set "PYTHON_EXE=py"
        set "PYTHONW_EXE=pyw"
    )
)

"%PYTHON_EXE%" tools\xray_release.py --if-missing
if errorlevel 1 (
    pause
    exit /b 1
)

start "" "%PYTHONW_EXE%" -m proxy_tester.gui
