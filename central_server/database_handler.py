import sqlite3
import os

class AlertDatabase:
    """
    Lớp xử lý tương tác với Cơ sở dữ liệu SQLite để lưu trữ các cảnh báo từ hệ thống.
    """
    def __init__(self, db_path="SmartFactory_IoT/logs/factory_alerts.db"):
        """
        Khởi tạo kết nối CSDL và tạo bảng nếu chưa tồn tại.
        
        Args:
            db_path (str): Đường dẫn tới file CSDL SQLite.
        """
        # Đảm bảo thư mục chứa log tồn tại
        db_dir = os.path.dirname(db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)
            
        self.db_path = db_path
        
        try:
            # Kết nối tới SQLite (file sẽ được tạo nếu chưa có)
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.cursor = self.conn.cursor()
            
            # Tạo bảng alerts nếu chưa tồn tại
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    alert_type TEXT NOT NULL
                )
            ''')
            self.conn.commit()
            print(f"[DATABASE] Đã kết nối thành công tới CSDL: {self.db_path}")
        except sqlite3.Error as e:
            print(f"[DATABASE LỖI] Không thể khởi tạo CSDL: {e}")

    def insert_alert(self, timestamp, camera_id, alert_type):
        """
        Thêm một bản ghi cảnh báo mới vào CSDL.
        
        Args:
            timestamp (str): Thời gian xảy ra cảnh báo.
            camera_id (str): ID của camera phát hiện.
            alert_type (str): Loại cảnh báo.
        """
        try:
            query = "INSERT INTO alerts (timestamp, camera_id, alert_type) VALUES (?, ?, ?)"
            self.cursor.execute(query, (timestamp, camera_id, alert_type))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"[DATABASE LỖI] Lỗi khi thêm dữ liệu: {e}")
            return False

    def close(self):
        """Đóng kết nối CSDL."""
        if self.conn:
            self.conn.close()
            print("[DATABASE] Đã đóng kết nối CSDL.")

if __name__ == "__main__":
    # Test nhanh CSDL
    db = AlertDatabase()
    db.insert_alert("2026-07-02 21:00:00", "Cam-Test", "test_connection")
    db.close()
