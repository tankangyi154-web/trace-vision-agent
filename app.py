"""Vercel FastAPI entrypoint. Static frontend is promoted to the CDN at build time."""
from api.index import app
from api.catalog import ROOT

app.frontend('/',directory=ROOT/'web'/'dist',fallback='index.html',check_dir=False)
