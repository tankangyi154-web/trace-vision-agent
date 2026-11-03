"""No-install local launcher. Binds loopback only and never installs system components."""
from pathlib import Path
import argparse,json,os,socket,subprocess,sys,time,urllib.request,uuid,webbrowser
ROOT=Path(__file__).resolve().parents[1]

def local_environment():
    names=('SYSTEMROOT','WINDIR','PATH','PATHEXT','COMSPEC','NUMBER_OF_PROCESSORS','PROCESSOR_ARCHITECTURE','OS','USERPROFILE','LOCALAPPDATA','APPDATA','TEMP','TMP')
    env={name:os.environ[name] for name in names if name in os.environ}
    env.update(PYTHONIOENCODING='utf-8',PYTHONUTF8='1',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',APP_MODE='local',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4')
    return env

def health(port):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',timeout=1) as response:return json.load(response)
    except (OSError,ValueError):return None

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--no-browser',action='store_true');parser.add_argument('--check-only',action='store_true');parser.add_argument('--port',type=int,default=8000);args=parser.parse_args()
    os.chdir(ROOT);work=ROOT/'work';work.mkdir(exist_ok=True)
    state=work/'portable-server.json'
    try:
        previous=json.loads(state.read_text(encoding='utf8'));ready=health(previous['port'])
        if ready and ready.get('runtime_instance')==previous['instance']:
            url=f"http://127.0.0.1:{previous['port']}/"
            if not args.no_browser:webbrowser.open(url)
            print(json.dumps({'ready':True,'url':url,'reused_server':True}));return 0
    except (OSError,ValueError,KeyError,TypeError):pass
    print('正在检查本机识别环境，稍后将打开分析工作台。',flush=True)
    flags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0
    with (work/'vision-selftest.log').open('w',encoding='utf8') as log:
        try:
            check=subprocess.run([sys.executable,str(ROOT/'scripts/vision_smoke.py')],cwd=ROOT,env=local_environment(),stdout=log,stderr=log,timeout=180,creationflags=flags)
            check_code=check.returncode
        except subprocess.TimeoutExpired:
            check_code=1
            (work/'vision-selftest.json').write_text(json.dumps({'ok':False,'code':'vision_self_test','reason':'识别自检超时，请运行环境检查。'}),encoding='utf8')
    print('图像分析自检通过。' if check_code==0 else '识别自检未通过，先开放已有案例；请运行环境检查获取修复说明。',flush=True)
    if args.check_only:return check_code
    selected=None
    for port in range(args.port,min(args.port+30,65536)):
        try:
            with socket.socket() as candidate:candidate.bind(('127.0.0.1',port))
            selected=port;break
        except OSError:continue
    if selected is None:raise RuntimeError('没有可用的本机端口，请关闭重复启动的程序。')
    instance=str(uuid.uuid4());env=local_environment();env['TRACE_DISTRIBUTION_INSTANCE']=instance
    with (work/'server.log').open('w',encoding='utf8') as out,(work/'server-error.log').open('w',encoding='utf8') as error:
        process=subprocess.Popen([sys.executable,'-m','uvicorn','app:app','--host','127.0.0.1','--port',str(selected),'--no-access-log'],cwd=ROOT,env=env,stdout=out,stderr=error,creationflags=flags)
    for _ in range(100):
        ready=health(selected)
        if ready and ready.get('runtime_instance')==instance:
            state.write_text(json.dumps({'pid':process.pid,'port':selected,'instance':instance}),encoding='utf8')
            url=f'http://127.0.0.1:{selected}/'
            if not args.no_browser:webbrowser.open(url)
            print(json.dumps({'ready':True,'url':url,'vision_ready':check_code==0}));return 0
        if process.poll() is not None:raise RuntimeError('启动失败，请查看work/server-error.log。')
        time.sleep(.2)
    process.terminate();raise RuntimeError('启动超时，请查看work/server-error.log。')

if __name__=='__main__':raise SystemExit(main())
