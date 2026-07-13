import json
import requests
import threading
import os
import paho.mqtt.client as mqtt
from database_handler import AlertDatabase

# Cấu hình Telegram
TELEGRAM_TOKEN = "8941449452:AAGBkSNRqmS3Avkw0mLZXojlbi1JgikVogM"
TELEGRAM_CHAT_ID = "8891749804"

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("[CẢNH BÁO] Cấu hình Telegram chưa đầy đủ. Hãy kiểm tra TELEGRAM_TOKEN và TELEGRAM_CHAT_ID.")

# Cấu hình MQTT
BROKER = "mqtt_broker"
PORT = 1883
TOPIC = "smartfactory/vntt/line1/alerts"

# Logic kết nối SQLite động
if os.path.exists("/.dockerenv"):
    db_path = "/app/logs/factory_alerts.db"
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, "logs", "factory_alerts.db")

# Khởi tạo đối tượng xử lý CSDL
db = AlertDatabase(db_path=db_path)

def send_telegram_alert(message):
    """
    Gửi tin nhắn cảnh báo qua Telegram.
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("[TELEGRAM] Đã gửi tin nhắn cảnh báo thành công!")
        else:
            print(f"[TELEGRAM LỖI] HTTP Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"[TELEGRAM LỖI] {e}")

def on_connect(client, userdata, flags, reason_code, properties=None):
    """
    Callback được gọi khi Client kết nối thành công tới Broker.
    """
    if reason_code == 0:
        print(f"[SERVER] Đã kết nối tới Broker {BROKER} thành công.")
        # Subscribe vào topic ngay khi kết nối thành công
        client.subscribe(TOPIC)
        print(f"[SERVER] Đang lắng nghe trên Topic: {TOPIC}")
    else:
        print(f"[SERVER] Kết nối thất bại, mã lỗi: {reason_code}")

def on_message(client, userdata, msg):
    """
    Callback được gọi khi có bản tin (message) mới gửi tới Topic đã Subscribe.
    """
    try:
        # Giải mã payload từ dạng byte sang chuỗi UTF-8
        payload_str = msg.payload.decode("utf-8")
        
        # Parse chuỗi JSON thành Dictionary
        data = json.loads(payload_str)
        
        # Trích xuất thông tin
        timestamp = data.get("timestamp", "N/A")
        camera_id = data.get("camera_id", "Unknown")
        alert_type = data.get("event_type", "N/A")
        
        # In thông báo đẹp mắt ra console
        print(f"\n" + "="*50)
        print(f"[SERVER] Nhận cảnh báo từ {camera_id}")
        print(f"Thời gian: {timestamp}")
        print(f"Sự kiện: {alert_type}")
        print("="*50)
        
        # Lưu dữ liệu vào SQLite
        db.insert_alert(timestamp, camera_id, alert_type)
        print("[DATABASE] Đã lưu bản ghi cảnh báo vào SQLite.")
        
        # Bắn cảnh báo Telegram nếu là Worker_Missing
        if alert_type == "Worker_Missing":
            zone_name = data.get("zone_name", camera_id)
            message = f"🚨 <b>CẢNH BÁO AN NINH NHÀ MÁY</b> 🚨\n\n⚠️ Trạng thái: Nhân viên vắng mặt!\n📍 Khu vực: {zone_name}\n🕒 Thời gian: {timestamp}"
            threading.Thread(target=send_telegram_alert, args=(message,), daemon=True).start()
            
    except json.JSONDecodeError:
        print(f"[SERVER LỖI] Không thể parse JSON. Nội dung nhận được: {msg.payload}")
    except Exception as e:
        print(f"[SERVER LỖI] Có lỗi xảy ra khi xử lý bản tin: {e}")

def main():
    """
    Hàm khởi chạy Máy chủ Trung tâm (Central Server).
    """
    print("=== MÁY CHỦ TRUNG TÂM (CENTRAL SERVER) ĐANG KHỞI ĐỘNG ===")
    
    # Khởi tạo MQTT Client (Tương thích v2.x)
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    
    # Thiết lập các hàm callback
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        # Kết nối tới Broker
        client.username_pw_set("admin", "admin123")
        client.connect(BROKER, PORT, keepalive=60)
        
        # Duy trì trạng thái lắng nghe liên tục 24/7
        print("[SERVER] Bắt đầu vòng lặp lắng nghe (loop_forever)...")
        client.loop_forever()
        
    except KeyboardInterrupt:
        print("\n[SERVER] Đang dừng máy chủ...")
    except Exception as e:
        print(f"[SERVER LỖI] Lỗi hệ thống: {e}")
    finally:
        db.close()
        print("[SERVER] Máy chủ đã dừng.")

if __name__ == "__main__":
    main()
