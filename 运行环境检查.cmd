@echo off
chcp 65001 >nul
cd /d "%~dp0"
"%~dp0work\vision-env\Scripts\python.exe" -X utf8 "%~dp0scripts\vision_smoke.py"
echo.
echo 如果提示 native_runtime，请从微软官网安装 x64 Visual C++ 运行库后重试：
echo https://aka.ms/vs/17/release/vc_redist.x64.exe
echo 本机诊断保存在 work\vision-selftest.json 和 work\vision-selftest.log。
pause
