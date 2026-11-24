"""Bản tin edge gửi phải qua được bước kiểm tra của server (lỗi lệch định dạng ở v1.0)."""
import os
import sys
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "edge_node"))
sys.path.insert(0, os.path.join(HERE, "..", "central_server"))
import mqtt_subscriber as sub  # noqa: E402
from mqtt_publisher import MQTTAlertPublisher  # noqa: E402
from zone_monitor import ZoneMonitor  # noqa: E402


class ContractTest(unittest.TestCase):
    def test_every_monitor_event_is_accepted_by_server(self):
        os.environ.update(MQTT_HOST="127.0.0.1", MQTT_PORT="1", MQTT_USER="u", MQTT_PASS="p")  # không có broker
        pub = MQTTAlertPublisher(camera_id="Cam-01")
        try:
            m = ZoneMonitor(["Zone_1"], enter_s=3, leave_s=2, alert_s=5, start=1000.0)
            events = []
            for i in range(400):  # có xe 0-10s, trống 10-30s, xe khác đến
                t = 1000.0 + i * 0.1
                events += m.update({"Zone_1": not (10 <= i * 0.1 < 30)}, t)
            self.assertEqual({e["event"] for e in events}, {"OCCUPIED", "VACANT", "ALERT"})
            for ev in events:
                parsed = sub.parse_message(pub.events_topic, pub.publish_event(ev).encode())
                self.assertIsNotNone(parsed, ev)
                self.assertEqual(parsed["zone_id"], "Zone_1")
            status = sub.parse_message(pub.status_topic, pub._status("offline").encode())
            self.assertEqual(status["event"], "OFFLINE")
        finally:
            pub.client.loop_stop()


if __name__ == "__main__":
    unittest.main()
