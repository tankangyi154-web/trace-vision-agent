"""Verify a completed review's frame provenance, geometry, artifacts and JSONL.

Does not run detection again or alter any result. Uses local source frames only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import review_gap as review


def validate(output: Path) -> dict:
    import cv2
    case = review.load_case()
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert not (output / "result.json.tmp").exists(), "Result did not finish atomic rename"
    for field in ["source_sha256", "scene_sha256", "model_sha256"]:
        assert result[field] == case[field], field
    assert result["case_id"] == "harbor-T001-gap"
    assert result["strategy_id"] == "roi-recheck-v1"
    config = result["config"]
    for field, value in {"imgsz": 960, "confidence": 0.25, "iou": 0.5, "classes": [8], "device": "cpu", "cpu_threads": 4, "frames": list(review.FRAMES), "association_iou": 0.2, "ambiguity_margin": 0.1, "max_frames": 7}.items():
        assert config[field] == value, field
    assert config["roi"] == case["roi"]
    assert config["roi_pixel_bounds"] == list(review.crop_bounds(case["roi"], 960, 540))
    assert [frame["frame"] for frame in result["frames"]] == list(review.FRAMES)
    stages = [json.loads(line) for line in (output / "stages.jsonl").read_text(encoding="utf-8").splitlines()]
    assert stages[0]["stage"] == "validating_source" and stages[-1]["stage"] == "complete"
    assert all(set(stage) == {"stage", "completed_frames", "total_frames"} and stage["total_frames"] == 7 for stage in stages)
    assert [stage["completed_frames"] for stage in stages if stage["stage"] == "reviewing_frames"] == list(range(8))
    assert all(stage["completed_frames"] <= stages[index + 1]["completed_frames"] for index, stage in enumerate(stages[:-1]))
    frames = {frame["frame"]: frame for frame in result["frames"]}
    observations = {observation["frame"]: observation for observation in result["observations"]}
    cap = cv2.VideoCapture(str(review.SOURCE))
    checked = 0
    try:
        for number in range(review.FRAMES[-1] + 1):
            ok, pixels = cap.read()
            assert ok, f"Source decode failed: {number}"
            if number not in frames:
                continue
            frame = frames[number]
            assert frame["t"] == number / 10 and frame["roi"] == case["roi"]
            assert int(cap.get(cv2.CAP_PROP_POS_FRAMES)) == number + 1
            left, top, right, bottom = config["roi_pixel_bounds"]
            # Byte-identical JPEG re-encoding proves images came from this exact decoded frame/crop.
            for field, expected_pixels in [("original_image", pixels), ("crop_image", pixels[top:bottom, left:right])]:
                relative = frame[field]
                assert relative == f"{'original' if field == 'original_image' else 'crop'}-{number:04d}.jpg"
                assert Path(relative).name == relative
                encoded_ok, encoded = cv2.imencode(".jpg", expected_pixels, [cv2.IMWRITE_JPEG_QUALITY, 92])
                assert encoded_ok and encoded.tobytes() == (output / relative).read_bytes(), field
            overlay = cv2.imread(str(output / frame["overlay_image"]))
            assert overlay is not None and overlay.shape == pixels.shape
            sidecar = json.loads((output / f"detections-{number:04d}.json").read_text(encoding="utf-8"))
            assert sidecar == frame
            details, accepted, selected, reason = review.associate(frame["detections"], case["before"]["bbox"], case["after"]["bbox"], case["zone"])
            assert details == frame["detections"]
            assert (accepted, selected, reason) == (frame["accepted"], frame["selected_index"], frame["reason"])
            assert frame["inference_ms"] > 0
            for detection in frame["detections"]:
                x1, y1, x2, y2 = detection["bbox"]
                assert 0 <= x1 <= x2 <= 1 and 0 <= y1 <= y2 <= 1
                assert detection["confidence"] >= 0.25 and detection["label"] == "boat"
            if accepted:
                observation = observations[number]
                assert observation["association"] == "geometric_candidate" and observation["source"] == "review"
                assert observation["bbox"] == frame["detections"][selected]["bbox"]
                assert observation["t"] == frame["t"]
            else:
                assert number not in observations
            checked += 1
    finally:
        cap.release()
    assert checked == 7
    expected_summary = {"reviewed_frames": 7, "accepted_frames": len(observations), "detected_frames": sum(bool(frame["detections"]) for frame in frames.values()), "unresolved_frames": 7 - len(observations)}
    assert result["summary"] == expected_summary
    assert review.digest(review.SOURCE) == case["source_sha256"] and review.digest(review.SCENE) == case["scene_sha256"]
    return {"status": "passed", "checked_frames": checked, "summary": expected_summary, "source_frames_and_crops": "byte-identical re-encoding", "geometry": "recomputed", "original_inputs": "unchanged"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(validate(args.output), ensure_ascii=False))
