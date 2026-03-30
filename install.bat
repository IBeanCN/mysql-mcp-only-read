@echo off
setlocal
cd /d "%~dp0"
set "SCRIPT=%~dp0install.py"

REM Prefer the user's usual `python` on PATH, then Launcher, then python3.

where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
  python "%SCRIPT%" %*
  exit /b %ERRORLEVEL%
)

where py >nul 2>&1
if %ERRORLEVEL% equ 0 (
  py -3 "%SCRIPT%" %*
  exit /b %ERRORLEVEL%
)

where python3 >nul 2>&1
if %ERRORLEVEL% equ 0 (
  python3 "%SCRIPT%" %*
  exit /b %ERRORLEVEL%
)

echo ERROR: No Python found. Install 3.10+ from https://www.python.org/downloads/ ^(add to PATH^) or run: py -3 install.py
exit /b 1
