import sqlite3
import time
import json
from core.logger import setup_logger

logger = setup_logger("Cache")
DB_PATH = 'data/sentinel.db'

def init_cache_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS intelligence_cache (
            key TEXT PRIMARY KEY,
            data TEXT,
            expiry INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def set_cache(key, data, duration=86400):
    """Veriyi belirtilen süre boyunca (varsayılan 24 saat) önbelleğe alır."""
    init_cache_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    expiry = int(time.time()) + duration
    cursor.execute("INSERT OR REPLACE INTO intelligence_cache (key, data, expiry) VALUES (?, ?, ?)", 
                   (key, json.dumps(data), expiry))
    conn.commit()
    conn.close()

def get_cache(key):
    """Önbellekten veri çeker, süresi dolmuşsa None döner."""
    init_cache_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT data, expiry FROM intelligence_cache WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        data_str, expiry = row
        if time.time() < expiry:
            logger.info(f"✅ Önbellek isabeti: {key}")
            return json.loads(data_str)
        else:
            logger.info(f"⌛ Önbellek süresi dolmuş: {key}")
    return None
