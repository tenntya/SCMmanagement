@echo off
setlocal
cd /d %~dp0\..
powershell -ExecutionPolicy Bypass -File scripts\push_with_token.ps1
endlocal

