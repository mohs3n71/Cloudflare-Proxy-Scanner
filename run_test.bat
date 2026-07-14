@echo off
setlocal

cd /d "%~dp0"

set "CODEX_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%CODEX_PYTHON%" (
    set "PYTHON_EXE=%CODEX_PYTHON%"
) else (
    where py >nul 2>&1
    if errorlevel 1 (set "PYTHON_EXE=python") else (set "PYTHON_EXE=py")
)

"%PYTHON_EXE%" tools\xray_release.py --if-missing
if errorlevel 1 exit /b 1

if "%~1"=="" (
    "%PYTHON_EXE%" test_xray_cloudflare.py
) else (
    "%PYTHON_EXE%" test_xray_cloudflare.py %1
)
pause
