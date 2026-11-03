"""Build the locked Vue client. No model, Redis or vision dependencies needed."""
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parent.parent
npm=shutil.which('npm.cmd') or shutil.which('npm')
if not npm: raise SystemExit('Node.js/npm is required to build the frontend')
subprocess.run([npm,'ci','--no-audit','--no-fund'],cwd=ROOT/'web',check=True)
subprocess.run([npm,'run','build'],cwd=ROOT/'web',check=True)
