import sqlite3
from datetime import datetime
from typing import List, Dict, Optional

DB_PATH = "outreach_state.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prospects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            x_user_id TEXT UNIQUE NOT NULL,
            username TEXT NOT NULL,
            display_name TEXT,
            bio TEXT,
            location TEXT,
            recent_tweets TEXT,
            is_fit INTEGER DEFAULT 1,
            fit_reason TEXT,
            evidence_quote TEXT,
            dm_text TEXT,
            status TEXT DEFAULT 'DRAFTED',
            approved_at DATETIME,
            sent_at DATETIME,
            replied_at DATETIME,
            reply_text TEXT,
            error_log TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def prospect_exists(x_user_id: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM prospects WHERE x_user_id = ?", (str(x_user_id),))
    exists = cur.fetchone() is not None
    conn.close()
    return exists


def insert_prospect(data: Dict) -> bool:
    """Chèn ứng viên mới. Trả về False nếu x_user_id đã tồn tại (chống trùng lặp)."""
    if prospect_exists(data["x_user_id"]):
        return False
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO prospects (
            x_user_id, username, display_name, bio, location,
            recent_tweets, is_fit, fit_reason, evidence_quote, dm_text, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(data["x_user_id"]),
        data["username"],
        data.get("display_name", ""),
        data.get("bio", ""),
        data.get("location", ""),
        data.get("recent_tweets", ""),
        1 if data.get("is_fit", True) else 0,
        data.get("fit_reason", ""),
        data.get("evidence_quote", ""),
        data.get("dm_text", ""),
        data.get("status", "DRAFTED"),
    ))
    conn.commit()
    conn.close()
    return True


def get_prospects_by_status(statuses: List[str]) -> List[Dict]:
    conn = get_connection()
    cur = conn.cursor()
    placeholders = ",".join("?" for _ in statuses)
    cur.execute(
        f"SELECT * FROM prospects WHERE status IN ({placeholders}) ORDER BY created_at DESC",
        statuses
    )
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def update_dm_and_approve(x_user_id: str, updated_dm: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE prospects
        SET dm_text = ?, status = 'APPROVED', approved_at = ?
        WHERE x_user_id = ? AND status IN ('DRAFTED', 'REJECTED')
    """, (updated_dm, datetime.utcnow().isoformat(), str(x_user_id)))
    conn.commit()
    conn.close()


def update_status(x_user_id: str, new_status: str, error_log: Optional[str] = None):
    conn = get_connection()
    cur = conn.cursor()
    sent_time = datetime.utcnow().isoformat() if new_status == "SENT" else None
    cur.execute("""
        UPDATE prospects
        SET status = ?,
            sent_at = COALESCE(?, sent_at),
            error_log = ?
        WHERE x_user_id = ?
    """, (new_status, sent_time, error_log, str(x_user_id)))
    conn.commit()
    conn.close()


def mark_replied(x_user_id: str, reply_text: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE prospects
        SET status = 'REPLIED', replied_at = ?, reply_text = ?
        WHERE x_user_id = ? AND status = 'SENT'
    """, (datetime.utcnow().isoformat(), reply_text, str(x_user_id)))
    conn.commit()
    conn.close()


def claim_for_sending(x_user_id: str) -> bool:
    """Khóa nguyên tử (Atomic Lock) đảm bảo 1 user chỉ được gửi đúng 1 lần duy nhất."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE prospects
        SET status = 'SENDING'
        WHERE x_user_id = ? AND status = 'APPROVED'
    """, (str(x_user_id),))
    claimed = cur.rowcount == 1
    conn.commit()
    conn.close()
    return claimed