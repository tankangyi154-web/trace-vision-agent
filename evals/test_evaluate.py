"""Small meaningful checks: one-to-one matching, class isolation, empty frames."""
import unittest
from evaluate import iou, match


class MatchTests(unittest.TestCase):
    def test_identical_boxes_have_iou_one(self):
        self.assertEqual(iou([0, 0, 10, 10], [0, 0, 10, 10]), 1)

    def test_duplicate_prediction_is_false_positive(self):
        box = {"label": "car", "bbox": [0, 0, 10, 10]}
        self.assertEqual(match([box], [box, box], 0.5), (1, 1, 0))

    def test_different_class_cannot_match(self):
        self.assertEqual(match([{"label": "boat", "bbox": [0, 0, 10, 10]}], [{"label": "car", "bbox": [0, 0, 10, 10]}], 0.5), (0, 1, 1))

    def test_empty_output_counts_missed_object(self):
        self.assertEqual(match([{"label": "car", "bbox": [0, 0, 10, 10]}], [], 0.5), (0, 0, 1))


if __name__ == "__main__":
    unittest.main()
