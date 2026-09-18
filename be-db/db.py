import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "recycling.db")

def get_guide(category):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT guide FROM recycling WHERE category = ?", (category,))
    result = cursor.fetchone()
    
    conn.close()
    
    return result[0] if result else None