import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "central_server"))
import mqtt_subscriber as sub  # noqa: E402
from database_handler import AlertDatabase  # noqa: E402

EV = sub.EVENTS_TOPIC
ST = "smartfactory/vntt/line1/status/Cam-01"


def msg(**kw):
    return json.dumps(kw).encode()


class ParseMessageTest(unittest.TestCase):
    def test_valid_alert(self):
        ev = sub.parse_message(EV, msg(camera_id="Cam-01", zone_id="Zone_1", event="ALERT", ts=100.0, absent_s=12.3))
        self.assertEqual(ev, {"camera_id": "Cam-01", "zone_id": "Zone_1", "event": "ALERT", "ts": 100.0, "absent_s": 12.3})

    def test_valid_status(self):
        ev = sub.parse_message(ST, msg(camera_id="Cam-01", event="OFFLINE", ts=5))
        self.assertEqual(ev["event"], "OFFLINE")
        self.assertNotIn("zone_id", ev)

    def test_rejects_bad_payloads(self):
        bad = [
            (EV, b"not json"),
            (EV, b"\xff\xfe"),
            (EV, b"[1, 2]"),
            (EV, msg(camera_id="Cam-01", zone_id="Zone_1", event="Worker_Missing_Zone_1", ts=1)),  # định dạng v1 cũ
            (EV, msg(camera_id="Cam-01", event="ALERT", ts=1)),                      # thiếu zone_id
            (EV, msg(camera_id="Cam-01", zone_id="Z", event="ALERT", ts="2026")),    # ts không phải số
            (EV, msg(camera_id="Cam-01", zone_id="Z", event="ALERT", ts=True)),
            (EV, msg(camera_id="x" * 65, zone_id="Z", event="ALERT", ts=1)),
            (ST, msg(camera_id="Cam-01", event="ALERT", ts=1)),                      # sai topic
            ("other/topic", msg(camera_id="Cam-01", zone_id="Z", event="ALERT", ts=1)),
        ]
        for topic, payload in bad:
            self.assertIsNone(sub.parse_message(topic, payload), payload)


class FormatAlertTest(unittest.TestCase):
    def test_escapes_html_from_edge(self):
        text = sub.format_alert({"camera_id": "<b>x</b>", "zone_id": "Z&1", "event": "ALERT", "ts": 0, "absent_s": 15})
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", text)
        self.assertIn("Z&amp;1", text)
        self.assertIn("15s", text)

    def test_only_alert_and_offline_notify(self):
        base = {"camera_id": "C", "zone_id": "Z", "ts": 0}
        self.assertIsNone(sub.format_alert({**base, "event": "OCCUPIED"}))
        self.assertIsNone(sub.format_alert({**base, "event": "ONLINE"}))
        self.assertIn("MẤT KẾT NỐI", sub.format_alert({**base, "event": "OFFLINE"}))


class DatabaseTest(unittest.TestCase):
    def test_insert_and_read_back(self):
        with tempfile.TemporaryDirectory() as d:
            db = AlertDatabase(os.path.join(d, "x.db"))
            self.assertTrue(db.insert_event({"camera_id": "C", "zone_id": "Z", "event": "VACANT", "ts": 1.0}, 1.5))
            row = db.conn.execute("SELECT ts, camera_id, zone_id, event, absent_s, received_at FROM events").fetchone()
            db.close()
        self.assertEqual(row, (1.0, "C", "Z", "VACANT", None, 1.5))


if __name__ == "__main__":
    unittest.main()
