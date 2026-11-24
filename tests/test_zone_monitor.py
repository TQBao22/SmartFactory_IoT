import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "edge_node"))
from zone_monitor import ZoneMonitor  # noqa: E402


def run(monitor, timeline, step=0.1):
    """timeline: hàm t -> bool (chỗ đỗ Z có xe?). Trả về danh sách sự kiện."""
    events, t = [], 0.0
    while t <= 60:
        events += monitor.update({"Z": timeline(t)}, round(t, 2))
        t += step
    return events


def kinds(events):
    return [e["event"] for e in events]


class ZoneMonitorTest(unittest.TestCase):
    def setUp(self):
        # Thời gian thu nhỏ để test nhanh: vào 3s, rời 2s, đỗ quá giờ 10s.
        self.m = ZoneMonitor(["Z"], enter_s=3, leave_s=2, alert_s=10, start=0.0)

    def test_parked_car_with_occlusions_alerts_once(self):
        # Xe đỗ suốt, bị xe khác che 1s mỗi 2.5s: không được thành VACANT, báo quá giờ đúng một lần.
        ev = run(self.m, lambda t: (t % 2.5) > 1.0)
        self.assertEqual(kinds(ev), ["OCCUPIED", "ALERT"])

    def test_empty_slot_never_alerts(self):
        ev = run(self.m, lambda t: False)
        self.assertEqual(kinds(ev), ["VACANT"])

    def test_timestamps_are_real_arrive_and_leave_times(self):
        # Trống 0-20s, xe đỗ 20-40s, rời từ 40s.
        ev = run(self.m, lambda t: 20 <= t < 40)
        self.assertEqual(kinds(ev), ["VACANT", "OCCUPIED", "ALERT", "VACANT"])
        arrive, alert, leave = ev[1], ev[2], ev[3]
        self.assertAlmostEqual(arrive["ts"], 20.0, delta=0.2)
        self.assertAlmostEqual(alert["ts"], 30.0, delta=0.2)
        self.assertAlmostEqual(alert["duration_s"], 10.0, delta=0.2)
        self.assertAlmostEqual(leave["ts"], 40.0, delta=0.2)

    def test_passing_car_is_not_parking(self):
        # Xe chạy ngang 1s ở giây 5: không có OCCUPIED, không cảnh báo.
        ev = run(self.m, lambda t: 5 <= t < 6)
        self.assertEqual(kinds(ev), ["VACANT"])

    def test_new_car_gets_its_own_alert(self):
        # Hai lượt đỗ 0-15s và 25-45s: mỗi lượt một cảnh báo, tính giờ lại từ lúc xe thứ hai đến.
        ev = run(self.m, lambda t: t < 15 or 25 <= t < 45)
        alerts = [e for e in ev if e["event"] == "ALERT"]
        self.assertEqual(len(alerts), 2)
        self.assertAlmostEqual(alerts[1]["ts"], 35.0, delta=0.2)


if __name__ == "__main__":
    unittest.main()
