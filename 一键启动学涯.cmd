@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
chcp 65001 >nul
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -X utf8 quick_start.py --prepare
) else (
    py -3 -X utf8 quick_start.py --prepare
)
set "XUEYA_LAUNCH_RESULT=%ERRORLEVEL%"
if not "%XUEYA_LAUNCH_RESULT%"=="0" goto finish
set /p XUEYA_URL=<".xueya-data\launch-url.txt"
echo Opening in your Windows default browser.
start "" "%XUEYA_URL%"
if errorlevel 1 goto browser_failed
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -X utf8 quick_start.py --verify
) else (
    py -3 -X utf8 quick_start.py --verify
)
set "XUEYA_LAUNCH_RESULT=%ERRORLEVEL%"
goto finish
:browser_failed
echo ERROR: Windows could not open the default browser.
echo ERROR: Windows could not open the default browser.>>".xueya-data\quick-start.log"
set "XUEYA_LAUNCH_RESULT=1"
:finish
echo.
echo Launcher exit code: %XUEYA_LAUNCH_RESULT%
echo This window stays open. Press any key to close it.
echo Closing this window does not stop the background service.
pause >nul
exit /b %XUEYA_LAUNCH_RESULT%
