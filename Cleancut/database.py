import sqlite3
import os
if os.getenv("SPACE_ID"):
    # Running in Hugging Face Spaces: Use persistent storage
    os.makedirs("/data", exist_ok=True)
    DB_PATH = "/data/clearcut.db"
else:
    # Running locally
    DB_PATH = os.path.join(os.path.dirname(__file__), "clearcut.db")


def get_db():
    """Get a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Initialize database tables."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key VARCHAR UNIQUE NOT NULL,
            email VARCHAR NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address VARCHAR NOT NULL,
            used_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Index for fast lookups
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_license_key ON licenses(license_key)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_usage_ip_date ON usage_log(ip_address, used_at)
    """)

    conn.commit()
    conn.close()
