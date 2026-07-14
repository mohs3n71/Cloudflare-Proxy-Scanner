@echo off
setlocal

set PYTHON_EXE=C:\Users\Mohsen\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe

"%PYTHON_EXE%" -m unittest discover -s "%~dp0tests" -p "test_*.py"
pause
