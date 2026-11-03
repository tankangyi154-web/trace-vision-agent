"""Integrity-bound normalized media for retry; never accepts a path from a manifest."""
import hashlib
import json


def file_digest(path):
    with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()


def write_source_cache(directory,metadata):
    data={**metadata,'schema':1,'cache_sha256':file_digest(directory/metadata['cache_file'])}
    temp=directory/'source-cache.tmp'
    temp.write_text(json.dumps(data,ensure_ascii=False),encoding='utf8')
    temp.replace(directory/'source-cache.json')


def read_source_cache(directory,expected_source=None):
    try:
        data=json.loads((directory/'source-cache.json').read_text(encoding='utf8'))
        kind=data['kind'];name={'image':'analysis-source.png','video':'analysis-source.mp4'}[kind]
        if data['schema']!=1 or data['cache_file']!=name:raise ValueError('decode')
        if expected_source is not None and data['source_sha256']!=expected_source:raise ValueError('decode')
        if data['cache_sha256']!=file_digest(directory/name):raise ValueError('decode')
        # Dimensions/duration/frame grid are bounded again before model execution.
        from vision.analyze_media import validated_metadata,MAX_VIDEO_FRAMES,SAMPLE_FPS
        validated_metadata(data['width'],data['height'])
        if kind=='video':
            if data['sample_fps']!=SAMPLE_FPS or not 1<=data['processed_frames']<=MAX_VIDEO_FRAMES:raise ValueError('decode')
            validated_metadata(data['source_width'],data['source_height'],SAMPLE_FPS,data['duration']*SAMPLE_FPS,'video')
        return data
    except (OSError,KeyError,TypeError,ValueError) as error:
        raise ValueError('decode') from error
