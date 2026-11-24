import json
import os
import time
import paho.mqtt.client as mqtt

TOPIC_PREFIX = "smartfactory/vntt/line1"


class MQTTAlertPublisher:
    """
    Gửi sự kiện zone (OCCUPIED / VACANT / ALERT) và trạng thái online/offline của camera lên MQTT Broker.

    Cấu hình qua biến môi trường: MQTT_HOST (mặc định 127.0.0.1), MQTT_PORT (1883), MQTT_USER, MQTT_PASS.
    - Topic sự kiện: smartfactory/vntt/line1/events   (QoS 1)
    - Topic trạng thái: smartfactory/vntt/line1/status/<camera_id>  (retained, LWT = offline)
    """

    def __init__(self, camera_id="Cam-01"):
        self.camera_id = camera_id
        self.events_topic = f"{TOPIC_PREFIX}/events"
        self.status_topic = f"{TOPIC_PREFIX}/status/{camera_id}"
        host = os.environ.get("MQTT_HOST", "127.0.0.1")
        port = int(os.environ.get("MQTT_PORT", "1883"))
        user, password = os.environ.get("MQTT_USER"), os.environ.get("MQTT_PASS")
        if not user or not password:
            raise SystemExit("[MQTT LỖI] Thiếu biến môi trường MQTT_USER / MQTT_PASS.")

        try:
            # paho-mqtt v2.x yêu cầu chỉ định rõ CallbackAPIVersion
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"edge-{camera_id}")
        except AttributeError:
            # paho-mqtt v1.x
            self.client = mqtt.Client(client_id=f"edge-{camera_id}")

        self.client.username_pw_set(user, password)
        # Nếu edge chết / mất mạng, broker tự báo offline cho server.
        self.client.will_set(self.status_topic, self._status("offline"), qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_connect_fail = lambda client, userdata: print(f"[MQTT] Không kết nối được tới {host}:{port}, đang thử lại...")
        # connect_async + loop_start: tự kết nối lại khi broker chưa sẵn sàng hoặc rớt mạng.
        self.client.connect_async(host, port, keepalive=30)
        self.client.loop_start()
        print(f"[MQTT] Đang kết nối tới Broker: {host}:{port}...")

    def _status(self, status):
        return json.dumps({"camera_id": self.camera_id, "event": status.upper(), "ts": time.time()})

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            client.publish(self.status_topic, self._status("online"), qos=1, retain=True)
            print("[MQTT] Đã kết nối, camera ONLINE.")
        else:
            print(f"[MQTT LỖI] Kết nối thất bại: {reason_code}")

    def publish_event(self, event):
        """event: dict từ ZoneMonitor ({zone_id, event, ts, ...}). Không chặn vòng lặp video."""
        payload = json.dumps({"camera_id": self.camera_id, **event}, ensure_ascii=False)
        info = self.client.publish(self.events_topic, payload, qos=1)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            print(f"[MQTT] Chưa kết nối (rc={info.rc}), bản tin chờ gửi lại: {payload}")
        return payload

    def disconnect(self):
        # Ngắt kết nối chủ động không kích hoạt LWT, nên tự báo offline.
        try:
            self.client.publish(self.status_topic, self._status("offline"), qos=1, retain=True).wait_for_publish(2)
        except (RuntimeError, ValueError) as e:
            print(f"[MQTT] Không gửi được trạng thái offline: {e}")
        self.client.loop_stop()
        self.client.disconnect()
        print("[MQTT] Đã ngắt kết nối an toàn.")
