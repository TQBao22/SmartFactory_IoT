import json
from datetime import datetime
import paho.mqtt.client as mqtt

class MQTTAlertPublisher:
    """
    Lớp kết nối thực tế tới MQTT Broker trên Cloud để gửi các bản tin cảnh báo xâm nhập.
    Sử dụng Public Broker: broker.emqx.io:1883
    """
    def __init__(self, broker="127.0.0.1", port=1883, camera_id="Cam-01"):
        """
        Khởi tạo đối tượng MQTT Publisher và thiết lập kết nối tới Broker.
        
        Args:
            broker (str): Địa chỉ Public Broker. Mặc định là 'broker.emqx.io'.
            port (int): Cổng kết nối MQTT. Mặc định là 1883.
            camera_id (str): Định danh của camera. Mặc định là 'Cam-01'.
        """
        self.broker = broker
        self.port = port
        self.camera_id = camera_id
        self.topic = "smartfactory/vntt/line1/alerts"
        
        # Khởi tạo MQTT Client tương thích với cả paho-mqtt v1.x và v2.x
        try:
            # paho-mqtt v2.x yêu cầu chỉ định rõ CallbackAPIVersion
            self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        except AttributeError:
            # Hỗ trợ tương thích ngược cho paho-mqtt v1.x cũ hơn
            self.client = mqtt.Client()
            
        print(f"[MQTT] Đang kết nối tới Broker: {self.broker}:{self.port}...")
        
        try:
            self.client.username_pw_set("admin", "admin123")
            self.client.connect(self.broker, self.port, keepalive=60)
            # Khởi động luồng chạy ngầm để duy trì kết nối (keepalive) và xử lý dữ liệu truyền/nhận
            self.client.loop_start()
            print("[MQTT] Kết nối thành công và đã kích hoạt loop_start.")
        except Exception as e:
            print(f"[MQTT LỖI] Không thể kết nối tới Broker: {e}")

    def publish_alert(self, alert_type="Intrusion_Detected"):
        """
        Đóng gói thông tin cảnh báo thành JSON payload và gửi tới topic định nghĩa trên Broker.
        
        Args:
            alert_type (str): Loại cảnh báo sự kiện. Mặc định là 'Intrusion_Detected'.
        """
        # Lấy mốc thời gian hiện tại
        current_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Cấu trúc JSON payload
        payload = {
            "timestamp": current_timestamp,
            "camera_id": self.camera_id,
            "event_type": alert_type
        }
        
        # Chuyển đổi sang dạng chuỗi JSON UTF-8
        json_payload = json.dumps(payload, ensure_ascii=False)
        
        try:
            # Xuất bản bản tin lên Topic
            result = self.client.publish(self.topic, json_payload, qos=1)
            # Chờ bản tin được gửi đi thành công (đối với QoS 1)
            result.wait_for_publish(timeout=2.0)
            print("[MQTT] Đã gửi bản tin cảnh báo lên Cloud.")
        except Exception as e:
            print(f"[MQTT LỖI] Gửi bản tin thất bại: {e}")
            
        return json_payload

    def disconnect(self):
        """
        Hàm giải phóng tài nguyên và ngắt kết nối an toàn khi tắt ứng dụng.
        """
        self.client.loop_stop()
        self.client.disconnect()
        print("[MQTT] Đã ngắt kết nối an toàn.")


# Khối chạy thử nghiệm độc lập
if __name__ == "__main__":
    import time
    # Khởi tạo publisher kết nối tới Cloud Broker
    publisher = MQTTAlertPublisher()
    
    print("Gửi thử nghiệm bản tin cảnh báo lên Cloud...")
    publisher.publish_alert("Intrusion_Detected")
    
    # Chờ 1 giây để bảo đảm gói tin được truyền đi hoàn tất trước khi ngắt kết nối
    time.sleep(1)
    publisher.disconnect()
