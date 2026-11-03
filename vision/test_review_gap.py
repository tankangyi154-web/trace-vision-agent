"""Focused regression tests for the fixed, local evidence-review worker."""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_gap as review


class CropAndAssociationTests(unittest.TestCase):
    def test_boundary_union_margin_is_clipped_and_pixel_mapping_uses_actual_crop(self):
        before = [0.092634, 0.434944, 0.893985, 0.748569]
        after = [0.0, 0.35357, 1.0, 0.850865]
        roi = review.fixed_roi(before, after)
        self.assertEqual(roi[0], 0)
        self.assertEqual(roi[2], 1)
        self.assertAlmostEqual(roi[1], 0.30357)
        self.assertAlmostEqual(roi[3], 0.900865)
        bounds = review.crop_bounds(roi, 960, 540)
        self.assertEqual(bounds, (0, 163, 960, 487))
        mapped = review.map_crop_box([0.25, 0.25, 0.75, 0.75], bounds, 960, 540)
        self.assertEqual(mapped[0], 0.25)
        self.assertEqual(mapped[2], 0.75)
        self.assertAlmostEqual(mapped[1], 244 / 540)
        self.assertAlmostEqual(mapped[3], 406 / 540)

    def test_candidate_must_overlap_both_sides_not_only_before(self):
        zone = [[0, 0], [1, 0], [1, 1], [0, 1]]
        detections = [{"bbox": [0, 0, 0.3, 0.3], "confidence": 0.9, "label": "boat"}]
        details, accepted, selected, reason = review.associate(detections, [0, 0, 0.3, 0.3], [0.7, 0.7, 1, 1], zone)
        self.assertFalse(accepted)
        self.assertIsNone(selected)
        self.assertEqual(reason, "no_candidate_passed_geometry")
        self.assertEqual(details[0]["iou_before"], 1)
        self.assertEqual(details[0]["iou_after"], 0)

    def test_matching_box_center_outside_zone_is_rejected(self):
        box = [0.5, 0.5, 1, 1]
        details, accepted, selected, _ = review.associate([{"bbox": box, "confidence": 0.9, "label": "boat"}], box, box, [[0, 0], [0.25, 0], [0.25, 0.25], [0, 0.25]])
        self.assertFalse(accepted)
        self.assertIsNone(selected)
        self.assertFalse(details[0]["inside_zone"])

    def test_two_close_geometric_candidates_are_ambiguous(self):
        box = [0.2, 0.2, 0.8, 0.8]
        detections = [{"bbox": box, "confidence": 0.9, "label": "boat"}, {"bbox": [0.21, 0.21, 0.79, 0.79], "confidence": 0.95, "label": "boat"}]
        _, accepted, selected, reason = review.associate(detections, box, box, [[0, 0], [1, 0], [1, 1], [0, 1]])
        self.assertFalse(accepted)
        self.assertIsNone(selected)
        self.assertEqual(reason, "ambiguous_candidates")

    def test_unique_valid_candidate_is_only_a_geometric_candidate(self):
        box = [0.2, 0.2, 0.8, 0.8]
        _, accepted, selected, reason = review.associate([{"bbox": box, "confidence": 0.9, "label": "boat"}], box, box, [[0, 0], [1, 0], [1, 1], [0, 1]])
        self.assertTrue(accepted)
        self.assertEqual(selected, 0)
        self.assertEqual(reason, "geometric_candidate")

    def test_no_detections_is_unresolved_and_zone_boundary_is_inside(self):
        _, accepted, selected, reason = review.associate([], [0, 0, 1, 1], [0, 0, 1, 1], [[0, 0], [1, 0], [1, 1], [0, 1]])
        self.assertFalse(accepted)
        self.assertIsNone(selected)
        self.assertEqual(reason, "no_detections")
        self.assertTrue(review.point_inside((1, 0.5), [[0, 0], [1, 0], [1, 1], [0, 1]]))


class FixedCaseTests(unittest.TestCase):
    def test_real_source_hash_and_gap_are_pinned(self):
        case = review.load_case()
        self.assertEqual(case["source_sha256"], "48acaf2024ca892a133c31b238742f8f76d6cef76188e33dc01904e15a600376")
        self.assertEqual(case["model_sha256"], "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1")
        self.assertEqual(case["frames"], [124, 125, 126, 127, 128, 129, 130])
        self.assertEqual(case["before"]["frame"], 123)
        self.assertEqual(case["after"]["frame"], 131)
        self.assertEqual(case["scene_sha256"], hashlib.sha256((review.ROOT / "data/scenes/harbor.json").read_bytes()).hexdigest())

    def test_output_must_be_absolute_and_inside_project_work(self):
        with self.assertRaises(ValueError):
            review.validate_output(Path("work/reviews/relative"))
        with self.assertRaises(ValueError):
            review.validate_output(review.ROOT / "web/public/review")


if __name__ == "__main__":
    unittest.main()
