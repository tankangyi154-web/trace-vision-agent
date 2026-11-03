"""Build three real examples as a classic-script file:// application; no server needed."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys,zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main():
    from api.presets import list_presets,get_preset,ORDER
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--archive',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() or args.archive.exists():raise RuntimeError('Use new output paths; existing folders are preserved')
    data={'catalog':list_presets(),'examples':{ident:get_preset(ident) for ident in ORDER}}
    # This edition exposes guided proof, not the complete private-workspace gallery.
    for example in data['examples'].values():
        proof_ids={row['id'] for guide in example['guides'] for row in guide['citations']}
        for field in ['evidence','highlights']:example['result'][field]=[row for row in example['result'][field] if row['id'] in proof_ids]
        for target in example['result']['targets']:target['evidence_ids']=[ident for ident in target['evidence_ids'] if ident in proof_ids]
    def local(value):
        if isinstance(value,str) and value.startswith('/media/'):return '.'+value
        if isinstance(value,list):return [local(v) for v in value]
        if isinstance(value,dict):return {k:local(v) for k,v in value.items()}
        return value
    (ROOT/'work').mkdir(exist_ok=True)
    (ROOT/'work/offline-data.json').write_text(json.dumps(local(data),ensure_ascii=False),encoding='utf8')
    node=shutil.which('node')
    if not node:raise RuntimeError('Build requires Node; the resulting offline package does not')
    subprocess.run([node,str(ROOT/'web/node_modules/vite/bin/vite.js'),'build','--config','vite.offline.config.ts'],cwd=ROOT/'web',check=True)
    shutil.copytree(ROOT/'web/offline-dist',args.output)
    referenced=set()
    def collect(value):
        if isinstance(value,str) and value.startswith('/media/presets/'):referenced.add(value.split('?',1)[0].lstrip('/'))
        elif isinstance(value,list):
            for item in value:collect(item)
        elif isinstance(value,dict):
            for item in value.values():collect(item)
    collect(data)
    for name in sorted(referenced):
        source=(ROOT/'web/public'/name).resolve()
        if not source.is_relative_to((ROOT/'web/public/media/presets').resolve()):raise RuntimeError('Unexpected media path')
        destination=args.output/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)
    (args.output/'index.html').write_text('<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>视迹 Trace · 离线案例</title><link rel="stylesheet" href="./style.css"><script defer src="./trace-demo.js"></script></head><body><div id="app"></div></body></html>',encoding='utf8')
    (args.output/'打开案例.cmd').write_bytes(b'@echo off\r\nstart "" "%~dp0index.html"\r\n')
    shutil.copyfile(ROOT/'docs/prepared-examples.md',args.output/'素材来源与验证.md')
    shutil.copyfile(ROOT/'LICENSE',args.output/'LICENSE')
    (args.output/'使用说明.txt').write_text('视迹 Trace 离线案例版\n\n解压后双击 index.html，或点击“打开案例.cmd”。使用新版 Edge / Chrome 浏览器。\n无需联网、Python、Node、GPU或模型密钥。不要在压缩包内部直接打开。\n三个案例来自已完成的真实检测，可播放、筛选类别、选编号、点击证据回看；示例解读来自保存的记录，不调用大模型。\n本版仅附示例问题引用的截图；完整证据图库和上传新素材请使用 Windows CPU 便携版。\n来源、许可与验证范围见“素材来源与验证.md”。\n',encoding='utf8')
    files=[]
    for path in sorted(args.output.rglob('*')):
        if path.is_file():files.append({'path':path.relative_to(args.output).as_posix(),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    (args.output/'OFFLINE-MANIFEST.json').write_text(json.dumps({'edition':'offline-examples','network_required':False,'new_uploads':False,'external_model_calls':0,'files':files},ensure_ascii=False,indent=2),encoding='utf8')
    args.archive.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.archive,'w',zipfile.ZIP_DEFLATED,compresslevel=5) as bundle:
        for path in sorted(args.output.rglob('*')):
            if path.is_file():bundle.write(path,'Trace-离线案例/'+path.relative_to(args.output).as_posix())
    with zipfile.ZipFile(args.archive) as bundle:assert bundle.testzip() is None
    print(json.dumps({'files':len(files)+1,'archive_bytes':args.archive.stat().st_size,'external_model_calls':0}))

if __name__=='__main__':main()
