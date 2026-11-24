# Kết quả đánh giá pipeline edge

Mỗi lần chạy thêm một dòng, không sửa dòng cũ. Chỉ so sánh các dòng cùng split.

| ngày | model | imgsz | conf | enter/leave/alert (s) | split | số video | P | R | F1 | báo giả/zone-giờ | trễ báo TB (s) | khớp trạng thái | sai số có mặt (điểm %) | suy luận p50 (ms) | FPS | ghi chú |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-11-24 | yolov8n.pt | 480 | 0.4 | 3/2/10 | synthetic | 1 | 1.00 | 1.00 | 1.00 | 0.0 | 0.0 | 99.8% | -0.2 | 40 | 52.2 | video tổng hợp 180s, CPU, predict |

## Bãi đỗ xe (từ 2026-11-25)

Dòng phía trên là pipeline giám sát người cũ, không so sánh với các dòng dưới. Video bãi đỗ: chấm cảnh báo đỗ quá giờ.

| ngày | model | imgsz | conf | enter/leave/alert (s) | split | số video | P | R | F1 | báo giả/zone-giờ | trễ báo TB (s) | khớp trạng thái | sai số lấp đầy (điểm %) | suy luận p50 (ms) | FPS | ghi chú |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
