import feedparser
import sqlite3
import json
import os
import time

DB_PATH = 'data/sentinel.db'

def init_db():
    """
    Uygulama için gerekli veritabanını ve 'news' tablosunu başlatır.
    Tablo yapısı: id, başlık, link, yayınlanma tarihi, kaynak ve AI analizi.
    """
    if not os.path.exists('data'):
        os.makedirs('data')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            link TEXT UNIQUE,
            published TEXT,
            source TEXT,
            ai_analysis TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def fetch_rss():
    """
    sources.json içindeki tüm RSS kaynaklarını tarar ve yeni haberleri veritabanına kaydeder.
    """
    init_db()
    with open('sources.json', 'r') as f:
        sources = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for source in sources['sources']:
        print(f"[Taraniyor] {source['name']}")
        feed = feedparser.parse(source['url'])
        for entry in feed.entries:
            try:
                # Sadece yeni haberleri ekle (link UNIQUE olduğu için hata vermez, geçer)
                cursor.execute(
                    "INSERT OR IGNORE INTO news (title, link, published, source) VALUES (?, ?, ?, ?)",
                    (entry.title, entry.link, entry.get('published', 'Bilinmiyor'), source['name'])
                )
            except Exception as e:
                print(f"[Hata] Kayit hatasi: {e}")
        
    conn.commit()
    conn.close()
    print("[Tamam] Tarama tamamlandi.")

if __name__ == "__main__":
    fetch_rss()
