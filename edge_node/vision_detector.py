"""
vision_detector.py
Trạm giám sát biên (Edge Node): YOLOv8 phát hiện người + ZoneMonitor, gửi sự kiện zone qua MQTT.

Chạy camera thật:   python vision_detector.py --source 0
Mô phỏng bằng video: python vision_detector.py --source test_video2.mp4
Không có màn hình (Jetson/Pi): thêm --headless

ROI lưu dạng {"Zone_1": [x, y, w, h], ...}. Mặc định:
- camera: edge_node/roi_config.json
- video:  <tên_video>_roi.json (ROI gắn với từng cảnh quay)
"""

import argparse
import json
import os
import time
from datetime import datetime

import cv2

from zone_monitor import ZoneMonitor, OCCUPIED, VACANT, ALERT

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
ROOT_DIR = os.path.dirname(PROJECT_DIR)

PERSON_CLASS = 0
PERSON_CONF = 0.4   # ngưỡng tính là có người; 0.6 cũ loại người ngồi bị che (0.41-0.57). Chọn lại bằng evaluate.py
SKIP_FRAMES = 2     # suy luận 1/3 số khung hình


def default_model_path(name="yolov8s.pt"):
    local = os.path.join(ROOT_DIR, name)
    return local if os.path.exists(local) else name  # ultralytics tự tải nếu không có file local


def load_model(path):
    from ultralytics import YOLO
    return YOLO(path)


def detect_people(model, frame, imgsz=480, conf=PERSON_CONF):
    """Trả về [(x1, y1, x2, y2, confidence)] cho các người có độ tin cậy >= conf.

    Dùng predict, không dùng track: ByteTrack bỏ mất người ngồi bị bàn/màn hình che
    (test_video2: track 0/258 khung, predict 239/258). ID tracking không dùng cho logic zone.
    """
    results = model.predict(frame, conf=conf, imgsz=imgsz, classes=[PERSON_CLASS], verbose=False)
    if not results or results[0].boxes is None:
        return []
    boxes = results[0].boxes
    return [(x1, y1, x2, y2, round(c, 2))
            for (x1, y1, x2, y2), c in zip(boxes.xyxy.int().cpu().tolist(), boxes.conf.cpu().tolist())]


def zones_occupied(people, zones):
    """Zone có người nếu tâm bounding box nằm trong ROI [x, y, w, h]."""
    occupied = {z: False for z in zones}
    for x1, y1, x2, y2, _ in people:
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        for z, (zx, zy, zw, zh) in zones.items():
            if zx <= cx <= zx + zw and zy <= cy <= zy + zh:
                occupied[z] = True
    return occupied


def setup_rois(cap, path, force=False):
    if os.path.exists(path) and not force:
        with open(path, "r", encoding="utf-8") as f:
            print(f"[INFO] Đã load ROI từ {path}.")
            return json.load(f)

    ret, frame = cap.read()
    if not ret:
        raise SystemExit("[LỖI] Không đọc được khung hình để thiết lập ROI.")
    print("[INFO] Kéo thả để vẽ từng vùng, ENTER/SPACE để chốt 1 vùng, ESC để hoàn tất.")
    rois = cv2.selectROIs("Select ROIs", frame, showCrosshair=True, fromCenter=False)
    cv2.destroyWindow("Select ROIs")
    zones = {f"Zone_{i + 1}": [int(v) for v in roi] for i, roi in enumerate(rois)}
    if not zones:
        raise SystemExit("[LỖI] Không có vùng nào được chọn.")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(zones, f, indent=4)
    print(f"[INFO] Đã lưu ROI vào {path}.")
    return zones


def draw(frame, people, zones, occupied, monitor, now):
    for x1, y1, x2, y2, conf in people:
        cv2.rectangle(frame, (x1, y1), (x2, y2), (200, 200, 200), 1)
        cv2.putText(frame, f"{conf:.2f}", (x1 + 2, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    states = monitor.states()
    for z, (zx, zy, zw, zh) in zones.items():
        state, since = states[z]
        if state == OCCUPIED or occupied.get(z):
            color, text = (0, 255, 0), f"{z}: Co nguoi"
        elif state == VACANT:
            absent = now - since
            color = (0, 0, 255) if absent >= monitor.alert_s else (0, 255, 255)
            text = f"{z} Vang: {int(absent)}s"
        else:
            color, text = (200, 200, 200), f"{z}: ..."
        cv2.rectangle(frame, (zx, zy), (zx + zw, zy + zh), color, 2)
        cv2.putText(frame, text, (zx, zy - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)


def open_source(source):
    cap = cv2.VideoCapture(int(source) if source.isdigit() else source)
    if not cap.isOpened():
        raise SystemExit(f"[LỖI] Không mở được nguồn video: {source}")
    return cap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="0", help="chỉ số camera hoặc đường dẫn file video")
    ap.add_argument("--roi", help="file ROI json")
    ap.add_argument("--model", default=default_model_path())
    ap.add_argument("--camera-id", default="Cam-01")
    ap.add_argument("--imgsz", type=int, default=480)
    ap.add_argument("--conf", type=float, default=PERSON_CONF, help="ngưỡng tin cậy tính là có người (chọn bằng evaluate.py)")
    ap.add_argument("--headless", action="store_true", help="không hiển thị cửa sổ")
    args = ap.parse_args()

    from mqtt_publisher import MQTTAlertPublisher

    is_video = not args.source.isdigit()
    roi_path = args.roi or (os.path.splitext(args.source)[0] + "_roi.json" if is_video
                            else os.path.join(BASE_DIR, "roi_config.json"))
    if args.headless and not os.path.exists(roi_path):
        raise SystemExit(f"[LỖI] --headless cần file ROI có sẵn ({roi_path}); chạy một lần có màn hình để vẽ zone.")
    snapshot_dir = os.path.join(PROJECT_DIR, "snapshots")
    os.makedirs(snapshot_dir, exist_ok=True)

    model = load_model(args.model)
    publisher = MQTTAlertPublisher(camera_id=args.camera_id)
    cap = open_source(args.source)
    zones = setup_rois(cap, roi_path)

    # Video: dùng thời gian nội tại video (neo vào giờ thật lúc bắt đầu) để kết quả không phụ thuộc tốc độ máy.
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    t0 = time.time()
    monitor = ZoneMonitor(zones, start=t0)
    frame_idx, people, occupied = 0, [], {}
    print(f"\n=== TRẠM GIÁM SÁT BIÊN: {len(zones)} vùng, nguồn {args.source} ===  'q' thoát, 'r' vẽ lại ROI\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            if is_video:
                print("[INFO] Hết video.")
                break
            print("[LỖI] Mất tín hiệu camera, thử mở lại sau 2s...")
            cap.release()
            time.sleep(2)
            cap = cv2.VideoCapture(int(args.source))
            continue

        frame_idx += 1
        now = t0 + frame_idx / fps if is_video else time.time()
        if is_video and now > time.time():
            time.sleep(now - time.time())  # phát video đúng tốc độ thật để mô phỏng camera (timestamp không vượt giờ thật)

        if frame_idx % (SKIP_FRAMES + 1) == 0:
            try:
                people = detect_people(model, frame, imgsz=args.imgsz, conf=args.conf)
            except Exception as e:  # lỗi suy luận 1 khung hình không được dừng cả trạm
                print(f"[LỖI] Tracking: {e}")
                people = []
            occupied = zones_occupied(people, zones)
            for ev in monitor.update(occupied, now):
                publisher.publish_event(ev)
                print(f"[SỰ KIỆN] {ev}")
                if ev["event"] == ALERT:
                    fname = f"missing_{ev['zone_id']}_{datetime.now():%Y%m%d_%H%M%S}.jpg"
                    cv2.imwrite(os.path.join(snapshot_dir, fname), frame)

        if args.headless:
            continue
        draw(frame, people, zones, occupied, monitor, now)
        cv2.imshow("Giam sat Bien - SmartFactory", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("r"):
            zones = setup_rois(cap, roi_path, force=True)
            monitor.reset(zones, now)

    cap.release()
    publisher.disconnect()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
