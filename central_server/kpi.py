"""
kpi.py — KPI bãi đỗ theo từng chỗ đỗ, tính từ bảng `events`.

    python kpi.py                                   # 24 giờ gần nhất
    python kpi.py --from "2026-11-24 08:00" --to "2026-11-24 17:00"

Thời gian camera OFFLINE không tính vào có xe lẫn trống.
"""
import argparse
import sqlite3
import statistics
import time
from datetime import datetime

from mqtt_subscriber import DB_PATH, LOCAL_TZ

OCCUPIED, VACANT, ALERT, OFFLINE = "OCCUPIED", "VACANT", "ALERT", "OFFLINE"


def _overlap(a, b, lo, hi):
    return max(0.0, min(b, hi) - max(a, lo))


def compute_kpis(events, t_from, t_to):
    """
    events: [{ts, camera_id, zone_id, event}] (thứ tự bất kỳ).
    Trả về {(camera_id, zone_id): {occupied_s, vacant_s, arrivals, dwell_s: [...], alerts, response_s: [...]}}
    - arrivals: số lượt xe đến đỗ trong khoảng thời gian (độ quay vòng của chỗ đỗ).
    - dwell_s: thời gian đỗ của các lượt đã kết thúc (xe rời đi) trong khoảng.
    - response_s: từ lúc cảnh báo đỗ quá giờ đến lúc xe rời đi.
    """
    stats, cur = {}, {}  # cur[(cam, zone)] = [state, since, alert_ts]

    def zone_stats(key):
        return stats.setdefault(key, {"occupied_s": 0.0, "vacant_s": 0.0, "arrivals": 0,
                                      "dwell_s": [], "alerts": 0, "response_s": []})

    def close(key, until):
        state, since, _ = cur[key]
        if state in (OCCUPIED, VACANT):
            zone_stats(key)["occupied_s" if state == OCCUPIED else "vacant_s"] += _overlap(since, until, t_from, t_to)

    for ev in sorted(events, key=lambda e: e["ts"]):
        ts, cam, kind = ev["ts"], ev["camera_id"], ev["event"]
        if ts > t_to:
            break
        in_window = t_from <= ts <= t_to
        if kind == OFFLINE:
            for key in [k for k in cur if k[0] == cam]:
                close(key, ts)
                cur[key] = [None, ts, None]
            continue
        if ev.get("zone_id") is None:
            continue  # ONLINE
        key = (cam, ev["zone_id"])
        s = zone_stats(key)
        state, since, alert_ts = cur.get(key, [None, ts, None])
        if kind == ALERT:
            s["alerts"] += in_window
            if state == OCCUPIED:
                cur[key][2] = ts
            continue
        if kind == state:
            continue
        if key in cur:
            close(key, ts)
        if kind == OCCUPIED:
            s["arrivals"] += in_window
        elif state == OCCUPIED and in_window:
            s["dwell_s"].append(ts - since)
            if alert_ts is not None and ts >= alert_ts:
                s["response_s"].append(ts - alert_ts)
        cur[key] = [kind, ts, None]

    for key in cur:
        close(key, t_to)
    return stats


def _mean_min(values):
    return f"{statistics.mean(values) / 60:.1f}" if values else "-"


def format_table(stats):
    head = ["camera", "chỗ đỗ", "giờ quan sát", "lấp đầy %", "lượt xe", "đỗ TB (phút)", "đỗ max (phút)",
            "quá giờ", "xử lý TB (phút)"]
    rows = [head]
    for (cam, zone), s in sorted(stats.items()):
        observed = s["occupied_s"] + s["vacant_s"]
        rows.append([cam, zone, f"{observed / 3600:.2f}",
                     f"{100 * s['occupied_s'] / observed:.1f}" if observed else "-",
                     str(s["arrivals"]), _mean_min(s["dwell_s"]),
                     f"{max(s['dwell_s']) / 60:.1f}" if s["dwell_s"] else "-",
                     str(s["alerts"]), _mean_min(s["response_s"])])
    widths = [max(len(r[i]) for r in rows) for i in range(len(head))]
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)) for r in rows)


def _parse_time(text):
    return datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=LOCAL_TZ).timestamp()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--from", dest="t_from", help='"YYYY-MM-DD HH:MM", mặc định 24 giờ trước')
    ap.add_argument("--to", dest="t_to", help='"YYYY-MM-DD HH:MM", mặc định bây giờ')
    args = ap.parse_args()
    t_to = _parse_time(args.t_to) if args.t_to else time.time()
    t_from = _parse_time(args.t_from) if args.t_from else t_to - 86400

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    # shortcut: đọc toàn bộ lịch sử trước t_to để biết trạng thái đầu kỳ; khi DB lớn thì chỉ đọc từ t_from - 1 ngày.
    rows = conn.execute("SELECT ts, camera_id, zone_id, event, received_at FROM events WHERE ts <= ? ORDER BY ts, id",
                        (t_to,)).fetchall()
    conn.close()
    events = [{"ts": r[0], "camera_id": r[1], "zone_id": r[2], "event": r[3]} for r in rows]

    print(f"KPI từ {datetime.fromtimestamp(t_from, LOCAL_TZ):%Y-%m-%d %H:%M} "
          f"đến {datetime.fromtimestamp(t_to, LOCAL_TZ):%Y-%m-%d %H:%M}\n")
    stats = compute_kpis(events, t_from, t_to)
    print(format_table(stats) if stats else "Không có dữ liệu.")

    delays = [r[4] - r[0] for r in rows if r[3] == ALERT and t_from <= r[0]]
    if delays:
        print(f"\nĐộ trễ edge -> server của cảnh báo: p50 {statistics.median(delays):.2f}s, "
              f"max {max(delays):.2f}s (n={len(delays)}; cần đồng bộ giờ NTP giữa edge và server)")


if __name__ == "__main__":
    main()
