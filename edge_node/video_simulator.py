"""
video_simulator.py
Mô phỏng camera giám sát từ file video có sẵn để phục vụ kiểm thử (Offline Inference).
Phiên bản Multi-ROI: Giám sát NHIỀU vùng làm việc độc lập cùng lúc,
mỗi vùng có bộ đếm thời gian và cờ cảnh báo riêng.
"""

import cv2
import os
import sys
import torch
from datetime import datetime
from mqtt_publisher import MQTTAlertPublisher
from ultralytics import YOLO

# Đường dẫn tuyệt đối
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
ROOT_DIR = os.path.dirname(PROJECT_DIR)

# Khởi tạo mô hình YOLOv8m (Medium) — cân bằng giữa độ chính xác và tốc độ
model = YOLO(os.path.join(ROOT_DIR, 'yolov8m.pt'))

# Kiểm tra phần cứng đang chạy mô hình
device_used = 'GPU (CUDA)' if torch.cuda.is_available() else 'CPU'
print(f"[INFO] Hệ thống đang chạy mô hình YOLOv8m trên: {device_used}")
if not torch.cuda.is_available():
    print("[WARNING] Chạy bản Medium trên CPU sẽ rất chậm. Khuyến nghị dùng GPU hoặc tối ưu hóa ONNX/OpenVINO.")


# ============================================================================
# CẤU HÌNH MULTI-ROI: Định nghĩa các vùng làm việc cần giám sát
# Mỗi vùng là một tuple (x1, y1, x2, y2) — góc trên-trái và dưới-phải
# Tọa độ sẽ được tự động tính lại theo kích thước frame thực tế trong main()
# ============================================================================
WORKZONES = {}

# Ngưỡng thời gian vắng mặt cho phép (giây)
MISSING_THRESHOLD = 10.0


def main():
    publisher = MQTTAlertPublisher()

    SNAPSHOT_DIR = os.path.join(PROJECT_DIR, "snapshots")
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)

    # Mở file video để mô phỏng
    cap = cv2.VideoCapture(os.path.join(BASE_DIR, 'test_video2.mp4'))
    if not cap.isOpened():
        print("[LỖI] Không thể mở file video test_video.mp4.")
        return

    ret, first_frame = cap.read()
    if not ret:
        sys.exit()

    print("[INFO] Hãy dùng chuột quét (kéo thả) các vùng làm việc. Nhấn SPACE hoặc ENTER để chốt 1 vùng. Nhấn ESC để hoàn tất và bắt đầu chạy AI.")
    rois = cv2.selectROIs("Chon Vung Giam Sat", first_frame, fromCenter=False, showCrosshair=True)
    cv2.destroyWindow("Chon Vung Giam Sat")

    global WORKZONES
    WORKZONES = {}
    
    if len(rois) == 0:
        print("[LỖI] Không có vùng nào được chọn.")
        sys.exit()

    for i, roi in enumerate(rois, start=1):
        x, y, w, h = roi
        WORKZONES[f"Zone_{i}"] = (int(x), int(y), int(x + w), int(y + h))

    # Lấy FPS gốc của video để tính thời gian nội tại
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 30  # Mặc định 30 FPS nếu không đọc được
    print(f"[INFO] FPS video: {fps}")

    # Bộ đếm khung hình — dùng để tính thời gian nội tại video
    frame_counter = 0

    # ========================================================================
    # BIẾN TRẠNG THÁI — mỗi Zone quản lý độc lập
    # ========================================================================
    last_seen_times = {zone: 0.0 for zone in WORKZONES}
    is_alerted = {zone: False for zone in WORKZONES}

    print("\n=== [SIMULATOR] TRẠM GIÁM SÁT BIÊN (MULTI-ROI TRACKING) ĐÃ KHỞI ĐỘNG ===")
    print(f"Đang giám sát {len(WORKZONES)} vùng: {', '.join(WORKZONES.keys())}")
    print("Nhấn 'q' để thoát.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[SIMULATOR] Đã phát hết video.")
            break

        # Tăng bộ đếm và tính thời gian nội tại video (giây)
        frame_counter += 1
        current_video_time = frame_counter / fps

        # Trạng thái tạm cho frame hiện tại: vùng nào đang có người?
        zone_occupied = {zone: False for zone in WORKZONES}

        # ==================================================================
        # TRACKING + KIỂM TRA TƯƠNG GIAO VỚI TỪNG ZONE
        # ==================================================================
        try:
            results = model.track(frame, persist=True, conf=0.35, imgsz=640, verbose=False)

            if results and len(results) > 0 and results[0].boxes is not None:
                boxes = results[0].boxes

                has_ids = boxes.id is not None
                if has_ids:
                    track_ids = boxes.id.int().cpu().tolist()

                class_ids = boxes.cls.int().cpu().tolist()
                confidences = boxes.conf.cpu().tolist()
                xyxy_list = boxes.xyxy.int().cpu().tolist()

                for i in range(len(class_ids)):
                    # Chỉ xử lý "Người" (class 0) với confidence > 0.6
                    if class_ids[i] != 0 or confidences[i] <= 0.6:
                        continue

                    bx1, by1, bx2, by2 = xyxy_list[i]
                    center_x = (bx1 + bx2) // 2
                    center_y = (by1 + by2) // 2
                    tid = track_ids[i] if has_ids else "?"

                    # Kiểm tra người này nằm trong Zone nào
                    person_in_any_zone = False
                    for zone_name, (zx1, zy1, zx2, zy2) in WORKZONES.items():
                        if zx1 <= center_x <= zx2 and zy1 <= center_y <= zy2:
                            zone_occupied[zone_name] = True
                            person_in_any_zone = True

                    # Vẽ bounding box: XANH nếu trong zone, XÁM nếu ngoài
                    box_color = (0, 255, 0) if person_in_any_zone else (200, 200, 200)
                    box_thick = 2 if person_in_any_zone else 1
                    label = f"ID:{tid}"

                    cv2.rectangle(frame, (bx1, by1), (bx2, by2), box_color, box_thick)
                    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                    cv2.rectangle(frame, (bx1, by1 - th - 8), (bx1 + tw + 4, by1), box_color, -1)
                    cv2.putText(frame, label, (bx1 + 2, by1 - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

        except Exception as e:
            print(f"[LỖI] Tracking: {e}")

        # ==================================================================
        # LOGIC BÁO ĐỘNG — DUYỆT TỪNG ZONE ĐỘC LẬP
        # ==================================================================
        for zone_name, (zx1, zy1, zx2, zy2) in WORKZONES.items():

            if zone_occupied[zone_name]:
                # ---- ZONE CÓ NGƯỜI: An toàn ----
                last_seen_times[zone_name] = current_video_time
                is_alerted[zone_name] = False

                border_color = (0, 255, 0)   # Xanh lá
                border_thick = 2
                status = f"{zone_name}: OK"
            else:
                # ---- ZONE TRỐNG: Tính thời gian vắng ----
                time_missing = current_video_time - last_seen_times[zone_name]

                if time_missing > MISSING_THRESHOLD and not is_alerted[zone_name]:
                    # BÁO ĐỘNG LẦN ĐẦU cho zone này
                    border_color = (0, 0, 255)   # Đỏ
                    border_thick = 3
                    status = f"{zone_name}: BAO DONG {int(time_missing)}s"

                    print(f"[CẢNH BÁO] {zone_name} trống quá {MISSING_THRESHOLD}s!")

                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    fname = f"missing_{zone_name}_{ts}.jpg"
                    cv2.imwrite(os.path.join(SNAPSHOT_DIR, fname), frame)
                    print(f"[CAMERA] Snapshot: {fname}")

                    # Gửi MQTT với tên zone cụ thể
                    publisher.publish_alert(alert_type=f"Worker_Missing_{zone_name}")
                    is_alerted[zone_name] = True

                elif time_missing > MISSING_THRESHOLD:
                    # Đã báo động rồi, giữ viền đỏ
                    border_color = (0, 0, 255)
                    border_thick = 3
                    status = f"{zone_name}: BAO DONG {int(time_missing)}s"
                else:
                    # Cảnh báo nhẹ (chưa quá ngưỡng)
                    border_color = (0, 255, 255)  # Vàng
                    border_thick = 2
                    status = f"{zone_name}: Trong {int(time_missing)}s"

            # Vẽ hình chữ nhật Zone và nhãn trạng thái
            cv2.rectangle(frame, (zx1, zy1), (zx2, zy2), border_color, border_thick)
            cv2.putText(frame, status, (zx1, zy1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, border_color, 2)

        # Hiển thị
        cv2.imshow("Giam sat Bien - SmartFactory (Multi-ROI)", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("Đang đóng trạm giám sát...")
            break

    cap.release()
    publisher.disconnect()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
