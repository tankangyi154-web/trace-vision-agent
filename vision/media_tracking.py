"""Keep classes separate and preserve the original high/low detection indices."""

def source_indices(source_rows,subset_rows):
    lookup={tuple(row):i for i,row in enumerate(source_rows)}
    return [lookup[tuple(row)] for row in subset_rows]

def create_trackers(classes,config,encoder=None):
    from types import SimpleNamespace
    from ultralytics.trackers.byte_tracker import BYTETracker

    class IndexedTracker(BYTETracker):
        def update(self,results,img=None,feats=None):
            self.source_rows=results.data.tolist()
            return super().update(results,img,feats)

        def init_track(self,results,img=None):
            tracks=super().init_track(results,img)
            # In pinned 8.3.231, init_track numbers each filtered confidence
            # subset from zero. That is not the original detector index.
            for track,index in zip(tracks,source_indices(self.source_rows,results.data.tolist())):track.idx=index
            return tracks

    trackers={}
    for cls in classes:
        if cls==0 and encoder is not None:
            import json
            from pathlib import Path
            from vision.appearance_tracker import AppearanceTracker
            policy=json.loads((Path(__file__).parent/'upload-tracking.json').read_text(encoding='utf8'))
            trackers[cls]=AppearanceTracker(SimpleNamespace(**config),encoder,policy)
        else:trackers[cls]=IndexedTracker(SimpleNamespace(**config),frame_rate=30)
    return trackers

def tracked_detections(trackers,detections,frame):
    indices=[];ids=[];classes=detections.cls.tolist()
    for cls,tracker in trackers.items():
        own=[i for i,value in enumerate(classes) if int(value)==cls]
        subset=detections[own]
        tracks=tracker.update(subset.cpu().numpy(),frame)
        for track in tracks:
            indices.append(own[int(track[-1])]);ids.append(f'{cls}:{int(track[4])}')
    if len(set(indices))!=len(indices):raise ValueError('processing')
    return detections[indices],ids
