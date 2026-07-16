from pathlib import Path
import sqlite3
from datetime import datetime

DB_PATH = Path("data/watcher.db")

def create_movie_project(pdf_path: str, user_email: str):
    """Start a new movie project from a PDF"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO movie_projects (pdf_path, user_email, status, created_at)
        VALUES (?, ?, ?, ?)
    """, (pdf_path, user_email, "uploaded", datetime.now().isoformat()))
    
    project_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return project_id


def update_project_status(project_id: int, new_status: str):
    """Update the status of a movie project"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE movie_projects 
        SET status = ?, updated_at = ?
        WHERE id = ?
    """, (new_status, datetime.now().isoformat(), project_id))
    
    conn.commit()
    conn.close()


def get_project(project_id: int):
    """Get project details"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM movie_projects WHERE id = ?", (project_id,))
    project = cursor.fetchone()
    conn.close()
    
    return project
