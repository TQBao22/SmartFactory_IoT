# 🏭 Smart Factory IoT: AI-Powered Worker Monitoring System

## 📖 Tổng quan dự án (Overview)
Hệ thống **Smart Factory IoT** kết hợp Computer Vision và IoT để giám sát **mức sử dụng trạm làm việc** (workstation occupancy) theo thời gian thực. Camera tại biên phát hiện người trong từng vùng làm việc (zone), gửi sự kiện đổi trạng thái về máy chủ trung tâm qua MQTT. Máy chủ lưu sự kiện, gửi cảnh báo Telegram khi trạm trống quá lâu hoặc camera mất kết nối, và tính KPI theo ca.

Hệ thống tách **Edge Node** (camera AI tại xưởng) và **Central Server** (broker + xử lý trung tâm).

> ⚖️ Đây là hệ thống giám sát người lao động bằng camera. Khi triển khai thật cần thông báo và có sự đồng ý của người lao động theo Nghị định 13/2023/NĐ-CP về bảo vệ dữ liệu cá nhân.

---

## ✨ Tính năng (Features)
- 👁️ **Phát hiện người theo vùng**: YOLOv8 + OpenCV, nhiều zone trên một camera.
- ⏱️ **Máy trạng thái chống báo giả** (`zone_monitor.py`): cần có người liên tục ≥3s mới tính là có mặt (lọc người đi ngang); mất detection <2s (bị che, quay lưng) không làm mất trạng thái; trống ≥10s → cảnh báo, chỉ một lần cho mỗi lần vắng.
- 📡 **Sự kiện đầy đủ**: gửi `OCCUPIED`, `VACANT`, `ALERT` kèm thời điểm thật, cùng trạng thái camera `ONLINE`/`OFFLINE` (MQTT Last Will) — camera chết thì quản lý được báo, không im lặng.
- 🔒 **Private MQTT Broker**: Mosquitto với username/password, QoS 1, persistence; bí mật đọc từ `.env`, không nằm trong code.
- ⚡ **Cảnh báo Telegram** khi trạm trống quá ngưỡng hoặc camera mất kết nối.
- 📊 **KPI vận hành** (`kpi.py`): tỉ lệ có mặt, số lần vắng, thời gian vắng TB/max, số cảnh báo, thời gian phản hồi.
- 🧪 **Đánh giá độ chính xác** (`evaluate.py`): precision/recall/F1 của cảnh báo, báo giả/giờ, độ khớp trạng thái, tốc độ suy luận — trên video có nhãn gold.

---

## 🏗️ Kiến trúc Hệ thống (System Architecture)

```
Camera ─► vision_detector.py ─► ZoneMonitor ─► MQTT (QoS 1) ─► Mosquitto ─► mqtt_subscriber.py ─► SQLite (events)
                                                   │ LWT offline                    │                     │
                                                   ▼                                ▼                     ▼
                                           status/<camera_id>               Telegram (ALERT/OFFLINE)    kpi.py
```

### 1. Edge Node (`edge_node/`)
- `vision_detector.py`: đọc camera (`--source 0`) hoặc video mô phỏng (`--source file.mp4`), phát hiện người, cập nhật `ZoneMonitor`, gửi sự kiện. Hỗ trợ `--headless` cho Jetson/Raspberry Pi không màn hình.
- `zone_monitor.py`: máy trạng thái của từng zone, không phụ thuộc OpenCV (test offline được).
- `mqtt_publisher.py`: gửi sự kiện, tự kết nối lại, Last Will báo offline.
- `evaluate.py`, `eval_metrics.py`, `label_video.py`: đánh giá độ chính xác trên video có nhãn.

### 2. Central Server (`central_server/`, chạy bằng Docker)
- **Mosquitto**: broker MQTT có xác thực và persistence.
- `mqtt_subscriber.py`: kiểm tra bản tin, lưu bảng `events`, gửi Telegram.
- `kpi.py`: báo cáo KPI theo khoảng thời gian.

**Định dạng bản tin** (topic `smartfactory/vntt/line1/events`):
```json
{"camera_id": "Cam-01", "zone_id": "Zone_1", "event": "ALERT", "ts": 1764000000.0, "absent_s": 10.2}
```

---

## 🚀 Cài đặt & Vận hành (Getting Started)

### Bước 1: Cấu hình bí mật
```bash
cp .env.example .env      # điền MQTT_USER, MQTT_PASS, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
```
Token Telegram lấy từ @BotFather. **Không commit file `.env`.**

### Bước 2: Tạo tài khoản MQTT và khởi động server
```bash
docker run --rm -v "$PWD/mosquitto/config:/mosquitto/config" eclipse-mosquitto:2.0 \
  mosquitto_passwd -c -b /mosquitto/config/pwfile <MQTT_USER> <MQTT_PASS>
docker compose up -d --build
```
Dùng cùng `MQTT_USER`/`MQTT_PASS` như trong `.env`.

### Bước 3: Chạy Edge Node
```bash
python -m venv venv && venv\Scripts\activate        # Linux/Mac: source venv/bin/activate
pip install -r requirements.txt

Nạp biến môi trường từ `.env` (PowerShell, trong thư mục `SmartFactory_IoT`). Edge chạy trên máy khác thì sửa `MQTT_HOST` thành IP máy chủ:
```powershell
Get-Content .env | Where-Object { $_ -match '^[^#].*=' } | ForEach-Object { $k, $v = $_ -split '=', 2; Set-Item "env:$($k.Trim())" $v.Trim() }
```
Chạy:
```bash
cd edge_node
python vision_detector.py --source 0                                   # camera thật
python vision_detector.py --source test_video2.mp4                     # mô phỏng bằng video (phát đúng tốc độ thật)
python vision_detector.py --source test_video2.mp4 --headless --model ..\..\yolov8n.pt   # không màn hình
```
- Lần đầu chạy sẽ yêu cầu vẽ các zone; nhấn `r` để vẽ lại, `q` để thoát. Zone lưu ở `edge_node/roi_config.json` (camera) hoặc `<video>_roi.json` (video).
- `--headless` cần file zone có sẵn, nên chạy một lần có màn hình để vẽ zone trước.
- `--conf` (mặc định 0.4): ngưỡng tin cậy tính là có người; chọn lại bằng `evaluate.py`.

### Bước 4: Xem KPI
```bash
docker exec smartfactory_central_server python kpi.py --from "2026-11-24 08:00" --to "2026-11-24 17:00"
```

---

## 🧪 Kiểm thử & Đánh giá

```bash
python -m unittest discover -s tests          # test offline, không cần camera/broker
```

Đánh giá độ chính xác trên video:
1. Gán nhãn: `cd edge_node && python label_video.py --video test_video2.mp4 --split dev` — vẽ zone, khi xem video nhấn phím `1..9` lúc zone bắt đầu trống và nhấn lại khi có người quay lại.
2. Chạy: `python evaluate.py --append --note "mô tả thay đổi, máy chạy"` — kết quả thêm vào `eval/RESULTS.md`.
3. Dùng split `dev` để chọn ngưỡng/model; split `test` chỉ chạy một lần khi đã chốt cấu hình.

**Video tổng hợp** (kiểm tra logic cảnh báo, không cần quay):
```bash
python make_synthetic_video.py                 # tạo edge_node/synthetic_scenario.mp4 (180s) + nhãn split "synthetic"
python evaluate.py --split synthetic --append --note "..."
```
Kịch bản: vắng 20s (phải báo), bị che 1.5s (không báo), vắng 5s (không báo), vắng 40s có người đi ngang 2s (phải báo, không tính là có người). Video này chứng minh logic và thời gian cảnh báo đúng, **không** thay được video thật khi báo cáo độ chính xác.

> Video quay người thật: không commit lên repo công khai (dữ liệu cá nhân). Chỉ commit file nhãn `eval/labels/*.json`, lưu video ở nơi riêng (Drive, ổ nội bộ).

---

## 🩺 Xử lý lỗi thường gặp
| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| `no configuration file provided: not found` | Chạy `docker compose` sai thư mục | `cd SmartFactory_IoT` rồi chạy lại |
| Server không in "Đã kết nối", broker log `not authorised` | `MQTT_USER`/`MQTT_PASS` trong `.env` không khớp `pwfile` | Tạo lại `pwfile` (Bước 2) rồi `docker restart smartfactory_mqtt` |
| Edge in `Không kết nối được tới ...` | Sai `MQTT_HOST` hoặc broker chưa chạy | Kiểm tra `docker ps`, IP máy chủ, port 1883 |
| `Thiếu biến môi trường MQTT_USER / MQTT_PASS` | Chưa nạp `.env` vào phiên PowerShell | Chạy lệnh `Get-Content .env ...` ở Bước 3 |
| Chữ tiếng Việt lỗi `UnicodeEncodeError` khi chạy qua pipe | Console Windows không phải UTF-8 | `$env:PYTHONIOENCODING="utf-8"` |

---

## 📁 Cấu trúc Thư mục
```text
SmartFactory_IoT/
├── central_server/
│   ├── mqtt_subscriber.py   # Nhận, kiểm tra, lưu sự kiện, gửi Telegram
│   ├── database_handler.py  # SQLite (bảng events)
│   ├── kpi.py               # Báo cáo KPI
│   └── Dockerfile
├── edge_node/
│   ├── vision_detector.py   # Camera/video + YOLOv8 + gửi sự kiện
│   ├── zone_monitor.py      # Máy trạng thái zone
│   ├── mqtt_publisher.py
│   ├── evaluate.py, eval_metrics.py, label_video.py
│   ├── make_synthetic_video.py  # Tạo video kịch bản có nhãn sẵn
│   └── *.mp4                # Video test
├── eval/                    # labels/*.json (nhãn gold), RESULTS.md
├── tests/                   # unittest offline
├── mosquitto/config/
├── docker-compose.yml
└── .env.example
```

---

## 🛠️ Công nghệ
YOLOv8 (Ultralytics), OpenCV · MQTT (Eclipse Mosquitto, Paho) · Python 3, SQLite · Docker Compose · Telegram Bot API.
