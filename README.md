🏭 Smart Factory IoT: AI-Powered Worker Monitoring System

📖 Giới thiệu (Overview)

Đây là hệ thống IoT kết hợp Trí tuệ Nhân tạo (AI) dành cho Nhà máy Thông minh. Hệ thống sử dụng Computer Vision để giám sát sự hiện diện của công nhân tại các trạm làm việc (Workstations) và tự động gửi cảnh báo qua Telegram nếu phát hiện vắng mặt quá thời gian quy định.

Hệ thống được thiết kế theo chuẩn Kiến trúc Công nghiệp (OT) với tính bảo mật cao, tách biệt hoàn toàn giữa Edge Node (Camera AI) và Central Server (Máy chủ xử lý).

✨ Tính năng Nổi bật (Features)

AI Computer Vision: Ứng dụng YOLOv8/OpenCV nhận diện con người chính xác theo từng vùng (Zone).

Lọc nhiễu thông minh (Dwell Time): Loại bỏ báo động giả bằng cách yêu cầu đối tượng lưu trú trong vùng tối thiểu 3 giây mới được công nhận là đang làm việc.

Bảo mật tuyệt đối: Sử dụng Private MQTT Broker (Eclipse Mosquitto) với chứng thực Username/Password nội bộ.

DevOps Ready: Toàn bộ Central Server được đóng gói bằng Docker, tự động phục hồi (auto-healing) khi có sự cố.

Real-time Alerts: Cảnh báo tức thời qua Telegram Bot.

🏗️ Kiến trúc Hệ thống (Architecture)

Dự án được chia làm 2 khối chính giao tiếp qua giao thức MQTT:

Edge Node (Client):

Chạy các model AI ngay tại xưởng trên máy tính nhúng/PC.

Xử lý hình ảnh, áp dụng logic Dwell Time và gửi tín hiệu MQTT (QoS 1) về máy chủ.

Central Server (Backend):

Đóng gói hoàn toàn bằng Docker & Docker Compose.

Private MQTT Broker: Sử dụng Mosquitto chặn mọi truy cập ẩn danh.

Data Logger & Alerter: Lắng nghe tín hiệu, lưu trữ lịch sử vào SQLite và đẩy thông báo qua Telegram API.

🚀 Hướng dẫn Cài đặt & Vận hành (Getting Started)

1. Khởi động Máy chủ Trung tâm (Dockerized)

Đứng tại thư mục gốc của dự án và chạy lệnh sau để khởi động Server và MQTT Broker:

docker compose up -d --build


2. Thiết lập Bảo mật (MQTT Credentials)

Tạo mật khẩu cho MQTT Broker bằng lệnh sau (tạo tài khoản admin - pass admin123):

docker exec smartfactory_mqtt mosquitto_passwd -c -b /mosquitto/config/pwfile admin admin123
docker restart smartfactory_mqtt


3. Chạy Camera AI (Edge Node)

Trên máy tính trạm, cài đặt các thư viện cần thiết:

pip install opencv-python paho-mqtt ultralytics


Sau đó chạy module nhận diện:

python edge_node/vision_detector.py
