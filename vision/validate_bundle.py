"""Validate that shipped scene contracts, timestamps and real media agree."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]


def public_file(url: str) -> Path:
    if not url.startswith("/media/") or ".." in url:
        raise AssertionError(f"Invalid media URL: {url}")
    path = ROOT / "web/public" / url.lstrip("/")
    assert path.is_file(), path
    return path


def main() -> None:
    frames_total, observations_total, tracks_total, evidence_total = 0, 0, 0, 0
    for path in sorted((ROOT / "data/scenes").glob("*.json")):
        scene = json.loads(path.read_text(encoding="utf-8"))
        assert scene["data_kind"] == "real_detection"
        assert scene["id"] == path.stem
        assert scene["source"]["license"] == "CC BY-SA 4.0"
        assert scene["processing"]["versions"]["torch"] == "2.6.0+cpu"
        original = public_file(scene["original_url"])
        assert hashlib.sha256(original.read_bytes()).hexdigest() == scene["processing"]["output_sha256"]
        public_file(scene["poster_url"])
        for key in ["original_url", "annotated_url"]:
            media = public_file(scene[key])
            cap = cv2.VideoCapture(str(media))
            assert cap.isOpened(), media
            assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == scene["processing"]["frame_count"]
            assert abs(cap.get(cv2.CAP_PROP_FPS) - scene["fps"]) < 1e-5
            fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
            codec = "".join(chr((fourcc >> (8 * i)) & 0xFF) for i in range(4))
            assert codec in {"avc1", "h264"}, (media, codec)
            decoded = 0
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                assert frame.shape[:2] == (scene["height"], scene["width"])
                decoded += 1
            cap.release()
            assert decoded == scene["processing"]["frame_count"], (media, decoded)
        assert abs(scene["duration"] - scene["processing"]["frame_count"] / scene["fps"]) < 1e-5
        identities, samples_by_id = set(), {}
        for track in scene["tracks"]:
            assert track["id"] not in identities
            identities.add(track["id"])
            assert len(track["samples"]) >= 3
            last_frame = -1
            samples_by_id[track["id"]] = {}
            for sample in track["samples"]:
                assert last_frame < sample["frame"] < scene["processing"]["frame_count"]
                last_frame = sample["frame"]
                assert abs(sample["t"] - sample["frame"] / scene["fps"]) < 1e-4
                x1, y1, x2, y2 = sample["bbox"]
                assert 0 <= x1 <= x2 <= 1 and 0 <= y1 <= y2 <= 1
                assert 0 <= sample["confidence"] <= 1
                samples_by_id[track["id"]][sample["t"]] = sample
                observations_total += 1
        evidence_ids = set()
        for evidence in scene["evidence"]:
            assert evidence["id"] not in evidence_ids
            evidence_ids.add(evidence["id"])
            assert evidence["track_id"] in identities
            assert evidence["t"] in samples_by_id[evidence["track_id"]]
            image = cv2.imread(str(public_file(evidence["image_url"])))
            assert image is not None and image.shape[:2] == (scene["height"], scene["width"])
        frames_total += scene["processing"]["frame_count"]
        tracks_total += len(scene["tracks"])
        evidence_total += len(scene["evidence"])
        print(f"PASS {scene['id']}: {len(scene['tracks'])} real tracks, {len(scene['evidence'])} evidence records, H264 decoded fully")
    evaluation = json.loads((ROOT / "evals/results.json").read_text(encoding="utf-8"))
    for failure in evaluation["failures"]:
        public_file(failure["image_url"])
    print(json.dumps({"frames": frames_total, "tracks": tracks_total, "observations": observations_total, "evidence_records": evidence_total}))


if __name__ == "__main__":
    main()
