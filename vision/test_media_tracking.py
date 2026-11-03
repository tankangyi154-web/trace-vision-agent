"""Run in the vision environment: python -m unittest discover -s vision -p test_media_tracking.py."""
import os
from pathlib import Path
os.environ.setdefault('YOLO_CONFIG_DIR',str(Path(__file__).resolve().parents[1]/'work/tracking-tests'))
os.environ['YOLO_OFFLINE']='true'
import unittest
import numpy as np
from ultralytics.engine.results import Boxes
from vision.media_tracking import create_trackers,tracked_detections

class TrackingTests(unittest.TestCase):
    def appearance_tracker(self):
        class Encoder:
            meta=[]
            def __call__(self,img,boxes):
                assert len(self.meta)==len(boxes)
                return self.meta
        encoder=Encoder();config=dict(track_high_thresh=.25,track_low_thresh=.1,new_track_thresh=.25,track_buffer=10,match_thresh=.8,fuse_score=True)
        return create_trackers([0],config,encoder),encoder

    def meta(self,kind,occluded=False):
        vector=np.array([1,0] if kind=='red' else [0,1],dtype=np.float32)
        return dict(feature=vector,color=vector.copy(),reliable=True,occluded=occluded)

    def test_high_and_low_confidence_cannot_steal_a_differently_looking_persons_id(self):
        for confidence in [.9,.15]:
            with self.subTest(confidence=confidence):
                trackers,encoder=self.appearance_tracker();encoder.meta=[self.meta('red')]
                initial=Boxes(np.array([[10,10,20,30,.9,0]],dtype=np.float32),(100,100))
                _,old_ids=tracked_detections(trackers,initial,None)
                encoder.meta=[self.meta('blue')]
                replacement=Boxes(np.array([[10,10,20,30,confidence,0]],dtype=np.float32),(100,100))
                _,new_ids=tracked_detections(trackers,replacement,None)
                self.assertNotIn(old_ids[0],new_ids)

    def test_crossing_people_keep_their_appearance_ids_and_do_not_learn_mixed_crops(self):
        trackers,encoder=self.appearance_tracker();encoder.meta=[self.meta('red'),self.meta('blue')]
        first=Boxes(np.array([[10,10,18,30,.9,0],[26,10,34,30,.9,0]],dtype=np.float32),(100,100))
        _,original=tracked_detections(trackers,first,None)
        encoder.meta=[self.meta('red',True),self.meta('blue',True)]
        middle=Boxes(np.array([[18,10,26,30,.9,0],[22,10,30,30,.9,0]],dtype=np.float32),(100,100))
        visible,ids=tracked_detections(trackers,middle,None)
        self.assertEqual(ids,original)
        self.assertTrue(all(t.clean_updates==1 for t in trackers[0].tracked_stracks))
        encoder.meta=[self.meta('red'),self.meta('blue')]
        last=Boxes(np.array([[26,10,34,30,.9,0],[14,10,22,30,.9,0]],dtype=np.float32),(100,100))
        visible,ids=tracked_detections(trackers,last,None)
        self.assertEqual(ids,original)

    def test_an_ambiguous_merged_detection_cannot_claim_either_old_identity(self):
        trackers,encoder=self.appearance_tracker();encoder.meta=[self.meta('red'),self.meta('red')]
        first=Boxes(np.array([[10,10,18,30,.9,0],[26,10,34,30,.9,0]],dtype=np.float32),(100,100))
        _,original=tracked_detections(trackers,first,None)
        encoder.meta=[self.meta('red',True)]
        merged=Boxes(np.array([[18,10,26,30,.9,0]],dtype=np.float32),(100,100))
        _,new_ids=tracked_detections(trackers,merged,None)
        self.assertFalse(set(original)&set(new_ids))
        self.assertGreater(trackers[0].diagnostics['ambiguous_pairs'],0)

    def test_people_already_overlapping_at_first_sighting_remain_visible(self):
        trackers,encoder=self.appearance_tracker()
        def crowded_meta():
            return [dict(feature=np.eye(10,dtype=np.float32)[i],color=np.eye(10,dtype=np.float32)[i],reliable=True,occluded=True) for i in range(10)]
        encoder.meta=crowded_meta()
        boxes=np.array([[10+i*6,10,28+i*6,50,.9,0] for i in range(10)],dtype=np.float32)
        _,original=tracked_detections(trackers,Boxes(boxes,(100,100)),None)
        for step in range(1,5):
            moved=boxes.copy();moved[:,[0,2]]+=step
            encoder.meta=crowded_meta()
            visible,ids=tracked_detections(trackers,Boxes(moved,(100,100)),None)
            self.assertEqual(ids,original)
            self.assertEqual(len(visible),10)
            self.assertTrue(all(t.profile is None and t.clean_updates==0 for t in trackers[0].tracked_stracks))

    def test_new_overlapping_person_can_be_confirmed_but_not_reused_after_gap(self):
        trackers,encoder=self.appearance_tracker()
        empty=Boxes(np.empty((0,6),dtype=np.float32),(100,100))
        encoder.meta=[];tracked_detections(trackers,empty,None)
        boxes=Boxes(np.array([[10,10,25,50,.9,0]],dtype=np.float32),(100,100))
        encoder.meta=[self.meta('red',True)]
        self.assertEqual(tracked_detections(trackers,boxes,None)[1],[])
        encoder.meta=[self.meta('red',True)]
        _,ids=tracked_detections(trackers,boxes,None)
        self.assertEqual(len(ids),1)
        encoder.meta=[];tracked_detections(trackers,empty,None)
        encoder.meta=[self.meta('red',True)]
        _,after_gap=tracked_detections(trackers,boxes,None)
        self.assertFalse(set(ids)&set(after_gap))

    def test_overlapping_first_sighting_cannot_transfer_to_different_clothing(self):
        trackers,encoder=self.appearance_tracker()
        boxes=Boxes(np.array([[10,10,25,50,.9,0]],dtype=np.float32),(100,100))
        encoder.meta=[self.meta('red',True)]
        _,ids=tracked_detections(trackers,boxes,None)
        encoder.meta=[self.meta('blue',True)]
        _,new_ids=tracked_detections(trackers,boxes,None)
        self.assertFalse(set(ids)&set(new_ids))

    def test_reordered_weak_detection_keeps_current_box_and_does_not_duplicate_car(self):
        config=dict(track_high_thresh=.25,track_low_thresh=.1,new_track_thresh=.25,track_buffer=10,match_thresh=.8,fuse_score=True)
        trackers=create_trackers([0,2],config);frame=np.zeros((100,100,3),dtype=np.uint8)
        first=Boxes(np.array([[10,10,20,30,.9,0],[50,10,90,35,.9,2]],dtype=np.float32),(100,100))
        detections,ids=tracked_detections(trackers,first,frame)
        self.assertEqual(len(ids),2)
        # The low-confidence person is the SECOND input, but the FIRST item in
        # the weak subset. It must not draw the car at input zero.
        second=Boxes(np.array([[51,10,91,35,.9,2],[11,10,21,30,.15,0],[75,70,85,90,.15,0]],dtype=np.float32),(100,100))
        detections,ids=tracked_detections(trackers,second,frame)
        self.assertEqual(len(ids),2)
        self.assertEqual(len({tuple(r) for r in detections.xyxy.tolist()}),2)
        for ident,row in zip(ids,detections.data.tolist()):
            if ident.startswith('0:'):self.assertEqual(row[:4],[11,10,21,30]);self.assertEqual(row[-1],0)
            else:self.assertEqual(row[:4],[51,10,91,35]);self.assertEqual(row[-1],2)
        self.assertEqual(len(tracked_detections(trackers,Boxes(np.empty((0,6),dtype=np.float32),(100,100)),frame)[1]),0)

if __name__=='__main__':unittest.main()
