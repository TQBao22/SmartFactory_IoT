"""
vision_detector.py
Giám sát camera thật (Real-time) tại trạm biên (Edge Node).
Sử dụng Multi-Object Tracking (YOLOv8) với logic Zone-Centric: giám sát vùng làm việc,
cảnh báo khi KHÔNG CÒN AI trong vùng ROI.
Tối ưu hóa: Bỏ qua khung hình (Frame Skipping) và giảm kích thước ảnh đầu vào (imgsz=480).
"""

import cv2
import time
import os
import json
from datetime import datetime
from mqtt_publisher import MQTTAlertPublisher
from ultralytics import YOLO

# Đường dẫn tuyệt đối
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
ROOT_DIR = os.path.dirname(PROJECT_DIR)

ROI_CONFIG_FILE = "roi_config.json"

# Khởi tạo mô hình nhẹ YOLOv8s để chạy mượt trên webcam
model = YOLO(os.path.join(ROOT_DIR, 'yolov8s.pt'))

def setup_rois(cap):
    if os.path.exists(ROI_CONFIG_FILE):
        with open(ROI_CONFIG_FILE, "r") as f:
            workzones = json.load(f)
        print("[INFO] Đã load cấu hình ROI từ file.")
        return workzones
        
    ret, frame = cap.read()
    if not ret:
        print("[LỖI] Không thể đọc frame để thiết lập ROI.")
        return {}
        
    print("[INFO] Vui lòng vẽ các vùng ROI, sau đó nhấn ENTER (hoặc SPACE).")
    rois = cv2.selectROIs("Select ROIs", frame, showCrosshair=True, fromCenter=False)
    cv2.destroyWindow("Select ROIs")
    
    workzones = {}
    for i, roi in enumerate(rois):
        workzones[f"Zone_{i+1}"] = [int(roi[0]), int(roi[1]), int(roi[2]), int(roi[3])]
        
    with open(ROI_CONFIG_FILE, "w") as f:
        json.dump(workzones, f, indent=4)
    print("[INFO] Đã lưu cấu hình ROI mới.")
    return workzones

def main():
    publisher = MQTTAlertPublisher()

    SNAPSHOT_DIR = os.path.join(PROJECT_DIR, "snapshots")
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)

    # Mở camera mặc định
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[LỖI] Không thể mở camera mặc định.")
        return

    WORKZONES = setup_rois(cap)

    # Biến trạng thái giám sát vùng
    MISSING_THRESHOLD = 10.0
    DWELL_THRESHOLD = 3
    last_seen_times = {zone: time.time() for zone in WORKZONES}
    zone_dwell_trackers = {}
    is_alerted = {zone: False for zone in WORKZONES}
    worker_in_zone = {zone: False for zone in WORKZONES}

    # Cấu hình Frame Skipping
    frame_count = 0
    SKIP_FRAMES = 2
    latest_detections = []
    cached_worker_in_zone = {zone: False for zone in WORKZONES}

    print("\n=== TRẠM GIÁM SÁT BIÊN (ZONE-CENTRIC TRACKING - TỐI ƯU HÓA) ĐÃ KHỞI ĐỘNG ===")
    print("Nhấn 'q' để thoát, 'r' để reset ROI.\n")

    while True:
        # Luôn đọc frame để xả buffer
        ret, frame = cap.read()
        if not ret:
            print("[LỖI] Không thể đọc khung hình từ camera.")
            break

        frame_count += 1
        height, width, _ = frame.shape

        # Logic Inference ngắt quãng
        if frame_count % (SKIP_FRAMES + 1) == 0:
            cached_worker_in_zone = {zone: False for zone in WORKZONES}
            latest_detections = []

            try:
                # Tracking với YOLOv8 (imgsz=480 để chạy nhanh hơn)
                results = model.track(frame, persist=True, conf=0.35, imgsz=480, verbose=False)

                if results and len(results) > 0 and results[0].boxes is not None:
                    boxes = results[0].boxes

                    # Kiểm tra tracker có gán được ID chưa
                    has_ids = boxes.id is not None
                    if has_ids:
                        track_ids = boxes.id.int().cpu().tolist()

                    class_ids = boxes.cls.int().cpu().tolist()
                    confidences = boxes.conf.cpu().tolist()
                    xyxy_list = boxes.xyxy.int().cpu().tolist()

                    for i in range(len(class_ids)):
                        class_id = class_ids[i]
                        confidence = confidences[i]

                        # Chỉ xử lý đối tượng "Người" với confidence > 0.6
                        if class_id != 0 or confidence <= 0.6:
                            continue

                        bx1, by1, bx2, by2 = xyxy_list[i]
                        center_x = (bx1 + bx2) // 2
                        center_y = (by1 + by2) // 2
                        
                        in_any_roi = False
                        for zone_name, (zx, zy, zw, zh) in WORKZONES.items():
                            if zx <= center_x <= zx + zw and zy <= center_y <= zy + zh:
                                cached_worker_in_zone[zone_name] = True
                                in_any_roi = True

                        tid = track_ids[i] if has_ids else "?"
                        latest_detections.append((bx1, by1, bx2, by2, tid, in_any_roi))

            except Exception as e:
                print(f"[LỖI] Tracking: {e}")

        # Vẽ Bounding Box từ latest_detections (Áp dụng cho cả frame không chạy inference)
        for bx1, by1, bx2, by2, tid, in_roi in latest_detections:
            box_color = (0, 255, 0) if in_roi else (200, 200, 200)
            box_thick = 2 if in_roi else 1
            label = f"ID:{tid}"

            cv2.rectangle(frame, (bx1, by1), (bx2, by2), box_color, box_thick)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(frame, (bx1, by1 - th - 8), (bx1 + tw + 4, by1), box_color, -1)
            cv2.putText(frame, label, (bx1 + 2, by1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

        # ======== LOGIC BÁO ĐỘNG ZONE-CENTRIC ========
        for zone_name, (zx, zy, zw, zh) in WORKZONES.items():
            if cached_worker_in_zone.get(zone_name, False):
                if zone_name not in zone_dwell_trackers:
                    zone_dwell_trackers[zone_name] = time.time()
                
                dwell_time = time.time() - zone_dwell_trackers[zone_name]
                if dwell_time >= DWELL_THRESHOLD:
                    last_seen_times[zone_name] = time.time()
                
                is_alerted[zone_name] = False
                border_color = (0, 255, 0)
                border_thick = 2
                status = f"{zone_name}: Co nguoi"
            else:
                if zone_name in zone_dwell_trackers:
                    del zone_dwell_trackers[zone_name]
                    
                time_missing = time.time() - last_seen_times[zone_name]

                if time_missing > MISSING_THRESHOLD and not is_alerted[zone_name]:
                    # BÁO ĐỘNG
                    border_color = (0, 0, 255)
                    border_thick = 3
                    status = f"{zone_name} Vang: {int(time_missing)}s"

                    print(f"[CẢNH BÁO] {zone_name} trống quá {MISSING_THRESHOLD}s!")

                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    fname = f"missing_{zone_name}_{ts}.jpg"
                    cv2.imwrite(os.path.join(SNAPSHOT_DIR, fname), frame)
                    print(f"[CAMERA] Snapshot: {fname}")

                    # Tạm thời đổi camera_id thành zone_name để gửi zone_name lên broker
                    old_id = publisher.camera_id
                    publisher.camera_id = zone_name
                    publisher.publish_alert(alert_type="Worker_Missing")
                    publisher.camera_id = old_id
                    
                    is_alerted[zone_name] = True

                elif time_missing > MISSING_THRESHOLD:
                    # Đã báo động rồi, giữ viền đỏ
                    border_color = (0, 0, 255)
                    border_thick = 3
                    status = f"{zone_name} Vang: {int(time_missing)}s"
                else:
                    # Cảnh báo nhẹ
                    border_color = (0, 255, 255)
                    border_thick = 2
                    status = f"Vang mat: {int(time_missing)}s"

            # Vẽ ROI và trạng thái
            cv2.rectangle(frame, (zx, zy), (zx + zw, zy + zh), border_color, border_thick)
            cv2.putText(frame, status, (zx, zy - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, border_color, 2)

        cv2.imshow("Giam sat Bien - SmartFactory (Zone-Centric)", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print("Đang đóng trạm giám sát...")
            break
        elif key == ord('r'):
            if os.path.exists(ROI_CONFIG_FILE):
                os.remove(ROI_CONFIG_FILE)
            WORKZONES = setup_rois(cap)
            last_seen_times = {zone: time.time() for zone in WORKZONES}
            zone_dwell_trackers = {}
            is_alerted = {zone: False for zone in WORKZONES}
            worker_in_zone = {zone: False for zone in WORKZONES}
            cached_worker_in_zone = {zone: False for zone in WORKZONES}

    cap.release()
    publisher.disconnect()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
