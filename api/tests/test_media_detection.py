from types import SimpleNamespace
from vision.media_detection import MediaDetector,normalization_bounds


class Data:
    def __init__(self,rows):self.rows=rows
    def tolist(self):return self.rows


class Model:
    def __init__(self,rows):self.rows=rows;self.calls=[]
    def predict(self,frame,**options):
        self.calls.append(options)
        return [SimpleNamespace(boxes=SimpleNamespace(data=Data(self.rows)))]


LOCK=dict(detector_confidence=.1,image_confidence=.25,iou=.5,imgsz=960)


def test_short_high_resolution_video_retains_detail_without_upscaling_or_unbounding_long_uploads():
    assert normalization_bounds(3840,2160,14)==(1920,1080)
    assert normalization_bounds(2160,3840,14)==(1080,1920)
    assert normalization_bounds(3840,2160,31)==(1280,960)
    # The ffmpeg min(width,iw)/min(height,ih) guards against upscaling.


def test_dense_frames_get_more_detail_once_without_lowering_confidence_or_class_filter():
    model=Model([[0,0,20,50,.7,0] for _ in range(15)])
    detector=MediaDetector(model,LOCK,[0,24],'video',70,5)
    detector(None);detector(None)
    assert len(model.calls)==3 and detector.extra_passes==1 and detector.dense_frames==2
    assert model.calls[0]['imgsz']==960 and model.calls[-1]['imgsz']==1280
    assert model.calls[-1]['iou']==.65 and model.calls[-1]['max_det']==200
    assert all(c['conf']==.1 and c['classes']==[0,24] for c in model.calls)


def test_long_dense_video_keeps_bounded_inference_size_and_sparse_video_uses_one_pass():
    model=Model([[0,0,20,50,.7,0] for _ in range(15)])
    detector=MediaDetector(model,LOCK,[0],'video',600,5)
    detector(None)
    assert detector.dense and model.calls[-1]['imgsz']==960
    sparse=Model([[0,0,20,50,.7,0]])
    detector=MediaDetector(sparse,LOCK,[0],'video',70,5)
    detector(None)
    assert not detector.dense and len(sparse.calls)==1 and sparse.calls[0]['iou']==.5


def test_weak_candidates_alone_cannot_trigger_density_mode():
    model=Model([[0,0,20,50,.15,0] for _ in range(50)])
    detector=MediaDetector(model,LOCK,[0],'video',70,5)
    detector(None)
    assert not detector.dense and len(model.calls)==1
