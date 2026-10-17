@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -X utf8 scripts\launch.py
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -X utf8 scripts\launch.py
    ) else (
        python -X utf8 scripts\launch.py
    )
)
if errorlevel 1 pause
