"""Keep the download's only launch entry separate from implementation and maintenance."""
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]

def batch(path,lines):
    # Windows CMD misparses some LF-only, UTF-8 scripts. Keep its program ASCII/CRLF.
    path.write_bytes(('\r\n'.join(lines)+'\r\n').encode('ascii'))

def create_layout(stage):
    app=stage/'app';app.mkdir()
    return app

def write_entries(stage):
    app=stage/'app';tools=stage/'开发与维护';tools.mkdir(exist_ok=True)
    batch(stage/'启动项目.cmd',[
        '@echo off','setlocal','chcp 65001 >nul','cd /d "%~dp0"',
        'if not exist "%~dp0app\\work\\vision-env\\Scripts\\python.exe" goto missing',
        '"%~dp0app\\work\\vision-env\\Scripts\\python.exe" -X utf8 "%~dp0app\\scripts\\launch_portable.py" %*',
        'if errorlevel 1 goto failed','exit /b 0',':missing',
        'echo Please extract the ENTIRE Trace folder before starting.',
        'echo Missing: app\\work\\vision-env\\Scripts\\python.exe','pause','exit /b 1',':failed',
        'echo Please keep the message above. See app\\work\\launch-error.log for details.',
        'pause','exit /b 1'])
    for name,script in [('停止项目.cmd','stop_portable.py'),('运行环境检查.cmd','vision_smoke.py')]:
        batch(tools/name,['@echo off','setlocal','chcp 65001 >nul','cd /d "%~dp0..\\app"',
            f'"work\\vision-env\\Scripts\\python.exe" -X utf8 "scripts\\{script}"',
            'echo.','echo Diagnostic files: app\\work\\vision-selftest.json and app\\work\\launch-error.log',
            'echo Microsoft runtime: https://aka.ms/vs/17/release/vc_redist.x64.exe','pause'])
    batch(tools/'可选GPU加速.cmd',['@echo off','setlocal','chcp 65001 >nul','cd /d "%~dp0..\\app"',
        'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "scripts\\setup_gpu.ps1"','pause'])
    # Source-specific entry points are not mixed with the runnable application's root.
    dev=tools/'开发入口';dev.mkdir(exist_ok=True)
    for name in ['启动本地.cmd','启动便携版.cmd','停止便携版.cmd','运行环境检查.cmd','setup.cmd','setup.ps1']:
        path=app/name
        if path.exists():path.unlink()
    (dev/'说明.txt').write_text('应用实现、构建脚本和项目文档位于 ../../app。\n二次开发请从 GitHub 克隆源码仓库；不要使用便携运行时安装开发依赖。\nhttps://github.com/tankangyi154-web/trace-vision-agent\n',encoding='utf8')
    shutil.copyfile(ROOT/'便携版使用说明.txt',stage/'使用说明.txt')
