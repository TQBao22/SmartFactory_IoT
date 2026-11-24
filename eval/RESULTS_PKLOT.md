# Kết quả trên PKLot

Mỗi lần chạy thêm một dòng, không sửa dòng cũ. Chỉ so sánh các dòng cùng split. Dữ liệu: PKLot (Almeida et al., 2015), CC BY 4.0.

| ngày | model | imgsz | conf | iou | split | số ảnh | số chỗ | accuracy | P | R | F1 | acc UFPR04 | acc UFPR05 | acc PUCPR | suy luận p50 (ms) | ghi chú |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-11-25 | yolov8s.pt | 1280 | 0.05 | 0.2 | dev | 284 | 14996 | 0.893 | 0.997 | 0.790 | 0.882 | 0.999 | 0.997 | 0.819 | 513 | yolov8s COCO không fine-tune, CPU i7-1165G7, 4 ảnh/ngày |
| 2026-11-25 | yolov8s.pt | 1280 | 0.05 | 0.2 | test | 6226 | 332838 | 0.915 | 0.999 | 0.824 | 0.903 | 0.998 | 0.996 | 0.859 | 424 | CHỐT 1280/0.05/0.2, yolov8s COCO không fine-tune, CPU i7-1165G7, toàn bộ ảnh ngày chẵn |
