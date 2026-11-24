"""
label_video.py — gán nhãn gold (các lượt đỗ xe của từng chỗ) cho video đánh giá.

    python label_video.py --video bai_xe.mp4 --split dev

1. Vẽ các chỗ đỗ (ENTER/SPACE chốt từng chỗ, ESC xong). Nếu file nhãn đã có thì dùng lại chỗ đỗ cũ.
2. Video chạy: nhấn phím 1..9 khi xe đỗ xong vào chỗ tương ứng, nhấn lại khi xe bắt đầu rời đi.
   SPACE tạm dừng/tiếp tục, q lưu và thoát. Chỗ đang đánh dấu có xe hiện màu đỏ.
   Chỗ đã có xe từ đầu video: nhấn phím ngay ở khung đầu tiên (video bắt đầu ở trạng thái tạm dừng).
Kết quả: eval/labels/<tên_video>.json
"""
import argparse
import json
import os

import cv2

from vision_detector import zone_polygon

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--split", default="dev", choices=["dev", "test"])
    args = ap.parse_args()

    video = os.path.abspath(args.video)
    out = os.path.join(PROJECT_DIR, "eval", "labels", os.path.splitext(os.path.basename(video))[0] + ".json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    cap = cv2.VideoCapture(video)
    ok, frame = cap.read()
    if not ok:
        raise SystemExit(f"[LỖI] Không mở được {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30

    if os.path.exists(out):
        with open(out, encoding="utf-8") as f:
            zones = json.load(f)["zones"]
    else:
        rois = cv2.selectROIs("Ve zone", frame, showCrosshair=True, fromCenter=False)
        cv2.destroyWindow("Ve zone")
        zones = {f"Slot_{i + 1}": [int(v) for v in r] for i, r in enumerate(rois)}
    names = list(zones)[:9]
    parked = {z: [] for z in zones}
    open_since = {}
    frame_idx, paused = 1, True

    while ok:
        t = frame_idx / fps
        view = frame.copy()
        for i, z in enumerate(names, start=1):
            pts = zone_polygon(zones[z])
            color = (0, 0, 255) if z in open_since else (0, 255, 0)
            cv2.polylines(view, [pts], True, color, 2)
            x, y = pts.min(axis=0)
            cv2.putText(view, f"[{i}] {z}", (int(x), int(y) - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        cv2.putText(view, f"t={t:.1f}s  SPACE: dung  1-9: xe den/xe di  q: luu",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        cv2.imshow("Gan nhan", view)
        key = cv2.waitKey(0 if paused else max(1, int(1000 / fps))) & 0xFF
        if key == ord("q"):
            break
        if key == ord(" "):
            paused = not paused
        elif ord("1") <= key <= ord(str(len(names))):
            z = names[key - ord("1")]
            if z in open_since:
                parked[z].append([round(open_since.pop(z), 1), round(t, 1)])
            else:
                open_since[z] = t
        if not paused:
            ok, frame = cap.read()
            frame_idx += ok

    end = round(frame_idx / fps, 1)
    for z, start in open_since.items():  # xe còn đỗ đến hết video
        parked[z].append([round(start, 1), end])
    cap.release()
    cv2.destroyAllWindows()

    # duration_s: chỉ phần đã xem mới được chấm (thoát sớm bằng q thì phần sau không tính).
    label = {"video": os.path.relpath(video, PROJECT_DIR).replace("\\", "/"), "split": args.split,
             "duration_s": end, "zones": zones, "parked": parked}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(label, f, indent=2, ensure_ascii=False)
    print(f"[NHÃN] Đã lưu {out}: {sum(len(v) for v in parked.values())} lượt đỗ.")


if __name__ == "__main__":
    main()
