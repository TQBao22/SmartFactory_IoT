import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "edge_node"))
from zone_monitor import ZoneMonitor  # noqa: E402


def run(monitor, timeline, step=0.1):
    """timeline: hàm t -> bool (zone Z có người?). Trả về danh sách sự kiện."""
    events, t = [], 0.0
    while t <= 60:
        events += monitor.update({"Z": timeline(t)}, round(t, 2))
        t += step
    return events


def kinds(events):
    return [e["event"] for e in events]


class ZoneMonitorTest(unittest.TestCase):
    def setUp(self):
        self.m = ZoneMonitor(["Z"], enter_s=3, leave_s=2, alert_s=10, start=0.0)

    def test_worker_present_with_dropouts_never_alerts(self):
        # Mất detection 1s mỗi 2.5s (bị che) — code cũ báo vắng sai sau ~10s.
        ev = run(self.m, lambda t: (t % 2.5) > 1.0)
        self.assertEqual(kinds(ev), ["OCCUPIED"])

    def test_empty_zone_alerts_once(self):
        ev = run(self.m, lambda t: False)
        self.assertEqual(kinds(ev), ["VACANT", "ALERT"])
        self.assertAlmostEqual(ev[1]["ts"], 10.0, places=1)

    def test_absence_timestamps_are_real_leave_and_arrive_times(self):
        # Có mặt 0-20s, vắng 20-40s, quay lại từ 40s.
        ev = run(self.m, lambda t: not (20 <= t < 40))
        self.assertEqual(kinds(ev), ["OCCUPIED", "VACANT", "ALERT", "OCCUPIED"])
        vac, alert, back = ev[1], ev[2], ev[3]
        self.assertAlmostEqual(vac["ts"], 20.0, delta=0.2)
        self.assertAlmostEqual(alert["ts"], 30.0, delta=0.2)
        self.assertAlmostEqual(back["ts"], 40.0, delta=0.2)

    def test_passer_by_does_not_reset_absence(self):
        # Vắng từ đầu, người đi ngang 1s ở giây 5 — vẫn phải báo động, không có OCCUPIED.
        ev = run(self.m, lambda t: 5 <= t < 6)
        self.assertNotIn("OCCUPIED", kinds(ev))
        self.assertIn("ALERT", kinds(ev))

    def test_flicker_after_alert_does_not_spam(self):
        # Sau khi báo động, người thoáng hiện 0.5s nhiều lần — code cũ gửi thêm cảnh báo mỗi lần.
        ev = run(self.m, lambda t: t > 15 and (t % 3) < 0.5)
        self.assertEqual(kinds(ev).count("ALERT"), 1)


if __name__ == "__main__":
    unittest.main()
