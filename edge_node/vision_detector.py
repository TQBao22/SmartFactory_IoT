"""
vision_detector.py
Trạm giám sát biên (Edge Node): YOLOv8 phát hiện xe + ZoneMonitor theo từng chỗ đỗ, gửi sự kiện qua MQTT.

Chạy camera thật:   python vision_detector.py --source 0
Mô phỏng bằng video: python vision_detector.py --source bai_xe.mp4
Không có màn hình (Jetson/Pi): thêm --headless

Chỗ đỗ lưu dạng {"Slot_1": [x, y, w, h] hoặc [[x, y], [x, y], ...] (đa giác)}. Mặc định:
- camera: edge_node/roi_config.json
- video:  <tên_video>_roi.json (ROI gắn với từng cảnh quay)
"""

import argparse
import json
import os
import time
from datetime import datetime

import cv2
import numpy as np

from zone_monitor import ZoneMonitor, OCCUPIED, VACANT, ALERT

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
ROOT_DIR = os.path.dirname(PROJECT_DIR)

VEHICLE_CLASSES = [2, 3, 5, 7]  # COCO: car, motorcycle, bus, truck
# Chọn trên PKLot dev (eval/RESULTS_PKLOT.md): conf thấp vẫn giữ P ~0.997 vì bước gán chỗ đỗ lọc nhiễu.
DETECT_CONF = 0.05  # ngưỡng tin cậy tính là có xe
ZONE_IOU = 0.2      # IoU tối thiểu giữa bbox xe và chỗ đỗ
IMGSZ = 1280        # 640 bỏ sót xe ở xa (PUCPR recall 0.03 so với 0.65 ở 1280)
DETECT_EVERY_S = 1.0  # bãi đỗ đổi trạng thái chậm: suy luận 1 lần/giây là đủ, đủ thời gian cho ảnh 1280 trên CPU


def default_model_path(name="yolov8s.pt"):
    local = os.path.join(ROOT_DIR, name)
    return local if os.path.exists(local) else name  # ultralytics tự tải nếu không có file local


def load_model(path):
    from ultralytics import YOLO
    return YOLO(path)


def detect_vehicles(model, frame, imgsz=IMGSZ, conf=DETECT_CONF):
    """Trả về [(x1, y1, x2, y2, confidence)] cho các xe có độ tin cậy >= conf.

    Dùng predict, không dùng track: zone chỉ cần biết có xe hay không, không cần ID.
    """
    results = model.predict(frame, conf=conf, imgsz=imgsz, classes=VEHICLE_CLASSES, verbose=False)
    if not results or results[0].boxes is None:
        return []
    boxes = results[0].boxes
    return [(x1, y1, x2, y2, round(c, 2))
            for (x1, y1, x2, y2), c in zip(boxes.xyxy.int().cpu().tolist(), boxes.conf.cpu().tolist())]


def zone_polygon(zone):
    """[x, y, w, h] (từ cv2.selectROIs) hoặc [[x, y], ...] -> mảng điểm int32 của đa giác."""
    if not isinstance(zone[0], (list, tuple)):
        x, y, w, h = zone
        zone = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
    return np.array(zone, np.int32)


def zones_occupied(boxes, zones, min_iou=ZONE_IOU):
    """Mỗi xe chiếm tối đa một chỗ: chỗ có IoU(bbox, đa giác chỗ đỗ) lớn nhất, nếu >= min_iou.

    Camera nhìn xiên làm bbox xe lấn sang chỗ bên cạnh; xét tâm bbox hoặc chỉ phần giao sẽ đếm một xe cho hai chỗ.
    """
    masks = {}
    for z, zone in zones.items():
        pts = zone_polygon(zone)
        x, y, w, h = cv2.boundingRect(pts)
        mask = np.zeros((h, w), np.uint8)
        cv2.fillPoly(mask, [pts - (x, y)], 1)
        masks[z] = (x, y, mask, int(mask.sum()))
    occupied = {z: False for z in zones}
    for x1, y1, x2, y2, _ in boxes:
        best, best_iou = None, min_iou
        for z, (zx, zy, mask, area) in masks.items():
            inter = int(mask[max(y1 - zy, 0):max(y2 - zy, 0), max(x1 - zx, 0):max(x2 - zx, 0)].sum())
            if inter:
                iou = inter / ((x2 - x1) * (y2 - y1) + area - inter)
                if iou >= best_iou:
                    best, best_iou = z, iou
        if best is not None:
            occupied[best] = True
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
    zones = {f"Slot_{i + 1}": [int(v) for v in roi] for i, roi in enumerate(rois)}
    if not zones:
        raise SystemExit("[LỖI] Không có vùng nào được chọn.")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(zones, f, indent=4)
    print(f"[INFO] Đã lưu ROI vào {path}.")
    return zones


def draw(frame, boxes, zones, occupied, monitor, now):
    for x1, y1, x2, y2, conf in boxes:
        cv2.rectangle(frame, (x1, y1), (x2, y2), (200, 200, 200), 1)
        cv2.putText(frame, f"{conf:.2f}", (x1 + 2, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    states = monitor.states()
    for z, zone in zones.items():
        state, since = states[z]
        if state == OCCUPIED:
            parked = now - since
            color = (0, 0, 255) if parked >= monitor.alert_s else (0, 255, 255)
            text = f"{z}: {int(parked // 60)}p"
        elif state == VACANT and not occupied.get(z):
            color, text = (0, 255, 0), f"{z}: trong"
        else:
            color, text = (200, 200, 200), f"{z}: ..."
        pts = zone_polygon(zone)
        cv2.polylines(frame, [pts], True, color, 2)
        cv2.putText(frame, text, tuple(int(v) for v in pts.min(axis=0)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)


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
    ap.add_argument("--imgsz", type=int, default=IMGSZ)
    ap.add_argument("--every-s", type=float, default=DETECT_EVERY_S, help="khoảng cách giữa hai lần suy luận (giây)")
    ap.add_argument("--conf", type=float, default=DETECT_CONF, help="ngưỡng tin cậy tính là có xe (chọn bằng eval_pklot.py)")
    ap.add_argument("--iou", type=float, default=ZONE_IOU, help="IoU tối thiểu giữa xe và chỗ đỗ")
    ap.add_argument("--enter-s", type=float, default=10.0, help="xe đứng yên bao lâu thì tính là đỗ")
    ap.add_argument("--leave-s", type=float, default=10.0, help="mất xe bao lâu thì tính là đã rời")
    ap.add_argument("--alert-s", type=float, default=7200.0, help="đỗ quá bao lâu thì cảnh báo")
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
    monitor = ZoneMonitor(zones, args.enter_s, args.leave_s, args.alert_s, start=t0)
    frame_idx, boxes, occupied, last_detect = 0, [], {}, float("-inf")
    print(f"\n=== TRẠM GIÁM SÁT BIÊN: {len(zones)} chỗ đỗ, nguồn {args.source} ===  'q' thoát, 'r' vẽ lại ROI\n")

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

        if now - last_detect >= args.every_s:
            last_detect = now
            try:
                boxes = detect_vehicles(model, frame, imgsz=args.imgsz, conf=args.conf)
            except Exception as e:  # lỗi suy luận 1 khung hình không được dừng cả trạm
                print(f"[LỖI] Suy luận: {e}")
                boxes = []
            occupied = zones_occupied(boxes, zones, args.iou)
            for ev in monitor.update(occupied, now):
                publisher.publish_event(ev)
                print(f"[SỰ KIỆN] {ev}")
                if ev["event"] == ALERT:
                    fname = f"overstay_{ev['zone_id']}_{datetime.now():%Y%m%d_%H%M%S}.jpg"
                    cv2.imwrite(os.path.join(snapshot_dir, fname), frame)

        if args.headless:
            continue
        draw(frame, boxes, zones, occupied, monitor, now)
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
