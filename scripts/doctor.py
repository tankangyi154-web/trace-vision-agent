"""Check prepared project capabilities without printing private configuration values."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api.runtime import inspect_runtime

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--require', choices=['api', 'vision', 'all'], default='api')
parser.add_argument('--json', action='store_true')
args = parser.parse_args()
packages = {name: bool(importlib.util.find_spec(name)) for name in ('fastapi', 'uvicorn', 'langgraph', 'dotenv')}
status = {'python_compatible': sys.version_info[:2] == (3, 12), 'api_packages': packages,
          'frontend_built': (ROOT / 'web/dist/index.html').is_file(), **inspect_runtime(ROOT)}
path = ROOT / '.env.local'
lines = path.read_text(encoding='utf-8').splitlines() if path.exists() else []
status['model_key_configured'] = any(line.startswith(('DEEPSEEK_API_KEY=', 'DASHSCOPE_API_KEY=')) and line.split('=', 1)[1].strip() for line in lines)
if args.json:
    print(json.dumps(status, ensure_ascii=False, indent=2))
else:
    for label, ready in [('Python 3.12', status['python_compatible']), ('API dependencies', all(packages.values())),
                         ('Frontend build', status['frontend_built']), ('Verified image runtime', status['image_analysis']),
                         ('Video runtime + FFmpeg', status['video_analysis']), ('Optional model key', status['model_key_configured'])]:
        print(f'{"READY" if ready else "MISSING":7} {label}')
    if status['missing']:
        print('Vision setup required: ' + ', '.join(status['missing']))
api_ready = status['python_compatible'] and all(packages.values()) and status['frontend_built']
ready = api_ready if args.require == 'api' else status['video_analysis'] if args.require == 'vision' else api_ready and status['video_analysis']
raise SystemExit(0 if ready else 1)
