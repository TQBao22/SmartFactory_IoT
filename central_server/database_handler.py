import os
import sqlite3
import time


class AlertDatabase:
    """
    Lưu sự kiện từ edge vào SQLite.

    Bảng `events`: mỗi dòng là một lần đổi trạng thái zone (OCCUPIED / VACANT / ALERT)
    hoặc trạng thái camera (ONLINE / OFFLINE, zone_id = NULL).
    `ts` là thời điểm xảy ra (epoch giây, do edge đo), `received_at` là lúc server nhận —
    hiệu hai cột cho độ trễ truyền tin.
    Bảng `alerts` cũ (v1.0) giữ nguyên, không đọc/ghi nữa.
    """

    def __init__(self, db_path):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          REAL NOT NULL,
                camera_id   TEXT NOT NULL,
                zone_id     TEXT,
                event       TEXT NOT NULL,
                duration_s  REAL,
                received_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_cam_zone_ts ON events(camera_id, zone_id, ts);
        """)
        self.conn.commit()
        print(f"[DATABASE] Đã kết nối CSDL: {db_path}")

    def insert_event(self, ev, received_at=None):
        try:
            self.conn.execute(
                "INSERT INTO events (ts, camera_id, zone_id, event, duration_s, received_at) VALUES (?, ?, ?, ?, ?, ?)",
                (ev["ts"], ev["camera_id"], ev.get("zone_id"), ev["event"], ev.get("duration_s"),
                 received_at or time.time()),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"[DATABASE LỖI] Lỗi khi thêm dữ liệu: {e}")
            return False

    def close(self):
        self.conn.close()
        print("[DATABASE] Đã đóng kết nối CSDL.")
