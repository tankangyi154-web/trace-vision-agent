"""Run with the existing vision runtime: python -m unittest vision.test_target_frames."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import cv2
import numpy as np
from vision.target_frames import make_cards,select_frames


class TargetFrameTests(unittest.TestCase):
    def test_selection_keeps_actual_times_and_prefers_clearer_views_within_each_period(self):
        rows=[{'t':t,'score':score} for t,score in [(0,1),(.2,10),(1,5),(1.2,20),(2,9),(2.2,30)]]
        self.assertEqual([r['t'] for r in select_frames(rows)],[.2,1.2,2.2])

    def test_body_prefers_a_complete_person_and_motion_keeps_both_ends(self):
        rows=[{'t':i,'score':10 if i==0 else 9 if i==2 else 8,'flags':['touching_frame_edge'] if i in (0,2,4) else [],'overlap':0} for i in range(6)]
        body=select_frames(rows,['body'])
        self.assertTrue(any(r['t'] in (1,3,5) for r in body))
        motion=select_frames(rows,['motion'])
        self.assertTrue(any(r['t']<=1 for r in motion));self.assertTrue(any(r['t']>=4 for r in motion))
        self.assertLessEqual(len(select_frames(rows,['body','motion','detail'])),3)

    def test_real_source_frames_produce_bounded_cards_and_hash_bound_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);frame=np.full((480,640,3),220,dtype=np.uint8)
            cv2.rectangle(frame,(200,80),(340,430),(20,30,200),-1)
            cv2.putText(frame,'real source',(80,45),cv2.FONT_HERSHEY_SIMPLEX,1,(0,0,0),2)
            source=directory/'analysis-source.png';self.assertTrue(cv2.imwrite(str(source),frame))
            box=[200/640,80/480,340/640,430/480]
            (directory/'result-r1.json').write_text(json.dumps({'kind':'image','sample_fps':0,'targets':[{'id':'7','samples':[{'t':0,'bbox':box,'confidence':.9}]}]}))
            digest=hashlib.sha256(source.read_bytes()).hexdigest()
            request=directory/'request.json';request.write_text(json.dumps({'target':'7','revision':1,'key':'test','cache_sha256':digest,'manifest':'manifest.json'}))
            make_cards(request)
            result=json.loads((directory/'manifest.json').read_text(encoding='utf8'));self.assertEqual(len(result['frames']),1)
            view=result['frames'][0];self.assertEqual(view['t'],0);self.assertEqual(view['bbox'],box)
            image=directory/view['image'];self.assertEqual(cv2.imread(str(image)).shape[:2],(600,1024))
            self.assertEqual(hashlib.sha256(image.read_bytes()).hexdigest(),view['sha256'])
            request.write_text(json.dumps({'target':'7','revision':1,'key':'test','cache_sha256':'wrong','manifest':'manifest.json'}))
            with self.assertRaises(ValueError):make_cards(request)


if __name__=='__main__':unittest.main()
