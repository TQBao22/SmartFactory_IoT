"""
eval_metrics.py — chấm sự kiện của ZoneMonitor với nhãn gold (khoảng vắng mặt do người gán tay).

Gold: {zone_id: [[start_s, end_s], ...]} theo thời gian video (giây). Ngoài các khoảng này = có người.
"""
import statistics

STEP = 0.1  # độ phân giải khi so trạng thái theo thời gian (giây)


def _in_any(t, intervals):
    return any(a <= t < b for a, b in intervals)


def _predicted_state(events, t):
    """Trạng thái dự đoán (OCCUPIED/VACANT/None) tại thời điểm t từ chuỗi sự kiện của một zone."""
    state = None
    for e in events:
        if e["ts"] > t:
            break
        if e["event"] in ("OCCUPIED", "VACANT"):
            state = e["event"]
    return state


def score_zone(absences, events, duration, alert_s, tol=3.0):
    """
    Cảnh báo đúng (TP): ALERT nằm trong một khoảng vắng gold dài >= alert_s, trong [start, end + tol].
    Mỗi khoảng vắng gold chỉ khớp một ALERT; ALERT thừa hoặc ngoài khoảng vắng = báo giả (FP).
    Khoảng vắng gold dài >= alert_s mà không có ALERT = bỏ sót (FN).
    """
    alerts = [e["ts"] for e in events if e["event"] == "ALERT"]
    eligible = [(a, b) for a, b in absences if b - a >= alert_s]
    matched, latencies, fp = set(), [], 0
    for t in alerts:
        hit = next((i for i, (a, b) in enumerate(eligible) if i not in matched and a <= t <= b + tol), None)
        if hit is None:
            fp += 1
        else:
            matched.add(hit)
            latencies.append(t - (eligible[hit][0] + alert_s))

    state_events = sorted((e for e in events if e["event"] != "ALERT"), key=lambda e: e["ts"])
    known = agree = gold_occ = pred_occ = 0
    for i in range(int(duration / STEP)):
        t = i * STEP
        pred = _predicted_state(state_events, t)
        if pred is None:
            continue  # chưa đủ dữ liệu để kết luận (vài giây đầu)
        gold = "VACANT" if _in_any(t, absences) else "OCCUPIED"
        known += 1
        agree += pred == gold
        gold_occ += gold == "OCCUPIED"
        pred_occ += pred == "OCCUPIED"

    return {"tp": len(matched), "fp": fp, "fn": len(eligible) - len(matched), "latencies": latencies,
            "known_s": known * STEP, "agree_s": agree * STEP, "gold_occ_s": gold_occ * STEP, "pred_occ_s": pred_occ * STEP,
            "zone_s": duration}


def aggregate(per_zone):
    """Gộp kết quả nhiều zone/video thành chỉ số tổng."""
    tot = {k: sum(z[k] for z in per_zone) for k in ("tp", "fp", "fn", "known_s", "agree_s", "gold_occ_s", "pred_occ_s", "zone_s")}
    lat = [x for z in per_zone for x in z["latencies"]]
    p = tot["tp"] / (tot["tp"] + tot["fp"]) if tot["tp"] + tot["fp"] else None
    r = tot["tp"] / (tot["tp"] + tot["fn"]) if tot["tp"] + tot["fn"] else None
    if tot["tp"]:
        f1 = 2 * p * r / (p + r)
    else:
        f1 = 0.0 if tot["fp"] + tot["fn"] else None  # None: không có gì để báo và không báo gì
    known = tot["known_s"]
    return {
        **tot, "precision": p, "recall": r, "f1": f1,
        "false_alarms_per_zone_hour": tot["fp"] / (tot["zone_s"] / 3600) if tot["zone_s"] else None,
        "latency_mean_s": statistics.mean(lat) if lat else None,
        "occ_accuracy": tot["agree_s"] / known if known else None,
        "occ_pct_error": 100 * (tot["pred_occ_s"] - tot["gold_occ_s"]) / known if known else None,
    }
