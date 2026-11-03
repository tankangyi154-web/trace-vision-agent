@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "PORTABLE-MANIFEST.json" (
  echo 当前是源码目录。请先运行 setup.cmd，再运行启动本地.cmd。
  pause
  exit /b 1
)
"%~dp0work\vision-env\Scripts\python.exe" -X utf8 "%~dp0scripts\launch_portable.py"
if errorlevel 1 pause
