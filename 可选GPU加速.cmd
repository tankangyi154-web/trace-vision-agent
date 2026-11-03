@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 可选 NVIDIA GPU 环境：需要兼容显卡、驱动及联网下载数GB依赖。
echo 本操作不安装或更新显卡驱动；未通过验证时继续使用CPU。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_gpu.ps1"
pause
