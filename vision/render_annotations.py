"""Rebuild demo annotation media from existing observations, without model inference.

Run with the prepared vision Python: python vision/render_annotations.py
Original videos, tracked observations, regions and evidence references are retained.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path

import cv2

from process import ROOT, draw, ffmpeg, publish_demo_cover


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def render_scene(path: Path, config: dict) -> dict:
    scene = json.loads(path.read_text(encoding='utf-8'))
    scene_id = scene['id']
    original = ROOT / 'web/public' / scene['original_url'].lstrip('/')
    original_sha = digest(original.read_bytes())
    assert original_sha == scene['processing']['output_sha256']
    facts = digest(json.dumps([scene['tracks'], scene['zones'], scene['evidence']], sort_keys=True).encode())
    directory = ROOT / 'work/annotation-render' / scene_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'evidence').mkdir(exist_ok=True)
    by_frame = defaultdict(list)
    for track in scene['tracks']:
        for sample in track['samples']:
            by_frame[sample['frame']].append({'id': track['id'], 'label': track['label'], **sample})
    shots = {round(item['t'] * scene['fps']): Path(item['image_url']).name for item in scene['evidence']}
    poster_frame = min(scene['processing']['frame_count'] - 1, round(config['poster_t'] * scene['fps']))
    cap = cv2.VideoCapture(str(original))
    writer = cv2.VideoWriter(str(directory / 'annotated.avi'), cv2.VideoWriter_fourcc(*'MJPG'), scene['fps'], (scene['width'], scene['height']))
    assert cap.isOpened() and writer.isOpened()
    try:
        for frame_number in range(scene['processing']['frame_count']):
            ok, frame = cap.read()
            assert ok, f'{scene_id}: could not decode frame {frame_number}'
            canvas = draw(frame, by_frame[frame_number], scene['width'], scene['height'])
            cv2.putText(canvas, f"{frame_number / scene['fps']:05.1f}s  YOLO11n + ByteTrack", (14, scene['height'] - 16), cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 1, cv2.LINE_AA)
            writer.write(canvas)
            if frame_number == poster_frame:
                assert cv2.imwrite(str(directory / 'poster.jpg'), canvas, [cv2.IMWRITE_JPEG_QUALITY, 86])
            if frame_number in shots:
                assert cv2.imwrite(str(directory / 'evidence' / shots[frame_number]), canvas, [cv2.IMWRITE_JPEG_QUALITY, 76])
        assert not cap.read()[0], f'{scene_id}: unexpected extra frames'
    finally:
        cap.release()
        writer.release()
    ffmpeg(['-i', str(directory / 'annotated.avi'), '-an', '-map_metadata', '-1', '-c:v', 'libx264', '-crf', '24', '-preset', 'medium', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(directory / 'annotated.mp4')])
    cap = cv2.VideoCapture(str(directory / 'annotated.mp4'))
    assert cap.isOpened() and int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == scene['processing']['frame_count']
    assert abs(cap.get(cv2.CAP_PROP_FPS) - scene['fps']) < 1e-5
    cap.release()
    # Replace only after a complete render. No inference or track reassignment occurs.
    assert original_sha == digest(original.read_bytes())
    assert facts == digest(json.dumps([scene['tracks'], scene['zones'], scene['evidence']], sort_keys=True).encode())
    target = original.parent
    for name in ('annotated.mp4', 'poster.jpg'):
        (directory / name).replace(target / name)
    publish_demo_cover(scene_id, target / 'poster.jpg')
    for name in shots.values():
        (directory / 'evidence' / name).replace(target / 'evidence' / name)
    scene['source']['modifications'] = scene['source']['modifications'].replace('示例区域及实际检测框', '实际检测框（统计区域由页面按需显示）')
    path.write_text(json.dumps(scene, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    return {'scene': scene_id, 'frames': scene['processing']['frame_count'], 'evidence_images': len(shots), 'original_sha256': original_sha, 'observation_contract_sha256': facts, 'model_inference': False}


if __name__ == '__main__':
    config = json.loads((ROOT / 'vision/demo-scenes.json').read_text(encoding='utf-8'))
    records = []
    for scene_id in ('harbor', 'crossing', 'night'):
        result = render_scene(ROOT / 'data/scenes' / f'{scene_id}.json', config[scene_id])
        records.append(result)
        print(json.dumps(result), flush=True)
    (ROOT / 'work/annotation-render/validation.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8')
