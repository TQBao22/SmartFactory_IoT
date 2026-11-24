"""
eval_pklot.py — đo độ chính xác nhận biết chỗ đỗ có xe / trống trên bộ dữ liệu công khai PKLot.

PKLot (CC BY 4.0): 12.417 ảnh 1280x720 từ 3 bãi (UFPR04, UFPR05, PUCPR), trời nắng/mây/mưa. Mỗi ảnh có file XML
ghi đa giác và nhãn occupied của từng chỗ đỗ. Trích dẫn: Almeida et al., "PKLot - A robust dataset for parking
lot classification", Expert Systems with Applications 42(11), 2015.

    python eval_pklot.py --root D:/datasets/PKLot/PKLot                        # split dev, 4 ảnh mỗi ngày
    python eval_pklot.py --root ... --grid                                     # dò conf x iou trong một lần chạy
    python eval_pklot.py --root ... --conf 0.15 --iou 0.1 --append --note "..."
    python eval_pklot.py --root ... --split test --per-day 0 --append --note "chốt cấu hình"   # test: chạy một lần

Chia split theo ngày vì ảnh cùng ngày rất giống nhau: ngày lẻ = dev, ngày chẵn = test.
Chạy đúng hàm của pipeline thật: detect_vehicles -> zones_occupied.
"""
import argparse
import glob
import os
import statistics
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date

import cv2

from vision_detector import DETECT_CONF, IMGSZ, ZONE_IOU, default_model_path, detect_vehicles, load_model, zones_occupied

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(PROJECT_DIR, "eval", "RESULTS_PKLOT.md")
LOTS = ["UFPR04", "UFPR05", "PUCPR"]
GRID_CONF = [0.03, 0.05, 0.1, 0.15, 0.25]
GRID_IOU = [0.05, 0.1, 0.2, 0.3]
HEADER = ("| ngày | model | imgsz | conf | iou | split | số ảnh | số chỗ | accuracy | P | R | F1 "
          "| acc UFPR04 | acc UFPR05 | acc PUCPR | suy luận p50 (ms) | ghi chú |\n"
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")


def parse_pklot_xml(path):
    """-> (zones {slot_id: [[x, y], ...]}, gold {slot_id: bool}). Bỏ chỗ thiếu nhãn occupied hoặc đa giác (lỗi gốc của PKLot)."""
    zones, gold = {}, {}
    for space in ET.parse(path).getroot().iter("space"):
        occ = space.get("occupied")
        pts = [[int(p.get("x")), int(p.get("y"))] for p in space.iter("point")]
        if occ not in ("0", "1") or len(pts) < 3:
            continue
        sid = f"Slot_{space.get('id')}"
        zones[sid] = pts
        gold[sid] = occ == "1"
    return zones, gold


def split_of(day):
    """'2012-09-11' -> 'dev' (ngày lẻ) / 'test' (ngày chẵn)."""
    return "dev" if int(day[-2:]) % 2 else "test"


def select_images(root, split, per_day):
    """[(lot, weather, xml_path)] — per_day ảnh cách đều trong mỗi ngày (0 = tất cả)."""
    out = []
    for lot in LOTS:
        for day_dir in sorted(glob.glob(os.path.join(root, lot, "*", "*"))):
            day = os.path.basename(day_dir)
            if split != "all" and split_of(day) != split:
                continue
            xmls = sorted(glob.glob(os.path.join(day_dir, "*.xml")))
            if per_day and len(xmls) > per_day:
                xmls = [xmls[i * len(xmls) // per_day] for i in range(per_day)]
            weather = os.path.basename(os.path.dirname(day_dir))
            out += [(lot, weather, x) for x in xmls]
    return out


def confusion(samples, conf, iou):
    """samples: [(lot, weather, zones, gold, boxes)] -> {nhóm: [tp, fp, fn, tn]} với nhóm 'all', lot, weather."""
    cm = defaultdict(lambda: [0, 0, 0, 0])
    for lot, weather, zones, gold, boxes in samples:
        pred = zones_occupied([b for b in boxes if b[4] >= conf], zones, iou)
        for sid, g in gold.items():
            idx = 0 if g and pred[sid] else 1 if pred[sid] else 2 if g else 3
            for key in ("all", lot, weather):
                cm[key][idx] += 1
    return cm


def scores(c):
    tp, fp, fn, tn = c
    n = tp + fp + fn + tn
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f1 = 2 * p * r / (p + r) if p and r else None
    return {"n": n, "acc": (tp + tn) / n if n else None, "p": p, "r": r, "f1": f1}


def fmt(v, pattern="{:.3f}"):
    return "-" if v is None else pattern.format(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="thư mục PKLot/PKLot (chứa UFPR04, UFPR05, PUCPR)")
    ap.add_argument("--split", default="dev", choices=["dev", "test", "all"])
    ap.add_argument("--per-day", type=int, default=4, help="số ảnh lấy mỗi ngày mỗi bãi, 0 = tất cả")
    ap.add_argument("--model", default=default_model_path())
    ap.add_argument("--imgsz", type=int, default=IMGSZ)
    ap.add_argument("--conf", type=float, default=DETECT_CONF)
    ap.add_argument("--iou", type=float, default=ZONE_IOU)
    ap.add_argument("--grid", action="store_true", help="in bảng F1 cho nhiều cặp conf x iou (chỉ suy luận một lần)")
    ap.add_argument("--append", action="store_true", help="ghi một dòng vào eval/RESULTS_PKLOT.md")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    images = select_images(args.root, args.split, args.per_day)
    if not images:
        raise SystemExit(f"[EVAL] Không thấy ảnh PKLot trong {args.root} (cần thư mục UFPR04/UFPR05/PUCPR).")
    model = load_model(args.model)
    min_conf = min([args.conf] + (GRID_CONF if args.grid else []))
    samples, infer_ms = [], []
    for i, (lot, weather, xml) in enumerate(images, 1):
        frame = cv2.imread(os.path.splitext(xml)[0] + ".jpg")
        if frame is None:
            print(f"[BỎ QUA] Không đọc được ảnh của {xml}")
            continue
        zones, gold = parse_pklot_xml(xml)
        t = time.perf_counter()
        boxes = detect_vehicles(model, frame, imgsz=args.imgsz, conf=min_conf)
        infer_ms.append(1000 * (time.perf_counter() - t))
        samples.append((lot, weather, zones, gold, boxes))
        if i % 50 == 0:
            print(f"[EVAL] {i}/{len(images)} ảnh")

    if args.grid:
        print("\nF1 (accuracy) theo conf x iou:")
        print("conf\\iou  " + "  ".join(f"{v:>13}" for v in GRID_IOU))
        for c in GRID_CONF:
            row = [scores(confusion(samples, c, u)["all"]) for u in GRID_IOU]
            print(f"{c:<9} " + "  ".join(f"{fmt(s['f1'])} ({fmt(s['acc'])})" for s in row))

    cm = confusion(samples, args.conf, args.iou)
    a = scores(cm["all"])
    p50 = statistics.median(infer_ms)
    print(f"\nconf={args.conf:g} iou={args.iou:g}: {len(samples)} ảnh, {a['n']} chỗ đỗ  "
          f"accuracy={fmt(a['acc'])} P={fmt(a['p'])} R={fmt(a['r'])} F1={fmt(a['f1'])}  suy luận p50={p50:.0f}ms")
    for key in LOTS + sorted(k for k in cm if k not in LOTS and k != "all"):
        s = scores(cm[key])
        print(f"  {key:<8} {s['n']:>6} chỗ  accuracy={fmt(s['acc'])} P={fmt(s['p'])} R={fmt(s['r'])}")

    if args.append:
        new = not os.path.exists(RESULTS)
        with open(RESULTS, "a", encoding="utf-8") as f:
            if new:
                f.write("# Kết quả trên PKLot\n\nMỗi lần chạy thêm một dòng, không sửa dòng cũ. Chỉ so sánh các dòng "
                        "cùng split. Dữ liệu: PKLot (Almeida et al., 2015), CC BY 4.0.\n\n" + HEADER)
            lot_acc = [fmt(scores(cm[lot])["acc"]) for lot in LOTS]
            f.write(f"| {date.today()} | {os.path.basename(args.model)} | {args.imgsz} | {args.conf:g} | {args.iou:g} | "
                    f"{args.split} | {len(samples)} | {a['n']} | {fmt(a['acc'])} | {fmt(a['p'])} | {fmt(a['r'])} | "
                    f"{fmt(a['f1'])} | {' | '.join(lot_acc)} | {p50:.0f} | {args.note} |\n")
        print(f"\n[EVAL] Đã ghi một dòng vào {RESULTS}")


if __name__ == "__main__":
    main()
