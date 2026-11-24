import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "edge_node"))
from eval_metrics import aggregate, score_zone  # noqa: E402


def e(ts, kind):
    return {"ts": ts, "event": kind}


class ScoreZoneTest(unittest.TestCase):
    def test_perfect_prediction(self):
        gold = [[20, 40]]
        events = [e(0, "OCCUPIED"), e(20, "VACANT"), e(30, "ALERT"), e(40, "OCCUPIED")]
        s = score_zone(gold, events, duration=60, alert_s=10)
        self.assertEqual((s["tp"], s["fp"], s["fn"]), (1, 0, 0))
        self.assertAlmostEqual(s["latencies"][0], 0.0)
        self.assertAlmostEqual(s["agree_s"], s["known_s"], places=5)

    def test_false_alarm_and_miss(self):
        gold = [[40, 55]]  # vắng thật 15s nhưng hệ thống không báo
        events = [e(0, "OCCUPIED"), e(5, "VACANT"), e(15, "ALERT"), e(20, "OCCUPIED")]  # báo giả lúc 15s
        s = score_zone(gold, events, duration=60, alert_s=10)
        self.assertEqual((s["tp"], s["fp"], s["fn"]), (0, 1, 1))

    def test_short_absence_is_not_required_to_alert(self):
        s = score_zone([[10, 15]], [e(0, "OCCUPIED")], duration=30, alert_s=10)
        self.assertEqual((s["tp"], s["fp"], s["fn"]), (0, 0, 0))

    def test_duplicate_alert_in_one_absence_is_false_alarm(self):
        events = [e(0, "VACANT"), e(10, "ALERT"), e(25, "ALERT")]
        s = score_zone([[0, 30]], events, duration=30, alert_s=10)
        self.assertEqual((s["tp"], s["fp"]), (1, 1))

    def test_unknown_period_excluded_from_occupancy(self):
        s = score_zone([], [e(3, "OCCUPIED")], duration=10, alert_s=10)
        self.assertAlmostEqual(s["known_s"], 7.0, places=5)


class AggregateTest(unittest.TestCase):
    def test_precision_recall_f1(self):
        z1 = score_zone([[20, 40]], [e(0, "OCCUPIED"), e(20, "VACANT"), e(31, "ALERT"), e(40, "OCCUPIED")], 60, 10)
        z2 = score_zone([[40, 55]], [e(0, "OCCUPIED"), e(5, "VACANT"), e(15, "ALERT"), e(20, "OCCUPIED")], 60, 10)
        a = aggregate([z1, z2])
        self.assertAlmostEqual(a["precision"], 0.5)
        self.assertAlmostEqual(a["recall"], 0.5)
        self.assertAlmostEqual(a["f1"], 0.5)
        self.assertAlmostEqual(a["latency_mean_s"], 1.0)
        self.assertAlmostEqual(a["false_alarms_per_zone_hour"], 1 / (120 / 3600))

    def test_no_alerts_no_absences(self):
        a = aggregate([score_zone([], [e(0, "OCCUPIED")], 30, 10)])
        self.assertIsNone(a["precision"])
        self.assertIsNone(a["f1"])
        self.assertAlmostEqual(a["occ_accuracy"], 1.0)

    def test_missed_everything_scores_zero(self):
        a = aggregate([score_zone([[0, 20]], [e(0, "OCCUPIED")], 30, 10)])
        self.assertIsNone(a["precision"])
        self.assertEqual(a["recall"], 0.0)
        self.assertEqual(a["f1"], 0.0)


if __name__ == "__main__":
    unittest.main()
