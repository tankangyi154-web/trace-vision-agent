"""Explicit optional video ranges. All result times are relative to the selected clip."""
import math

def validate_scope(value,kind='video',limit=120):
    if value is None:return None
    if kind!='video' or not isinstance(value,dict) or set(value)!={'start_seconds','end_seconds'}:raise ValueError('segment')
    start,end=value['start_seconds'],value['end_seconds']
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in (start,end)) or not 0<=start<end<=limit:raise ValueError('segment')
    return {'start_seconds':float(start),'end_seconds':float(end)}

def resolve_scope(value,duration):
    value=validate_scope(value)
    start,end=(value['start_seconds'],value['end_seconds']) if value else (0.,duration)
    if start>=duration or end>duration+.05:raise ValueError('segment')
    end=min(end,duration)
    return {'start_seconds':start,'end_seconds':end,'source_duration_seconds':duration,
        'partial':start>0 or end<duration-.05,'time_origin':'selected_clip'}
