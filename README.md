# 🏭 Smart Factory IoT: AI-Powered Worker Monitoring System

## 📖 Tổng quan dự án (Overview)
Hệ thống **Smart Factory IoT** là một giải pháp kết hợp Trí tuệ Nhân tạo (AI) và Internet vạn vật (IoT) được thiết kế đặc biệt cho các nhà máy sản xuất. Hệ thống sử dụng Computer Vision (Thị giác máy tính) để giám sát sự hiện diện của công nhân tại các trạm làm việc (Workstations) theo thời gian thực. 
Nếu phát hiện công nhân vắng mặt hoặc rời vị trí quá thời gian quy định (Dwell Time logic), hệ thống sẽ tự động gửi cảnh báo qua ứng dụng Telegram để quản lý có thể can thiệp kịp thời.

Dự án được xây dựng tuân thủ tiêu chuẩn kiến trúc Công nghiệp (OT) với tính bảo mật cao, tách biệt rõ ràng giữa **Edge Node** (Thiết bị Camera AI tại biên) và **Central Server** (Máy chủ xử lý trung tâm).

---

## ✨ Tính năng Nổi bật (Key Features)
- 👁️ **AI Computer Vision**: Tích hợp mô hình YOLOv8 và OpenCV giúp nhận diện chính xác con người theo từng khu vực làm việc cụ thể (Zone-based detection).
- ⏱️ **Lọc nhiễu thông minh (Dwell Time Logic)**: Khắc phục tình trạng báo động giả bằng cách yêu cầu đối tượng phải xuất hiện liên tục trong vùng giám sát tối thiểu 3 giây mới được hệ thống ghi nhận là đang làm việc.
- 🔒 **Bảo mật tối đa (High Security)**: Triển khai Private MQTT Broker sử dụng Eclipse Mosquitto với cơ chế xác thực Username/Password nội bộ khép kín.
- 🐳 **DevOps Ready**: Toàn bộ hệ thống Backend (Central Server) được đóng gói gọn gàng bằng Docker & Docker Compose, hỗ trợ tính năng tự động phục hồi (Auto-healing) khi xảy ra sự cố nghẽn mạng hay crash ứng dụng.
- ⚡ **Real-time Alerts**: Tích hợp Telegram Bot API để đẩy thông báo và hình ảnh cảnh báo ngay tức thì đến các thiết bị di động của quản lý phân xưởng.

---

## 🏗️ Kiến trúc Hệ thống (System Architecture)

Hệ thống hoạt động theo mô hình Client-Server giao tiếp thông qua giao thức **MQTT (Message Queuing Telemetry Transport)**.

### 1. Edge Node (Client - Tại Phân xưởng)
- Được triển khai trên các máy tính công nghiệp nhúng (Jetson Nano, Raspberry Pi) hoặc PC tại xưởng.
- Chịu trách nhiệm chạy mô hình YOLOv8 xử lý luồng Video/Camera theo thời gian thực.
- Thực thi thuật toán Dwell Time và phân tích dữ liệu vùng (Zone).
- Gửi gói tin cảnh báo chuẩn MQTT (QoS 1) về máy chủ khi phát hiện bất thường.
- *Các tệp tin chính:* `vision_detector.py`, `mqtt_publisher.py`, `video_simulator.py`.

### 2. Central Server (Backend - Tại Phòng Máy/Cloud)
- Được thiết lập hoàn toàn tự động bằng Docker, đảm bảo tính nhất quán trên mọi môi trường.
- **Private MQTT Broker**: Container Mosquitto chịu trách nhiệm điều phối tin nhắn, có cơ chế cấu hình user/pass nghiêm ngặt.
- **Data Logger & Alerter**: Container ứng dụng Python `central_server` lắng nghe các topic MQTT, ghi log sự kiện vào cơ sở dữ liệu SQLite và kích hoạt gửi thông báo qua Telegram.
- *Các tệp tin chính:* `mqtt_subscriber.py`, `database_handler.py`, `Dockerfile`, `docker-compose.yml`.

---

## 🚀 Hướng dẫn Cài đặt & Vận hành (Getting Started)

### Yêu cầu hệ thống (Prerequisites)
- Docker và Docker Compose (dành cho Server).
- Python 3.8+ (dành cho Edge Node).
- Git.

### Bước 1: Khởi động Máy chủ Trung tâm (Dockerized)
Đứng tại thư mục gốc của dự án `SmartFactory_IoT` và chạy lệnh sau để khởi động Backend (MQTT Broker & Central Server DB Handler):
```bash
docker compose up -d --build
```
*Lệnh này sẽ tải các image cần thiết, build ứng dụng `central_server` và chạy ẩn dưới nền (detached mode).*

### Bước 2: Thiết lập Bảo mật cho MQTT Broker (MQTT Credentials)
Theo mặc định, Mosquitto Broker cần được cấu hình xác thực. Chạy lệnh sau để tạo một tài khoản MQTT (ví dụ: tạo tài khoản `admin` với mật khẩu là `admin123`):
```bash
docker exec -it smartfactory_mqtt mosquitto_passwd -c -b /mosquitto/config/pwfile admin admin123
```
Sau khi tạo tài khoản, tiến hành khởi động lại container MQTT để cập nhật thay đổi:
```bash
docker restart smartfactory_mqtt
```

### Bước 3: Cài đặt và Chạy Camera AI (Edge Node)
Mở một terminal mới (hoặc thực hiện trên máy tính trạm Edge Node). Bạn nên tạo môi trường ảo Python (Virtual Environment) trước khi cài đặt:
```bash
# Tạo và kích hoạt môi trường ảo (Tuỳ chọn nhưng khuyến nghị)
python -m venv venv
# Trên Linux/Mac: source venv/bin/activate
# Trên Windows: venv\Scripts\activate

# Cài đặt thư viện AI và MQTT
pip install opencv-python paho-mqtt ultralytics
```

Sau khi cài đặt xong, khởi chạy module nhận diện chính:
```bash
# Chạy script AI Vision
python edge_node/vision_detector.py
```
*(Nếu muốn chạy mô phỏng với video test, bạn có thể sử dụng `edge_node/video_simulator.py`)*

---

## 📁 Cấu trúc Thư mục (Directory Structure)
```text
SmartFactory_IoT/
├── central_server/          # Backend xử lý dữ liệu và gửi cảnh báo
│   ├── database_handler.py  # Xử lý tương tác với SQLite
│   ├── mqtt_subscriber.py   # Lắng nghe dữ liệu MQTT từ Edge
│   ├── Dockerfile           # Docker configuration cho backend
│   ├── requirements.txt
│   └── logs/                # Lưu trữ file database (.db)
├── edge_node/               # AI Edge xử lý Camera
│   ├── vision_detector.py   # Code nhận diện YOLOv8 + Dwell Time
│   ├── mqtt_publisher.py    # Gửi tín hiệu báo động
│   ├── video_simulator.py   # Script giả lập luồng video
│   └── *.mp4                # Các video test
├── mosquitto/               
│   └── config/              # Cấu hình bảo mật cho MQTT Broker
├── docker-compose.yml       # Tự động hóa triển khai Server
├── .gitignore               # Cấu hình bỏ qua file rác
└── README.md                # Tài liệu dự án (bạn đang đọc file này)
```

---

## 🛠️ Công nghệ Sử dụng (Tech Stack)
- **Computer Vision**: YOLOv8 (Ultralytics), OpenCV.
- **IoT Protocol**: MQTT (Eclipse Mosquitto, Eclipse Paho).
- **Backend**: Python 3, SQLite.
- **DevOps**: Docker, Docker Compose.
- **Notification**: Telegram Bot API.

---
*Phát triển bởi đội ngũ Kỹ sư Hệ thống Smart Factory.*
