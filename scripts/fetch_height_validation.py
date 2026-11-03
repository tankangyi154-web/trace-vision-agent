"""Fetch only pinned public benchmark assets; do not execute downloaded content."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]


def fetch(row,directory):
    relative=Path(row['path']);target=(directory/relative).resolve()
    if relative.is_absolute() or directory.resolve() not in target.parents:raise ValueError('Output escaped benchmark directory')
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest()==row['sha256']:return 'cached'
    if not row['url'].startswith('https://raw.githubusercontent.com/'):raise ValueError('Unsupported data origin')
    with urlopen(Request(row['url'],headers={'User-Agent':'Trace-height-validation'}),timeout=25) as response:
        content=response.read(row['bytes']+1)
    if len(content)!=row['bytes'] or hashlib.sha256(content).hexdigest()!=row['sha256']:raise ValueError('Benchmark asset differs from pinned SHA256')
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_suffix(target.suffix+'.tmp');temporary.write_bytes(content);temporary.replace(target)
    return 'downloaded'


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--part',choices=('geometry','images','all'),default='all')
    parser.add_argument('--directory',type=Path,default=ROOT/'work/height-validation');args=parser.parse_args()
    manifest=json.loads((ROOT/'evals/height-data-sources.json').read_text(encoding='utf8'))
    rows=[r for r in manifest['files'] if args.part=='all' or r['part']==args.part]
    with ThreadPoolExecutor(max_workers=4) as pool:states=list(pool.map(lambda row:fetch(row,args.directory),rows))
    print(json.dumps({'files':len(states),'downloaded':states.count('downloaded'),'cached':states.count('cached'),'model_calls':0}))
