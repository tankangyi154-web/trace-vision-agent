from pathlib import Path
import json,os,signal,sys,urllib.request
ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'work/portable-server.json'
try:
    state=json.loads(path.read_text(encoding='utf8'))
    with urllib.request.urlopen(f"http://127.0.0.1:{state['port']}/api/health",timeout=2) as response:health=json.load(response)
    if health.get('runtime_instance')!=state['instance']:raise ValueError('另一个服务正在使用此端口，未停止任何进程。')
    os.kill(state['pid'],signal.SIGTERM);path.unlink(missing_ok=True);print('已停止这份运行包启动的服务。')
except FileNotFoundError:print('这份运行包没有正在运行的服务。')
except (OSError,ValueError,KeyError) as error:print('未停止其他程序；请查看本机服务状态。');raise SystemExit(1)
