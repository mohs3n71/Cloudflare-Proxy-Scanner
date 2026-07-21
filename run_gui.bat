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

start "" "%PYTHONW_EXE%" -m proxy_tester.launcher
