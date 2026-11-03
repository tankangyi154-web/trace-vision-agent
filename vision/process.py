"""Run real YOLO11n + ByteTrack locally and export Contract v1 scene bundles.

Bundled demos: python vision/process.py --all
Own licensed video: python vision/process.py --input my.mp4 --scene-id custom --config metadata.json
The custom config includes source, title, subtitle, focus, zones, default_dwell_seconds.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("YOLO_CONFIG_DIR", str(ROOT / "work/yolo-config"))
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "work/mpl-config"))

import cv2
import imageio_ffmpeg
import numpy as np
import torch
from ultralytics import YOLO

MODEL = ROOT / "vision/weights/yolo11n.pt"
TRACKER = ROOT / "vision/bytetrack.yaml"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def publish_demo_cover(scene_id: str, poster: Path) -> None:
    """Keep the bundled, content-hashed frontend covers in sync with demo media."""
    if scene_id not in {'harbor', 'crossing', 'night'}:
        return
    directory = ROOT / 'web/src/assets/demo-covers'
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(poster, directory / f'{scene_id}.jpg')


def ffmpeg(args: list[str]) -> None:
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def draw(frame: np.ndarray, boxes: list[dict], width: int, height: int) -> np.ndarray:
    """Bake only actual object detections into media; regions belong to the UI."""
    canvas = frame.copy()
    for box in boxes:
        x1, y1, x2, y2 = [round(value * size) for value, size in zip(box["bbox"], [width, height, width, height])]
        color = (70, 225, 235)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
        cv2.putText(canvas, f'{box["id"]} {box["label"]} {box["confidence"]:.2f}', (max(0, x1), max(16, y1 - 7)), cv2.FONT_HERSHEY_SIMPLEX, 0.47, color, 1, cv2.LINE_AA)
    return canvas


def write_evidence_frame(directory: Path, frame_number: int, canvas: np.ndarray, written_frames: set[int]) -> str:
    """Share one frame within this run, always replace a previous run's pixels."""
    filename=f"frame-{frame_number:04d}.jpg"
    if frame_number not in written_frames:
        if not cv2.imwrite(str(directory/filename),canvas,[cv2.IMWRITE_JPEG_QUALITY,76]):
            raise RuntimeError(f'Failed to write evidence frame {frame_number}')
        written_frames.add(frame_number)
    return filename


def process(input_path: Path, scene_id: str, config: dict, source: dict, output_fps: int = 10) -> dict:
    if not scene_id or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-" for ch in scene_id):
        raise ValueError("scene-id must use lower-case ASCII letters, digits and hyphens")
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    output_dir = ROOT / "web/public/media" / scene_id
    evidence_dir = output_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    original = output_dir / "original.mp4"
    # CFR output makes t = frame/fps exact, normalizes dimensions, strips audio and metadata.
    ffmpeg(["-i", str(input_path), "-t", str(config.get("max_duration", 30)), "-vf", f"scale=960:-2,fps={output_fps}", "-an", "-map_metadata", "-1", "-c:v", "libx264", "-crf", "25", "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(original)])
    cap = cv2.VideoCapture(str(original))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width, height = int(cap.get(3)), int(cap.get(4))
    if frame_count <= 0 or fps <= 0:
        raise RuntimeError("Decoded video has no frames")
    torch.set_num_threads(4)
    torch.manual_seed(0)
    np.random.seed(0)
    model = YOLO(str(MODEL))
    tracks = defaultdict(list)
    labels: dict[str, str] = {}
    frame_boxes: list[list[dict]] = []
    inference_ms: list[float] = []
    processing_start = time.perf_counter()
    for frame_number in range(frame_count):
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError(f"Failed to decode frame {frame_number}")
        start = time.perf_counter()
        result = model.track(frame, persist=True, tracker=str(TRACKER), conf=0.25, iou=0.5, imgsz=640, classes=config.get("classes", [0, 1, 2, 3, 5, 7, 8]), device="cpu", verbose=False)[0]
        inference_ms.append((time.perf_counter() - start) * 1000)
        boxes = []
        if result.boxes.id is not None:
            for bbox, confidence, class_id, track_id in zip(result.boxes.xyxyn.tolist(), result.boxes.conf.tolist(), result.boxes.cls.tolist(), result.boxes.id.tolist()):
                identity = f"T{int(track_id):03d}"
                bbox = [round(min(1.0, max(0.0, x)), 6) for x in bbox]
                sample = {"frame": frame_number, "t": round(frame_number / fps, 4), "bbox": bbox, "confidence": round(confidence, 5)}
                tracks[identity].append(sample)
                label = model.names[int(class_id)]
                labels[identity] = label
                boxes.append({"id": identity, "label": label, **sample})
        frame_boxes.append(boxes)
        if frame_number % 50 == 0:
            print(f"{scene_id}: frame {frame_number}/{frame_count}", flush=True)
    cap.release()
    # No fabricated interpolation. Every saved sample corresponds to a real tracked detection.
    retained = {identity for identity, samples in tracks.items() if len(samples) >= 3}
    scene_tracks = [{"id": identity, "label": labels[identity], "samples": samples} for identity, samples in sorted(tracks.items()) if identity in retained]
    cap = cv2.VideoCapture(str(original))
    raw_annotated = ROOT / "work" / f"{scene_id}-annotated.avi"
    writer = cv2.VideoWriter(str(raw_annotated), cv2.VideoWriter_fourcc(*"MJPG"), fps, (width, height))
    evidence = []
    written_evidence_frames: set[int] = set()
    poster_frame = min(frame_count - 1, round(config.get("poster_t", 0) * fps))
    for frame_number in range(frame_count):
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError(f"Failed second-pass decoding at {frame_number}")
        boxes = [box for box in frame_boxes[frame_number] if box["id"] in retained]
        canvas = draw(frame, boxes, width, height)
        cv2.putText(canvas, f"{frame_number / fps:05.1f}s  YOLO11n + ByteTrack", (14, height - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
        writer.write(canvas)
        if frame_number == poster_frame:
            cv2.imwrite(str(output_dir / "poster.jpg"), canvas, [cv2.IMWRITE_JPEG_QUALITY, 86])
        # Capture each track start/end plus 0.5 s cadence: real time is recorded explicitly.
        for box in boxes:
            samples = tracks[box["id"]]
            is_boundary = frame_number in {samples[0]["frame"], samples[-1]["frame"]}
            if frame_number % max(1, round(fps / 2)) != 0 and not is_boundary:
                continue
            evidence_id = f"{scene_id}-{box['id']}-f{frame_number:04d}"
            # One full-frame image per timestamp, shared by target evidence records.
            filename = write_evidence_frame(evidence_dir,frame_number,canvas,written_evidence_frames)
            evidence.append({"id": evidence_id, "track_id": box["id"], "t": round(frame_number / fps, 4), "image_url": f"/media/{scene_id}/evidence/{filename}", "description": f"{labels[box['id']]} {box['id']}，视频 {frame_number / fps:.1f} 秒的真实检测帧"})
    cap.release()
    writer.release()
    publish_demo_cover(scene_id, output_dir / 'poster.jpg')
    ffmpeg(["-i", str(raw_annotated), "-an", "-map_metadata", "-1", "-c:v", "libx264", "-crf", "24", "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output_dir / "annotated.mp4")])
    versions = {package: importlib.metadata.version(package) for package in ["torch", "torchvision", "ultralytics", "opencv-python", "numpy", "lap", "imageio-ffmpeg"]}
    versions["python"] = platform.python_version()
    source = {key: source[key] for key in ["title", "url", "author", "license", "license_url"]}
    source["modifications"] = f"无音频；等比缩至 {width}×{height}；重采样 {fps:g}fps；裁至前 {frame_count / fps:.2f} 秒；标注版增加实际检测框，统计区域由页面按需显示。素材及派生媒体的许可为 {source['license']}。"
    scene = {"id": scene_id, "title": config["title"], "subtitle": config["subtitle"], "focus": config["focus"], "duration": round(frame_count / fps, 4), "fps": fps, "width": width, "height": height, "original_url": f"/media/{scene_id}/original.mp4", "annotated_url": f"/media/{scene_id}/annotated.mp4", "poster_url": f"/media/{scene_id}/poster.jpg", "data_kind": "real_detection", "zones": config["zones"], "default_zone_id": "A", "default_dwell_seconds": config["default_dwell_seconds"], "tracks": scene_tracks, "evidence": evidence, "source": source, "processing": {"model": "YOLO11n (COCO pretrained)", "tracker": "ByteTrack", "confidence": 0.25, "iou": 0.5, "imgsz": 640, "sample_fps": fps, "versions": versions, "model_sha256": sha256(MODEL), "tracker_sha256": sha256(TRACKER), "input_sha256": sha256(input_path), "output_sha256": sha256(original), "classes": config.get("classes"), "min_track_samples": 3, "device": "cpu", "cpu_threads": 4, "frame_count": frame_count, "inference_ms_mean": round(float(np.mean(inference_ms)), 3), "inference_ms_p50": round(float(np.median(inference_ms)), 3), "inference_ms_p95": round(float(np.percentile(inference_ms, 95)), 3), "processing_wall_seconds": round(time.perf_counter() - processing_start, 3)}, "notes": config["notes"]}
    (ROOT / "data/scenes").mkdir(parents=True, exist_ok=True)
    (ROOT / "data/scenes" / f"{scene_id}.json").write_text(json.dumps(scene, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"scene": scene_id, "frames": frame_count, "tracks": len(scene_tracks), "samples": sum(len(track["samples"]) for track in scene_tracks), "evidence": len(evidence)}, ensure_ascii=False), flush=True)
    return scene


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--scene", choices=["harbor", "crossing", "night"])
    parser.add_argument("--input", type=Path)
    parser.add_argument("--scene-id")
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    if not MODEL.exists():
        raise SystemExit("Download the pinned model first: python vision/download_model.py")
    demos = json.loads((ROOT / "vision/demo-scenes.json").read_text(encoding="utf-8"))
    if args.all or args.scene:
        sources = json.loads((ROOT / "vision/sources.lock.json").read_text(encoding="utf-8"))["sources"]
        for source in sources:
            if args.scene and source["id"] != args.scene:
                continue
            process(ROOT / "work/video-sources" / source["download_name"], source["id"], demos[source["id"]], source)
    elif args.input and args.scene_id and args.config:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        process(args.input, args.scene_id, config, config["source"])
    else:
        parser.error("Use --all, --scene or --input + --scene-id + --config")


if __name__ == "__main__":
    main()
