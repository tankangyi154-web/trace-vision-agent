"""Only synthetic colored unit inputs; never used as release media."""
import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np
from process import draw, write_evidence_frame


class EvidenceTests(unittest.TestCase):
    def test_render_keeps_original_pixels_outside_real_object_annotations(self):
        frame=np.full((120,160,3),40,dtype=np.uint8)
        untouched=frame.copy()
        self.assertTrue(np.array_equal(draw(frame,[],160,120),frame))
        canvas=draw(frame,[{'id':'T001','label':'boat','confidence':.8,'bbox':[.3,.4,.6,.8]}],160,120)
        self.assertTrue(np.array_equal(frame,untouched), 'the original frame must remain unchanged')
        self.assertTrue(np.array_equal(canvas[100:],frame[100:]), 'no unrelated region tint or boundary is baked in')
        self.assertTupleEqual(tuple(canvas[48,48]),(70,225,235), 'the actual yellow detection box is retained')

    def test_new_run_replaces_old_frame_but_one_run_deduplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            first=np.zeros((8,8,3),dtype=np.uint8)
            second=np.full((8,8,3),255,dtype=np.uint8)
            run=set()
            filename=write_evidence_frame(directory,10,first,run)
            write_evidence_frame(directory,10,second,run)
            self.assertLess(cv2.imread(str(directory/filename)).mean(),10)
            write_evidence_frame(directory,10,second,set())
            self.assertGreater(cv2.imread(str(directory/filename)).mean(),245)


if __name__=='__main__': unittest.main()
