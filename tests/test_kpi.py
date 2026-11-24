import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "central_server"))
from kpi import compute_kpis, format_table  # noqa: E402


def ev(ts, event, zone="Z", cam="C"):
    return {"ts": ts, "camera_id": cam, "zone_id": zone, "event": event}


class KpiTest(unittest.TestCase):
    def test_occupancy_absence_alert_response(self):
        events = [ev(0, "OCCUPIED"), ev(600, "VACANT"), ev(1200, "ALERT"), ev(1500, "OCCUPIED")]
        s = compute_kpis(events, 0, 3600)[("C", "Z")]
        self.assertEqual(s["occupied_s"], 600 + 2100)
        self.assertEqual(s["vacant_s"], 900)
        self.assertEqual(s["absences"], 1)
        self.assertEqual(s["absence_s"], [900])
        self.assertEqual(s["alerts"], 1)
        self.assertEqual(s["response_s"], [300])

    def test_window_clips_and_uses_state_from_before(self):
        # Vắng từ trước kỳ báo cáo, quay lại trong kỳ: thời gian vắng chỉ tính phần nằm trong kỳ.
        events = [ev(0, "VACANT"), ev(150, "OCCUPIED")]
        s = compute_kpis(events, 100, 200)[("C", "Z")]
        self.assertEqual(s["vacant_s"], 50)
        self.assertEqual(s["occupied_s"], 50)
        self.assertEqual(s["absences"], 0)  # bắt đầu vắng ngoài kỳ

    def test_offline_time_is_not_counted(self):
        events = [ev(0, "OCCUPIED"), {"ts": 100, "camera_id": "C", "zone_id": None, "event": "OFFLINE"},
                  {"ts": 500, "camera_id": "C", "zone_id": None, "event": "ONLINE"}, ev(503, "OCCUPIED")]
        s = compute_kpis(events, 0, 600)[("C", "Z")]
        self.assertEqual(s["occupied_s"], 100 + 97)
        self.assertEqual(s["vacant_s"], 0)

    def test_offline_only_affects_its_camera(self):
        events = [ev(0, "OCCUPIED", cam="A"), ev(0, "OCCUPIED", cam="B"),
                  {"ts": 50, "camera_id": "A", "zone_id": None, "event": "OFFLINE"}]
        out = compute_kpis(events, 0, 100)
        self.assertEqual(out[("A", "Z")]["occupied_s"], 50)
        self.assertEqual(out[("B", "Z")]["occupied_s"], 100)

    def test_table_renders(self):
        table = format_table(compute_kpis([ev(0, "OCCUPIED"), ev(1800, "VACANT")], 0, 3600))
        self.assertIn("50.0", table)  # có mặt 50%


if __name__ == "__main__":
    unittest.main()
