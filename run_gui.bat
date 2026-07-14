@echo off
setlocal

cd /d "%~dp0"

set PYTHON_EXE=C:\Users\Mohsen\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe

start "" "%PYTHON_EXE%" -m proxy_tester.gui
