@echo off
setlocal

set "CODEX_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%CODEX_PYTHON%" (
    set "PYTHON_EXE=%CODEX_PYTHON%"
) else (
    where py >nul 2>&1
    if errorlevel 1 (set "PYTHON_EXE=python") else (set "PYTHON_EXE=py")
)

"%PYTHON_EXE%" -m unittest discover -s "%~dp0tests" -p "test_*.py"
pause
