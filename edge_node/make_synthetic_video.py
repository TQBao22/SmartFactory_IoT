"""
make_synthetic_video.py — tạo video tổng hợp theo kịch bản để kiểm tra logic cảnh báo (không thay được video thật).

    python make_synthetic_video.py

Lặp test_video2.mp4 làm nền, dán hình một người ngồi (cắt từ chính video đó, có chuyển động thật)
vào một bàn trống theo lịch có/vắng định trước. Nhãn đúng theo cách dựng nên được ghi tự động
với split "synthetic" — tách khỏi dev/test do người gán.

Đo được: máy trạng thái, ngưỡng thời gian, độ trễ báo, phát hiện người trên nền thật.
Không đo được: đi vào/ra tự nhiên, ánh sáng, góc camera, người khác nhau.
"""
import json
import os

import cv2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
SOURCE = os.path.join(BASE_DIR, "test_video2.mp4")
OUT_VIDEO = os.path.join(BASE_DIR, "synthetic_scenario.mp4")
OUT_LABEL = os.path.join(PROJECT_DIR, "eval", "labels", "synthetic_scenario.json")

CROP = (165, 545, 120, 175)       # x, y, w, h: người ngồi góc trái dưới trong test_video2
PASTE_AT = (835, 455)             # bàn trống (không ai đi vào suốt test_video2)
ZONE = {"Tram_A": [820, 440, 150, 205]}
DURATION = 180.0

# Kịch bản (giây). Ngoài các khoảng "present" thì không dán người.
PRESENT = [(0, 30), (50, 60), (61.5, 80), (85, 110), (120, 122), (150, DURATION)]
GOLD_ABSENCES = [
    [30, 50],    # vắng 20s  -> phải cảnh báo
    [80, 85],    # vắng 5s   -> không được cảnh báo
    [110, 150],  # vắng 40s, người khác đi ngang 120-122s -> phải cảnh báo, không tính là có người
]
# 60-61.5s: công nhân vẫn ngồi nhưng bị che 1.5s -> gold vẫn là có người, không được báo vắng.


def present(t):
    return any(a <= t < b for a, b in PRESENT)


def main():
    src = cv2.VideoCapture(SOURCE)
    fps = src.get(cv2.CAP_PROP_FPS) or 25
    w, h = int(src.get(cv2.CAP_PROP_FRAME_WIDTH)), int(src.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out = cv2.VideoWriter(OUT_VIDEO, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    x, y, cw, ch = CROP
    px, py = PASTE_AT
    for i in range(int(DURATION * fps)):
        ok, frame = src.read()
        if not ok:  # hết video nền thì lặp lại
            src.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = src.read()
        if present(i / fps):
            frame[py:py + ch, px:px + cw] = frame[y:y + ch, x:x + cw].copy()
        out.write(frame)
    src.release()
    out.release()

    label = {"video": "edge_node/synthetic_scenario.mp4", "split": "synthetic", "duration_s": DURATION,
             "zones": ZONE, "absences": {"Tram_A": GOLD_ABSENCES},
             "note": "Video tổng hợp, nhãn đúng theo cách dựng (make_synthetic_video.py)."}
    os.makedirs(os.path.dirname(OUT_LABEL), exist_ok=True)
    with open(OUT_LABEL, "w", encoding="utf-8") as f:
        json.dump(label, f, indent=2, ensure_ascii=False)
    print(f"[SYNTH] {OUT_VIDEO} ({DURATION:.0f}s) + {OUT_LABEL}")


if __name__ == "__main__":
    main()
