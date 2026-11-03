"""Build a relocatable Windows CPU distribution from explicitly prepared environments."""
from pathlib import Path
import argparse,hashlib,json,os,re,shutil,sys,urllib.request,uuid,zipfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
from portable_layout import create_layout,write_entries
ROOT=Path(__file__).resolve().parents[1]
ROOT_DIRS={'.github','api','data','deploy','docs','evals','scripts','vision','web'}
ROOT_FILES={'.env.example','.gitattributes','.gitignore','.vercelignore','.dockerignore','Dockerfile','compose.yaml','LICENSE','README.md','THIRD_PARTY_NOTICES.md','app.py','pyproject.toml','pytest.ini','requirements.txt','requirements-dev.txt','setup.cmd','setup.ps1','vercel.json','启动本地.cmd','启动便携版.cmd','停止便携版.cmd','运行环境检查.cmd'}
SKIP={'node_modules','__pycache__','.pytest_cache','.git','.venv','work','weights','cache','Ultralytics'}

def digest(path):
    with path.open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()

def secrets_to_exclude():
    path=ROOT/'.env.local'
    if not path.is_file():return []
    values=[]
    for line in path.read_text(encoding='utf8').splitlines():
        if '=' not in line or line.lstrip().startswith('#'):continue
        key,value=line.split('=',1);value=value.strip().strip('"\'')
        if any(word in key.upper() for word in ('KEY','TOKEN','SECRET','PASSWORD')) and len(value)>=12:values.append(value.encode())
    return values

def safe_source_files():
    for base,dirs,files in os.walk(ROOT):
        base=Path(base)
        dirs[:]=[d for d in dirs if d not in SKIP and (base!=ROOT or d in ROOT_DIRS)]
        relative=base.relative_to(ROOT)
        if relative==Path('web'):dirs[:]=[d for d in dirs if d!='offline-dist']
        if relative==Path('web/dist'):dirs[:]=[d for d in dirs if d!='media']
        for name in files:
            path=base/name
            if base==ROOT and name not in ROOT_FILES:continue
            if (name.startswith('.env') or name.endswith('.env')) and name!='.env.example' or path.suffix in ('.pyc','.pyo','.sqlite3','.log'):continue
            yield path

def copy_site(source,target):
    excluded={'__pycache__','tests','pip-wheel-metadata','.cache','onnx','onnx-1.19.1.dist-info','pytest','_pytest','iniconfig','pluggy'}
    for base,dirs,files in os.walk(source):
        base=Path(base);relative=base.relative_to(source)
        dirs[:]=[d for d in dirs if d not in excluded and not d.startswith(('pytest-','iniconfig-','pluggy-'))]
        if relative==Path('torch'):dirs[:]=[d for d in dirs if d not in ('include','test')]
        if relative==Path('imageio_ffmpeg'):dirs[:]=[d for d in dirs if d!='binaries']
        for name in files:
            path=base/name
            if path.suffix in ('.pyc','.pyo','.lib','.exp','.a') or path.suffix=='.pth' and name!='distutils-precedence.pth':continue
            dest=target/relative/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)

def check_secrets(path,values):
    if not values:return
    keep=max(map(len,values))-1;tail=b''
    with path.open('rb') as handle:
        while chunk:=handle.read(1024*1024):
            block=tail+chunk
            if any(value in block for value in values):raise RuntimeError('Private configuration detected in selected file: '+path.name)
            tail=block[-keep:]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--api-site',type=Path,required=True);parser.add_argument('--vision-site',type=Path,required=True)
    parser.add_argument('--stage',type=Path,required=True);parser.add_argument('--archive',type=Path,required=True);parser.add_argument('--download-cache',type=Path,required=True)
    parser.add_argument('--stage-only',action='store_true')
    args=parser.parse_args();stage=args.stage.resolve()
    if stage.exists():raise RuntimeError('Use a new staging directory; existing user records are never overwritten')
    stage.mkdir(parents=True);values=secrets_to_exclude();app=create_layout(stage)
    for source in safe_source_files():
        dest=app/source.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
    write_entries(stage)
    runtime=app/'work/vision-env/Scripts';runtime.mkdir(parents=True)
    lock=json.loads((ROOT/'scripts/portable-runtime.lock.json').read_text(encoding='utf8'));args.download_cache.mkdir(parents=True,exist_ok=True)
    embedded=args.download_cache/'python-embed.zip'
    if not embedded.is_file() or digest(embedded)!=lock['sha256']:
        request=urllib.request.Request(lock['url'],headers={'User-Agent':'Trace-portable-builder'})
        with urllib.request.urlopen(request,timeout=60) as response,embedded.open('wb') as output:shutil.copyfileobj(response,output)
    if embedded.stat().st_size!=lock['bytes'] or digest(embedded)!=lock['sha256']:raise RuntimeError('Official Python archive checksum mismatch')
    with zipfile.ZipFile(embedded) as bundle:
        for name in bundle.namelist():
            if Path(name).name!=name:raise RuntimeError('Unexpected embedded Python archive path')
        bundle.extractall(runtime)
    # Windows embedded Python canonicalizes a trailing '..' differently without '/'.
    (runtime/'python312._pth').write_text('python312.zip\n.\nLib/site-packages\n../../../\nimport site\n',encoding='utf8')
    site=runtime/'Lib/site-packages';site.mkdir(parents=True)
    copy_site(args.api_site,site);copy_site(args.vision_site,site)
    weights=app/'vision/weights';weights.mkdir(parents=True)
    for name in ['model.lock.json','upload-model.lock.json','appearance-model.lock.json']:
        model=json.loads((ROOT/'vision'/name).read_text(encoding='utf8'));source=ROOT/'vision/weights'/model['model']
        if digest(source)!=model['sha256']:raise RuntimeError('Unverified source model')
        shutil.copyfile(source,weights/source.name)
    for name in ['detector.onnx','appearance.onnx','manifest.json']:
        destination=app/'work/onnx-models'/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/'work/onnx-models'/name,destination)
    (app/'work/bin').mkdir(parents=True);shutil.copyfile(ROOT/'work/bin/ffmpeg.exe',app/'work/bin/ffmpeg.exe')
    for filename in ['.env.local','work/local.sqlite3','work/agent-identity.json','work/cpu-profile.json','work/vision-selftest.json','work/portable-server.json']:
        if (app/filename).exists():raise RuntimeError('User state cannot be distributed')
    files=[]
    for path in sorted(stage.rglob('*')):
        if not path.is_file():continue
        check_secrets(path,values)
        files.append({'path':path.relative_to(stage).as_posix(),'bytes':path.stat().st_size,'sha256':digest(path)})
    manifest={'project':'video-event-agent','edition':'windows-cpu-portable','build_id':str(uuid.uuid4()),'date':'2026-11-03','python':lock,
        'api_keys_included':False,'user_records_included':False,'gpu_dependencies_included':False,
        'version':'1.0.2','launch':'启动项目.cmd','application_directory':'app','maintenance_directory':'开发与维护',
        'native_runtime_note':'Some Windows machines require the Microsoft x64 Visual C++ runtime; startup checks it and preserves prepared examples when unavailable.',
        'files':files}
    (app/'PORTABLE-MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    if args.stage_only:
        print(json.dumps({'stage_ready':True,'files':len(files)+1,'uncompressed_bytes':sum(row['bytes'] for row in files),'credential_scan':'passed'}));return
    if args.archive.exists():raise RuntimeError('Archive exists; use a new output filename')
    args.archive.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.archive,'w',zipfile.ZIP_DEFLATED,compresslevel=5) as bundle:
        for path in sorted(stage.rglob('*')):
            if path.is_file():bundle.write(path,'Trace/'+path.relative_to(stage).as_posix())
    with zipfile.ZipFile(args.archive) as bundle:
        if bundle.testzip() is not None:raise RuntimeError('Archive integrity check failed')
    summary={'files':len(files)+1,'uncompressed_bytes':sum(row['bytes'] for row in files),'archive_bytes':args.archive.stat().st_size,'archive_sha256':digest(args.archive),'credential_scan':'passed'}
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
