@echo off
setlocal
cd /d %~dp0

set LOGDIR=%CD%\logs
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
for /f "tokens=1-3 delims=/-. " %%a in ("%date%") do set D=%%a%%b%%c
set LOGFILE=%LOGDIR%\run_%D%.log

echo [%date% %time%] start >> "%LOGFILE%"

if exist .\dist\procurement_manager.exe (
  start "" /B cmd /c ".\dist\procurement_manager.exe --once --no-sample >> \"%LOGFILE%\" 2>&1"
) else (
  py -3 procurement_manager\main.py --once >> "%LOGFILE%" 2>&1
)

echo [%date% %time%] done >> "%LOGFILE%"
endlocal
