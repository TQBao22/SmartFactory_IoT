# 🚗 Smart Parking IoT: Giám sát chỗ đỗ xe bằng camera AI

## 📖 Tổng quan
Hệ thống theo dõi **từng chỗ đỗ ô tô** theo thời gian thực. Camera tại biên (edge) dùng YOLOv8 phát hiện xe, xác định chỗ nào có xe, chỗ nào trống, rồi gửi sự kiện về máy chủ trung tâm qua MQTT. Máy chủ lưu sự kiện, gửi cảnh báo Telegram khi **xe đỗ quá giờ** hoặc camera mất kết nối, và tính KPI của bãi: tỉ lệ lấp đầy, số lượt xe, thời gian đỗ.

Độ chính xác được đo trên bộ dữ liệu công khai **PKLot**: 12.417 ảnh, 3 bãi, trời nắng/mây/mưa, có nhãn theo từng chỗ đỗ.

> Dự án trước đây giám sát công nhân tại trạm làm việc, nay chuyển sang bãi đỗ xe. Lý do: dễ ứng dụng, có dữ liệu công khai để đánh giá, và gần như không xử lý dữ liệu cá nhân. Camera vẫn có thể quay được biển số và người đi bộ, nên không lưu và không gửi ảnh gốc: chỉ gửi trạng thái chỗ đỗ. Ảnh chụp lúc cảnh báo chỉ lưu tại máy edge.

---

## ✨ Tính năng
- 🅿️ **Nhận biết từng chỗ đỗ**: chỗ đỗ là hình chữ nhật hoặc đa giác. Mỗi xe được gán cho **một** chỗ có IoU lớn nhất, nên xe lấn vạch do camera nhìn xiên không bị đếm cho hai chỗ.
- ⏱️ **Máy trạng thái chống báo giả** (`zone_monitor.py`):
  - xe phải đứng yên ≥10s mới tính là đỗ, để lọc xe chạy ngang;
  - bị che <10s không làm mất trạng thái;
  - đỗ ≥2 giờ thì cảnh báo **đỗ quá giờ**, mỗi lượt đỗ một lần.
- 📡 **Sự kiện đầy đủ**: `OCCUPIED`, `VACANT`, `ALERT` kèm thời điểm thật, cùng trạng thái camera `ONLINE`/`OFFLINE` qua MQTT Last Will.
- 🔒 **MQTT riêng**: Mosquitto có username/password, QoS 1, persistence. Bí mật đọc từ `.env`.
- 📊 **KPI bãi đỗ** (`kpi.py`):
  - tỉ lệ lấp đầy;
  - số lượt xe;
  - thời gian đỗ trung bình và lâu nhất;
  - số lần quá giờ;
  - thời gian từ lúc cảnh báo đến khi xe rời đi.
- 🧪 **Đánh giá**:
  - `eval_pklot.py`: accuracy, P, R, F1 theo từng chỗ đỗ trên PKLot;
  - `evaluate.py`: cảnh báo theo thời gian trên video có nhãn.

---

## 🏗️ Kiến trúc

```
Camera ─► vision_detector.py ─► ZoneMonitor ─► MQTT (QoS 1) ─► Mosquitto ─► mqtt_subscriber.py ─► SQLite (events)
          (YOLO: xe, IoU chỗ đỗ)                │ LWT offline                    │                     │
                                               ▼                                ▼                     ▼
                                       status/<camera_id>          Telegram (quá giờ / OFFLINE)     kpi.py
```

**Định dạng bản tin**, topic `smartfactory/vntt/line1/events` (tên topic giữ nguyên từ phiên bản cũ):
```json
{"camera_id": "Cam-01", "zone_id": "Slot_12", "event": "ALERT", "ts": 1764000000.0, "duration_s": 7215.4}
```

---

## 🚀 Cài đặt & Vận hành

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
Dùng cùng `MQTT_USER`/`MQTT_PASS` như trong `.env`. Sự kiện lưu ở `logs/parking.db`.

### Bước 3: Chạy Edge Node
```bash
python -m venv venv && venv\Scripts\activate        # Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
```
Nạp biến môi trường từ `.env` (PowerShell, trong thư mục `SmartFactory_IoT`). Nếu edge chạy trên máy khác thì sửa `MQTT_HOST` thành IP máy chủ:
```powershell
Get-Content .env | Where-Object { $_ -match '^[^#].*=' } | ForEach-Object { $k, $v = $_ -split '=', 2; Set-Item "env:$($k.Trim())" $v.Trim() }
```
Chạy:
```bash
cd edge_node
python vision_detector.py --source 0                         # camera thật
python vision_detector.py --source bai_xe.mp4                # mô phỏng bằng video (phát đúng tốc độ thật)
python vision_detector.py --source bai_xe.mp4 --alert-s 60   # demo: cảnh báo sau 1 phút thay vì 2 giờ
```
- Lần đầu chạy sẽ yêu cầu vẽ các chỗ đỗ. Nhấn `r` để vẽ lại, `q` để thoát. Chỗ đỗ lưu ở `edge_node/roi_config.json` (camera) hoặc `<video>_roi.json` (video). Có thể sửa tay file này thành đa giác `[[x, y], ...]`.
- `--headless` cần file chỗ đỗ có sẵn.
- Tham số chính:
  - `--conf` (0.05), `--iou` (0.2), `--imgsz` (1280): chọn bằng `eval_pklot.py`;
  - `--every-s` (1): mỗi giây suy luận một lần (ảnh 1280 mất ~0.5s trên CPU);
  - `--enter-s` (10), `--leave-s` (10), `--alert-s` (7200): theo quy định của bãi.

### Bước 4: Xem KPI
```bash
docker exec smartfactory_central_server python kpi.py --from "2026-11-25 07:00" --to "2026-11-25 19:00"
```

---

## 🧪 Kiểm thử & Đánh giá

```bash
python -m unittest discover -s tests          # test offline, không cần camera/broker
```

### Độ chính xác trên PKLot (ảnh tĩnh)
1. Tải [PKLot](https://web.inf.ufpr.br/vri/?p=72) (4.6 GB, CC BY 4.0), rồi giải nén phần ảnh đầy đủ:
   ```bash
   tar -xzf PKLot.tar.gz --wildcards "PKLot/PKLot/*"
   ```
2. Dò ngưỡng trên split dev (ngày lẻ). Lệnh này suy luận một lần, rồi in F1 cho từng cặp conf × iou:
   ```bash
   cd edge_node
   python eval_pklot.py --root D:/datasets/PKLot/PKLot --grid
   ```
3. Ghi kết quả cấu hình đã chọn:
   ```bash
   python eval_pklot.py --root ... --conf 0.05 --iou 0.2 --append --note "mô tả, máy chạy"
   ```
   Kết quả được thêm vào `eval/RESULTS_PKLOT.md`.
4. Khi đã chốt cấu hình, chạy split test (ngày chẵn) **một lần**:
   ```bash
   python eval_pklot.py --root ... --split test --per-day 0 --append --note "chốt"
   ```

Trích dẫn khi dùng số liệu PKLot: Almeida, P. et al. *PKLot – A robust dataset for parking lot classification.* Expert Systems with Applications 42(11), 2015.

### Cảnh báo theo thời gian (video có nhãn)
1. Gán nhãn:
   ```bash
   python label_video.py --video bai_xe.mp4 --split dev
   ```
   Vẽ các chỗ đỗ. Video bắt đầu ở trạng thái tạm dừng. Nhấn phím `1..9` khi xe đỗ xong vào chỗ tương ứng, nhấn lại khi xe rời đi.
2. Chạy đánh giá:
   ```bash
   python evaluate.py --alert-s 60 --append --note "..."
   ```
   Video thường ngắn, nên rút ngưỡng quá giờ xuống để có cảnh báo mà chấm. Kết quả thêm vào `eval/RESULTS.md`.

> Không commit ảnh PKLot hay video quay bãi xe (có thể thấy biển số, người đi bộ). Chỉ commit file nhãn `eval/labels/*.json`.

---

## 🩺 Xử lý lỗi thường gặp
| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| `no configuration file provided: not found` | Chạy `docker compose` sai thư mục | `cd SmartFactory_IoT` rồi chạy lại |
| Server không in "Đã kết nối", broker log `not authorised` | `MQTT_USER`/`MQTT_PASS` trong `.env` không khớp `pwfile` | Tạo lại `pwfile` (Bước 2) rồi `docker restart smartfactory_mqtt` |
| Edge in `Không kết nối được tới ...` | Sai `MQTT_HOST` hoặc broker chưa chạy | Kiểm tra `docker ps`, IP máy chủ, port 1883 |
| `Thiếu biến môi trường MQTT_USER / MQTT_PASS` | Chưa nạp `.env` vào phiên PowerShell | Chạy lệnh `Get-Content .env ...` ở Bước 3 |
| Xe ở xa không được nhận | Ảnh thu nhỏ quá mức khi suy luận | Tăng `--imgsz` (960) hoặc giảm `--conf`, rồi đo lại bằng `eval_pklot.py` |
| Chữ tiếng Việt lỗi `UnicodeEncodeError` khi chạy qua pipe | Console Windows không phải UTF-8 | `$env:PYTHONIOENCODING="utf-8"` |

---

## 📁 Cấu trúc Thư mục
```text
SmartFactory_IoT/
├── central_server/
│   ├── mqtt_subscriber.py   # Nhận, kiểm tra, lưu sự kiện, gửi Telegram
│   ├── database_handler.py  # SQLite (bảng events)
│   ├── kpi.py               # KPI bãi đỗ
│   └── Dockerfile
├── edge_node/
│   ├── vision_detector.py   # Camera/video + YOLOv8 phát hiện xe + gán chỗ đỗ + gửi sự kiện
│   ├── zone_monitor.py      # Máy trạng thái chỗ đỗ (đỗ / trống / quá giờ)
│   ├── mqtt_publisher.py
│   ├── eval_pklot.py        # Đánh giá trên PKLot
│   └── evaluate.py, eval_metrics.py, label_video.py   # Đánh giá trên video có nhãn
├── eval/                    # labels/*.json, RESULTS.md, RESULTS_PKLOT.md
├── tests/                   # unittest offline
├── mosquitto/config/
├── docker-compose.yml
└── .env.example
```

---

## 🛠️ Công nghệ
YOLOv8 (Ultralytics), OpenCV · MQTT (Eclipse Mosquitto, Paho) · Python 3, SQLite · Docker Compose · Telegram Bot API · Dữ liệu đánh giá: PKLot (CC BY 4.0).
