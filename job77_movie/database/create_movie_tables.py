import sqlite3
from pathlib import Path

DB_PATH = Path("data/watcher.db")

def create_movie_tables():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movie_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            pdf_path TEXT,
            title TEXT,
            status TEXT DEFAULT 'uploaded',
            created_at TEXT,
            updated_at TEXT,
            final_movie_path TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movie_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            step TEXT,
            status TEXT,
            message TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()
    print("✅ Movie tables created successfully")

if __name__ == "__main__":
    create_movie_tables()
