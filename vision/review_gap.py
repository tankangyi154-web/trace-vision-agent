"""One fixed, offline ROI recheck of harbor/T001 frames 124..130.

This worker never edits baseline scene data and never asserts target identity.
Only --output is configurable. Inputs, model, ROI construction and gates are fixed.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "web/public/media/harbor/original.mp4"
SCENE = ROOT / "data/scenes/harbor.json"
MODEL = ROOT / "vision/weights/yolo11n.pt"
EXPECTED_SOURCE_SHA = "48acaf2024ca892a133c31b238742f8f76d6cef76188e33dc01904e15a600376"
EXPECTED_MODEL_SHA = "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1"
FRAMES = tuple(range(124, 131))
ASSOCIATION_IOU = 0.2
AMBIGUITY_MARGIN = 0.1


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixed_roi(before: list[float], after: list[float]) -> list[float]:
    return [max(0.0, min(before[0], after[0]) - 0.05), max(0.0, min(before[1], after[1]) - 0.05), min(1.0, max(before[2], after[2]) + 0.05), min(1.0, max(before[3], after[3]) + 0.05)]


def crop_bounds(roi: list[float], width: int, height: int) -> tuple[int, int, int, int]:
    return (max(0, math.floor(roi[0] * width)), max(0, math.floor(roi[1] * height)), min(width, math.ceil(roi[2] * width)), min(height, math.ceil(roi[3] * height)))


def map_crop_box(box: list[float], bounds: tuple[int, int, int, int], width: int, height: int) -> list[float]:
    left, top, right, bottom = bounds
    crop_width, crop_height = right - left, bottom - top
    return [min(1.0, max(0.0, (left + box[0] * crop_width) / width)), min(1.0, max(0.0, (top + box[1] * crop_height) / height)), min(1.0, max(0.0, (left + box[2] * crop_width) / width)), min(1.0, max(0.0, (top + box[3] * crop_height) / height))]


def box_iou(a: list[float], b: list[float]) -> float:
    intersection = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union > 0 else 0.0


def point_inside(point: tuple[float, float], polygon: list[list[float]]) -> bool:
    x, y = point
    inside = False
    for index, (ax, ay) in enumerate(polygon):
        bx, by = polygon[(index + 1) % len(polygon)]
        cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax)
        if abs(cross) <= 1e-10 and min(ax, bx) - 1e-10 <= x <= max(ax, bx) + 1e-10 and min(ay, by) - 1e-10 <= y <= max(ay, by) + 1e-10:
            return True
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return inside


def associate(detections: list[dict], before: list[float], after: list[float], zone: list[list[float]]) -> tuple[list[dict], bool, int | None, str]:
    details, eligible = [], []
    for index, detection in enumerate(detections):
        bbox = detection["bbox"]
        before_iou, after_iou = box_iou(bbox, before), box_iou(bbox, after)
        inside = point_inside(((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2), zone)
        details.append({**detection, "iou_before": before_iou, "iou_after": after_iou, "inside_zone": inside})
        if detection["label"] == "boat" and before_iou >= ASSOCIATION_IOU and after_iou >= ASSOCIATION_IOU and inside:
            eligible.append((min(before_iou, after_iou), index))
    if not detections:
        return details, False, None, "no_detections"
    if not eligible:
        return details, False, None, "no_candidate_passed_geometry"
    eligible.sort(key=lambda item: (-item[0], item[1]))
    if len(eligible) > 1 and eligible[0][0] - eligible[1][0] < AMBIGUITY_MARGIN:
        return details, False, None, "ambiguous_candidates"
    return details, True, eligible[0][1], "geometric_candidate"


def load_case() -> dict:
    source_sha, model_sha = digest(SOURCE), digest(MODEL)
    if source_sha != EXPECTED_SOURCE_SHA:
        raise ValueError("Source video does not match the pinned case")
    lock = json.loads((ROOT / "vision/model.lock.json").read_text(encoding="utf-8"))
    if model_sha != EXPECTED_MODEL_SHA or model_sha != lock["sha256"]:
        raise ValueError("Model artifact does not match the pinned case")
    scene = json.loads(SCENE.read_text(encoding="utf-8"))
    if scene["id"] != "harbor" or scene["fps"] != 10 or scene["width"] != 960 or scene["height"] != 540:
        raise ValueError("Baseline scene dimensions or timing changed")
    track = next(track for track in scene["tracks"] if track["id"] == "T001")
    samples = {sample["frame"]: sample for sample in track["samples"]}
    if 123 not in samples or 131 not in samples or any(frame in samples for frame in FRAMES):
        raise ValueError("The fixed baseline gap is not present")
    before, after = samples[123], samples[131]
    if before["t"] != 12.3 or after["t"] != 13.1:
        raise ValueError("Baseline boundary timestamps changed")
    zone = next(zone for zone in scene["zones"] if zone["id"] == "A")
    return {"source_sha256": source_sha, "scene_sha256": digest(SCENE), "model_sha256": model_sha, "scene": scene, "before": before, "after": after, "zone": zone["polygon"], "frames": list(FRAMES), "roi": fixed_roi(before["bbox"], after["bbox"])}


def validate_output(output: Path) -> Path:
    if not output.is_absolute():
        raise ValueError("Output must be an absolute project work directory")
    resolved = output.resolve()
    work = (ROOT / "work").resolve()
    if not resolved.is_relative_to(work) or resolved == work:
        raise ValueError("Output must stay inside a project work subdirectory")
    if (resolved / "result.json").exists():
        raise ValueError("A completed review is immutable; use a new job directory")
    return resolved


def run(output: Path) -> dict:
    start = time.perf_counter()
    output = validate_output(output)
    output.mkdir(parents=True, exist_ok=True)
    stages_path = output / "stages.jsonl"

    def stage(name: str, completed: int) -> None:
        record = {"stage": name, "completed_frames": completed, "total_frames": len(FRAMES)}
        line = json.dumps(record, separators=(",", ":"))
        with stages_path.open("a", encoding="utf-8") as log:
            log.write(line + "\n")
        print(line, flush=True)

    stage("validating_source", 0)
    case = load_case()
    roi = case["roi"]
    width, height = case["scene"]["width"], case["scene"]["height"]
    bounds = crop_bounds(roi, width, height)
    for directory in [ROOT / "work/review-yolo/Ultralytics", ROOT / "work/review-mpl"]:
        directory.mkdir(parents=True, exist_ok=True)
    os.environ["YOLO_CONFIG_DIR"] = str(ROOT / "work/review-yolo")
    os.environ["MPLCONFIGDIR"] = str(ROOT / "work/review-mpl")
    os.environ["YOLO_OFFLINE"] = "true"
    stage("loading_model", 0)
    # Keep stdout machine-readable even if third-party libraries print startup notices.
    with contextlib.redirect_stdout(sys.stderr):
        import cv2
        import numpy as np
        import torch
        from ultralytics import YOLO
        torch.set_num_threads(4)
        torch.manual_seed(0)
        np.random.seed(0)
        model = YOLO(str(MODEL))
    cap = cv2.VideoCapture(str(SOURCE))
    if not cap.isOpened() or cap.get(cv2.CAP_PROP_FPS) != 10 or int(cap.get(3)) != width or int(cap.get(4)) != height:
        raise RuntimeError("Pinned video could not be decoded with expected timing/dimensions")
    result_frames, observations = [], []
    stage("reviewing_frames", 0)
    try:
        # Sequential decode fixes frame provenance; only the seven bounded frames run inference.
        for number in range(FRAMES[-1] + 1):
            ok, image = cap.read()
            if not ok:
                raise RuntimeError(f"Failed decoding fixed source frame {number}")
            if number not in FRAMES:
                continue
            if int(cap.get(cv2.CAP_PROP_POS_FRAMES)) != number + 1:
                raise RuntimeError("Video decoder position does not match requested frame")
            left, top, right, bottom = bounds
            crop = image[top:bottom, left:right].copy()
            original_name, crop_name, overlay_name = (f"{kind}-{number:04d}.jpg" for kind in ["original", "crop", "overlay"])
            for filename, pixels in [(original_name, image), (crop_name, crop)]:
                if not cv2.imwrite(str(output / filename), pixels, [cv2.IMWRITE_JPEG_QUALITY, 92]):
                    raise RuntimeError("Failed writing local review artifact")
            inference_start = time.perf_counter()
            with contextlib.redirect_stdout(sys.stderr):
                prediction = model.predict(crop, imgsz=960, conf=0.25, iou=0.5, classes=[8], device="cpu", verbose=False, save=False)[0]
            inference_ms = (time.perf_counter() - inference_start) * 1000
            detections = []
            for box, confidence, class_id in zip(prediction.boxes.xyxyn.tolist(), prediction.boxes.conf.tolist(), prediction.boxes.cls.tolist()):
                detections.append({"bbox": map_crop_box(box, bounds, width, height), "confidence": confidence, "label": model.names[int(class_id)]})
            details, accepted, selected, reason = associate(detections, case["before"]["bbox"], case["after"]["bbox"], case["zone"])
            overlay = image.copy()
            cv2.rectangle(overlay, (left, top), (right - 1, bottom - 1), (255, 255, 255), 1)
            zone_points = np.array([[round(x * width), round(y * height)] for x, y in case["zone"]], dtype=np.int32)
            cv2.polylines(overlay, [zone_points], True, (230, 160, 70), 1)
            for index, detection in enumerate(details):
                x1, y1, x2, y2 = [round(value * size) for value, size in zip(detection["bbox"], [width, height, width, height])]
                color = (60, 220, 80) if index == selected else (40, 180, 250)
                cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)
                cv2.putText(overlay, f"boat #{index} {detection['confidence']:.3f} IoU {detection['iou_before']:.2f}/{detection['iou_after']:.2f}", (max(0, x1), max(17, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 1, cv2.LINE_AA)
            cv2.putText(overlay, f"frame {number} / {number / 10:.1f}s: {reason}", (14, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.putText(overlay, "Geometric candidate only; identity / physical continuity unproven", (14, height - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.43, (255, 255, 255), 1, cv2.LINE_AA)
            if not cv2.imwrite(str(output / overlay_name), overlay, [cv2.IMWRITE_JPEG_QUALITY, 92]):
                raise RuntimeError("Failed writing review overlay")
            record = {"frame": number, "t": number / 10, "original_image": original_name, "crop_image": crop_name, "overlay_image": overlay_name, "roi": roi, "detections": details, "accepted": accepted, "selected_index": selected, "reason": reason, "inference_ms": round(inference_ms, 3)}
            result_frames.append(record)
            (output / f"detections-{number:04d}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if accepted and selected is not None:
                candidate = details[selected]
                observations.append({"frame": number, "t": number / 10, "bbox": candidate["bbox"], "confidence": candidate["confidence"], "source": "review", "association": "geometric_candidate"})
            stage("reviewing_frames", len(result_frames))
    finally:
        cap.release()
    if len(result_frames) != len(FRAMES):
        raise RuntimeError("Review did not produce all fixed frames")
    if digest(SOURCE) != case["source_sha256"] or digest(SCENE) != case["scene_sha256"] or digest(MODEL) != case["model_sha256"]:
        raise RuntimeError("Pinned inputs changed while review was running")
    stage("writing_result", len(FRAMES))
    result = {
        "case_id": "harbor-T001-gap", "strategy_id": "roi-recheck-v1", "source_sha256": case["source_sha256"], "scene_sha256": case["scene_sha256"], "model_sha256": case["model_sha256"],
        "config": {"imgsz": 960, "confidence": 0.25, "iou": 0.5, "classes": [8], "device": "cpu", "cpu_threads": 4, "frames": list(FRAMES), "roi": roi, "roi_pixel_bounds": list(bounds), "roi_effective": [bounds[0] / width, bounds[1] / height, bounds[2] / width, bounds[3] / height], "association_iou": ASSOCIATION_IOU, "ambiguity_margin": AMBIGUITY_MARGIN, "max_frames": 7, "fps": 10, "width": width, "height": height, "boundary_frames": [123, 131], "boundary_boxes": [case["before"]["bbox"], case["after"]["bbox"]], "ranking": "eligible candidates ranked by min(iou_before,iou_after); top-two difference <0.1 rejects", "versions": {"torch": torch.__version__, "ultralytics": __import__("ultralytics").__version__, "opencv": cv2.__version__}},
        "frames": result_frames, "observations": observations,
        "summary": {"reviewed_frames": len(result_frames), "accepted_frames": len(observations), "detected_frames": sum(bool(frame["detections"]) for frame in result_frames), "unresolved_frames": len(result_frames) - len(observations)},
        "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
        "limitations": ["唯一固定策略只复检这7个真实帧，没有调参、降低置信阈值或更换模型。", "接受观测仅为与两侧框一致的几何候选，不是T001同一身份或物理连续性证明。", "无检测、几何不合或歧义帧保留未解，不填补合成观测；不得仅凭容忍规则桥接就宣称完全连续。", "ROI在画面坐标中定义；本片有镜头运动，不是地理围栏。", "这是文本Agent可读取的结构化检测结果，不能声称语言模型已经直接看懂这些图片。"]
    }
    temporary = output / "result.json.tmp"
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, output / "result.json")
    stage("complete", len(FRAMES))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.output)
    except Exception as error:
        print(f"review failed: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
