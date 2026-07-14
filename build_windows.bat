@echo off
setlocal

cd /d "%~dp0"

set APP_NAME=cloudflare-proxy-tester
set PYTHON_EXE=python

if exist "C:\Users\Mohsen\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
    set PYTHON_EXE=C:\Users\Mohsen\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
)

if not exist "bin\xray\xray.exe" (
    echo Missing bin\xray\xray.exe
    echo Put the Windows Xray binary there before building.
    exit /b 1
)

"%PYTHON_EXE%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo PyInstaller is not installed for "%PYTHON_EXE%".
    echo Install it with: "%PYTHON_EXE%" -m pip install pyinstaller
    exit /b 1
)

"%PYTHON_EXE%" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "%APP_NAME%" ^
    --add-data "bin\xray;bin\xray" ^
    proxy_tester\gui_entry.py

if errorlevel 1 exit /b 1

echo.
echo Built dist\%APP_NAME%.exe
