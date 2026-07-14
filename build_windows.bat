@echo off
setlocal

cd /d "%~dp0"

if not "%PYTHON_EXE%"=="" goto python_ready

set "CODEX_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%CODEX_PYTHON%" (
    set "PYTHON_EXE=%CODEX_PYTHON%"
) else (
    where py >nul 2>&1
    if errorlevel 1 (set "PYTHON_EXE=python") else (set "PYTHON_EXE=py")
)

:python_ready

set TARGET_ARCH=%~1
if "%XRAY_VERSION%"=="" set XRAY_VERSION=latest

if "%TARGET_ARCH%"=="" (
    "%PYTHON_EXE%" tools\build_release.py --os windows --xray-version "%XRAY_VERSION%"
) else (
    "%PYTHON_EXE%" tools\build_release.py --os windows --arch "%TARGET_ARCH%" --xray-version "%XRAY_VERSION%"
)

exit /b %errorlevel%
