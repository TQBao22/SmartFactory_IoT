"""
zone_monitor.py
Máy trạng thái cho từng chỗ đỗ (zone). Không phụ thuộc OpenCV/YOLO để test được offline.

Mỗi zone ở một trong ba trạng thái: UNKNOWN (vừa khởi động), OCCUPIED, VACANT.
- OCCUPIED: thấy xe liên tục >= enter_s giây (lọc xe chạy ngang qua chỗ đỗ).
  Mất detection ngắn hơn leave_s giây (bị xe/người khác che) không làm mất chuỗi có xe.
- VACANT: không thấy xe quá leave_s giây. Thời điểm xe rời = lần cuối thấy xe.
- ALERT: xe đỗ liên tục >= alert_s giây (đỗ quá giờ), chỉ phát một lần cho mỗi lượt đỗ.

update() trả về danh sách sự kiện đổi trạng thái; server dùng chúng để tính KPI.
"""

OCCUPIED = "OCCUPIED"
VACANT = "VACANT"
ALERT = "ALERT"


class ZoneMonitor:
    def __init__(self, zones, enter_s=10.0, leave_s=10.0, alert_s=7200.0, start=0.0):
        self.enter_s = enter_s
        self.leave_s = leave_s
        self.alert_s = alert_s
        self.reset(zones, start)

    def reset(self, zones, start):
        self.start = start
        self._z = {
            z: {"state": "UNKNOWN", "streak": None, "last_seen": None, "since": start, "alerted": False}
            for z in zones
        }

    def update(self, occupied, now):
        """occupied: {zone_id: bool} cho khung hình vừa suy luận. now: giây (đồng hồ thật hoặc thời gian video)."""
        events = []
        for zone, s in self._z.items():
            self._step(zone, s, bool(occupied.get(zone)), now, events)
        return events

    def _step(self, zone, s, seen, now, events):
        last = self.start if s["last_seen"] is None else s["last_seen"]
        if seen:
            if s["last_seen"] is None or now - last > self.leave_s:
                s["streak"] = now
            s["last_seen"] = now
            if s["state"] != OCCUPIED and now - s["streak"] >= self.enter_s:
                s["state"] = OCCUPIED
                s["since"] = s["streak"]
                s["alerted"] = False
                events.append({"zone_id": zone, "event": OCCUPIED, "ts": s["streak"]})
        elif s["state"] != VACANT and now - last > self.leave_s:
            s["state"] = VACANT
            s["since"] = last
            events.append({"zone_id": zone, "event": VACANT, "ts": last})

        if s["state"] == OCCUPIED and not s["alerted"] and now - s["since"] >= self.alert_s:
            s["alerted"] = True
            events.append({"zone_id": zone, "event": ALERT, "ts": now,
                           "duration_s": round(now - s["since"], 1)})

    def states(self):
        """{zone_id: (state, since)} để vẽ lên màn hình."""
        return {z: (s["state"], s["since"]) for z, s in self._z.items()}
