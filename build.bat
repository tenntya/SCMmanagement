@echo off
setlocal
cd /d %~dp0

if not exist .venv (
  echo [i] Creating venv
  py -3 -m venv .venv
)
call .venv\Scripts\activate
pip install -U pip
pip install -r requirements.txt

set NAME=procurement_manager
set SRC=procurement_manager\main.py
set TEMPLATES=procurement_manager\templates
set STATIC=procurement_manager\static

pyinstaller --noconfirm --clean ^
  --onefile --name %NAME% ^
  --add-data "%TEMPLATES%;procurement_manager/templates" ^
  --add-data "%STATIC%;procurement_manager/static" ^
  %SRC%

REM copy external settings next to EXE
if exist pm_settings.ini (
  copy /Y pm_settings.ini dist\pm_settings.ini >nul
) else if exist procurement_manager\example_pm_settings.ini (
  copy /Y procurement_manager\example_pm_settings.ini dist\pm_settings.ini >nul
)

echo.
echo [OK] Built dist\%NAME%.exe
endlocal
