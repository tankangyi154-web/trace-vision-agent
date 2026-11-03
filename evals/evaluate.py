"""Small, disclosed ROI spot-check of actual exported tracked detections.

No torch or online API dependency. Does not measure mAP/identity tracking quality.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def iou(a: list[float], b: list[float]) -> float:
    intersection = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    return intersection / (area_a + area_b - intersection) if area_a + area_b > intersection else 0.0


def in_roi(box: list[float], roi: list[float]) -> bool:
    x, y = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return roi[0] <= x <= roi[2] and roi[1] <= y <= roi[3]


def match(ground_truth: list[dict], predictions: list[dict], threshold: float) -> tuple[int, int, int]:
    candidates = sorted(((iou(g["bbox"], p["bbox"]), gi, pi) for gi, g in enumerate(ground_truth) for pi, p in enumerate(predictions) if g["label"] == p["label"]), reverse=True)
    used_g, used_p = set(), set()
    for score, gi, pi in candidates:
        if score >= threshold and gi not in used_g and pi not in used_p:
            used_g.add(gi)
            used_p.add(pi)
    return len(used_g), len(predictions) - len(used_p), len(ground_truth) - len(used_g)


def evaluate() -> dict:
    annotations = json.loads((ROOT / "evals/annotations.json").read_text(encoding="utf-8"))
    scenes = {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in (ROOT / "data/scenes").glob("*.json")}
    per_frame = []
    for frame in annotations["frames"]:
        scene = scenes[frame["scene_id"]]
        predictions = []
        for track in scene["tracks"]:
            if track["label"] not in frame["classes"]:
                continue
            for sample in track["samples"]:
                if sample["frame"] != frame["frame"]:
                    continue
                box = [round(value * size, 3) for value, size in zip(sample["bbox"], [scene["width"], scene["height"], scene["width"], scene["height"]])]
                if in_roi(box, frame["roi"]):
                    predictions.append({"label": track["label"], "track_id": track["id"], "bbox": box})
        ground_truth = [box for box in frame["boxes"] if in_roi(box["bbox"], frame["roi"])]
        tp, fp, fn = match(ground_truth, predictions, annotations["iou_threshold"])
        per_frame.append({"scene_id": frame["scene_id"], "frame": frame["frame"], "t": frame["t"], "ground_truth": len(ground_truth), "predictions": len(predictions), "true_positives": tp, "false_positives": fp, "false_negatives": fn, "predicted_boxes": predictions})
    per_scene = []
    for scene_id in scenes:
        records = [record for record in per_frame if record["scene_id"] == scene_id]
        totals = {key: sum(record[key] for record in records) for key in ["ground_truth", "predictions", "true_positives", "false_positives", "false_negatives"]}
        tp, fp, fn = (totals[key] for key in ["true_positives", "false_positives", "false_negatives"])
        per_scene.append({"scene_id": scene_id, "frames": len(records), **totals, "precision": round(tp / (tp + fp), 4) if tp + fp else None, "recall": round(tp / (tp + fn), 4) if tp + fn else None})
    tp, fp, fn = (sum(record[key] for record in per_frame) for key in ["true_positives", "false_positives", "false_negatives"])
    result = {
        "status": "measured",
        "title": "真实轨迹输出的开发抽检",
        "protocol": "6个预选帧；限定ROI与类别；目视标注框和实际导出跟踪框按同类IoU≥0.5贪心一对一匹配；开发代理辅助标注，尚未独立人工复核。",
        "dataset": {"scene_count": len(scenes), "frames_annotated": len(annotations["frames"]), "objects_annotated": sum(record["ground_truth"] for record in per_frame), "classes": ["boat", "car"], "sample_selection": annotations["selection"]},
        "metrics": [
            {"name": "ROI框定位精确率", "value": round(tp / (tp + fp), 4) if tp + fp else None, "unit": "ratio", "description": f"TP/(TP+FP)；TP={tp}, FP={fp}。仅代表这6帧的开发抽检。"},
            {"name": "ROI框定位召回率", "value": round(tp / (tp + fn), 4) if tp + fn else None, "unit": "ratio", "description": f"TP/(TP+FN)；TP={tp}, FN={fn}。不代表全场景准确率。"},
            {"name": "真实处理帧数", "value": sum(scene["processing"]["frame_count"] for scene in scenes.values()), "unit": "frames", "description": "本地实际解码、检测及跟踪帧数。"},
            {"name": "真实观测样本数", "value": sum(len(track["samples"]) for scene in scenes.values() for track in scene["tracks"]), "unit": "samples", "description": "至少3帧的轨迹内实际观测，无合成插值。"}
        ],
        "per_scene": per_scene,
        "per_frame": per_frame,
        "failures": [],
        "limitations": ["抽检仅6帧，ROI由开发阶段限定且未覆盖全部类别和小目标，不能推广为全视频或真实部署准确率。", "目视标注由开发代理辅助完成，尚未独立人工复核，不是正式金标准。", "未测mAP、IDF1、HOTA，不报告这些指标或性能提升。", "夜间低照度、运动模糊、远处小目标和相互遮挡会造成漏检和ID分裂。", "区域为画面坐标，镜头平移时不代表地理区域；无法推断真实速度、距离或违法结论。"],
        "configuration": {"model": "YOLO11n (COCO pretrained; no fine-tuning)", "tracker": "ByteTrack", "confidence": 0.25, "iou": 0.5, "imgsz": 640, "sample_fps": 10, "device": "cpu", "versions": next(iter(scenes.values()))["processing"]["versions"], "timing_by_scene": [{"scene_id": scene["id"], **{key: scene["processing"][key] for key in ["inference_ms_mean", "inference_ms_p50", "inference_ms_p95", "processing_wall_seconds"]}} for scene in scenes.values()]},
        "contributions": {"open_source": ["Ultralytics YOLO11n COCO预训练检测器（未重训）", "Ultralytics集成ByteTrack跟踪器", "LangGraph、Qwen和BM25基础方法"], "project": ["本地可复现视觉处理及契约导出", "区域/驻留/中断事件与可核查证据", "工具/RAG/有界Agent与成本控制", "响应式工作台、导出与开发抽检"]}
    }
    # Failures are derived from observed unmatched annotated objects, not invented examples.
    for record in per_frame:
        if record["false_negatives"] or record["false_positives"]:
            scene_id, frame_number = record["scene_id"], record["frame"]
            result["failures"].append({"id": f"spotcheck-{scene_id}-{frame_number}", "scene_id": scene_id, "t": record["t"], "image_url": f"/media/{scene_id}/evaluation/frame-{frame_number:04d}.jpg", "title": f"{scenes[scene_id]['title']} · {record['t']}秒", "description": f"此抽检帧有{record['false_negatives']}个未匹配标注框、{record['false_positives']}个未匹配输出框。绿色框为开发目视标注，黄色框为实际跟踪输出，白框为评测ROI；标注尚未独立人工复核。"})
    (ROOT / "evals/results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"frames": len(per_frame), "tp": tp, "fp": fp, "fn": fn, "per_scene": per_scene}, ensure_ascii=False, indent=2))
    return result


def render_frames() -> None:
    import cv2
    annotations = json.loads((ROOT / "evals/annotations.json").read_text(encoding="utf-8"))
    result = json.loads((ROOT / "evals/results.json").read_text(encoding="utf-8"))
    for annotation, record in zip(annotations["frames"], result["per_frame"]):
        scene_id = annotation["scene_id"]
        cap = cv2.VideoCapture(str(ROOT / f"web/public/media/{scene_id}/original.mp4"))
        cap.set(cv2.CAP_PROP_POS_FRAMES, annotation["frame"])
        ok, frame = cap.read()
        cap.release()
        if not ok:
            raise RuntimeError(f"Cannot decode evaluation frame {scene_id}:{annotation['frame']}")
        x1, y1, x2, y2 = annotation["roi"]
        cv2.rectangle(frame, (x1, y1), (x2 - 1, y2 - 1), (255, 255, 255), 1)
        for box in annotation["boxes"]:
            x1, y1, x2, y2 = map(round, box["bbox"])
            cv2.rectangle(frame, (x1, y1), (x2, y2), (80, 235, 70), 2)
            cv2.putText(frame, "reference " + box["label"], (x1, max(16, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (80, 235, 70), 1)
        for box in record["predicted_boxes"]:
            x1, y1, x2, y2 = map(round, box["bbox"])
            cv2.rectangle(frame, (x1, y1), (x2, y2), (40, 210, 250), 2)
            cv2.putText(frame, box["track_id"], (x1, min(frame.shape[0] - 4, y2 + 15)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (40, 210, 250), 1)
        output = ROOT / f"web/public/media/{scene_id}/evaluation"
        output.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output / f"frame-{annotation['frame']:04d}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 86])


if __name__ == "__main__":
    evaluate()
    render_frames()
