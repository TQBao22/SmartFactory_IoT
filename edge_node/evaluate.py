"""
evaluate.py — đo độ chính xác và tốc độ của pipeline edge trên video đã gán nhãn (eval/labels/*.json).

    python evaluate.py                                  # split dev, model mặc định
    python evaluate.py --model ../../yolov8n.pt --append --note "thử bản nano"
    python evaluate.py --split test --append --note "chốt cấu hình v1.1"   # test: chỉ chạy khi đã chốt

Nhãn tạo bằng label_video.py. Chạy đúng pipeline thật (detect_people -> zones_occupied -> ZoneMonitor)
nhưng dùng thời gian video, không gửi MQTT.
"""
import argparse
import glob
import json
import os
import statistics
import time
from datetime import date

import cv2

from eval_metrics import aggregate, score_zone
from vision_detector import PERSON_CONF, SKIP_FRAMES, default_model_path, detect_people, load_model, zones_occupied
from zone_monitor import ZoneMonitor

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELS_DIR = os.path.join(PROJECT_DIR, "eval", "labels")
RESULTS = os.path.join(PROJECT_DIR, "eval", "RESULTS.md")
HEADER = ("| ngày | model | imgsz | conf | enter/leave/alert (s) | split | số video | P | R | F1 | báo giả/zone-giờ "
          "| trễ báo TB (s) | khớp trạng thái | sai số có mặt (điểm %) | suy luận p50 (ms) | FPS | ghi chú |\n"
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")


def run_video(model, label, args):
    zones = label["zones"]
    cap = cv2.VideoCapture(os.path.join(PROJECT_DIR, label["video"]))
    if not cap.isOpened():
        raise SystemExit(f"[LỖI] Không mở được video {label['video']}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    monitor = ZoneMonitor(zones, args.enter_s, args.leave_s, args.alert_s, start=0.0)
    limit = label.get("duration_s", float("inf"))
    events, infer_ms, frame_idx = [], [], 0
    wall_start = time.perf_counter()
    while True:
        ret, frame = cap.read()
        if not ret or (frame_idx + 1) / fps > limit:
            break
        frame_idx += 1
        if frame_idx % (SKIP_FRAMES + 1):
            continue
        t = time.perf_counter()
        people = detect_people(model, frame, imgsz=args.imgsz, conf=args.conf)
        infer_ms.append(1000 * (time.perf_counter() - t))
        events += monitor.update(zones_occupied(people, zones), frame_idx / fps)
    cap.release()
    duration = frame_idx / fps
    per_zone = [score_zone(label["absences"].get(z, []), [e for e in events if e["zone_id"] == z], duration, args.alert_s)
                for z in zones]
    return per_zone, events, infer_ms, frame_idx / (time.perf_counter() - wall_start)


def fmt(v, pattern="{:.2f}"):
    return "-" if v is None else pattern.format(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default=LABELS_DIR)
    ap.add_argument("--split", default="dev", choices=["dev", "test", "synthetic", "all"])
    ap.add_argument("--model", default=default_model_path())
    ap.add_argument("--imgsz", type=int, default=480)
    ap.add_argument("--conf", type=float, default=PERSON_CONF, help="ngưỡng tin cậy tính là có người")
    ap.add_argument("--enter-s", type=float, default=3.0)
    ap.add_argument("--leave-s", type=float, default=2.0)
    ap.add_argument("--alert-s", type=float, default=10.0)
    ap.add_argument("--append", action="store_true", help="ghi một dòng vào eval/RESULTS.md")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    labels = []
    for path in sorted(glob.glob(os.path.join(args.labels, "*.json"))):
        with open(path, encoding="utf-8") as f:
            label = json.load(f)
        if args.split == "all" or label.get("split") == args.split:
            labels.append(label)
    if not labels:
        raise SystemExit(f"[EVAL] Không có nhãn split={args.split} trong {args.labels}. "
                         "Gán nhãn trước: python label_video.py --video <file.mp4>")

    model = load_model(args.model)
    all_zones, all_ms, fps_list, per_video = [], [], [], []
    for label in labels:
        per_zone, events, infer_ms, fps = run_video(model, label, args)
        all_zones += per_zone
        all_ms += infer_ms
        fps_list.append(fps)
        v = aggregate(per_zone)
        per_video.append((v["fp"] + v["fn"], label["video"], v, events))
        print(f"[EVAL] {label['video']}: TP={v['tp']} FP={v['fp']} FN={v['fn']} "
              f"khớp trạng thái={fmt(v['occ_accuracy'], '{:.1%}')}  {fps:.1f} FPS")

    a = aggregate(all_zones)
    p50 = statistics.median(all_ms) if all_ms else None
    fps = statistics.mean(fps_list)
    print(f"\nP={fmt(a['precision'])} R={fmt(a['recall'])} F1={fmt(a['f1'])} "
          f"báo giả/zone-giờ={fmt(a['false_alarms_per_zone_hour'], '{:.1f}')} trễ báo TB={fmt(a['latency_mean_s'], '{:.1f}')}s "
          f"khớp trạng thái={fmt(a['occ_accuracy'], '{:.1%}')} sai số có mặt={fmt(a['occ_pct_error'], '{:+.1f}')} điểm % "
          f"suy luận p50={fmt(p50, '{:.0f}')}ms FPS={fps:.1f}")

    print("\nVideo sai nhiều nhất (FP+FN):")
    for errors, video, v, events in sorted(per_video, key=lambda x: -x[0])[:5]:
        alerts = [f"{e['zone_id']}@{e['ts']:.1f}s" for e in events if e["event"] == "ALERT"]
        print(f"  {video}: FP={v['fp']} FN={v['fn']} cảnh báo={alerts}")

    if args.append:
        new = not os.path.exists(RESULTS)
        with open(RESULTS, "a", encoding="utf-8") as f:
            if new:
                f.write("# Kết quả đánh giá pipeline edge\n\nMỗi lần chạy thêm một dòng, không sửa dòng cũ. "
                        "Chỉ so sánh các dòng cùng split.\n\n" + HEADER)
            f.write(f"| {date.today()} | {os.path.basename(args.model)} | {args.imgsz} | {args.conf:g} | "
                    f"{args.enter_s:g}/{args.leave_s:g}/{args.alert_s:g} | {args.split} | {len(labels)} | "
                    f"{fmt(a['precision'])} | {fmt(a['recall'])} | {fmt(a['f1'])} | "
                    f"{fmt(a['false_alarms_per_zone_hour'], '{:.1f}')} | {fmt(a['latency_mean_s'], '{:.1f}')} | "
                    f"{fmt(a['occ_accuracy'], '{:.1%}')} | {fmt(a['occ_pct_error'], '{:+.1f}')} | "
                    f"{fmt(p50, '{:.0f}')} | {fps:.1f} | {args.note} |\n")
        print(f"\n[EVAL] Đã ghi một dòng vào {RESULTS}")


if __name__ == "__main__":
    main()
