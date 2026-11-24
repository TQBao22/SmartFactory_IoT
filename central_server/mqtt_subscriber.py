import html
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import paho.mqtt.client as mqtt
import requests

from database_handler import AlertDatabase

# Bí mật và cấu hình đọc từ biến môi trường (file .env, xem .env.example). Không hardcode.
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
BROKER = os.environ.get("MQTT_HOST", "mqtt_broker")
PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASS = os.environ.get("MQTT_PASS", "")
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                 "logs", "parking.db"))
LOCAL_TZ = timezone(timedelta(hours=float(os.environ.get("TZ_OFFSET_HOURS", "7"))))

TOPIC_PREFIX = "smartfactory/vntt/line1"
EVENTS_TOPIC = f"{TOPIC_PREFIX}/events"
STATUS_TOPIC = f"{TOPIC_PREFIX}/status/+"
ZONE_EVENTS = {"OCCUPIED", "VACANT", "ALERT"}
STATUS_EVENTS = {"ONLINE", "OFFLINE"}

db = None


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_name(v):
    return isinstance(v, str) and 0 < len(v) <= 64


def parse_message(topic, payload):
    """Kiểm tra bản tin từ edge (dữ liệu không tin cậy). Hợp lệ -> dict, không hợp lệ -> None."""
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not _is_name(data.get("camera_id")) or not _is_number(data.get("ts")):
        return None
    ev = {"camera_id": data["camera_id"], "ts": float(data["ts"]), "event": data.get("event")}
    if topic == EVENTS_TOPIC:
        if ev["event"] not in ZONE_EVENTS or not _is_name(data.get("zone_id")):
            return None
        ev["zone_id"] = data["zone_id"]
        if _is_number(data.get("duration_s")):
            ev["duration_s"] = float(data["duration_s"])
    elif topic.startswith(f"{TOPIC_PREFIX}/status/"):
        if ev["event"] not in STATUS_EVENTS:
            return None
    else:
        return None
    return ev


def format_alert(ev):
    """Nội dung Telegram cho ALERT / OFFLINE, None nếu sự kiện không cần báo."""
    when = datetime.fromtimestamp(ev["ts"], LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")
    cam = html.escape(ev["camera_id"])
    if ev["event"] == "ALERT":
        zone = html.escape(ev["zone_id"])
        parked = f"{ev['duration_s'] / 60:.0f} phút" if "duration_s" in ev else "?"
        return (f"🚗 <b>XE ĐỖ QUÁ GIỜ</b>\n\n⏱️ Đã đỗ {parked}\n"
                f"📍 Chỗ đỗ: {zone} ({cam})\n🕒 Thời gian: {when}")
    if ev["event"] == "OFFLINE":
        return f"📴 <b>CAMERA MẤT KẾT NỐI</b>\n\n📷 {cam}\n🕒 Thời gian: {when}\nHệ thống KHÔNG giám sát các chỗ đỗ của camera này."
    return None


def send_telegram_alert(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TELEGRAM] Chưa cấu hình TELEGRAM_TOKEN / TELEGRAM_CHAT_ID, bỏ qua.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=10)
        print("[TELEGRAM] Đã gửi." if r.ok else f"[TELEGRAM LỖI] HTTP {r.status_code}: {r.text}")
    except requests.RequestException as e:
        print(f"[TELEGRAM LỖI] {e}")


def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        client.subscribe([(EVENTS_TOPIC, 1), (STATUS_TOPIC, 1)])
        print(f"[SERVER] Đã kết nối {BROKER}, lắng nghe {EVENTS_TOPIC} và {STATUS_TOPIC} (QoS 1).")
    else:
        print(f"[SERVER] Kết nối thất bại, mã lỗi: {reason_code}")


def on_connect_fail(client, userdata):
    print(f"[SERVER] Không kết nối được tới {BROKER}:{PORT}, đang thử lại...")


def on_message(client, userdata, msg):
    # Bản tin retained là trạng thái cũ gửi lại khi subscribe — đã xử lý trước đó, bỏ qua để không lưu/báo trùng.
    if msg.retain:
        return
    ev = parse_message(msg.topic, msg.payload)
    if ev is None:
        print(f"[SERVER] Bỏ qua bản tin không hợp lệ trên {msg.topic}: {msg.payload[:200]!r}")
        return
    print(f"[SERVER] {ev}")
    db.insert_event(ev, received_at=time.time())
    message = format_alert(ev)
    if message:
        threading.Thread(target=send_telegram_alert, args=(message,), daemon=True).start()


def main():
    global db
    print("=== MÁY CHỦ TRUNG TÂM (CENTRAL SERVER) ĐANG KHỞI ĐỘNG ===")
    if not MQTT_USER or not MQTT_PASS:
        raise SystemExit("[SERVER LỖI] Thiếu biến môi trường MQTT_USER / MQTT_PASS.")
    db = AlertDatabase(DB_PATH)

    # client_id cố định + clean_session=False: broker giữ bản tin QoS 1 khi server tạm tắt.
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="central-server", clean_session=False)
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect
    client.on_connect_fail = on_connect_fail
    client.on_message = on_message
    try:
        client.connect_async(BROKER, PORT, keepalive=60)
        client.loop_forever(retry_first_connection=True)
    except KeyboardInterrupt:
        print("\n[SERVER] Đang dừng máy chủ...")
    finally:
        db.close()


if __name__ == "__main__":
    main()
