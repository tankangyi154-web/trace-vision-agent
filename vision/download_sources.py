"""Download explicitly licensed public demo sources; no credentials are used."""
from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    cache = ROOT / "work" / "video-sources"
    cache.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / "vision/sources.json").read_text(encoding="utf-8"))
    lock_path = ROOT / "vision/sources.lock.json"
    expected = {source["id"]: source["sha256"] for source in json.loads(lock_path.read_text(encoding="utf-8"))["sources"]} if lock_path.exists() else {}
    for source in manifest["sources"]:
        path = cache / source["download_name"]
        if not path.exists():
            request = urllib.request.Request(source["download_url"], headers={"User-Agent": "VideoEventAgentDemo/1.0 (public educational project)"})
            temporary = path.with_suffix(path.suffix + ".download")
            with urllib.request.urlopen(request, timeout=90) as response, temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            downloaded_hash = hashlib.sha256(temporary.read_bytes()).hexdigest()
            if source["id"] in expected and downloaded_hash != expected[source["id"]]:
                raise RuntimeError(f"Source checksum mismatch: {source['id']}")
            temporary.replace(path)
        source["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        if source["id"] in expected and source["sha256"] != expected[source["id"]]:
            raise RuntimeError(f"Cached source checksum mismatch: {source['id']}")
        source["bytes"] = path.stat().st_size
        print(source["id"], source["bytes"], source["sha256"])
    lock_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
