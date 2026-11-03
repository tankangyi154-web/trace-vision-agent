"""Native/runtime self-test happens on the deployment host, never at image build time."""
from pathlib import Path
import os,subprocess,sys
root=Path(__file__).resolve().parents[1]
try:
    subprocess.run([str(root/'work/vision-env/bin/python'),str(root/'scripts/vision_smoke.py')],cwd=root,timeout=180,check=False)
except subprocess.TimeoutExpired:
    import json
    (root/'work/vision-selftest.json').write_text(json.dumps({'ok':False,'code':'vision_self_test'}))
os.chdir(root)
os.execv(sys.executable,[sys.executable,'-m','uvicorn','app:app','--host','0.0.0.0','--port','8000','--workers','1','--no-access-log'])
