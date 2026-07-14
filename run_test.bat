@echo off
setlocal

set PYTHON_EXE=C:\Users\Mohsen\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe

if "%~1"=="" (
    "%PYTHON_EXE%" "%~dp0test_xray_cloudflare.py"
) else (
    "%PYTHON_EXE%" "%~dp0test_xray_cloudflare.py" %1
)
pause
