@echo off
chcp 65001 >nul
cd /d "%~dp0"
"%~dp0work\vision-env\Scripts\python.exe" -X utf8 "%~dp0scripts\stop_portable.py"
if errorlevel 1 pause
