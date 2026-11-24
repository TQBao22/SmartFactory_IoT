import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "edge_node"))
from eval_pklot import confusion, parse_pklot_xml, scores, split_of  # noqa: E402
from vision_detector import zones_occupied  # noqa: E402

# Hai chỗ đỗ cạnh nhau, mỗi chỗ 100x200.
SLOTS = {"A": [0, 0, 100, 200], "B": [[100, 0], [200, 0], [200, 200], [100, 200]]}


class ZonesOccupiedTest(unittest.TestCase):
    def test_car_spilling_into_neighbour_counts_once(self):
        # Xe ở chỗ A nhưng bbox lấn 30px sang B (camera nhìn xiên): chỉ A có xe.
        self.assertEqual(zones_occupied([(0, 0, 130, 200, 0.9)], SLOTS, 0.1), {"A": True, "B": False})

    def test_two_cars_two_slots(self):
        boxes = [(5, 5, 95, 195, 0.9), (105, 5, 195, 195, 0.8)]
        self.assertEqual(zones_occupied(boxes, SLOTS, 0.1), {"A": True, "B": True})

    def test_small_overlap_below_threshold_ignored(self):
        # Người/xe máy nhỏ ở mép chỗ A: IoU thấp, không tính là có xe.
        self.assertEqual(zones_occupied([(0, 0, 20, 20, 0.9)], SLOTS, 0.1), {"A": False, "B": False})


XML = """<?xml version="1.0"?>
<parking id="ufpr04">
  <space id="1" occupied="1"><contour><point x="0" y="0"/><point x="100" y="0"/><point x="100" y="200"/><point x="0" y="200"/></contour></space>
  <space id="2" occupied="0"><contour><point x="100" y="0"/><point x="200" y="0"/><point x="200" y="200"/><point x="100" y="200"/></contour></space>
  <space id="3"><contour><point x="200" y="0"/><point x="300" y="0"/><point x="300" y="200"/></contour></space>
</parking>"""


class PklotTest(unittest.TestCase):
    def test_parse_skips_unlabelled_space(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.xml")
            with open(path, "w") as f:
                f.write(XML)
            zones, gold = parse_pklot_xml(path)
        self.assertEqual(gold, {"Slot_1": True, "Slot_2": False})
        self.assertEqual(zones["Slot_2"][0], [100, 0])

    def test_split_by_day(self):
        self.assertEqual(split_of("2012-09-11"), "dev")
        self.assertEqual(split_of("2012-09-12"), "test")

    def test_confusion_and_scores(self):
        zones = {"Slot_1": SLOTS["A"], "Slot_2": SLOTS["B"]}
        gold = {"Slot_1": True, "Slot_2": False}
        boxes = [(5, 5, 95, 195, 0.9), (105, 5, 195, 195, 0.2)]  # xe thứ hai là phát hiện sai, conf thấp
        cm = confusion([("UFPR04", "Sunny", zones, gold, boxes)], conf=0.5, iou=0.1)
        self.assertEqual(cm["all"], [1, 0, 0, 1])
        self.assertEqual(scores(cm["all"])["acc"], 1.0)
        cm = confusion([("UFPR04", "Sunny", zones, gold, boxes)], conf=0.1, iou=0.1)
        self.assertEqual(cm["UFPR04"], [1, 1, 0, 0])


if __name__ == "__main__":
    unittest.main()
